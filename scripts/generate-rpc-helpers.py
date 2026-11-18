"""Generate the public RPC helpers from the bundled ExternalInterface descriptor."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from google.protobuf.descriptor import FieldDescriptor as Field
from google.protobuf.descriptor import MethodDescriptor

from pyddlvector.messaging.external_interface_pb2 import DESCRIPTOR

OUTPUT = Path(__file__).resolve().parents[1] / "src/pyddlvector/_external_interface.py"
FIELD_TYPES = {
    Field.TYPE_DOUBLE: "float",
    Field.TYPE_FLOAT: "float",
    Field.TYPE_INT64: "int",
    Field.TYPE_UINT64: "int",
    Field.TYPE_INT32: "int",
    Field.TYPE_FIXED64: "int",
    Field.TYPE_FIXED32: "int",
    Field.TYPE_BOOL: "bool",
    Field.TYPE_STRING: "str",
    Field.TYPE_BYTES: "bytes",
    Field.TYPE_UINT32: "int",
    Field.TYPE_ENUM: "int | str",
    Field.TYPE_SFIXED32: "int",
    Field.TYPE_SFIXED64: "int",
    Field.TYPE_SINT32: "int",
    Field.TYPE_SINT64: "int",
}


HELPER_NAMES = {
    "AlexaOptIn": "set_alexa_opt_in",
    "AppIntent": "send_app_intent",
    "AssumeBehaviorControl": "assume_behavior_control",
    "AudioFeed": "iter_audio_feed",
    "BatteryState": "get_battery_state",
    "BehaviorControl": "open_behavior_control",
    "CameraFeed": "iter_camera_feed",
    "CancelActionByIdTag": "cancel_action_by_id",
    "CubesAvailable": "list_available_cubes",
    "DisplayFaceImageRGB": "display_rgb_face_image",
    "EraseAllEnrolledFaces": "erase_all_enrolled_faces",
    "EraseEnrolledFaceByID": "erase_enrolled_face",
    "EventStream": "iter_event_responses",
    "ExternalAudioStreamPlayback": "open_audio_playback",
    "IsImageStreamingEnabled": "get_image_streaming_status",
    "NavMapFeed": "iter_nav_map_feed",
    "Photo": "get_photo",
    "PhotosInfo": "list_photos",
    "ProtocolVersion": "negotiate_protocol_version",
    "RequestEnrolledNames": "list_enrolled_faces",
    "SDKInitialization": "initialize_sdk",
    "Thumbnail": "get_photo_thumbnail",
    "UpdateEnrolledFaceByID": "rename_enrolled_face",
    "UserAuthentication": "authenticate_user",
    "VersionState": "get_firmware_version",
}


def helper_name(rpc_name: str) -> str:
    if rpc_name in HELPER_NAMES:
        return HELPER_NAMES[rpc_name]
    word_boundaries = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", rpc_name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", word_boundaries).lower()


def field_type(field: Field) -> str:
    if field.type == Field.TYPE_MESSAGE:
        if field.message_type.GetOptions().map_entry:
            key, value = field.message_type.fields
            return f"dict[{field_type(key)}, {field_type(value)}]"
        value_type = f"protocol.{field.message_type.name} | dict[str, Any]"
    else:
        value_type = FIELD_TYPES[field.type]
    if hasattr(field, "is_repeated"):
        repeated = field.is_repeated
    else:
        repeated = field.label == Field.LABEL_REPEATED
    if repeated:
        return f"Iterable[{value_type}]"
    return value_type


def helper_source(method: MethodDescriptor) -> str:
    name = helper_name(method.name)
    request = f"protocol.{method.input_type.name}"
    response = f"protocol.{method.output_type.name}"

    if method.client_streaming:
        if not method.server_streaming:
            raise ValueError(f"No helper generation rule for client-streaming RPC {method.name}")
        return f'''
    def {name}(self, *, timeout: float | None = None
    ) -> AbstractAsyncContextManager[DuplexStream[{request}, {response}]]:
        """Open the `{method.name}` stream."""
        return self._client._duplex_rpc("{method.name}", {request}, timeout=timeout)
'''

    timeout = "read_timeout" if method.server_streaming else "timeout"
    result = f"AsyncGenerator[{response}]" if method.server_streaming else response
    async_prefix = "" if method.server_streaming else "async "
    fields = method.input_type.fields
    if any(field.name in {"self", timeout} for field in fields):
        raise ValueError(f"Request field conflicts with helper signature for {method.name}")
    parameters = "".join(f"{field.name}: {field_type(field)} | None = None,\n" for field in fields)
    arguments = ", ".join(f"{field.name}={field.name}" for field in fields)
    setup = ""
    if method.name == "EventStream":
        setup = "        connection_id = connection_id or uuid4().hex\n"
    build = f"build_request({request}, {arguments})" if fields else f"{request}()"
    operation = "self._client.iter_rpc" if method.server_streaming else "await self._client.rpc"
    summary = "Stream responses from" if method.server_streaming else "Call"
    return f'''
    {async_prefix}def {name}(self, *, {parameters}{timeout}: float | None = None) -> {result}:
        """{summary} `{method.name}`."""
{setup}        request = {build}
        return {operation}("{method.name}", request, {timeout}={timeout})
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    service = DESCRIPTOR.services_by_name["ExternalInterface"]
    stale_names = HELPER_NAMES.keys() - service.methods_by_name.keys()
    if stale_names:
        raise ValueError(f"Unknown RPCs in HELPER_NAMES: {sorted(stale_names)}")
    names = [helper_name(method.name) for method in service.methods]
    if len(names) != len(set(names)):
        raise ValueError("ExternalInterface RPCs produce duplicate helper names")

    source = '''"""RPC helpers generated by scripts/generate-rpc-helpers.py."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ._rpc import DuplexStream, build_request
from .messaging import protocol

if TYPE_CHECKING:
    from .client import VectorClient


class ExternalInterface:
    """Named helpers for every RPC in the bundled Vector ExternalInterface."""

    def __init__(self, client: VectorClient) -> None:
        self._client = client
'''
    source += "".join(helper_source(method) for method in service.methods)
    generated = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--stdin-filename", str(OUTPUT), "-"],
        input=source,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != generated:
            sys.exit(
                "RPC helpers are out of date. "
                "Run poetry run python scripts/generate-rpc-helpers.py."
            )
    else:
        OUTPUT.write_text(generated)


if __name__ == "__main__":
    main()

"""Robot settings helpers."""

from __future__ import annotations

import json
from typing import Any

from .client import VectorClient
from .exceptions import VectorProtocolError, VectorRPCError
from .messaging import protocol

_PULL_JDOCS_PATH = "/Anki.Vector.external_interface.ExternalInterface/PullJdocs"
_VOLUME_OPTIONS: tuple[str, ...] = (
    "mute",
    "low",
    "medium_low",
    "medium",
    "medium_high",
    "high",
)


def normalize_master_volume(value: str) -> str:
    """Normalize a volume option string to canonical lowercase snake_case."""
    normalized = value.strip().lower().replace(" ", "_")
    if normalized in _VOLUME_OPTIONS:
        return normalized
    raise VectorProtocolError(f"Unsupported master volume option: {value}")


def _parse_master_volume_from_robot_settings_jdoc(raw_json: str) -> str:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise VectorProtocolError("Robot settings jdoc is not valid JSON") from err

    if "master_volume" not in payload:
        raise VectorProtocolError("Robot settings jdoc is missing master_volume")

    raw_value = payload["master_volume"]
    if isinstance(raw_value, str):
        candidate = raw_value.strip()
        if candidate.isdigit():
            raw_value = int(candidate)
        else:
            candidate = candidate.upper()
            if candidate.startswith("VOLUME_"):
                candidate = candidate[len("VOLUME_") :]
            return normalize_master_volume(candidate)

    if isinstance(raw_value, int):
        try:
            return normalize_master_volume(protocol.Volume.Name(raw_value))
        except ValueError as err:
            raise VectorProtocolError(
                f"Robot settings jdoc has unsupported master_volume value: {raw_value}"
            ) from err

    raise VectorProtocolError("Robot settings jdoc has invalid master_volume type")


async def fetch_master_volume(
    client: VectorClient[Any],
    *,
    timeout: float | None = None,
) -> str:
    """Fetch current master volume from robot settings jdoc."""
    request = protocol.PullJdocsRequest(jdoc_types=[protocol.ROBOT_SETTINGS])

    if hasattr(client.stub, "PullJdocs"):
        response = await client.rpc("PullJdocs", request, timeout=timeout)
    else:
        response = await client.unary_unary(
            _PULL_JDOCS_PATH,
            request,
            request_serializer=protocol.PullJdocsRequest.SerializeToString,
            response_deserializer=protocol.PullJdocsResponse.FromString,
            timeout=timeout,
        )

    for named_jdoc in response.named_jdocs:
        if named_jdoc.jdoc_type == protocol.ROBOT_SETTINGS:
            return _parse_master_volume_from_robot_settings_jdoc(named_jdoc.doc.json_doc)

    raise VectorProtocolError("ROBOT_SETTINGS jdoc was not returned by robot")


async def update_master_volume(
    client: VectorClient[Any],
    value: str,
    *,
    timeout: float | None = None,
) -> str:
    """Update robot master volume and return canonical selected option."""
    normalized = normalize_master_volume(value)

    if normalized == "mute":
        return await _update_master_volume_via_update_settings(client, normalized, timeout=timeout)

    try:
        return await _update_master_volume_via_set_master_volume(
            client,
            normalized,
            timeout=timeout,
        )
    except (VectorProtocolError, VectorRPCError) as err:
        if not _should_fallback_to_update_settings(err):
            raise
        return await _update_master_volume_via_update_settings(client, normalized, timeout=timeout)


async def _update_master_volume_via_set_master_volume(
    client: VectorClient[Any],
    normalized: str,
    *,
    timeout: float | None = None,
) -> str:
    request = protocol.MasterVolumeRequest(
        volume_level=protocol.MasterVolumeLevel.Value(f"VOLUME_{normalized.upper()}"),
    )
    await client.rpc("SetMasterVolume", request, timeout=timeout)
    return normalized


async def _update_master_volume_via_update_settings(
    client: VectorClient[Any],
    normalized: str,
    *,
    timeout: float | None = None,
) -> str:
    request = protocol.UpdateSettingsRequest(
        settings=protocol.RobotSettingsConfig(
            master_volume=protocol.Volume.Value(normalized.upper()),
        )
    )
    response = await client.rpc("UpdateSettings", request, timeout=timeout)

    accepted = protocol.ResultCode.Value("SETTINGS_ACCEPTED")
    response_code = getattr(response, "code", None)
    if response_code is not None and int(response_code) != accepted:
        raise VectorProtocolError(f"Volume update was not accepted by robot: code={response_code}")

    return normalized


def _should_fallback_to_update_settings(err: VectorProtocolError | VectorRPCError) -> bool:
    if isinstance(err, VectorProtocolError):
        return True

    status_code = getattr(err, "status_code", None)
    return str(status_code) == "StatusCode.UNIMPLEMENTED"

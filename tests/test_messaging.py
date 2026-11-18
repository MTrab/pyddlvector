"""Check that the generated gRPC stub exposes the bundled service definition."""

import re
from importlib.resources import files
from unittest.mock import Mock

from pyddlvector.messaging.external_interface_pb2 import DESCRIPTOR
from pyddlvector.messaging.external_interface_pb2_grpc import ExternalInterfaceStub


def test_stub_matches_external_interface_proto() -> None:
    source = files("pyddlvector.messaging").joinpath("external_interface.proto").read_text()
    expected = set(re.findall(r"^\s*rpc (\w+)\(", source, re.MULTILINE))
    service = DESCRIPTOR.services_by_name["ExternalInterface"]
    channel = Mock()
    stub = ExternalInterfaceStub(channel)

    assert set(service.methods_by_name) == expected
    assert set(vars(stub)) == expected
    for method in service.methods:
        input_kind = "stream" if method.client_streaming else "unary"
        output_kind = "stream" if method.server_streaming else "unary"
        factory = getattr(channel, f"{input_kind}_{output_kind}")
        assert any(
            call.args[0] == f"/{service.full_name}/{method.name}" for call in factory.call_args_list
        )

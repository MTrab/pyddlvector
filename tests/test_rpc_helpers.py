"""RPC helper coverage and wire request construction."""

from __future__ import annotations

import asyncio
import inspect
import re
from contextlib import aclosing
from typing import get_type_hints

import grpc
import pytest
from google.protobuf.message_factory import GetMessageClass

from pyddlvector import RobotConfig, VectorClient, VectorProtocolError, VectorTimeoutError
from pyddlvector._external_interface import ExternalInterface
from pyddlvector.messaging import protocol
from pyddlvector.messaging.external_interface_pb2 import DESCRIPTOR

SERVICE = DESCRIPTOR.services_by_name["ExternalInterface"]
HELPERS = {
    re.search(r"`(\w+)`", method.__doc__)[1]: name
    for name, method in inspect.getmembers(ExternalInterface, inspect.isfunction)
    if not name.startswith("_")
}


class FakeStream:
    def __init__(self, response):
        self.responses = iter((response, grpc.aio.EOF))
        self.requests = []
        self.writing_finished = False
        self.cancelled = False

    async def read(self):
        return next(self.responses)

    async def write(self, request):
        self.requests.append(request)

    async def done_writing(self):
        self.writing_finished = True

    def cancel(self):
        self.cancelled = True


@pytest.fixture
def client() -> VectorClient:
    return VectorClient(
        RobotConfig.from_runtime(name="Vector-Test", ip="127.0.0.1", guid="test", cert_pem=b"test")
    )


def test_rpc_helpers_cover_service_once() -> None:
    public = [name for name in vars(ExternalInterface) if not name.startswith("_")]
    assert len(public) == len(HELPERS)
    assert HELPERS.keys() == set(SERVICE.methods_by_name)


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", SERVICE.methods_by_name)
async def test_rpc_helper_dispatches_request(
    client: VectorClient, monkeypatch: pytest.MonkeyPatch, method_name: str
) -> None:
    descriptor = SERVICE.methods_by_name[method_name]
    expected_response = GetMessageClass(descriptor.output_type)()
    expected_request_type = GetMessageClass(descriptor.input_type)
    stream = FakeStream(expected_response)
    calls = []

    async def unary(request, *, timeout):
        calls.append(request)
        assert timeout == 2.0
        return expected_response

    def server_stream(request):
        calls.append(request)
        return stream

    def duplex():
        return stream

    def get_rpc(name):
        assert name == method_name
        if descriptor.client_streaming:
            return duplex
        return server_stream if descriptor.server_streaming else unary

    monkeypatch.setattr(client, "_get_rpc", get_rpc)
    method = getattr(client.api, HELPERS[method_name])
    get_type_hints(method)
    parameters = inspect.signature(method).parameters.keys()

    if descriptor.client_streaming:
        assert set(parameters) == {"timeout"}
        async with method(timeout=2.0) as session:
            await session.send()
            await session.finish_sending()
            assert [response async for response in session] == [expected_response]
        assert stream.writing_finished
        assert stream.cancelled
        assert isinstance(stream.requests[0], expected_request_type)
        return

    timeout_name = "read_timeout" if descriptor.server_streaming else "timeout"
    assert set(parameters) == {timeout_name, *descriptor.input_type.fields_by_name}
    if descriptor.server_streaming:
        async with aclosing(method(read_timeout=2.0)) as responses:
            assert [response async for response in responses] == [expected_response]
        assert stream.cancelled
    else:
        assert await method(timeout=2.0) == expected_response

    assert len(calls) == 1
    assert isinstance(calls[0], expected_request_type)


@pytest.mark.asyncio
async def test_rpc_helpers_build_nested_settings_and_repeated_enums(
    client: VectorClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {}

    def get_rpc(name):
        async def call(request, *, timeout):
            calls[name] = request

        return call

    monkeypatch.setattr(client, "_get_rpc", get_rpc)
    await client.api.update_settings(settings={"master_volume": "MUTE", "clock_24_hour": False})
    await client.api.pull_jdocs(jdoc_types=["ROBOT_SETTINGS", protocol.ROBOT_LIFETIME_STATS])

    settings = calls["UpdateSettings"].settings
    assert settings.HasField("master_volume")
    assert settings.HasField("clock_24_hour")
    assert settings.master_volume == protocol.Volume.MUTE
    assert list(calls["PullJdocs"].jdoc_types) == [0, 1]


@pytest.mark.asyncio
async def test_event_helper_uses_sdk_connection_id_and_rejects_conflicting_filters(
    client: VectorClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = []

    def event_stream(request):
        requests.append(request)
        return FakeStream(protocol.EventResponse())

    monkeypatch.setattr(client, "_get_rpc", lambda name: event_stream)
    for _ in range(2):
        async with aclosing(
            client.api.iter_event_responses(white_list={"list": ["robot_state"]})
        ) as responses:
            await anext(responses)

    assert requests[0].connection_id
    assert requests[0].connection_id != requests[1].connection_id
    assert list(requests[0].white_list.list) == ["robot_state"]
    with pytest.raises(VectorProtocolError, match="list_type"):
        client.api.iter_event_responses(white_list={}, black_list={})


@pytest.mark.asyncio
async def test_duplex_reads_and_writes_concurrently_and_cancels_after_timeout(
    client: VectorClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ControlStream(FakeStream):
        def __init__(self):
            super().__init__(None)
            self.granted = asyncio.Event()

        async def write(self, request):
            await super().write(request)
            self.granted.set()

        async def read(self):
            await self.granted.wait()
            self.granted.clear()
            return protocol.BehaviorControlResponse(
                control_granted_response=protocol.ControlGrantedResponse()
            )

    call = ControlStream()
    monkeypatch.setattr(client, "_get_rpc", lambda name: lambda: call)
    async with client.api.open_behavior_control(timeout=0.1) as stream:
        with pytest.raises(VectorProtocolError, match="request_type"):
            await stream.send(control_request={}, control_release={})
        response, _ = await asyncio.gather(
            stream.read(),
            stream.send(control_request={"priority": "DEFAULT"}),
        )
        assert response.HasField("control_granted_response")
        assert call.requests[0].control_request.priority == protocol.ControlRequest.DEFAULT

        with pytest.raises(VectorTimeoutError, match="BehaviorControl"):
            await stream.read()
        assert call.cancelled

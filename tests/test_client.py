from __future__ import annotations

import asyncio
from contextlib import aclosing
from pathlib import Path
from typing import Any

import grpc
import pytest

from pyddlvector.client import VectorClient
from pyddlvector.config import RobotConfig
from pyddlvector.exceptions import (
    VectorAuthenticationError,
    VectorConfigurationError,
    VectorConnectionError,
    VectorProtocolError,
    VectorRPCError,
    VectorTimeoutError,
)
from pyddlvector.messaging import protocol


class FakeChannel:
    def __init__(self) -> None:
        self.closed = False
        self.should_timeout = False

    async def channel_ready(self) -> None:
        if self.should_timeout:
            raise TimeoutError

    async def close(self) -> None:
        self.closed = True


class FakeStub:
    def __init__(self) -> None:
        self.sdk_init_request: object | None = None
        self.sdk_init_timeout: float | None = None
        self.protocol_request: object | None = None
        self.protocol_timeout: float | None = None

    async def SDKInitialization(
        self,
        request: object,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.sdk_init_request = request
        self.sdk_init_timeout = timeout
        return {"ok": True}

    async def ProtocolVersion(
        self,
        request: object,
        *,
        timeout: float | None = None,
    ) -> protocol.ProtocolVersionResponse:
        self.protocol_request = request
        self.protocol_timeout = timeout
        return protocol.ProtocolVersionResponse(
            result=protocol.ProtocolVersionResponse.SUCCESS,
            host_version=protocol.PROTOCOL_VERSION_CURRENT,
        )

    async def Echo(
        self,
        request: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return {"request": request, "timeout": timeout}

    async def FailingRpc(
        self,
        request: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        del request, timeout
        raise FakeUnauthenticatedRpcError()


class FakeUnauthenticatedRpcError(grpc.RpcError):
    def code(self) -> grpc.StatusCode:
        return grpc.StatusCode.UNAUTHENTICATED

    def details(self) -> str:
        return "bad token"


class FakeInternalRpcError(grpc.RpcError):
    def code(self) -> grpc.StatusCode:
        return grpc.StatusCode.INTERNAL

    def details(self) -> str:
        return "internal"


class FakeUnimplementedRpcError(grpc.RpcError):
    def code(self) -> grpc.StatusCode:
        return grpc.StatusCode.UNIMPLEMENTED

    def details(self) -> str:
        return "unimplemented"


@pytest.fixture
def robot_config(tmp_path: Path) -> RobotConfig:
    cert_file = tmp_path / "robot.cert"
    cert_file.write_bytes(b"cert-bytes")
    return RobotConfig(
        serial="00e20100",
        name="Vector-A1B2",
        ip="192.168.1.10",
        guid="my-guid",
        cert_file=cert_file,
    )


def _patch_grpc(monkeypatch: pytest.MonkeyPatch, fake_channel: FakeChannel) -> None:
    monkeypatch.setattr(
        "pyddlvector.client.grpc.ssl_channel_credentials",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr("pyddlvector.client.grpc.access_token_call_credentials", lambda guid: guid)
    monkeypatch.setattr(
        "pyddlvector.client.grpc.composite_channel_credentials",
        lambda channel_creds, call_creds: (channel_creds, call_creds),
    )
    monkeypatch.setattr(
        "pyddlvector.client.grpc.aio.secure_channel",
        lambda host, creds, options=(): fake_channel,
    )


@pytest.mark.asyncio
async def test_connect_and_rpc_success(
    monkeypatch: pytest.MonkeyPatch,
    robot_config: RobotConfig,
) -> None:
    fake_channel = FakeChannel()
    _patch_grpc(monkeypatch, fake_channel)

    client = VectorClient(robot_config, stub_factory=lambda channel: FakeStub())
    await client.connect()

    response = await client.rpc("Echo", {"type": "ping"})
    assert response["request"] == {"type": "ping"}
    assert response["timeout"] == 10.0

    await client.disconnect()
    assert fake_channel.closed is True


@pytest.mark.asyncio
async def test_connect_calls_sdk_initialization_when_supported(
    monkeypatch: pytest.MonkeyPatch,
    robot_config: RobotConfig,
) -> None:
    fake_channel = FakeChannel()
    _patch_grpc(monkeypatch, fake_channel)
    stub = FakeStub()

    client = VectorClient(robot_config, stub_factory=lambda channel: stub)
    await client.connect()

    assert stub.sdk_init_request is not None
    assert stub.sdk_init_timeout == 10.0
    assert stub.protocol_request is not None
    assert stub.protocol_timeout == 10.0


@pytest.mark.asyncio
async def test_connect_ignores_unimplemented_sdk_initialization(
    monkeypatch: pytest.MonkeyPatch,
    robot_config: RobotConfig,
) -> None:
    fake_channel = FakeChannel()
    _patch_grpc(monkeypatch, fake_channel)

    class UnimplementedInitStub(FakeStub):
        async def SDKInitialization(
            self,
            request: object,
            *,
            timeout: float | None = None,
        ) -> dict[str, Any]:
            del request, timeout
            raise FakeUnimplementedRpcError()

    client = VectorClient(robot_config, stub_factory=lambda channel: UnimplementedInitStub())
    await client.connect()
    assert client.connected is True


@pytest.mark.asyncio
async def test_connect_requires_cert_file(tmp_path: Path) -> None:
    config = RobotConfig(
        serial="00e20100",
        name="Vector-A1B2",
        ip="192.168.1.10",
        guid="my-guid",
        cert_file=tmp_path / "missing.cert",
    )
    client = VectorClient(config, stub_factory=lambda channel: FakeStub())

    with pytest.raises(VectorConfigurationError):
        await client.connect()


@pytest.mark.asyncio
async def test_rpc_requires_connected_client(robot_config: RobotConfig) -> None:
    client = VectorClient(robot_config, stub_factory=lambda channel: FakeStub())

    with pytest.raises(VectorConnectionError):
        await client.rpc("Echo", {})


@pytest.mark.asyncio
async def test_missing_method_raises_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
    robot_config: RobotConfig,
) -> None:
    fake_channel = FakeChannel()
    _patch_grpc(monkeypatch, fake_channel)

    client = VectorClient(robot_config, stub_factory=lambda channel: FakeStub())
    await client.connect()

    with pytest.raises(VectorProtocolError):
        await client.rpc("NotARealMethod", {})


@pytest.mark.asyncio
async def test_unauthenticated_rpc_maps_to_auth_error(
    monkeypatch: pytest.MonkeyPatch,
    robot_config: RobotConfig,
) -> None:
    fake_channel = FakeChannel()
    _patch_grpc(monkeypatch, fake_channel)

    client = VectorClient(robot_config, stub_factory=lambda channel: FakeStub())
    await client.connect()

    with pytest.raises(VectorAuthenticationError):
        await client.rpc("FailingRpc", {})


@pytest.mark.asyncio
async def test_non_auth_rpc_maps_to_generic_rpc_error(
    monkeypatch: pytest.MonkeyPatch,
    robot_config: RobotConfig,
) -> None:
    fake_channel = FakeChannel()
    _patch_grpc(monkeypatch, fake_channel)

    class InternalStub(FakeStub):
        async def FailingRpc(
            self,
            request: dict[str, Any],
            *,
            timeout: float | None = None,
        ) -> dict[str, Any]:
            del request, timeout
            raise FakeInternalRpcError()

    client = VectorClient(robot_config, stub_factory=lambda channel: InternalStub())
    await client.connect()

    with pytest.raises(VectorRPCError):
        await client.rpc("FailingRpc", {})


@pytest.mark.asyncio
async def test_connect_timeout_maps_to_vector_timeout(
    monkeypatch: pytest.MonkeyPatch,
    robot_config: RobotConfig,
) -> None:
    fake_channel = FakeChannel()

    async def timed_out_channel_ready() -> None:
        raise TimeoutError

    fake_channel.channel_ready = timed_out_channel_ready
    _patch_grpc(monkeypatch, fake_channel)

    client = VectorClient(robot_config, stub_factory=lambda channel: FakeStub())
    with pytest.raises(VectorTimeoutError):
        await client.connect(timeout=0.01)


@pytest.mark.asyncio
async def test_connect_with_runtime_inline_cert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_channel = FakeChannel()
    _patch_grpc(monkeypatch, fake_channel)

    runtime_config = RobotConfig.from_runtime(
        serial="00908e7e",
        name="Vector-T3X9",
        ip="192.168.1.201",
        guid="my-guid",
        cert_pem=b"fake-pem-data",
    )
    client = VectorClient(runtime_config, stub_factory=lambda channel: FakeStub())

    await client.connect()
    assert client.connected is True


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_handshake", [False, True])
async def test_connect_and_disconnect_during_handshake(
    monkeypatch: pytest.MonkeyPatch, robot_config: RobotConfig, cancel_handshake: bool
) -> None:
    handshake_started = asyncio.Event()
    handshake_can_finish = asyncio.Event()
    channels = []

    class PendingStub(FakeStub):
        async def ProtocolVersion(self, request, *, timeout):
            handshake_started.set()
            await handshake_can_finish.wait()
            return await super().ProtocolVersion(request, timeout=timeout)

    def open_channel(*args, **kwargs):
        channels.append(FakeChannel())
        return channels[-1]

    _patch_grpc(monkeypatch, FakeChannel())
    monkeypatch.setattr(grpc.aio, "secure_channel", open_channel)
    client = VectorClient(robot_config, stub_factory=lambda channel: PendingStub())
    first = asyncio.create_task(client.connect())
    await handshake_started.wait()
    second = asyncio.create_task(client.connect())
    close = asyncio.create_task(client.disconnect())
    await asyncio.sleep(0)
    assert not client.connected
    assert len(channels) == 1

    if cancel_handshake:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

    handshake_can_finish.set()
    await asyncio.gather(second, close)
    if not cancel_handshake:
        await first
    assert not client.connected
    assert len(channels) == (2 if cancel_handshake else 1)
    assert all(channel.closed for channel in channels)


@pytest.mark.asyncio
async def test_failed_stub_construction_closes_channel(
    monkeypatch: pytest.MonkeyPatch, robot_config: RobotConfig
) -> None:
    def broken_stub(channel):
        raise RuntimeError("stub failed")

    channel = FakeChannel()
    _patch_grpc(monkeypatch, channel)
    client = VectorClient(robot_config, stub_factory=broken_stub)
    with pytest.raises(RuntimeError, match="stub failed"):
        await client.connect()
    assert channel.closed
    assert not client.connected


@pytest.mark.asyncio
async def test_event_stream_preserves_filter_and_sets_unique_id(
    monkeypatch: pytest.MonkeyPatch, robot_config: RobotConfig
) -> None:
    class EventStream:
        closed = False

        def __init__(self):
            self.responses = iter(
                [
                    protocol.EventResponse(),
                    protocol.EventResponse(event=protocol.Event(robot_state=protocol.RobotState())),
                    grpc.aio.EOF,
                ]
            )

        async def read(self):
            return next(self.responses)

        def cancel(self):
            self.closed = True

    class EventStub(FakeStub):
        def __init__(self):
            super().__init__()
            self.requests = []
            self.streams = []

        def EventStream(self, request):
            self.requests.append(request)
            self.streams.append(EventStream())
            return self.streams[-1]

    _patch_grpc(monkeypatch, FakeChannel())
    stub = EventStub()
    client = VectorClient(robot_config, stub_factory=lambda channel: stub)
    await client.connect()
    request = protocol.EventRequest(white_list=protocol.FilterList(list=["robot_state"]))

    async with aclosing(client.iter_events(request)) as events:
        assert (await anext(events)).WhichOneof("event_type") == "robot_state"
    assert len([event async for event in client.iter_events(request)]) == 1

    assert request.connection_id == ""
    assert stub.requests[0].white_list == request.white_list
    assert stub.requests[0].connection_id
    assert stub.requests[0].connection_id != stub.requests[1].connection_id
    assert all(stream.closed for stream in stub.streams)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "revoked", "cancelled"])
async def test_behavior_control_releases_after_command_or_control_loss(
    monkeypatch: pytest.MonkeyPatch, robot_config: RobotConfig, outcome: str
) -> None:
    command_started = asyncio.Event()
    command_finished = asyncio.Event()
    command_stopped = asyncio.Event()

    class ControlStream:
        closed = False

        def __init__(self):
            self.requests = []
            self.responses = asyncio.Queue()

        async def write(self, request):
            self.requests.append(request.WhichOneof("request_type"))
            if self.requests == ["control_request"]:
                self.responses.put_nowait(
                    protocol.BehaviorControlResponse(keep_alive=protocol.KeepAlivePing())
                )
                self.responses.put_nowait(
                    protocol.BehaviorControlResponse(
                        control_granted_response=protocol.ControlGrantedResponse()
                    )
                )
            else:
                self.revoke()

        def revoke(self):
            self.responses.put_nowait(
                protocol.BehaviorControlResponse(control_lost_event=protocol.ControlLostResponse())
            )

        async def read(self):
            return await self.responses.get()

        async def done_writing(self):
            pass

        def done(self):
            return self.closed

        def cancel(self):
            self.closed = True

    class ControlStub(FakeStub):
        stream = ControlStream()

        def BehaviorControl(self):
            return self.stream

        async def SayText(self, request, *, timeout):
            command_started.set()
            try:
                await command_finished.wait()
                return protocol.SayTextResponse()
            finally:
                command_stopped.set()

    _patch_grpc(monkeypatch, FakeChannel())
    stub = ControlStub()
    client = VectorClient(robot_config, stub_factory=lambda channel: stub)
    await client.connect()
    command = asyncio.create_task(
        client.run_with_behavior_control("SayText", protocol.SayTextRequest(text="test"))
    )
    await command_started.wait()

    if outcome == "revoked":
        stub.stream.revoke()
        with pytest.raises(VectorProtocolError, match="revoked"):
            await command
    elif outcome == "cancelled":
        command.cancel()
        with pytest.raises(asyncio.CancelledError):
            await command
    else:
        command_finished.set()
        assert await command == protocol.SayTextResponse()

    assert command_stopped.is_set()
    assert stub.stream.requests == ["control_request", "control_release"]
    assert stub.stream.closed

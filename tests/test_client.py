from __future__ import annotations

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

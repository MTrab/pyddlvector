"""Async gRPC client for Vector robots."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Generic, TypeVar

import grpc

from .config import RobotConfig
from .exceptions import (
    VectorAuthenticationError,
    VectorConnectionError,
    VectorProtocolError,
    VectorRPCError,
    VectorTimeoutError,
)

StubT = TypeVar("StubT")
ResponseT = TypeVar("ResponseT")


class VectorClient(Generic[StubT]):
    """Maintains an authenticated gRPC channel to one Vector robot."""

    def __init__(
        self,
        robot: RobotConfig,
        *,
        stub_factory: Callable[[grpc.aio.Channel], StubT],
        default_timeout: float = 10.0,
        channel_options: tuple[tuple[str, Any], ...] = (),
    ) -> None:
        self._robot = robot
        self._stub_factory = stub_factory
        self._default_timeout = default_timeout
        self._channel_options = channel_options
        self._channel: grpc.aio.Channel | None = None
        self._stub: StubT | None = None

    @property
    def robot(self) -> RobotConfig:
        """Robot configuration backing this client."""
        return self._robot

    @property
    def connected(self) -> bool:
        """Whether a channel and stub are currently active."""
        return self._channel is not None and self._stub is not None

    @property
    def stub(self) -> StubT:
        """Return the bound gRPC stub when connected."""
        if self._stub is None:
            raise VectorConnectionError("Client is not connected")
        return self._stub

    async def connect(self, *, timeout: float | None = None) -> None:
        """Open TLS/authenticated gRPC channel using cert + guid from config."""
        if self.connected:
            return

        trusted_certs = self._robot.trusted_certs()

        channel_credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)
        call_credentials = grpc.access_token_call_credentials(self._robot.guid)
        credentials = grpc.composite_channel_credentials(channel_credentials, call_credentials)

        options = (("grpc.ssl_target_name_override", self._robot.name),) + self._channel_options
        channel = grpc.aio.secure_channel(self._robot.host, credentials, options=options)

        effective_timeout = timeout if timeout is not None else self._default_timeout
        try:
            await asyncio.wait_for(channel.channel_ready(), timeout=effective_timeout)
        except TimeoutError as err:
            await channel.close()
            raise VectorTimeoutError(
                f"Timed out connecting to {self._robot.host} after {effective_timeout:.2f}s"
            ) from err
        except Exception:
            await channel.close()
            raise

        self._channel = channel
        self._stub = self._stub_factory(channel)

    async def disconnect(self) -> None:
        """Close the active channel and clear stub references."""
        channel = self._channel
        self._stub = None
        self._channel = None

        if channel is not None:
            await channel.close()

    async def rpc(
        self,
        method_name: str,
        request: Any,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Call a unary RPC by method name on the configured stub."""
        if not self.connected:
            raise VectorConnectionError("Client is not connected")

        method = getattr(self.stub, method_name, None)
        if method is None:
            raise VectorProtocolError(f"Stub does not expose RPC method '{method_name}'")
        if not callable(method):
            raise VectorProtocolError(f"Stub attribute '{method_name}' is not callable")

        effective_timeout = timeout if timeout is not None else self._default_timeout
        try:
            return await method(request, timeout=effective_timeout)
        except TimeoutError as err:
            raise VectorTimeoutError(
                f"RPC '{method_name}' timed out after {effective_timeout:.2f}s"
            ) from err
        except grpc.RpcError as err:
            raise _map_rpc_error(err, method_name) from err

    async def run(
        self,
        rpc: Callable[..., Awaitable[ResponseT]],
        request: Any,
        *,
        timeout: float | None = None,
    ) -> ResponseT:
        """Call a provided stub method directly for typed usage in integrations."""
        if not self.connected:
            raise VectorConnectionError("Client is not connected")

        effective_timeout = timeout if timeout is not None else self._default_timeout
        try:
            return await rpc(request, timeout=effective_timeout)
        except TimeoutError as err:
            raise VectorTimeoutError(f"RPC call timed out after {effective_timeout:.2f}s") from err
        except grpc.RpcError as err:
            raise _map_rpc_error(err, getattr(rpc, "__name__", "<rpc>")) from err


def _map_rpc_error(
    error: grpc.RpcError,
    method_name: str,
) -> VectorRPCError | VectorAuthenticationError:
    status_code = None
    details = None

    if hasattr(error, "code"):
        status_code = error.code()
    if hasattr(error, "details"):
        details = error.details()

    message = f"RPC '{method_name}' failed"
    if status_code is not None:
        message = f"{message} with status {status_code}"

    if status_code == grpc.StatusCode.UNAUTHENTICATED:
        return VectorAuthenticationError("Authentication failed for robot RPC call")

    return VectorRPCError(message, status_code=status_code, details=details)

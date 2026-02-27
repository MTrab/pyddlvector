"""Async gRPC client for Vector robots."""

from __future__ import annotations

import asyncio
import platform
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
        try:
            await self._maybe_protocol_handshake(timeout=effective_timeout)
            await self._maybe_sdk_initialize(timeout=effective_timeout)
        except Exception:
            self._stub = None
            self._channel = None
            await channel.close()
            raise

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

    async def unary_unary(
        self,
        path: str,
        request: Any,
        *,
        request_serializer: Callable[[Any], bytes],
        response_deserializer: Callable[[bytes], ResponseT],
        timeout: float | None = None,
    ) -> ResponseT:
        """Invoke a unary gRPC endpoint by fully-qualified RPC path."""
        if not self.connected or self._channel is None:
            raise VectorConnectionError("Client is not connected")

        effective_timeout = timeout if timeout is not None else self._default_timeout
        rpc = self._channel.unary_unary(
            path,
            request_serializer=request_serializer,
            response_deserializer=response_deserializer,
        )
        try:
            return await rpc(request, timeout=effective_timeout)
        except TimeoutError as err:
            raise VectorTimeoutError(
                f"RPC '{path}' timed out after {effective_timeout:.2f}s"
            ) from err
        except grpc.RpcError as err:
            raise _map_rpc_error(err, path) from err

    async def _maybe_sdk_initialize(self, *, timeout: float) -> None:
        """Send SDK initialization metadata when supported by the bound stub."""
        method = getattr(self.stub, "SDKInitialization", None)
        if method is None:
            return
        if not callable(method):
            raise VectorProtocolError("Stub attribute 'SDKInitialization' is not callable")

        request = _build_sdk_initialization_request()
        try:
            await method(request, timeout=timeout)
        except TimeoutError as err:
            raise VectorTimeoutError(
                f"RPC 'SDKInitialization' timed out after {timeout:.2f}s"
            ) from err
        except grpc.RpcError as err:
            if err.code() == grpc.StatusCode.UNIMPLEMENTED:
                return
            raise _map_rpc_error(err, "SDKInitialization") from err

    async def _maybe_protocol_handshake(self, *, timeout: float) -> None:
        """Negotiate protocol version when supported by the bound stub."""
        method = getattr(self.stub, "ProtocolVersion", None)
        if method is None:
            return
        if not callable(method):
            raise VectorProtocolError("Stub attribute 'ProtocolVersion' is not callable")

        request = _build_protocol_version_request()
        if request is None:
            return
        try:
            response = await method(request, timeout=timeout)
        except TimeoutError as err:
            raise VectorTimeoutError(
                f"RPC 'ProtocolVersion' timed out after {timeout:.2f}s"
            ) from err
        except grpc.RpcError as err:
            if err.code() == grpc.StatusCode.UNIMPLEMENTED:
                return
            raise _map_rpc_error(err, "ProtocolVersion") from err

        # Match SDK expectation when response shape includes result enum.
        if hasattr(response, "result") and hasattr(request, "min_host_version"):
            result = int(getattr(response, "result", 0))
            success = int(getattr(_messaging_protocol().ProtocolVersionResponse, "SUCCESS", 1))
            if result != success:
                raise VectorProtocolError("Robot rejected protocol version negotiation")
            host_version = int(getattr(response, "host_version", 0))
            min_host_version = int(getattr(request, "min_host_version", 0))
            if host_version < min_host_version:
                raise VectorProtocolError("Robot host protocol version is too old")


def _build_sdk_initialization_request() -> Any:
    protocol = _messaging_protocol()

    return protocol.SDKInitializationRequest(
        sdk_module_version=_module_version(),
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        os_version=platform.platform(),
        cpu_version=platform.machine(),
    )


def _module_version() -> str:
    # Keep this non-blocking for asyncio integrations (e.g. Home Assistant).
    return "0.1.0"


def _build_protocol_version_request() -> Any | None:
    protocol = _messaging_protocol()
    if not hasattr(protocol, "ProtocolVersionRequest"):
        return None
    return protocol.ProtocolVersionRequest(
        client_version=getattr(protocol, "PROTOCOL_VERSION_CURRENT", 0),
        min_host_version=getattr(protocol, "PROTOCOL_VERSION_MINIMUM", 0),
    )


def _messaging_protocol() -> Any:
    from . import messaging

    return messaging.protocol


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

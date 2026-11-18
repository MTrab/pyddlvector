"""Async gRPC client for Vector robots."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing, asynccontextmanager, suppress
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from uuid import uuid4

import grpc

from ._rpc import DuplexStream, RequestT, _map_rpc_error
from .config import RobotConfig
from .exceptions import (
    VectorAuthenticationError,
    VectorConnectionError,
    VectorProtocolError,
    VectorTimeoutError,
)
from .messaging import protocol
from .messaging.external_interface_pb2_grpc import ExternalInterfaceStub

if TYPE_CHECKING:
    from ._external_interface import ExternalInterface

StubT = TypeVar("StubT", default=ExternalInterfaceStub)
ResponseT = TypeVar("ResponseT")


class VectorClient(Generic[StubT]):
    """Maintains an authenticated gRPC channel to one Vector robot."""

    def __init__(
        self,
        robot: RobotConfig,
        *,
        stub_factory: Callable[[grpc.aio.Channel], StubT] | None = None,
        default_timeout: float = 10.0,
        channel_options: tuple[tuple[str, Any], ...] = (),
    ) -> None:
        from ._external_interface import ExternalInterface

        self._robot = robot
        self._stub_factory = (
            stub_factory
            if stub_factory is not None
            else cast(Callable[[grpc.aio.Channel], StubT], ExternalInterfaceStub)
        )
        self._api = ExternalInterface(self)
        self._default_timeout = default_timeout
        self._channel_options = channel_options
        self._lifecycle_lock = asyncio.Lock()
        self._control_lock = asyncio.Lock()
        self._channel: grpc.aio.Channel | None = None
        self._stub: StubT | None = None

    @property
    def api(self) -> ExternalInterface:
        """Named helpers for the bundled ExternalInterface RPCs."""
        return self._api

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
        async with self._lifecycle_lock:
            if self.connected:
                return

            trusted_certs = await asyncio.to_thread(self._robot.trusted_certs)
            channel_credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)
            call_credentials = grpc.access_token_call_credentials(self._robot.guid)
            credentials = grpc.composite_channel_credentials(channel_credentials, call_credentials)

            options = self._channel_options + (("grpc.ssl_target_name_override", self._robot.name),)
            channel = grpc.aio.secure_channel(self._robot.host, credentials, options=options)
            effective_timeout = timeout if timeout is not None else self._default_timeout

            try:
                try:
                    await asyncio.wait_for(channel.channel_ready(), timeout=effective_timeout)
                except TimeoutError as err:
                    raise VectorTimeoutError(
                        f"Timed out opening the robot gRPC channel after {effective_timeout:.2f}s"
                    ) from err

                stub = self._stub_factory(channel)
                response = await self._handshake_rpc(
                    stub,
                    "ProtocolVersion",
                    protocol.ProtocolVersionRequest(
                        client_version=protocol.PROTOCOL_VERSION_CURRENT,
                        min_host_version=protocol.PROTOCOL_VERSION_MINIMUM,
                    ),
                    effective_timeout,
                )
                if response is not None:
                    if response.result != protocol.ProtocolVersionResponse.SUCCESS:
                        raise VectorProtocolError("Robot rejected protocol version negotiation")
                    if response.host_version < protocol.PROTOCOL_VERSION_MINIMUM:
                        raise VectorProtocolError("Robot host protocol version is too old")

                response = await self._handshake_rpc(
                    stub,
                    "SDKInitialization",
                    await asyncio.to_thread(_build_sdk_initialization_request),
                    effective_timeout,
                )
                _check_response_status(response, "SDKInitialization")
                self._channel, self._stub = channel, stub
            finally:
                if self._channel is not channel:
                    await channel.close()

    async def disconnect(self) -> None:
        """Close the active channel and clear stub references."""
        async with self._lifecycle_lock:
            channel = self._channel
            self._channel = None
            self._stub = None
            if channel is not None:
                await channel.close()

    def _get_rpc(self, method_name: str) -> Callable[..., Any]:
        method = getattr(self.stub, method_name, None)
        if not callable(method):
            raise VectorProtocolError(f"Stub does not expose callable RPC '{method_name}'")
        return method

    async def rpc(
        self,
        method_name: str,
        request: Any,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Call a unary RPC by method name on the configured stub."""
        return await self._call_unary(
            self._get_unary_rpc(method_name), method_name, request, timeout
        )

    def _get_unary_rpc(self, method_name: str) -> Callable[..., Awaitable[Any]]:
        method = self._get_rpc(method_name)
        if isinstance(
            method, grpc.aio.UnaryStreamMultiCallable | grpc.aio.StreamStreamMultiCallable
        ):
            raise VectorProtocolError(f"RPC '{method_name}' returns a stream")
        return method

    async def _call_unary(
        self,
        method: Callable[..., Awaitable[ResponseT]],
        method_name: str,
        request: Any,
        timeout: float | None,
    ) -> ResponseT:
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

        return await self._call_unary(rpc, getattr(rpc, "__name__", "<rpc>"), request, timeout)

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

        rpc = self._channel.unary_unary(
            path,
            request_serializer=request_serializer,
            response_deserializer=response_deserializer,
        )
        return await self._call_unary(rpc, path, request, timeout)

    async def iter_rpc(
        self,
        method_name: str,
        request: Any,
        *,
        read_timeout: float | None = None,
    ) -> AsyncGenerator[Any]:
        """Read a server stream with an idle timeout and cancel it on close."""
        method = self._get_rpc(method_name)
        if isinstance(
            method,
            grpc.aio.UnaryUnaryMultiCallable
            | grpc.aio.StreamUnaryMultiCallable
            | grpc.aio.StreamStreamMultiCallable,
        ):
            raise VectorProtocolError(f"RPC '{method_name}' is not a server-streaming RPC")
        effective_timeout = read_timeout if read_timeout is not None else self._default_timeout
        stream = method(request)
        try:
            while True:
                response = await asyncio.wait_for(stream.read(), effective_timeout)
                if response is grpc.aio.EOF:
                    return
                yield response
        except TimeoutError as err:
            raise VectorTimeoutError(f"RPC '{method_name}' stopped sending responses") from err
        except grpc.RpcError as err:
            raise _map_rpc_error(err, method_name) from err
        finally:
            stream.cancel()

    @asynccontextmanager
    async def _duplex_rpc(
        self,
        method_name: str,
        request_type: type[RequestT],
        *,
        timeout: float | None,
    ) -> AsyncGenerator[DuplexStream[RequestT, Any]]:
        method = self._get_rpc(method_name)
        idle_timeout = self._default_timeout if timeout is None else timeout
        call = method()
        try:
            yield DuplexStream(call, method_name, request_type, idle_timeout)
        finally:
            call.cancel()

    async def iter_events(
        self,
        request: protocol.EventRequest | None = None,
        *,
        read_timeout: float | None = None,
    ) -> AsyncGenerator[protocol.Event]:
        """Read EventStream payloads using a unique connection ID by default."""
        event_request = protocol.EventRequest()
        if request is not None:
            event_request.CopyFrom(request)
        if not event_request.connection_id:
            event_request.connection_id = uuid4().hex
        async with aclosing(
            self.iter_rpc("EventStream", event_request, read_timeout=read_timeout)
        ) as responses:
            async for response in responses:
                _check_response_status(response, "EventStream")
                if response.event.WhichOneof("event_type") is not None:
                    yield response.event

    async def run_with_behavior_control(
        self,
        method_name: str,
        request: Any,
        *,
        priority: int = protocol.ControlRequest.DEFAULT,
        timeout: float | None = None,
    ) -> Any:
        """Run one unary RPC after control is granted and release control on exit."""
        effective_timeout = timeout if timeout is not None else self._default_timeout
        async with self._control_lock:
            method = self._get_unary_rpc(method_name)
            stream = self._get_rpc("BehaviorControl")()
            command = None
            loss = None
            try:
                async with asyncio.timeout(effective_timeout):
                    await stream.write(
                        protocol.BehaviorControlRequest(
                            control_request=protocol.ControlRequest(priority=priority)
                        )
                    )
                    await _wait_for_control(stream, granted=True)

                command = asyncio.create_task(
                    self._call_unary(method, method_name, request, timeout)
                )
                loss = asyncio.create_task(_wait_for_control(stream, granted=False))
                done, _ = await asyncio.wait((command, loss), return_when=asyncio.FIRST_COMPLETED)
                if command not in done:
                    await loss
                    raise VectorProtocolError("Robot revoked behavior control")
                response = await command
                _check_response_status(response, method_name)
                return response
            except TimeoutError as err:
                raise VectorTimeoutError("Timed out waiting for robot behavior control") from err
            except grpc.RpcError as err:
                raise _map_rpc_error(err, "BehaviorControl") from err
            finally:
                if command is not None:
                    command.cancel()
                try:
                    if loss is not None and not stream.done():
                        with suppress(TimeoutError, grpc.RpcError):
                            async with asyncio.timeout(effective_timeout):
                                await stream.write(
                                    protocol.BehaviorControlRequest(
                                        control_release=protocol.ControlRelease()
                                    )
                                )
                                await stream.done_writing()
                                # Cancelling the reader before release would cancel the stream.
                                if not loss.done():
                                    await asyncio.wait((loss,))
                finally:
                    stream.cancel()
                    if command is not None and loss is not None:
                        loss.cancel()
                        await asyncio.gather(command, loss, return_exceptions=True)

    @staticmethod
    async def _handshake_rpc(stub: StubT, method_name: str, request: Any, timeout: float) -> Any:
        method = getattr(stub, method_name, None)
        if method is None:
            return None
        if not callable(method):
            raise VectorProtocolError(f"Stub attribute '{method_name}' is not callable")
        try:
            return await asyncio.wait_for(method(request, timeout=timeout), timeout=timeout)
        except TimeoutError as err:
            raise VectorTimeoutError(f"RPC '{method_name}' timed out after {timeout:.2f}s") from err
        except grpc.RpcError as err:
            if err.code() == grpc.StatusCode.UNIMPLEMENTED:
                return None
            raise _map_rpc_error(err, method_name) from err


async def _wait_for_control(stream: grpc.aio.StreamStreamCall, *, granted: bool) -> None:
    while (response := await stream.read()) is not grpc.aio.EOF:
        response_type = response.WhichOneof("response_type")
        if granted and response_type == "control_granted_response":
            return
        if response_type in {"control_lost_event", "reserved_control_lost_event"}:
            if granted:
                raise VectorProtocolError("Robot did not grant behavior control")
            return
    raise VectorConnectionError("Robot closed the behavior control stream")


def _check_response_status(response: Any, method_name: str) -> None:
    """Raise for explicit failures in Vector's generic protobuf status."""
    code = getattr(getattr(response, "status", None), "code", None)
    if code == protocol.ResponseStatus.FORBIDDEN:
        raise VectorAuthenticationError(f"Robot refused authorization for '{method_name}'")
    if code in (
        protocol.ResponseStatus.NOT_FOUND,
        protocol.ResponseStatus.ERROR_UPDATE_IN_PROGRESS,
    ):
        status_name = protocol.ResponseStatus.StatusCode.Name(code)
        raise VectorProtocolError(f"Robot rejected '{method_name}': {status_name}")


def _build_sdk_initialization_request() -> protocol.SDKInitializationRequest:
    try:
        module_version = version("pyddlvector")
    except PackageNotFoundError:
        module_version = ""
    return protocol.SDKInitializationRequest(
        sdk_module_version=module_version,
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        os_version=platform.platform(),
        cpu_version=platform.machine(),
    )

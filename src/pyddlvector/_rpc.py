"""Request validation and asynchronous bidirectional RPC operations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any, Self, TypeVar

import grpc
from google.protobuf.message import Message

from .exceptions import (
    VectorAuthenticationError,
    VectorProtocolError,
    VectorRPCError,
    VectorTimeoutError,
)

RequestT = TypeVar("RequestT", bound=Message)


def build_request(request_type: type[RequestT], **fields: Any) -> RequestT:
    """Construct a request with regular Python values and optional nested mappings."""
    for oneof in request_type.DESCRIPTOR.oneofs:
        if sum(fields.get(field.name) is not None for field in oneof.fields) > 1:
            raise VectorProtocolError(
                f"Specify at most one field for {request_type.__name__}.{oneof.name}"
            )
    try:
        return request_type(**fields)
    except (TypeError, ValueError, OverflowError) as err:
        raise VectorProtocolError(f"Invalid fields for {request_type.__name__}") from err


class DuplexStream[RequestT: Message, ResponseT: Message]:
    """Send requests and receive responses on a bidirectional RPC."""

    def __init__(
        self,
        call: grpc.aio.StreamStreamCall,
        method_name: str,
        request_type: type[RequestT],
        timeout: float,
    ) -> None:
        self._call = call
        self._method_name = method_name
        self._request_type = request_type
        self._timeout = timeout

    async def send(self, request: RequestT | None = None, /, **fields: Any) -> None:
        """Send a request built from keyword fields, or send a protobuf request."""
        if request is None:
            request = build_request(self._request_type, **fields)
        elif fields or not isinstance(request, self._request_type):
            raise VectorProtocolError(f"Expected a single {self._request_type.__name__} request")
        await self._transfer(self._call.write(request))

    async def finish_sending(self) -> None:
        """Half-close the request stream while continuing to receive responses."""
        await self._transfer(self._call.done_writing())

    async def read(self) -> ResponseT | None:
        """Read a response, returning None when the robot closes the stream."""
        response = await self._transfer(self._call.read())
        return None if response is grpc.aio.EOF else response

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> ResponseT:
        response = await self.read()
        if response is None:
            raise StopAsyncIteration
        return response

    async def _transfer[TransferT](self, operation: Awaitable[TransferT]) -> TransferT:
        try:
            return await asyncio.wait_for(operation, timeout=self._timeout)
        except TimeoutError as err:
            self._call.cancel()
            raise VectorTimeoutError(f"RPC '{self._method_name}' stream timed out") from err
        except grpc.RpcError as err:
            raise _map_rpc_error(err, self._method_name) from err


def _map_rpc_error(
    error: grpc.RpcError,
    method_name: str,
) -> VectorRPCError | VectorAuthenticationError | VectorTimeoutError:
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

    if status_code == grpc.StatusCode.DEADLINE_EXCEEDED:
        return VectorTimeoutError(f"RPC '{method_name}' exceeded its deadline")

    return VectorRPCError(message, status_code=status_code, details=details)

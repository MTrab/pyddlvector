"""Multi-robot client lifecycle management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .client import StubT, VectorClient
from .config import SdkConfigStore


class VectorFleet:
    """Creates and caches ``VectorClient`` instances for configured robots."""

    def __init__(
        self,
        *,
        config_store: SdkConfigStore | None = None,
        stub_factory: Callable[[Any], StubT],
        default_timeout: float = 10.0,
        channel_options: tuple[tuple[str, Any], ...] = (),
    ) -> None:
        self._config_store = config_store or SdkConfigStore()
        self._stub_factory = stub_factory
        self._default_timeout = default_timeout
        self._channel_options = channel_options
        self._clients: dict[str, VectorClient[StubT]] = {}

    def get(self, serial: str) -> VectorClient[StubT]:
        """Return cached client for serial, creating it from config on first use."""
        normalized = serial.strip().lower()
        client = self._clients.get(normalized)
        if client is not None:
            return client

        robot = self._config_store.load(normalized)
        client = VectorClient[
            StubT
        ](
            robot,
            stub_factory=self._stub_factory,
            default_timeout=self._default_timeout,
            channel_options=self._channel_options,
        )
        self._clients[normalized] = client
        return client

    async def connect(self, serial: str, *, timeout: float | None = None) -> VectorClient[StubT]:
        """Get and connect client for serial."""
        client = self.get(serial)
        await client.connect(timeout=timeout)
        return client

    async def disconnect(self, serial: str) -> None:
        """Disconnect a single serial if its client exists."""
        normalized = serial.strip().lower()
        client = self._clients.get(normalized)
        if client is not None:
            await client.disconnect()

    async def close(self) -> None:
        """Disconnect all tracked clients."""
        for client in self._clients.values():
            await client.disconnect()

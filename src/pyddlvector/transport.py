"""Transport protocol for robot communication backends."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class Transport(Protocol):
    """Low-level async transport contract used by :class:`VectorClient`."""

    @property
    def connected(self) -> bool:
        """Whether the transport has an active connection."""

    async def connect(self) -> None:
        """Establish transport connection."""

    async def disconnect(self) -> None:
        """Close transport connection."""

    async def send(
        self,
        command: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a command and return a decoded response payload."""

"""Error types used by pyddlvector."""

from __future__ import annotations

from typing import Any


class VectorError(Exception):
    """Base error for all module-level failures."""


class VectorConfigurationError(VectorError):
    """Raised for invalid or incomplete robot configuration."""


class VectorConnectionError(VectorError):
    """Raised when the client is not connected or cannot establish a channel."""


class VectorTimeoutError(VectorError):
    """Raised when an operation exceeds the configured timeout."""


class VectorProtocolError(VectorError):
    """Raised when client API usage does not match expected RPC protocol semantics."""


class VectorAuthenticationError(VectorError):
    """Raised when robot authentication fails (guid/certificate mismatch, invalid token)."""


class VectorProvisioningError(VectorError):
    """Raised when runtime credential provisioning fails."""


class VectorRPCError(VectorError):
    """Raised for non-authentication RPC failures returned by gRPC."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Any | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details

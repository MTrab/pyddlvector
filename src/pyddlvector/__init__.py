"""Public API for pyddlvector."""

from importlib import import_module
from typing import Any

from .client import VectorClient
from .config import RobotConfig, SdkConfigStore
from .exceptions import (
    VectorAuthenticationError,
    VectorConfigurationError,
    VectorConnectionError,
    VectorError,
    VectorProtocolError,
    VectorProvisioningError,
    VectorRPCError,
    VectorTimeoutError,
)
from .fleet import VectorFleet
from .provisioning import (
    authenticate_robot_guid,
    fetch_cert_for_official_serial,
    fetch_cert_for_wirepod_serial,
    fetch_cert_from_robot_tls,
    fetch_official_session_token,
    provision_runtime_robot,
)
from .statistics import RobotStatistics, fetch_lifetime_statistics

__all__ = [
    "RobotConfig",
    "SdkConfigStore",
    "VectorClient",
    "VectorFleet",
    "VectorAuthenticationError",
    "VectorConfigurationError",
    "VectorConnectionError",
    "VectorError",
    "VectorProvisioningError",
    "VectorProtocolError",
    "VectorRPCError",
    "VectorTimeoutError",
    "authenticate_robot_guid",
    "fetch_cert_for_official_serial",
    "fetch_cert_for_wirepod_serial",
    "fetch_cert_from_robot_tls",
    "fetch_official_session_token",
    "fetch_lifetime_statistics",
    "messaging",
    "provision_runtime_robot",
    "RobotStatistics",
]


def __getattr__(name: str) -> Any:
    """Lazy-load heavy modules for faster import and optional dependencies."""
    if name == "messaging":
        return import_module(".messaging", __name__)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

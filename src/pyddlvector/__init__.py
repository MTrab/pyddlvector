"""Public API for pyddlvector."""

from importlib import import_module
from typing import Any

from .activity import RobotActivityTracker, describe_robot_activity
from .camera import CameraFrame, extract_camera_frame
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
from .settings import fetch_master_volume, update_master_volume
from .statistics import RobotStatistics, fetch_lifetime_statistics
from .stimulation import RobotStimulation, parse_stimulation_info

__all__ = [
    "RobotConfig",
    "SdkConfigStore",
    "VectorClient",
    "VectorFleet",
    "CameraFrame",
    "describe_robot_activity",
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
    "extract_camera_frame",
    "fetch_official_session_token",
    "fetch_lifetime_statistics",
    "fetch_master_volume",
    "messaging",
    "parse_stimulation_info",
    "provision_runtime_robot",
    "RobotActivityTracker",
    "RobotStimulation",
    "RobotStatistics",
    "update_master_volume",
]


def __getattr__(name: str) -> Any:
    """Lazy-load heavy modules for faster import and optional dependencies."""
    if name == "messaging":
        return import_module(".messaging", __name__)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

"""Robot settings helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .client import VectorClient
from .exceptions import VectorProtocolError, VectorRPCError
from .messaging import protocol

_PULL_JDOCS_PATH = "/Anki.Vector.external_interface.ExternalInterface/PullJdocs"
_VOLUME_OPTIONS: tuple[str, ...] = (
    "mute",
    "low",
    "medium_low",
    "medium",
    "medium_high",
    "high",
)

_EYE_COLOR_OPTIONS: tuple[str, ...] = (
    "teal",
    "orange",
    "yellow",
    "lime_green",
    "azure_blue",
    "purple",
    "other_green",
)

_EYE_COLOR_PRESET_TO_ENUM: dict[str, str] = {
    "teal": "TIP_OVER_TEAL",
    "orange": "OVERFIT_ORANGE",
    "yellow": "UNCANNY_YELLOW",
    "lime_green": "NON_LINEAR_LIME",
    "azure_blue": "SINGULARITY_SAPPHIRE",
    "purple": "FALSE_POSITIVE_PURPLE",
    "other_green": "CONFUSION_MATRIX_GREEN",
}

_EYE_COLOR_ENUM_TO_PRESET: dict[str, str] = {
    enum_name: preset for preset, enum_name in _EYE_COLOR_PRESET_TO_ENUM.items()
}


@dataclass(frozen=True, slots=True)
class RobotEyeColor:
    """Normalized eye color state derived from robot settings jdoc."""

    preset: str
    custom_enabled: bool
    custom_hue: float | None
    custom_saturation: float | None


def normalize_master_volume(value: str) -> str:
    """Normalize a volume option string to canonical lowercase snake_case."""
    normalized = value.strip().lower().replace(" ", "_")
    if normalized in _VOLUME_OPTIONS:
        return normalized
    raise VectorProtocolError(f"Unsupported master volume option: {value}")


def normalize_eye_color_preset(value: str) -> str:
    """Normalize an eye color preset string to canonical lowercase snake_case."""
    normalized = value.strip().lower().replace(" ", "_")
    if normalized in _EYE_COLOR_OPTIONS:
        return normalized

    candidate = normalized.upper()
    if candidate.startswith("EYE_COLOR_"):
        candidate = candidate[len("EYE_COLOR_") :]
    if candidate in _EYE_COLOR_ENUM_TO_PRESET:
        return _EYE_COLOR_ENUM_TO_PRESET[candidate]

    raise VectorProtocolError(f"Unsupported eye color preset: {value}")


def _parse_master_volume_from_robot_settings_jdoc(raw_json: str) -> str:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise VectorProtocolError("Robot settings jdoc is not valid JSON") from err

    if "master_volume" not in payload:
        raise VectorProtocolError("Robot settings jdoc is missing master_volume")

    raw_value = payload["master_volume"]
    if isinstance(raw_value, str):
        candidate = raw_value.strip()
        if candidate.isdigit():
            raw_value = int(candidate)
        else:
            candidate = candidate.upper()
            if candidate.startswith("VOLUME_"):
                candidate = candidate[len("VOLUME_") :]
            return normalize_master_volume(candidate)

    if isinstance(raw_value, int):
        try:
            return normalize_master_volume(protocol.Volume.Name(raw_value))
        except ValueError as err:
            raise VectorProtocolError(
                f"Robot settings jdoc has unsupported master_volume value: {raw_value}"
            ) from err

    raise VectorProtocolError("Robot settings jdoc has invalid master_volume type")


def _parse_eye_color_from_robot_settings_jdoc(raw_json: str) -> RobotEyeColor:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise VectorProtocolError("Robot settings jdoc is not valid JSON") from err

    if "eye_color" not in payload:
        raise VectorProtocolError("Robot settings jdoc is missing eye_color")

    raw_value = payload["eye_color"]
    if isinstance(raw_value, str):
        candidate = raw_value.strip()
        if candidate.isdigit():
            raw_value = int(candidate)
        else:
            candidate = candidate.upper()
            if candidate.startswith("EYE_COLOR_"):
                candidate = candidate[len("EYE_COLOR_") :]
            preset = normalize_eye_color_preset(candidate)
            return _parse_custom_eye_color(payload, preset)

    if isinstance(raw_value, int):
        try:
            enum_name = protocol.EyeColor.Name(raw_value)
        except ValueError as err:
            raise VectorProtocolError(
                f"Robot settings jdoc has unsupported eye_color value: {raw_value}"
            ) from err
        preset = normalize_eye_color_preset(enum_name)
        return _parse_custom_eye_color(payload, preset)

    raise VectorProtocolError("Robot settings jdoc has invalid eye_color type")


def _parse_custom_eye_color(payload: dict[str, Any], preset: str) -> RobotEyeColor:
    custom_payload = payload.get("custom_eye_color")
    if not isinstance(custom_payload, dict):
        return RobotEyeColor(
            preset=preset,
            custom_enabled=False,
            custom_hue=None,
            custom_saturation=None,
        )

    enabled = bool(custom_payload.get("enabled", False))
    if not enabled:
        return RobotEyeColor(
            preset=preset,
            custom_enabled=False,
            custom_hue=None,
            custom_saturation=None,
        )

    try:
        hue = float(custom_payload["hue"])
        saturation = float(custom_payload["saturation"])
    except (KeyError, TypeError, ValueError):
        return RobotEyeColor(
            preset=preset,
            custom_enabled=False,
            custom_hue=None,
            custom_saturation=None,
        )

    if not (0.0 <= hue <= 1.0 and 0.0 <= saturation <= 1.0):
        return RobotEyeColor(
            preset=preset,
            custom_enabled=False,
            custom_hue=None,
            custom_saturation=None,
        )

    return RobotEyeColor(
        preset=preset,
        custom_enabled=True,
        custom_hue=hue,
        custom_saturation=saturation,
    )


async def fetch_master_volume(
    client: VectorClient[Any],
    *,
    timeout: float | None = None,
) -> str:
    """Fetch current master volume from robot settings jdoc."""
    request = protocol.PullJdocsRequest(jdoc_types=[protocol.ROBOT_SETTINGS])

    if hasattr(client.stub, "PullJdocs"):
        response = await client.rpc("PullJdocs", request, timeout=timeout)
    else:
        response = await client.unary_unary(
            _PULL_JDOCS_PATH,
            request,
            request_serializer=protocol.PullJdocsRequest.SerializeToString,
            response_deserializer=protocol.PullJdocsResponse.FromString,
            timeout=timeout,
        )

    for named_jdoc in response.named_jdocs:
        if named_jdoc.jdoc_type == protocol.ROBOT_SETTINGS:
            return _parse_master_volume_from_robot_settings_jdoc(named_jdoc.doc.json_doc)

    raise VectorProtocolError("ROBOT_SETTINGS jdoc was not returned by robot")


async def fetch_eye_color(
    client: VectorClient[Any],
    *,
    timeout: float | None = None,
) -> RobotEyeColor:
    """Fetch current eye color state from robot settings jdoc."""
    request = protocol.PullJdocsRequest(jdoc_types=[protocol.ROBOT_SETTINGS])

    if hasattr(client.stub, "PullJdocs"):
        response = await client.rpc("PullJdocs", request, timeout=timeout)
    else:
        response = await client.unary_unary(
            _PULL_JDOCS_PATH,
            request,
            request_serializer=protocol.PullJdocsRequest.SerializeToString,
            response_deserializer=protocol.PullJdocsResponse.FromString,
            timeout=timeout,
        )

    for named_jdoc in response.named_jdocs:
        if named_jdoc.jdoc_type == protocol.ROBOT_SETTINGS:
            return _parse_eye_color_from_robot_settings_jdoc(named_jdoc.doc.json_doc)

    raise VectorProtocolError("ROBOT_SETTINGS jdoc was not returned by robot")


async def update_master_volume(
    client: VectorClient[Any],
    value: str,
    *,
    timeout: float | None = None,
) -> str:
    """Update robot master volume and return canonical selected option."""
    normalized = normalize_master_volume(value)

    if normalized == "mute":
        return await _update_master_volume_via_update_settings(client, normalized, timeout=timeout)

    try:
        return await _update_master_volume_via_set_master_volume(
            client,
            normalized,
            timeout=timeout,
        )
    except (VectorProtocolError, VectorRPCError) as err:
        if not _should_fallback_to_update_settings(err):
            raise
        return await _update_master_volume_via_update_settings(client, normalized, timeout=timeout)


async def _update_master_volume_via_set_master_volume(
    client: VectorClient[Any],
    normalized: str,
    *,
    timeout: float | None = None,
) -> str:
    request = protocol.MasterVolumeRequest(
        volume_level=protocol.MasterVolumeLevel.Value(f"VOLUME_{normalized.upper()}"),
    )
    await client.rpc("SetMasterVolume", request, timeout=timeout)
    return normalized


async def update_eye_color_preset(
    client: VectorClient[Any],
    value: str,
    *,
    timeout: float | None = None,
) -> str:
    """Update robot eye color preset and return canonical selected preset."""
    normalized = normalize_eye_color_preset(value)
    enum_name = _EYE_COLOR_PRESET_TO_ENUM[normalized]

    request = protocol.UpdateSettingsRequest(
        settings=protocol.RobotSettingsConfig(
            eye_color=protocol.EyeColor.Value(enum_name),
        )
    )
    response = await client.rpc("UpdateSettings", request, timeout=timeout)

    accepted = protocol.ResultCode.Value("SETTINGS_ACCEPTED")
    response_code = getattr(response, "code", None)
    if response_code is not None and int(response_code) != accepted:
        raise VectorProtocolError(
            f"Eye color preset update was not accepted by robot: code={response_code}"
        )

    return normalized


async def update_custom_eye_color(
    client: VectorClient[Any],
    *,
    hue: float,
    saturation: float,
    timeout: float | None = None,
) -> tuple[float, float]:
    """Set custom eye color hue/saturation in the [0.0, 1.0] range."""
    if not (0.0 <= hue <= 1.0):
        raise VectorProtocolError("Custom eye color hue must be between 0.0 and 1.0")
    if not (0.0 <= saturation <= 1.0):
        raise VectorProtocolError("Custom eye color saturation must be between 0.0 and 1.0")

    request = protocol.SetEyeColorRequest(
        hue=float(hue),
        saturation=float(saturation),
    )
    await client.rpc("SetEyeColor", request, timeout=timeout)
    return float(hue), float(saturation)


async def _update_master_volume_via_update_settings(
    client: VectorClient[Any],
    normalized: str,
    *,
    timeout: float | None = None,
) -> str:
    request = protocol.UpdateSettingsRequest(
        settings=protocol.RobotSettingsConfig(
            master_volume=protocol.Volume.Value(normalized.upper()),
        )
    )
    response = await client.rpc("UpdateSettings", request, timeout=timeout)

    accepted = protocol.ResultCode.Value("SETTINGS_ACCEPTED")
    response_code = getattr(response, "code", None)
    if response_code is not None and int(response_code) != accepted:
        raise VectorProtocolError(f"Volume update was not accepted by robot: code={response_code}")

    return normalized


def _should_fallback_to_update_settings(err: VectorProtocolError | VectorRPCError) -> bool:
    if isinstance(err, VectorProtocolError):
        return True

    status_code = getattr(err, "status_code", None)
    return str(status_code) == "StatusCode.UNIMPLEMENTED"

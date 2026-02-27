"""Robot state telemetry helpers."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RobotTelemetry:
    """Normalized orientation, lift, accelerometer and gyroscope data."""

    roll_rad: float
    pitch_rad: float
    yaw_rad: float
    lift_height_mm: float
    accel_x_mmps2: float
    accel_y_mmps2: float
    accel_z_mmps2: float
    gyro_x_radps: float
    gyro_y_radps: float
    gyro_z_radps: float


@dataclass(slots=True)
class TelemetryFilter:
    """Rate-limit and quantize telemetry updates to reduce noisy change spam."""

    min_update_interval_seconds: float = 0.5
    orientation_quantum_rad: float = 0.05
    lift_quantum_mm: float = 1.0
    accel_quantum_mmps2: float = 5.0
    gyro_quantum_radps: float = 0.01
    _last_published: RobotTelemetry | None = None
    _last_published_monotonic: float | None = None

    def process(
        self,
        telemetry: RobotTelemetry,
        *,
        now_monotonic: float | None = None,
    ) -> RobotTelemetry | None:
        """Return filtered telemetry when publish criteria are met, otherwise None."""
        now_value = time.monotonic() if now_monotonic is None else now_monotonic
        quantized = self.quantize(telemetry)

        if self._last_published is None:
            self._last_published = quantized
            self._last_published_monotonic = now_value
            return quantized

        if quantized == self._last_published:
            return None

        assert self._last_published_monotonic is not None
        if (now_value - self._last_published_monotonic) < self.min_update_interval_seconds:
            return None

        self._last_published = quantized
        self._last_published_monotonic = now_value
        return quantized

    def quantize(self, telemetry: RobotTelemetry) -> RobotTelemetry:
        """Round telemetry fields to configured quanta."""
        return RobotTelemetry(
            roll_rad=_quantize(telemetry.roll_rad, self.orientation_quantum_rad),
            pitch_rad=_quantize(telemetry.pitch_rad, self.orientation_quantum_rad),
            yaw_rad=_quantize(telemetry.yaw_rad, self.orientation_quantum_rad),
            lift_height_mm=_quantize(telemetry.lift_height_mm, self.lift_quantum_mm),
            accel_x_mmps2=_quantize(telemetry.accel_x_mmps2, self.accel_quantum_mmps2),
            accel_y_mmps2=_quantize(telemetry.accel_y_mmps2, self.accel_quantum_mmps2),
            accel_z_mmps2=_quantize(telemetry.accel_z_mmps2, self.accel_quantum_mmps2),
            gyro_x_radps=_quantize(telemetry.gyro_x_radps, self.gyro_quantum_radps),
            gyro_y_radps=_quantize(telemetry.gyro_y_radps, self.gyro_quantum_radps),
            gyro_z_radps=_quantize(telemetry.gyro_z_radps, self.gyro_quantum_radps),
        )

    def reset(self) -> None:
        """Reset filter history."""
        self._last_published = None
        self._last_published_monotonic = None


def extract_robot_telemetry(robot_state: Any) -> RobotTelemetry:
    """Extract normalized telemetry fields from a RobotState-like payload."""
    pose = getattr(robot_state, "pose", None)
    q0 = float(getattr(pose, "q0", 1.0))
    q1 = float(getattr(pose, "q1", 0.0))
    q2 = float(getattr(pose, "q2", 0.0))
    q3 = float(getattr(pose, "q3", 0.0))
    quat_roll_rad, quat_pitch_rad, quat_yaw_rad = _quaternion_to_euler_rad(q0, q1, q2, q3)

    # Prefer explicit SDK pose angle/pitch fields when present.
    yaw_rad = float(getattr(robot_state, "pose_angle_rad", quat_yaw_rad))
    pitch_rad = float(getattr(robot_state, "pose_pitch_rad", quat_pitch_rad))
    roll_rad = quat_roll_rad

    accel = getattr(robot_state, "accel", None)
    gyro = getattr(robot_state, "gyro", None)

    return RobotTelemetry(
        roll_rad=roll_rad,
        pitch_rad=pitch_rad,
        yaw_rad=yaw_rad,
        lift_height_mm=float(getattr(robot_state, "lift_height_mm", 0.0)),
        accel_x_mmps2=float(getattr(accel, "x", 0.0)),
        accel_y_mmps2=float(getattr(accel, "y", 0.0)),
        accel_z_mmps2=float(getattr(accel, "z", 0.0)),
        gyro_x_radps=float(getattr(gyro, "x", 0.0)),
        gyro_y_radps=float(getattr(gyro, "y", 0.0)),
        gyro_z_radps=float(getattr(gyro, "z", 0.0)),
    )


def _quaternion_to_euler_rad(
    q0: float,
    q1: float,
    q2: float,
    q3: float,
) -> tuple[float, float, float]:
    # q0/q1/q2/q3 are w/x/y/z in Vector's PoseStruct.
    sinr_cosp = 2.0 * (q0 * q1 + q2 * q3)
    cosr_cosp = 1.0 - 2.0 * (q1 * q1 + q2 * q2)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (q0 * q2 - q3 * q1)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)

    siny_cosp = 2.0 * (q0 * q3 + q1 * q2)
    cosy_cosp = 1.0 - 2.0 * (q2 * q2 + q3 * q3)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return roll, pitch, yaw


def _quantize(value: float, quantum: float) -> float:
    if quantum <= 0:
        return float(value)
    return round(float(value) / quantum) * quantum

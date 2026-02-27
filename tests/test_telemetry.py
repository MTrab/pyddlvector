from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from pyddlvector.telemetry import RobotTelemetry, TelemetryFilter, extract_robot_telemetry


def _quaternion_from_euler(
    roll: float, pitch: float, yaw: float
) -> tuple[float, float, float, float]:
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)

    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    return w, x, y, z


def test_extract_robot_telemetry_uses_pose_angle_and_pitch_fields() -> None:
    q0, q1, q2, q3 = _quaternion_from_euler(0.2, -0.1, 0.3)
    robot_state = SimpleNamespace(
        pose=SimpleNamespace(q0=q0, q1=q1, q2=q2, q3=q3),
        pose_angle_rad=1.1,
        pose_pitch_rad=-0.4,
        lift_height_mm=52.5,
        accel=SimpleNamespace(x=5.0, y=6.0, z=7.0),
        gyro=SimpleNamespace(x=0.01, y=0.02, z=0.03),
    )

    telemetry = extract_robot_telemetry(robot_state)

    assert isinstance(telemetry, RobotTelemetry)
    assert telemetry.roll_rad == pytest_approx(0.2)
    assert telemetry.pitch_rad == pytest_approx(-0.4)
    assert telemetry.yaw_rad == pytest_approx(1.1)
    assert telemetry.lift_height_mm == 52.5
    assert telemetry.accel_x_mmps2 == 5.0
    assert telemetry.accel_y_mmps2 == 6.0
    assert telemetry.accel_z_mmps2 == 7.0
    assert telemetry.gyro_x_radps == 0.01
    assert telemetry.gyro_y_radps == 0.02
    assert telemetry.gyro_z_radps == 0.03


def test_extract_robot_telemetry_falls_back_to_quaternion() -> None:
    expected_roll = 0.35
    expected_pitch = -0.2
    expected_yaw = 0.75
    q0, q1, q2, q3 = _quaternion_from_euler(expected_roll, expected_pitch, expected_yaw)
    robot_state = SimpleNamespace(
        pose=SimpleNamespace(q0=q0, q1=q1, q2=q2, q3=q3),
        lift_height_mm=0.0,
        accel=SimpleNamespace(),
        gyro=SimpleNamespace(),
    )

    telemetry = extract_robot_telemetry(robot_state)

    assert telemetry.roll_rad == pytest_approx(expected_roll)
    assert telemetry.pitch_rad == pytest_approx(expected_pitch)
    assert telemetry.yaw_rad == pytest_approx(expected_yaw)
    assert telemetry.accel_x_mmps2 == 0.0
    assert telemetry.gyro_z_radps == 0.0


def test_telemetry_filter_emits_first_value() -> None:
    filter_ = TelemetryFilter(min_update_interval_seconds=1.0)
    telemetry = RobotTelemetry(
        roll_rad=0.12,
        pitch_rad=0.23,
        yaw_rad=0.34,
        lift_height_mm=10.4,
        accel_x_mmps2=1.0,
        accel_y_mmps2=2.0,
        accel_z_mmps2=3.0,
        gyro_x_radps=0.011,
        gyro_y_radps=0.022,
        gyro_z_radps=0.033,
    )

    published = filter_.process(telemetry, now_monotonic=1.0)
    assert published is not None


def test_telemetry_filter_rate_limits_updates() -> None:
    filter_ = TelemetryFilter(min_update_interval_seconds=1.0, orientation_quantum_rad=0.01)
    first = RobotTelemetry(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    second = RobotTelemetry(0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    assert filter_.process(first, now_monotonic=10.0) is not None
    assert filter_.process(second, now_monotonic=10.2) is None
    assert filter_.process(second, now_monotonic=11.2) is not None


def test_telemetry_filter_quantizes_and_suppresses_noise() -> None:
    filter_ = TelemetryFilter(
        min_update_interval_seconds=0.1,
        orientation_quantum_rad=0.05,
        lift_quantum_mm=1.0,
    )
    base = RobotTelemetry(0.12, 0.12, 0.12, 10.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    noisy = RobotTelemetry(0.121, 0.119, 0.124, 10.41, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    first = filter_.process(base, now_monotonic=1.0)
    second = filter_.process(noisy, now_monotonic=2.0)

    assert first is not None
    assert second is None


def test_telemetry_filter_reset() -> None:
    filter_ = TelemetryFilter(min_update_interval_seconds=10.0)
    telemetry = RobotTelemetry(0.1, 0.1, 0.1, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert filter_.process(telemetry, now_monotonic=1.0) is not None
    filter_.reset()
    assert filter_.process(telemetry, now_monotonic=1.1) is not None


def pytest_approx(value: float):
    return pytest.approx(value, abs=1e-6)

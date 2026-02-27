from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from pyddlvector.telemetry import RobotTelemetry, extract_robot_telemetry


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


def pytest_approx(value: float):
    return pytest.approx(value, abs=1e-6)

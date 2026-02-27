from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys

from pyddlvector import (
    RobotActivityTracker,
    VectorClient,
    extract_robot_telemetry,
    fetch_lifetime_statistics,
    messaging,
    provision_runtime_robot,
)

DEFAULT_NAME = "Vector-T3X9"
# DEFAULT_NAME = "Vector-A9E9"
DEFAULT_SERIAL = "00908e7e"
# DEFAULT_SERIAL = "00608f75"
DEFAULT_IP = "192.168.1.201"
# DEFAULT_IP = "192.168.1.202"
DEFAULT_WIREPOD_URL = "http://escapepod.local:8080"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision and connect to Vector-T3X9 using pyddlvector runtime flow.",
    )
    parser.add_argument("--mode", choices=["wirepod", "official"], default="wirepod")
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--ip", default=DEFAULT_IP)
    parser.add_argument("--wirepod-url", default=DEFAULT_WIREPOD_URL)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args()


def _battery_level_name(level_value: int) -> str:
    try:
        return messaging.protocol.BatteryLevel.Name(level_value)
    except ValueError:
        return f"UNKNOWN({level_value})"


async def _read_current_robot_activity(
    client: VectorClient,
    *,
    timeout: float,
) -> tuple[str, object | None]:
    stream = client.stub.EventStream(messaging.protocol.EventRequest(), timeout=timeout)
    tracker = RobotActivityTracker()
    latest_robot_state = None
    try:
        for _ in range(25):
            event_response = await asyncio.wait_for(stream.read(), timeout=timeout)
            if event_response is None or not event_response.HasField("event"):
                continue

            event = event_response.event
            tracker.observe_event(event)
            event_type = event.WhichOneof("event_type")
            if event_type == "robot_state":
                latest_robot_state = event.robot_state
                if (
                    tracker.saw_face_search
                    or tracker.saw_charger_search
                    or tracker.saw_cube_search
                    or tracker.saw_object_search
                ):
                    return tracker.activity_from_robot_state(latest_robot_state), latest_robot_state
        if latest_robot_state is None:
            return "Unknown (no robot_state event received)", None
        return tracker.activity_from_robot_state(latest_robot_state), latest_robot_state
    except TimeoutError:
        return "Unknown (timed out waiting for robot_state)", None
    finally:
        stream.cancel()


async def main() -> int:
    args = parse_args()

    def stub_factory(channel):
        return messaging.client.ExternalInterfaceStub(channel)

    def request_factory(session_id: str, client_name: str):
        return messaging.protocol.UserAuthenticationRequest(
            user_session_id=session_id.encode("utf-8"),
            client_name=client_name.encode("utf-8"),
        )

    username = os.getenv("VECTOR_EMAIL") if args.mode == "official" else None
    password = os.getenv("VECTOR_PASSWORD") if args.mode == "official" else None

    if args.mode == "official" and (not username or not password):
        print(
            "Official mode requires VECTOR_EMAIL and VECTOR_PASSWORD env vars.",
            file=sys.stderr,
        )
        return 2

    robot = await provision_runtime_robot(
        mode=args.mode,
        name=args.name,
        ip=args.ip,
        serial=args.serial,
        wirepod_url=args.wirepod_url if args.mode == "wirepod" else None,
        username=username,
        password=password,
        stub_factory=stub_factory,
        request_factory=request_factory,
        session_id="Anything1",
        timeout=args.timeout,
    )

    client = VectorClient(robot, stub_factory=stub_factory, default_timeout=args.timeout)

    await client.connect(timeout=args.timeout)
    try:
        request = messaging.protocol.ProtocolVersionRequest(
            client_version=messaging.protocol.PROTOCOL_VERSION_CURRENT,
            min_host_version=messaging.protocol.PROTOCOL_VERSION_MINIMUM,
        )
        response = await client.rpc("ProtocolVersion", request, timeout=args.timeout)
        print("Connected to:", robot.name, robot.ip)
        print("Serial:", robot.serial)
        print("Host version:", getattr(response, "host_version", "<unknown>"))
        print("Local client:", socket.gethostname())

        battery_response = await client.rpc(
            "BatteryState",
            messaging.protocol.BatteryStateRequest(),
            timeout=args.timeout,
        )
        battery_level = int(getattr(battery_response, "battery_level", 0))
        battery_volts = float(getattr(battery_response, "battery_volts", 0.0))
        is_charging = bool(getattr(battery_response, "is_charging", False))
        on_charger = bool(getattr(battery_response, "is_on_charger_platform", False))

        activity, robot_state = await _read_current_robot_activity(client, timeout=args.timeout)

        print("Battery level:", _battery_level_name(battery_level))
        print("Battery volts:", f"{battery_volts:.2f}V")
        print("Charging:", "yes" if is_charging else "no")
        print("On charger:", "yes" if on_charger else "no")
        print("Current activity:", activity)
        if robot_state is not None:
            telemetry = extract_robot_telemetry(robot_state)
            print("Roll (rad):", f"{telemetry.roll_rad:.3f}")
            print("Pitch (rad):", f"{telemetry.pitch_rad:.3f}")
            print("Yaw (rad):", f"{telemetry.yaw_rad:.3f}")
            print("Lift height (mm):", f"{telemetry.lift_height_mm:.1f}")
            print(
                "Accel (mm/s^2):",
                f"x={telemetry.accel_x_mmps2:.2f}",
                f"y={telemetry.accel_y_mmps2:.2f}",
                f"z={telemetry.accel_z_mmps2:.2f}",
            )
            print(
                "Gyro (rad/s):",
                f"x={telemetry.gyro_x_radps:.3f}",
                f"y={telemetry.gyro_y_radps:.3f}",
                f"z={telemetry.gyro_z_radps:.3f}",
            )

        stats = await fetch_lifetime_statistics(client, timeout=args.timeout)
        print("Days alive:", stats.days_alive)
        print("Reacted to trigger word:", stats.reacted_to_trigger_word, "times")
        print("Utility features used:", stats.utility_features_used)
        print("Seconds petted:", stats.seconds_petted)
        print("Distance moved (cm):", stats.distance_moved_cm)
    finally:
        await client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

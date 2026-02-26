from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys

from pyddlvector import VectorClient, messaging, provision_runtime_robot

DEFAULT_NAME = "Vector-T3X9"
DEFAULT_SERIAL = "00908e7e"
# DEFAULT_SERIAL = "00608f75"
DEFAULT_IP = "192.168.1.201"
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


def _describe_robot_activity(robot_state: object) -> str:
    left_speed = abs(getattr(robot_state, "left_wheel_speed_mmps", 0.0))
    right_speed = abs(getattr(robot_state, "right_wheel_speed_mmps", 0.0))
    is_moving = (left_speed + right_speed) > 1.0

    touch_data = getattr(robot_state, "touch_data", None)
    being_touched = bool(getattr(touch_data, "is_being_touched", False))

    carrying_object_id = int(getattr(robot_state, "carrying_object_id", -1))
    is_carrying_object = carrying_object_id >= 0

    if is_moving:
        return "Moving around"
    if being_touched:
        return "Being touched"
    if is_carrying_object:
        return "Standing still while carrying an object"
    return "Idle / standing still"


async def _read_current_robot_activity(
    client: VectorClient,
    *,
    timeout: float,
) -> str:
    stream = client.stub.EventStream(messaging.protocol.EventRequest(), timeout=timeout)
    try:
        for _ in range(10):
            event_response = await asyncio.wait_for(stream.read(), timeout=timeout)
            if event_response is None or not event_response.HasField("event"):
                continue

            event_type = event_response.event.WhichOneof("event_type")
            if event_type == "robot_state":
                return _describe_robot_activity(event_response.event.robot_state)
        return "Unknown (no robot_state event received)"
    except TimeoutError:
        return "Unknown (timed out waiting for robot_state)"
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

        activity = await _read_current_robot_activity(client, timeout=args.timeout)

        print("Battery level:", _battery_level_name(battery_level))
        print("Battery volts:", f"{battery_volts:.2f}V")
        print("Charging:", "yes" if is_charging else "no")
        print("On charger:", "yes" if on_charger else "no")
        print("Current activity:", activity)
    finally:
        await client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

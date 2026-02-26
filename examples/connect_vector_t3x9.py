from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys

from pyddlvector import VectorClient, messaging, provision_runtime_robot

DEFAULT_NAME = "Vector-T3X9"
DEFAULT_SERIAL = "00908e7e"
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
    finally:
        await client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

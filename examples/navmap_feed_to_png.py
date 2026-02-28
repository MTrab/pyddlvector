from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
from pathlib import Path

from pyddlvector import VectorClient, iter_nav_map_frames, messaging, provision_runtime_robot

DEFAULT_NAME = "Vector-T3X9"
DEFAULT_SERIAL = "00908e7e"
DEFAULT_IP = "192.168.1.201"
DEFAULT_WIREPOD_URL = "http://escapepod.local:8080"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read NavMapFeed and write each frame as a PNG file "
            "(no sdk_config.ini needed)."
        ),
    )
    parser.add_argument("--mode", choices=["wirepod", "official"], default="wirepod")
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--ip", default=DEFAULT_IP)
    parser.add_argument("--wirepod-url", default=DEFAULT_WIREPOD_URL)
    parser.add_argument("--output-dir", default="navmap_frames")
    parser.add_argument("--max-frames", type=int, default=20)
    parser.add_argument("--frequency", type=float, default=2.0)
    parser.add_argument("--max-side", type=int, default=256)
    parser.add_argument("--min-coverage", type=float, default=0.75)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--reconnect-delay", type=float, default=1.0)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    username = os.getenv("VECTOR_EMAIL") if args.mode == "official" else None
    password = os.getenv("VECTOR_PASSWORD") if args.mode == "official" else None
    if args.mode == "official" and (not username or not password):
        print(
            "Official mode requires VECTOR_EMAIL and VECTOR_PASSWORD env vars.",
            file=sys.stderr,
        )
        return 2

    def stub_factory(channel):
        return messaging.client.ExternalInterfaceStub(channel)

    def request_factory(session_id: str, client_name: str):
        return messaging.protocol.UserAuthenticationRequest(
            user_session_id=session_id.encode("utf-8"),
            client_name=client_name.encode("utf-8"),
        )

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

    client = VectorClient(
        robot,
        stub_factory=stub_factory,
        default_timeout=args.timeout,
    )
    await client.connect(timeout=args.timeout)
    print("Connected to:", robot.name, robot.ip, f"(local host: {socket.gethostname()})")

    written = 0
    try:
        async for frame in iter_nav_map_frames(
            client,
            frequency=args.frequency,
            max_side=args.max_side,
            read_timeout=args.timeout,
            reconnect_delay=args.reconnect_delay,
            min_coverage_ratio=args.min_coverage,
        ):
            file_path = output_dir / f"navmap_{written:04d}.png"
            file_path.write_bytes(frame.data)
            print(
                f"Wrote {file_path} ({frame.width}x{frame.height}, origin={frame.origin_id})",
            )
            written += 1
            if written >= args.max_frames:
                break
    finally:
        await client.disconnect()

    print(f"Done. Wrote {written} frame(s) to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

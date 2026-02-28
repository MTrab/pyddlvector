from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import os
import socket
import sys
from dataclasses import dataclass, field

from pyddlvector import (
    NavMapRobotPose,
    VectorClient,
    iter_nav_map_frames,
    messaging,
    nav_map_robot_pose_from_state,
    provision_runtime_robot,
)

DEFAULT_NAME = "Vector-T3X9"
DEFAULT_SERIAL = "00908e7e"
DEFAULT_IP = "192.168.1.201"
DEFAULT_WIREPOD_URL = "http://escapepod.local:8080"
BOUNDARY = "frame"
_PLACEHOLDER_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c $.',#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01"
    b"\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xda\x00\x08"
    b"\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9"
)
_PLACEHOLDER_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\xa0\x1f\x00"
    b"\x00\x03\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve NavMap frames as a multipart HTTP image stream.",
    )
    parser.add_argument("--mode", choices=["wirepod", "official"], default="wirepod")
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--ip", default=DEFAULT_IP)
    parser.add_argument("--wirepod-url", default=DEFAULT_WIREPOD_URL)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--frequency", type=float, default=2.0)
    parser.add_argument("--max-side", type=int, default=256)
    parser.add_argument("--min-coverage", type=float, default=0.75)
    parser.add_argument("--reconnect-delay", type=float, default=1.0)
    parser.add_argument("--stream-fps", type=float, default=5.0)
    parser.add_argument("--frame-mime", choices=["jpeg", "png"], default="jpeg")
    parser.add_argument(
        "--lock-origin",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep stream on one navmap origin to avoid transient map rotation/jumps.",
    )
    parser.add_argument(
        "--origin-switch-confirmation",
        type=int,
        default=3,
        help=(
            "Consecutive frames required before accepting a new origin "
            "when lock-origin is enabled."
        ),
    )
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


@dataclass(slots=True)
class SharedFrame:
    latest_image: bytes | None = None
    frame_content_type: str = "image/png"
    update_event: asyncio.Event = field(default_factory=asyncio.Event)
    latest_robot_pose: NavMapRobotPose | None = None
    latest_charger_pose: NavMapRobotPose | None = None
    active_origin_id: int | None = None


async def _read_request_headers(reader: asyncio.StreamReader) -> bytes:
    return await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10.0)


def _placeholder_for_mime(frame_mime: str) -> tuple[bytes, str]:
    if frame_mime == "jpeg":
        return _PLACEHOLDER_JPEG, "image/jpeg"
    return _PLACEHOLDER_PNG, "image/png"


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    shared: SharedFrame,
    stream_fps: float,
) -> None:
    try:
        await _read_request_headers(reader)
        header = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: multipart/x-mixed-replace; boundary={BOUNDARY}\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        writer.write(header.encode("ascii"))
        await writer.drain()

        interval = 1.0 / max(0.1, stream_fps)
        while True:
            if shared.latest_image is None:
                shared.update_event.clear()
                await shared.update_event.wait()
                continue

            payload = shared.latest_image
            assert payload is not None
            part_header = (
                f"--{BOUNDARY}\r\n"
                f"Content-Type: {shared.frame_content_type}\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "\r\n"
            )
            writer.write(part_header.encode("ascii"))
            writer.write(payload)
            writer.write(b"\r\n")
            await writer.drain()
            await asyncio.sleep(interval)
    except (
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,
        TimeoutError,
        ConnectionError,
        BrokenPipeError,
    ):
        pass
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def _produce_frames(
    client: VectorClient,
    *,
    shared: SharedFrame,
    frame_mime: str,
    frequency: float,
    max_side: int,
    min_coverage_ratio: float,
    read_timeout: float,
    reconnect_delay: float,
    lock_origin: bool,
    origin_switch_confirmation: int,
) -> None:
    jpeg_encoder = None
    if frame_mime == "jpeg":
        try:
            from PIL import Image
        except ImportError as err:
            raise RuntimeError(
                "JPEG streaming requires Pillow. Install with: poetry add Pillow"
            ) from err

        def _encode_jpeg(png_bytes: bytes) -> bytes:
            with Image.open(io.BytesIO(png_bytes)) as image:
                rgb = image.convert("RGB")
                out = io.BytesIO()
                rgb.save(out, format="JPEG", quality=85, optimize=True)
                return out.getvalue()

        jpeg_encoder = _encode_jpeg

    active_origin_id: int | None = None
    pending_origin_id: int | None = None
    pending_origin_count = 0
    switch_threshold = max(1, int(origin_switch_confirmation))

    async for frame in iter_nav_map_frames(
        client,
        frequency=frequency,
        max_side=max_side,
        min_coverage_ratio=min_coverage_ratio,
        read_timeout=read_timeout,
        reconnect_delay=reconnect_delay,
        center_content=True,
        robot_pose_provider=lambda: shared.latest_robot_pose,
        charger_pose_provider=lambda: shared.latest_charger_pose,
    ):
        if lock_origin:
            if active_origin_id is None:
                active_origin_id = frame.origin_id
                shared.active_origin_id = active_origin_id
                print(f"Locked navmap origin: {active_origin_id}")
            elif frame.origin_id != active_origin_id:
                if pending_origin_id == frame.origin_id:
                    pending_origin_count += 1
                else:
                    pending_origin_id = frame.origin_id
                    pending_origin_count = 1
                if pending_origin_count < switch_threshold:
                    continue
                print(
                    "Switching navmap origin: "
                    f"{active_origin_id} -> {pending_origin_id} "
                    f"(confirmed {pending_origin_count} frames)",
                )
                active_origin_id = pending_origin_id
                shared.active_origin_id = active_origin_id
                pending_origin_id = None
                pending_origin_count = 0
            else:
                pending_origin_id = None
                pending_origin_count = 0

        payload = frame.data if jpeg_encoder is None else jpeg_encoder(frame.data)
        shared.latest_image = payload
        shared.frame_content_type = "image/png" if jpeg_encoder is None else "image/jpeg"
        shared.update_event.set()


async def _consume_robot_state(
    client: VectorClient,
    *,
    shared: SharedFrame,
    read_timeout: float,
    reconnect_delay: float,
) -> None:
    while True:
        stream = client.stub.EventStream(messaging.protocol.EventRequest())
        pending_read: asyncio.Task[object | None] | None = None
        try:
            while True:
                if pending_read is None:
                    pending_read = asyncio.create_task(stream.read())

                done, _ = await asyncio.wait({pending_read}, timeout=read_timeout)
                if not done:
                    break

                try:
                    event_response = pending_read.result()
                except asyncio.CancelledError:
                    break
                finally:
                    pending_read = None

                if event_response is None:
                    break
                if not getattr(event_response, "HasField", lambda _f: False)("event"):
                    continue
                event = event_response.event
                event_type = getattr(event, "WhichOneof", lambda _name: None)("event_type")
                if event_type == "robot_state":
                    pose = nav_map_robot_pose_from_state(event.robot_state)
                    if pose is not None:
                        locked_origin = shared.active_origin_id
                        if locked_origin is not None and int(pose.origin_id) != locked_origin:
                            continue
                        shared.latest_robot_pose = pose
                    continue

                if event_type != "object_event":
                    continue
                object_event = event.object_event
                object_event_type = getattr(
                    object_event,
                    "WhichOneof",
                    lambda _name: None,
                )("object_event_type")
                if object_event_type != "robot_observed_object":
                    continue
                observed_object = object_event.robot_observed_object
                if int(getattr(observed_object, "object_type", 0)) != int(
                    messaging.protocol.CHARGER_BASIC
                ):
                    continue
                charger_pose = getattr(observed_object, "pose", None)
                if charger_pose is None:
                    continue
                try:
                    charger_pose = NavMapRobotPose(
                        origin_id=int(charger_pose.origin_id),
                        x_mm=float(charger_pose.x),
                        y_mm=float(charger_pose.y),
                    )
                    locked_origin = shared.active_origin_id
                    if locked_origin is not None and int(charger_pose.origin_id) != locked_origin:
                        continue
                    shared.latest_charger_pose = charger_pose
                except (AttributeError, TypeError, ValueError):
                    continue
        finally:
            if pending_read is not None and not pending_read.done():
                pending_read.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending_read
            stream.cancel()

        await asyncio.sleep(max(0.0, reconnect_delay))


async def main() -> int:
    args = parse_args()
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
    client = VectorClient(robot, stub_factory=stub_factory, default_timeout=args.timeout)
    await client.connect(timeout=args.timeout)

    placeholder_bytes, placeholder_type = _placeholder_for_mime(args.frame_mime)
    shared = SharedFrame(
        latest_image=placeholder_bytes,
        frame_content_type=placeholder_type,
    )
    producer_task = asyncio.create_task(
        _produce_frames(
            client,
            shared=shared,
            frame_mime=args.frame_mime,
            frequency=args.frequency,
            max_side=args.max_side,
            min_coverage_ratio=args.min_coverage,
            read_timeout=args.timeout,
            reconnect_delay=args.reconnect_delay,
            lock_origin=args.lock_origin,
            origin_switch_confirmation=args.origin_switch_confirmation,
        ),
    )
    pose_task = asyncio.create_task(
        _consume_robot_state(
            client,
            shared=shared,
            read_timeout=args.timeout,
            reconnect_delay=args.reconnect_delay,
        ),
    )

    server = await asyncio.start_server(
        lambda r, w: _handle_client(r, w, shared=shared, stream_fps=args.stream_fps),
        host=args.bind,
        port=args.port,
    )
    local_host = socket.gethostname()
    print("Connected to robot:", robot.name, robot.ip, f"(local host: {local_host})")
    print(f"NavMap stream endpoint: http://{args.bind}:{args.port}/ ({args.frame_mime})")
    print(f"Min coverage threshold: {args.min_coverage:.2f}")
    print(f"Origin lock enabled: {args.lock_origin}")

    try:
        async with server:
            await asyncio.gather(
                server.serve_forever(),
                producer_task,
                pose_task,
            )
    finally:
        producer_task.cancel()
        pose_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await producer_task
        with contextlib.suppress(asyncio.CancelledError):
            await pose_task
        await client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

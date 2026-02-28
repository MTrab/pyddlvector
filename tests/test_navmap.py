from __future__ import annotations

import struct
import zlib
from types import SimpleNamespace

from pyddlvector.navmap import NavMapFrame, extract_nav_map_frame, nav_map_robot_pose_from_state


def test_extract_nav_map_frame_returns_png_image() -> None:
    response = SimpleNamespace(
        origin_id=4,
        map_info=SimpleNamespace(
            root_depth=1,
            root_size_mm=200.0,
            root_center_x=0.0,
            root_center_y=0.0,
        ),
        quad_infos=[
            SimpleNamespace(content=1, depth=0),
            SimpleNamespace(content=3, depth=0),
            SimpleNamespace(content=7, depth=0),
            SimpleNamespace(content=0, depth=0),
        ],
    )

    frame = extract_nav_map_frame(response)

    assert isinstance(frame, NavMapFrame)
    assert frame.origin_id == 4
    assert frame.width == 2
    assert frame.height == 2
    assert frame.data.startswith(b"\x89PNG\r\n\x1a\n")

    width, height, pixels = _decode_png_rgb(frame.data)
    assert (width, height) == (2, 2)
    # top-left, top-right, bottom-left, bottom-right
    assert _pixel(pixels, width, 0, 0) == (20, 20, 24)
    assert _pixel(pixels, width, 1, 0) == (212, 224, 231)
    assert _pixel(pixels, width, 0, 1) == (24, 28, 35)
    assert _pixel(pixels, width, 1, 1) == (250, 191, 87)


def test_extract_nav_map_frame_rejects_invalid_payload() -> None:
    missing_map_info = SimpleNamespace(
        origin_id=1,
        quad_infos=[SimpleNamespace(content=1, depth=0)],
    )
    invalid_map_info = SimpleNamespace(
        origin_id=2,
        map_info=SimpleNamespace(root_depth=1, root_size_mm=0.0),
        quad_infos=[SimpleNamespace(content=1, depth=0)],
    )
    empty_map = SimpleNamespace(
        origin_id=3,
        map_info=SimpleNamespace(
            root_depth=1,
            root_size_mm=100.0,
            root_center_x=0.0,
            root_center_y=0.0,
        ),
        quad_infos=[],
    )

    assert extract_nav_map_frame(missing_map_info) is None
    assert extract_nav_map_frame(invalid_map_info) is None
    assert extract_nav_map_frame(empty_map) is None


def test_extract_nav_map_frame_rejects_partial_quadtree_payload() -> None:
    partial_map = SimpleNamespace(
        origin_id=6,
        map_info=SimpleNamespace(
            root_depth=1,
            root_size_mm=100.0,
            root_center_x=0.0,
            root_center_y=0.0,
        ),
        quad_infos=[SimpleNamespace(content=1, depth=0)],
    )

    assert extract_nav_map_frame(partial_map) is None


def test_extract_nav_map_frame_obeys_max_side() -> None:
    response = SimpleNamespace(
        origin_id=5,
        map_info=SimpleNamespace(
            root_depth=8,
            root_size_mm=512.0,
            root_center_x=0.0,
            root_center_y=0.0,
        ),
        quad_infos=[SimpleNamespace(content=1, depth=8)],
    )

    frame = extract_nav_map_frame(response, max_side=32)

    assert frame is not None
    assert frame.width == 32
    assert frame.height == 32


def test_extract_nav_map_frame_can_overlay_robot_pose_marker() -> None:
    response = SimpleNamespace(
        origin_id=7,
        map_info=SimpleNamespace(
            root_depth=8,
            root_size_mm=200.0,
            root_center_x=0.0,
            root_center_y=0.0,
        ),
        quad_infos=[SimpleNamespace(content=1, depth=8)],
    )
    robot_state = SimpleNamespace(
        pose=SimpleNamespace(x=0.0, y=0.0, origin_id=7),
        pose_angle_rad=0.0,
    )
    marker = nav_map_robot_pose_from_state(robot_state)

    frame = extract_nav_map_frame(response, max_side=64, robot_pose=marker)

    assert frame is not None
    width, height, pixels = _decode_png_rgb(frame.data)
    assert (width, height) == (64, 64)
    marker_pixels = 0
    for idx in range(0, len(pixels), 3):
        rgb = (pixels[idx], pixels[idx + 1], pixels[idx + 2])
        if rgb in {(255, 0, 255), (0, 255, 255), (255, 255, 255)}:
            marker_pixels += 1
    assert marker_pixels > 0


def _decode_png_rgb(data: bytes) -> tuple[int, int, bytes]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    cursor = 8
    width = 0
    height = 0
    idat = bytearray()

    while cursor < len(data):
        chunk_length = struct.unpack("!I", data[cursor : cursor + 4])[0]
        chunk_type = data[cursor + 4 : cursor + 8]
        chunk_data = data[cursor + 8 : cursor + 8 + chunk_length]
        cursor += chunk_length + 12

        if chunk_type == b"IHDR":
            width, height = struct.unpack("!II", chunk_data[:8])
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    raw = zlib.decompress(bytes(idat))
    stride = width * 3 + 1
    pixels = bytearray(width * height * 3)
    for y in range(height):
        row_start = y * stride
        assert raw[row_start] == 0
        source_start = row_start + 1
        source_end = source_start + width * 3
        target_start = y * width * 3
        pixels[target_start : target_start + width * 3] = raw[source_start:source_end]
    return width, height, bytes(pixels)


def _pixel(pixels: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    index = (y * width + x) * 3
    return (pixels[index], pixels[index + 1], pixels[index + 2])

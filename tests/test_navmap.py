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
        if rgb in {(255, 0, 255), (255, 255, 255), (0, 0, 0)}:
            marker_pixels += 1
    assert marker_pixels > 0


def test_extract_nav_map_frame_can_overlay_charger_marker() -> None:
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
    charger_pose = SimpleNamespace(origin_id=7, x_mm=0.0, y_mm=0.0, yaw_rad=None)

    frame = extract_nav_map_frame(response, max_side=64, charger_pose=charger_pose)

    assert frame is not None
    _, _, pixels = _decode_png_rgb(frame.data)
    marker_pixels = 0
    for idx in range(0, len(pixels), 3):
        rgb = (pixels[idx], pixels[idx + 1], pixels[idx + 2])
        if rgb in {(0, 180, 255), (0, 0, 0)}:
            marker_pixels += 1
    assert marker_pixels > 0


def test_extract_nav_map_frame_can_center_content() -> None:
    response = SimpleNamespace(
        origin_id=9,
        map_info=SimpleNamespace(
            root_depth=1,
            root_size_mm=200.0,
            root_center_x=0.0,
            root_center_y=0.0,
        ),
        quad_infos=[
            SimpleNamespace(content=0, depth=0),
            SimpleNamespace(content=0, depth=0),
            SimpleNamespace(content=0, depth=0),
            SimpleNamespace(content=1, depth=0),
        ],
    )

    frame = extract_nav_map_frame(response, max_side=8, center_content=True)

    assert frame is not None
    width, height, pixels = _decode_png_rgb(frame.data)
    assert (width, height) == (2, 2)
    unknown = (24, 28, 35)
    coords: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if _pixel(pixels, width, x, y) != unknown:
                coords.append((x, y))
    # Without centering this would only hit the bottom-right corner.
    assert coords
    avg_x = sum(x for x, _ in coords) / len(coords)
    avg_y = sum(y for _, y in coords) / len(coords)
    assert abs(avg_x - ((width - 1) / 2)) <= 0.5
    assert abs(avg_y - ((height - 1) / 2)) <= 0.5


def test_centering_ignores_overlay_marker_pixels() -> None:
    response = SimpleNamespace(
        origin_id=10,
        map_info=SimpleNamespace(
            root_depth=5,
            root_size_mm=200.0,
            root_center_x=0.0,
            root_center_y=0.0,
        ),
        quad_infos=[SimpleNamespace(content=1, depth=0)],
    )
    robot_pose = SimpleNamespace(origin_id=10, x_mm=-95.0, y_mm=-95.0, yaw_rad=0.0)

    frame_without_marker = extract_nav_map_frame(
        response,
        max_side=32,
        min_coverage_ratio=0.0,
        center_content=True,
    )
    frame_with_marker = extract_nav_map_frame(
        response,
        max_side=32,
        min_coverage_ratio=0.0,
        center_content=True,
        robot_pose=robot_pose,
    )

    assert frame_without_marker is not None
    assert frame_with_marker is not None
    width_a, height_a, pixels_a = _decode_png_rgb(frame_without_marker.data)
    width_b, height_b, pixels_b = _decode_png_rgb(frame_with_marker.data)
    assert (width_a, height_a) == (width_b, height_b)

    nav_color = (212, 224, 231)
    nav_pixels_a: set[tuple[int, int]] = set()
    nav_pixels_b: set[tuple[int, int]] = set()
    for y in range(height_a):
        for x in range(width_a):
            if _pixel(pixels_a, width_a, x, y) == nav_color:
                nav_pixels_a.add((x, y))
            if _pixel(pixels_b, width_b, x, y) == nav_color:
                nav_pixels_b.add((x, y))

    assert nav_pixels_a
    assert nav_pixels_a == nav_pixels_b


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

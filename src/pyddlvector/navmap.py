"""Nav map feed helpers."""

from __future__ import annotations

import asyncio
import contextlib
import math
import struct
import zlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import grpc

from .messaging import protocol

_DEFAULT_MAX_SIDE = 256
_MIN_COVERAGE_RATIO = 0.995
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_NODE_COLOR_MAP: dict[int, tuple[int, int, int]] = {
    int(protocol.NAV_NODE_UNKNOWN): (24, 28, 35),
    int(protocol.NAV_NODE_CLEAR_OF_OBSTACLE): (212, 224, 231),
    int(protocol.NAV_NODE_CLEAR_OF_CLIFF): (179, 205, 224),
    int(protocol.NAV_NODE_OBSTACLE_CUBE): (250, 191, 87),
    int(protocol.NAV_NODE_OBSTACLE_PROXIMITY): (224, 95, 95),
    int(protocol.NAV_NODE_OBSTACLE_PROXIMITY_EXPLORED): (191, 120, 88),
    int(protocol.NAV_NODE_OBSTACLE_UNRECOGNIZED): (178, 120, 188),
    int(protocol.NAV_NODE_CLIFF): (20, 20, 24),
    int(protocol.NAV_NODE_INTERESTING_EDGE): (120, 217, 195),
    int(protocol.NAV_NODE_NON_INTERESTING_EDGE): (115, 145, 163),
}
_FALLBACK_NODE_COLOR = (80, 80, 88)
_ROBOT_MARKER_CORE = (255, 0, 255)  # magenta
_ROBOT_MARKER_OUTLINE = (255, 255, 255)  # white
_ROBOT_FRONT_ARROW = (0, 0, 0)  # black
_CHARGER_MARKER_CORE = (0, 180, 255)  # cyan-blue
_CHARGER_MARKER_OUTLINE = (0, 0, 0)  # black
_RECOVERABLE_STREAM_ERRORS = {
    grpc.StatusCode.CANCELLED,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.UNAVAILABLE,
}


@dataclass(frozen=True, slots=True)
class NavMapFrame:
    """Rasterized nav map frame as PNG image bytes."""

    origin_id: int
    width: int
    height: int
    data: bytes


@dataclass(frozen=True, slots=True)
class NavMapRobotPose:
    """Robot pose projected into nav map coordinates."""

    origin_id: int
    x_mm: float
    y_mm: float
    yaw_rad: float | None = None


def nav_map_robot_pose_from_state(robot_state: Any) -> NavMapRobotPose | None:
    """Extract robot pose from a RobotState-like payload."""
    pose = getattr(robot_state, "pose", None)
    if pose is None:
        return None
    try:
        yaw = float(robot_state.pose_angle_rad) if hasattr(robot_state, "pose_angle_rad") else 0.0
        return NavMapRobotPose(
            origin_id=int(pose.origin_id),
            x_mm=float(pose.x),
            y_mm=float(pose.y),
            yaw_rad=yaw,
        )
    except (AttributeError, TypeError, ValueError):
        return None


async def iter_nav_map_frames(
    client: Any,
    *,
    frequency: float = 2.0,
    max_side: int = _DEFAULT_MAX_SIDE,
    read_timeout: float = 10.0,
    reconnect_delay: float = 1.0,
    min_coverage_ratio: float = _MIN_COVERAGE_RATIO,
    center_content: bool = False,
    robot_pose_provider: Callable[[], NavMapRobotPose | None] | None = None,
    charger_pose_provider: Callable[[], NavMapRobotPose | None] | None = None,
) -> AsyncIterator[NavMapFrame]:
    """Yield parsed nav map frames from a reconnecting NavMapFeed stream."""
    request = protocol.NavMapFeedRequest(frequency=frequency)

    while True:
        stream = client.stub.NavMapFeed(request)
        pending_read: asyncio.Task[Any] | None = None
        try:
            while True:
                if pending_read is None:
                    pending_read = asyncio.create_task(stream.read())

                done, _ = await asyncio.wait({pending_read}, timeout=read_timeout)
                if not done:
                    # Some robot/bridge stacks keep the stream open but stop emitting.
                    # Reconnect on idle timeout to recover from stalled streams.
                    break

                try:
                    response = pending_read.result()
                except asyncio.CancelledError:
                    break
                except grpc.aio.AioRpcError as err:
                    if err.code() in _RECOVERABLE_STREAM_ERRORS:
                        break
                    raise
                finally:
                    pending_read = None

                if response is None:
                    break

                robot_pose = None if robot_pose_provider is None else robot_pose_provider()
                frame = extract_nav_map_frame(
                    response,
                    max_side=max_side,
                    min_coverage_ratio=min_coverage_ratio,
                    center_content=center_content,
                    robot_pose=robot_pose,
                    charger_pose=None
                    if charger_pose_provider is None
                    else charger_pose_provider(),
                )
                if frame is not None:
                    yield frame
        finally:
            if pending_read is not None and not pending_read.done():
                pending_read.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending_read
            stream.cancel()

        await asyncio.sleep(max(0.0, reconnect_delay))


@dataclass(slots=True)
class _NavQuadNode:
    depth: int
    grid_x: int
    grid_y: int
    grid_size: int
    children: list[_NavQuadNode] | None = None
    content: int | None = None
    _next_child: int = 0

    def add_quad(self, *, content: int, depth: int) -> bool:
        """Add one serialized quad entry into the tree."""
        if depth == self.depth:
            self.content = content
            return True

        if self.children is None:
            next_depth = self.depth - 1
            next_size = self.grid_size // 2
            next_x = self.grid_x
            next_y = self.grid_y
            self.children = [
                _NavQuadNode(
                    next_depth,
                    next_x + next_size,
                    next_y + next_size,
                    next_size,
                ),
                _NavQuadNode(next_depth, next_x + next_size, next_y, next_size),
                _NavQuadNode(next_depth, next_x, next_y + next_size, next_size),
                _NavQuadNode(next_depth, next_x, next_y, next_size),
            ]

        child_index = min(self._next_child, 3)
        if self.children[child_index].add_quad(content=content, depth=depth):
            self._next_child += 1
        return self._next_child > 3

    def collect_leaf_nodes(self, sink: list[_NavQuadNode]) -> None:
        """Collect all terminal cells that contain map content."""
        if self.children is None:
            if self.content is not None:
                sink.append(self)
            return

        for child in self.children:
            child.collect_leaf_nodes(sink)


def extract_nav_map_frame(
    response: Any,
    *,
    max_side: int = _DEFAULT_MAX_SIDE,
    min_coverage_ratio: float = _MIN_COVERAGE_RATIO,
    center_content: bool = False,
    robot_pose: NavMapRobotPose | None = None,
    charger_pose: NavMapRobotPose | None = None,
) -> NavMapFrame | None:
    """Extract a rasterized PNG nav map frame from a ``NavMapFeedResponse`` payload."""
    map_info = getattr(response, "map_info", None)
    if map_info is None:
        return None

    root_depth = int(getattr(map_info, "root_depth", -1))
    root_size_mm = float(getattr(map_info, "root_size_mm", 0.0))
    if root_depth < 0 or root_size_mm <= 0.0:
        return None

    side = min(max(int(max_side), 1), 1 << root_depth)
    root_cells = 1 << root_depth
    root = _NavQuadNode(
        depth=root_depth,
        grid_x=0,
        grid_y=0,
        grid_size=root_cells,
    )

    for quad in getattr(response, "quad_infos", ()):
        quad_depth = int(getattr(quad, "depth", -1))
        if quad_depth < 0 or quad_depth > root_depth:
            continue
        root.add_quad(
            content=int(getattr(quad, "content", int(protocol.NAV_NODE_UNKNOWN))),
            depth=quad_depth,
        )

    leaf_nodes: list[_NavQuadNode] = []
    root.collect_leaf_nodes(leaf_nodes)
    if not leaf_nodes:
        return None
    covered_cells = sum(node.grid_size * node.grid_size for node in leaf_nodes)
    total_cells = root_cells * root_cells
    if total_cells <= 0:
        return None
    coverage_ratio = covered_cells / total_cells
    if coverage_ratio < float(min_coverage_ratio):
        # Some feeds intermittently emit partial trees; skip those to avoid clipped maps.
        return None

    rgb = bytearray(_rasterize_leaf_nodes(leaf_nodes, side=side, root_cells=root_cells))
    if charger_pose is not None:
        _overlay_nav_pose_marker(
            rgb,
            side=side,
            map_info=map_info,
            response_origin_id=int(getattr(response, "origin_id", 0)),
            pose=charger_pose,
            core_color=_CHARGER_MARKER_CORE,
            outline_color=_CHARGER_MARKER_OUTLINE,
            radius=max(2, side // 48),
            draw_heading_arrow=False,
        )
    if robot_pose is not None:
        _overlay_nav_pose_marker(
            rgb,
            side=side,
            map_info=map_info,
            response_origin_id=int(getattr(response, "origin_id", 0)),
            pose=robot_pose,
            core_color=_ROBOT_MARKER_CORE,
            outline_color=_ROBOT_MARKER_OUTLINE,
            radius=max(3, side // 44),
            draw_heading_arrow=True,
        )
    if center_content:
        rgb = _center_content_in_frame(rgb, side=side)
    return NavMapFrame(
        origin_id=int(getattr(response, "origin_id", 0)),
        width=side,
        height=side,
        data=_encode_png_rgb(side, side, bytes(rgb)),
    )


def _rasterize_leaf_nodes(
    leaf_nodes: list[_NavQuadNode],
    *,
    side: int,
    root_cells: int,
) -> bytes:
    image = bytearray(side * side * 3)
    _fill_full_image(image, side, _NODE_COLOR_MAP[int(protocol.NAV_NODE_UNKNOWN)])

    for node in leaf_nodes:
        color = _NODE_COLOR_MAP.get(int(node.content), _FALLBACK_NODE_COLOR)
        px0 = _clamp((node.grid_x * side) // root_cells, 0, side)
        px1 = _clamp(((node.grid_x + node.grid_size) * side) // root_cells, 0, side)
        py0 = _clamp((node.grid_y * side) // root_cells, 0, side)
        py1 = _clamp(((node.grid_y + node.grid_size) * side) // root_cells, 0, side)
        if px0 >= px1 or py0 >= py1:
            continue

        _fill_region(image, side, px0, px1, py0, py1, color)

    return bytes(image)


def _fill_full_image(image: bytearray, side: int, color: tuple[int, int, int]) -> None:
    row = bytes((color[0], color[1], color[2])) * side
    for y in range(side):
        start = y * side * 3
        image[start : start + side * 3] = row


def _fill_region(
    image: bytearray,
    side: int,
    px0: int,
    px1: int,
    py0: int,
    py1: int,
    color: tuple[int, int, int],
) -> None:
    fill = bytes((color[0], color[1], color[2])) * (px1 - px0)
    for map_y in range(py0, py1):
        pixel_y = side - 1 - map_y
        start = (pixel_y * side + px0) * 3
        image[start : start + (px1 - px0) * 3] = fill


def _encode_png_rgb(width: int, height: int, rgb_data: bytes) -> bytes:
    raw_rows = bytearray()
    stride = width * 3
    for row in range(height):
        start = row * stride
        raw_rows.append(0)
        raw_rows.extend(rgb_data[start : start + stride])

    ihdr = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw_rows))
    return b"".join(
        (
            _PNG_SIGNATURE,
            _png_chunk(b"IHDR", ihdr),
            _png_chunk(b"IDAT", idat),
            _png_chunk(b"IEND", b""),
        )
    )


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(payload, crc)
    return (
        struct.pack("!I", len(payload))
        + chunk_type
        + payload
        + struct.pack("!I", crc & 0xFFFFFFFF)
    )


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _overlay_nav_pose_marker(
    rgb: bytearray,
    *,
    side: int,
    map_info: Any,
    response_origin_id: int,
    pose: NavMapRobotPose,
    core_color: tuple[int, int, int],
    outline_color: tuple[int, int, int],
    radius: int,
    draw_heading_arrow: bool,
) -> None:
    if int(pose.origin_id) != int(response_origin_id):
        return
    root_size_mm = float(getattr(map_info, "root_size_mm", 0.0))
    if root_size_mm <= 0.0:
        return
    root_center_x = float(getattr(map_info, "root_center_x", 0.0))
    root_center_y = float(getattr(map_info, "root_center_y", 0.0))

    min_x = root_center_x - (root_size_mm * 0.5)
    min_y = root_center_y - (root_size_mm * 0.5)
    norm_x = (pose.x_mm - min_x) / root_size_mm
    norm_y = (pose.y_mm - min_y) / root_size_mm
    if not (0.0 <= norm_x <= 1.0 and 0.0 <= norm_y <= 1.0):
        return

    px = _clamp(int(norm_x * side), 0, side - 1)
    py_map = _clamp(int(norm_y * side), 0, side - 1)
    py = (side - 1) - py_map

    _draw_disc(rgb, side, px, py, radius + 1, outline_color)
    _draw_disc(rgb, side, px, py, radius, core_color)
    if not draw_heading_arrow or pose.yaw_rad is None:
        return

    ring_radius = radius + 1
    tip_x = int(round(px + (math.cos(pose.yaw_rad) * ring_radius)))
    tip_y = int(round(py - (math.sin(pose.yaw_rad) * ring_radius)))
    tail_radius = max(1, radius - 1)
    tail_x = int(round(px + (math.cos(pose.yaw_rad) * tail_radius)))
    tail_y = int(round(py - (math.sin(pose.yaw_rad) * tail_radius)))

    # Small front arrow that stays on the marker ring.
    wing_len = max(2, radius)
    wing_spread = math.radians(35.0)
    left_angle = pose.yaw_rad + math.pi - wing_spread
    right_angle = pose.yaw_rad + math.pi + wing_spread
    left_x = int(round(tip_x + (math.cos(left_angle) * wing_len)))
    left_y = int(round(tip_y - (math.sin(left_angle) * wing_len)))
    right_x = int(round(tip_x + (math.cos(right_angle) * wing_len)))
    right_y = int(round(tip_y - (math.sin(right_angle) * wing_len)))

    _draw_line_thick(
        rgb,
        side,
        tail_x,
        tail_y,
        tip_x,
        tip_y,
        thickness=1,
        color=_ROBOT_FRONT_ARROW,
    )
    _draw_line_thick(
        rgb,
        side,
        tip_x,
        tip_y,
        left_x,
        left_y,
        thickness=1,
        color=_ROBOT_FRONT_ARROW,
    )
    _draw_line_thick(
        rgb,
        side,
        tip_x,
        tip_y,
        right_x,
        right_y,
        thickness=1,
        color=_ROBOT_FRONT_ARROW,
    )


def _draw_disc(
    rgb: bytearray,
    side: int,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    radius_sq = radius * radius
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if (dx * dx) + (dy * dy) > radius_sq:
                continue
            x = cx + dx
            y = cy + dy
            if x < 0 or y < 0 or x >= side or y >= side:
                continue
            idx = (y * side + x) * 3
            rgb[idx : idx + 3] = bytes(color)


def _draw_line(
    rgb: bytearray,
    side: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
) -> None:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x = x0
    y = y0

    while True:
        if 0 <= x < side and 0 <= y < side:
            idx = (y * side + x) * 3
            rgb[idx : idx + 3] = bytes(color)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def _draw_line_thick(
    rgb: bytearray,
    side: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    thickness: int,
    color: tuple[int, int, int],
) -> None:
    for offset_x in range(-thickness, thickness + 1):
        for offset_y in range(-thickness, thickness + 1):
            if (offset_x * offset_x) + (offset_y * offset_y) > (thickness * thickness):
                continue
            _draw_line(
                rgb,
                side,
                x0 + offset_x,
                y0 + offset_y,
                x1 + offset_x,
                y1 + offset_y,
                color,
            )


def _center_content_in_frame(rgb: bytearray, *, side: int) -> bytearray:
    unknown = _NODE_COLOR_MAP[int(protocol.NAV_NODE_UNKNOWN)]
    min_x = side
    min_y = side
    max_x = -1
    max_y = -1

    for y in range(side):
        for x in range(side):
            idx = (y * side + x) * 3
            pixel = (rgb[idx], rgb[idx + 1], rgb[idx + 2])
            if pixel == unknown:
                continue
            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y

    if max_x < min_x or max_y < min_y:
        return rgb

    content_cx = (min_x + max_x) // 2
    content_cy = (min_y + max_y) // 2
    frame_cx = side // 2
    frame_cy = side // 2
    shift_x = frame_cx - content_cx
    shift_y = frame_cy - content_cy
    if shift_x == 0 and shift_y == 0:
        return rgb

    out = bytearray(side * side * 3)
    _fill_full_image(out, side, unknown)
    for y in range(side):
        ny = y + shift_y
        if ny < 0 or ny >= side:
            continue
        for x in range(side):
            nx = x + shift_x
            if nx < 0 or nx >= side:
                continue
            src = (y * side + x) * 3
            dst = (ny * side + nx) * 3
            out[dst : dst + 3] = rgb[src : src + 3]
    return out

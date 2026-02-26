"""Camera feed helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_JPEG_IMAGE_ENCODING_VALUES: set[int] = {6, 7, 8, 9, 10}


@dataclass(frozen=True, slots=True)
class CameraFrame:
    """Normalized camera frame payload."""

    timestamp: int
    image_id: int
    data: bytes


def extract_camera_frame(response: Any) -> CameraFrame | None:
    """Extract a JPEG camera frame from a CameraFeedResponse payload."""
    image_encoding = int(getattr(response, "image_encoding", -1))
    if image_encoding not in _JPEG_IMAGE_ENCODING_VALUES:
        return None

    data = bytes(getattr(response, "data", b""))
    if not data:
        return None

    return CameraFrame(
        timestamp=int(getattr(response, "frame_time_stamp", 0)),
        image_id=int(getattr(response, "image_id", 0)),
        data=data,
    )

from __future__ import annotations

from types import SimpleNamespace

from pyddlvector.camera import CameraFrame, extract_camera_frame


def test_extract_camera_frame_returns_jpeg_frame() -> None:
    response = SimpleNamespace(
        image_encoding=7,
        frame_time_stamp=123,
        image_id=42,
        data=b"\xff\xd8\xff",
    )

    frame = extract_camera_frame(response)

    assert isinstance(frame, CameraFrame)
    assert frame.timestamp == 123
    assert frame.image_id == 42
    assert frame.data == b"\xff\xd8\xff"


def test_extract_camera_frame_rejects_non_jpeg() -> None:
    response = SimpleNamespace(
        image_encoding=1,
        frame_time_stamp=1,
        image_id=1,
        data=b"\x00",
    )

    assert extract_camera_frame(response) is None

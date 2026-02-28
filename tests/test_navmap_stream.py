from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pyddlvector.navmap import iter_nav_map_frames


class FakeNavMapStream:
    def __init__(self, responses: list[object | None]) -> None:
        self._responses = list(responses)

    async def read(self) -> object | None:
        if not self._responses:
            return None
        response = self._responses.pop(0)
        if response == "pending":
            await asyncio.sleep(3600)
        if isinstance(response, Exception):
            raise response
        return response

    def cancel(self) -> None:
        return


class FakeStub:
    def __init__(self, streams: list[FakeNavMapStream]) -> None:
        self._streams = streams
        self.calls = 0

    def NavMapFeed(self, request: object) -> FakeNavMapStream:
        del request
        index = min(self.calls, len(self._streams) - 1)
        self.calls += 1
        return self._streams[index]


class FakeClient:
    def __init__(self, streams: list[FakeNavMapStream]) -> None:
        self.stub = FakeStub(streams)


def _response(origin_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        origin_id=origin_id,
        map_info=SimpleNamespace(
            root_depth=1,
            root_size_mm=200.0,
            root_center_x=0.0,
            root_center_y=0.0,
        ),
        quad_infos=[
            SimpleNamespace(content=1, depth=0),
            SimpleNamespace(content=1, depth=0),
            SimpleNamespace(content=1, depth=0),
            SimpleNamespace(content=1, depth=0),
        ],
    )


@pytest.mark.asyncio
async def test_iter_nav_map_frames_yields_frame() -> None:
    client = FakeClient([FakeNavMapStream([_response(2), None])])
    frames = iter_nav_map_frames(client, read_timeout=0.1, reconnect_delay=0.0)

    frame = await anext(frames)
    await frames.aclose()

    assert frame.origin_id == 2
    assert frame.width == 2
    assert frame.height == 2
    assert frame.data.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_iter_nav_map_frames_reconnects_after_stream_close() -> None:
    client = FakeClient(
        [
            FakeNavMapStream([_response(10), None]),
            FakeNavMapStream([_response(11), None]),
        ],
    )
    frames = iter_nav_map_frames(client, read_timeout=0.1, reconnect_delay=0.0)

    first = await anext(frames)
    second = await anext(frames)
    await frames.aclose()

    assert first.origin_id == 10
    assert second.origin_id == 11
    assert client.stub.calls >= 2


@pytest.mark.asyncio
async def test_iter_nav_map_frames_reconnects_after_idle_timeout() -> None:
    client = FakeClient(
        [
            FakeNavMapStream(["pending"]),
            FakeNavMapStream([_response(22), None]),
        ],
    )
    frames = iter_nav_map_frames(client, read_timeout=0.01, reconnect_delay=0.0)

    frame = await anext(frames)
    await frames.aclose()

    assert frame.origin_id == 22
    assert client.stub.calls >= 2

from __future__ import annotations

import asyncio

import pytest

from pyddlvector.exceptions import VectorProtocolError
from pyddlvector.settings import fetch_master_volume, normalize_master_volume, update_master_volume


def test_normalize_master_volume_accepts_wirepod_style_labels() -> None:
    assert normalize_master_volume("Medium Low") == "medium_low"
    assert normalize_master_volume("high") == "high"


def test_normalize_master_volume_rejects_unknown_value() -> None:
    with pytest.raises(VectorProtocolError):
        normalize_master_volume("max")


def test_fetch_master_volume_from_robot_settings_jdoc_int_value() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()

        async def unary_unary(self, path: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del request, kwargs
            assert path == "/Anki.Vector.external_interface.ExternalInterface/PullJdocs"

            class FakeDoc:
                json_doc = '{"master_volume": 2}'

            class FakeNamedJdoc:
                jdoc_type = 0
                doc = FakeDoc()

            class FakeResponse:
                named_jdocs = [FakeNamedJdoc()]

            return FakeResponse()

    volume = asyncio.run(fetch_master_volume(FakeClient(), timeout=5))
    assert volume == "medium_low"


def test_update_master_volume_uses_update_settings_rpc() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()

        async def rpc(self, method_name: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            assert method_name == "UpdateSettings"
            assert request.settings.master_volume == 4

            class FakeResponse:
                code = 0

            return FakeResponse()

    selected = asyncio.run(update_master_volume(FakeClient(), "medium_high", timeout=5))
    assert selected == "medium_high"

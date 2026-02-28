from __future__ import annotations

import asyncio

import pytest

from pyddlvector.exceptions import VectorProtocolError
from pyddlvector.settings import (
    fetch_eye_color,
    fetch_master_volume,
    normalize_eye_color_preset,
    normalize_master_volume,
    update_custom_eye_color,
    update_eye_color_preset,
    update_master_volume,
)


def test_normalize_master_volume_accepts_wirepod_style_labels() -> None:
    assert normalize_master_volume("Medium Low") == "medium_low"
    assert normalize_master_volume("high") == "high"


def test_normalize_master_volume_rejects_unknown_value() -> None:
    with pytest.raises(VectorProtocolError):
        normalize_master_volume("max")


def test_normalize_eye_color_preset_accepts_user_labels_and_enum_names() -> None:
    assert normalize_eye_color_preset("Azure Blue") == "azure_blue"
    assert normalize_eye_color_preset("CONFUSION_MATRIX_GREEN") == "other_green"


def test_normalize_eye_color_preset_rejects_unknown_value() -> None:
    with pytest.raises(VectorProtocolError):
        normalize_eye_color_preset("pink")


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


def test_fetch_eye_color_from_robot_settings_jdoc_with_custom_enabled() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()

        async def unary_unary(self, path: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del request, kwargs
            assert path == "/Anki.Vector.external_interface.ExternalInterface/PullJdocs"

            class FakeDoc:
                json_doc = (
                    '{"eye_color": 4, "custom_eye_color": '
                    '{"enabled": true, "hue": 0.42, "saturation": 0.75}}'
                )

            class FakeNamedJdoc:
                jdoc_type = 0
                doc = FakeDoc()

            class FakeResponse:
                named_jdocs = [FakeNamedJdoc()]

            return FakeResponse()

    eye_color = asyncio.run(fetch_eye_color(FakeClient(), timeout=5))
    assert eye_color.preset == "azure_blue"
    assert eye_color.custom_enabled is True
    assert eye_color.custom_hue == pytest.approx(0.42)
    assert eye_color.custom_saturation == pytest.approx(0.75)


def test_update_master_volume_uses_set_master_volume_rpc() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.calls: list[str] = []

        async def rpc(self, method_name: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            self.calls.append(method_name)
            assert method_name == "SetMasterVolume"
            assert request.volume_level == 3

            class FakeResponse:
                pass

            return FakeResponse()

    selected = asyncio.run(update_master_volume(FakeClient(), "medium_high", timeout=5))
    assert selected == "medium_high"


def test_update_eye_color_preset_uses_update_settings_rpc() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.calls: list[str] = []

        async def rpc(self, method_name: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            self.calls.append(method_name)
            assert method_name == "UpdateSettings"
            assert request.settings.eye_color == 5

            class FakeResponse:
                code = 0

            return FakeResponse()

    client = FakeClient()
    selected = asyncio.run(update_eye_color_preset(client, "purple", timeout=5))
    assert selected == "purple"
    assert client.calls == ["UpdateSettings"]


def test_update_eye_color_preset_falls_back_to_update_settings_path() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.unary_calls: list[str] = []

        async def unary_unary(self, path: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            self.unary_calls.append(path)
            assert path == "/Anki.Vector.external_interface.ExternalInterface/UpdateSettings"
            assert request.settings.eye_color == 4

            class FakeResponse:
                code = 0

            return FakeResponse()

    client = FakeClient()
    selected = asyncio.run(update_eye_color_preset(client, "azure_blue", timeout=5))
    assert selected == "azure_blue"
    assert client.unary_calls == [
        "/Anki.Vector.external_interface.ExternalInterface/UpdateSettings"
    ]


def test_update_eye_color_preset_retries_when_update_in_progress() -> None:
    class FakeClient:
        class Stub:
            UpdateSettings = object()

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.calls: list[str] = []
            self._responses = [1, 0]

        async def rpc(self, method_name: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs, request
            self.calls.append(method_name)
            assert method_name == "UpdateSettings"

            class FakeResponse:
                code = self._responses.pop(0)

            return FakeResponse()

    client = FakeClient()
    selected = asyncio.run(update_eye_color_preset(client, "purple", timeout=5))
    assert selected == "purple"
    assert client.calls == ["UpdateSettings", "UpdateSettings"]


def test_update_custom_eye_color_uses_set_eye_color_rpc() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.calls: list[str] = []

        async def rpc(self, method_name: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            self.calls.append(method_name)
            assert method_name == "SetEyeColor"
            assert request.hue == pytest.approx(0.2)
            assert request.saturation == pytest.approx(0.8)

            class FakeResponse:
                pass

            return FakeResponse()

    client = FakeClient()
    hue, saturation = asyncio.run(
        update_custom_eye_color(client, hue=0.2, saturation=0.8, timeout=5)
    )
    assert (hue, saturation) == (0.2, 0.8)
    assert client.calls == ["SetEyeColor"]


def test_update_custom_eye_color_rejects_out_of_range_values() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()

    with pytest.raises(VectorProtocolError):
        asyncio.run(update_custom_eye_color(FakeClient(), hue=1.2, saturation=0.4))


def test_update_master_volume_falls_back_to_update_settings() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.calls: list[str] = []

        async def rpc(self, method_name: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            self.calls.append(method_name)
            if method_name == "SetMasterVolume":
                raise VectorProtocolError("Stub does not expose RPC method 'SetMasterVolume'")

            assert method_name == "UpdateSettings"
            assert request.settings.master_volume == 4

            class FakeResponse:
                code = 0

            return FakeResponse()

    client = FakeClient()
    selected = asyncio.run(update_master_volume(client, "medium_high", timeout=5))
    assert selected == "medium_high"
    assert client.calls == ["SetMasterVolume", "UpdateSettings"]


def test_update_master_volume_mute_uses_update_settings_directly() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.calls: list[str] = []

        async def rpc(self, method_name: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            self.calls.append(method_name)
            assert method_name == "UpdateSettings"
            assert request.settings.master_volume == 0

            class FakeResponse:
                code = 0

            return FakeResponse()

    client = FakeClient()
    selected = asyncio.run(update_master_volume(client, "mute", timeout=5))
    assert selected == "mute"
    assert client.calls == ["UpdateSettings"]


def test_update_master_volume_mute_falls_back_to_update_settings_path() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.unary_calls: list[str] = []

        async def unary_unary(self, path: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            self.unary_calls.append(path)
            assert path == "/Anki.Vector.external_interface.ExternalInterface/UpdateSettings"
            assert request.settings.master_volume == 0

            class FakeResponse:
                code = 0

            return FakeResponse()

    client = FakeClient()
    selected = asyncio.run(update_master_volume(client, "mute", timeout=5))
    assert selected == "mute"
    assert client.unary_calls == [
        "/Anki.Vector.external_interface.ExternalInterface/UpdateSettings"
    ]


def test_update_master_volume_mute_retries_when_update_in_progress() -> None:
    class FakeClient:
        class Stub:
            UpdateSettings = object()

        def __init__(self) -> None:
            self.stub = self.Stub()
            self.calls: list[str] = []
            self._responses = [1, 0]

        async def rpc(self, method_name: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs, request
            self.calls.append(method_name)
            assert method_name == "UpdateSettings"

            class FakeResponse:
                code = self._responses.pop(0)

            return FakeResponse()

    client = FakeClient()
    selected = asyncio.run(update_master_volume(client, "mute", timeout=5))
    assert selected == "mute"
    assert client.calls == ["UpdateSettings", "UpdateSettings"]

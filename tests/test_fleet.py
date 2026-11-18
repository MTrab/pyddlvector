from __future__ import annotations

import asyncio
from pathlib import Path
from threading import get_ident

import pytest

from pyddlvector.client import VectorClient
from pyddlvector.config import RobotConfig, SdkConfigStore
from pyddlvector.fleet import VectorFleet


class FakeStub:
    pass


@pytest.mark.asyncio
async def test_fleet_caches_clients(tmp_path: Path) -> None:
    cert_file = tmp_path / "robot.cert"
    cert_file.write_text("cert")

    config_file = tmp_path / "sdk_config.ini"
    config_file.write_text(
        """
[00e20100]
name = Vector-A1B2
ip = 192.168.1.40
guid = guid-1
cert = {cert}
""".strip().format(cert=cert_file)
    )

    fleet = VectorFleet(
        config_store=SdkConfigStore(config_file),
        stub_factory=lambda channel: FakeStub(),
    )

    a = fleet.get("00e20100")
    b = fleet.get("00e20100")

    assert a is b
    await fleet.close()


@pytest.mark.asyncio
async def test_fleet_loads_config_off_loop_once_for_concurrent_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop_thread = get_ident()

    class Store(SdkConfigStore):
        loads = 0

        def load(self, serial: str) -> RobotConfig:
            assert get_ident() != loop_thread
            self.loads += 1
            return RobotConfig.from_runtime(
                serial=serial,
                name="Vector-A1B2",
                ip="192.168.1.40",
                guid="guid-1",
                cert_pem=b"cert",
            )

    async def connect(self, *, timeout=None):
        assert get_ident() == loop_thread

    monkeypatch.setattr(VectorClient, "connect", connect)
    store = Store()
    fleet = VectorFleet(config_store=store, stub_factory=lambda channel: FakeStub())
    first, second = await asyncio.gather(fleet.connect("00e20100"), fleet.connect("00E20100"))

    assert first is second
    assert store.loads == 1

from __future__ import annotations

from pathlib import Path

import pytest

from pyddlvector.config import SdkConfigStore
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

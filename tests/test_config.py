from __future__ import annotations

from pathlib import Path

import pytest

from pyddlvector.config import RobotConfig, SdkConfigStore
from pyddlvector.exceptions import VectorConfigurationError


def test_load_robot_config_from_sdk_ini(tmp_path: Path) -> None:
    config_file = tmp_path / "sdk_config.ini"
    cert_file = tmp_path / "vector.cert"
    cert_file.write_text("cert")
    config_file.write_text(
        """
[00e20100]
name = Vector-A1B2
ip = 192.168.1.42
guid = super-secret-guid
cert = {cert}
""".strip().format(cert=cert_file)
    )

    store = SdkConfigStore(config_file)
    config = store.load("00e20100")

    assert config.serial == "00e20100"
    assert config.name == "Vector-A1B2"
    assert config.host == "192.168.1.42:443"
    assert config.cert_file == cert_file


def test_missing_section_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "sdk_config.ini"
    config_file.write_text("[abc]\nname=Vector-ABCD\n")

    store = SdkConfigStore(config_file)
    with pytest.raises(VectorConfigurationError):
        store.load("missing")


def test_runtime_config_with_inline_cert() -> None:
    config = RobotConfig.from_runtime(
        serial="00908e7e",
        name="Vector-T3X9",
        ip="192.168.1.201",
        guid="guid",
        cert_pem="-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----",
    )

    assert config.serial == "00908e7e"
    assert config.host == "192.168.1.201:443"
    assert config.trusted_certs().startswith(b"-----BEGIN CERTIFICATE-----")

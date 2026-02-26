"""Robot configuration models and loaders."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from .exceptions import VectorConfigurationError


@dataclass(frozen=True, slots=True)
class RobotConfig:
    """Connection material required to authenticate and talk to a single robot."""

    serial: str | None
    name: str
    ip: str
    guid: str
    cert_file: Path | None = None
    cert_pem: bytes | None = None
    port: int = 443

    @property
    def host(self) -> str:
        """Return host:port used for the gRPC target."""
        return f"{self.ip}:{self.port}"

    @classmethod
    def from_runtime(
        cls,
        *,
        name: str,
        ip: str,
        guid: str,
        serial: str | None = None,
        cert_file: Path | str | None = None,
        cert_pem: bytes | str | None = None,
        port: int = 443,
    ) -> RobotConfig:
        """Build a config from runtime values (no sdk_config.ini required)."""
        cert_path = Path(cert_file) if cert_file is not None else None
        cert_bytes: bytes | None
        if isinstance(cert_pem, str):
            cert_bytes = cert_pem.encode("utf-8")
        else:
            cert_bytes = cert_pem

        if cert_path is None and cert_bytes is None:
            raise VectorConfigurationError("Either cert_file or cert_pem must be provided")

        return cls(
            serial=serial,
            name=name.strip(),
            ip=ip.strip(),
            guid=guid.strip(),
            cert_file=cert_path,
            cert_pem=cert_bytes,
            port=port,
        )

    def trusted_certs(self) -> bytes:
        """Return certificate bytes for TLS trust pinning."""
        if self.cert_pem is not None:
            if not self.cert_pem:
                raise VectorConfigurationError("Provided cert_pem is empty")
            return self.cert_pem

        if self.cert_file is None:
            raise VectorConfigurationError("No certificate source configured")
        if not self.cert_file.exists():
            raise VectorConfigurationError(f"Certificate file does not exist: {self.cert_file}")

        cert_bytes = self.cert_file.read_bytes()
        if not cert_bytes:
            raise VectorConfigurationError(f"Certificate file is empty: {self.cert_file}")
        return cert_bytes


class SdkConfigStore:
    """Loads robot credentials from a Vector-style ``sdk_config.ini`` file."""

    def __init__(self, config_file: Path | None = None) -> None:
        self._config_file = config_file or (Path.home() / ".anki_vector" / "sdk_config.ini")

    @property
    def path(self) -> Path:
        """Return resolved config file path."""
        return self._config_file

    def load(self, serial: str) -> RobotConfig:
        """Load a single robot config section by serial."""
        normalized = serial.strip().lower()
        parser = self._read_parser()

        if normalized not in parser:
            raise VectorConfigurationError(
                f"Robot serial '{normalized}' was not found in {self._config_file}"
            )

        section = parser[normalized]
        return self._robot_from_section(normalized, section)

    def load_all(self) -> dict[str, RobotConfig]:
        """Load all robot configurations keyed by serial."""
        parser = self._read_parser()
        robots: dict[str, RobotConfig] = {}

        for section_name in parser.sections():
            robots[section_name] = self._robot_from_section(section_name, parser[section_name])

        return robots

    def _read_parser(self) -> configparser.ConfigParser:
        if not self._config_file.exists():
            raise VectorConfigurationError(f"Config file does not exist: {self._config_file}")

        parser = configparser.ConfigParser(strict=False)
        parser.read(self._config_file)
        return parser

    def _robot_from_section(
        self,
        serial: str,
        section: configparser.SectionProxy,
    ) -> RobotConfig:
        try:
            ip = section["ip"].strip()
            name = section["name"].strip()
            guid = section["guid"].strip()
            cert_file = Path(section["cert"].strip())
        except KeyError as err:
            raise VectorConfigurationError(
                f"Missing key '{err.args[0]}' in config section '{serial}'"
            ) from err

        if not ip or not name or not guid:
            raise VectorConfigurationError(f"Section '{serial}' contains empty required values")

        return RobotConfig(
            serial=serial,
            name=name,
            ip=ip,
            guid=guid,
            cert_file=cert_file,
            cert_pem=None,
            port=443,
        )

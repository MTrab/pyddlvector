from __future__ import annotations

from typing import Any

import pytest

from pyddlvector.exceptions import (
    VectorAuthenticationError,
    VectorProvisioningError,
)
from pyddlvector.provisioning import (
    authenticate_robot_guid,
    fetch_official_session_token,
    provision_runtime_robot,
)


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, Any], content: bytes = b"x") -> None:
        self._payload = payload
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb
        return None

    async def post(
        self,
        url: str,
        data: dict[str, Any],
        headers: dict[str, str],
    ) -> _FakeHttpResponse:
        del url, data, headers
        return _FakeHttpResponse({"session": {"session_token": "token-123"}})


class _FakeChannel:
    def __init__(self) -> None:
        self.closed = False

    async def channel_ready(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class _AuthResponse:
    def __init__(self, guid: str | None) -> None:
        self.client_token_guid = guid


class _AuthStub:
    def __init__(self, guid: str | None = "guid-123") -> None:
        self._guid = guid

    async def UserAuthentication(
        self,
        request: dict[str, str],
        *,
        timeout: float | None = None,
    ) -> _AuthResponse:
        del request, timeout
        return _AuthResponse(self._guid)


class _AuthStubBytes:
    async def UserAuthentication(
        self,
        request: dict[str, str],
        *,
        timeout: float | None = None,
    ) -> _AuthResponse:
        del request, timeout
        return _AuthResponse(b"guid-bytes-123")


def _patch_grpc(monkeypatch: pytest.MonkeyPatch, channel: _FakeChannel) -> None:
    monkeypatch.setattr(
        "pyddlvector.provisioning.grpc.ssl_channel_credentials",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "pyddlvector.provisioning.grpc.aio.secure_channel",
        lambda host, creds, options=(): channel,
    )


@pytest.mark.asyncio
async def test_fetch_official_session_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pyddlvector.provisioning.httpx.AsyncClient", _FakeAsyncClient)

    token = await fetch_official_session_token("user@example.com", "password")
    assert token == "token-123"


@pytest.mark.asyncio
async def test_authenticate_robot_guid_success(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _FakeChannel()
    _patch_grpc(monkeypatch, channel)

    guid = await authenticate_robot_guid(
        ip="192.168.1.201",
        name="Vector-T3X9",
        cert_pem=b"pem",
        user_session_id="Anything1",
        stub_factory=lambda ch: _AuthStub(),
        request_factory=lambda session_id, client_name: {
            "user_session_id": session_id,
            "client_name": client_name,
        },
    )

    assert guid == "guid-123"
    assert channel.closed is True


@pytest.mark.asyncio
async def test_authenticate_robot_guid_bytes_are_decoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _FakeChannel()
    _patch_grpc(monkeypatch, channel)

    guid = await authenticate_robot_guid(
        ip="192.168.1.201",
        name="Vector-T3X9",
        cert_pem=b"pem",
        user_session_id="Anything1",
        stub_factory=lambda ch: _AuthStubBytes(),
        request_factory=lambda session_id, client_name: {
            "user_session_id": session_id,
            "client_name": client_name,
        },
    )

    assert guid == "guid-bytes-123"


@pytest.mark.asyncio
async def test_authenticate_robot_guid_missing_guid_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _FakeChannel()
    _patch_grpc(monkeypatch, channel)

    with pytest.raises(VectorAuthenticationError):
        await authenticate_robot_guid(
            ip="192.168.1.201",
            name="Vector-T3X9",
            cert_pem=b"pem",
            user_session_id="Anything1",
            stub_factory=lambda ch: _AuthStub(guid=None),
            request_factory=lambda session_id, client_name: {
                "user_session_id": session_id,
                "client_name": client_name,
            },
        )


@pytest.mark.asyncio
async def test_provision_runtime_robot_official(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_cert(serial: str, *, timeout: float = 10.0) -> bytes:
        del serial, timeout
        return b"cert-bytes"

    async def fake_session(
        username: str,
        password: str,
        *,
        timeout: float = 10.0,
        accounts_url: str = "",
        app_key: str = "",
    ) -> str:
        del username, password, timeout, accounts_url, app_key
        return "session-token"

    async def fake_guid(**kwargs: Any) -> str:
        del kwargs
        return "guid-from-rpc"

    monkeypatch.setattr("pyddlvector.provisioning.fetch_cert_for_official_serial", fake_cert)
    monkeypatch.setattr("pyddlvector.provisioning.fetch_official_session_token", fake_session)
    monkeypatch.setattr("pyddlvector.provisioning.authenticate_robot_guid", fake_guid)

    config = await provision_runtime_robot(
        mode="official",
        name="Vector-T3X9",
        ip="192.168.1.201",
        serial="00908e7e",
        username="user@example.com",
        password="secret",
        stub_factory=lambda ch: object(),
        request_factory=lambda session_id, client_name: {
            "user_session_id": session_id,
            "client_name": client_name,
        },
    )

    assert config.guid == "guid-from-rpc"
    assert config.cert_pem == b"cert-bytes"


@pytest.mark.asyncio
async def test_provision_runtime_robot_requires_official_credentials() -> None:
    with pytest.raises(VectorProvisioningError):
        await provision_runtime_robot(
            mode="official",
            name="Vector-T3X9",
            ip="192.168.1.201",
            serial="00908e7e",
            stub_factory=lambda ch: object(),
            request_factory=lambda session_id, client_name: {
                "user_session_id": session_id,
                "client_name": client_name,
            },
        )


@pytest.mark.asyncio
async def test_wirepod_falls_back_to_robot_tls_when_url_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_wirepod_fetch(
        serial: str,
        *,
        wirepod_url: str,
        timeout: float = 10.0,
    ) -> bytes:
        del serial, wirepod_url, timeout
        raise VectorProvisioningError("wirepod fetch failed")

    async def tls_cert(ip: str, *, timeout: float = 10.0, port: int = 443) -> bytes:
        del ip, timeout, port
        return b"tls-cert"

    async def fake_guid(**kwargs: Any) -> str:
        del kwargs
        return "guid-from-rpc"

    monkeypatch.setattr(
        "pyddlvector.provisioning.fetch_cert_for_wirepod_serial",
        failing_wirepod_fetch,
    )
    monkeypatch.setattr("pyddlvector.provisioning.fetch_cert_from_robot_tls", tls_cert)
    monkeypatch.setattr("pyddlvector.provisioning.authenticate_robot_guid", fake_guid)

    config = await provision_runtime_robot(
        mode="wirepod",
        name="Vector-T3X9",
        ip="192.168.1.201",
        serial="00908e7e",
        wirepod_url="http://escapepod.local:8080",
        stub_factory=lambda ch: object(),
        request_factory=lambda session_id, client_name: {
            "user_session_id": session_id,
            "client_name": client_name,
        },
    )

    assert config.cert_pem == b"tls-cert"
    assert config.guid == "guid-from-rpc"

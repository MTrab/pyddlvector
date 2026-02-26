"""Runtime provisioning helpers for certs, tokens, and robot GUIDs."""

from __future__ import annotations

import asyncio
import socket
import ssl
from typing import Any

import grpc
import httpx

from .config import RobotConfig
from .exceptions import (
    VectorAuthenticationError,
    VectorProvisioningError,
    VectorTimeoutError,
)

DEFAULT_ANKI_ACCOUNTS_URL = "https://accounts.api.anki.com/1/sessions"
DEFAULT_ANKI_CERT_URL_TEMPLATE = "https://session-certs.token.global.anki-services.com/vic/{serial}"
DEFAULT_WIREPOD_CERT_PATH_TEMPLATE = "/session-certs/{serial}"
DEFAULT_ANKI_APP_KEY = "aung2ieCho3aiph7Een3Ei"


async def fetch_official_session_token(
    username: str,
    password: str,
    *,
    timeout: float = 10.0,
    accounts_url: str = DEFAULT_ANKI_ACCOUNTS_URL,
    app_key: str = DEFAULT_ANKI_APP_KEY,
) -> str:
    """Authenticate against Anki accounts API and return session token."""
    headers = {
        "Anki-App-Key": app_key,
        "User-Agent": "pyddlvector/0.1",
    }
    payload = {"username": username, "password": password}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(accounts_url, data=payload, headers=headers)
        response.raise_for_status()
    except httpx.TimeoutException as err:
        raise VectorTimeoutError("Timed out while requesting official session token") from err
    except httpx.HTTPError as err:
        raise VectorProvisioningError("Failed to request official session token") from err

    try:
        data = response.json()
        token = data["session"]["session_token"]
    except (KeyError, TypeError, ValueError) as err:
        raise VectorProvisioningError("Official session token response was malformed") from err

    if not token:
        raise VectorProvisioningError("Official session token was empty")

    return token


async def fetch_cert_for_official_serial(serial: str, *, timeout: float = 10.0) -> bytes:
    """Download robot cert from official serial-based cert endpoint."""
    normalized = serial.strip().lower()
    if not normalized:
        raise VectorProvisioningError("Serial is required for official cert retrieval")

    url = DEFAULT_ANKI_CERT_URL_TEMPLATE.format(serial=normalized)
    return await fetch_cert_from_url(url, timeout=timeout)


async def fetch_cert_for_wirepod_serial(
    serial: str,
    *,
    wirepod_url: str,
    timeout: float = 10.0,
) -> bytes:
    """Download robot cert from a wire-pod instance."""
    normalized = serial.strip().lower()
    if not normalized:
        raise VectorProvisioningError("Serial is required for wire-pod cert retrieval")

    base = wirepod_url.rstrip("/")
    path = DEFAULT_WIREPOD_CERT_PATH_TEMPLATE.format(serial=normalized)
    return await fetch_cert_from_url(f"{base}{path}", timeout=timeout)


async def fetch_cert_from_url(url: str, *, timeout: float = 10.0) -> bytes:
    """Download PEM cert bytes from URL."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        response.raise_for_status()
    except httpx.TimeoutException as err:
        raise VectorTimeoutError(f"Timed out downloading cert from {url}") from err
    except httpx.HTTPError as err:
        raise VectorProvisioningError(f"Failed to download cert from {url}") from err

    if not response.content:
        raise VectorProvisioningError(f"Empty cert payload received from {url}")

    return bytes(response.content)


async def fetch_cert_from_robot_tls(
    hostname: str,
    *,
    port: int = 443,
    timeout: float = 10.0,
) -> bytes:
    """Read server certificate directly from robot TLS endpoint."""

    def _fetch() -> bytes:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((hostname, port), timeout=timeout) as raw_sock:
            with context.wrap_socket(raw_sock, server_hostname=hostname) as tls_sock:
                cert_der = tls_sock.getpeercert(binary_form=True)
        if cert_der is None:
            raise VectorProvisioningError("Robot did not present a TLS certificate")
        pem = ssl.DER_cert_to_PEM_cert(cert_der)
        return pem.encode("utf-8")

    try:
        return await asyncio.to_thread(_fetch)
    except TimeoutError as err:
        raise VectorTimeoutError(f"Timed out reading TLS cert from {hostname}:{port}") from err
    except OSError as err:
        raise VectorProvisioningError(f"Failed reading TLS cert from {hostname}:{port}") from err


async def authenticate_robot_guid(
    *,
    ip: str,
    name: str,
    cert_pem: bytes,
    user_session_id: str,
    stub_factory: Any,
    request_factory: Any,
    auth_rpc_name: str = "UserAuthentication",
    timeout: float = 10.0,
    port: int = 443,
    client_name: str | None = None,
) -> str:
    """Call robot UserAuthentication and return GUID token."""
    channel = None
    try:
        channel_creds = grpc.ssl_channel_credentials(root_certificates=cert_pem)
        channel = grpc.aio.secure_channel(
            f"{ip}:{port}",
            channel_creds,
            options=(("grpc.ssl_target_name_override", name),),
        )

        await asyncio.wait_for(channel.channel_ready(), timeout=timeout)

        stub = stub_factory(channel)
        rpc = getattr(stub, auth_rpc_name, None)
        if rpc is None or not callable(rpc):
            raise VectorProvisioningError(f"Stub does not expose auth RPC '{auth_rpc_name}'")

        actual_client_name = client_name or socket.gethostname()
        request = request_factory(user_session_id, actual_client_name)
        response = await rpc(request, timeout=timeout)
    except TimeoutError as err:
        raise VectorTimeoutError("Timed out while authenticating against robot") from err
    except grpc.RpcError as err:
        raise VectorAuthenticationError("Robot authentication RPC failed") from err
    finally:
        if channel is not None:
            await channel.close()

    guid = getattr(response, "client_token_guid", None)
    if not guid:
        raise VectorAuthenticationError("Robot auth response did not include a GUID token")
    return str(guid)


async def provision_runtime_robot(
    *,
    mode: str,
    name: str,
    ip: str,
    serial: str | None,
    stub_factory: Any,
    request_factory: Any,
    username: str | None = None,
    password: str | None = None,
    wirepod_url: str | None = None,
    session_id: str | None = None,
    timeout: float = 10.0,
) -> RobotConfig:
    """Provision cert+guid at runtime and return a ready RobotConfig.

    Supported modes:
    - ``official``: requires ``serial``, ``username``, and ``password``.
    - ``wirepod``: requires ``serial`` + ``wirepod_url`` or will fallback to robot TLS cert.
    """
    normalized_mode = mode.strip().lower()

    if normalized_mode == "official":
        if serial is None:
            raise VectorProvisioningError("Serial is required for official provisioning")
        if not username or not password:
            raise VectorProvisioningError("Username and password are required for official mode")

        cert_pem = await fetch_cert_for_official_serial(serial, timeout=timeout)
        resolved_session_id = await fetch_official_session_token(
            username,
            password,
            timeout=timeout,
        )
    elif normalized_mode == "wirepod":
        if wirepod_url and serial:
            cert_pem = await fetch_cert_for_wirepod_serial(
                serial,
                wirepod_url=wirepod_url,
                timeout=timeout,
            )
        else:
            cert_pem = await fetch_cert_from_robot_tls(ip, timeout=timeout)
        resolved_session_id = session_id or "Anything1"
    else:
        raise VectorProvisioningError(f"Unsupported provisioning mode '{mode}'")

    guid = await authenticate_robot_guid(
        ip=ip,
        name=name,
        cert_pem=cert_pem,
        user_session_id=resolved_session_id,
        stub_factory=stub_factory,
        request_factory=request_factory,
        timeout=timeout,
    )

    return RobotConfig.from_runtime(
        serial=serial,
        name=name,
        ip=ip,
        guid=guid,
        cert_pem=cert_pem,
    )

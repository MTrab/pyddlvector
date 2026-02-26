# pyddlvector

Async-first Python module for communicating with Vector robots over authenticated gRPC.

## What This Provides

- `RobotConfig.from_runtime(...)`: build robot config from runtime values
- `SdkConfigStore`: optional loader from `~/.anki_vector/sdk_config.ini`
- `VectorClient`: async TLS + token authenticated gRPC client per robot
- `VectorFleet`: multi-robot lifecycle and client cache
- `provision_runtime_robot(...)`: runtime provisioning for `official` and `wirepod`
- `pyddlvector.messaging`: bundled protobuf + gRPC stubs (no external SDK required)
- typed, integration-friendly exception model

## Quick Start (Home Assistant Runtime Style)

```python
import asyncio

from pyddlvector import RobotConfig, VectorClient, messaging


async def main() -> None:
    robot = RobotConfig.from_runtime(
        serial="00908e7e",
        name="Vector-T3X9",
        ip="192.168.1.201",
        guid="<GUID_FROM_SETUP>",
        cert_file="/path/to/Vector-T3X9-00908e7e.cert",
        # Alternative: cert_pem=b"..."
    )

    client = VectorClient(
        robot,
        stub_factory=lambda channel: messaging.client.ExternalInterfaceStub(channel),
        default_timeout=10.0,
    )

    await client.connect()
    try:
        # Example: invoke an RPC exposed by your stub.
        # request = protocol.ProtocolVersionRequest(...)
        # response = await client.rpc("ProtocolVersion", request)
        pass
    finally:
        await client.disconnect()


asyncio.run(main())
```

## Runtime Provisioning (No INI File)

You can provision cert + GUID at runtime and get a ready `RobotConfig`.

```python
import asyncio

from pyddlvector import messaging, provision_runtime_robot


def auth_request_factory(session_id: str, client_name: str):
    return messaging.protocol.UserAuthenticationRequest(
        user_session_id=session_id.encode("utf-8"),
        client_name=client_name.encode("utf-8"),
    )


async def main() -> None:
    robot = await provision_runtime_robot(
        mode="wirepod",  # or "official"
        name="Vector-T3X9",
        ip="192.168.1.201",
        serial="00908e7e",
        wirepod_url="http://escapepod.local:8080",  # for wire-pod mode
        # username="you@example.com",              # required for official mode
        # password="secret",                       # required for official mode
        stub_factory=lambda channel: messaging.client.ExternalInterfaceStub(channel),
        request_factory=auth_request_factory,
    )
    print(robot)


asyncio.run(main())
```

## Notes

- Connection model follows Vector SDK behavior: pinned robot certificate + guid access token.
- `sdk_config.ini` is optional; runtime injection works directly for Home Assistant config entries.
- This package intentionally stays Home Assistant agnostic in core client logic.
- In some container/remote environments, `*.local` mDNS hostnames (for example `escapepod.local`)
  do not resolve. Use a direct `wirepod_url` IP like `http://192.168.1.50:8080` in those setups.

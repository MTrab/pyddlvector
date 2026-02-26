# pyddlvector

Async-first Python communication module for Digital Dream Labs / Anki Vector.

`pyddlvector` is designed as a reusable transport/client layer that Home Assistant can consume, while keeping Home Assistant-specific logic outside the core package.

## Goals

- Async-first robot communication APIs
- Deterministic connection lifecycle with explicit timeouts
- Typed, actionable exceptions for integration consumers
- Runtime provisioning support (`wirepod` and `official`)
- Bundled protobuf/gRPC messaging modules (`pyddlvector.messaging`)

## Python and Tooling

- Python: `3.13+`
- Package manager/build: `poetry`
- Tests: `pytest`, `pytest-asyncio`
- Lint/format: `ruff`

## Installation

### From source (development)

```bash
git clone https://github.com/MTrab/pyddlvector.git
cd pyddlvector
poetry install
```

### In another project

Pinning directly from Git is supported:

```text
pyddlvector@git+https://github.com/MTrab/pyddlvector.git@main
```

## Package Layout

- `src/pyddlvector/client.py`: async gRPC client (`VectorClient`)
- `src/pyddlvector/config.py`: robot config model and optional SDK INI loader
- `src/pyddlvector/fleet.py`: multi-robot lifecycle helper
- `src/pyddlvector/provisioning.py`: runtime provisioning flow
- `src/pyddlvector/settings.py`: settings parsing + master volume utilities
- `src/pyddlvector/statistics.py`: lifetime statistics parsing
- `src/pyddlvector/stimulation.py`: stimulation payload parsing
- `src/pyddlvector/camera.py`: camera frame extraction helper
- `src/pyddlvector/messaging/`: bundled generated protobuf + gRPC stubs

## Public API Snapshot

Imported from `pyddlvector` top-level:

- `RobotConfig`, `SdkConfigStore`
- `VectorClient`, `VectorFleet`
- `provision_runtime_robot`
- `fetch_lifetime_statistics`, `parse_lifetime_statistics_jdoc`
- `fetch_master_volume`, `update_master_volume`, `normalize_master_volume`
- `parse_stimulation_info`
- `extract_camera_frame`
- `messaging`
- Exception types under `pyddlvector.exceptions`

## Quickstart: Async Client

```python
import asyncio

from pyddlvector import RobotConfig, VectorClient, messaging


async def main() -> None:
    robot = RobotConfig.from_runtime(
        serial="00908e7e",
        name="Vector-T3X9",
        ip="192.168.1.201",
        guid="<GUID>",
        cert_file="/path/to/Vector-T3X9-00908e7e.cert",
    )

    client = VectorClient(
        robot,
        stub_factory=lambda channel: messaging.client.ExternalInterfaceStub(channel),
        default_timeout=10.0,
    )

    await client.connect(timeout=10.0)
    try:
        # request = messaging.protocol.BatteryStateRequest()
        # response = await client.rpc("BatteryState", request, timeout=10.0)
        pass
    finally:
        await client.disconnect()


asyncio.run(main())
```

## Quickstart: Runtime Provisioning

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
        wirepod_url="http://192.168.1.50:8080",  # wirepod mode
        # username="you@example.com",            # official mode
        # password="secret",                     # official mode
        stub_factory=lambda channel: messaging.client.ExternalInterfaceStub(channel),
        request_factory=auth_request_factory,
        timeout=10.0,
    )
    print(robot)


asyncio.run(main())
```

## Error Model

Core exceptions are mapped into explicit integration-friendly types:

- `VectorConfigurationError`
- `VectorConnectionError`
- `VectorTimeoutError`
- `VectorProtocolError`
- `VectorAuthenticationError`
- `VectorProvisioningError`
- `VectorRPCError`

When consuming this module, prefer handling these types rather than raw transport exceptions.

## Development Workflow

### Run tests

```bash
poetry run pytest
```

### Run lint/format checks

```bash
poetry run ruff check .
poetry run ruff format .
```

### Optional pre-commit hooks

```bash
python3 -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Integration Notes (Home Assistant)

- Keep Home Assistant-specific behavior out of this package core.
- Preserve bounded retry loops and explicit timeouts in I/O paths.
- Avoid leaking secrets/certificates/tokens in logs.
- Maintain stable typed APIs where possible.

## Limitations and Environment Notes

- mDNS hostnames (for example `*.local`) may fail in some containerized environments.
- Prefer direct IPs for `wirepod_url` when mDNS resolution is unreliable.

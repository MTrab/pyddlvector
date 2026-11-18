# Vector protocol sources

The Python service and message definitions are based on the
[Wire-pod Python SDK at `065fc19`](https://github.com/kercre123/wirepod-vector-python-sdk/tree/065fc19/anki_vector/messaging).
The settings messages match the
[DDL vector-cloud settings descriptor at `bba1d08`](https://github.com/digital-dream-labs/vector-cloud/blob/bba1d08028b18c504d6cad781790f4c4f2e3cf7d/internal/proto/external_interface/settings.pb.go).
It defines field 7 for `master_volume` and preserves explicitly set default
values such as mute and teal. Set a preset together with an empty
`CustomEyeColor` message to disable custom mode.

The generated bindings use protoc 5.29.0 from `grpcio-tools==1.70.0`. When
regenerating, stage the proto files under `anki_vector/messaging` to preserve
their descriptor import names. Use the installed `googleapis-common-protos`
package as an additional include root. Generate Python with `--python_out` and
generate the service bindings with `--grpc_python_out` for
`external_interface.proto`. Change generated imports of sibling modules to
relative imports and use `__name__` for the generated Python message module name.

Regenerate the named RPC helpers after changing the service descriptor or
request schemas. The generator reads the bundled descriptor and preserves
the Python names defined in its explicit overrides.

```bash
poetry run python scripts/generate-rpc-helpers.py
poetry run python scripts/generate-rpc-helpers.py --check
```

## Provisioning endpoints

| Mode | Request |
|---|---|
| Official | `POST https://accounts.api.anki.com/1/sessions` for an Anki session token |
| Official | `GET https://session-certs.token.global.anki-services.com/vic/{serial}` for the robot certificate |
| Wire-pod | `GET {wirepod_url}/session-certs/{serial}` for the robot certificate, as used by the Wire-pod SDK |
| Both | `UserAuthentication` on the robot's TLS gRPC endpoint, port 443 by default, to exchange the session ID for a GUID |

The client uses the trusted robot certificate and checks the configured robot
name. Subsequent RPCs send the GUID as a bearer token. A failed certificate
download stops provisioning. Supply a previously trusted certificate via
`cert_pem` when the Wire-pod certificate endpoint is unavailable.
`fetch_cert_from_robot_tls` validates the peer against system trust or the
provided `trusted_cert_pem`, using `server_name` when connecting by IP.

## Physical robot smoke test

1. Connect with an existing SDK configuration or provision through a trusted
   Wire-pod instance. Confirm that `BatteryState` returns and `iter_events()`
   yields `robot_state` events.
2. Save the current volume and eye color. Test mute and teal and read them back
   through `PullJdocs`. Restore the original settings.
3. Play a short `SayText` command with `run_with_behavior_control`. Confirm that
   the robot resumes normal behavior after completion and after cancellation.
4. Receive a camera JPEG and a NavMap PNG. Interrupt the network and verify
   that the consumers time out and that a subsequent connection works after
   restoring the network.

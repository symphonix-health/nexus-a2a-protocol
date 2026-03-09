# SDK Harness

## Purpose

`tests/sdk_harness` validates SDK transport behavior with a matrix-driven harness.

Matrix:

- `nexus-a2a/artefacts/matrices/nexus_sdk_transport_matrix.json` (44 baseline scenarios)

Profiles:

- `smoke`: fast PR subset (`test_tags` includes `smoke`)
- `full`: all scenarios

Modes:

- `mock` (default): deterministic in-process runtime
- `live`: external Nexus runtime

## Commands

```bash
# smoke profile, deterministic mock runtime
$env:SDK_HARNESS_MODE="mock"
$env:SDK_HARNESS_PROFILE="smoke"
python -m pytest tests/sdk_harness/test_sdk_transport.py -q

# full profile, deterministic mock runtime
$env:SDK_HARNESS_MODE="mock"
$env:SDK_HARNESS_PROFILE="full"
python -m pytest tests/sdk_harness/test_sdk_transport.py -q

# live runtime validation
$env:SDK_HARNESS_MODE="live"
$env:SDK_HARNESS_PROFILE="smoke"
$env:NEXUS_ROUTER_URL="http://localhost:9000"
$env:NEXUS_ROUTER_RPC_URL="http://localhost:9000/rpc"
$env:NEXUS_WS_URL_TEMPLATE="ws://localhost:9000/ws/{task_id}?token={token}"
$env:NEXUS_JWT_TOKEN="<token>"
python -m pytest tests/sdk_harness/test_sdk_transport.py -q
```

## Environment Variables

- `SDK_HARNESS_MODE`: `mock|live` (default `mock`)
- `SDK_HARNESS_PROFILE`: `smoke|full` (default `full`)
- `NEXUS_ROUTER_URL`: `http://localhost:9000` (`live` mode)
- `NEXUS_ROUTER_RPC_URL`: `http://localhost:9000/rpc` (`live` mode)
- `NEXUS_WS_URL_TEMPLATE`: `ws://localhost:9000/ws/{task_id}?token={token}` (`live` mode)
- `NEXUS_JWT_TOKEN`: unset by default (`live` mode)
- `NEXUS_JWT_SECRET`: `dev-secret-change-me` fallback if token is unset (`live` mode)

## Report Output

Harness writes:

- `docs/sdk-conformance-report.json`

Fields include total/pass/fail/error counts and per-scenario duration/status.

## Troubleshooting

- Auth failures in live mode: verify token scope includes `nexus:invoke`.
- Stream timeout: confirm runtime emits events for submitted `task_id`.
- WebSocket auth failures: verify `token` placeholder in `NEXUS_WS_URL_TEMPLATE`.
- Scenario mismatch: run smoke first, then full to isolate failures quickly.

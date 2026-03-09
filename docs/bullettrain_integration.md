# BulletTrain Integration Guide

## Goal

Consume Nexus as an external SDK dependency while keeping BulletTrain tests transport-agnostic.

## Dependency Strategy

Use git dependency pinning first.

```toml
# pyproject.toml (BulletTrain)
[project.dependencies]
nexus-a2a-protocol = { git = "https://github.com/GMailTedam/nexus-a2a-protocol", rev = "<commit-or-tag>" }
```

## Adapter Contract in BulletTrain

Inside BulletTrain, depend only on the SDK transport contract.

```python
from nexus_a2a_protocol import AgentTransport, TransportFactory

transport: AgentTransport = TransportFactory.from_env()
```

## Transport Switch in BulletTrain

```bash
# CI deterministic simulation
$env:AGENT_TRANSPORT="simulation"

# integration environment with real Nexus
$env:AGENT_TRANSPORT="http_sse"
$env:NEXUS_ROUTER_URL="http://localhost:9000"
$env:NEXUS_JWT_TOKEN="<token>"
```

or

```bash
$env:AGENT_TRANSPORT="websocket"
$env:NEXUS_ROUTER_RPC_URL="http://localhost:9000/rpc"
$env:NEXUS_WS_URL_TEMPLATE="ws://localhost:9000/ws/{task_id}?token={token}"
$env:NEXUS_JWT_TOKEN="<token>"
```

## BulletTrain Consumer Checklist

- Pin Nexus SDK to a specific commit/tag.
- Keep BulletTrain workflow tests bound to `AgentTransport` only.
- Run simulation profile in PR CI.
- Run Nexus live profile in integration/staging.
- Enforce schema-compatible event assertions (`type`, `payload`, terminal event).
- Track deprecation notices for `shared.nexus_common.mcp_adapter` and avoid new usage.

## Troubleshooting

- Event assertion drift: compare BulletTrain assertions with `docs/sdk_transport.md` schema.
- Live-mode auth errors: align token secret/scope with Nexus runtime policy.
- WS stream issues: verify runtime websocket endpoint and URL template formatting.

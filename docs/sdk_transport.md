# SDK Transport Layer

## Purpose

The Nexus SDK transport layer exposes a stable adapter contract for orchestration and test code:

- `AgentTransport.connect()`
- `AgentTransport.send_task()`
- `AgentTransport.stream_events()`
- `AgentTransport.stop()`

Implementations:

- `SimulationTransport`
- `HttpSseTransport`
- `WebSocketTransport`

Factory:

- `TransportFactory.from_env()`

## Unified Event Schema

All transports emit normalized `TaskEvent` values:

```json
{
  "event_id": "string",
  "timestamp": "ISO-8601",
  "agent_id": "string",
  "type": "nexus.task.status|nexus.task.final|nexus.task.error",
  "payload": {},
  "task_id": "string",
  "seq": 1
}
```

## Mode Selection

```bash
# simulation (default)
$env:AGENT_TRANSPORT="simulation"

# HTTP + SSE
$env:AGENT_TRANSPORT="http_sse"
$env:NEXUS_ROUTER_URL="http://localhost:9000"

# WebSocket streaming + HTTP RPC
$env:AGENT_TRANSPORT="websocket"
$env:NEXUS_ROUTER_RPC_URL="http://localhost:9000/rpc"
$env:NEXUS_WS_URL_TEMPLATE="ws://localhost:9000/ws/{task_id}?token={token}"
```

## Authentication

Token resolution order:

1. `NEXUS_JWT_TOKEN` (pass-through)
2. `NEXUS_JWT_SECRET` (mint HS256 token)
3. dev fallback secret (`dev-secret-change-me`)

Optional overrides:

- `NEXUS_JWT_SUBJECT` (default `sdk-client`)
- `NEXUS_JWT_SCOPE` (default `nexus:invoke`)

## Environment Variables and Defaults

- `AGENT_TRANSPORT`: `simulation` (default), `http_sse`, `websocket`
- `NEXUS_ROUTER_URL`: `http://localhost:9000` (used by `http_sse`)
- `NEXUS_ROUTER_RPC_URL`: `http://localhost:9000/rpc` (used by `websocket`)
- `NEXUS_WS_URL_TEMPLATE`: `ws://localhost:9000/ws/{task_id}?token={token}` (used by `websocket`)
- `NEXUS_TRANSPORT_TIMEOUT_SECONDS`: `30`
- `NEXUS_AGENT_ID`: `nexus-agent`
- `NEXUS_SIM_AGENT_ID`: `simulation-agent`
- `NEXUS_JWT_TOKEN`: unset by default
- `NEXUS_JWT_SECRET`: `dev-secret-change-me` fallback if no token is provided
- `NEXUS_JWT_SUBJECT`: `sdk-client`
- `NEXUS_JWT_SCOPE`: `nexus:invoke`

## Minimal Usage

```python
import asyncio

from nexus_a2a_protocol import TransportFactory


async def main() -> None:
    transport = TransportFactory.from_env()
    await transport.connect()

    submission = await transport.send_task(
        {
            "method": "tasks/sendSubscribe",
            "params": {
                "task": {"type": "ConformanceTask", "inputs": {"message": "hello"}}
            },
        }
    )

    async for event in transport.stream_events(submission.task_id):
        print(event.type, event.payload)
        if event.is_terminal:
            break

    await transport.stop()


asyncio.run(main())
```

## Troubleshooting

- `401 auth_failed`: set a valid `NEXUS_JWT_TOKEN` or align `NEXUS_JWT_SECRET` with runtime secret.
- No streamed events: verify `/events/{task_id}` is reachable and supports `text/event-stream`.
- WebSocket mode stalls: verify `NEXUS_WS_URL_TEMPLATE` path and token placeholder.
- Mode mismatch: ensure `AGENT_TRANSPORT` matches the environment under test.

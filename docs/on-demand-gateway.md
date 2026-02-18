# On-Demand Gateway and Process Manager

The On-Demand Gateway lazily starts agent processes and proxies JSON-RPC over HTTP to them. It provides a single entry point for all agent RPC calls and manages agent lifecycles, including dependency start order and idle reaping.

## Why use it?

- Single endpoint for agent RPC: `POST /rpc/{agent_alias}`
- Lazy start agents only when needed; stop them after idle TTL
- Automatically bring up transitive dependencies first (e.g., `triage` depends on `diagnosis`)
- Uniform health/readiness endpoints for automation
- Great for demos, CI, and local development

## Endpoints

- `GET /health` → service liveness
- `GET /readyz` → service readiness metadata (includes managed agent count)
- `GET /api/agents` → status list of all configured agents (running/pid/port/path)
- `POST /api/agents/{alias}/start` → ensure agent (and its deps) are started
- `POST /api/agents/{alias}/stop` → stop a managed agent process
- `POST /rpc/{agent_alias}` → JSON-RPC 2.0 proxy to the agent’s `/rpc`

Example RPC via gateway:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:8100/rpc/triage \
  -d '{"jsonrpc":"2.0","id":"1","method":"tasks/sendSubscribe","params":{"task":{}}}'
```

## Agent aliases

The gateway normalizes aliases to improve ergonomics:
- lowercased, hyphens → underscores
- common suffixes stripped: `_agent`, `_scheduler`, `_service`
- `care_coordinator` → `coordinator`

Examples: `triage`, `primary_care`, `coordinator`, `followup`, `diagnosis`.

## Dependencies and reaping

- Dependencies are expanded in a stable topological order; see `DEFAULT_DEPENDENCY_GRAPH` in `shared/on_demand_gateway/app/main.py`.
- Idle processes are reaped after `IDLE_TTL_SECONDS` (env-configurable); background task runs on `IDLE_REAP_INTERVAL_SECONDS` cadence.

## Environment variables

- `NEXUS_ON_DEMAND_GATEWAY_PORT` (default: `8100`)
- `NEXUS_ON_DEMAND_HEALTH_ATTEMPTS` / `NEXUS_ON_DEMAND_HEALTH_TIMEOUT_SECONDS` / `NEXUS_ON_DEMAND_HEALTH_INTERVAL_SECONDS`
- `NEXUS_ON_DEMAND_RPC_TIMEOUT_SECONDS`
- `NEXUS_ON_DEMAND_IDLE_TTL_SECONDS` / `NEXUS_ON_DEMAND_DEPENDENCIES_JSON`

When the gateway launches agents, it also prepares a base environment for children:
- Populates `PYTHONPATH`, `NEXUS_JWT_SECRET`, `OPENAI_MODEL`, `DID_VERIFY`
- Sets per-agent RPC/HTTP envs from `config/agents.json` (e.g., `NEXUS_TRIAGE_RPC`, `TRIAGE_URL`)
- Exports `AGENT_URLS` (comma-separated) for the Command Centre

## Using the launcher

You can have the launcher manage the gateway and backend together.

```powershell
# Full system with gateway (agents + backend + gateway)
.\.venv\Scripts\python.exe tools\launch_all_agents.py --with-gateway

# Backend only + gateway (for traffic generator routed via gateway)
.\.venv\Scripts\python.exe tools\launch_all_agents.py --backend-only --with-gateway

# Only the gateway (pure on-demand workflows)
.\.venv\Scripts\python.exe tools\launch_all_agents.py --only-gateway

# Override the gateway port
.\.venv\Scripts\python.exe tools\launch_all_agents.py --with-gateway --gateway-port 8111
```

Behavior niceties:
- If a gateway is already running on the chosen port, the launcher prints an "already running" message and skips counting it.
- After start, the launcher prints an "Effective configuration" block with the Backend URL, Gateway URL, and selected LLM profile.

## Scenario runner and traffic generator

- Scenario runner can route via the gateway:

```powershell
.\.venv\Scripts\python.exe tools\run_helixcare_scenarios.py --gateway http://localhost:8100
```

- Traffic generator can route triage RPC via the gateway:

```powershell
.\.venv\Scripts\python.exe tools\traffic_generator.py --gateway-url http://localhost:8100
```

## Security notes

- Gateway forwards `Authorization` headers and uses `application/json` content type
- Use TLS by providing `NEXUS_SSL_CERTFILE` and `NEXUS_SSL_KEYFILE` (optional `NEXUS_SSL_CA_CERTS` and `NEXUS_SSL_CERT_REQS`)

## Troubleshooting

- 404 on `/rpc/{alias}`: verify the alias after normalization (see rules above) and that the agent exists in `config/agents.json`
- 503 on proxy: check child process health at `/.well-known/agent-card.json` on the agent’s port; verify dependency graph and logs
- Idle shutdowns: increase `NEXUS_ON_DEMAND_IDLE_TTL_SECONDS` to keep agents warm during demos

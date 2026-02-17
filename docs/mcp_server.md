# NEXUS-A2A MCP Server

## Purpose

The NEXUS-A2A MCP Server is a **thin Model Context Protocol (MCP) façade** over the NEXUS agent mesh. It exposes agent discovery, JSON-RPC calling, and task streaming as MCP tools, allowing any MCP host (VS Code Copilot, Claude Desktop, etc.) to interact with the full agent ecosystem through a single, standardised interface.

The server does **not** run clinical logic itself — it routes calls to already-running NEXUS agents and translates their SSE task events into MCP progress notifications.

```
┌───────────┐      STDIO / JSON-RPC 2.0      ┌────────────────────┐
│  MCP Host  │ ◄──────────────────────────────► │  nexus-a2a-mcp     │
│ (Copilot)  │                                  │  MCP Server        │
└───────────┘                                  └──────┬─────────────┘
                                                      │
                          ┌───────────────────────────┼───────────────┐
                          ▼                           ▼               ▼
                   ┌──────────┐             ┌──────────────┐   ┌──────────┐
                   │ Triage   │             │ Diagnosis    │   │ Other    │
                   │ Agent    │             │ Agent        │   │ Agents   │
                   │ :8021    │             │ :8022        │   │ :80xx    │
                   └──────────┘             └──────────────┘   └──────────┘
```

## Quick Start

### 1. Install dependencies

```bash
pip install -e ".[mcp]"
```

### 2. Start agents

Use one of:

```bash
python tools/launch_all_agents.py                # all agents
python tools/launch_all_agents.py --with-backend  # agents + command centre
```

### 3. Run the MCP server

```bash
python tools/nexus_mcp_server.py
```

Or use the VS Code task **"MCP Server: Start"**.

### 4. VS Code integration

The server is pre-configured in `.vscode/mcp.json`. Once agents are running, VS Code Copilot can discover and invoke the NEXUS tools automatically.

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `NEXUS_JWT_TOKEN` | *(none)* | Pre-minted bearer token (mode A — highest priority) |
| `NEXUS_JWT_SECRET` | `dev-secret-change-me` | HS256 secret to mint a token on startup (mode B) |
| `NEXUS_JWT_SUBJECT` | `mcp-server` | JWT subject claim |
| `NEXUS_JWT_SCOPE` | `nexus:invoke` | JWT scope claim |
| `AGENT_URLS` | *(none)* | Comma-separated agent base URLs (overrides config) |
| `NEXUS_AGENTS_CONFIG` | auto-discover | Explicit path to `agents.json` |

### Authentication modes

1. **Mode A (token passthrough)**: Set `NEXUS_JWT_TOKEN` with a pre-minted token.
2. **Mode B (mint on startup)**: Set `NEXUS_JWT_SECRET` — the server mints a 24h token using HS256.
3. **Mode C (default fallback)**: No env set — uses `dev-secret-change-me` (with warning).
4. **Per-call override**: Every tool accepts an optional `token` parameter.

## Tool Reference

### `nexus_list_agents`

List all registered NEXUS agents with optional live health probing.

**Input:**
```json
{ "include_status": true }
```

**Output:**
```json
[
  {
    "alias": "triage_agent",
    "port": 8021,
    "url": "http://localhost:8021",
    "description": "Patient triage agent",
    "category": "ed_triage",
    "health": { "status": "healthy" }
  }
]
```

### `nexus_get_agent_card`

Fetch the agent card JSON from `/.well-known/agent-card.json`.

**Input:**
```json
{ "agent": "triage_agent" }
```

**Output:** The agent card document (agent_id, capabilities, endpoint, etc.).

### `nexus_call_rpc`

Generic JSON-RPC call to any agent method.

**Input:**
```json
{
  "agent": "triage_agent",
  "method": "tasks/send",
  "params": "{\"task_id\": \"t-1\", \"message\": {\"role\": \"user\", \"parts\": [{\"type\": \"text\", \"text\": \"Patient: fever\"}]}}"
}
```

**Output:** The raw JSON-RPC response envelope (`result` or `error`).

### `nexus_send_task`

Convenience wrapper for `tasks/send` / `tasks/sendSubscribe`.

**Input:**
```json
{
  "agent": "triage_agent",
  "message": "Patient: chest pain, age 65, vital signs stable",
  "subscribe": false
}
```

**Output:** JSON-RPC response with task_id, status, and artifacts.

### `nexus_stream_task_events`

Stream SSE events for a running task until terminal.

**Input:**
```json
{
  "agent": "triage_agent",
  "task_id": "t-12345"
}
```

**Output:** JSON array of events (`nexus.task.status`, `nexus.task.final`, etc.).

## Resource

### `nexus://topology`

Returns the full agent topology from `config/agents.json` as a JSON document. Available to MCP hosts that support resource reading.

## Walkthrough

A typical pair-programming session:

1. **Discover agents:**
   ```
   → nexus_list_agents(include_status=true)
   ← [{alias: "triage_agent", health: {status: "healthy"}}, ...]
   ```

2. **Inspect capabilities:**
   ```
   → nexus_get_agent_card(agent="triage_agent")
   ← {agent_id: "did:nexus:triage", capabilities: ["tasks/send", ...]}
   ```

3. **Send a task:**
   ```
   → nexus_send_task(agent="triage_agent", message="Patient: 65yo, chest pain")
   ← {result: {task_id: "t-xxx", status: {state: "completed"}, artifacts: [...]}}
   ```

4. **Stream events** (for long-running tasks):
   ```
   → nexus_stream_task_events(agent="triage_agent", task_id="t-xxx")
   ← [{event: "nexus.task.status", data: ...}, {event: "nexus.task.final", data: ...}]
   ```

## STDIO Logging Caveats

The MCP STDIO transport uses `stdout` exclusively for JSON-RPC protocol messages. All logging is directed to `stderr`. If you see garbled output, ensure no library writes to stdout.

## Transport

- **Current:** STDIO (ideal for local VS Code pairing)
- **Future:** Streamable HTTP for remote connectivity (MCP spec supports this natively)

## Testing

```bash
# Unit tests (no agents needed)
python -m pytest tests/test_mcp_adapter.py tests/test_mcp_server_tools.py -v

# Integration tests (uses in-process mock agent)
python -m pytest tests/test_mcp_integration.py -v

# All tests
python -m pytest tests/ -v
```

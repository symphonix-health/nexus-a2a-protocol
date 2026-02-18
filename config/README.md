# NEXUS-A2A Agent Configuration

## Overview

The `agents.json` file is the **centralized port registry** for all NEXUS-A2A agents and backend services. This prevents port conflicts and provides a single source of truth for agent discovery.

## Structure

### Backend Services

Backend services (like Command Centre) are NOT agents - they are monitoring/infrastructure services.

```json
{
  "backend": {
    "command_centre": {
      "port": 8099,
      "path": "shared/command-centre",
      "description": "Command Centre monitoring dashboard backend",
      "type": "backend"
    }
  }
}
```

**Key Point**: Backend services are on port 8099+ and should NOT be included in agent health checks.

### Agents

Agents are organized by use case category:

```json
{
  "agents": {
    "category_name": {
      "agent_name": {
        "port": 8021,
        "path": "demos/category/agent-name",
        "description": "Agent description",
        "rpc_env": "NEXUS_AGENT_RPC",  // Optional: RPC endpoint env var
        "env": "AGENT_URL"              // Optional: HTTP endpoint env var
      }
    }
  }
}
```

## Port Allocation Strategy

| Port Range | Purpose | Notes |
|------------|---------|-------|
| 8020-8029 | HelixCare + ED Triage | Core clinical workflow agents |
| 8030-8039 | Telemed Scribe | Transcription and EHR agents |
| 8040-8049 | Consent Verification | Privacy and consent agents |
| 8050-8059 | Public Health | Surveillance and reporting agents |
| 8090-8099 | Backend/Infrastructure | Command Centre, mock servers |
| 1883 | MQTT Broker | Message queue |
| 6379 | Redis | Cache and pub/sub |
| 8080 | Mock FHIR Server | Testing FHIR API |

## Usage

### Launch Agents + Backend (default)

```bash
python tools/launch_all_agents.py
```

Starts agents on ports 8021-8053 and the Command Centre backend on port 8099 by default.

### Launch Agents Only (skip backend)

```bash
python tools/launch_all_agents.py --no-backend
```

Skips Command Centre startup.

### On-Demand Gateway (optional)

```bash
# Start with gateway (agents + backend + gateway)
python tools/launch_all_agents.py --with-gateway

# Start only backend + gateway (no agents)
python tools/launch_all_agents.py --backend-only --with-gateway

# Start only the gateway (no backend, no agents)
python tools/launch_all_agents.py --only-gateway

# Override port
python tools/launch_all_agents.py --with-gateway --gateway-port 8111
```

The gateway proxies JSON-RPC to `/rpc/{agent}` and lazily starts agent processes.

### Stop All Services

```bash
python tools/launch_all_agents.py --stop
```

## Why This Matters

### Problem Before

- Port 8099 (Command Centre) was in the agent list
- Health checks tried to fetch `/.well-known/agent-card.json` from port 8099
- Command Centre doesn't have this endpoint → **404 errors**
- No clear separation between agents and infrastructure

### Solution Now

- ✅ Centralized configuration in `agents.json`
- ✅ Backend services separated from agents
- ✅ Health checks only run against actual agents
- ✅ Port conflicts prevented at configuration level
- ✅ Auto-generated environment variables for inter-agent communication

## Adding a New Agent

1. Choose an available port from the appropriate range
2. Add entry to `agents.json` under the correct category:

```json
{
  "agents": {
    "your_category": {
      "new_agent": {
        "port": 8060,
        "path": "demos/your-category/new-agent",
        "description": "Your agent description",
        "rpc_env": "NEXUS_NEW_AGENT_RPC"
      }
    }
  }
}
```

1. No code changes needed - `launch_all_agents.py` reads this automatically

## Environment Variables Auto-Generated

The launcher automatically creates these environment variables:

- **RPC endpoints**: `NEXUS_*_RPC` → `http://localhost:PORT/rpc`
- **HTTP endpoints**: `*_URL` → `http://localhost:PORT`
- **Agent list**: `AGENT_URLS` → Comma-separated list of all agent URLs (excludes backend)

## Verification

After launching, check:

```bash
# Command Centre agent list
curl http://localhost:8099/api/agents

# Verify agent health (should have agent-card.json)
curl http://localhost:8021/.well-known/agent-card.json
```

## Reserved Ports Reference

Documented in `agents.json`:

```json
{
  "reserved_ports": {
    "8080": "Mock FHIR Server",
    "8090": "Compliance HITL Agent",
    "1883": "MQTT Broker",
    "6379": "Redis"
  }
}
```

## Migration Notes

Old hardcoded `AGENTS` list in `launch_all_agents.py` has been replaced with dynamic loading from `agents.json`. The backend (port 8099) is now properly separated and only started with `--with-backend` flag.

# Fix: Port 8099 HTTP Error 404 - Backend Port Conflict Resolution

## Problem

Port 8099 (Command Centre backend) was returning **404 errors** when agents tried to fetch `/.well-known/agent-card.json`.

### Root Cause

The Command Centre backend (port 8099) was incorrectly listed in the `AGENTS` array alongside actual agents. During health checks, the launcher tried to verify it as an agent endpoint, but the Command Centre is a **backend service** that doesn't implement the agent discovery protocol.

```
✗ :8099 HTTP Error 404: Not Found
```

## Solution

### 1. Centralized Configuration (`config/agents.json`)

Created a **port registry** that separates:

- **Agents** (ports 8021-8053) - implement NEXUS-A2A protocol
- **Backend** (port 8099) - Command Centre monitoring dashboard
- **Reserved Ports** (1883, 6379, 8080, 8090)

### 2. Updated Launch Script

`tools/launch_all_agents.py` now:

- ✅ Reads from centralized config
- ✅ Separates agents from backend services
- ✅ Only health checks agents (not backend)
- ✅ Auto-generates `AGENT_URLS` excluding port 8099
- ✅ Supports optional `--with-backend` flag

### 3. Usage

#### Launch Only Agents (Default)

```bash
python tools/launch_all_agents.py
```

Starts ports 8021-8053 (**excludes** 8099)

#### Launch Agents + Backend

```bash
python tools/launch_all_agents.py --with-backend
```

Starts agents + Command Centre on 8099

#### Stop All

```bash
python tools/launch_all_agents.py --stop
```

### 4. VS Code Tasks

Updated `.vscode/tasks.json` with two tasks:

- **HelixCare: Launch All Agents** - agents only
- **HelixCare: Launch Agents + Command Centre** - agents + backend

## Benefits

1. **No More 404 Errors** - Backend excluded from agent health checks
2. **Clear Separation** - Agents vs infrastructure services
3. **Centralized Config** - Single source of truth for port allocation
4. **Prevents Conflicts** - Port registry prevents accidental overlaps
5. **Auto Environment Vars** - `NEXUS_*_RPC` and `AGENT_URLS` generated automatically

## Configuration Structure

```json
{
  "backend": {
    "command_centre": {
      "port": 8099,
      "type": "backend",
      "endpoints": ["/api/agents", "/api/events", "/ws"]
    }
  },
  "agents": {
    "category": {
      "agent_name": {
        "port": 8021,
        "path": "demos/.../agent",
        "rpc_env": "NEXUS_AGENT_RPC"
      }
    }
  }
}
```

## Environment Variables

Automatically set from config:

| Variable | Value | Purpose |
|----------|-------|---------|
| `AGENT_URLS` | `http://localhost:8021,...,8053` | Command Centre monitoring (excludes 8099) |
| `NEXUS_TRIAGE_RPC` | `http://localhost:8021/rpc` | Inter-agent RPC |
| `NEXUS_DIAGNOSIS_RPC` | `http://localhost:8022/rpc` | Inter-agent RPC |
| ... | ... | Auto-generated for all agents |

## Health Check Output

### Before (Error)

```
✗ :8099 HTTP Error 404: Not Found
```

### After (Correct)

```
Agent Health: 18/18 agents responding
✓ :8021 healthy
✓ :8022 healthy
...
✓ :8053 healthy

Backend Services:
✓ Command Centre :8099 running
```

## Documentation

- `config/README.md` - Full configuration guide
- `config/agents.json` - Port registry
- Updated docstring in `tools/launch_all_agents.py`

## Migration Notes

Old hardcoded approach:

```python
AGENTS = [
    ("demos/ed-triage/triage-agent", 8021),
    # ...
    ("shared/command-centre", 8099),  # ❌ Backend mixed with agents
]
```

New config-driven approach:

```python
agents, backend = load_agent_config()  # ✅ Separated
```

## Verification

```bash
# No 404 on backend
curl http://localhost:8099/api/agents  # ✅ 200 OK

# Agents have discovery endpoint
curl http://localhost:8021/.well-known/agent-card.json  # ✅ 200 OK

# Backend doesn't (and shouldn't)
curl http://localhost:8099/.well-known/agent-card.json  # ❌ 404 (expected)
```

## Files Changed

- ✅ Created `config/agents.json` - Port registry
- ✅ Created `config/README.md` - Configuration docs
- ✅ Updated `tools/launch_all_agents.py` - Config-driven launcher
- ✅ Updated `.vscode/tasks.json` - Added backend launch task

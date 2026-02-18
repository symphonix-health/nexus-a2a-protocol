# HelixCare Architecture (High-Level and Detailed)

This document captures the current architecture aligned with the on-demand gateway and process manager, Command Centre observability, and JSON-RPC agent mesh.

## High-Level (Components)

Rendered image (for decks/wikis):

![High-Level Architecture](diagrams/architecture-high-level.svg)

```mermaid
flowchart LR
  subgraph Clients
    A1[Scenario Runner\n(tools/helixcare_scenarios.py)]
    A2[Traffic Generator\n(tools/traffic_generator.py)]
    A3[Other Clients / Tests]
  end

  GW[On-Demand Gateway\nFastAPI + httpx\n/rpc/{agent}]:::svc
  CC[Command Centre\nFastAPI + Dashboard\n:8099]:::svc

  subgraph Agents
    AG1[Primary Care]
    AG2[Diagnosis]
    AG3[Pharmacy]
    AG4[Followup]
    AG5[Imaging]
    AG6[Coordinator]
    AGN(... more ...)
  end

  R[Redis (pub/sub)]:::infra
  FHIR[FHIR Server]:::infra
  MQTT[MQTT Broker]:::infra

  classDef svc fill:#eaf5ff,stroke:#3b82f6,color:#000;
  classDef infra fill:#f5f5f5,stroke:#64748b,color:#000;

  A1 -->|JSON-RPC| GW
  A2 -->|JSON-RPC| GW
  A3 -->|JSON-RPC| GW

  GW -->|Proxy /rpc| AG1
  GW --> AG2
  GW --> AG3
  GW --> AG4
  GW --> AG5
  GW --> AG6

  CC <-->|Health, Agents| Agents
  Agents -->|Events| R

  CC -->|Subscribe| R
  Agents -->|FHIR API| FHIR
  Agents -->|Pub/Sub| MQTT
```

Notes:
- Clients call the Gateway at `/rpc/{agent}`. The gateway lazily starts the target agent and its dependencies, then proxies JSON-RPC.
- Command Centre monitors agents via `/health` and discovery endpoints and consumes events from Redis.
- Agents may publish events to Redis, interact with FHIR, and optionally with MQTT for streaming workflows.

## Detailed (Gateway-First RPC Path)

Rendered image (for decks/wikis):

![Detailed RPC Path](diagrams/architecture-detailed.svg)

```mermaid
sequenceDiagram
  participant Client (Scenario Runner)
  participant Gateway (/rpc/{alias})
  participant ProcMgr (Process Manager)
  participant Agent (Primary Care)
  participant DepA (Diagnosis)
  participant DepB (Pharmacy)

  Client->>Gateway: POST /rpc/primary_care { jsonrpc, method, params }
  activate Gateway
  Gateway->>ProcMgr: ensure_started("primary_care")
  activate ProcMgr
  ProcMgr->>DepA: start if needed; wait for /.well-known/agent-card.json
  ProcMgr->>DepB: start if needed; wait for /.well-known/agent-card.json
  ProcMgr->>Agent: start if needed; wait for /.well-known/agent-card.json
  ProcMgr-->>Gateway: spec(port=8025, alias=primary_care)
  deactivate ProcMgr
  Gateway->>Agent: POST /rpc { same JSON-RPC payload }
  activate Agent
  Agent-->>Gateway: JSON-RPC response
  deactivate Agent
  Gateway-->>Client: JSON-RPC response (transparent proxy)
  deactivate Gateway
```

Alignment Highlights:
- The gateway manages dependency ordering and readiness checks before proxying.
- Dependencies and idle reaping are environment-configurable and implemented in `shared/on_demand_gateway/app/main.py`.
- Direct-to-agent RPC remains supported, but gateway routing is recommended in local/dev flows for process lifecycle convenience.

---

Rendering locally:

```powershell
# Render SVG/PNG via Kroki (requires internet):
.\.venv\Scripts\python.exe scripts\render_mermaid_via_kroki.py \
  docs\diagrams\architecture-high-level.mmd \
  docs\diagrams\architecture-detailed.mmd

# Or render fully offline with Node (after npm install):
npm run diagrams

# If corporate policy blocks Chromium download, point to an existing Chrome:
$env:CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
npm run diagrams:chrome
```

Outputs are saved next to the .mmd files as .svg and .png.

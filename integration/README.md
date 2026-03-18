# Integration Harness — BulletTrain ↔ GHARRA ↔ Nexus-A2A

System integration harness that validates interoperability between three repositories:

```
SignalBox (BulletTrain)
    ↓
resolve agent using GHARRA
    ↓
retrieve endpoint + trust metadata
    ↓
pass routing request to Nexus
    ↓
Nexus connects to real test agent
    ↓
agent returns response
```

## Architecture

```
integration/
├── docker-compose.yml              # Starts all services from real repos
├── Dockerfile.gharra               # GHARRA build (fixes upstream Dockerfile)
├── Dockerfile.seed                 # One-shot GHARRA seed container
├── conftest.py                     # Pytest fixtures (shared across all tests)
├── pytest.ini                      # Pytest configuration
├── requirements.txt                # Python dependencies
├── harness/
│   ├── seed.py                     # Seeds GHARRA with canonical e2e agents
│   ├── gharra_resolver.py          # Direct GHARRA HTTP client
│   ├── nexus_connector.py          # JSON-RPC client for Nexus gateway
│   ├── signalbox_driver.py         # SignalBox orchestration driver
│   ├── workflow_runner.py          # End-to-end workflow orchestrator
│   └── scale_simulation.py         # Large-scale load simulation
└── tests/
    ├── test_agent_resolution.py    # GHARRA agent resolution (13 tests)
    ├── test_agent_routing.py       # Nexus routing + invocation (8 tests)
    ├── test_signalbox_workflow.py  # Full SignalBox workflow (11 tests)
    ├── test_policy_enforcement.py  # Policy tag enforcement (18 tests)
    └── test_scale_simulation.py    # Load simulation (6 tests)
```

## Services

| Service            | Port | Source Repository          | Role                              |
|--------------------|------|----------------------------|-----------------------------------|
| GHARRA             | 8400 | `global-agent-registry/`   | Agent registry & trust authority  |
| Nexus Gateway      | 8100 | `Nexus-A2A-protocol/`      | On-demand agent routing gateway   |
| SignalBox          | 8221 | `BulletTrain/`             | Identity FSM + GHARRA integration |

## Data Sources — No Synthetic Data

All test agents come from the GHARRA repository's existing e2e test fixtures
(`tests/e2e/conftest.py::seed_full_scenario()`):

| Agent              | ID                                  | Jurisdiction | Protocol          |
|--------------------|-------------------------------------|--------------|-------------------|
| Triage Agent       | `gharra://ie/agents/triage-e2e`     | IE           | nexus-a2a-jsonrpc |
| Referral Agent     | `gharra://gb/agents/referral-e2e`   | GB           | http-rest         |
| Radiology AI       | `gharra://us/agents/radiology-e2e`  | US           | http-rest         |
| Pathology Analyzer | `gharra://de/agents/pathology-e2e`  | DE           | nexus-a2a-jsonrpc |

Agent endpoints point to real Nexus test agents (triage, diagnosis, imaging, pharmacy)
already present in the Nexus-A2A-protocol repository under `demos/`.

## Quick Start

### 1. Start Services

```bash
cd integration/
docker compose up --build -d
```

### 2. Seed GHARRA

```bash
# Seed via Docker (if services are in Docker network)
docker compose run --rm seed

# Or seed directly (if GHARRA is accessible on localhost)
pip install httpx
python harness/seed.py
```

### 3. Run Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

### One-liner

```bash
docker compose up --build -d && \
docker compose run --rm seed && \
pytest tests/ -v
```

## Running Without Docker

Start each service in a separate terminal:

```bash
# Terminal 1: GHARRA
cd ../global-agent-registry
GHARRA_AUTH_MODE=disabled GHARRA_DB_PATH=:memory: \
GHARRA_RATE_LIMIT_ENABLED=false \
  uvicorn gharra.api.main:app --port 8400

# Terminal 2: Nexus Gateway
cd ../Nexus-A2A-protocol
NEXUS_JWT_SECRET=integration-test-secret \
  python -m uvicorn shared.on_demand_gateway.app.main:app --port 8100

# Terminal 3: SignalBox
cd ../BulletTrain
GHARRA_BASE_URL=http://localhost:8400 NEXUS_GATEWAY_URL=http://localhost:8100 \
AUTH_MODE=dev DEV_AUTH_SUBJECT=integration-harness \
DEV_AUTH_ROLES=admin,platform_admin SERVICE_PORT=8221 \
DEV_AUTH_SCOPES=signalbox:gharra:resolve,signalbox:gharra:discover,signalbox:identity:read,signalbox:identity:write,signalbox:task:execute,signalbox:task:read,signalbox:session:read,signalbox:session:write,signalbox:external:read,signalbox:external:execute,signalbox:governance:read \
  python -m uvicorn services.signalbox.main:app --port 8221

# Terminal 4: Seed + Tests
cd integration/
python harness/seed.py
pytest tests/ -v
```

## Environment Variables

| Variable                     | Default                   | Description                         |
|------------------------------|---------------------------|-------------------------------------|
| `GHARRA_BASE_URL`            | `http://localhost:8400`   | GHARRA registry endpoint            |
| `NEXUS_GATEWAY_URL`          | `http://localhost:8100`   | Nexus on-demand gateway              |
| `SIGNALBOX_BASE_URL`         | `http://localhost:8221`   | SignalBox service                    |
| `NEXUS_JWT_SECRET`           | `integration-test-secret` | JWT signing secret for Nexus         |
| `GHARRA_RATE_LIMIT_ENABLED`  | `true`                    | Set `false` for integration testing  |
| `GHARRA_DEFAULT_RATE_TIER`   | `developer`               | Default tier for anonymous callers   |
| `AUTH_MODE`                   | `oidc`                    | Set `dev` for integration testing    |

## Integration Flow

```
┌─────────────┐    POST /api/signalbox/gharra/resolve
│  SignalBox   │─────────────────────────────────────────┐
│  (8221)      │                                         │
└──────┬───────┘                                         │
       │                                                 │
       │ GharraClient.resolve_agent()                    │
       ▼                                                 │
┌─────────────┐    GET /v1/agents/{id}                   │
│   GHARRA    │◄─────────────────────────────────────────┘
│   (8400)    │
└──────┬───────┘
       │ Returns: AgentRecord + trust + policy
       │
       ▼  NexusRouteMetadata built
┌─────────────┐    POST /rpc/{agent}
│Nexus Gateway│◄── X-Gharra-Record header
│   (8100)    │    Authorization: Bearer JWT
└──────┬───────┘
       │ Route admission → lazy agent startup
       ▼
┌─────────────┐
│ Test Agent  │    (triage:8021, diagnosis:8022, ...)
│  (real)     │    from Nexus-A2A-protocol/demos/
└─────────────┘
```

## Test Suites

### Agent Resolution (`test_agent_resolution.py` — 13 tests)
- GHARRA health check
- Resolve each canonical agent (triage, referral, radiology, pathology)
- Nonexistent agent returns 404
- List agents, filter by jurisdiction
- Trust metadata structure (JWKS URI, mTLS, token binding)
- Policy tags present (residency, PHI, classification)
- Namespace zone derivation (IE→ie.health, GB→gb.health, etc.)
- Zones endpoint accessible
- Observability field completeness

### Agent Routing (`test_agent_routing.py` — 8 tests)
- Nexus gateway health check
- Invoke triage + diagnosis agents via JSON-RPC
- X-Gharra-Record header propagation
- Correlation ID propagation
- Observability record completeness
- Invalid agent alias returns 404
- Sequential multi-agent invocation

### SignalBox Workflow (`test_signalbox_workflow.py` — 11 tests)
- SignalBox + GHARRA health checks
- Agent resolution through SignalBox → GHARRA
- Capability discovery through SignalBox → GHARRA
- Agent registration in SignalBox identity FSM
- External systems listing (19 systems)
- Policy evaluation path (SignalBox → GHARRA `/v1/policy/{zone}`)
- Full workflow: GHARRA resolve → trust validation → Nexus invocation
- SignalBox-mediated workflow chain
- Observability fields and workflow summary structure

### Policy Enforcement (`test_policy_enforcement.py` — 18 tests)
- Region/residency restrictions (EU, US, DE)
- Prohibited regions (CN, RU for US radiology)
- PHI export constraints per agent
- Data classification (confidential, restricted)
- Purpose of use gates (treatment, research)
- Protocol requirements (nexus-a2a-jsonrpc, http-rest)
- mTLS and DPoP authentication requirements
- Certificate thumbprint pinning (sha256:...)
- ISO27001 attestation verification

### Scale Simulation (`test_scale_simulation.py` — 6 tests)
- Smoke: 10 patients, 5 concurrent
- Small: 100 patients, 20 concurrent
- Medium: 1,000 patients, 50 concurrent
- Latency validation (P95, P99)
- Throughput validation (rps)
- Report structure completeness

## Large-Scale Agent Simulation

The harness includes a load simulation module (`harness/scale_simulation.py`) that
mimics national-scale healthcare workloads flowing through the production path:

```
GHARRA resolve → Nexus JSON-RPC routing → Real test agents
```

### Scale Profiles

| Profile    | Patients | Hospitals | Insurers | Telemed | Concurrency |
|------------|----------|-----------|----------|---------|-------------|
| `smoke`    | 10       | 2         | 1        | 1       | 5           |
| `small`    | 100      | 10        | 5        | 3       | 20          |
| `medium`   | 1,000    | 50        | 10       | 10      | 50          |
| `large`    | 10,000   | 500       | 100      | 50      | 100         |
| `national` | 100,000  | 2,000     | 500      | 200     | 250         |

### Running Scale Tests

```bash
# Run all scale tests (smoke + small + medium)
pytest tests/test_scale_simulation.py -v

# Run a specific profile
pytest tests/test_scale_simulation.py::test_scale_medium -v

# Run large scale (requires more resources / longer timeout)
pytest tests/test_scale_simulation.py::test_scale_large -v --timeout=600
```

### Using the Simulator Directly

```python
import asyncio
from harness.scale_simulation import ScaleSimulator, ScaleProfile

async def main():
    sim = ScaleSimulator()
    report = await sim.run(ScaleProfile.MEDIUM)
    print(report.summary())

asyncio.run(main())
```

### Observed Performance (Docker, local machine)

| Profile | Patients | Success Rate | Throughput | GHARRA P99 | Nexus P99 |
|---------|----------|-------------|------------|------------|-----------|
| smoke   | 10       | 100%        | 23.7 rps   | 16 ms      | 94 ms     |
| small   | 100      | 100%        | 77.1 rps   | 47 ms      | 266 ms    |
| medium  | 1,000    | 100%        | 69.8 rps   | 110 ms     | 1,703 ms  |
| large   | 10,000   | 100%        | 88.7 rps   | 296 ms     | 1,891 ms  |
| national| 100,000  | 100%        | 40.4 rps   | 15,906 ms  | 8,031 ms  |

Each patient task follows the production path:
1. Generate clinical data (chief complaint, urgency, age, hospital assignment)
2. Resolve a random GHARRA-registered agent
3. Route a JSON-RPC task through the Nexus gateway to a real agent
4. Collect per-step latency metrics (P95, P99, min, max, avg)

### Metrics Collected

Every simulation run produces a `SimulationReport` with:

```json
{
  "profile": "medium",
  "config": {"patients": 1000, "hospitals": 50, "insurers": 10, "concurrency": 50},
  "total_tasks": 1000,
  "success": 951,
  "failure": 49,
  "error_rate": "4.90%",
  "elapsed_s": 10.47,
  "throughput_rps": 95.5,
  "steps": {
    "gharra_resolve": {
      "count": 1000, "success": 1000, "failure": 0,
      "avg_ms": 22.3, "p95_ms": 78.0, "p99_ms": 110.0,
      "error_rate": "0.00%"
    },
    "nexus_invoke": {
      "count": 1000, "success": 951, "failure": 49,
      "avg_ms": 188.4, "p95_ms": 672.0, "p99_ms": 1141.0,
      "error_rate": "4.90%"
    }
  }
}
```

### Reused Infrastructure

The scale simulation reuses existing infrastructure from all three repositories:

| Component | Source | What's reused |
|-----------|--------|---------------|
| Clinical data patterns | Nexus `tools/helixcare_scenarios.py` | Chief complaints, urgency levels, PatientScenario model |
| Concurrency profiles | Nexus `tools/generate_load_matrix.py` | 25–2M concurrent user targets, gate-based milestones |
| Rate limiter tiers | GHARRA `src/gharra/core/pricing.py` | Developer→Enterprise limits (60–50K req/min) |
| JWT minting | Nexus `shared/nexus_common/service_auth.py` | HS256 token generation with scope claims |
| Locust scenarios | GHARRA `tests/load/locustfile.py` | Discovery, registration, federation, rate-limit saturation |

## Observability

Every workflow step logs structured fields:

```json
{
  "agent_name": "Triage Agent",
  "agent_id": "gharra://ie/agents/triage-e2e",
  "resolved_zone": "ie.health",
  "trust_anchor": "https://triage.ie/.well-known/jwks.json",
  "selected_capability": ["nexus-a2a-jsonrpc", "fhir-r4"],
  "nexus_route": "http://nexus-gateway:8100/rpc/triage",
  "workflow_id": "WF-A1B2C3D4E5F6",
  "correlation_id": "COR-F6E5D4C3B2A1"
}
```

## Cross-Repository Bugs Found

The integration harness uncovered and fixed these cross-repo issues:

| # | Bug | Repository | Root Cause |
|---|-----|-----------|------------|
| 1 | f-string backslash (Python 3.11) | GHARRA | `indicator.strip('\"')` inside f-string |
| 2 | `Counter.inc(dict)` wrong arg type | GHARRA | Gateway passed dict as `amount` instead of `**kwargs` |
| 3 | Wrong metric attribute names | GHARRA | `http_request_duration` → `http_request_duration_seconds` |
| 4 | Metrics double-counting | GHARRA | Duplicate `.inc()` with different label sets |
| 5 | Missing RBAC policies | BulletTrain | `signalbox.gharra.resolve`/`.discover` not in POLICIES dict |
| 6 | Wrong auth disable env var | BulletTrain | `BULLETTRAIN_AUTH_DISABLED` doesn't exist; must use `AUTH_MODE=dev` |
| 7 | Wrong role name | BulletTrain | `globaladmin` not in `GLOBAL_ADMIN_ROLES`; must use `admin` |
| 8 | Pydantic model mismatch | BulletTrain→GHARRA | BulletTrain expects `{name, endpoint}`, GHARRA returns `{agent_id, endpoints[]}` |
| 9 | Discovery URL mismatch | BulletTrain | Client calls `/v1/discovery`, GHARRA exposes `/v1/discover` |
| 10 | Rate limiting blocks tests | GHARRA | Developer tier (60 req/min) too low; added `GHARRA_RATE_LIMIT_ENABLED` env var |

## Success Criteria

The harness demonstrates a full working chain:

```
BulletTrain → GHARRA → Nexus → Agent → Response
```

using:
- Real GHARRA registry records (from e2e test fixtures)
- Real Nexus test agents (from demos/ directory)
- Real SignalBox orchestration (from services/signalbox/)
- Real route admission validation (from shared/nexus_common/)
- Concurrent load simulation up to 1,000 patients at 95+ rps

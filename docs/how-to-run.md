# NEXUS-A2A Protocol – How to Run

## Prerequisites

| Tool | Version |
|------|---------|
| Docker & Docker Compose | v2+ |
| Python | 3.11+ |
| curl / httpx | any |

## 1. Environment Setup

```bash
# Clone the repo
git clone <repo-url> && cd nexus-a2a-protocol

# Copy the env template for the demo you want to run
cp demos/ed-triage/.env.example demos/ed-triage/.env
# (repeat for other demos)

# Generate a JWT token (needs NEXUS_JWT_SECRET in .env)
python tools/nexus_mint_jwt.py
# Paste the printed token into NEXUS_JWT_TOKEN in .env
```

> **Optional:** Set `OPENAI_API_KEY` for real LLM responses.  
> Without it every LLM call returns a deterministic `MOCK_RESPONSE`.

---

## 2. Running a Demo

Each demo lives under `demos/<name>/` with its own `docker-compose.yml`.

### ED Triage (ports 8021-8023)

```bash
cd demos/ed-triage
docker compose up --build -d

# Seed FHIR test data
bash tools/seed_fhir.sh

# Smoke test
bash tools/smoke_test.sh
```

| Agent | Port | Card |
|-------|------|------|
| triage-agent | 8021 | `http://localhost:8021/.well-known/agent-card.json` |
| diagnosis-agent | 8022 | `http://localhost:8022/.well-known/agent-card.json` |
| openhie-mediator | 8023 | `http://localhost:8023/.well-known/agent-card.json` |

### Telemed Scribe (ports 8031-8033)

```bash
cd demos/telemed-scribe
docker compose up --build -d
bash tools/smoke_test.sh
```

| Agent | Port | Card |
|-------|------|------|
| transcriber-agent | 8031 | `http://localhost:8031/.well-known/agent-card.json` |
| summariser-agent | 8032 | `http://localhost:8032/.well-known/agent-card.json` |
| ehr-writer-agent | 8033 | `http://localhost:8033/.well-known/agent-card.json` |

### Consent Verification (ports 8041-8044)

```bash
cd demos/consent-verification
docker compose up --build -d
bash tools/smoke_test.sh
```

| Agent | Port | Card |
|-------|------|------|
| insurer-agent | 8041 | `http://localhost:8041/.well-known/agent-card.json` |
| provider-agent | 8042 | `http://localhost:8042/.well-known/agent-card.json` |
| consent-analyser | 8043 | `http://localhost:8043/.well-known/agent-card.json` |
| hitl-ui | 8044 | `http://localhost:8044/.well-known/agent-card.json` |

### Public Health Surveillance (ports 8051-8053)

```bash
cd demos/public-health-surveillance
docker compose up --build -d
bash tools/smoke_test.sh
```

| Agent | Port | Card |
|-------|------|------|
| hospital-reporter | 8051 | `http://localhost:8051/.well-known/agent-card.json` |
| osint-agent | 8052 | `http://localhost:8052/.well-known/agent-card.json` |
| central-surveillance | 8053 | `http://localhost:8053/.well-known/agent-card.json` |

> The surveillance demo includes a **Mosquitto MQTT broker** on port 1883.  
> The central-surveillance agent tries MQTT first and falls back to HTTP.

---

## 3. Manual JSON-RPC Call

```bash
TOKEN=$(python tools/nexus_mint_jwt.py)

# ED Triage example
curl -X POST http://localhost:8021/rpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": "demo-1",
    "method": "tasks/sendSubscribe",
    "params": {
      "task": {
        "patient_ref": "Patient/123",
        "inputs": {
          "chief_complaint": "chest pain",
          "age": 55,
          "vitals": {"hr": 110, "bp": "160/95", "spo2": 94}
        }
      }
    }
  }'
```

## 4. SSE / WebSocket Streaming

```bash
# SSE
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8021/events/<task_id>

# WebSocket (with wscat)
wscat -c "ws://localhost:8021/ws/<task_id>?token=$TOKEN"
```

---

## 5. Running the Conformance Test Harness

```bash
# Start the demo(s) you want to test, then:
pip install pytest pytest-asyncio httpx

# Run all harness tests
NEXUS_JWT_SECRET=super-secret-test-key-change-me \
  pytest tests/nexus_harness/ -v --tb=short

# Run a single tier
pytest tests/nexus_harness/test_ed_triage.py -v

# The conformance report is written to docs/conformance-report.json
```

---

## 6. Stopping

```bash
cd demos/<name>
docker compose down -v
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  shared/nexus_common/                                           │
│  ┌───────┐ ┌─────┐ ┌───────────┐ ┌─────┐ ┌─────┐ ┌──────────┐│
│  │auth.py│ │ids.py│ │jsonrpc.py │ │sse.py│ │did.py│ │mqtt_cl...││
│  └───────┘ └─────┘ └───────────┘ └─────┘ └─────┘ └──────────┘│
│  ┌─────────────┐ ┌───────────────┐                              │
│  │http_client.py│ │openai_helper.py│                             │
│  └─────────────┘ └───────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
           │                    │                    │
    ┌──────▼──────┐   ┌────────▼───────┐   ┌───────▼────────┐
    │ ED Triage   │   │ Telemed Scribe │   │ Consent Verif. │ ...
    │ 8021-8023   │   │ 8031-8033      │   │ 8041-8044      │
    └─────────────┘   └────────────────┘   └────────────────┘
```

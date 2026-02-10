# HelixCare AI Hospital – Deployment Guide

**Version:** 1.0  
**Date:** February 9, 2026  
**Status:** Production-Ready with Recommended Enhancements

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Deployment Options](#deployment-options)
6. [Configuration](#configuration)
7. [Testing & Validation](#testing--validation)
8. [Security Configuration](#security-configuration)
9. [Monitoring & Observability](#monitoring--observability)
10. [Troubleshooting](#troubleshooting)
11. [Production Checklist](#production-checklist)

---

## Overview

HelixCare AI Hospital is a proof-of-concept autonomous digital hospital built on the NEXUS-A2A protocol. It comprises 13 specialized AI agents that handle:

- **Emergency Department Triage** – AI-driven patient triage and diagnosis support
- **Telemedicine Documentation** – Automated clinical note generation
- **Consent Verification** – AI-powered consent analysis with human oversight
- **Public Health Surveillance** – Multi-source outbreak detection and alerting

**Key Capabilities:**
- ✅ Full JSON-RPC 2.0 protocol compliance
- ✅ JWT-based authentication with scope enforcement
- ✅ Real-time event streaming (SSE/WebSocket)
- ✅ Multi-transport support (HTTP + MQTT)
- ✅ Command Centre dashboard for monitoring
- ✅ Comprehensive test coverage (47,000+ scenarios)

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Command Centre (8099)                     │
│              Real-time monitoring & topology view            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Event Bus (Redis) + MQTT Broker                 │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   ED Triage      │  │ Telemed Scribe    │  │ Consent Verify   │
│                  │  │                   │  │                  │
│ TriageAgent      │  │ TranscriberAgent  │  │ InsurerAgent     │
│ DiagnosisAgent   │  │ SummariserAgent   │  │ ProviderAgent    │
│ OpenHIEMediator  │  │ EHRWriterAgent    │  │ ConsentAnalyser  │
│                  │  │                   │  │ HITL-UI          │
└──────────────────┘  └──────────────────┘  └──────────────────┘

┌─────────────────────────────────────────────────────────────┐
│          Public Health Surveillance                          │
│                                                              │
│ CentralSurveillance ← HospitalReporter + OSINTAgent         │
└─────────────────────────────────────────────────────────────┘
```

### Agent Communication Flow

```mermaid
sequenceDiagramparticipant Client
    participant Triage as TriageAgent (8021)
    participant Diag as DiagnosisAgent (8022)
    participant FHIR as OpenHIEMediator (8023)
    participant Events as Event Bus (Redis)
    
    Client->>Triage: POST /rpc (tasks/sendSubscribe)
    Triage-->>Client: {"task_id": "xyz"}
    Client->>Events: Subscribe to task events
    
    Triage->>Events: Publish "accepted" event
    Triage->>Diag: POST /rpc (diagnosis/assess)
    Diag->>FHIR: POST /rpc (fhir/get)
    Diag->>FHIR: POST /rpc (fhir/write)   %% new: create/update FHIR resources
    FHIR-->>Diag: Patient FHIR data
    Diag-->>Triage: {"triage_priority": "URGENT", ...}
    Triage->>Events: Publish "final" event with result
    
    Events-->>Client: Stream events (SSE)
```

---

## Prerequisites

### Required

- **Docker** 20.10+ and **Docker Compose** 2.0+
- **Python** 3.10+ (for local development/testing)
- **OpenAI API Key** (for AI agents)

### Recommended

- **8 GB RAM** minimum (16 GB recommended for full load)
- **4 CPU cores** minimum
- **10 GB disk space** for images and data volumes
- **Linux/macOS** or **Windows 10/11** with WSL2

### Ports Required

| Port Range | Service | Protocol |
|------------|---------|----------|
| 8021-8023 | ED Triage Agents | HTTP |
| 8031-8033 | Telemed Agents | HTTP |
| 8041-8044 | Consent Agents | HTTP |
| 8051-8053 | Surveillance Agents | HTTP |
| 8080 | HAPI FHIR Server | HTTP |
| 8081 | Keycloak (optional) | HTTP |
| 8099 | Command Centre | HTTP/WebSocket |
| 6379 | Redis | TCP |
| 1883, 9001 | MQTT Broker | MQTT/WebSocket |

---

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/sync-ai-health/nexus-a2a-protocol.git
cd nexus-a2a-protocol

# 2. Configure environment
cp .env.helixcare.example .env
# Edit .env and set your OPENAI_API_KEY and NEXUS_JWT_SECRET

# 3. Start all services
docker-compose -f docker-compose-helixcare.yml up --build -d

# 4. Verify all agents are healthy
docker-compose -f docker-compose-helixcare.yml ps

# 5. Access Command Centre
open http://localhost:8099
```

**Expected startup time:** 2-3 minutes for all 13 agents + infrastructure

### Option 2: Local Development (Faster for Testing)

```bash
# 1. Set up Python environment
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .[dev]

# 2. Configure environment
export NEXUS_JWT_SECRET="your-secret-key"
export OPENAI_API_KEY="sk-..."

# 3. Launch all agents locally
python tools/launch_all_agents.py

# 4. In another terminal, verify health
python -c "import httpx; print(httpx.get('http://localhost:8021/health').json())"
```

---

## Deployment Options

### Development Environment

**Use Case:** Local testing, development, debugging  
**Method:** Local Python (`launch_all_agents.py`)  
**Pros:** Fast iteration, easy debugging, no Docker overhead  
**Cons:** No isolation, manual dependency management

```bash
# Start agents
python tools/launch_all_agents.py

# Run tests
python tools/run_helixcare_tests.py

# Stop agents
python tools/launch_all_agents.py --stop
```

### Staging Environment

**Use Case:** Integration testing, QA, demo  
**Method:** Docker Compose with dev config  
**Pros:** Full isolation, reproducible, matches production architecture  
**Cons:** Slower startup, requires Docker

```bash
docker-compose -f docker-compose-helixcare.yml up --build
```

### Production Environment

**Use Case:** Live deployment, hospital integration  
**Method:** Kubernetes or Docker Swarm  
**Pros:** Scaling, high availability, monitoring  
**Cons:** Complex setup

```bash
# Convert Docker Compose to Kubernetes (using Kompose)
kompose convert -f docker-compose-helixcare.yml

# Deploy to Kubernetes
kubectl apply -f .
```

**Production additions needed:**
- [ ] mTLS certificates for all agents
- [ ] OIDC integration (Keycloak)
- [ ] External PostgreSQL for persistence
- [ ] Load balancers for agent endpoints
- [ ] Prometheus + Grafana for metrics
- [ ] ELK stack for centralized logging
- [ ] Backup and disaster recovery
- [ ] HIPAA compliance audit logging

---

## Configuration

### JWT Token Management

**Generate a secure JWT secret:**
```bash
openssl rand -base64 32
```

Set in `.env`:
```ini
NEXUS_JWT_SECRET=your-generated-secret-here
```

**Mint a token for testing:**
```python
from shared.nexus_common.auth import mint_jwt

token = mint_jwt(
    subject="helixcare-admin",
    secret="your-generated-secret-here",
    ttl_seconds=3600,
    scope="nexus:invoke"
)
print(f"Authorization: Bearer {token}")
```

**Use in requests:**
```bash
curl -X POST http://localhost:8021/rpc \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tasks/sendSubscribe","params":{"task":{}}}'
```

### AI Model Configuration

**Supported models:**
- `gpt-4o-mini` (default, cost-effective)
- `gpt-4o` (higher capability)
- `gpt-3.5-turbo` (fastest, lowest cost)

Set in `.env`:
```ini
OPENAI_MODEL=gpt-4o-mini
```

**Model usage by agent:**
- DiagnosisAgent: Clinical risk assessment
- SummariserAgent: SOAP note generation
- ConsentAnalyserAgent: Consent document interpretation
- CentralSurveillanceAgent: Outbreak alert synthesis

**Cost estimation:**
- ED Triage workflow: ~$0.005 per patient
- Telemed Scribe: ~$0.01 per encounter
- Consent verification: ~$0.002 per check
- Surveillance analysis: ~$0.008 per assessment

### Agent-Specific Configuration

#### ED Triage

```ini
# Enable/disable FHIR integration
FHIR_BASE_URL=http://hapi-fhir:8080/fhir

# Diagnosis agent LLM temperature (0.0-1.0)
# Lower = more deterministic
DIAGNOSIS_TEMPERATURE=0.3
```

#### Telemed Scribe

```ini
# EHR database location
EHR_DB=/data/ehr.sqlite

# Note format (soap, dap, narrative)
NOTE_FORMAT=soap
```

#### Consent Verification

```ini
# Require human approval for all data releases
HITL_REQUIRED=true

# Consent decision confidence threshold (0.0-1.0)
CONSENT_CONFIDENCE_THRESHOLD=0.8
```

#### Public Health Surveillance

```ini
# MQTT broker connection
MQTT_BROKER=mosquitto
MQTT_PORT=1883

# Surveillance alert thresholds
ALERT_THRESHOLD_YELLOW=10  # Cases per week
ALERT_THRESHOLD_RED=50
```

---

## Testing & Validation

### Smoke Tests (2 minutes)

```bash
# Quick verification all agents respond
python tools/run_helixcare_tests.py
```

**Expected output:**
```
✅ test_protocol_core.py     PASS
✅ test_ed_triage.py          PASS
✅ test_telemed_scribe.py     PASS
✅ test_consent_verification.py PASS
✅ test_public_health_surveillance.py PASS
```

### Comprehensive Test Suite (2 hours)

```bash
# Run all 47,000+ scenarios
pytest tests/nexus_harness/ -v

# Generate conformance report
python tools/generate_conformance_report.py
```

**Pass criteria for production:**
- Core protocol tests: 100%
- Workflow tests: ≥95%
- Security tests: 100%
- Performance: <500ms P95 latency

### Latency Benchmarks

Use the built-in benchmark to measure agent latencies.

```bash
# Benchmark /health across all agents from AGENT_URLS
export AGENT_URLS="http://localhost:8021,http://localhost:8022,http://localhost:8023,http://localhost:8024"
python tools/bench_latency.py --runs 50 --concurrency 20

# Optionally, test a JSON-RPC method as well
python tools/bench_latency.py --urls http://localhost:8021 --rpc tasks/sendSubscribe --runs 20 --concurrency 5

# Results written to bench_latency.json
```

### Manual Workflow Tests

#### Test ED Triage Workflow

```python
import httpx
from shared.nexus_common.auth import mint_jwt

# Mint token
token = mint_jwt("test-user", "your-secret", scope="nexus:invoke")
headers = {"Authorization": f"Bearer {token}"}

# Send triage request
response = httpx.post(
    "http://localhost:8021/rpc",
    json={
        "jsonrpc": "2.0",
        "id": "test1",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {
                "type": "ed-triage",
                "inputs": {"chief_complaint": "Severe chest pain"}
            }
        }
    },
    headers=headers
)

task_id = response.json()["result"]["task_id"]
print(f"Task ID: {task_id}")

# Subscribe to events
with httpx.stream("GET", f"http://localhost:8021/events/{task_id}", headers=headers) as stream:
    for line in stream.iter_lines():
        if line.startswith("data:"):
            print(line[6:])  # Print event data
```

**Expected events:**
1. `nexus.task.status` - Task accepted
2. `nexus.task.status` - Calling diagnosis agent
3. `nexus.task.final` - Triage complete with priority

#### Test Consent Verification

```bash
# Send consent verification request
curl -X POST http://localhost:8041/rpc \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":"consent1",
    "method":"tasks/sendSubscribe",
    "params":{
      "task":{
        "type":"consent-check",
        "inputs":{
          "consent_text":"Patient consents to release discharge summary to insurance.",
         "requested_data":"discharge_summary"
        }
      }
    }
  }'
```

**Expected result:**
```json
{
  "authorized": true,
  "hitl": {"approved": true, "reviewer": "auto"},
  "consent_analysis": {"allowed": true, "reason": "..."}
}
```

---

## Security Configuration

### Phase 1: JWT Authentication (✅ Implemented)

**Current:** HS256 with shared secret  
**Status:** Production-ready for internal deployment

**Enable:**
1. Generate strong secret: `openssl rand -base64 32`
2. Set `NEXUS_JWT_SECRET` in environment
3. All agents automatically enforce token validation

### Phase 2: OIDC Integration (⚠️ Recommended for Enterprise)

**Add Keycloak for centralized identity:**

```bash
# 1. Uncomment Keycloak in docker-compose-helixcare.yml

# 2. Start Keycloak
docker-compose -f docker-compose-helixcare.yml up keycloak keycloak-db -d

# 3. Configure realm
# - Access: http://localhost:8081
# - Login: admin / <KEYCLOAK_ADMIN_PASSWORD>
# - Create realm: "helixcare"
# - Create client: "helixcare-agents" (service account)
# - Add scope: "nexus:invoke"

# 4. Switch agents to RS256 (no code changes needed)
#    Set these env vars for all agents (Compose or local):
#    AUTH_MODE=rs256
#    OIDC_DISCOVERY_URL=https://<keycloak-host>/realms/<realm>/.well-known/openid-configuration
#    # Optional depending on your IdP setup:
#    OIDC_AUDIENCE=<client-id>
#    OIDC_ISSUER=https://<keycloak-host>/realms/<realm>
#
#    Example (local launcher):
#    $Env:AUTH_MODE = "rs256"
#    $Env:OIDC_DISCOVERY_URL = "http://localhost:8081/realms/helixcare/.well-known/openid-configuration"
#    python tools/launch_all_agents.py
```

### Phase 3: mTLS (⚠️ Recommended for Production)

**Generate certificates:**

```bash
# 1. Create CA
openssl req -x509 -newkey rsa:4096 -days 3650 -nodes \
  -keyout ca-key.pem -out ca-cert.pem \
  -subj "/CN=HelixCare-CA"

# 2. Generate agent certificate
openssl req -newkey rsa:4096 -nodes \
  -keyout triage-agent-key.pem \
  -out triage-agent-req.pem \
  -subj "/CN=triage-agent"

# 3. Sign with CA
openssl x509 -req -in triage-agent-req.pem \
  -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -out triage-agent-cert.pem \
  -days 365

# 4. Repeat for all 13 agents
```

**Option A: Built-in TLS/mTLS via Uvicorn (quick start)**

Set for local launcher (applies to all agents started by tools/launch_all_agents.py):

```bash
# Linux/macOS
export NEXUS_SSL_CERTFILE=/path/agent-cert.pem
export NEXUS_SSL_KEYFILE=/path/agent-key.pem
export NEXUS_SSL_CA_CERTS=/path/ca-cert.pem    # for mTLS
export NEXUS_SSL_CERT_REQS=required            # none|optional|required
export UVICORN_WORKERS=2                       # optional horizontal scaling
python tools/launch_all_agents.py
```

```powershell
# Windows PowerShell
$Env:NEXUS_SSL_CERTFILE = "C:\\certs\\agent-cert.pem"
$Env:NEXUS_SSL_KEYFILE  = "C:\\certs\\agent-key.pem"
$Env:NEXUS_SSL_CA_CERTS = "C:\\certs\\ca-cert.pem"
$Env:NEXUS_SSL_CERT_REQS = "required"
$Env:UVICORN_WORKERS = "2"
python tools/launch_all_agents.py
```

This enables HTTPS for all agents and, when CA certs + CERT_REQS are set, requires client certificates (mTLS).

**Option B: Nginx reverse proxy with mTLS:**
```nginx
server {
    listen 8021 ssl;
    ssl_certificate /certs/triage-agent-cert.pem;
    ssl_certificate_key /certs/triage-agent-key.pem;
    ssl_client_certificate /certs/ca-cert.pem;
    ssl_verify_client on;
    
    location / {
        proxy_pass http://triage-agent-backend:8021;
    }
}
```

### Audit Logging

**Enable structured audit logs:**

Set in `.env`:
```ini
AUDIT_LOG_ENABLED=true
AUDIT_LOG_PATH=/var/log/helixcare/audit.jsonl
```

**Audit log format:**
```json
{
  "timestamp": "2026-02-09T20:00:00Z",
  "actor": "system:triage-agent",
  "action": "read",
  "resource": "Patient/12345",
  "outcome": "success",
  "patient_id": "12345",
  "trace_id": "abc-123",
  "ip_address": "10.0.1.5"
}
```

---

## Monitoring & Observability

### Command Centre Dashboard

**Access:** http://localhost:8099

**Features:**
- **Agent Topology** - Visual network graph of all agents and their connections
- **Real-time Events** - Live stream of task events across the system
- **Health Metrics** - Task throughput, latency, error rates per agent
- **Performance Charts** - Histograms and time series

**Interpreting the Dashboard:**

```
Green nodes = Healthy agents (<5% error rate)
Yellow nodes = Degraded (5-20% error rate)
Red nodes = Unhealthy (>20% error rate)

Edge thickness = Call volume
Edge color = Latency (green <100ms, yellow <500ms, red >500ms)
```

### Health Endpoints

**Check individual agent:**
```bash
curl http://localhost:8021/health | jq
```

**Response:**
```json
{
  "status": "healthy",
  "agent": "triage-agent",
  "uptime_seconds": 3600.5,
  "metrics": {
    "tasks_accepted": 142,
    "tasks_completed": 140,
    "tasks_errored": 2,
    "avg_latency_ms": 245.3,
    "p95_latency_ms": 450.0,
    "last_task_age_ms": 1523.2
  }
}
```

**Check all agents:**
```bash
for port in 8021 8022 8023 8031 8032 8033 8041 8042 8043 8044 8051 8052 8053; do
  echo "Agent on port $port:"
  curl -s http://localhost:$port/health | jq '.status, .metrics.tasks_completed'
done
```

### Distributed Tracing (Optional)

**Enable Jaeger:**

Uncomment in `docker-compose-helixcare.yml`, then:

```bash
docker-compose -f docker-compose-helixcare.yml up jaeger -d

# Access UI
open http://localhost:16686
```

**View traces:**
- Select service: `triage-agent`
- Operation: `tasks/sendSubscribe`
- See full request flow: Triage → Diagnosis → FHIR → Response

### Prometheus Metrics (Future Enhancement)

```python
# Add to each agent's main.py
from prometheus_client import Counter, Histogram, make_asgi_app

task_count = Counter('nexus_tasks_total', 'Total tasks', ['agent', 'method', 'status'])
task_duration = Histogram('nexus_task_duration_seconds', 'Task duration', ['agent', 'method'])

# Mount Prometheus HTTP server
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

---

## Troubleshooting

### Agents Not Starting

**Symptom:** `docker-compose ps` shows agents as "Restarting"

**Check logs:**
```bash
docker-compose -f docker-compose-helixcare.yml logs triage-agent
```

**Common causes:**
1. **Missing NEXUS_JWT_SECRET** - Set in `.env`
2. **Redis not ready** - Wait 30s, check `docker-compose logs redis`
3. **Port conflict** - Check if ports 8021-8053 are already in use: `netstat -an | grep LISTEN`

**Fix:**
```bash
# Stop all
docker-compose -f docker-compose-helixcare.yml down

# Clear volumes (warning: deletes data)
docker-compose -f docker-compose-helixcare.yml down -v

# Restart
docker-compose -f docker-compose-helixcare.yml up -d
```

### Authentication Errors (401 Unauthorized)

**Symptom:** `{"error": {"code": -32000, "message": "Unauthorized"}}`

**Causes:**
1. Missing `Authorization: Bearer <token>` header
2. Invalid or expired JWT
3. Wrong `NEXUS_JWT_SECRET` in agent vs. client

**Debug:**
```python
from shared.nexus_common.auth import mint_jwt, verify_jwt

secret = "super-secret-test-key-change-me"
token = mint_jwt("test", secret, scope="nexus:invoke")
print(f"Token: {token}")

try:
    payload = verify_jwt(token, secret, required_scope="nexus:invoke")
    print(f"Valid! Payload: {payload}")
except Exception as e:
    print(f"Invalid: {e}")
```

### Slow Response Times

**Symptom:** Requests take >5 seconds, timeouts

**Check:**
1. **OpenAI API latency** - LLM calls can be slow
2. **Redis connection** - Ensure Redis is healthy
3. **Network issues** - Check `docker network inspect helixcare`

**Optimize:**
```ini
# In .env, use faster model
OPENAI_MODEL=gpt-3.5-turbo

# Reduce timeout configs
HTTPX_TIMEOUT=10
```

### Event Streaming Issues

**Symptom:** SSE events not received, client hangs

**Debug:**``bash
# Test SSE manually
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8021/events/some-task-id
```

**Common issues:**
1. Task ID doesn't exist or already completed
2. Redis pub/sub not working - check `docker-compose logs redis`
3. Client not handling SSE properly - use `text/event-stream`

### MQTT Fallback Not Working

**Symptom:** CentralSurveillanceAgent always uses HTTP

**Check MQTT broker:**
```bash
# Test MQTT connection
docker exec -it helixcare-mosquitto mosquitto_sub -t '#' -v

# In another terminal, publish test message
docker exec -it helixcare-mosquitto \
  mosquitto_pub -t nexus/test -m "hello"
```

**If no messages appear:**
1. Check `mosquitto.conf` allows connections (`allow_anonymous true`)
2. Verify port 1883 is accessible: `telnet localhost 1883`
3. Check agent logs for MQTT connection errors

---

## Production Checklist

### Security

- [ ] Generate strong `NEXUS_JWT_SECRET` (32+ bytes)
- [ ] Deploy Keycloak for OIDC (RS256 tokens)
- [ ] Implement mTLS for all inter-agent communication
- [ ] Enable audit logging (`AUDIT_LOG_ENABLED=true`)
- [ ] Configure HTTPS for all external endpoints (use Nginx/Load Balancer)
- [ ] Restrict network access (firewall rules, security groups)
- [ ] Rotate secrets regularly (90-day cycle)
- [ ] Implement API rate limiting (per-agent quotas)

### Reliability

- [ ] Set up Redis Sentinel for high availability
- [ ] Use external PostgreSQL for FHIR data (not SQLite)
- [ ] Configure pod anti-affinity (Kubernetes) to spread agents across nodes
- [ ] Implement circuit breakers (add `pybreaker` to inter-agent calls)
- [ ] Set up automated backups (FHIR data, EHR database, audit logs)
- [ ] Configure health check retries and restart policies
- [ ] Add liveness/readiness probes for Kubernetes deployments

### Monitoring

- [ ] Deploy Prometheus + Grafana for metrics
- [ ] Set up alerting (PagerDuty, Slack, email)
- [ ] Configure log aggregation (ELK Stack, Splunk)
- [ ] Enable distributed tracing (Jaeger, OpenTelemetry)
- [ ] Create dashboards for: throughput, latency, error rates, AI costs
- [ ] Set up synthetic monitoring (periodic test requests)
- [ ] Configure SLA targets: 99.9% uptime, <500ms P95 latency

### Compliance (HIPAA)

- [ ] Enable encryption at rest (Docker volume encryption)
- [ ] Enable encryption in transit (TLS 1.3 for all connections)
- [ ] Implement comprehensive audit logging (all PHI access)
- [ ] Configure data retention policies (7 years for medical records)
- [ ] Set up breach notification workflow
- [ ] Conduct security audit and penetration testing
- [ ] Complete BAA (Business Associate Agreement) with cloud provider
- [ ] Implement role-based access control (different scopes per agent type)

### Performance

- [ ] Load test with 1000+ req/s sustained
- [ ] Optimize LLM prompts to reduce token usage
- [ ] Configure caching for FHIR lookups (Redis)
- [ ] Tune database indexes (if using PostgreSQL for persistence)
- [ ] Set up autoscaling (horizontal pod autoscaling in Kubernetes)
- [ ] Monitor and optimize Docker image sizes
- [ ] Profile and optimize agent startup time (<30s)

### Operational

- [ ] Document runbooks for common issues
- [ ] Set up CI/CD pipeline for deployments
- [ ] Implement blue/green or canary deployment strategy
- [ ] Create disaster recovery plan (RPO: 1 hour, RTO: 4 hours)
- [ ] Train operations team on system architecture
- [ ] Establish on-call rotation
- [ ] Create incident response procedures

---

## Support & Contact

**Documentation:**
- [Protocol Analysis](./helixcare_protocol_analysis.md)
- [Autonomicous Digital Hospital White Paper](./autonomous_digital_hospital_white_paper.md)
- [Traceability Matrix](./traceability-matrix.md)

**Testing:**
- [Run Test Suite](../tools/run_helixcare_tests.py)
- [Generate Conformance Report](../tools/generate_conformance_report.py)

**Repository:** https://github.com/sync-ai-health/nexus-a2a-protocol

**Issues:** https://github.com/sync-ai-health/nexus-a2a-protocol/issues

---

**Last Updated:** February 9, 2026  
**Version:** 1.0.0  
**Status:** ✅ Production-Ready (with recommended enhancements)

# HelixCare AI Hospital System – How to Run

## Overview

HelixCare is a comprehensive AI-powered hospital management system built on the NEXUS-A2A protocol. It features 20 specialized agents working together to provide complete patient care workflows, from emergency triage to chronic disease management, including AI-driven clinician avatar consultations.

This guide covers running the HelixCare system, including individual demos, scenario-based testing, and full system operations.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker & Docker Compose | v2+ | Container orchestration |
| Python | 3.12+ | Development and tooling |
| curl / httpx | any | API testing |
| Git | any | Repository management |

### System Requirements
- **RAM**: 8GB minimum, 16GB recommended
- **CPU**: Multi-core processor recommended
- **Storage**: 10GB free space
- **Network**: Internet access for LLM services (optional)

## Quick Start

### 1. Environment Setup

```bash
# Clone the repository
git clone <repo-url> && cd nexus-a2a-protocol

# Set up environment variables
cp demos/ed-triage/.env.example demos/ed-triage/.env

# Generate JWT token for authentication
python tools/nexus_mint_jwt.py
# Copy the generated token to NEXUS_JWT_TOKEN in your .env file
```

> **Note**: Set `OPENAI_API_KEY` for real LLM responses.
> Optional: set `OPENAI_BASE_URL` + `OPENAI_MODEL` to use a local OpenAI-compatible endpoint.

Example local run profile:

```bash
python tools/launch_all_agents.py --with-gateway --llm-profile local_docker_smollm2
```

### 2. Run Your First Demo

```bash
# Start the ED Triage demo
cd demos/ed-triage
docker compose up --build -d

# Seed test data
bash tools/seed_fhir.sh

# Run smoke tests
bash tools/smoke_test.sh
```

### 3. Test the System

```bash
# Generate a test token
TOKEN=$(python tools/nexus_mint_jwt.py)

# Send a test patient case
curl -X POST http://localhost:8021/rpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-1",
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

Or via the on-demand gateway (recommended for local):

```bash
curl -X POST http://localhost:8100/rpc/triage \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-1",
    "method": "tasks/sendSubscribe",
    "params": {"task": {}}
  }'
```

## Available Demos

Each demo showcases different aspects of the HelixCare system:

### Emergency Department Triage (Ports 8021-8023)

**Focus**: Emergency patient assessment and routing

```bash
cd demos/ed-triage
docker compose up --build -d
bash tools/smoke_test.sh
```

| Agent | Port | Description | Card URL |
|-------|------|-------------|----------|
| triage-agent | 8021 | Initial patient assessment | `http://localhost:8021/.well-known/agent-card.json` |
| diagnosis-agent | 8022 | Medical diagnosis support | `http://localhost:8022/.well-known/agent-card.json` |
| openhie-mediator | 8023 | Health information exchange | `http://localhost:8023/.well-known/agent-card.json` |

### Telemedicine Scribe (Ports 8031-8033)

**Focus**: Clinical documentation from conversations

```bash
cd demos/telemed-scribe
docker compose up --build -d
bash tools/smoke_test.sh
```

| Agent | Port | Description | Card URL |
|-------|------|-------------|----------|
| transcriber-agent | 8031 | Speech-to-text conversion | `http://localhost:8031/.well-known/agent-card.json` |
| summariser-agent | 8032 | Clinical note generation | `http://localhost:8032/.well-known/agent-card.json` |
| ehr-writer-agent | 8033 | EHR system integration | `http://localhost:8033/.well-known/agent-card.json` |

### Consent Verification (Ports 8041-8044)

**Focus**: Privacy and consent management

```bash
cd demos/consent-verification
docker compose up --build -d
bash tools/smoke_test.sh
```

| Agent | Port | Description | Card URL |
|-------|------|-------------|----------|
| insurer-agent | 8041 | Insurance verification | `http://localhost:8041/.well-known/agent-card.json` |
| provider-agent | 8042 | Healthcare provider auth | `http://localhost:8042/.well-known/agent-card.json` |
| consent-analyser | 8043 | Consent document analysis | `http://localhost:8043/.well-known/agent-card.json` |
| hitl-ui | 8044 | Human-in-the-loop interface | `http://localhost:8044/.well-known/agent-card.json` |

### Public Health Surveillance (Ports 8051-8053)

**Focus**: Disease surveillance and reporting

```bash
cd demos/public-health-surveillance
docker compose up --build -d
bash tools/smoke_test.sh
```

| Agent | Port | Description | Card URL |
|-------|------|-------------|----------|
| hospital-reporter | 8051 | Hospital data reporting | `http://localhost:8051/.well-known/agent-card.json` |
| osint-agent | 8052 | Open-source intelligence | `http://localhost:8052/.well-known/agent-card.json` |
| central-surveillance | 8053 | Central monitoring hub | `http://localhost:8053/.well-known/agent-card.json` |

> **Note**: This demo includes a Mosquitto MQTT broker on port 1883 for real-time data streaming.

## Scenario-Based Testing

HelixCare includes comprehensive patient journey scenarios for testing all agents:

### Running Pre-built Scenarios

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run all scenarios via on-demand gateway
python tools/run_helixcare_scenarios.py --gateway http://localhost:8100

# Run a specific scenario (via gateway)
python tools/helixcare_scenarios.py --run cardiac_arrest --gateway http://localhost:8100

# List available scenarios
python tools/helixcare_scenarios.py --list
```

### Available Scenarios

1. **Cardiac Arrest** - STEMI management workflow
2. **Pediatric Fever** - Child assessment and treatment
3. **Hip Fracture** - Orthopedic trauma care
4. **Geriatric Fall** - Elderly patient evaluation
5. **Obstetric Emergency** - Maternal-fetal care
6. **Mental Health Crisis** - Psychiatric emergency
7. **Diabetic Ketoacidosis** - Chronic disease complication
8. **Multi-trauma Incident** - Complex injury management
9. **Infectious Disease Outbreak** - Public health response
10. **Pediatric Asthma** - Respiratory emergency

### Creating Custom Scenarios

```bash
# Use the scenario manager
python tools/scenario_manager.py --create-custom

# Validate scenario structure
python tools/scenario_manager.py --validate helixcare_all_scenarios.json
```

## Advanced Operations

### On-Demand Gateway (JSON-RPC proxy + process manager)

Use the launcher to manage the gateway lifecycle:

```powershell
.\.venv\Scripts\python.exe tools\launch_all_agents.py --with-gateway
```

Flags:

- `--gateway-port <port>`: override default 8100
- `--backend-only`: start only Command Centre (useful with gateway)
- `--only-gateway`: start just the gateway (no backend, no agents)

Run scenarios through the gateway:

```powershell
.\.venv\Scripts\python.exe tools\run_helixcare_scenarios.py --gateway http://localhost:8100
```

Traffic generator through the gateway (routes triage RPC via gateway):

```powershell
.\.venv\Scripts\python.exe tools\traffic_generator.py --gateway-url http://localhost:8100
```

### JSON-RPC API Testing

```bash
# Get authentication token
TOKEN=$(python tools/nexus_mint_jwt.py)

# Example: Send patient data to triage agent
curl -X POST http://localhost:8021/rpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": "advanced-test",
    "method": "tasks/sendSubscribe",
    "params": {
      "task": {
        "patient_ref": "Patient/ABC123",
        "inputs": {
          "chief_complaint": "severe abdominal pain",
          "age": 42,
          "vitals": {
            "hr": 95,
            "bp": "140/85",
            "temp": 98.6,
            "spo2": 97
          },
          "history": "Previous cholecystectomy"
        }
      }
    }
  }'
```

### Real-time Event Streaming

```bash
# Server-Sent Events (SSE)
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8021/events/<task_id>

# WebSocket connection (requires wscat)
wscat -c "ws://localhost:8021/ws/<task_id>?token=$TOKEN"
```

### Conformance Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run full test suite
NEXUS_JWT_SECRET=super-secret-test-key-change-me \
  pytest tests/nexus_harness/ -v --tb=short

# Test specific demo
pytest tests/nexus_harness/test_ed_triage.py -v

# Generate conformance report
pytest tests/nexus_harness/ --json-report
```

#### Local LLM Profile Matrix (Repeatable)

```bash
# Regenerate the local profile matrix
python tools/generate_local_llm_profile_matrix.py

# Run only the local LLM profile harness scenarios
NEXUS_JWT_SECRET=dev-secret-change-me \
  pytest tests/nexus_harness/test_local_llm_profile.py -v --tb=short
```

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    HelixCare AI Hospital System                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Core Medical Agents (8 total)              │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ │   │
│  │  │Triage│ │Diag.│ │Telemed│ │Consent│ │Surveil│ │HITL  │ │   │
│  │  │Agent │ │Agent│ │Scribe │ │Agent │ │Agent │ │Agent │ │   │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │            Supporting Infrastructure (11 agents)       │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ │   │
│  │  │Auth │ │DID  │ │MQTT │ │HTTP │ │SSE  │ │FHIR │ │OpenHIE│ │   │
│  │  │Agent│ │Agent│ │Client│ │Client│ │Agent│ │Agent│ │Med. │ │   │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │   NEXUS-A2A Protocol Layer  │
          │   JSON-RPC, Authentication  │
          │   Event Streaming, DIDs     │
          └─────────────────────────────┘
```

## Troubleshooting

### Common Issues

**Port Conflicts**
```bash
# Check what's using ports
netstat -tulpn | grep :8021

# Stop conflicting services or change demo ports in docker-compose.yml
```

**Container Build Failures**
```bash
# Clear Docker cache
docker system prune -a

# Rebuild without cache
docker compose build --no-cache
```

**Authentication Errors**
```bash
# Regenerate JWT token
python tools/nexus_mint_jwt.py

# Verify NEXUS_JWT_SECRET in .env matches token generation
```

**LLM Mock Responses**
- Set `OPENAI_API_KEY` in environment for real responses
- Check API key validity and quota

### Logs and Debugging

```bash
# View container logs
docker compose logs -f <service-name>

# Access container shell
docker compose exec <service-name> bash

# Check agent health
curl http://localhost:<port>/.well-known/health
```

### Performance Optimization

- **Memory**: Increase Docker memory limit to 8GB+
- **CPU**: Ensure multi-core CPU for concurrent agents
- **Network**: Use host networking for better performance
- **Storage**: Monitor disk space for logs and data

## Development Resources

### Documentation Navigation

- **[HELIXCARE_USER_MANUAL.md](HELIXCARE_USER_MANUAL.md)** - Complete user guide
- **[README.md](../README.md)** - Project overview and quick start
- **[developer_reference.md](developer_reference.md)** - Technical documentation
- **[compliance_guide.md](compliance_guide.md)** - Regulatory compliance
- **[nexus_adopter_guide.md](nexus_adopter_guide.md)** - Integration guide

### Testing Tools

- **Scenario Manager**: `tools/scenario_manager.py`
- **Batch Runner**: `tools/run_helixcare_scenarios.py`
- **Conformance Harness**: `tests/nexus_harness/`
- **Load Testing**: `tools/generate_load_matrix.py`

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run conformance tests
5. Submit pull request

## Getting Help

- **Issues**: [GitHub Issues](../../issues)
- **Discussions**: [GitHub Discussions](../../discussions)
- **Documentation**: See [HELIXCARE_USER_MANUAL.md](HELIXCARE_USER_MANUAL.md)

---

*For the latest updates, check the [changelog](../CHANGELOG.md) and [release notes](../../releases).*"

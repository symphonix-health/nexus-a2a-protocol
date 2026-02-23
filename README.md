<p align="center">
  <img src="docs/assets/nexus-logo.svg" alt="Nexus A2A Protocol" width="420">
</p>

<h1 align="center">HelixCare AI Hospital</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/docker-ready-blue.svg" alt="Docker">
  <img src="https://img.shields.io/badge/agents-20-teal.svg" alt="20 Agents">
  <img src="https://img.shields.io/badge/scenarios-25-teal.svg" alt="25 Scenarios">
</p>

<p align="center">
  <strong>A comprehensive AI-powered hospital management system built on the NEXUS Agent-to-Agent (A2A) protocol.</strong><br>
  20 specialized AI agents — including a clinician avatar for structured clinical interviews — real-time monitoring, and 25 end-to-end patient journey scenarios.
</p>

---

## Table of Contents

- [Quick Start](#-quick-start-5-minutes)
- [System Overview](#-system-overview)
- [Patient Journey Scenarios](#-patient-journey-scenarios)
- [Clinician Avatar](#-clinician-avatar)
- [Command Centre](#-command-centre)
- [Docker Deployment](#-docker-deployment)
- [Agent Management](#-agent-management)
- [Testing & Validation](#-testing--validation)
- [Troubleshooting](#-troubleshooting)
- [Architecture](#-architecture)
- [Development](#-development)
- [Documentation (Deep Dives)](#-documentation-deep-dives)
- [Compliance & Governance](#-compliance--governance)
- [License](#-license) · [Support](#-support) · [Research](#-research--papers)

---

## 🚀 Quick Start (5 minutes)

```bash
# 1. Clone and setup
git clone https://github.com/sync-ai-health/nexus-a2a-protocol.git
cd nexus-a2a-protocol
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 2. Start everything (agents + on-demand gateway)
python tools/launch_all_agents.py --with-gateway

# 3. Run a patient scenario
python tools/helixcare_scenarios.py --run chest_pain_cardiac --gateway http://localhost:8100

# 4. Monitor in real-time
python tools/monitor_command_centre.py
```

| Endpoint | URL |
|----------|-----|
| **Command Centre** (dashboard) | <http://localhost:8099> |
| **On-Demand Gateway** (JSON-RPC proxy) | <http://localhost:8100/rpc/{agent}> |
| **Clinician Avatar** (3D interface) | <http://localhost:8039/avatar> |

> **Tip**: The gateway starts agents lazily on first request — no need to launch every agent up-front.

---

## 🏥 System Overview

### 20 AI Agents Working Together

#### Core Medical Agents (9)

| Agent | Port | Role |
|-------|------|------|
| **Triage Agent** | 8021 | Initial patient assessment and urgency classification |
| **Diagnosis Agent** | 8022 | Medical diagnosis and differential generation |
| **Imaging Agent** | 8023 | Radiology coordination and image ordering |
| **Pharmacy Agent** | 8024 | Medication recommendations and interaction checks |
| **Bed Manager** | 8025 | Admission coordination and bed allocation |
| **Discharge Agent** | 8026 | Discharge planning and transition-of-care |
| **Follow-up Agent** | 8027 | Post-discharge scheduling and care continuity |
| **Care Coordinator** | 8028 | End-to-end journey orchestration |
| **Clinician Avatar** | 8039 | Structured clinical interview (Calgary-Cambridge / SOCRATES / ABCDE) |

#### Infrastructure Agents (11)
- **Command Centre** — Real-time monitoring dashboard (port 8099)
- **Security & Authentication** — JWT-based access control
- **Protocol Services** — Discovery, surveillance, compliance, and gateway routing

### Key Features
- 🤖 **AI-Powered** — Specialized medical AI for each clinical domain
- 🔄 **Autonomous** — Agents communicate via JSON-RPC 2.0 without human intervention
- 🩺 **Clinician Avatar** — Interactive 3D clinical interview with established frameworks
- 📊 **Real-time Monitoring** — Live dashboard with topology, timeline, and flow board
- 🛡️ **Secure** — JWT authentication with role-based access and audit logging
- ✅ **Fully Tested** — 7,000+ scenarios across 7 test harnesses, 100% compliance
- 📈 **Scalable** — Microservices architecture with on-demand process management

---

## 🎯 Patient Journey Scenarios

HelixCare includes **25 patient journey scenarios** organised into 10 canonical and 15 additional variants. Every scenario carries a full `medical_history` block (past medical history, medications, allergies, social/family history, review of systems, vital signs) that is threaded through each agent interaction as clinical context.

### Canonical Scenarios (10)

| Scenario | Description |
|----------|-------------|
| `primary_care_outpatient_in_person` | In-person primary care visit with assessment, treatment, and checkout |
| `specialty_outpatient_clinic` | Specialty clinic workflow with referral triage and diagnostics |
| `telehealth_video_consult` | Video telehealth consultation with documentation chain |
| `telehealth_audio_only_followup` | Audio-only chronic condition follow-up |
| `home_visit_house_call` | Home-based visit for mobility-impaired patients |
| `chronic_care_management_monthly` | Monthly chronic care management coordination |
| `emergency_department_treat_and_release` | ED treat-and-release for moderate presentation |
| `emergency_department_to_inpatient_admission` | ED to inpatient admission for complex cases |
| `inpatient_admission_and_daily_rounds` | Inpatient admission with daily clinical rounds |
| `inpatient_discharge_transition` | Discharge planning with transition-of-care coordination |

### Additional Scenarios (15)

| Scenario | Description |
|----------|-------------|
| `chest_pain_cardiac` | Adult cardiac chest pain with ACS workup |
| `pediatric_fever_sepsis` | Child with sepsis and isolation |
| `orthopedic_fracture` | Extremity fracture with imaging and follow-up |
| `geriatric_confusion` | Elderly delirium with CT workup |
| `obstetric_emergency` | Pregnancy bleeding at 28 weeks |
| `mental_health_crisis` | Acute psychiatric crisis with safety planning |
| `chronic_diabetes_complication` | Diabetic foot ulcer with multidisciplinary care |
| `trauma_motor_vehicle_accident` | Polytrauma from high-speed MVC |
| `infectious_disease_outbreak` | Respiratory outbreak with isolation |
| `pediatric_asthma_exacerbation` | Severe paediatric asthma stabilisation |
| `regional_hie_referral_exchange` | Cross-network referral via OpenHIE mediation |
| `telemed_scribe_documentation_chain` | Telemedicine with transcriber → summariser → EHR writer |
| `consent_and_payer_authorization` | Prior-auth with consent verification and HITL adjudication |
| `notifiable_outbreak_public_health_loop` | Public health escalation with OSINT corroboration |
| `clinician_avatar_consultation` | Clinician avatar structured interview with diagnosis, imaging, and follow-up |

### Running Scenarios

```bash
# List all available scenarios
python tools/helixcare_scenarios.py --list

# Run a single scenario (via gateway — starts dependencies automatically)
python tools/helixcare_scenarios.py --run chest_pain_cardiac --gateway http://localhost:8100

# Run all scenarios
python tools/run_helixcare_scenarios.py --gateway http://localhost:8100

# Monitor progress in a second terminal
python tools/monitor_command_centre.py
```

### Scenario Data Structure

Each scenario is a `PatientScenario` dataclass containing:
- **Patient Profile** — Demographics, chief complaint, urgency level
- **Medical History** — Past conditions, medications, allergies, social/family history, review of systems, vital signs
- **Journey Steps** — Sequential agent interactions (triage → diagnosis → imaging → pharmacy → discharge/follow-up)
- **Expected Duration** — Estimated seconds for the complete journey

<details>
<summary><strong>Example medical_history block (JSON)</strong></summary>

```json
{
  "past_medical_history": ["Hypertension", "Type 2 diabetes"],
  "medications": ["Metformin 1000 mg BID", "Lisinopril 10 mg daily"],
  "allergies": ["Penicillin (hives)"],
  "social_history": { "tobacco": "never", "alcohol": "occasional" },
  "family_history": ["Mother with hypertension"],
  "review_of_systems": { "constitutional": "Fatigue over 6 weeks" },
  "vital_signs": { "blood_pressure": "152/92", "heart_rate": 82, "oxygen_saturation": 98 }
}
```

</details>

---

## 🩺 Clinician Avatar

The **Clinician Avatar Agent** (port 8039) provides AI-driven structured clinical interviews backed by established medical consultation frameworks, rendered in a 3D browser-based interface.

### Clinical Frameworks

| Framework | Selected When | Structure |
|-----------|---------------|-----------|
| **Calgary-Cambridge** | Default for general consultations | Initiating → Gathering information → Physical examination → Explanation & planning → Closing |
| **SOCRATES** | Pain-related chief complaints (chest pain, abdominal pain, etc.) | Site → Onset → Character → Radiation → Associations → Time course → Exacerbating/relieving → Severity |
| **ABCDE** | Critical/emergency urgency | Airway → Breathing → Circulation → Disability → Exposure |

The framework is **automatically selected** based on the patient's chief complaint and urgency level.

### 3D Avatar Interface

Access the web-based avatar at: **<http://localhost:8039/avatar>**

- **Three.js 3D head** with real-time lip-sync driven by viseme timelines
- **Chat panel** for text-based patient–clinician dialogue
- **TTS API** (`POST /api/tts`) generating audio with viseme synchronisation
- **Session lifecycle** — start, converse, end — managed via JSON-RPC

### Avatar JSON-RPC API

All methods are available at `POST /rpc` (or via the gateway at `/rpc/clinician_avatar`):

| Method | Description |
|--------|-------------|
| `avatar/start_session` | Start a structured interview; returns session ID, selected framework, and opening greeting |
| `avatar/patient_message` | Send a patient message; returns clinician response and updated consultation phase |
| `avatar/get_status` | Get current session state including framework progress and collected findings |
| `avatar/end_session` | End the consultation and retrieve the session summary |

### Example: Running the Avatar Scenario

```bash
# Via the on-demand gateway (recommended — starts dependencies automatically)
python tools/helixcare_scenarios.py --gateway http://localhost:8100 --retry-mode fast --run clinician_avatar_consultation
```

The `clinician_avatar_consultation` scenario walks through:
1. **Triage** — establishes urgency for exertional chest tightness
2. **Avatar start_session** — Calgary-Cambridge interview begins
3. **Patient messages** (×2) — patient describes onset, radiation, and associated symptoms
4. **Diagnosis** — differential based on gathered findings
5. **Imaging** — ECG + stress echocardiogram
6. **Pharmacy** — aspirin + nitroglycerin
7. **Follow-up** — cardiology review in 7 days

---

## 📡 Command Centre

The Command Centre provides real-time visibility into the entire HelixCare system.

### Accessing the Dashboard

```bash
# Start Command Centre (auto-started by launch_all_agents.py)
python shared/command-centre/app/main.py
# Open: http://localhost:8099
```

### Key Features

| Feature | Description |
|---------|-------------|
| **Agent Topology** | Visual map of all 20 agents with health status and connections |
| **Patient Journey Tracking** | Live workflow progression with agent interaction timelines |
| **Flow Board** | Kanban-style view of active scenarios with at-risk/stale detection |
| **System Metrics** | Performance monitoring, error tracking, and bottleneck identification |
| **Alert Management** | Critical event notifications with 30 s staleness threshold |

### API Endpoints

```bash
GET  http://localhost:8099/api/agents            # All agent statuses
GET  http://localhost:8099/api/scenarios/active   # Active scenarios
GET  http://localhost:8099/api/metrics            # System metrics
```

### Real-time Streaming

```javascript
// WebSocket for live updates
const ws = new WebSocket('ws://localhost:8099/ws');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Agent update:', data);
};
```

---

## 🐳 Docker Deployment

```bash
# Start all services
docker-compose -f docker-compose-helixcare.yml up -d

# Check status
docker-compose -f docker-compose-helixcare.yml ps

# View logs
docker-compose -f docker-compose-helixcare.yml logs -f command-centre

# Stop
docker-compose -f docker-compose-helixcare.yml down
```

---

## ⚙️ Agent Management

### Starting Agents

```bash
# All agents + gateway (recommended)
python tools/launch_all_agents.py --with-gateway

# All agents without gateway
python tools/launch_all_agents.py

# Individual agent
python demos/helixcare/triage-agent/main.py
```

### Health Checks

```bash
# Individual agent
curl http://localhost:8021/health

# All agents via gateway
curl http://localhost:8100/health
```

### Environment Variables

```bash
# Required
NEXUS_JWT_SECRET=your-secret-key       # JWT signing secret

# Optional
LOG_LEVEL=INFO                          # Logging level
AGENT_PORT=8021                         # Override agent port
COMMAND_CENTRE_URL=http://localhost:8099 # Command Centre endpoint
```

### Agent Configuration

Each agent accepts a `config.json` in its directory:

```json
{
  "port": 8021,
  "log_level": "INFO",
  "command_centre_url": "http://localhost:8099",
  "jwt_secret": "dev-secret-change-me"
}
```

---

## 🧪 Testing & Validation

### Overview

- **7 Test Harnesses** — Complete functional coverage
- **7,000+ Scenarios** — All medical workflows tested
- **100% Compliance** — All requirements validated
- **Performance Benchmarks** — Latency and throughput metrics

### Running Tests

```bash
# Full validation suite
python tools/run_hc_validation.py

# Detailed pytest output
python -m pytest tests/nexus_harness/test_helixcare_*.py -v

# Individual harness
python -m pytest tests/nexus_harness/test_helixcare_ed_intake.py -v
python -m pytest tests/nexus_harness/test_helixcare_diagnosis_imaging.py -v
python -m pytest tests/nexus_harness/test_helixcare_protocol_security.py -v

# Clinician avatar tests
python -m pytest tests/test_clinician_avatar.py -v

# All unit tests
python -m pytest tests/ -v
```

### Reports & Compliance

```bash
# Compliance suite
python tools/run_compliance_suite.py

# Conformance report
python tools/generate_conformance_report.py

# Traceability matrix
python tools/generate_traceability_matrix.py
```

---

## 🔍 Troubleshooting

### Common Issues

| Problem | Diagnosis | Solution |
|---------|-----------|----------|
| **Agents won't start** | Port already in use | `netstat -an \| findstr :8021` — kill conflicting process |
| **Authentication errors** | JWT secret mismatch | Verify `NEXUS_JWT_SECRET` env var matches across agents |
| **Agent not found (404)** | Agent not running | Check health: `curl http://localhost:{port}/health` |
| **Slow responses** | Resource contention | `python tools/system_monitor.py` — check CPU/memory |
| **Gateway timeout** | Agent startup delay | Retry with `--retry-mode fast` or increase timeout |

### VS Code Ruff `EPIPE` / "Server process exited with code 1"

If VS Code shows Ruff language-server crashes like `write EPIPE` or `Stopping server timed out`:

Open workspace settings (`.vscode/settings.json`), set `"ruff.importStrategy": "fromEnvironment"`, then reload the VS Code window and restart the Ruff server.

Why this helps: in this repo, Ruff runs correctly from `.venv`, and using the same binary in the editor avoids bundled-runtime mismatch crashes.

### Error Codes

| Code | Description | Solution |
|------|-------------|----------|
| 401 | Authentication failed | Check JWT token and secret |
| 403 | Authorisation failed | Verify user permissions / scopes |
| 404 | Agent not found | Check agent startup and port |
| 500 | Internal server error | Check agent logs in `logs/` directory |
| 503 | Service unavailable | Restart agent or check dependencies |

### Diagnostics

```bash
# Check Python environment
python --version
pip list | findstr fastapi

# Test token generation
python -c "from shared.nexus_common.auth import mint_jwt; print(mint_jwt('test'))"

# Run system diagnostics
python tools/diagnose_system.py
```

---

## 📊 Architecture

```
┌──────────────────┐     ┌──────────────────┐
│   Command        │     │   Patient        │
│   Centre         │◄───►│   Scenarios      │
│   (Port 8099)    │     │   (25 journeys)  │
└──────────────────┘     └──────────────────┘
         │                        │
    ┌────┴────────────────────────┴────┐
    │         On-Demand Gateway        │
    │     (Port 8100 – /rpc/{agent})   │
    └────┬────────────────────────┬────┘
         │                        │
    ┌────┴────┐            ┌──────┴──────┐
    │  NEXUS  │            │  Clinician  │
    │  A2A    │            │  Avatar     │
    │ Protocol│            │ (Port 8039) │
    └────┬────┘            └─────────────┘
         │
    ┌────┴────┐
    │ 9 Core  │
    │ Medical │
    │ Agents  │
    └─────────┘
```

**Communication**: JSON-RPC 2.0 over HTTP with JWT authentication (HS256)
**Real-time**: WebSocket and Server-Sent Events (SSE)
**Gateway**: On-demand process manager — starts agents lazily on first request
**Security**: Bearer tokens with `nexus:invoke` scope, configurable secret

---

## 🔧 Development

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Git

### Setup

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v             # Run tests
python -m ruff check src tests         # Lint
python -m ruff format src tests        # Format
```

### Project Structure

```
nexus-a2a-protocol/
├── src/                        # Core NEXUS protocol implementation
├── demos/helixcare/            # 20 AI agent implementations
│   ├── triage-agent/           #   Port 8021
│   ├── diagnosis-agent/        #   Port 8022
│   ├── imaging-agent/          #   Port 8023
│   ├── pharmacy-agent/         #   Port 8024
│   ├── bed-manager-agent/      #   Port 8025
│   ├── discharge-agent/        #   Port 8026
│   ├── followup-scheduler/     #   Port 8027
│   ├── care-coordinator-agent/ #   Port 8028
│   ├── clinician-avatar-agent/ #   Port 8039  (NEW)
│   └── ...                     #   Infrastructure agents
├── shared/                     # Common utilities
│   ├── clinician_avatar/       #   Avatar engine, frameworks, prompts
│   ├── command-centre/         #   Dashboard (Three.js topology, flow board)
│   ├── on_demand_gateway/      #   Lazy process manager + JSON-RPC proxy
│   └── nexus_common/           #   Auth, agent base classes
├── tests/                      # Comprehensive test suite (7,000+ scenarios)
├── tools/                      # Scenario runner, launcher, validation
├── docs/                       # Deep-dive documentation
├── config/                     # Agent registry (agents.json)
└── HELIXCARE_USER_MANUAL.md    # Detailed user manual
```

### Adding a New Agent

```python
from shared.nexus_common.agent import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="my-agent",
            port=8030,
            capabilities=["custom.task"]
        )

    async def handle_task(self, task_data):
        return {"result": "processed"}
```

### Adding a New Scenario

```python
from tools.helixcare_scenarios import PatientScenario

my_scenario = PatientScenario(
    name="my_custom_case",
    description="Custom medical scenario",
    patient_profile={
        "age": 45, "gender": "female",
        "chief_complaint": "Persistent headache",
        "urgency": "medium"
    },
    medical_history={
        "past_medical_history": ["Migraine", "Hypertension"],
        "medications": ["Sumatriptan 50 mg PRN"],
        "allergies": ["No known drug allergies"],
        "social_history": {"tobacco": "never", "alcohol": "occasional"},
        "family_history": ["Mother with migraine"],
        "review_of_systems": {"neurologic": "Throbbing left-sided headache"},
        "vital_signs": {"blood_pressure": "128/80", "heart_rate": 76},
    },
    journey_steps=[...],
    expected_duration=30,
)
```

> **Note**: All scenarios must include a `medical_history` block. This data is threaded through each agent interaction as clinical context.

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-agent`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`python -m pytest tests/ -v`)
6. Submit a pull request

---

## 📚 Documentation (Deep Dives)

| Document | Description |
|----------|-------------|
| [User Manual](HELIXCARE_USER_MANUAL.md) | Detailed walkthrough of every system component |
| [How to Run](docs/how-to-run.md) | Extended setup including all demo groups and LLM profiles |
| [On-Demand Gateway](docs/on-demand-gateway.md) | Gateway architecture — lazy process management and dependency graphs |
| [Deployment Guide](docs/helixcare_deployment_guide.md) | Production deployment — Kubernetes, security hardening, production checklist |
| [Architecture](docs/architecture.md) | High-level and detailed architecture diagrams |
| [Developer Reference](docs/developer_reference.md) | Protocol patterns, agent mesh architecture, avatar integration |
| [Compliance Guide](docs/compliance_guide.md) | EU AI Act, HIPAA, GDPR, shared responsibility model |
| [Command Centre](docs/command-centre-summary.md) | Dashboard implementation — heatmaps, metrics, WebSocket protocol |
| [MCP Server](docs/mcp_server.md) | MCP Server facade for VS Code Copilot / Claude Desktop |
| [Adopter Guide](docs/nexus_adopter_guide.md) | National digital health adoption guide |
| [Traceability Matrix](docs/traceability-matrix.md) | Requirements → test → code mapping |

---

## 🛡️ Compliance & Governance

HelixCare maintains compliance with:

| Standard | Scope |
|----------|-------|
| **HIPAA** | Health data protection and privacy |
| **HITRUST** | Security framework and controls |
| **GDPR** | International data privacy |
| **FDA Guidelines** | Medical device and AI regulations |

**Security features**: JWT authentication, role-based access, audit logging, encryption in transit.

```bash
# Compliance validation
python tools/validate_compliance.py

# Generate audit reports
python tools/generate_audit_report.py --period 30d

# Security assessment
python tools/security_scan.py
```

See [Compliance Guide](docs/compliance_guide.md) and [Strategic Governance Brief](docs/strategic_governance_brief.md) for full details.

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/sync-ai-health/nexus-a2a-protocol/issues)
- **Discussions**: Community Q&A and collaboration
- **Documentation**: [User Manual](HELIXCARE_USER_MANUAL.md) · [Developer Reference](docs/developer_reference.md)

## 🔬 Research & Papers

- [Autonomous Digital Hospital White Paper](docs/autonomous_digital_hospital_white_paper.md)
- [NEXUS A2A Protocol Research](docs/research.md)
- [Strategic Governance Brief](docs/strategic_governance_brief.md)
- [Hyperscale Implementation Backlog](docs/hyperscale_implementation_backlog.md)

---

<p align="center">
  <strong>HelixCare</strong> — Revolutionising healthcare through autonomous AI agent collaboration.<br>
  <em>Built with the NEXUS Agent-to-Agent protocol for secure, scalable healthcare automation.</em>
</p>

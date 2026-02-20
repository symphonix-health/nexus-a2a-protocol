# HelixCare AI Hospital User Manual

## Welcome to HelixCare

HelixCare is a comprehensive AI-powered hospital management system built on the NEXUS-A2A protocol. This manual will guide you through understanding, deploying, and using the HelixCare system.

---

## Table of Contents

### [1. Quick Start Guide](#1-quick-start-guide)
### [2. System Overview](#2-system-overview)
### [3. Installation & Setup](#3-installation--setup)
### [4. Agent Management](#4-agent-management)
### [5. Patient Journey Scenarios](#5-patient-journey-scenarios)
### [6. Command Centre Operations](#6-command-centre-operations)
### [7. Testing & Validation](#7-testing--validation)
### [8. Troubleshooting](#8-troubleshooting)
### [9. Developer Resources](#9-developer-resources)
### [10. Compliance & Governance](#10-compliance--governance)

---

## 1. Quick Start Guide

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- Git
- 8GB+ RAM recommended

### Fastest Way to Get Started

```bash
# 1. Clone the repository
git clone https://github.com/sync-ai-health/nexus-a2a-protocol.git
cd nexus-a2a-protocol

# 2. Set up environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start all agents
python tools/launch_all_agents.py

# 5. Run a patient scenario
python tools/helixcare_scenarios.py --run chest_pain_cardiac

# 6. Monitor in Command Centre
python tools/monitor_command_centre.py
```

**Expected Result**: You'll see a complete patient journey from triage to discharge, with real-time monitoring in the Command Centre.

[← Back to Table of Contents](#table-of-contents)

---

## 2. System Overview

### Architecture

HelixCare consists of **20 specialized AI agents** working together:

#### Core Medical Agents (9)
- **Triage Agent** (Port 8021) - Initial patient assessment
- **Diagnosis Agent** (Port 8022) - Medical diagnosis and differential diagnosis
- **Imaging Agent** (Port 8024) - Radiology order coordination
- **Pharmacy Agent** (Port 8025) - Medication recommendations
- **Bed Manager Agent** (Port 8026) - Admission coordination
- **Discharge Agent** (Port 8027) - Discharge planning
- **Follow-up Agent** (Port 8028) - Post-discharge care scheduling
- **Care Coordinator Agent** (Port 8029) - End-to-end journey orchestration
- **Clinician Avatar Agent** (Port 8039) - AI-driven structured clinical interview with 3D avatar

#### Supporting Infrastructure (11)
- Command Centre (Port 8099) - Real-time monitoring dashboard
- Authentication & Security agents
- Protocol discovery and surveillance agents

### Communication Protocol
- **NEXUS-A2A**: JSON-RPC 2.0 over HTTP with JWT authentication
- **Real-time Updates**: WebSocket and Server-Sent Events (SSE)
- **Multi-transport**: MQTT support for IoT integration

### Key Features
- 🤖 **AI-Powered**: Each agent uses specialized AI for medical decision support
- 🔄 **Autonomous**: Agents communicate and coordinate without human intervention
- 📊 **Real-time Monitoring**: Command Centre provides live system visibility
- 🛡️ **Secure**: JWT-based authentication with role-based access control
- 📈 **Scalable**: Microservices architecture supports horizontal scaling
- 🧑‍⚕️ **Clinician Avatar**: 3D avatar-driven structured clinical interviews (Calgary-Cambridge, SOCRATES, ABCDE)
- ✅ **Tested**: Comprehensive test suite with 7,000+ scenarios

[← Back to Table of Contents](#table-of-contents)

---

## 3. Installation & Setup

### Option 1: Docker Deployment (Recommended)

```bash
# Start all services
docker-compose -f docker-compose-helixcare.yml up -d

# Check status
docker-compose -f docker-compose-helixcare.yml ps

# View logs
docker-compose -f docker-compose-helixcare.yml logs -f command-centre
```

### Option 2: Local Development Setup

```bash
# 1. Environment Setup
python -m venv .venv
.venv\Scripts\activate  # Windows

# 2. Install Dependencies
pip install -r requirements.txt

# 3. Set Environment Variables
$env:NEXUS_JWT_SECRET = "dev-secret-change-me"

# 4. Start Individual Agents
python tools/launch_all_agents.py

# Or start specific agents
python demos/helixcare/triage-agent/main.py &
python demos/helixcare/diagnosis-agent/main.py &
# ... etc
```

### Option 3: Production Deployment

See [Deployment Guide](docs/how-to-run.md) for production setup instructions.

### Verification

```bash
# Check agent health
curl http://localhost:8021/health
curl http://localhost:8099/health

# Run basic connectivity test
python tools/test_connection.py
```

[← Back to Table of Contents](#table-of-contents)

---

## 4. Agent Management

### Starting Agents

#### All at Once
```bash
python tools/launch_all_agents.py
```

#### Individual Agents
```bash
# Core medical agents
python demos/helixcare/triage-agent/main.py
python demos/helixcare/diagnosis-agent/main.py
python demos/helixcare/imaging-agent/main.py
python demos/helixcare/pharmacy-agent/main.py
python demos/helixcare/bed-manager-agent/main.py
python demos/helixcare/discharge-agent/main.py
python demos/helixcare/followup-scheduler/main.py
python demos/helixcare/care-coordinator-agent/main.py

# Infrastructure
python shared/command-centre/app/main.py
```

#### Docker Compose
```bash
docker-compose -f docker-compose-helixcare.yml up -d
```

### Monitoring Agents

#### Command Centre Dashboard
```bash
python tools/monitor_command_centre.py
```
Access at: http://localhost:8099

#### Health Checks
```bash
# Individual agent health
curl http://localhost:8021/health

# All agents status
python tools/check_agent_health.py
```

#### Logs
```bash
# Docker logs
docker-compose -f docker-compose-helixcare.yml logs -f

# Individual agent logs
tail -f logs/triage-agent.log
```

### Configuration

#### Environment Variables
```bash
# Required
NEXUS_JWT_SECRET=your-secret-key

# Optional
LOG_LEVEL=INFO
AGENT_PORT=8021
COMMAND_CENTRE_URL=http://localhost:8099
```

#### Agent Configuration
Each agent has a `config.json` file in its directory:
```json
{
  "port": 8021,
  "log_level": "INFO",
  "command_centre_url": "http://localhost:8099",
  "jwt_secret": "dev-secret-change-me"
}
```

[← Back to Table of Contents](#table-of-contents)

---

## 5. Patient Journey Scenarios

### Available Scenarios

HelixCare includes **25 patient journey scenarios** organised into 10 canonical and 15 additional variants. Every scenario carries a full `medical_history` block with past medical history, medications, allergies, social/family history, review of systems, and vital signs.

#### Canonical Scenarios (10)

| Scenario | Description |
|---|---|
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

#### Additional Scenarios (15)

| Scenario | Description |
|---|---|
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
| `clinician_avatar_consultation` | **NEW** — Clinician avatar structured interview (Calgary-Cambridge) with diagnosis, imaging, and follow-up |

### Running Scenarios

#### Single Scenario
```bash
# List available scenarios
python tools/helixcare_scenarios.py --list

# Run a canonical scenario
python tools/helixcare_scenarios.py --run primary_care_outpatient_in_person

# Run an additional scenario (including the avatar scenario)
python tools/helixcare_scenarios.py --run clinician_avatar_consultation
```

#### Multiple Scenarios
```bash
# Run all scenarios (canonical + additional)
python tools/run_helixcare_scenarios.py

# Run with Command Centre monitoring
python tools/monitor_command_centre.py &
python tools/run_helixcare_scenarios.py
```

### Scenario Structure

Each scenario is a `PatientScenario` dataclass with:
- **Patient Profile**: Demographics, chief complaint, and urgency level
- **Medical History**: Past medical history, current medications, allergies, social history, family history, review of systems, and vital signs
- **Journey Steps**: Sequential agent interactions (triage → diagnosis → imaging → pharmacy → discharge/follow-up)
- **Expected Duration**: Estimated seconds for the complete journey

Example `medical_history` block:
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

### Monitoring Scenarios

```bash
# Real-time monitoring
python tools/monitor_command_centre.py

# Scenario progress tracking
python tools/scenario_tracker.py --scenario chest_pain_cardiac
```

[← Back to Table of Contents](#table-of-contents)

---

## 5a. Clinician Avatar

The **Clinician Avatar Agent** (port 8039) provides AI-driven structured clinical interviews backed by established medical consultation frameworks.

### Clinical Frameworks

| Framework | Selected When | Structure |
|---|---|---|
| **Calgary-Cambridge** | Default for general consultations | Initiating → Gathering information → Physical examination → Explanation & planning → Closing |
| **SOCRATES** | Pain-related chief complaints (chest pain, abdominal pain, etc.) | Site → Onset → Character → Radiation → Associations → Time course → Exacerbating/relieving → Severity |
| **ABCDE** | Critical/emergency urgency | Airway → Breathing → Circulation → Disability → Exposure |

The framework is automatically selected based on the patient's chief complaint and urgency level.

### 3D Avatar Interface

Access the web-based avatar at: **http://localhost:8039/avatar**

Features:
- **Three.js 3D head** with real-time lip-sync driven by viseme timelines
- **Chat panel** for text-based patient–clinician dialogue
- **TTS API** (`POST /api/tts`) generating audio with viseme synchronisation
- **Session lifecycle** — start, converse, end — via JSON-RPC

### Avatar API (JSON-RPC)

| Method | Description |
|---|---|
| `avatar/start_session` | Start a structured interview; returns session ID, selected framework, and opening greeting |
| `avatar/patient_message` | Send a patient message; returns clinician response and updated consultation phase |
| `avatar/get_status` | Get current session state including framework progress and findings |
| `avatar/end_session` | End the consultation and retrieve the session summary |

### Example: Running the Avatar Scenario

```bash
# Via the on-demand gateway (starts dependencies automatically)
python tools/helixcare_scenarios.py --gateway http://localhost:8100 --retry-mode fast --run clinician_avatar_consultation

# Or start the avatar agent directly first
python -m uvicorn demos.helixcare.clinician-avatar-agent.app.main:app --host 127.0.0.1 --port 8039
```

The `clinician_avatar_consultation` scenario walks through:
1. **Triage** — establishes urgency for exertional chest tightness
2. **Avatar start_session** — Calgary-Cambridge interview begins
3. **Patient messages** (×2) — patient describes onset, radiation, and associated symptoms
4. **Diagnosis** — differential based on gathered findings
5. **Imaging** — ECG + stress echocardiogram
6. **Pharmacy** — aspirin + nitroglycerin
7. **Follow-up** — cardiology review in 7 days

[← Back to Table of Contents](#table-of-contents)

---

## 6. Command Centre Operations

### Dashboard Overview

The Command Centre provides real-time visibility into:
- **Agent Status**: Health and activity of all 20 agents
- **Patient Journeys**: Live tracking of active scenarios
- **System Metrics**: Performance and error monitoring
- **Alert Management**: Critical event notifications

### Accessing the Dashboard

```bash
# Start Command Centre
python shared/command-centre/app/main.py

# Access dashboard
# http://localhost:8099
```

### Key Features

#### Agent Monitoring
- Real-time health status
- Activity logs and metrics
- Error tracking and alerts

#### Patient Journey Tracking
- Visual workflow progression
- Agent interaction timelines
- Bottleneck identification

#### System Administration
- Agent restart capabilities
- Configuration management
- Performance analytics

### API Endpoints

```bash
# Get all agent statuses
GET http://localhost:8099/api/agents

# Get active scenarios
GET http://localhost:8099/api/scenarios/active

# Get system metrics
GET http://localhost:8099/api/metrics
```

### WebSocket Integration

```javascript
// Real-time updates
const ws = new WebSocket('ws://localhost:8099/ws');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Agent update:', data);
};
```

[← Back to Table of Contents](#table-of-contents)

---

## 7. Testing & Validation

### Test Suite Overview

HelixCare includes comprehensive testing:
- **7 Test Harnesses**: Covering all functional requirements
- **7,000+ Scenarios**: Complete coverage of medical workflows
- **100% Compliance**: All requirements validated

### Running Tests

#### Full Test Suite
```bash
# Run all HelixCare tests
python tools/run_hc_validation.py

# With detailed output
python -m pytest tests/nexus_harness/test_helixcare_*.py -v
```

#### Individual Test Categories
```bash
# ED Intake tests
python -m pytest tests/nexus_harness/test_helixcare_ed_intake.py -v

# Diagnosis & Imaging
python -m pytest tests/nexus_harness/test_helixcare_diagnosis_imaging.py -v

# Protocol Security
python -m pytest tests/nexus_harness/test_helixcare_protocol_security.py -v
```

#### Performance Testing
```bash
# Load testing
python tools/burst_test.py --agents 19 --duration 300

# Latency benchmarking
python tools/bench_latency.py
```

### Validation Reports

```bash
# Generate compliance report
python tools/generate_conformance_report.py

# View traceability matrix
python tools/generate_traceability_matrix.py
```

### Continuous Integration

```bash
# Run tests in CI environment
python tools/run_compliance_suite.py --ci

# Generate coverage reports
python -m pytest --cov=src --cov-report=html
```

[← Back to Table of Contents](#table-of-contents)

---

## 8. Troubleshooting

### Common Issues

#### Agents Won't Start
```bash
# Check port availability
netstat -an | findstr :8021

# Check Python environment
python --version
pip list | grep fastapi

# Check logs
tail -f logs/agent-startup.log
```

#### Authentication Errors
```bash
# Verify JWT secret
echo $NEXUS_JWT_SECRET

# Test token generation
python -c "from shared.nexus_common.auth import mint_jwt; print(mint_jwt('test'))"
```

#### Network Connectivity
```bash
# Test agent communication
curl -H "Authorization: Bearer $(python tools/generate_token.py)" \
     http://localhost:8021/rpc -X POST \
     -d '{"jsonrpc":"2.0","id":"test","method":"system.health","params":{}}'

# Check Docker networking
docker network ls
docker network inspect helixcare-network
```

#### Performance Issues
```bash
# Monitor resource usage
python tools/system_monitor.py

# Check agent metrics
curl http://localhost:8099/api/metrics

# Profile slow operations
python -m cProfile tools/helixcare_scenarios.py --run chest_pain_cardiac
```

### Error Codes

| Code | Description | Solution |
|------|-------------|----------|
| 401 | Authentication failed | Check JWT token and secret |
| 403 | Authorization failed | Verify user permissions |
| 404 | Agent not found | Check agent startup and ports |
| 500 | Internal server error | Check agent logs |
| 503 | Service unavailable | Restart agent or check dependencies |

### Getting Help

1. **Check Logs**: All agents write to `logs/` directory
2. **Run Diagnostics**: `python tools/diagnose_system.py`
3. **Community Support**: GitHub Issues
4. **Documentation**: See [Developer Reference](docs/developer_reference.md)

[← Back to Table of Contents](#table-of-contents)

---

## 9. Developer Resources

### Architecture Documentation

- **[Developer Reference](docs/developer_reference.md)**: Complete API documentation
- **[How to Run](docs/how-to-run.md)**: Detailed setup instructions
- **[NEXUS Protocol](docs/nexus_adopter_guide.md)**: Protocol specifications

### Code Organization

```
nexus-a2a-protocol/
├── src/                    # Core protocol implementation
├── demos/helixcare/        # Agent implementations
├── shared/                 # Common utilities
├── tests/                  # Test suites
├── tools/                  # Development tools
└── docs/                   # Documentation
```

### Contributing

```bash
# Development setup
git checkout -b feature/new-agent
python -m venv .venv
pip install -r requirements-dev.txt

# Run tests before committing
python -m pytest tests/ -x

# Code formatting
black src/ demos/ tools/
isort src/ demos/ tools/
```

### API Development

#### Creating New Agents
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
        # Implement your logic
        return {"result": "processed"}
```

#### Adding Scenarios
```python
from tools.helixcare_scenarios import PatientScenario

my_scenario = PatientScenario(
    name="my_custom_case",
    description="Custom medical scenario",
    patient_profile={"age": 45, "gender": "female",
                     "chief_complaint": "Persistent headache",
                     "urgency": "medium"},
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

> **Note**: All scenarios must include a `medical_history` block. This data is threaded
> through the journey as clinical context for each agent interaction.

[← Back to Table of Contents](#table-of-contents)

---

## 10. Compliance & Governance

### Regulatory Compliance

HelixCare maintains compliance with:
- **HIPAA**: Health data protection
- **HITRUST**: Security framework
- **GDPR**: Data privacy (international)
- **FDA Guidelines**: Medical device regulations

### Security Features

- **JWT Authentication**: Bearer token validation
- **Role-Based Access**: Granular permissions
- **Audit Logging**: Complete activity tracking
- **Encryption**: Data in transit and at rest

### Governance Documents

- **[Compliance Guide](docs/compliance_guide.md)**: Security and compliance requirements
- **[Strategic Governance](docs/strategic_governance_brief.md)**: Governance framework
- **[Traceability Matrix](docs/traceability-matrix.md)**: Requirements mapping

### Audit & Reporting

```bash
# Generate audit reports
python tools/generate_audit_report.py --period 30d

# Compliance validation
python tools/validate_compliance.py

# Security assessment
python tools/security_scan.py
```

### Data Privacy

- **Patient Data**: De-identified in test scenarios
- **PHI Protection**: Encryption and access controls
- **Retention Policies**: Configurable data lifecycle
- **Consent Management**: Patient permission tracking

---

## Additional Resources

### White Papers & Research
- [Autonomous Digital Hospital](docs/autonomous_digital_hospital_white_paper.md)
- [Research Overview](docs/research.md)

### Community & Support
- **GitHub Repository**: https://github.com/sync-ai-health/nexus-a2a-protocol
- **Issues**: Bug reports and feature requests
- **Discussions**: Community Q&A and collaboration

### Training & Certification
- **Scenario Library**: 25 comprehensive patient journeys (10 canonical + 15 additional)
- **Clinician Avatar**: Interactive clinical interview with Calgary-Cambridge, SOCRATES, and ABCDE frameworks
- **Test Suite**: 7,000+ validation scenarios
- **Performance Benchmarks**: Latency and throughput metrics

---

*This manual is continuously updated. Last updated: February 20, 2026*

For the latest version, visit: [HelixCare Documentation](docs/)

[← Back to Table of Contents](#table-of-contents)

<div align="center">
  <img src="docs/assets/nexus-logo.svg" alt="Nexus A2A Protocol" width="420"/>
  <h3>The open protocol for healthcare agent-to-agent communication</h3>
  <p>Secure clinical delegation chains. 25 agents. 7,000+ test scenarios. Apache 2.0.</p>
</div>

<div align="center">

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![FHIR R4](https://img.shields.io/badge/FHIR-R4_Compatible-green.svg)](https://hl7.org/fhir/R4/)
[![Tests](https://img.shields.io/badge/tests-7%2C000%2B_scenarios-brightgreen.svg)](#testing)
[![Agents](https://img.shields.io/badge/agents-25_clinical-teal.svg)](#25-clinical-agents)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](#quick-start)

</div>

<div align="center">
  <a href="#quick-start">Quick Start</a> · <a href="#25-clinical-agents">25 Agents</a> · <a href="#architecture">Architecture</a> · <a href="#protocol">Protocol Spec</a> · <a href="https://symphonix-health.github.io">Documentation</a>
</div>

---

## What is Nexus A2A?

Nexus A2A is the communication protocol that lets healthcare AI agents delegate tasks to each other securely. When a triage agent needs imaging, or a discharge agent needs pharmacy clearance, Nexus handles the trusted handshake — with 13 security checks on every call. Built on JSON-RPC 2.0 with JWT authentication, the protocol defines the full task lifecycle from request through checkpoint to completion or escalation. The reference implementation (HelixCare) demonstrates a complete AI-powered hospital with 25 clinical agents across 5 workflow domains.

---

## Quick Start

```bash
git clone https://github.com/symphonix-health/nexus-a2a-protocol.git
cd nexus-a2a-protocol
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Launch all 25 agents + Command Centre
NEXUS_JWT_SECRET=dev-secret-change-me python tools/launch_all_agents.py --with-gateway

# Run a patient scenario
python tools/helixcare_scenarios.py --run chest_pain_cardiac --gateway http://localhost:8100
```

| Endpoint | URL |
|----------|-----|
| Command Centre | [localhost:8099](http://localhost:8099) |
| On-Demand Gateway | [localhost:8100/rpc/{agent}](http://localhost:8100) |
| Clinician Avatar | [localhost:8039/avatar](http://localhost:8039/avatar) |

---

## Architecture

```
Patient --> Clinician Avatar --> Triage Agent --> Diagnosis Agent
                                                   |-> Imaging Agent
                                                   |-> Pharmacy Agent
                                                   '-> Care Coordinator
                                                         |-> Bed Manager
                                                         |-> Discharge Agent
                                                         |    '-> Follow-up Scheduler
                                                         '-> Primary Care Agent
```

All communication flows through the **On-Demand Gateway** (port 8100), which starts agents lazily on first request. The **Command Centre** (port 8099) provides real-time topology, patient journey tracking, and a flow board with stale-detection alerts.

**Transport**: JSON-RPC 2.0 over HTTP | **Auth**: JWT HS256 | **Streaming**: SSE + WebSocket

---

## 25 Clinical Agents

### ED Triage (3 agents)

| Agent | Port | Role |
|-------|------|------|
| Triage Agent | 8021 | Initial assessment and urgency classification |
| Diagnosis Agent | 8022 | Differential diagnosis generation |
| OpenHIE Mediator | 8023 | Cross-network referral exchange |

### HelixCare Hospital (12 agents)

| Agent | Port | Role |
|-------|------|------|
| Imaging Agent | 8024 | Radiology coordination and image ordering |
| Pharmacy Agent | 8025 | Medication recommendations and interaction checks |
| Bed Manager | 8026 | Admission coordination and bed allocation |
| Discharge Agent | 8027 | Discharge planning and transition of care |
| Follow-up Scheduler | 8028 | Post-discharge scheduling and care continuity |
| Care Coordinator | 8029 | End-to-end journey orchestration |
| Primary Care Agent | 8034 | General practice consultations |
| Specialty Care Agent | 8035 | Specialist referral management |
| Telehealth Agent | 8036 | Video and audio-only consultations |
| Home Visit Agent | 8037 | Home-based care for mobility-impaired patients |
| CCM Agent | 8038 | Chronic care management coordination |
| Clinician Avatar | 8039 | Structured clinical interview (3D interface) |

### Telemed Scribe (3 agents)

| Agent | Port | Role |
|-------|------|------|
| Transcriber Agent | 8031 | Real-time clinical transcription |
| Summariser Agent | 8032 | Clinical note summarisation |
| EHR Writer Agent | 8033 | Electronic health record integration |

### Consent Verification (4 agents)

| Agent | Port | Role |
|-------|------|------|
| Insurer Agent | 8041 | Prior authorisation and claims |
| Provider Agent | 8042 | Clinical provider verification |
| Consent Analyser | 8043 | Patient consent validation |
| HITL UI | 8044 | Human-in-the-loop adjudication |

### Public Health Surveillance (3 agents)

| Agent | Port | Role |
|-------|------|------|
| Hospital Reporter | 8051 | Notifiable disease reporting |
| OSINT Agent | 8052 | Open-source intelligence corroboration |
| Central Surveillance | 8053 | National surveillance aggregation |

---

## Clinician Avatar

The Clinician Avatar (port 8039) provides AI-driven structured clinical interviews rendered in a 3D browser-based interface.

- **Clinical frameworks** — Calgary-Cambridge (general), SOCRATES (pain), ABCDE (emergency) — auto-selected by chief complaint and urgency
- **Real-time TTS with lip sync** — OpenAI streaming PCM with viseme-driven Three.js animation; browser SpeechSynthesis fallback
- **68 personas across 3 countries** — UK, USA, and Kenya clinician profiles from `config/personas.json`
- **Barge-in support** — patients can interrupt mid-response for natural conversation flow

---

## 13-Point Route Admission

Every agent-to-agent call passes through the GHARRA (Global Healthcare Agent Registry & Routing Authority) route admission gate. All 13 checks must pass before a transport connection opens:

| # | Check | Purpose |
|---|-------|---------|
| 1 | Record status is active | Reject decommissioned agents |
| 2 | Agent name is valid | Enforce `.health` namespace |
| 3 | Namespace delegation is valid | Verify zone chain integrity |
| 4 | Trust anchors match | Configured trust anchor validation |
| 5 | JWKS URI is well-formed | Key discovery endpoint check |
| 6 | Thumbprint policy is consistent | Certificate binding rules |
| 7 | Certificate-bound token rules | mTLS token binding |
| 8 | Policy tags allow operation | Operation-level authorisation |
| 9 | Jurisdiction / data-residency | Geographic compliance |
| 10 | Federated trust anchors validated | Cross-domain federation |
| 11 | Protocol is nexus-a2a | Version compatibility |
| 12 | Feature flags supported | Capability negotiation |
| 13 | Transport endpoint is non-empty | Reachability verification |

---

## Protocol

Nexus A2A uses **JSON-RPC 2.0 over HTTP** with JWT HS256 authentication.

**Task lifecycle:**

```
request --> accept --> checkpoint --> complete
                  \                \-> escalate
                   \-> reject
```

- **Request**: Caller sends a task with patient context and required capability
- **Accept**: Target agent acknowledges and begins processing
- **Checkpoint**: Intermediate progress updates streamed via SSE
- **Complete/Escalate**: Final result or escalation to a higher-capability agent

**Streaming**: Server-Sent Events for unidirectional progress; WebSocket for bidirectional real-time communication (Command Centre, Avatar TTS).

---

## Identity and Trust

- **68 personas** across UK, USA, and Kenya — each with job profile, qualifications, and care setting
- **6 IAM groups**: `nexus-clinical-high`, `nexus-clinical-medium`, `nexus-operations`, `nexus-governance`, `nexus-connector`, `nexus-intelligence`
- **DID support** — decentralised identifier verification for agent-to-agent trust (`DID_VERIFY` env flag)
- **GHARRA integration** — Global Healthcare Agent Registry & Routing Authority provides the trust backbone for cross-domain agent discovery and delegation

---

## Testing

- **7,000+ scenarios** across 7 harness suites with 100% pass rate
- **Matrix-driven**: each harness reads from a JSON scenario matrix in `HelixCare/`
- **Live and mock modes**: full agent integration tests or isolated mock transport

| Harness | Coverage |
|---------|----------|
| ED Intake and Triage | Emergency department workflow |
| Diagnosis and Imaging | Differential diagnosis with radiology |
| Admission and Treatment | Bed allocation and care plans |
| Discharge | Transition-of-care coordination |
| Avatar Streaming | TTS, visemes, auth, and edge cases |
| Persona and IAM | Identity resolution and access control |
| Protocol Security | Authentication, authorisation, and audit |

```bash
# Full validation suite
python tools/run_hc_validation.py

# Individual harness
python -m pytest tests/nexus_harness/test_helixcare_ed_intake.py -v
```

---

## Powered By

Nexus A2A supports multi-model AI through configurable LLM profiles:

| Provider | Model | Role |
|----------|-------|------|
| Bevan LLM | Local inference | Patient-data-safe on-premise processing |
| Anthropic | Claude Sonnet 4.6 | Third-party clinical reasoning |
| OpenAI | GPT-5.4 | Third-party clinical reasoning |
| DeepSeek | v3 | Third-party clinical reasoning |

LLM selection is per-agent via `config/agents.json` profiles. Local models keep patient data on-premise; cloud models are used only where data governance permits.

---

## Documentation

Full documentation is available at **[symphonix-health.github.io](https://symphonix-health.github.io)**.

Key references:

| Document | Description |
|----------|-------------|
| [User Manual](HELIXCARE_USER_MANUAL.md) | Complete walkthrough of every component |
| [Architecture](docs/architecture.md) | System diagrams and data flow |
| [Developer Reference](docs/developer_reference.md) | Protocol patterns and agent mesh |
| [Deployment Guide](docs/helixcare_deployment_guide.md) | Kubernetes, security hardening, production checklist |
| [Compliance Guide](docs/compliance_guide.md) | EU AI Act, HIPAA, GDPR, shared responsibility |
| [IAM Architecture](docs/iam_identity_architecture.md) | Agent identity, personas, and access control |
| [Adopter Guide](docs/nexus_adopter_guide.md) | National digital health adoption guide |

---

## Contributing

We welcome contributions from the healthcare and AI communities.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-agent`)
3. Add tests for new functionality
4. Ensure all tests pass (`python -m pytest tests/ -v`)
5. Submit a pull request

See the full [Contributing Guide](CONTRIBUTING.md) for coding standards, agent registration, and scenario authoring.

---

## License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.

---

## About Symphonix Health

Symphonix Health builds open infrastructure for autonomous healthcare systems. The Nexus A2A Protocol is our foundational layer for secure agent-to-agent communication in clinical environments, designed to be adopted by national digital health programmes, hospital networks, and health-tech innovators worldwide. Learn more at [symphonix-health.github.io](https://symphonix-health.github.io).

---

<div align="center">
  <strong>Nexus A2A Protocol</strong> — Secure agent-to-agent communication for healthcare.<br>
  <sub>Built by <a href="https://symphonix-health.github.io">Symphonix Health</a> | Apache 2.0</sub>
</div>

# HelixCare AI Hospital - NEXUS A2A Protocol

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

**HelixCare** is a comprehensive AI-powered hospital management system built on the NEXUS Agent-to-Agent (A2A) protocol. This repository contains a complete implementation with 19 specialized AI agents, real-time monitoring, and comprehensive testing.

## 🚀 Quick Start (5 minutes)

```bash
# 1. Clone and setup
git clone https://github.com/sync-ai-health/nexus-a2a-protocol.git
cd nexus-a2a-protocol
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 2. Start the system (agents + backend)
python tools/launch_all_agents.py --with-gateway

# 3. Run a patient scenario (via on-demand gateway)
python tools/helixcare_scenarios.py --run chest_pain_cardiac --gateway http://localhost:8100

# 4. Monitor in real-time
python tools/monitor_command_centre.py
```

**Result**: Complete patient journey from triage to discharge with live monitoring at <http://localhost:8099>.
Gateway routes JSON-RPC to agents on-demand at <http://localhost:8100/rpc/{agent}>.

## 📖 Documentation

| Document | Description | Use Case |
|----------|-------------|----------|
| **[User Manual](HELIXCARE_USER_MANUAL.md)** | Complete guide for users | **Start Here** - Full system walkthrough |
| **[How to Run](docs/how-to-run.md)** | Setup and deployment | Installation & configuration (includes on-demand gateway) |
| **[On-Demand Gateway](docs/on-demand-gateway.md)** | Lazy process manager + JSON-RPC proxy | Route all RPC to /rpc/{agent} |
| **[Architecture](docs/architecture.md)** | High-level and detailed diagrams | Align code, specs, diagrams |
| **[Developer Reference](docs/developer_reference.md)** | API documentation | Technical development |
| **[Scenarios Guide](tools/SCENARIOS_README.md)** | Patient journey scenarios | Testing & demonstrations |
| **[Compliance Guide](docs/compliance_guide.md)** | Security & compliance | Regulatory requirements |
| **[Command Centre](docs/command-centre-summary.md)** | Monitoring dashboard | System operations |

## 🏥 System Overview

### 19 AI Agents Working Together

#### Core Medical Agents (8)
- **Triage Agent** - Initial patient assessment
- **Diagnosis Agent** - Medical diagnosis & differentials
- **Imaging Agent** - Radiology coordination
- **Pharmacy Agent** - Medication recommendations
- **Bed Manager** - Admission coordination
- **Discharge Agent** - Discharge planning
- **Follow-up Agent** - Post-discharge care
- **Care Coordinator** - Journey orchestration

#### Infrastructure (11)
- **Command Centre** - Real-time monitoring dashboard
- **Security & Authentication** - JWT-based access control
- **Protocol Services** - Discovery, surveillance, and compliance

### Key Features
- 🤖 **AI-Powered**: Specialized medical AI for each agent
- 🔄 **Autonomous**: Agents communicate without human intervention
- 📊 **Real-time Monitoring**: Live dashboard at http://localhost:8099
- 🛡️ **Secure**: JWT authentication with role-based access
- ✅ **Fully Tested**: 7,000+ scenarios, 100% compliance
- 📈 **Scalable**: Microservices architecture

## 🎯 Common Tasks

### Run Patient Scenarios
```bash
# List all scenarios
python tools/helixcare_scenarios.py --list

# Run cardiac emergency
python tools/helixcare_scenarios.py --run chest_pain_cardiac

# Run all scenarios
python tools/run_helixcare_scenarios.py --gateway http://localhost:8100
```

### Monitor System Health
```bash
# Start Command Centre
python -m uvicorn app.main:app --host 0.0.0.0 --port 8099 --app-dir shared/command-centre
# Visit: http://localhost:8099

# Real-time monitoring
python tools/monitor_command_centre.py
```

### Run Full Test Suite
```bash
# Complete validation (7,000+ scenarios)
python tools/run_hc_validation.py

# Individual test categories
python -m pytest tests/nexus_harness/test_helixcare_*.py -v
```

## 🐳 Docker Deployment

```bash
# Start all services
docker-compose -f docker-compose-helixcare.yml up -d

# Check status
docker-compose -f docker-compose-helixcare.yml ps

# View logs
docker-compose -f docker-compose-helixcare.yml logs -f command-centre
```

## 📊 Architecture

```
┌─────────────────┐    ┌─────────────────┐
│   Command       │    │   Patient       │
│   Centre        │◄──►│   Scenarios     │
│   (Port 8099)   │    │   (10 types)    │
└─────────────────┘    └─────────────────┘
         │
    ┌────┴────┐
    │  NEXUS  │
    │  A2A    │
    │ Protocol│
    └────┴────┘
         │
    ┌────┴────┐
    │ 8 Core  │
    │ Medical │
    │ Agents  │
    └─────────┘
```

**Communication**: JSON-RPC 2.0 over HTTP with JWT authentication. Supports an on-demand gateway at `/rpc/{agent}`.
**Real-time**: WebSocket and Server-Sent Events
**Security**: HS256 JWT tokens with configurable secrets

## 🔧 Development

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- Git

### Setup Development Environment
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/ -v

# Code formatting
black src/ demos/ tools/
isort src/ demos/ tools/

# Type checking
mypy src/
```

### Project Structure
```
nexus-a2a-protocol/
├── src/                    # Core NEXUS protocol
├── demos/helixcare/        # 19 AI agent implementations
├── shared/                 # Common utilities & Command Centre
├── tests/                  # Comprehensive test suite
├── tools/                  # Development & testing tools
├── docs/                   # Documentation
└── HELIXCARE_USER_MANUAL.md # Complete user guide
```

## 🧪 Testing & Validation

- **7 Test Harnesses**: Complete functional coverage
- **7,000+ Scenarios**: All medical workflows tested
- **100% Compliance**: All requirements validated
- **Performance Benchmarks**: Latency and throughput metrics

```bash
# Run compliance suite
python tools/run_compliance_suite.py

# Generate reports
python tools/generate_conformance_report.py
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

See [Developer Reference](docs/developer_reference.md) for detailed contribution guidelines.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

- **Documentation**: [User Manual](HELIXCARE_USER_MANUAL.md)
- **Issues**: [GitHub Issues](https://github.com/sync-ai-health/nexus-a2a-protocol/issues)
- **Discussions**: Community Q&A and collaboration

## 🔬 Research & Papers

- [Autonomous Digital Hospital White Paper](docs/autonomous_digital_hospital_white_paper.md)
- [NEXUS A2A Protocol Research](docs/research.md)
- [Strategic Governance Brief](docs/strategic_governance_brief.md)

---

**HelixCare**: Revolutionizing healthcare through autonomous AI agent collaboration.

*Built with the NEXUS Agent-to-Agent protocol for secure, scalable healthcare automation.*
- Workspace environments are in `.vscode/settings.json` under `rest-client.environmentVariables`.
- Sample requests are in `requests/nexus-a2a.http`.

To use:
1. Open `requests/nexus-a2a.http`.
2. In VS Code, choose environment `local`, `dev`, or `prod`.
3. Update `apiToken` and `baseUrl` values in `.vscode/settings.json`.

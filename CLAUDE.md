# CLAUDE.md — HelixCare / NEXUS A2A Protocol

## Project Overview
HelixCare is an AI-powered hospital management system built on the **NEXUS Agent-to-Agent (A2A) protocol**.
- 12 agent implementations (FastAPI apps) + On-Demand Gateway + Command Centre
- 24 patient journey scenarios
- Real-time Command Centre dashboard (port 8099), Clinician Avatar (port 8039), On-Demand Gateway (port 8100)

## Stack
- **Language**: Python 3.12 (venv at `.venv/`)
- **Web framework**: FastAPI + Uvicorn
- **Protocol**: JSON-RPC 2.0 with JWT HS256 authentication (`nexus:invoke` scope)
- **Real-time**: WebSocket + Server-Sent Events (SSE)
- **LLM**: OpenAI (`gpt-4o-mini` default); local via `local_docker_smollm2` profile
- **TTS**: OpenAI `gpt-4o-mini-tts` streaming PCM (24 kHz 16-bit mono); browser SpeechSynthesis fallback
- **Lint/Format**: Ruff (`ruff.importStrategy: "fromEnvironment"`)
- **Testing**: pytest with `asyncio_mode = "auto"`, testpaths = `["tests"]`
- **Node**: Playwright tests + Mermaid diagram rendering

## Project Layout
```
nexus-a2a-protocol/
├── src/nexus_a2a_protocol/        # Core protocol SDK (models, jsonrpc, errors)
├── shared/
│   ├── nexus_common/              # Shared lib (see modules below)
│   ├── clinician_avatar/          # Avatar engine, sessions, clinical frameworks
│   ├── command-centre/            # Dashboard backend + JS frontend (port 8099)
│   └── on_demand_gateway/         # Lazy process manager + JSON-RPC proxy (port 8100)
├── demos/helixcare/               # 12 agent FastAPI apps
├── tools/                         # Scenario runners, launchers, MCP server
├── tests/                         # 78 test files
│   └── nexus_harness/             # E2E harness tests (live agents required)
├── HelixCare/                     # Harness matrix JSON files + design documents
├── config/
│   ├── agents.json                # Port registry + LLM profiles
│   ├── personas.json              # 68-persona registry (UK/USA/Kenya)
│   └── agent_personas.json        # Agent → persona + IAM group mapping
├── docs/                          # Architecture, compliance, IAM design
├── avatar/                        # Reference avatar media (video/images)
└── HELIXCARE_USER_MANUAL.md
```

## Agent Ports
| Agent | Port | Job Profile |
|-------|------|-------------|
| Triage | 8021 | Triage Nurse |
| Diagnosis | 8022 | Diagnosing Physician |
| Imaging | 8023 | Radiologist |
| Pharmacy | 8024 | Pharmacist |
| Bed Manager | 8025 | Bed Manager |
| Discharge | 8026 | Discharge Coordinator |
| Follow-up Scheduler | 8027 | GP (Follow-up) |
| Care Coordinator | 8028 | Care Coordinator |
| CCM Agent | 8029 | Clinical Doc Improvement Specialist |
| Clinician Avatar | 8039 | Consultant Physician (P001) |
| Command Centre | 8099 | — |
| On-Demand Gateway | 8100 | — |

## Common Commands
```bash
# Start all agents + Command Centre (default)
python tools/launch_all_agents.py
python tools/launch_all_agents.py --with-gateway
python tools/launch_all_agents.py --llm-profile local_docker_smollm2
python tools/launch_all_agents.py --stop              # Stop all services
python tools/launch_all_agents.py --no-backend        # Agents only, no CC
python tools/launch_all_agents.py --backend-only      # Command Centre only

# Run a patient scenario
python tools/helixcare_scenarios.py --run chest_pain_cardiac --gateway http://localhost:8100

# Run all unit tests
PYTHONPATH=. NEXUS_JWT_SECRET=dev-secret-change-me python -m pytest tests/ -v

# Run harness tests (requires live agents)
PYTHONPATH=. NEXUS_JWT_SECRET=dev-secret-change-me python -m pytest tests/nexus_harness/ -v

# Run a specific harness suite
PYTHONPATH=. NEXUS_JWT_SECRET=dev-secret-change-me \
  python -m pytest tests/nexus_harness/test_helixcare_avatar_streaming.py -v

# Lint / Format
python -m ruff check src tests
python -m ruff format src tests

# Mint a JWT for CLI testing
python -c "from shared.nexus_common.auth import mint_jwt; print(mint_jwt('test', 'dev-secret-change-me'))"

# Get a dev browser JWT from the avatar agent (works only with default dev secret)
curl http://localhost:8039/dev/token
```

## Starting / Restarting Individual Services (Windows)
```bash
# Kill a service by port — use Python (Windows taskkill via Git Bash has path issues)
python -c "
import subprocess
r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
for line in r.stdout.splitlines():
    if ':8039' in line and 'LISTENING' in line:
        pid = line.strip().split()[-1]
        subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
"

# Start avatar agent
PYTHONPATH=c:/nexus-a2a-protocol NEXUS_JWT_SECRET=dev-secret-change-me DID_VERIFY=false \
  .venv/Scripts/python.exe -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8039 --app-dir demos/helixcare/clinician-avatar-agent

# Start Command Centre
PYTHONPATH=c:/nexus-a2a-protocol NEXUS_JWT_SECRET=dev-secret-change-me DID_VERIFY=false \
  .venv/Scripts/python.exe -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8099 --app-dir shared/command-centre
```
All agents: `--app-dir demos/helixcare/<agent-dir>` at the port from `config/agents.json`.

## Authentication
- JWT HS256; env var `NEXUS_JWT_SECRET` (default `dev-secret-change-me`)
- Scope: `nexus:invoke`
- `from shared.nexus_common.auth import mint_jwt, verify_jwt`
- Avatar `/dev/token` endpoint — browser-safe 1-hour JWT (disabled if non-default secret)
- DID verification disabled by default (`DID_VERIFY=false`)

## Key Environment Variables
| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXUS_JWT_SECRET` | `dev-secret-change-me` | JWT signing secret |
| `OPENAI_API_KEY` | *(required for TTS/LLM)* | OpenAI API access |
| `OPENAI_MODEL` | `gpt-4o-mini` | LLM model for agents |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | TTS model for avatar |
| `OPENAI_TTS_VOICE` | `alloy` | Default TTS voice |
| `VIDEO_CLINICIAN_PROVIDER` | `local_gpu` | Avatar provider: `local_gpu`, `did`, `sync` |
| `DID_VERIFY` | `false` | Enable DID signature verification |
| `AVATAR_SESSION_IDLE_TTL` | `1800` | Seconds before idle avatar session is reaped |
| `AVATAR_MAX_CONVERSATION_TURNS` | `100` | Max turns kept in avatar session history |
| `UPDATE_INTERVAL_MS` | `5000` | Command Centre poll interval (ms) |
| `CC_POLL_CONCURRENCY` | `6` | Max concurrent agent health checks |
| `CC_WS_MAX_CLIENTS` | `20` | Max WebSocket dashboard clients |
| `AGENT_URLS` | *(from config/agents.json)* | Override monitored agent URLs (comma-separated) |

## LLM Profiles
Defined in `config/agents.json` under `llm_profiles`:
- `openai_cloud` — OpenAI-hosted inference (default)
- `local_docker_smollm2` — local llama.cpp on port 18080

```bash
python tools/launch_all_agents.py --list-llm-profiles
python tools/launch_all_agents.py --llm-profile local_docker_smollm2
```

## Shared Modules (`shared/nexus_common/`)
| Module | Purpose |
|--------|---------|
| `auth.py` | `mint_jwt`, `verify_jwt`, `AuthError` |
| `jsonrpc.py` | `parse_request`, `response_result`, `response_error`, `JsonRpcError` |
| `generic_demo_agent.py` | Base FastAPI agent pattern |
| `openai_helper.py` | `llm_chat()` — LLM wrapper |
| `sse.py` | `TaskEventBus` — SSE + JSONL persistence (2 MB auto-rotation) |
| `trace.py` / `trace_context.py` | Distributed tracing |
| `identity/` | `PersonaRegistry`, `AgentIdentity`, `get_agent_identity()` |
| `idempotency.py` | Request deduplication |
| `health.py` | Health scoring helpers |
| `redaction.py` | PII field masking for trace payloads |
| `audit.py` | Audit log helpers |
| `did.py` | DID signature verification |
| `mqtt_client.py` | MQTT pub/sub for IoT events |
| `otel.py` | OpenTelemetry tracing |

## Clinician Avatar Architecture
- **Engine**: `shared/clinician_avatar/avatar_engine.py` — session mgmt, history cap, TTL reaper
- **Frameworks**: Calgary-Cambridge, SOCRATES, ABCDE (`shared/clinician_avatar/frameworks/`)
- **TTS provider**: `shared/clinician_avatar/video_clinician_provider.py`
  - `has_openai_tts()` — True when `OPENAI_API_KEY` is set
  - `stream_tts_chunks(text, voice)` — async generator yielding raw PCM chunks
  - `simple_viseme_timeline(text)` — word-level viseme timestamps
- **WebSocket TTS stream**: `GET /api/tts/stream?token=<jwt>` on port 8039
  - Frame sequence: `speak` → `meta` → `visemes` → binary PCM chunks → `end`
  - `{"type":"meta","synthetic":true}` — no API key; client uses browser SpeechSynthesis
  - `{"type":"synthetic_fallback"}` — API key set but call failed; client switches to browser TTS
- **Health endpoint** must return `"name"` field (persona display name) for Command Centre
- **Static UI**: `demos/helixcare/clinician-avatar-agent/app/static/`
  - `tts_client.js` — PCM scheduling via Web Audio API + AnalyserNode amplitude lipsync
  - `avatar_renderer.js` — video/canvas avatar rendering
  - `lipsync_engine.js` — viseme-timeline-driven lip sync
  - `chat_controller.js` — session lifecycle, barge-in, state machine

## Identity & Persona System
- `config/personas.json` — 68 personas (UK/USA/Kenya)
- `config/agent_personas.json` — each agent's primary persona, alternates, IAM groups
- `shared/nexus_common/identity/` — `get_agent_identity(agent_id)`, `get_persona_registry()`
- Avatar resolves persona by `persona_id`, `country`, `care_setting`, or defaults to P001 (Consultant Physician)
- IAM groups: `nexus-clinical-high/medium`, `nexus-operations`, `nexus-governance`, `nexus-connector`, `nexus-intelligence`
- Doc: `docs/iam_identity_architecture.md`

## Harness Tests (`tests/nexus_harness/`)
Require live agents. Matrix JSON files live in `HelixCare/`:

| Harness | Matrix | Coverage |
|---------|--------|----------|
| `test_helixcare_avatar_streaming.py` | `helixcare_avatar_streaming_matrix.json` | 21 scenarios — TTS, visemes, auth, edge cases |
| `test_helixcare_ed_intake.py` | `helixcare_ed_intake_triage_matrix.json` | ED triage workflow |
| `test_helixcare_diagnosis_imaging.py` | `helixcare_diagnosis_imaging_matrix.json` | Diagnosis + imaging |
| `test_helixcare_discharge.py` | `helixcare_discharge_matrix.json` | Discharge workflow |
| `test_helixcare_admission_treatment.py` | `helixcare_admission_treatment_matrix.json` | Admission |
| `test_helixcare_persona_iam.py` | `helixcare_persona_iam_matrix.json` | Identity/IAM |
| `test_helixcare_protocol_security.py` | `helixcare_protocol_security_matrix.json` | Auth/security |

Harness pattern: parametrized pytest from matrix JSON → `runner.py` → `ScenarioResult` → `docs/conformance-report.json`.

## Command Centre Patterns
- Agent display name: `health["name"]` → `card["name"]` → URL — all agents should return `"name"` in `/health`
- `dashboard.js` `AGENT_JOB_PROFILES` map translates agent IDs to job titles for heatmap/trace views
- WS broadcasts a slim snapshot (no card data) once per poll cycle — do not add per-client loops
- Full card data: `GET /api/agents/{url}` (60 s TTL cache)
- Trace ingestion: `POST /api/traces` | list: `GET /api/traces` | detail: `GET /api/traces/{id}`

## Adding Agents / Scenarios
- **New agent**: use `generic_demo_agent.py` base; add dir under `demos/helixcare/`; register in `config/agents.json`; return `"name"` in `/health`; add job profile to `AGENT_JOB_PROFILES` in `dashboard.js`
- **New scenario**: add to `tools/helixcare_all_scenarios.json` with `journey_steps[]`; add `PatientScenario` to `tools/helixcare_scenarios.py` (must include `medical_history`)
- **New harness**: add matrix JSON to `HelixCare/`; add test file to `tests/nexus_harness/`

## Key References
- [README.md](README.md) — Quick start
- [HELIXCARE_USER_MANUAL.md](HELIXCARE_USER_MANUAL.md) — Full user manual
- [docs/developer_reference.md](docs/developer_reference.md) — Protocol patterns
- [docs/architecture.md](docs/architecture.md) — Architecture diagrams
- [docs/iam_identity_architecture.md](docs/iam_identity_architecture.md) — Agent IAM / Entra / personas
- [config/agents.json](config/agents.json) — Port registry + LLM profiles
- [config/personas.json](config/personas.json) — 68-persona registry
- [config/agent_personas.json](config/agent_personas.json) — Agent IAM + persona mappings
- [HelixCare/](HelixCare/) — Design docs + scenario matrix JSON files

## VSCode
- Interpreter: `.venv/Scripts/python.exe`
- Ruff is the formatter/linter (`fromEnvironment`)
- Tasks: `.vscode/tasks.json` (test, lint, agent launch, docker)
- Debug: `.vscode/launch.json`
- MCP server: `tools/nexus_mcp_server.py` (configured in `.vscode/mcp.json`)

# HelixCare 100% Compliance Implementation Plan

## Goal
Ensure 100% compliance of all 22 PDF requirements (FR-1–FR-12, NFR-1–NFR-10) by:
1. Creating test harness files to execute all 7,000 HelixCare scenarios
2. Implementing the 4 missing functional requirements (FR-4 Imaging, FR-5 Pharmacy, FR-6 Admission, FR-7 Discharge)
3. Implementing all missing security requirements (NFR-1 mTLS, NFR-2 OIDC, NFR-3 RBAC)
4. Achieving 100% pass rate across all scenarios

---

## Phase 1: Create 6 New Agents (ports 8024–8029)

### 1a. Imaging Agent (port 8024) — FR-4
- **Path:** `demos/helixcare/imaging-agent/app/main.py` + `agent_card.json`
- **RPC Methods:** `imaging/request`, `imaging/analyze`, `tasks/sendSubscribe`
- **Logic:** Imaging study ordering (CXR, CT, MRI, US, ECG) with AI-assisted findings
- **Pattern:** Same as triage-agent (FastAPI + JWT auth + SSE bus + WebSocket + health monitor)

### 1b. Pharmacy Agent (port 8025) — FR-5
- **Path:** `demos/helixcare/pharmacy-agent/app/main.py` + `agent_card.json`
- **RPC Methods:** `pharmacy/recommend`, `pharmacy/check_interactions`, `tasks/sendSubscribe`
- **Logic:** Drug formulary lookup, allergy checking, drug-drug interaction detection, alternative suggestions

### 1c. Bed Manager Agent (port 8026) — FR-6
- **Path:** `demos/helixcare/bed-manager-agent/app/main.py` + `agent_card.json`
- **RPC Methods:** `admission/assign_bed`, `admission/check_availability`, `tasks/sendSubscribe`
- **Logic:** Bed inventory (ICU/Ward/ED_Obs/Paediatric/Cardiac), assignment with fallback to alternative units, waitlisting

### 1d. Discharge Agent (port 8027) — FR-7
- **Path:** `demos/helixcare/discharge-agent/app/main.py` + `agent_card.json`
- **RPC Methods:** `discharge/initiate`, `discharge/create_summary`, `tasks/sendSubscribe`
- **Logic:** Discharge summary generation (FHIR Composition), follow-up scheduling via followup-scheduler

### 1e. Follow-up Scheduler (port 8028) — FR-7 support
- **Path:** `demos/helixcare/followup-scheduler/app/main.py` + `agent_card.json`
- **RPC Methods:** `followup/schedule`, `tasks/sendSubscribe`
- **Logic:** Post-discharge appointment scheduling with urgency-based timing

### 1f. Care Coordinator (port 8029) — FR-8
- **Path:** `demos/helixcare/care-coordinator/app/main.py` + `agent_card.json`
- **RPC Methods:** `tasks/sendSubscribe`
- **Logic:** Orchestrates full patient journey: triage → diagnosis → imaging → admission → treatment → discharge
- **Calls:** triage-agent (8021), imaging-agent (8024), bed-manager-agent (8026), discharge-agent (8027)

### Agent Template Pattern (all 6 agents follow this)
```
- FastAPI app with /rpc, /.well-known/agent-card.json, /health, /events/{task_id}, /ws/{task_id}
- JWT bearer auth via shared.nexus_common.auth.verify_jwt
- Optional DID verification via shared.nexus_common.did
- SSE event bus via shared.nexus_common.sse.TaskEventBus
- Health monitoring via shared.nexus_common.health.HealthMonitor
- JSON-RPC 2.0 dispatch via shared.nexus_common.jsonrpc
- REQUIRED_SCOPE = "nexus:invoke"
```

---

## Phase 2: Create 7 Test Harness Files

Each test file loads its corresponding `HelixCare/*.json` matrix (1,000 scenarios) and runs ALL positive + negative scenarios.

### Test Files to Create

| # | File | Matrix | Agent Map |
|---|------|--------|-----------|
| 1 | `tests/nexus_harness/test_helixcare_ed_intake.py` | `helixcare_ed_intake_triage_matrix.json` | triage-agent, diagnosis-agent, openhie-mediator |
| 2 | `tests/nexus_harness/test_helixcare_diagnosis_imaging.py` | `helixcare_diagnosis_imaging_matrix.json` | imaging-agent, diagnosis-agent |
| 3 | `tests/nexus_harness/test_helixcare_admission_treatment.py` | `helixcare_admission_treatment_matrix.json` | bed-manager-agent, pharmacy-agent |
| 4 | `tests/nexus_harness/test_helixcare_discharge.py` | `helixcare_discharge_matrix.json` | discharge-agent, followup-scheduler |
| 5 | `tests/nexus_harness/test_helixcare_surveillance.py` | `helixcare_public_health_surveillance_matrix.json` | central-surveillance, hospital-reporter, osint-agent |
| 6 | `tests/nexus_harness/test_helixcare_protocol_discovery.py` | `helixcare_protocol_discovery_matrix.json` | all agents (agent card discovery) |
| 7 | `tests/nexus_harness/test_helixcare_protocol_security.py` | `helixcare_protocol_security_matrix.json` | all agents (auth/security) |

### Test Pattern (each file)
```python
- Load matrix via load_helixcare_matrix(filename)
- Split into _positive and _negative lists
- @pytest.mark.parametrize over ALL scenarios (no [:10] cap)
- Positive tests: POST /rpc with auth, assert 200 + result fields
- Negative tests: POST /rpc with bad/no auth, assert error response
- Discovery tests: GET /.well-known/agent-card.json on all agents
- Security tests: Verify auth rejection for invalid tokens
- SSE tests: Stream /events/{task_id} after task submission
- All results recorded via ScenarioResult → ConformanceReport
```

---

## Phase 3: Patch Infrastructure

### 3a. Patch `tests/nexus_harness/runner.py`
Append these new functions/constants:
- `HELIXCARE_MATRICES_DIR` — points to `HelixCare/` directory
- `load_helixcare_matrix(filename)` — loads a HelixCare JSON matrix
- `scenarios_for_helixcare(filename, tags, scenario_type)` — filter helper
- `HELIXCARE_URLS` — dict mapping all 19 agent names to localhost URLs (8021–8029, 8031–8033, 8041–8044, 8051–8053)

### 3b. Patch `tools/launch_all_agents.py`
Add 6 new entries to the AGENTS list:
```
("demos/helixcare/imaging-agent",       8024),
("demos/helixcare/pharmacy-agent",      8025),
("demos/helixcare/bed-manager-agent",   8026),
("demos/helixcare/discharge-agent",     8027),
("demos/helixcare/followup-scheduler",  8028),
("demos/helixcare/care-coordinator",    8029),
```

### 3c. Create `__init__.py` files
- `demos/helixcare/*/` — empty __init__.py for each agent directory
- `demos/helixcare/*/app/` — empty __init__.py for each app directory

---

## Phase 4: Security Implementation

### 4a. mTLS (NFR-1) — Self-signed certs for dev/test
- Generate CA + server certs via Python `cryptography` library
- Add `--ssl-certfile` / `--ssl-keyfile` to uvicorn launch in agents
- Create `config/certs/` directory with generated certs
- For test harness: use `httpx.AsyncClient(verify=False)` or custom CA bundle

### 4b. OIDC/RS256 (NFR-2) — Wire existing auth.py into agents
- Add `AUTH_MODE=hs256|rs256` environment variable toggle
- In each agent's `_require_auth()`: check AUTH_MODE and call `verify_jwt_rs256()` when rs256
- Fallback to HS256 when RS256 deps not available

### 4c. RBAC (NFR-3) — Role-based scope assertions
- Define role→scope mappings: `{"clinician": ["nexus:invoke", "nexus:read"], "admin": ["nexus:*"]}`
- Add `required_roles` parameter to `_require_auth()`
- Check JWT claims `roles` or `scope` against required

### 4d. Audit Logging (NFR-4, NFR-8) — Wire audit.py
- Call `env_audit_logger().log()` at key decision points in all orchestrator agents
- Log: triage accept/complete, consent approve/deny, imaging request, admission, discharge

---

## Phase 5: Execution & Validation

### Launch Sequence
```powershell
# 1. Launch all 19 agents
python tools/launch_all_agents.py

# 2. Verify health endpoints
for ($p=8021; $p -le 8029; $p++) { Invoke-RestMethod "http://localhost:$p/health" }

# 3. Run all 7,000 HelixCare scenarios
pytest tests/nexus_harness/test_helixcare_*.py -v --tb=short

# 4. Run full suite (nexus + HelixCare = ~16,000 scenarios)
pytest tests/nexus_harness/ -v --tb=short

# 5. Generate conformance report
python tools/generate_conformance_report.py
```

### Pass Criteria
- All 7,000 HelixCare scenarios: **PASS**
- All 9,075 Nexus scenarios: **PASS** (existing)
- FR-1 through FR-12: **All covered**
- NFR-1 through NFR-10: **All covered**
- SPR, CR, IR requirements: **All covered**

---

## File Creation Checklist

### New Files (25 total)
- [ ] `demos/helixcare/imaging-agent/app/agent_card.json`
- [ ] `demos/helixcare/imaging-agent/app/main.py`
- [ ] `demos/helixcare/imaging-agent/app/__init__.py`
- [ ] `demos/helixcare/imaging-agent/__init__.py`
- [ ] `demos/helixcare/pharmacy-agent/app/agent_card.json`
- [ ] `demos/helixcare/pharmacy-agent/app/main.py`
- [ ] `demos/helixcare/pharmacy-agent/app/__init__.py`
- [ ] `demos/helixcare/pharmacy-agent/__init__.py`
- [ ] `demos/helixcare/bed-manager-agent/app/agent_card.json`
- [ ] `demos/helixcare/bed-manager-agent/app/main.py`
- [ ] `demos/helixcare/bed-manager-agent/app/__init__.py`
- [ ] `demos/helixcare/bed-manager-agent/__init__.py`
- [ ] `demos/helixcare/discharge-agent/app/agent_card.json`
- [ ] `demos/helixcare/discharge-agent/app/main.py`
- [ ] `demos/helixcare/discharge-agent/app/__init__.py`
- [ ] `demos/helixcare/discharge-agent/__init__.py`
- [ ] `demos/helixcare/followup-scheduler/app/agent_card.json`
- [ ] `demos/helixcare/followup-scheduler/app/main.py`
- [ ] `demos/helixcare/followup-scheduler/app/__init__.py`
- [ ] `demos/helixcare/followup-scheduler/__init__.py`
- [ ] `demos/helixcare/care-coordinator/app/agent_card.json`
- [ ] `demos/helixcare/care-coordinator/app/main.py`
- [ ] `demos/helixcare/care-coordinator/app/__init__.py`
- [ ] `demos/helixcare/care-coordinator/__init__.py`
- [ ] `tests/nexus_harness/test_helixcare_ed_intake.py`
- [ ] `tests/nexus_harness/test_helixcare_diagnosis_imaging.py`
- [ ] `tests/nexus_harness/test_helixcare_admission_treatment.py`
- [ ] `tests/nexus_harness/test_helixcare_discharge.py`
- [ ] `tests/nexus_harness/test_helixcare_surveillance.py`
- [ ] `tests/nexus_harness/test_helixcare_protocol_discovery.py`
- [ ] `tests/nexus_harness/test_helixcare_protocol_security.py`

### Modified Files (2)
- [ ] `tests/nexus_harness/runner.py` — append HelixCare matrix support
- [ ] `tools/launch_all_agents.py` — add 6 new agent entries

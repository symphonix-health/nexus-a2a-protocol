# NEXUS-A2A Traceability Matrix

This document maps **requirement IDs** (from the scenario matrices) to the
**test modules** and **code modules** that exercise them.

> Auto-traceable: every scenario in the JSON matrices carries a
> `requirement_ids` array.  The test harness propagates these into the
> conformance report, enabling full bidirectional traceability.

---

## Requirement → Test → Code

| Req ID | Category | Test Module(s) | Code Module(s) |
|--------|----------|----------------|-----------------|
| CR-1 | Core – JSON-RPC envelope | `test_protocol_core` | `shared/nexus_common/jsonrpc.py` |
| CR-2 | Core – Agent card | `test_protocol_core`, `test_ed_triage` | All `agent_card.json` files |
| FR-1 | Functional – Task lifecycle | `test_protocol_core`, demo tests | `shared/nexus_common/ids.py`, agent `main.py` |
| FR-2 | Functional – RPC dispatch | `test_protocol_core` | `shared/nexus_common/jsonrpc.py`, agent `main.py` |
| FR-3 | Functional – ED triage flow | `test_ed_triage` | `demos/ed-triage/*/app/main.py` |
| FR-4 | Functional – Diagnosis | `test_ed_triage` | `demos/ed-triage/diagnosis-agent/app/main.py` |
| FR-5 | Functional – FHIR lookup | `test_ed_triage` | `demos/ed-triage/openhie-mediator/app/main.py` |
| FR-6 | Functional – Agent discovery | All tests | `/.well-known/agent-card.json` endpoint |
| FR-7 | Functional – Streaming | `test_protocol_streaming` | `shared/nexus_common/sse.py` |
| IR-1 | Integration – Inter-agent call | Demo tests | `shared/nexus_common/http_client.py` |
| IR-2 | Integration – MQTT | `test_protocol_multitransport`, `test_surveillance` | `shared/nexus_common/mqtt_client.py` |
| NFR-1 | Non-functional – Auth | `test_protocol_core` (negative) | `shared/nexus_common/auth.py` |
| NFR-2 | Non-functional – HS256 JWT | All tests | `shared/nexus_common/auth.py` |
| NFR-3 | Non-functional – Error codes | Negative tests | `shared/nexus_common/jsonrpc.py` |
| SPR-1 | Security – Bearer token | All tests | `_require_auth()` in all agents |
| SPR-2 | Security – DID verification | (Feature-flagged) | `shared/nexus_common/did.py` |
| SPR-5 | Security – Scope checking | `test_protocol_core` | `shared/nexus_common/auth.py` |

---

## Demo → Requirements Covered

| Demo | Matrix File | Requirement IDs (sample) |
|------|-------------|--------------------------|
| ED Triage | `nexus_ed_triage_matrix.json` | FR-3, FR-4, FR-5, FR-6, FR-7, IR-1, NFR-1-3, SPR-1 |
| Telemed Scribe | `nexus_telemed_scribe_matrix.json` | FR-6, FR-7, IR-1, NFR-1-3, SPR-1 |
| Consent Verification | `nexus_consent_verification_matrix.json` | FR-6, FR-7, IR-1, NFR-1-3, SPR-1 |
| Public Health Surveillance | `nexus_public_health_surveillance_matrix.json` | FR-6, FR-7, IR-1, IR-2, NFR-1-3, SPR-1 |
| Protocol Core | `nexus_protocol_core_matrix.json` | CR-1, CR-2, FR-1, FR-2, NFR-1-3, SPR-5 |
| Protocol Streaming | `nexus_protocol_streaming_matrix.json` | FR-7, NFR-1-3 |
| Protocol Multitransport | `nexus_protocol_multitransport_matrix.json` | IR-2, NFR-1-3 |

---

## How to Regenerate

```bash
# Run the full harness – the report is written automatically
pytest tests/nexus_harness/ -v
cat docs/conformance-report.json | python -m json.tool
```

The `conformance-report.json` carries `requirement_ids` per scenario result,
enabling programmatic extraction of coverage metrics.

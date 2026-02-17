# NEXUS-A2A Protocol Hyperscale Backlog

Date: 2026-02-16
Scope: protocol and shared protocol-runtime only (not infra product selection)
Target: operationally ready protocol profile for 1,000,000,000 users and 10,000,000 concurrent sessions

## 1. Readiness definition for protocol hyperscalability

Protocol is considered hyperscalable only when all conditions are true:

1. All mutating RPC methods strictly enforce the v1.1 scale profile and idempotency profile.
2. Stream sequencing and resume contracts are deterministic under reconnect, replay, failover, and duplicate delivery.
3. Admission-control semantics are protocol-stable and machine-actionable across all agents (`-32004` strict payload contract).
4. Capability/version negotiation is safe for rolling upgrades and mixed-version fleets.
5. Multi-region write consistency and conflict semantics are deterministic and observable.
6. Conformance gates include deterministic, repeatable high-concurrency certification evidence, not only schema checks.

## 2. Milestones and exit criteria

| Milestone | Window | Exit criteria |
| --- | --- | --- |
| M0 Baseline Freeze | Week 1 | Current protocol behavior frozen; ticket register accepted; risk register created |
| M1 Contract Completeness | Weeks 2-3 | All mutating methods return consistent validation and negotiation errors with deterministic payloads |
| M2 Stateful Semantics | Weeks 4-5 | Idempotency and stream resume semantics deterministic across restart/replay paths |
| M3 Multi-Region Semantics | Weeks 6-7 | Conflict and consistency metadata complete and validated for reject/vector-clock flows |
| M4 Deterministic Certification | Weeks 8-9 | G0-G4 deterministic in CI with strict-fail and bounded runtime |
| M5 Hyperscale Evidence Pack | Weeks 10-12 | Protocol certification report includes synthetic 10M concurrency evidence and unresolved risk log |

## 3. Service backlog tickets

| Ticket | Priority | Milestone | Service | Status | Deliverables | Done when |
| --- | --- | --- | --- | --- | --- | --- |
| SVC-PROT-001 | P0 | M1 | jsonrpc validation | done | `src/nexus_a2a_protocol/jsonrpc.py`, `shared/nexus_common/jsonrpc.py` | `scale_profile` required fields enforced on all mutating methods |
| SVC-PROT-002 | P0 | M1 | idempotency contract | done | `src/nexus_a2a_protocol/jsonrpc.py`, `shared/nexus_common/idempotency.py` | key/scope/payload-hash validation deterministic |
| SVC-PROT-003 | P0 | M2 | stream sequencing | done | `shared/nexus_common/sse.py` | event `seq`, `stream_epoch`, cursor helpers emitted and parsed |
| SVC-PROT-004 | P0 | M1 | admission error semantics | done | `shared/nexus_common/jsonrpc.py` | strict `-32004` helper payload available |
| SVC-PROT-005 | P0 | M1 | canonical shard routing contract | done | `shared/nexus_common/scale_profile.py`, `shared/nexus_common/jsonrpc.py`, `src/nexus_a2a_protocol/jsonrpc.py` | deterministic shard-key canonicalization algorithm documented and enforced |
| SVC-PROT-006 | P0 | M2 | signed resume cursor | done | `shared/nexus_common/sse.py`, `shared/nexus_common/jsonrpc.py`, `src/nexus_a2a_protocol/jsonrpc.py` | cursor signature + expiry verification mandatory in resubscribe path |
| SVC-PROT-007 | P0 | M3 | mutation response metadata | done | `shared/nexus_common/protocol.py`, `shared/nexus_common/jsonrpc.py`, `src/nexus_a2a_protocol/jsonrpc.py` | all mutating success responses include `resource_version`, `region_served`, `consistency_applied` |
| SVC-PROT-008 | P0 | M3 | conflict policy implementation | done | `shared/nexus_common/protocol.py`, `shared/nexus_common/jsonrpc.py`, `src/nexus_a2a_protocol/jsonrpc.py` | `reject_on_conflict` and `vector_clock` responses deterministic |
| SVC-PROT-009 | P0 | M1 | feature negotiation middleware | done | `shared/nexus_common/scale_profile.py`, `shared/nexus_common/jsonrpc.py` | required/optional features negotiated in one shared path |
| SVC-PROT-010 | P1 | M1 | agent-card capability profile | planned | agent-card emitters across demo agents | every agent exposes protocol, scale profile, feature flags consistently |
| SVC-PROT-011 | P1 | M4 | deterministic error taxonomy | planned | `shared/nexus_common/jsonrpc.py` | every scale-path rejection includes stable `failure_domain` and `reason` |
| SVC-PROT-012 | P1 | M4 | protocol metrics surface | planned | `shared/nexus_common/metrics.py` | counters for throttles, conflicts, cursor rejects, idempotency mismatches |
| SVC-PROT-013 | P1 | M5 | protocol compatibility mode tests | planned | `tests/test_nexus_protocol_contracts.py` | mixed 1.0/1.1 upgrade scenarios pass without contract drift |
| SVC-PROT-014 | P2 | M5 | protocol SDK reference helpers | planned | `shared/nexus_common/protocol.py` | helper builders for scale profile, idempotency block, retry metadata |

## 4. Datastore backlog tickets (protocol-state stores)

| Ticket | Priority | Milestone | Datastore role | Status | Deliverables | Done when |
| --- | --- | --- | --- | --- | --- | --- |
| DS-IDEMP-001 | P0 | M2 | idempotency L1 | done | `shared/nexus_common/idempotency.py`, `tests/test_idempotency_runtime.py` | strict dedupe window logic validated with deterministic clock tests |
| DS-IDEMP-002 | P0 | M2 | idempotency mismatch tracking | done | `shared/nexus_common/idempotency.py`, `tests/test_idempotency_runtime.py` | conflict payload includes previous hash metadata |
| DS-IDEMP-003 | P1 | M2 | idempotency backend contract | planned | adapter interface + fake backend tests | backend adapter supports in-memory and Redis with same semantics |
| DS-STREAM-001 | P0 | M2 | cursor retention contract | done | `shared/nexus_common/sse.py`, `shared/nexus_common/jsonrpc.py`, `src/nexus_a2a_protocol/jsonrpc.py`, `tests/test_scale_profile_v1_1.py` | cursor expiry and replay windows enforced deterministically |
| DS-STREAM-002 | P1 | M3 | stream epoch reset semantics | planned | `shared/nexus_common/sse.py` | epoch rollover rules validated for replay/reset/failover |
| DS-CAP-001 | P1 | M1 | capability registry snapshot | planned | `shared/nexus_common/scale_profile.py` | capability lookup deterministic by version and feature set |
| DS-CONFLICT-001 | P0 | M3 | version metadata contract | done | `shared/nexus_common/protocol.py`, `shared/nexus_common/jsonrpc.py`, `src/nexus_a2a_protocol/jsonrpc.py`, `tests/test_nexus_protocol_contracts.py`, `tests/test_nexus_jsonrpc.py` | mutation responses carry strict resource/version consistency metadata across all mutation paths |
| DS-CONFLICT-002 | P1 | M3 | vector clock payload schema | done | `shared/nexus_common/protocol.py`, `tests/test_nexus_protocol_contracts.py` | concurrent version payload schema stable and validated |

## 5. Conformance gate backlog tickets

| Ticket | Priority | Milestone | Gate | Status | Deliverables | Done when |
| --- | --- | --- | --- | --- | --- | --- |
| GATE-G0-001 | P0 | M4 | G0 | done | `tests/test_scale_profile_v1_1.py`, `nexus-a2a/artefacts/matrices/nexus_protocol_scale_profile_v1_1_matrix.json` | schema fuzz and negative contract cases deterministic |
| GATE-G0-002 | P0 | M4 | G0 | done | `nexus-a2a/artefacts/matrices/nexus_protocol_scale_profile_v1_1_matrix.json`, `tests/test_scale_profile_v1_1.py` | every required field has explicit reject/accept pair |
| GATE-G1-001 | P0 | M4 | G1 | done | `tools/traffic_generator.py`, `tests/test_traffic_generator_admission.py` | throttling always emits strict `-32004` payload fields |
| GATE-G1-002 | P1 | M4 | G1 | done | `tests/test_traffic_generator_determinism.py`, `tools/traffic_generator.py` | seeded runs produce stable scenario sequence and result shape |
| GATE-G2-001 | P0 | M4 | G2 | done | `tools/run_scale_profile_conformance.py`, `tests/test_scale_profile_v1_1.py` | conflict policy outcomes are deterministic by input policy |
| GATE-G2-002 | P1 | M4 | G2 | done | `tools/run_scale_profile_conformance.py`, `tests/test_scale_profile_v1_1.py` | cursor resume from `seq+1` survives region switch simulation |
| GATE-G3-001 | P0 | M4 | G3 | planned | reorder/duplicate traffic tests | idempotency mismatch and dedupe semantics strict under reordering |
| GATE-G3-002 | P1 | M4 | G3 | planned | fanout sequencing tests | monotonic sequence maintained for high fanout replay |
| GATE-G4-001 | P0 | M4 | G4 | done | `tools/traffic_generator.py` deterministic controls | strict-fail and bounded runtime controls active |
| GATE-G4-002 | P0 | M4 | G4 | done | `tools/run_target_architecture_validation.py` | gate orchestration deterministic and health-state isolated |
| GATE-G5-001 | P0 | M5 | G5 | planned | synthetic hyperscale protocol benchmark | protocol-only harness simulates 10M concurrent sessions |
| GATE-G5-002 | P1 | M5 | G5 | planned | certification report generator | machine-readable pass/fail with unresolved risk list |

## 6. Immediate implementation queue (next 10 tickets)

Execution order for immediate protocol hardening:

1. SVC-PROT-005
2. SVC-PROT-006
3. SVC-PROT-009
4. SVC-PROT-007
5. SVC-PROT-008
6. DS-IDEMP-002
7. DS-STREAM-001
8. GATE-G0-001
9. GATE-G1-001
10. GATE-G2-001

## 7. Definition of protocol hyperscalable state (repo-level)

`protocol_hyperscalable=true` can be declared only when:

1. All P0 tickets in sections 3, 4, 5 are done.
2. `tools/run_scale_profile_conformance.py` reports 100% pass with expanded matrix.
3. `tools/run_target_architecture_validation.py` passes deterministic G0-G4 plus G5 synthetic run.
4. Certification artifact is committed with run metadata, seed, and scenario manifest hash.

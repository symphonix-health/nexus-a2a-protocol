# NEXUS A2A Protocol v1.1 Scale Profile

Status: Draft
Date: 2026-02-15
Audience: Protocol implementers and conformance test authors
Scope: Protocol-level scale readiness profile for deployments targeting 1B users and 1M concurrent sessions

## 1. Objective

This profile defines normative protocol requirements that make large-scale deployments interoperable and operationally safe.

This profile does not prescribe infrastructure products. It standardizes:
- wire fields
- required behaviors
- conformance gates

## 2. Compatibility and Negotiation

`v1.1` is backward-compatible with existing v1.0 message envelopes when scale profile features are not negotiated.

Implementations claiming `v1.1-scale` support MUST implement capability negotiation in agent-card metadata and request parameters.

## 3. Normative Terms

The key words `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` are to be interpreted as in RFC 2119.

## 4. Scale Profile Envelope Extensions

### 4.1 Request `params.scale_profile`

All mutating methods (`tasks/send`, `tasks/sendSubscribe`, `tasks/cancel`) MUST include:

```json
{
  "scale_profile": {
    "profile": "nexus-scale-v1.1",
    "tenant_key": "tenant-123",
    "user_key": "user-456",
    "task_key": "task-abc",
    "shard_key": "sha256:...",
    "region_hint": "us-east-1",
    "write_consistency": "local_quorum",
    "conflict_policy": "reject_on_conflict",
    "expected_version": "etag-or-version-token",
    "features_required": [
      "routing.v1",
      "stream.resume.v1",
      "admission.v1",
      "idempotency.strict.v1"
    ],
    "features_optional": [
      "consistency.vectorclock.v1"
    ]
  }
}
```

### 4.2 Field Semantics

- `tenant_key`: stable tenant namespace key.
- `user_key`: stable user identity key inside tenant namespace.
- `task_key`: globally unique task identity.
- `shard_key`: deterministic partition key for routing. MUST be canonical (see 5.2).
- `region_hint`: preferred execution/read region.
- `write_consistency`: `eventual` | `local_quorum` | `global_quorum`.
- `conflict_policy`: `last_write_wins` | `vector_clock` | `reject_on_conflict`.
- `expected_version`: optimistic concurrency token.

## 5. Mandatory Partition and Routing Contract

### 5.1 Requirements

- Receivers MUST validate presence and non-empty values for `tenant_key`, `task_key`, `shard_key` on mutating methods.
- Receivers MUST validate that `shard_key` is canonical for the routing tuple (`tenant_key`, `user_key`, `task_key`).
- Receivers MUST reject invalid routing contracts with JSON-RPC error `-32602`.
- Routing keys MUST be logged in structured telemetry (hashed/redacted where sensitive).

### 5.2 Error Payload

```json
{
  "code": -32602,
  "message": "Invalid params",
  "data": {
    "failure_domain": "validation",
    "reason": "non_canonical_shard_key",
    "field": "shard_key",
    "expected_shard_key": "sha256:<64-lowercase-hex>"
  }
}
```

### 5.3 Canonical Shard-Key Algorithm

Canonical shard key derivation is deterministic and mandatory:

1. Normalize each routing field by trimming leading/trailing whitespace.
2. Build routing material as UTF-8 bytes of:
   - `tenant_key + U+001F + user_key + U+001F + task_key`
3. Compute `sha256` digest (lowercase hex).
4. Prefix with `sha256:`.

Result format:
- `sha256:<64 lowercase hex characters>`

If format is invalid, reject with `reason = invalid_shard_key_format`.
If value does not match canonical derivation, reject with `reason = non_canonical_shard_key`.

## 6. Stream Sequencing and Resume Cursor Contract

### 6.1 Event Contract

All task stream events MUST include:

```json
{
  "stream": {
    "stream_id": "task_id",
    "stream_epoch": "uuid",
    "seq": 12345,
    "ts_unix_ms": 1770000000000
  }
}
```

Rules:
- `seq` MUST be strictly increasing within a `stream_epoch`.
- `stream_epoch` MUST change if stream state is reset/replayed with non-monotonic sequence.

### 6.2 Resume Cursor

Cursor format:
- Base64url encoded JSON:
  - `stream_id`
  - `stream_epoch`
  - `seq`
  - `exp_unix_ms`
  - `sig`

`tasks/resubscribe` MUST accept:

```json
{
  "cursor": "<base64url-json>",
  "max_catchup_events": 10000
}
```

### 6.3 Resume Behavior

- If cursor is valid and within retention window, server MUST resume from `seq + 1`.
- If cursor is expired or invalid, server MUST return `-32002` with `retryable=false`.
- If requested catch-up exceeds policy, server MUST return `-32004` with `retry_after_ms`.

## 7. Admission Control Contract

### 7.1 Required Error Semantics

On throttling, server MUST return JSON-RPC error `-32004` and include:

```json
{
  "retryable": true,
  "retry_after_ms": 250,
  "failure_domain": "network",
  "rate_limit_scope": "tenant",
  "bucket_id": "tenant-123:tasks/sendSubscribe",
  "limit_rps": 1000.0,
  "observed_rps": 1250.0
}
```

### 7.2 Agent Card Hints

Agent-card MUST expose:
- `x-nexus-backpressure.max_concurrency`
- `x-nexus-backpressure.rate_limit_rps`
- `x-nexus-backpressure.retry_after_ms`

## 8. Strict Idempotency Profile

### 8.1 Mandatory for Mutations

Mutating methods MUST include:

```json
{
  "idempotency": {
    "idempotency_key": "opaque-key",
    "scope": "tenant:task:method",
    "dedup_window_ms": 60000,
    "payload_hash": "sha256:..."
  }
}
```

### 8.2 Required Behavior

- Same `idempotency_key + scope` within dedup window MUST NOT create duplicate side effects.
- If payload hash differs for same key/scope, server MUST return conflict error:
  - `code = -32000`
  - `failure_domain = validation`
  - `reason = idempotency_payload_mismatch`

## 9. Multi-Region Consistency and Conflict Resolution

### 9.1 Version Contract

All mutating responses MUST include:
- `resource_version`
- `region_served`
- `consistency_applied`

### 9.2 Conflict Contract

For concurrency conflicts:
- If `conflict_policy = reject_on_conflict`, server MUST reject with deterministic conflict payload.
- If `conflict_policy = vector_clock`, server MUST return payload shape:

```json
{
  "reason": "conflict",
  "conflict_policy": "vector_clock",
  "expected_version": "rv:expected",
  "current_version": "rv:current",
  "competing_versions": [
    {"version": "rv:expected", "source": "expected"},
    {"version": "rv:current", "source": "current"}
  ],
  "causality": {
    "policy": "vector_clock",
    "resolution": "manual_or_merge_required",
    "winner": null
  }
}
```

`vector_clock` payload contract:
- `expected_version` and `current_version` MUST be non-empty strings.
- `competing_versions` MUST be a list with at least two entries.
- Each `competing_versions[*]` entry MUST include non-empty `version` and `source`.
- `causality.policy` MUST be `vector_clock`.
- `causality.resolution` MUST be one of `manual_or_merge_required`, `winner_selected`, `merge_applied`.
- `causality.winner` MUST be `null` or one of the `competing_versions[*].version` values.

## 10. Version and Capability Negotiation

### 10.1 Agent Card Fields

Agent card MUST expose:

```json
{
  "protocol_versions": ["1.0", "1.1"],
  "scale_profile_versions": ["nexus-scale-v1.1"],
  "feature_flags": [
    "routing.v1",
    "stream.resume.v1",
    "admission.v1",
    "idempotency.strict.v1",
    "consistency.versioning.v1"
  ]
}
```

### 10.2 Negotiation Outcome

Servers MUST:
- accept when all `features_required` are supported
- reject with `-32601` + `unsupported_feature` data when not supported
- echo accepted profile/features in response metadata

## 11. Performance Conformance Profile (Normative)

To claim `nexus-scale-v1.1-ready`, implementation MUST pass the gates below.

### Gate G0 (Contract Integrity)
- Schema and behavior conformance for all new fields.
- Replay/resume correctness on synthetic streams.

### Gate G1 (Regional Scale Unit)
- `>=100k` concurrent sessions profile exercised.
- Admission-control semantics validated under overload.

### Gate G2 (Multi-Region)
- Conflict and version semantics validated across region simulation.
- Resume cursors remain valid across region failover.

### Gate G3 (Cell-Level Stress)
- High fanout stream sequencing and catch-up correctness.
- Idempotency strict profile with duplicate/reordered traffic.

### Gate G4 (Target Readiness Profile)
- Profile includes `2,000,000` concurrency scenarios.
- Strict pass criteria:
  - no protocol contract violations
  - no unclassified error taxonomy
  - deterministic retry semantics

Note:
- These gates are protocol conformance gates. Infrastructure throughput ceilings are evaluated separately.

## 12. Mapping of Identified Gaps to v1.1 Controls

All listed gaps are protocol-implementable:

1. No mandatory partition/shard routing contract.
- Implemented by `params.scale_profile.{tenant_key,user_key,task_key,shard_key}` requirements.

2. No standardized stream sequencing/resume cursor.
- Implemented by `stream_epoch`, monotonic `seq`, and `tasks/resubscribe` cursor contract.

3. No required admission-control behavior contract.
- Implemented by mandatory `-32004` error payload semantics.

4. Idempotency not mandatory/strict for mutations.
- Implemented by strict idempotency profile with payload hash validation.

5. No multi-region consistency/conflict semantics.
- Implemented by `write_consistency`, `conflict_policy`, and versioned response contract.

6. No formal version/capability negotiation profile.
- Implemented by agent-card `protocol_versions`, `scale_profile_versions`, and feature negotiation.

7. No normative performance conformance profile.
- Implemented by mandatory scale conformance gates `G0..G4`.

## 13. Implementation Plan (Repository-Specific)

### Phase P1 - Contract and Schema
- Add v1.1 scale profile schemas and validators in:
  - `src/nexus_a2a_protocol/jsonrpc.py`
  - `shared/nexus_common/protocol.py`
  - `shared/nexus_common/jsonrpc.py`
- Add agent-card schema extensions and validation.

Deliverables:
- strict parameter validation for `scale_profile`
- deterministic error payloads for unsupported features

### Phase P2 - Runtime Behavior
- Add strict idempotency checks in common runtime:
  - `shared/nexus_common/idempotency.py`
- Add stream sequencing/cursor generation and validation:
  - `shared/nexus_common/sse.py`
- Add admission-control error helpers:
  - `shared/nexus_common/health.py`
  - `shared/nexus_common/jsonrpc.py`

Deliverables:
- monotonic sequence contract
- resumable stream cursor contract
- strict throttling response semantics

### Phase P3 - Multi-Region and Negotiation Semantics
- Add capability negotiation hooks in request handlers across agents.
- Add consistency and conflict metadata to mutating responses.

Deliverables:
- profile/feature acceptance-rejection behavior
- conflict-resolution response structures

### Phase P4 - Conformance Gates
- Add/expand matrix and tests:
  - `nexus-a2a/artefacts/matrices/nexus_protocol_scale_profile_v1_1_matrix.json`
  - `tests/test_nexus_protocol_contracts.py`
  - `tests/nexus_harness/*` gate-specific assertions

Deliverables:
- protocol-only conformance test suite for G0-G4
- integration harness checks for negotiation and strict idempotency

### Phase P5 - Certification Workflow
- Extend orchestrator:
  - `tools/run_target_architecture_validation.py`
- Enforce strict fail for gate failures (already aligned).

Deliverables:
- reproducible report with per-gate pass/fail and protocol violation summaries

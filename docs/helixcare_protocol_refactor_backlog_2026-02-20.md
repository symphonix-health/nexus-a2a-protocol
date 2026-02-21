# HelixCare Protocol Refactor Backlog (2026-02-20)

## Scope

Concrete protocol/runtime improvements for the current `nexus-a2a-protocol` repository with acceptance criteria that can be verified in a single test run.

## Priority Legend

- `P0`: correctness/compliance gaps that affect protocol guarantees
- `P1`: conformance confidence and quality gates

## Tickets

### `P0-001` Implement runtime support for `tasks/resubscribe`

- Problem:
  Runtime validators accept `tasks/resubscribe`, but demo runtimes do not implement method handlers.
- Files:
  - `shared/nexus_common/sse.py`
  - `shared/nexus_common/generic_demo_agent.py`
  - `demos/ed-triage/triage-agent/app/main.py`
- Acceptance Criteria:
  1. `tasks/resubscribe` is callable over `/rpc` on generic demo agents and triage agent.
  2. Runtime can replay events after a valid signed cursor.
  3. Invalid or out-of-stream cursor returns a structured JSON-RPC error (not crash/500).
  4. Regression tests cover cursor replay path.
- Verification:
  - `tests/test_generic_demo_agent_runtime.py`

### `P0-002` Enforce active idempotency behavior in generic runtime

- Problem:
  Generic runtime forwards idempotency metadata but does not perform deduplication.
- Files:
  - `shared/nexus_common/generic_demo_agent.py`
- Acceptance Criteria:
  1. Repeated `tasks/send` or `tasks/sendSubscribe` with same key/scope returns duplicate metadata.
  2. Cached response is reused for duplicate requests.
  3. Payload-hash mismatch is surfaced in duplicate metadata.
  4. Works with existing memory backend and optional Redis backend pattern.
- Verification:
  - `tests/test_generic_demo_agent_runtime.py`

### `P0-003` Normalize agent-card consistency for public-health agents

- Problem:
  Public-health cards are schema-inconsistent and generic app path lookup can miss card files.
- Files:
  - `shared/nexus_common/generic_demo_agent.py`
  - `demos/public-health-surveillance/central-surveillance/agent_card.json`
  - `demos/public-health-surveillance/hospital-reporter/agent_card.json`
  - `demos/public-health-surveillance/osint-agent/agent_card.json`
- Acceptance Criteria:
  1. Generic runtime can load card from app dir and one-level parent fallback.
  2. Public-health cards include protocol fields and declared methods.
  3. Card contract test validates required keys for all demo cards.
- Verification:
  - `tests/test_protocol_backlog_completeness.py`

### `P1-001` Remove hardcoded `[:10]` matrix slicing in harness tests

- Problem:
  Conformance suites silently run tiny samples and overstate coverage.
- Files:
  - `tests/nexus_harness/test_protocol_core.py`
  - `tests/nexus_harness/test_protocol_streaming.py`
  - `tests/nexus_harness/test_protocol_multitransport.py`
  - `tests/nexus_harness/test_ed_triage.py`
  - `tests/nexus_harness/test_telemed_scribe.py`
  - `tests/nexus_harness/test_consent_verification.py`
  - `tests/nexus_harness/test_public_health_surveillance.py`
- Acceptance Criteria:
  1. No harness test uses `[:10]` scenario slicing.
  2. Static guard test prevents reintroduction.
- Verification:
  - `tests/test_protocol_backlog_completeness.py`

## Delivery Plan

1. Implement all `P0` tickets.
2. Implement `P1-001`.
3. Add acceptance-criteria tests.
4. Run one-shot verification command.
5. Publish completion status per ticket.


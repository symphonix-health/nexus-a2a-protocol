# Hybrid Profiles Implementation (Standards-Neutral Nexus Core)

This document captures the concrete implementation scaffolding for a hybrid-profiles
interoperability layer on top of Nexus A2A.

## Delivered artifacts

- Contracts and registry logic:
  - `src/nexus_a2a_protocol/interop/contracts.py`
  - `src/nexus_a2a_protocol/interop/profile_registry.py`
- JSON schemas:
  - `src/nexus_a2a_protocol/schemas/nexus-envelope.schema.json`
  - `src/nexus_a2a_protocol/schemas/nexus-artifact-part.schema.json`
  - `src/nexus_a2a_protocol/schemas/nexus-problem.schema.json`
  - `src/nexus_a2a_protocol/schemas/profile-registry-entry.schema.json`
- Adapter helper primitives:
  - `shared/nexus_common/interop_healthcare.py`
- Agent runtime stubs:
  - `demos/interop/...`
- Conformance harness scaffold + fixtures:
  - `tests/conformance/...`

## Operational boundaries

- Nexus core remains standards-neutral.
- Healthcare-specific semantics are delegated to profile adapters.
- Profile discovery and version selection are deterministic.
- Audit and security expectations are captured in config and test scaffolding.

## CI conformance scope

Protocol-level checks:
- discovery/profile drift
- task lifecycle compatibility
- idempotency/replay behavior
- auth failure and scope enforcement

Domain-level checks:
- minimal FHIR structural validation
- X12 structural markers + transaction classification
- NCPDP required field validation
- mapping smoke checks through canonical event templates

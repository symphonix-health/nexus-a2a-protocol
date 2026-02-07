# Nexus A2A Protocol Research Notes (2026-02-07)

These notes document the initial protocol direction used for this repository's SDK and PoC.

## Primary References

- Google A2A project site: https://google-a2a.github.io/A2A/
- A2A Python README (official repo): https://github.com/google/A2A/blob/main/samples/python/README.md
- A2A specification: https://google-a2a.github.io/A2A/specification/

## Key Findings

- The reference protocol uses JSON-RPC 2.0 request/response envelopes for cross-agent operations.
- Task-oriented methods include `tasks/send`, `tasks/get`, and stream/subscribe variants.
- Messages are multi-part objects with role + parts, and task lifecycles include states such as
  `submitted`, `working`, `input-required`, and `completed`.
- The A2A documents position the protocol as transport-level agent interoperability. MCP is
  discussed as complementary for tool/resource access.

## Initial Repository Decisions

- Model the SDK around validated Message/Task structures with explicit task state transitions.
- Include JSON-RPC helper utilities rather than a network transport first.
- Provide an in-memory PoC transport so protocol behavior is testable before adding HTTP/SSE.
- Keep the implementation dependency-light for easier iteration while protocol details evolve.

## Open Questions for Next Iteration

- Should Nexus-specific capabilities be namespaced (for example `nexus/*`) alongside base A2A?
- Should we add strict schema version negotiation in Agent Cards from day one?
- Which transport should be prioritized first after PoC: HTTP polling, SSE, or WebSocket?

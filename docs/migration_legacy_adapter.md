# Legacy MCP Adapter Migration

## Current State

`shared/nexus_common/mcp_adapter.py` now acts as a compatibility shim that delegates to `nexus_a2a_protocol.sdk`.

Existing imports continue to work, but a `DeprecationWarning` is emitted.

## Shim Scope

Still supported:

- `load_agent_registry`
- `resolve_agent_url`
- `resolve_jwt_token`
- `fetch_agent_card`
- `probe_agent_health`
- `nexus_rpc_call`
- `parse_sse_chunk`
- `consume_sse_stream`
- `map_nexus_event_to_progress`

## Migration Steps

1. Replace imports:

```python
# before
from shared.nexus_common import mcp_adapter

# after
from nexus_a2a_protocol.sdk import (
    load_agent_registry,
    resolve_agent_url,
    resolve_jwt_token,
    fetch_agent_card,
    probe_agent_health,
    nexus_rpc_call,
    parse_sse_chunk,
    consume_sse_stream,
    map_nexus_event_to_progress,
)
```

2. Use SDK transports for new orchestration/test code.
3. Keep legacy shim only for backward compatibility windows.

## Deprecation Timeline

- Phase 1 (now): shim active, warning emitted, behavior parity verified.
- Phase 2: callers migrated to SDK import path.
- Phase 3: shim removed in a major release.

## Removal Criteria

- No repo code imports `shared.nexus_common.mcp_adapter`.
- BulletTrain integration uses `nexus_a2a_protocol` SDK APIs only.
- CI no longer depends on legacy shim tests.

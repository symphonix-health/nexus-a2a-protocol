"""Compatibility shim for legacy MCP adapter imports.

This module remains stable for existing callers, but delegates to the
installable SDK transport/client implementation in ``nexus_a2a_protocol.sdk``.
"""

from __future__ import annotations

import sys
import warnings
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


try:
    from nexus_a2a_protocol.sdk import (
        AgentInfo,
        TransportError,
        consume_sse_stream as _sdk_consume_sse_stream,
        fetch_agent_card as _sdk_fetch_agent_card,
        load_agent_registry as _sdk_load_agent_registry,
        map_nexus_event_to_progress as _sdk_map_nexus_event_to_progress,
        make_task_event,
        nexus_rpc_call as _sdk_nexus_rpc_call,
        parse_sse_chunk as _sdk_parse_sse_chunk,
        probe_agent_health as _sdk_probe_agent_health,
        resolve_agent_url as _sdk_resolve_agent_url,
        resolve_jwt_token as _sdk_resolve_jwt_token,
    )
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    src_dir = str(repo_root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from nexus_a2a_protocol.sdk import (  # type: ignore[no-redef]
        AgentInfo,
        TransportError,
        consume_sse_stream as _sdk_consume_sse_stream,
        fetch_agent_card as _sdk_fetch_agent_card,
        load_agent_registry as _sdk_load_agent_registry,
        map_nexus_event_to_progress as _sdk_map_nexus_event_to_progress,
        make_task_event,
        nexus_rpc_call as _sdk_nexus_rpc_call,
        parse_sse_chunk as _sdk_parse_sse_chunk,
        probe_agent_health as _sdk_probe_agent_health,
        resolve_agent_url as _sdk_resolve_agent_url,
        resolve_jwt_token as _sdk_resolve_jwt_token,
    )

_DEPRECATION_MESSAGE = (
    "shared.nexus_common.mcp_adapter is deprecated and will be removed in a future release. "
    "Use nexus_a2a_protocol.sdk instead."
)
_WARNED = False


def _warn_deprecated() -> None:
    global _WARNED
    if _WARNED:
        return
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    _WARNED = True


@dataclass(slots=True)
class SseEvent:
    """Legacy SSE event shape preserved for compatibility."""

    event: str = ""
    data: Any = None
    seq: int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.event in ("nexus.task.final", "nexus.task.error")


@dataclass(slots=True)
class McpProgressUpdate:
    """Legacy progress update shape preserved for compatibility."""

    progress: int
    total: int = 100
    description: str = ""



def load_agent_registry(config_path: str | None = None) -> dict[str, AgentInfo]:
    _warn_deprecated()
    return _sdk_load_agent_registry(config_path)



def resolve_agent_url(alias_or_url: str, registry: dict[str, AgentInfo]) -> str:
    _warn_deprecated()
    return _sdk_resolve_agent_url(alias_or_url, registry)



def resolve_jwt_token(
    *,
    token_env: str = "NEXUS_JWT_TOKEN",
    secret_env: str = "NEXUS_JWT_SECRET",
    subject_env: str = "NEXUS_JWT_SUBJECT",
    scope_env: str = "NEXUS_JWT_SCOPE",
) -> str:
    _warn_deprecated()
    return _sdk_resolve_jwt_token(
        token_env=token_env,
        secret_env=secret_env,
        subject_env=subject_env,
        scope_env=scope_env,
    )


async def fetch_agent_card(base_url: str, token: str, *, timeout: float = 10.0) -> dict[str, Any]:
    _warn_deprecated()
    return await _sdk_fetch_agent_card(base_url, token, timeout=timeout)


async def probe_agent_health(base_url: str, token: str, *, timeout: float = 5.0) -> dict[str, Any]:
    _warn_deprecated()
    return await _sdk_probe_agent_health(base_url, token, timeout=timeout)


async def nexus_rpc_call(
    base_url: str,
    method: str,
    params: dict[str, Any],
    token: str,
    *,
    request_id: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    _warn_deprecated()
    try:
        return await _sdk_nexus_rpc_call(
            base_url,
            method,
            params,
            token,
            request_id=request_id or "legacy-mcp-adapter",
            timeout=timeout,
        )
    except TransportError:
        raise



def parse_sse_chunk(chunk: str) -> SseEvent | None:
    _warn_deprecated()
    evt = _sdk_parse_sse_chunk(chunk)
    if evt is None:
        return None
    return SseEvent(event=evt.type, data=evt.payload, seq=evt.seq)


async def consume_sse_stream(
    base_url: str,
    task_id: str,
    token: str,
    *,
    timeout: float = 120.0,
) -> AsyncIterator[SseEvent]:
    _warn_deprecated()
    async for evt in _sdk_consume_sse_stream(base_url, task_id, token, timeout=timeout):
        yield SseEvent(event=evt.type, data=evt.payload, seq=evt.seq)



def map_nexus_event_to_progress(evt: SseEvent, current_progress: int = 0) -> McpProgressUpdate:
    _warn_deprecated()
    sdk_evt = make_task_event(
        event_type=evt.event,
        payload=evt.data,
        seq=evt.seq,
    )
    update = _sdk_map_nexus_event_to_progress(sdk_evt, current_progress)
    return McpProgressUpdate(
        progress=update.progress,
        total=update.total,
        description=update.description,
    )

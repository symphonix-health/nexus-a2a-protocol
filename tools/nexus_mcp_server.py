#!/usr/bin/env python3
"""NEXUS-A2A MCP Server.

Exposes NEXUS agent-mesh capabilities as MCP tools so that any MCP host
(VS Code Copilot, Claude Desktop, etc.) can discover agents, invoke
JSON-RPC methods, and stream task progress through a single facade.

Usage (STDIO transport — default for local pairing):
    python tools/nexus_mcp_server.py

Environment:
    NEXUS_JWT_TOKEN     Pre-minted bearer token (mode A).
    NEXUS_JWT_SECRET    HS256 secret to mint a token on startup (mode B).
    NEXUS_JWT_SUBJECT   JWT subject claim (default: mcp-server).
    NEXUS_JWT_SCOPE     JWT scope claim  (default: nexus:invoke).
    AGENT_URLS          Comma-separated agent base URLs (overrides config).
    NEXUS_AGENTS_CONFIG Path to agents.json (default: auto-discover).
"""

from __future__ import annotations

import json
import logging
import sys

# ── Logging to stderr only (STDIO transport reserves stdout) ──────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("nexus-mcp")

# Ensure no handler writes to stdout
for h in logging.root.handlers:
    if getattr(h, "stream", None) is sys.stdout:
        h.stream = sys.stderr

# ── Imports (after logging setup) ─────────────────────────────────────
import os  # noqa: E402
import uuid  # noqa: E402
from typing import Any  # noqa: E402

# Add shared/ and src/ to path for repo-root invocation
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _d in ("shared", "src"):
    _p = os.path.join(_repo_root, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    logger.error(
        "MCP SDK not installed. Run:  pip install 'mcp[cli]>=1.0.0'\n"
        "Or install with the optional extra:  pip install -e '.[mcp]'"
    )
    sys.exit(1)

from nexus_common.mcp_adapter import (  # noqa: E402
    AgentInfo,
    consume_sse_stream,
    fetch_agent_card,
    load_agent_registry,
    nexus_rpc_call,
    probe_agent_health,
    resolve_agent_url,
    resolve_jwt_token,
)

# ── Server setup ──────────────────────────────────────────────────────
mcp = FastMCP(
    "nexus-a2a-mcp",
    instructions=(
        "NEXUS-A2A MCP Server — a thin facade over a mesh of healthcare "
        "AI agents. Use 'nexus_list_agents' to discover available agents, "
        "'nexus_get_agent_card' to inspect capabilities, 'nexus_call_rpc' "
        "for generic JSON-RPC calls, 'nexus_send_task' for task invocation, "
        "and 'nexus_stream_task_events' to follow SSE progress."
    ),
)

# ── Lazy-init globals ────────────────────────────────────────────────
_registry: dict[str, AgentInfo] | None = None
_default_token: str | None = None


def _get_registry() -> dict[str, AgentInfo]:
    global _registry
    if _registry is None:
        config_path = os.getenv("NEXUS_AGENTS_CONFIG")
        _registry = load_agent_registry(config_path)
    return _registry


def _get_token(override: str | None = None) -> str:
    if override:
        return override
    global _default_token
    if _default_token is None:
        _default_token = resolve_jwt_token()
    return _default_token


# ═══════════════════════════════════════════════════════════════════════
# Tools
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
async def nexus_list_agents(
    include_status: bool = False,
) -> str:
    """List all registered NEXUS agents.

    Args:
        include_status: When true, probe each agent's /health endpoint
            and include live status in the response.

    Returns:
        JSON array of agent objects with alias, port, url, description,
        and category.  If include_status is true, adds a 'health' field.
    """
    registry = _get_registry()
    token = _get_token()
    agents: list[dict[str, Any]] = []

    for info in registry.values():
        entry = info.to_dict()
        if include_status:
            health = await probe_agent_health(info.url, token)
            entry["health"] = health
        agents.append(entry)

    return json.dumps(agents, indent=2)


@mcp.tool()
async def nexus_get_agent_card(
    agent: str,
) -> str:
    """Fetch the agent card for a NEXUS agent.

    Args:
        agent: Agent alias (e.g. 'triage_agent') or full base URL.

    Returns:
        The agent-card JSON document from /.well-known/agent-card.json.
    """
    registry = _get_registry()
    token = _get_token()

    try:
        url = resolve_agent_url(agent, registry)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    try:
        card = await fetch_agent_card(url, token)
        return json.dumps(card, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Failed to fetch agent card: {exc}"})


@mcp.tool()
async def nexus_call_rpc(
    agent: str,
    method: str,
    params: str = "{}",
    token: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Call any JSON-RPC method on a NEXUS agent.

    Args:
        agent: Agent alias or full base URL.
        method: JSON-RPC method name (e.g. 'tasks/send').
        params: JSON object string of method parameters.
        token: Optional bearer token override.
        idempotency_key: Optional idempotency key for the request.

    Returns:
        The raw JSON-RPC response (result or error envelope).
    """
    registry = _get_registry()
    effective_token = _get_token(token)

    try:
        url = resolve_agent_url(agent, registry)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    try:
        parsed_params = json.loads(params) if isinstance(params, str) else params
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON params: {exc}"})

    if idempotency_key:
        parsed_params.setdefault("idempotency", {})["idempotency_key"] = idempotency_key

    try:
        result = await nexus_rpc_call(url, method, parsed_params, effective_token)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"RPC call failed: {exc}"})


@mcp.tool()
async def nexus_send_task(
    agent: str,
    message: str,
    task_id: str | None = None,
    session_id: str | None = None,
    subscribe: bool = False,
    correlation_trace_id: str | None = None,
    token: str | None = None,
) -> str:
    """Send a task to a NEXUS agent (convenience wrapper for tasks/send).

    Constructs a proper NEXUS task envelope with a user message and
    calls the agent's /rpc endpoint.

    Args:
        agent: Agent alias or full base URL.
        message: The user message text to send.
        task_id: Optional task ID (generated if not supplied).
        session_id: Optional session ID (generated if not supplied).
        subscribe: If true, uses tasks/sendSubscribe instead of tasks/send.
        correlation_trace_id: Optional trace ID for correlation.
        token: Optional bearer token override.

    Returns:
        JSON-RPC response from the agent.
    """
    registry = _get_registry()
    effective_token = _get_token(token)

    try:
        url = resolve_agent_url(agent, registry)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    tid = task_id or str(uuid.uuid4())
    sid = session_id or str(uuid.uuid4())

    params: dict[str, Any] = {
        "task_id": tid,
        "session_id": sid,
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": message}],
        },
    }

    if correlation_trace_id:
        params["correlation"] = {
            "trace_id": correlation_trace_id,
            "parent_task_id": tid,
        }

    method = "tasks/sendSubscribe" if subscribe else "tasks/send"

    try:
        result = await nexus_rpc_call(url, method, params, effective_token)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Task send failed: {exc}"})


@mcp.tool()
async def nexus_stream_task_events(
    agent: str,
    task_id: str,
    token: str | None = None,
) -> str:
    """Stream SSE events for a running NEXUS task.

    Connects to the agent's /events/{task_id} SSE endpoint and
    collects events until a terminal event (nexus.task.final or
    nexus.task.error) is received.

    Args:
        agent: Agent alias or full base URL.
        task_id: The task ID to stream events for.
        token: Optional bearer token override.

    Returns:
        JSON array of all events received, with the final/error
        event last. Each event has 'event', 'data', and 'seq' fields.
    """
    registry = _get_registry()
    effective_token = _get_token(token)

    try:
        url = resolve_agent_url(agent, registry)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    events: list[dict[str, Any]] = []
    try:
        async for evt in consume_sse_stream(url, task_id, effective_token):
            events.append(
                {
                    "event": evt.event,
                    "data": evt.data,
                    "seq": evt.seq,
                }
            )
    except Exception as exc:
        events.append({"error": f"Stream error: {exc}"})

    return json.dumps(events, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# Resources (optional topology view)
# ═══════════════════════════════════════════════════════════════════════


@mcp.resource("nexus://topology")
async def get_topology() -> str:
    """Full agent topology from config/agents.json."""
    registry = _get_registry()
    agents = [info.to_dict() for info in registry.values()]
    return json.dumps({"agents": agents, "count": len(agents)}, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("Starting NEXUS-A2A MCP Server (STDIO transport)")
    registry = _get_registry()
    logger.info("Agent registry loaded: %d agents", len(registry))
    mcp.run(transport="stdio")

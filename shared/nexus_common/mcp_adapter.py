"""MCP adapter layer for NEXUS-A2A protocol.

Provides agent registry loading, URL resolution, health probing,
agent-card fetching, JSON-RPC calling, and SSE-to-MCP-progress bridging.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .auth import mint_jwt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent registry data model
# ---------------------------------------------------------------------------


@dataclass
class AgentInfo:
    """Metadata for a single NEXUS agent resolved from config/agents.json."""

    alias: str
    port: int
    url: str
    description: str = ""
    category: str = ""
    path: str = ""
    rpc_env: str = ""
    env: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v}


# ---------------------------------------------------------------------------
# Config loading (mirrors shared/command-centre/app/main.py resolution)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_RELATIVE = Path("config") / "agents.json"


def _find_config_path(config_path: str | None = None) -> Path | None:
    """Locate agents.json, searching upward from this file if needed."""
    if config_path:
        p = Path(config_path)
        return p if p.is_file() else None

    # Walk up from this module to repo root looking for config/agents.json
    anchor = Path(__file__).resolve()
    for parent in (anchor.parent, *anchor.parents):
        candidate = parent / _DEFAULT_CONFIG_RELATIVE
        if candidate.is_file():
            return candidate
    return None


def load_agent_registry(
    config_path: str | None = None,
) -> dict[str, AgentInfo]:
    """Load the agent registry as a flat alias → AgentInfo map.

    Resolution order:
    1. ``AGENT_URLS`` env var (comma-separated ``http://host:port`` entries).
       Aliases are synthesised as ``agent_<port>``.
    2. ``config/agents.json`` file (auto-discovered or explicit path).
    3. Empty dict if neither source is available.
    """
    # --- Mode 1: env-var based ---
    env_urls = os.getenv("AGENT_URLS", "").strip()
    if env_urls:
        registry: dict[str, AgentInfo] = {}
        for raw in env_urls.split(","):
            url = raw.strip()
            if not url:
                continue
            # Derive a synthetic alias from the port
            try:
                port = int(url.rsplit(":", 1)[-1].rstrip("/"))
            except (ValueError, IndexError):
                port = 0
            alias = f"agent_{port}" if port else url
            registry[alias] = AgentInfo(alias=alias, port=port, url=url)
        if registry:
            logger.info("Loaded %d agents from AGENT_URLS env", len(registry))
            return registry

    # --- Mode 2: config file ---
    cfg_path = _find_config_path(config_path)
    if cfg_path is None:
        logger.warning("No agent config found (AGENT_URLS unset, agents.json not found)")
        return {}

    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read %s: %s", cfg_path, exc)
        return {}

    agents_by_group = raw.get("agents", {})
    if not isinstance(agents_by_group, dict):
        return {}

    registry = {}
    for category, group in agents_by_group.items():
        if not isinstance(group, dict):
            continue
        for alias, info in group.items():
            if not isinstance(info, dict):
                continue
            port = info.get("port")
            if not isinstance(port, int) or port <= 0:
                continue
            registry[alias] = AgentInfo(
                alias=alias,
                port=port,
                url=f"http://localhost:{port}",
                description=info.get("description", ""),
                category=category,
                path=info.get("path", ""),
                rpc_env=info.get("rpc_env", ""),
                env=info.get("env", ""),
            )

    logger.info("Loaded %d agents from %s", len(registry), cfg_path)
    return registry


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


def resolve_agent_url(alias_or_url: str, registry: dict[str, AgentInfo]) -> str:
    """Resolve an agent alias to its base URL, or pass through a raw URL.

    Raises ``ValueError`` for unknown aliases.
    """
    if alias_or_url.startswith("http://") or alias_or_url.startswith("https://"):
        return alias_or_url.rstrip("/")

    info = registry.get(alias_or_url)
    if info is None:
        available = ", ".join(sorted(registry.keys())) if registry else "(none)"
        raise ValueError(f"Unknown agent alias {alias_or_url!r}. Available: {available}")
    return info.url


# ---------------------------------------------------------------------------
# JWT / auth bootstrap
# ---------------------------------------------------------------------------

_DEFAULT_SECRET = "dev-secret-change-me"


def resolve_jwt_token(
    *,
    token_env: str = "NEXUS_JWT_TOKEN",
    secret_env: str = "NEXUS_JWT_SECRET",
    subject_env: str = "NEXUS_JWT_SUBJECT",
    scope_env: str = "NEXUS_JWT_SCOPE",
) -> str:
    """Resolve a bearer JWT for outbound NEXUS calls.

    Priority:
    A) ``NEXUS_JWT_TOKEN`` env → use directly.
    B) ``NEXUS_JWT_SECRET`` env → mint with configurable subject/scope.
    C) Fall back to ``dev-secret-change-me`` default (warning logged).
    """
    existing = os.getenv(token_env, "").strip()
    if existing:
        logger.debug("Using pre-existing JWT from %s", token_env)
        return existing

    secret = os.getenv(secret_env, "").strip()
    if not secret:
        logger.warning(
            "%s not set — falling back to default dev secret. Set %s or %s for production use.",
            secret_env,
            secret_env,
            token_env,
        )
        secret = _DEFAULT_SECRET

    subject = os.getenv(subject_env, "mcp-server").strip()
    scope = os.getenv(scope_env, "nexus:invoke").strip()
    return mint_jwt(subject, secret, ttl_seconds=86400, scope=scope)


# ---------------------------------------------------------------------------
# HTTP helpers (agent card, health)
# ---------------------------------------------------------------------------


async def fetch_agent_card(base_url: str, token: str, *, timeout: float = 10.0) -> dict[str, Any]:
    """GET /.well-known/agent-card.json from an agent."""
    url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


async def probe_agent_health(base_url: str, token: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """GET /health from an agent.  Returns the JSON body or an error dict."""
    url = f"{base_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc)}


# ---------------------------------------------------------------------------
# NEXUS JSON-RPC calling
# ---------------------------------------------------------------------------


async def nexus_rpc_call(
    base_url: str,
    method: str,
    params: dict[str, Any],
    token: str,
    *,
    request_id: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Call a NEXUS agent's /rpc endpoint with a JSON-RPC 2.0 envelope.

    Returns the full JSON-RPC response dict (``result`` or ``error``).
    """
    rpc_url = f"{base_url.rstrip('/')}/rpc"
    rid = request_id or str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "id": rid,
        "method": method,
        "params": params,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(rpc_url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# SSE event parsing
# ---------------------------------------------------------------------------


@dataclass
class SseEvent:
    """Parsed SSE event from a NEXUS agent stream."""

    event: str = ""
    data: Any = field(default_factory=dict)
    seq: int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.event in ("nexus.task.final", "nexus.task.error")


def parse_sse_chunk(chunk: str) -> SseEvent | None:
    """Parse a single SSE frame (``id:…\\nevent:…\\ndata:…\\n\\n``) into an SseEvent."""
    event_name = ""
    data_lines: list[str] = []
    seq: int | None = None

    for line in chunk.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        elif line.startswith("id:"):
            raw_id = line[len("id:") :].strip()
            try:
                seq = int(raw_id)
            except ValueError:
                pass

    if not event_name and not data_lines:
        return None

    raw_data = "\n".join(data_lines)
    try:
        parsed_data = json.loads(raw_data)
    except (json.JSONDecodeError, ValueError):
        parsed_data = raw_data

    return SseEvent(event=event_name, data=parsed_data, seq=seq)


async def consume_sse_stream(
    base_url: str,
    task_id: str,
    token: str,
    *,
    timeout: float = 120.0,
) -> AsyncIterator[SseEvent]:
    """Connect to GET /events/{task_id} and yield SseEvents until terminal."""
    url = f"{base_url.rstrip('/')}/events/{task_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            buffer = ""
            async for text in response.aiter_text():
                buffer += text
                # SSE frames are delimited by double newlines
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    evt = parse_sse_chunk(frame)
                    if evt is not None:
                        yield evt
                        if evt.is_terminal:
                            return


# ---------------------------------------------------------------------------
# NEXUS → MCP progress mapping
# ---------------------------------------------------------------------------


@dataclass
class McpProgressUpdate:
    """Intermediate representation of an MCP progress notification."""

    progress: int
    total: int = 100
    description: str = ""


def map_nexus_event_to_progress(evt: SseEvent, current_progress: int = 0) -> McpProgressUpdate:
    """Map a NEXUS SSE event to an MCP progress update.

    Guarantees monotonically increasing progress values.
    """
    data = evt.data if isinstance(evt.data, dict) else {}

    if evt.event == "nexus.task.final":
        return McpProgressUpdate(progress=100, description="Task completed")

    if evt.event == "nexus.task.error":
        return McpProgressUpdate(
            progress=max(current_progress, 99),
            description="Task error",
        )

    # nexus.task.status — extract state and optional percent
    status = data.get("status", data)
    if isinstance(status, dict):
        state = status.get("state", "")
        percent = status.get("percent")
    else:
        state = str(status)
        percent = None

    if state == "accepted":
        new = max(current_progress, 0)
        return McpProgressUpdate(progress=new, description="Task accepted")

    if state == "working":
        if percent is not None:
            new = max(current_progress + 1, int(percent))
        else:
            # Increment by 1 to ensure monotonicity
            new = max(current_progress + 1, 10)
        return McpProgressUpdate(progress=min(new, 99), description="Task working")

    # Unknown state — small bump
    return McpProgressUpdate(
        progress=min(current_progress + 1, 99),
        description=f"Event: {evt.event}",
    )

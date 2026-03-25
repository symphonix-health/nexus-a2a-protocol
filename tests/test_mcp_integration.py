"""Integration tests for the MCP adapter layer.

These tests use a mock NEXUS agent built with FastAPI and tested
in-process via httpx.ASGITransport (no real server needed), following
the same pattern used in tests/test_trace_api.py.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# This file tests functionality via the deprecated mcp_adapter shim.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# Ensure shared/ and src/ are importable
REPO_ROOT = Path(__file__).resolve().parents[1]
for sub in ("shared", "src"):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from nexus_common.mcp_adapter import (  # noqa: E402
    AgentInfo,
    map_nexus_event_to_progress,
    parse_sse_chunk,
    probe_agent_health,
)

# ── Mock NEXUS Agent ──────────────────────────────────────────────────

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")


def _build_mock_agent() -> FastAPI:
    """Build a minimal NEXUS-compatible FastAPI agent for testing."""
    app = FastAPI(title="mock-agent")

    AGENT_CARD = {
        "agent_id": "did:nexus:mock-agent",
        "name": "Mock Test Agent",
        "protocol_version": "1.0",
        "endpoint": "http://localhost:9999",
        "capabilities": ["tasks/send", "tasks/sendSubscribe"],
    }

    @app.get("/.well-known/agent-card.json")
    async def agent_card():
        return JSONResponse(content=AGENT_CARD)

    @app.get("/health")
    async def health():
        return JSONResponse(content={"status": "healthy", "agent": "mock-agent"})

    @app.post("/rpc")
    async def rpc(request: Request):
        body = await request.json()
        method = body.get("method", "")
        params = body.get("params", {})
        rid = body.get("id", "1")

        if method in ("tasks/send", "tasks/sendSubscribe"):
            task_id = params.get("task_id", str(uuid.uuid4()))
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "task_id": task_id,
                        "status": {"state": "completed"},
                        "artifacts": [
                            {
                                "type": "text",
                                "text": "Mock result for testing",
                            }
                        ],
                    },
                }
            )

        if method == "tasks/get":
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "task_id": params.get("task_id", "unknown"),
                        "status": {"state": "completed"},
                    },
                }
            )

        # Unknown method
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": rid,
                "error": {
                    "code": -32601,
                    "message": "Method not found",
                    "data": {"method": method, "retryable": False},
                },
            }
        )

    @app.get("/events/{task_id}")
    async def events(task_id: str):
        async def generate():
            yield ('id: 1\nevent: nexus.task.status\ndata: {"status":{"state":"accepted"}}\n\n')
            yield (
                "id: 2\nevent: nexus.task.status\n"
                'data: {"status":{"state":"working","percent":50}}\n\n'
            )
            yield (
                f"id: 3\nevent: nexus.task.final\n"
                f'data: {{"task_id":"{task_id}","result":"done"}}\n\n'
            )

        return StreamingResponse(generate(), media_type="text/event-stream")

    return app


if HAS_FASTAPI:
    mock_app = _build_mock_agent()
    MOCK_BASE = "http://mock-agent"
    MOCK_TOKEN = "test-token-for-integration"


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def mock_registry() -> dict[str, AgentInfo]:
    return {
        "mock_agent": AgentInfo(
            alias="mock_agent",
            port=9999,
            url=MOCK_BASE,
            description="Mock agent for testing",
            category="test",
        ),
    }


@pytest.fixture()
async def client():
    transport = ASGITransport(app=mock_app)
    async with AsyncClient(transport=transport, base_url=MOCK_BASE) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════
# I1: Live health probing
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_probe_health_live(client: AsyncClient):
    """I1: Mock agent health endpoint returns healthy status."""
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"


# ═══════════════════════════════════════════════════════════════════════
# I2: Agent card retrieval
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_fetch_agent_card_live(client: AsyncClient):
    """I2: Agent card contains expected fields."""
    r = await client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    card = r.json()
    assert "agent_id" in card
    assert "capabilities" in card
    assert "tasks/send" in card["capabilities"]


# ═══════════════════════════════════════════════════════════════════════
# I3: RPC tasks/send
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rpc_tasks_send(client: AsyncClient):
    """I3: tasks/send returns a JSON-RPC result with task_id."""
    payload = {
        "jsonrpc": "2.0",
        "id": "test-1",
        "method": "tasks/send",
        "params": {
            "task_id": "t-001",
            "session_id": "s-001",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Patient: fever"}],
            },
        },
    }
    r = await client.post("/rpc", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert data["result"]["task_id"] == "t-001"


# ═══════════════════════════════════════════════════════════════════════
# I4: RPC error propagation
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rpc_error_propagation(client: AsyncClient):
    """I4: Unknown method returns JSON-RPC error with correct code."""
    payload = {
        "jsonrpc": "2.0",
        "id": "test-err",
        "method": "unknown/method",
        "params": {},
    }
    r = await client.post("/rpc", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32601


# ═══════════════════════════════════════════════════════════════════════
# I5: SSE streaming lifecycle
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_stream_lifecycle(client: AsyncClient):
    """I5: SSE events stream from accepted → working → final."""
    r = await client.get("/events/task-123")
    assert r.status_code == 200

    body = r.text
    chunks = [c.strip() for c in body.split("\n\n") if c.strip()]

    assert len(chunks) >= 3

    # Parse each chunk
    events = [parse_sse_chunk(c) for c in chunks]
    events = [e for e in events if e is not None]

    assert events[0].event == "nexus.task.status"
    assert events[-1].event == "nexus.task.final"
    assert events[-1].is_terminal


# ═══════════════════════════════════════════════════════════════════════
# I6: Progress mapping over full stream
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_progress_mapping_over_stream(client: AsyncClient):
    """I6: Mapping a full SSE stream produces monotonic MCP progress."""
    r = await client.get("/events/task-progress")
    body = r.text
    chunks = [c.strip() for c in body.split("\n\n") if c.strip()]
    events = [parse_sse_chunk(c) for c in chunks if parse_sse_chunk(c)]

    progress_vals = []
    current = 0
    for evt in events:
        update = map_nexus_event_to_progress(evt, current)
        progress_vals.append(update.progress)
        current = update.progress

    # Monotonic
    for i in range(1, len(progress_vals)):
        assert progress_vals[i] >= progress_vals[i - 1]

    # Terminal is 100
    assert progress_vals[-1] == 100


# ═══════════════════════════════════════════════════════════════════════
# I7: Per-call token override
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_per_call_token_override(client: AsyncClient):
    """I7: Custom Authorization header is accepted by the agent."""
    r = await client.get(
        "/.well-known/agent-card.json",
        headers={"Authorization": "Bearer custom-override-token"},
    )
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# I8: Unreachable agent
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_agent_unreachable_graceful():
    """I8: Probing an unreachable URL returns error dict, no crash."""
    result = await probe_agent_health("http://localhost:1", "fake-token", timeout=1.0)
    assert result["status"] == "unreachable"
    assert "error" in result

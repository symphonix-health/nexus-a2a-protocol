"""Tests for Command Centre trace API endpoints (POST/GET/export)."""

from __future__ import annotations

import importlib
import json
import os
import sys

import pytest
from httpx import ASGITransport, AsyncClient

# The directory uses a hyphen ("command-centre") which is not a valid
# Python package name, so we add the app directory to sys.path and
# import the module directly.
_app_dir = os.path.join(os.path.dirname(__file__), os.pardir, "shared", "command-centre", "app")
sys.path.insert(0, os.path.abspath(_app_dir))
_main = importlib.import_module("main")
sys.path.pop(0)

app = _main.app
trace_store = _main.trace_store
trace_lock = _main.trace_lock
TRACE_STORE_MAX = _main.TRACE_STORE_MAX

BASE = "http://testserver"


@pytest.fixture(autouse=True)
async def _clear_trace_store():
    """Ensure each test starts with an empty trace store."""
    async with trace_lock:
        trace_store.clear()
    yield
    async with trace_lock:
        trace_store.clear()


def _sample_trace_body(trace_id: str = "trace-T1", **overrides) -> dict:
    body = {
        "trace_id": trace_id,
        "scenario_name": "ed_intake",
        "visit_id": "V-100",
        "patient_id": "P-200",
        "patient_profile": {"age": 45, "gender": "male"},
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T00:01:00Z",
        "status": "final",
        "steps": [
            {
                "trace_id": trace_id,
                "correlation_id": "corr-1",
                "scenario_name": "ed_intake",
                "patient_id": "P-200",
                "visit_id": "V-100",
                "agent": "triage",
                "method": "tasks/send",
                "step_index": 0,
                "timestamp_start": "2025-01-01T00:00:00Z",
                "timestamp_end": "2025-01-01T00:00:02Z",
                "duration_ms": 2000.0,
                "status": "final",
                "request_redacted": {"age": 45},
                "response_redacted": {"result": "ok"},
                "redaction_meta": {"masked_fields": ["name"], "policy_version": "v1"},
                "retry_count": 0,
            }
        ],
        "total_duration_ms": 2000.0,
        "step_count": 1,
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_post_trace_returns_201():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/traces", json=_sample_trace_body())
    assert resp.status_code == 201
    data = resp.json()
    assert data["trace_id"] == "trace-T1"
    assert data["stored"] is True


@pytest.mark.asyncio
async def test_post_trace_missing_trace_id_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.post("/api/traces", json={"scenario_name": "x"})
    assert resp.status_code == 400
    assert "trace_id" in resp.json()["error"]


@pytest.mark.asyncio
async def test_list_traces_returns_summaries():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        await client.post("/api/traces", json=_sample_trace_body("trace-A"))
        await client.post("/api/traces", json=_sample_trace_body("trace-B"))
        resp = await client.get("/api/traces")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    ids = [i["trace_id"] for i in items]
    assert "trace-A" in ids
    assert "trace-B" in ids
    # Each summary should have key fields
    for item in items:
        assert "scenario_name" in item
        assert "step_count" in item


@pytest.mark.asyncio
async def test_get_trace_returns_full_run():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        await client.post("/api/traces", json=_sample_trace_body("trace-X"))
        resp = await client.get("/api/traces/trace-X")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == "trace-X"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["agent"] == "triage"


@pytest.mark.asyncio
async def test_get_unknown_trace_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.get("/api/traces/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_trace_returns_json_attachment():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        await client.post("/api/traces", json=_sample_trace_body("trace-E"))
        resp = await client.get("/api/traces/trace-E/export")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    data = json.loads(resp.text)
    assert data["trace_id"] == "trace-E"


@pytest.mark.asyncio
async def test_export_unknown_trace_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        resp = await client.get("/api/traces/nope/export")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ring_buffer_evicts_oldest():
    """When trace_store exceeds TRACE_STORE_MAX, oldest entries are evicted."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        # Insert TRACE_STORE_MAX + 5 traces
        for i in range(TRACE_STORE_MAX + 5):
            await client.post("/api/traces", json=_sample_trace_body(f"trace-{i:04d}"))

        resp = await client.get("/api/traces")
    items = resp.json()
    assert len(items) <= TRACE_STORE_MAX
    # The oldest 5 should have been evicted
    ids = {i["trace_id"] for i in items}
    for i in range(5):
        assert f"trace-{i:04d}" not in ids


@pytest.mark.asyncio
async def test_reset_traces_clears_store():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as client:
        await client.post("/api/traces", json=_sample_trace_body("trace-reset-1"))
        await client.post("/api/traces", json=_sample_trace_body("trace-reset-2"))

        reset_resp = await client.delete("/api/traces")
        assert reset_resp.status_code == 200
        payload = reset_resp.json()
        assert payload["cleared"] is True
        assert payload["cleared_count"] == 2

        list_resp = await client.get("/api/traces")
        assert list_resp.status_code == 200
        assert list_resp.json() == []

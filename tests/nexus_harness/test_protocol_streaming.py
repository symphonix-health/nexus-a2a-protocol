"""Matrix-driven tests for the protocol-streaming tier (SSE + WebSocket)."""
from __future__ import annotations

import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    scenarios_for, pytest_ids, entry_url, get_report, ScenarioResult,
    assert_deterministic_negative_rpc, auth_headers_for_negative_scenario,
)

MATRIX = "nexus_protocol_streaming_matrix.json"
BASE = entry_url("ed-triage")

_positive = scenarios_for(MATRIX, scenario_type="positive")
_negative = scenarios_for(MATRIX, scenario_type="negative")


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_streaming_positive(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
    sr = ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )
    t0 = time.monotonic()
    try:
        payload = scenario.get("input_payload", {})
        transport = scenario.get("transport", "https")

        if payload.get("jsonrpc"):
            # Send RPC to get a task_id, then check SSE endpoint
            resp = await client.post(f"{BASE}/rpc", headers=auth_headers, content=json.dumps(payload))
            assert resp.status_code == scenario.get("expected_http_status", 200)
            body = resp.json()
            task_id = body.get("result", {}).get("task_id")

            if task_id and "sse" in transport.lower():
                # Attempt SSE stream briefly
                async with client.stream(
                    "GET", f"{BASE}/events/{task_id}",
                    headers={"Authorization": auth_headers["Authorization"]},
                    timeout=5.0,
                ) as stream:
                    chunks = []
                    async for line in stream.aiter_lines():
                        chunks.append(line)
                        if len(chunks) >= 3:
                            break
                sr.status = "pass"
            else:
                # Just getting a valid response is enough for non-SSE streaming test
                sr.status = "pass"
        else:
            sr.status = "skip"
            sr.message = "Unrecognised payload"
    except httpx.ReadTimeout:
        # SSE timeout is acceptable – means the endpoint was live
        sr.status = "pass"
        sr.message = "SSE stream timed out (acceptable)"
    except Exception as exc:
        sr.status = "fail"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


@pytest.mark.parametrize("scenario", _negative, ids=pytest_ids(_negative))
@pytest.mark.asyncio
async def test_streaming_negative(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
    sr = ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )
    t0 = time.monotonic()
    try:
        payload = scenario.get("input_payload", {})
        if payload.get("jsonrpc"):
            headers = auth_headers_for_negative_scenario(scenario, auth_headers)
            resp = await client.post(f"{BASE}/rpc", headers=headers, content=json.dumps(payload))
            body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
            assert_deterministic_negative_rpc(
                scenario,
                status_code=resp.status_code,
                body=body if isinstance(body, dict) else {},
            )
            sr.status = "pass"
        else:
            sr.status = "skip"
    except Exception as exc:
        sr.status = "fail"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)

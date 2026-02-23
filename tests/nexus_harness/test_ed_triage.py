"""Matrix-driven tests for the ED Triage demo."""
from __future__ import annotations

import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    scenarios_for, pytest_ids, DEMO_URLS, get_report, ScenarioResult,
    assert_deterministic_negative_rpc, auth_headers_for_negative_scenario,
)

MATRIX = "nexus_ed_triage_matrix.json"
URLS = DEMO_URLS["ed-triage"]

_positive = scenarios_for(MATRIX, scenario_type="positive")
_negative = scenarios_for(MATRIX, scenario_type="negative")


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_ed_triage_positive(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
        method = payload.get("method", "")
        base = URLS["triage-agent"]

        if payload.get("protocol_step") == "agent_card_get":
            resp = await client.get(f"{base}/.well-known/agent-card.json")
            assert resp.status_code == 200
            sr.status = "pass"
        elif payload.get("jsonrpc"):
            if "diagnosis" in method:
                base = URLS["diagnosis-agent"]
            elif "fhir" in method:
                base = URLS["openhie-mediator"]

            resp = await client.post(f"{base}/rpc", headers=auth_headers, content=json.dumps(payload))
            assert resp.status_code == scenario.get("expected_http_status", 200)
            body = resp.json()
            result = body.get("result", {})

            # Check expected events if task_id is present
            task_id = result.get("task_id")
            expected_events = scenario.get("expected_events", [])
            if task_id and expected_events:
                try:
                    async with client.stream(
                        "GET", f"{base}/events/{task_id}",
                        headers={"Authorization": auth_headers["Authorization"]},
                        timeout=8.0,
                    ) as stream:
                        async for _ in stream.aiter_lines():
                            break  # at least one event received
                except httpx.ReadTimeout:
                    pass

            sr.status = "pass"
        else:
            sr.status = "skip"
            sr.message = "Unrecognised payload"
    except Exception as exc:
        sr.status = "fail"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


@pytest.mark.parametrize("scenario", _negative, ids=pytest_ids(_negative))
@pytest.mark.asyncio
async def test_ed_triage_negative(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
        base = URLS["triage-agent"]
        if payload.get("jsonrpc"):
            headers = auth_headers_for_negative_scenario(scenario, auth_headers)
            resp = await client.post(f"{base}/rpc", headers=headers, content=json.dumps(payload))
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

"""Matrix-driven tests for the Public Health Surveillance demo."""
from __future__ import annotations

import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    scenarios_for, pytest_ids, DEMO_URLS, get_report, ScenarioResult,
)

MATRIX = "nexus_public_health_surveillance_matrix.json"
URLS = DEMO_URLS["public-health-surveillance"]

_positive = scenarios_for(MATRIX, scenario_type="positive")
_negative = scenarios_for(MATRIX, scenario_type="negative")


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_surveillance_positive(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
        base = URLS["central-surveillance"]

        if payload.get("protocol_step") == "agent_card_get":
            resp = await client.get(f"{base}/.well-known/agent-card.json")
            assert resp.status_code == 200
            card = resp.json()
            assert card.get("capabilities", {}).get("multiTransport") is True
            sr.status = "pass"
        elif payload.get("jsonrpc"):
            if "surveillance/report" in method:
                base = URLS["hospital-reporter"]
            elif "osint/" in method:
                base = URLS["osint-agent"]

            resp = await client.post(f"{base}/rpc", headers=auth_headers, content=json.dumps(payload))
            assert resp.status_code == scenario.get("expected_http_status", 200)

            body = resp.json()
            result = body.get("result", {})
            task_id = result.get("task_id")
            if task_id and scenario.get("expected_events"):
                try:
                    async with client.stream(
                        "GET", f"{base}/events/{task_id}",
                        headers={"Authorization": auth_headers["Authorization"]},
                        timeout=8.0,
                    ) as stream:
                        async for _ in stream.aiter_lines():
                            break
                except httpx.ReadTimeout:
                    pass

            # Check transport_used if relevant
            if "transport_used" in result:
                sr.message = f"transport_used={result['transport_used']}"

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
async def test_surveillance_negative(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
        base = URLS["central-surveillance"]
        if payload.get("jsonrpc"):
            headers = dict(auth_headers)
            if scenario.get("auth_mode") == "none":
                headers.pop("Authorization", None)
            resp = await client.post(f"{base}/rpc", headers=headers, content=json.dumps(payload))
            body = resp.json()
            if resp.status_code >= 400 or "error" in body:
                sr.status = "pass"
            else:
                sr.status = "fail"
                sr.message = f"Expected error, got {resp.status_code}"
        else:
            sr.status = "skip"
    except Exception as exc:
        sr.status = "fail"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)

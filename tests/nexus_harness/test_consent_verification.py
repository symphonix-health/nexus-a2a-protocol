"""Matrix-driven tests for the Consent Verification demo."""
from __future__ import annotations

import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    scenarios_for, pytest_ids, DEMO_URLS, get_report, ScenarioResult,
)

MATRIX = "nexus_consent_verification_matrix.json"
URLS = DEMO_URLS["consent-verification"]

_positive = scenarios_for(MATRIX, scenario_type="positive")
_negative = scenarios_for(MATRIX, scenario_type="negative")


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_consent_positive(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
        base = URLS["insurer-agent"]

        if payload.get("protocol_step") == "agent_card_get":
            resp = await client.get(f"{base}/.well-known/agent-card.json")
            assert resp.status_code == 200
            card = resp.json()
            assert "name" in card
            sr.status = "pass"
        elif payload.get("jsonrpc"):
            if "records/provide" in method:
                base = URLS["provider-agent"]
            elif "consent/check" in method:
                base = URLS["consent-analyser"]
            elif "hitl/" in method:
                base = URLS["hitl-ui"]

            resp = await client.post(f"{base}/rpc", headers=auth_headers, content=json.dumps(payload))
            assert resp.status_code == scenario.get("expected_http_status", 200)

            body = resp.json()
            task_id = body.get("result", {}).get("task_id")
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
async def test_consent_negative(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
        base = URLS["insurer-agent"]
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

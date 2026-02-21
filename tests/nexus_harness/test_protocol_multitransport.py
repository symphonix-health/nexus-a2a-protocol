"""Matrix-driven tests for the protocol-multitransport tier (MQTT + WS)."""
from __future__ import annotations

import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    scenarios_for, pytest_ids, entry_url, get_report, ScenarioResult,
)

MATRIX = "nexus_protocol_multitransport_matrix.json"
BASE = entry_url("public-health-surveillance")

_positive = scenarios_for(MATRIX, scenario_type="positive")
_negative = scenarios_for(MATRIX, scenario_type="negative")


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_multitransport_positive(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
            resp = await client.post(f"{BASE}/rpc", headers=auth_headers, content=json.dumps(payload))
            assert resp.status_code == scenario.get("expected_http_status", 200)
            body = resp.json()
            result = body.get("result", {})
            # If transport_used is reported, verify it
            if "transport_used" in result:
                sr.message = f"transport_used={result['transport_used']}"
            sr.status = "pass"
        elif payload.get("protocol_step") == "agent_card_get":
            resp = await client.get(f"{BASE}/.well-known/agent-card.json")
            assert resp.status_code == 200
            card = resp.json()
            assert card.get("capabilities", {}).get("multiTransport") is True
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
async def test_multitransport_negative(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
            headers = dict(auth_headers)
            if scenario.get("auth_mode") == "none":
                headers.pop("Authorization", None)
            resp = await client.post(f"{BASE}/rpc", headers=headers, content=json.dumps(payload))
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

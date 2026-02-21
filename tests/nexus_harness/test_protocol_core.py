"""Matrix-driven tests for the protocol-core tier.

These tests validate core JSON-RPC 2.0 envelope handling, agent-card
discovery, and JWT authentication – independent of any specific demo.
They run against a lightweight conformance agent (or any agent that
exposes /.well-known/agent-card.json and /rpc).
"""
from __future__ import annotations

import json
import time
import pytest
import httpx

from tests.nexus_harness.runner import (
    scenarios_for, pytest_ids, entry_url, get_report, ScenarioResult,
)

MATRIX = "nexus_protocol_core_matrix.json"
# Use the first available demo agent for core protocol tests
CORE_BASE = entry_url("ed-triage")

_positive = scenarios_for(MATRIX, scenario_type="positive")
_negative = scenarios_for(MATRIX, scenario_type="negative")


# ── helpers ─────────────────────────────────────────────────────────
def _rpc_payload(scenario: dict) -> dict | None:
    p = scenario.get("input_payload", {})
    if p.get("jsonrpc"):
        return p
    return None


def _is_agent_card_test(scenario: dict) -> bool:
    p = scenario.get("input_payload", {})
    return p.get("protocol_step") == "agent_card_get"


# ── positive scenarios ──────────────────────────────────────────────
@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_core_positive(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
    sr = ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )
    t0 = time.monotonic()
    try:
        if _is_agent_card_test(scenario):
            resp = await client.get(f"{CORE_BASE}/.well-known/agent-card.json")
            assert resp.status_code == scenario.get("expected_http_status", 200)
            card = resp.json()
            assert "name" in card
        elif (payload := _rpc_payload(scenario)):
            resp = await client.post(f"{CORE_BASE}/rpc", headers=auth_headers, content=json.dumps(payload))
            assert resp.status_code == scenario.get("expected_http_status", 200)
            body = resp.json()
            assert "jsonrpc" in body
        else:
            sr.status = "skip"
            sr.message = "Unrecognised input_payload shape"
            return

        sr.status = "pass"
    except Exception as exc:
        sr.status = "fail"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


# ── negative scenarios ──────────────────────────────────────────────
@pytest.mark.parametrize("scenario", _negative, ids=pytest_ids(_negative))
@pytest.mark.asyncio
async def test_core_negative(scenario: dict, client: httpx.AsyncClient, auth_headers: dict):
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
            # For negative tests, send the bad payload and expect an error
            headers = dict(auth_headers)
            if scenario.get("auth_mode") == "none":
                headers.pop("Authorization", None)
            resp = await client.post(f"{CORE_BASE}/rpc", headers=headers, content=json.dumps(payload))
            expected_status = scenario.get("expected_http_status", 400)
            # Accept either the expected status or 200 with JSON-RPC error
            body = resp.json()
            if resp.status_code == expected_status:
                sr.status = "pass"
            elif "error" in body:
                sr.status = "pass"
            else:
                sr.status = "fail"
                sr.message = f"Expected status {expected_status}, got {resp.status_code}"
        else:
            sr.status = "skip"
            sr.message = "Non-RPC negative scenario"
    except Exception as exc:
        sr.status = "fail"
        sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)

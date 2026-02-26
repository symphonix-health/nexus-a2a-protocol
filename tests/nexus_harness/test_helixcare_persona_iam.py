"""Matrix-driven E2E tests for the Persona & IAM system.

Covers:
- avatar/start_session with persona_id, country, and care_setting routing
- avatar/list_personas RPC method
- GET /api/identity endpoint
- /health identity section
- Auth security on new endpoints
- Full multi-turn consultations with registry-resolved personas

Matrix: HelixCare/helixcare_persona_iam_matrix.json
Agent: clinician-avatar-agent (port 8039)
"""
from __future__ import annotations

import json
import time

import httpx
import pytest

from tests.nexus_harness.runner import (
    HELIXCARE_URLS,
    ScenarioResult,
    assert_deterministic_negative_rpc,
    auth_headers_for_negative_scenario,
    get_report,
    scenarios_for_helixcare,
    pytest_ids,
)

MATRIX = "helixcare_persona_iam_matrix.json"
AVATAR_URL = HELIXCARE_URLS["clinician-avatar"]

_positive = scenarios_for_helixcare(MATRIX, scenario_type="positive")
_negative = scenarios_for_helixcare(MATRIX, scenario_type="negative")
_edge = scenarios_for_helixcare(MATRIX, scenario_type="edge")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _rpc(method: str, params: dict, req_id: str = "test") -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


async def _start_session(
    client: httpx.AsyncClient,
    headers: dict,
    params: dict,
) -> tuple[int, dict]:
    payload = _rpc("avatar/start_session", params)
    resp = await client.post(f"{AVATAR_URL}/rpc", headers=headers,
                             content=json.dumps(payload), timeout=15.0)
    body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
    return resp.status_code, body


async def _run_full_consult(
    client: httpx.AsyncClient,
    headers: dict,
    persona_id: str,
    patient_case: dict,
    messages: list[str],
) -> dict:
    """Start a session then send all patient messages. Return last result."""
    status, body = await _start_session(
        client, headers,
        {"persona_id": persona_id, "patient_case": patient_case},
    )
    assert status == 200, f"start_session failed: {body}"
    session_id = body.get("result", {}).get("session_id", "")
    assert session_id, f"No session_id in: {body}"

    result = body.get("result", {})
    for msg in messages:
        payload = _rpc("avatar/patient_message", {"session_id": session_id, "message": msg})
        resp = await client.post(f"{AVATAR_URL}/rpc", headers=headers,
                                 content=json.dumps(payload), timeout=15.0)
        assert resp.status_code == 200, f"patient_message failed: {resp.text}"
        result = resp.json().get("result", {})

    return result


def _assert_contains(body: dict, fields: list[str], use_case_id: str) -> None:
    result = body.get("result", body)
    result_str = json.dumps(result)
    for field in fields:
        assert field in result or field in result_str, (
            f"{use_case_id}: expected field '{field}' not found in {result_str[:200]}"
        )


# ── Positive Tests ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_helixcare_persona_iam_positive(
    scenario: dict,
    client: httpx.AsyncClient,
    auth_headers: dict,
) -> None:
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
        step = payload.get("protocol_step", "")

        # ── Unit-only scenarios (no HTTP call needed) ──────────────────────
        if scenario.get("transport") == "unit":
            sr.status = "skip"
            sr.message = "unit-only scenario — covered by test_persona_registry.py and test_agent_identity.py"
            return

        # ── Health check ──────────────────────────────────────────────────
        if step == "health_check":
            resp = await client.get(f"{AVATAR_URL}/health", timeout=10.0)
            assert resp.status_code == 200
            body = resp.json()
            assert "status" in body
            assert "identity" in body, f"Expected 'identity' in health: {body}"
            sr.status = "pass"
            return

        # ── GET /api/identity ─────────────────────────────────────────────
        if step == "get_identity":
            resp = await client.get(f"{AVATAR_URL}/api/identity",
                                    headers=auth_headers, timeout=10.0)
            assert resp.status_code == 200
            body = resp.json()
            for field in scenario.get("expected_result", {}).get("contains", []):
                assert field in body, f"Missing '{field}' in identity response: {body}"
            sr.status = "pass"
            return

        # ── Full multi-turn consultation ───────────────────────────────────
        if step == "avatar_full_consult":
            messages = payload.get("patient_messages", [])
            result = await _run_full_consult(
                client, auth_headers,
                persona_id=payload.get("persona_id", "P001"),
                patient_case=payload.get("patient_case", {}),
                messages=messages,
            )
            assert result, "Empty result from avatar consultation"
            sr.status = "pass"
            return

        # ── JSON-RPC calls ─────────────────────────────────────────────────
        if payload.get("jsonrpc"):
            resp = await client.post(f"{AVATAR_URL}/rpc", headers=auth_headers,
                                     content=json.dumps(payload), timeout=15.0)
            exp_status = scenario.get("expected_http_status", 200)
            assert resp.status_code == exp_status, (
                f"{scenario['use_case_id']}: expected {exp_status}, got {resp.status_code}"
            )
            body = resp.json()
            expected = scenario.get("expected_result", {})

            if expected.get("is_list"):
                result = body.get("result", [])
                assert isinstance(result, list), f"Expected list result, got: {result}"
                min_count = expected.get("min_count", 1)
                assert len(result) >= min_count, (
                    f"Expected at least {min_count} personas, got {len(result)}"
                )
            elif expected.get("ok"):
                contains = expected.get("contains", [])
                _assert_contains(body, contains, scenario["use_case_id"])

            sr.status = "pass"
            return

        sr.status = "skip"
        sr.message = "Unrecognised payload shape"

    except AssertionError as exc:
        sr.status = "fail"
        sr.message = str(exc)
    except Exception as exc:
        sr.status = "fail"
        sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


# ── Negative Tests ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scenario", _negative, ids=pytest_ids(_negative))
@pytest.mark.asyncio
async def test_helixcare_persona_iam_negative(
    scenario: dict,
    client: httpx.AsyncClient,
    auth_headers: dict,
) -> None:
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
        step = payload.get("protocol_step", "")

        # Unit-only scenarios delegated to unit test files
        if scenario.get("transport") == "unit":
            sr.status = "skip"
            sr.message = "unit-only negative — covered by test_agent_identity.py"
            return

        # GET /api/identity without auth
        if step == "get_identity_unauth":
            resp = await client.get(f"{AVATAR_URL}/api/identity", timeout=10.0)
            assert resp.status_code == 401, (
                f"Expected 401, got {resp.status_code}"
            )
            sr.status = "pass"
            return

        # JSON-RPC auth negative (e.g. list_personas without token)
        if payload.get("jsonrpc"):
            headers = auth_headers_for_negative_scenario(scenario, auth_headers)
            resp = await client.post(f"{AVATAR_URL}/rpc", headers=headers,
                                     content=json.dumps(payload), timeout=10.0)
            body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}

            # Special case: unknown persona_id must still start a session (graceful fallback)
            if scenario.get("error_condition") == "unknown_persona_id_falls_back":
                assert resp.status_code == 200, (
                    f"Expected graceful 200, got {resp.status_code}"
                )
                result = body.get("result", {})
                assert "session_id" in result, f"Expected session_id in fallback result: {body}"
                sr.status = "pass"
                return

            assert_deterministic_negative_rpc(
                scenario,
                status_code=resp.status_code,
                body=body if isinstance(body, dict) else {},
            )
            sr.status = "pass"
            return

        sr.status = "skip"
        sr.message = "Unsupported negative scenario shape"

    except AssertionError as exc:
        sr.status = "fail"
        sr.message = str(exc)
    except Exception as exc:
        sr.status = "fail"
        sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


# ── Edge Tests ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scenario", _edge, ids=pytest_ids(_edge))
@pytest.mark.asyncio
async def test_helixcare_persona_iam_edge(
    scenario: dict,
    client: httpx.AsyncClient,
    auth_headers: dict,
) -> None:
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
        step = payload.get("protocol_step", "")

        # Unit edge scenarios delegated to unit tests
        if scenario.get("transport") == "unit":
            sr.status = "skip"
            sr.message = "unit-only edge — covered by test_persona_registry.py"
            return

        if payload.get("jsonrpc"):
            resp = await client.post(f"{AVATAR_URL}/rpc", headers=auth_headers,
                                     content=json.dumps(payload), timeout=15.0)
            exp_status = scenario.get("expected_http_status")
            if exp_status not in (None, ""):
                assert resp.status_code == int(exp_status), (
                    f"Expected {exp_status}, got {resp.status_code}"
                )
            else:
                assert resp.status_code < 500, (
                    f"Edge scenario returned server error {resp.status_code}"
                )
            if "application/json" in resp.headers.get("content-type", ""):
                body = resp.json()
                assert isinstance(body, dict), "Expected JSON object"
                assert ("result" in body) or ("error" in body), "Expected JSON-RPC envelope"
            sr.status = "pass"
            return

        sr.status = "skip"
        sr.message = "Unsupported edge scenario shape"

    except AssertionError as exc:
        sr.status = "fail"
        sr.message = str(exc)
    except Exception as exc:
        sr.status = "fail"
        sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)

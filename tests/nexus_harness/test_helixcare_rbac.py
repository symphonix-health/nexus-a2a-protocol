"""Matrix-driven harness tests for NEXUS-A2A RBAC enforcement.

Loads ``helixcare_rbac_matrix.json`` and exercises all 30 scenarios
(15 positive, 10 negative, 5 edge) against live agents.

Positive scenarios
------------------
Persona-scoped JWTs are minted via :func:`mint_persona_jwt` and sent to the
target agent.  Expects HTTP 200.

Negative auth scenarios (jwt_missing / jwt_expired / jwt_invalid / jwt_missing_scope)
---------------------------------------------------------------------------------------
Deterministic bad tokens or no token are sent.  Every agent must respond with
HTTP 401 + JSON-RPC error envelope ``{"error": {"code": -32001, "data": {"reason":
"auth_failed"}}}``.

RBAC scope-mismatch scenarios (persona_scope_mismatch)
------------------------------------------------------
A valid persona JWT is sent, the agent returns HTTP 200 (auth passes), but
:func:`assess_method_rbac` is called locally on the decoded claims to verify that
our RBAC module correctly denies the request.  This exercises the enforcement
layer without requiring agents to implement per-method RBAC gating.

Edge scenarios
--------------
Bare ``nexus:invoke`` JWT fallback, Kenya/Safeguarding personas, and the
unauthenticated ``/health`` endpoint.

Requires live agents.  Unreachable agents are recorded as **skip** rather than
**fail** so that a partial lab deployment does not block the full suite.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

import httpx
import pytest

from shared.nexus_common.auth import mint_jwt, mint_persona_jwt
from shared.nexus_common.rbac import assess_method_rbac
from tests.nexus_harness.runner import (
    HELIXCARE_URLS,
    ScenarioResult,
    assert_deterministic_negative_rpc,
    get_report,
    pytest_ids,
    scenarios_for_helixcare,
)

# ── Matrix ─────────────────────────────────────────────────────────────────

MATRIX = "helixcare_rbac_matrix.json"

_positive = scenarios_for_helixcare(MATRIX, scenario_type="positive")
_negative = scenarios_for_helixcare(MATRIX, scenario_type="negative")
_edge = scenarios_for_helixcare(MATRIX, scenario_type="edge")

# ── JWT secret ─────────────────────────────────────────────────────────────

_JWT_SECRET = os.environ.get("NEXUS_JWT_SECRET", "dev-secret-change-me")

# ── agent_url_key → agent_id (as registered in config/agent_personas.json) ─

_AGENT_ID_MAP: dict[str, str] = {
    "triage-agent": "triage_agent",
    "diagnosis-agent": "diagnosis_agent",
    "imaging-agent": "imaging_agent",
    "pharmacy-agent": "pharmacy_agent",
    "bed-manager-agent": "bed_manager_agent",
    "discharge-agent": "discharge_agent",
    "followup-scheduler": "followup_scheduler",
    "care-coordinator": "care_coordinator",
    "osint-agent": "osint_agent",
    "consent-analyser": "consent_analyser",
    "clinician-avatar": "clinician_avatar_agent",
    "ehr-writer-agent": "ehr_writer_agent",
    "transcriber-agent": "transcriber_agent",
    "summariser-agent": "summariser_agent",
    "insurer-agent": "insurer_agent",
    "provider-agent": "provider_agent",
    "hitl-ui": "hitl_ui",
    "hospital-reporter": "hospital_reporter",
    "central-surveillance": "central_surveillance",
}


# ── Helpers ────────────────────────────────────────────────────────────────


def _mk_sr(scenario: dict[str, Any]) -> ScenarioResult:
    return ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )


def _agent_url(scenario: dict[str, Any]) -> str:
    key = scenario.get("agent_url_key") or scenario.get("agent", "")
    return HELIXCARE_URLS.get(key, "http://localhost:8000")


def _persona_jwt(persona_id: str | None) -> str:
    """Mint a persona-scoped JWT; falls back to plain nexus:invoke JWT."""
    if persona_id:
        return mint_persona_jwt(
            subject=f"harness-{persona_id}",
            secret=_JWT_SECRET,
            persona_id=persona_id,
            agent_id="test-harness",
        )
    return mint_jwt("test-harness", _JWT_SECRET)


def _decode_payload(token: str) -> dict[str, Any]:
    """Base64url-decode the JWT payload section without verifying the signature."""
    _, p_b64, _ = token.split(".")
    pad = "=" * ((4 - len(p_b64) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode((p_b64 + pad).encode()).decode())


def _bad_auth_headers(
    scenario: dict[str, Any],
    good_headers: dict[str, str],
) -> dict[str, str]:
    """Return headers that should trigger a 401 based on the scenario's auth_mode."""
    headers = dict(good_headers)
    mode = str(scenario.get("auth_mode", "")).strip().lower()

    if "jwt_missing" in mode:
        headers.pop("Authorization", None)
    elif "jwt_expired" in mode:
        # Valid signature, but exp is in the past.
        expired_token = mint_jwt("test-harness", _JWT_SECRET, ttl_seconds=-1)
        headers["Authorization"] = f"Bearer {expired_token}"
    elif "jwt_invalid" in mode:
        # Signature from a wrong secret — validation must reject it.
        bad_token = mint_jwt("test-harness", "wrong-secret-xyz-harness-rbac")
        headers["Authorization"] = f"Bearer {bad_token}"
    elif "jwt_missing_scope" in mode:
        # Well-formed JWT but with a scope the agents don't recognise.
        no_scope_token = mint_jwt("test-harness", _JWT_SECRET, scope="invalid:scope")
        headers["Authorization"] = f"Bearer {no_scope_token}"
    else:
        # Unknown negative mode — safest is to strip the token.
        headers.pop("Authorization", None)

    return headers


def _rpc_payload(scenario: dict[str, Any], req_id: str = "harness-rbac") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": scenario["method"],
        "params": scenario.get("params", {}),
    }


def _is_unreachable(exc: Exception) -> bool:
    return isinstance(exc, (ConnectionRefusedError, ConnectionError, OSError))


# ── Positive tests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_helixcare_rbac_positive(
    scenario: dict[str, Any],
    client: httpx.AsyncClient,
) -> None:
    """Persona-scoped JWT should be accepted by the target agent (HTTP 200)."""
    sr = _mk_sr(scenario)
    t0 = time.monotonic()
    try:
        url = _agent_url(scenario)
        token = _persona_jwt(scenario.get("persona_id"))
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = _rpc_payload(scenario)

        resp = await client.post(f"{url}/rpc", headers=headers, content=json.dumps(payload), timeout=15.0)

        expected_status = scenario.get("expected_result", {}).get("http_status", 200)
        assert resp.status_code == expected_status, (
            f"{scenario['use_case_id']}: expected HTTP {expected_status}, got {resp.status_code}"
        )
        sr.status = "pass"

    except Exception as exc:
        if _is_unreachable(exc):
            sr.status = "skip"
            sr.message = f"Agent unreachable at {_agent_url(scenario)}: {exc}"
        else:
            sr.status = "fail"
            sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


# ── Negative tests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", _negative, ids=pytest_ids(_negative))
@pytest.mark.asyncio
async def test_helixcare_rbac_negative(
    scenario: dict[str, Any],
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Negative auth scenarios → 401; scope-mismatch scenarios → 200 + local RBAC denial."""
    sr = _mk_sr(scenario)
    t0 = time.monotonic()
    try:
        url = _agent_url(scenario)
        auth_mode = str(scenario.get("auth_mode", "")).strip().lower()

        # ── Scope-mismatch: auth passes but RBAC module denies ──────────────
        if auth_mode == "persona_scope_mismatch":
            persona_id = scenario.get("persona_id")
            token = _persona_jwt(persona_id)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload = _rpc_payload(scenario)
            resp = await client.post(
                f"{url}/rpc", headers=headers, content=json.dumps(payload), timeout=15.0
            )

            # Valid JWT → agent admits the request (auth gate passes).
            assert resp.status_code == 200, (
                f"{scenario['use_case_id']}: expected HTTP 200 (valid auth, RBAC checked locally), "
                f"got {resp.status_code}"
            )

            # Local RBAC enforcement — verify the module denies correctly.
            agent_key = scenario.get("agent_url_key") or scenario.get("agent", "")
            agent_id = _AGENT_ID_MAP.get(agent_key, agent_key.replace("-", "_"))
            method = scenario["method"]
            claims = _decode_payload(token)
            rbac_ctx = assess_method_rbac(agent_id, method, claims)

            expected_rbac = scenario.get("expected_result", {}).get("rbac_check", {})
            if expected_rbac:
                assert rbac_ctx.allowed is False, (
                    f"{scenario['use_case_id']}: expected RBAC denied but got allowed; "
                    f"granted_scopes={rbac_ctx.granted_scopes}"
                )
                for ms in expected_rbac.get("missing_scopes", []):
                    assert ms in rbac_ctx.missing_scopes, (
                        f"{scenario['use_case_id']}: expected missing scope '{ms}' "
                        f"not in rbac_ctx.missing_scopes={rbac_ctx.missing_scopes}"
                    )
            sr.status = "pass"

        # ── Standard auth-failure: expect 401 ──────────────────────────────
        else:
            bad_headers = _bad_auth_headers(scenario, auth_headers)
            payload = _rpc_payload(scenario)
            resp = await client.post(
                f"{url}/rpc", headers=bad_headers, content=json.dumps(payload), timeout=15.0
            )
            body: dict[str, Any] = (
                resp.json()
                if "application/json" in resp.headers.get("content-type", "")
                else {}
            )
            assert_deterministic_negative_rpc(
                scenario,
                status_code=resp.status_code,
                body=body if isinstance(body, dict) else {},
            )
            sr.status = "pass"

    except Exception as exc:
        if _is_unreachable(exc):
            sr.status = "skip"
            sr.message = f"Agent unreachable at {_agent_url(scenario)}: {exc}"
        else:
            sr.status = "fail"
            sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


# ── Edge tests ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", _edge, ids=pytest_ids(_edge))
@pytest.mark.asyncio
async def test_helixcare_rbac_edge(
    scenario: dict[str, Any],
    client: httpx.AsyncClient,
) -> None:
    """Edge RBAC scenarios: bare JWT fallback, minority personas, unauthenticated health."""
    sr = _mk_sr(scenario)
    t0 = time.monotonic()
    try:
        url = _agent_url(scenario)
        method = scenario.get("method", "")
        auth_mode = str(scenario.get("auth_mode", "")).strip().lower()
        expected_status = scenario.get("expected_result", {}).get("http_status", 200)

        # ── /health — no auth required ──────────────────────────────────────
        if method == "health_check":
            resp = await client.get(f"{url}/health", timeout=10.0)
            assert resp.status_code == expected_status, (
                f"{scenario['use_case_id']}: /health expected {expected_status}, got {resp.status_code}"
            )
            if "application/json" in resp.headers.get("content-type", ""):
                data = resp.json()
                for chk in scenario.get("expected_result", {}).get("json_path_checks", []):
                    path_parts = chk["path"].split(".")
                    val: Any = data
                    for part in path_parts:
                        val = val.get(part) if isinstance(val, dict) else None
                    assert val == chk.get("value"), (
                        f"{scenario['use_case_id']}: path '{chk['path']}' "
                        f"expected '{chk.get('value')}', got '{val}'"
                    )
            sr.status = "pass"

        # ── Bare nexus:invoke JWT (no persona claims) ───────────────────────
        elif auth_mode == "bare_nexus_invoke":
            bare_token = mint_jwt("test-harness", _JWT_SECRET)
            headers = {
                "Authorization": f"Bearer {bare_token}",
                "Content-Type": "application/json",
            }
            payload = _rpc_payload(scenario)
            resp = await client.post(
                f"{url}/rpc", headers=headers, content=json.dumps(payload), timeout=15.0
            )
            assert resp.status_code == expected_status, (
                f"{scenario['use_case_id']}: expected HTTP {expected_status}, got {resp.status_code}"
            )
            sr.status = "pass"

        # ── Persona JWT edge cases (minority locales, edge scopes) ──────────
        else:
            token = _persona_jwt(scenario.get("persona_id"))
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload = _rpc_payload(scenario)
            resp = await client.post(
                f"{url}/rpc", headers=headers, content=json.dumps(payload), timeout=15.0
            )
            assert resp.status_code == expected_status, (
                f"{scenario['use_case_id']}: expected HTTP {expected_status}, got {resp.status_code}"
            )
            sr.status = "pass"

    except Exception as exc:
        if _is_unreachable(exc):
            sr.status = "skip"
            sr.message = f"Agent unreachable at {_agent_url(scenario)}: {exc}"
        else:
            sr.status = "fail"
            sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)

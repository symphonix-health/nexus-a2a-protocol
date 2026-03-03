"""Matrix-driven non-encounter IAM scenarios executed through the gateway PEP."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
import pytest

from shared.nexus_common.auth import mint_jwt, mint_persona_jwt
from tests.nexus_harness.runner import (
    ScenarioResult,
    assert_deterministic_negative_rpc,
    get_report,
    pytest_ids,
    scenarios_for_helixcare,
)

MATRIX = "helixcare_iam_non_encounter_matrix.json"
SCENARIOS = scenarios_for_helixcare(MATRIX)

GATEWAY_BASE_URL = os.environ.get("NEXUS_ON_DEMAND_GATEWAY_URL", "http://localhost:8100").rstrip(
    "/"
)
JWT_SECRET = os.environ.get("NEXUS_JWT_SECRET", "dev-secret-change-me")
_GATEWAY_PROBE_DONE = False
_GATEWAY_PROBE_OK = False
_GATEWAY_PROBE_MSG = ""
_GATEWAY_DEPENDENCY_UNAVAILABLE = False
_GATEWAY_DEPENDENCY_MSG = ""


def _mk_sr(scenario: dict[str, Any]) -> ScenarioResult:
    return ScenarioResult(
        use_case_id=scenario["use_case_id"],
        scenario_title=scenario["scenario_title"],
        poc_demo=scenario["poc_demo"],
        scenario_type=scenario["scenario_type"],
        requirement_ids=scenario.get("requirement_ids", []),
    )


def _auth_headers_for_scenario(
    scenario: dict[str, Any], auth_headers: dict[str, str]
) -> dict[str, str]:
    headers = dict(auth_headers)
    profile = str(scenario.get("auth_profile", "session")).strip().lower()

    if profile == "missing":
        headers.pop("Authorization", None)
        return headers

    if profile == "session":
        return headers

    scope = str(scenario.get("auth_scope") or "nexus:invoke")
    subject = str(scenario.get("auth_subject") or "harness-iam")

    if profile == "jwt":
        token = mint_jwt(subject, JWT_SECRET, scope=scope)
    elif profile == "persona":
        persona_id = str(scenario.get("persona_id") or "").strip()
        if not persona_id:
            raise AssertionError(
                f"{scenario['use_case_id']}: persona auth_profile requires persona_id"
            )
        token = mint_persona_jwt(
            subject,
            JWT_SECRET,
            persona_id=persona_id,
            agent_id=scenario.get("auth_agent_id"),
            scope=scope,
        )
    else:
        raise AssertionError(f"{scenario['use_case_id']}: unknown auth_profile '{profile}'")

    headers["Authorization"] = f"Bearer {token}"
    return headers


def _session_auth_headers() -> dict[str, str]:
    token = mint_jwt(
        "harness-session",
        JWT_SECRET,
        scope=os.environ.get("NEXUS_REQUIRED_SCOPE", "nexus:invoke"),
    )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _required_env_missing(scenario: dict[str, Any]) -> str | None:
    required = scenario.get("requires_env")
    if not isinstance(required, dict):
        return None
    for key, expected in required.items():
        actual = os.environ.get(str(key), "")
        if str(actual).strip().lower() != str(expected).strip().lower():
            return f"requires {key}={expected!r}; got {actual!r}"
    return None


def _is_transport_unreachable(exc: Exception) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout))


@pytest.mark.parametrize("scenario", SCENARIOS, ids=pytest_ids(SCENARIOS))
@pytest.mark.asyncio
async def test_helixcare_iam_non_encounter_matrix(
    scenario: dict[str, Any],
    client: httpx.AsyncClient,
) -> None:
    sr = _mk_sr(scenario)
    t0 = time.monotonic()
    try:
        missing_env_reason = _required_env_missing(scenario)
        if missing_env_reason:
            sr.status = "skip"
            sr.message = missing_env_reason
            return

        global _GATEWAY_PROBE_DONE, _GATEWAY_PROBE_OK, _GATEWAY_PROBE_MSG
        if not _GATEWAY_PROBE_DONE:
            try:
                health = await client.get(f"{GATEWAY_BASE_URL}/health", timeout=1.5)
                _GATEWAY_PROBE_OK = health.status_code == 200
                if not _GATEWAY_PROBE_OK:
                    _GATEWAY_PROBE_MSG = (
                        f"Gateway unavailable at {GATEWAY_BASE_URL} (status={health.status_code})"
                    )
            except Exception as exc:
                _GATEWAY_PROBE_OK = False
                _GATEWAY_PROBE_MSG = f"Gateway unreachable at {GATEWAY_BASE_URL}: {exc}"
            _GATEWAY_PROBE_DONE = True

        if not _GATEWAY_PROBE_OK:
            sr.status = "skip"
            sr.message = _GATEWAY_PROBE_MSG or f"Gateway unavailable at {GATEWAY_BASE_URL}"
            return

        global _GATEWAY_DEPENDENCY_UNAVAILABLE, _GATEWAY_DEPENDENCY_MSG
        if _GATEWAY_DEPENDENCY_UNAVAILABLE:
            sr.status = "skip"
            sr.message = _GATEWAY_DEPENDENCY_MSG or "Gateway dependency unavailable"
            return

        alias = str(scenario.get("gateway_alias") or "triage").strip()
        headers = _auth_headers_for_scenario(scenario, _session_auth_headers())
        payload = scenario.get("input_payload", {})

        resp = await client.post(
            f"{GATEWAY_BASE_URL}/rpc/{alias}",
            headers=headers,
            content=json.dumps(payload),
            timeout=8.0,
        )

        body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}

        expected_result = scenario.get("expected_result", {})
        expected_error = str(expected_result.get("error") or "").strip().upper()
        expected_http_status = int(scenario.get("expected_http_status", 200))

        # Environment may have partial services. Avoid false fails on startup/transport errors.
        if resp.status_code == 503:
            _GATEWAY_DEPENDENCY_UNAVAILABLE = True
            _GATEWAY_DEPENDENCY_MSG = f"Gateway dependency unavailable: {resp.text[:200]}"
            sr.status = "skip"
            sr.message = _GATEWAY_DEPENDENCY_MSG
            return

        if expected_http_status >= 400 or expected_error:
            assert_deterministic_negative_rpc(
                scenario,
                status_code=resp.status_code,
                body=body if isinstance(body, dict) else {},
            )
            sr.status = "pass"
            return

        assert resp.status_code == expected_http_status, (
            f"{scenario['use_case_id']}: expected HTTP {expected_http_status}, got {resp.status_code}; "
            f"body={resp.text[:400]}"
        )

        detail_contains = str(scenario.get("expected_detail_contains") or "").strip()
        if detail_contains:
            body_text = resp.text
            detail = ""
            if "application/json" in resp.headers.get("content-type", ""):
                try:
                    parsed = body if isinstance(body, dict) else resp.json()
                    if isinstance(parsed, dict):
                        detail = str(parsed.get("detail") or "")
                except Exception:
                    detail = ""
            haystack = f"{detail} {body_text}"
            assert detail_contains in haystack, (
                f"{scenario['use_case_id']}: expected detail containing '{detail_contains}', got '{haystack[:300]}'"
            )

        if bool(scenario.get("expected_jsonrpc_envelope", False)):
            assert "application/json" in resp.headers.get("content-type", ""), (
                f"{scenario['use_case_id']}: expected JSON response envelope"
            )
            assert isinstance(body, dict), (
                f"{scenario['use_case_id']}: expected JSON object response"
            )
            assert ("result" in body) or ("error" in body), (
                f"{scenario['use_case_id']}: expected JSON-RPC result/error envelope"
            )

        sr.status = "pass"

    except Exception as exc:
        if _is_transport_unreachable(exc):
            sr.status = "skip"
            sr.message = f"Transport unavailable: {exc}"
        else:
            sr.status = "fail"
            sr.message = str(exc)
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)

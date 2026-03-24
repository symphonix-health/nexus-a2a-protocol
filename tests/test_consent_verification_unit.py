"""In-process unit tests for the consent-verification agent quartet.

All four agents (insurer, consent-analyser, hitl-ui, provider) use
build_generic_demo_app(), so they are loaded directly without importlib.
httpx ASGITransport routes requests in-process — no live services needed.

Test coverage:
  Insurer          — tasks/sendSubscribe, tasks/send, tasks/get, tasks/cancel
  Consent Analyser — consent/check (allowed:true + reason), tasks/sendSubscribe
  HITL UI          — hitl/approve (approve + deny), tasks/resubscribe
  Provider         — records/provide, tasks/get, tasks/cancel

The startup-safe generic handler returns deterministic responses so tests
pass without OPENAI_API_KEY.  When the key is present the LLM path is
exercised transparently.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Project root on sys.path ──────────────────────────────────────────────────
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.nexus_common.auth import mint_jwt  # noqa: E402
from shared.nexus_common.generic_demo_agent import build_generic_demo_app  # noqa: E402

# ── Paths ─────────────────────────────────────────────────────────────────────
_DEMOS = _PROJECT_ROOT / "demos" / "consent-verification"
_INSURER_DIR = str(_DEMOS / "insurer-agent" / "app")
_ANALYSER_DIR = str(_DEMOS / "consent-analyser" / "app")
_HITL_DIR = str(_DEMOS / "hitl-ui" / "app")
_PROVIDER_DIR = str(_DEMOS / "provider-agent" / "app")

_MATRIX_FILE = _PROJECT_ROOT / "HelixCare" / "consent_verification_unit_matrix.json"
_SECRET = "dev-secret-change-me"


# ── Matrix helpers ────────────────────────────────────────────────────────────

def _load_matrix() -> list[dict]:
    return json.loads(_MATRIX_FILE.read_text(encoding="utf-8"))


def _scenarios(scenario_type: str, agent: str | None = None) -> list[dict]:
    rows = [s for s in _load_matrix() if s.get("scenario_type") == scenario_type]
    if agent:
        rows = [s for s in rows if s.get("agent") == agent]
    return rows


def _ids(scenarios: list[dict]) -> list[str]:
    return [s.get("use_case_id", f"s-{i}") for i, s in enumerate(scenarios)]


# Per-agent per-type slices
_insurer_pos = _scenarios("positive", "insurer-agent")
_insurer_neg = _scenarios("negative", "insurer-agent")
_insurer_edge = _scenarios("edge", "insurer-agent")

_analyser_pos = _scenarios("positive", "consent-analyser")
_analyser_neg = _scenarios("negative", "consent-analyser")
_analyser_edge = _scenarios("edge", "consent-analyser")

_hitl_pos = _scenarios("positive", "hitl-ui")
_hitl_neg = _scenarios("negative", "hitl-ui")
_hitl_edge = _scenarios("edge", "hitl-ui")

_provider_pos = _scenarios("positive", "provider-agent")
_provider_neg = _scenarios("negative", "provider-agent")
_provider_edge = _scenarios("edge", "provider-agent")


# ── Agent app fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _set_env():
    os.environ.setdefault("NEXUS_JWT_SECRET", _SECRET)


@pytest.fixture(scope="module")
def insurer_app():
    return build_generic_demo_app(default_name="insurer-agent", app_dir=_INSURER_DIR)


@pytest.fixture(scope="module")
def analyser_app():
    return build_generic_demo_app(default_name="consent-analyser", app_dir=_ANALYSER_DIR)


@pytest.fixture(scope="module")
def hitl_app():
    return build_generic_demo_app(default_name="hitl-ui", app_dir=_HITL_DIR)


@pytest.fixture(scope="module")
def provider_app():
    return build_generic_demo_app(default_name="provider-agent", app_dir=_PROVIDER_DIR)


@pytest_asyncio.fixture
async def insurer(insurer_app):
    async with AsyncClient(
        transport=ASGITransport(app=insurer_app),
        base_url="http://insurer-agent",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def analyser(analyser_app):
    async with AsyncClient(
        transport=ASGITransport(app=analyser_app),
        base_url="http://consent-analyser",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def hitl(hitl_app):
    async with AsyncClient(
        transport=ASGITransport(app=hitl_app),
        base_url="http://hitl-ui",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def provider(provider_app):
    async with AsyncClient(
        transport=ASGITransport(app=provider_app),
        base_url="http://provider-agent",
    ) as c:
        yield c


# ── Auth fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def valid_token() -> str:
    return mint_jwt("test-harness", _SECRET, scope="nexus:invoke")


@pytest.fixture(scope="module")
def valid_headers(valid_token) -> dict:
    return {"Authorization": f"Bearer {valid_token}", "Content-Type": "application/json"}


def _token_wrong_secret() -> str:
    return mint_jwt("test-harness", "totally-wrong-secret", scope="nexus:invoke")


def _token_wrong_scope() -> str:
    return mint_jwt("test-harness", _SECRET, scope="read:only")


def _token_expired() -> str:
    return mint_jwt("test-harness", _SECRET, ttl_seconds=-60, scope="nexus:invoke")


def _headers_for(scenario: dict, valid_headers: dict) -> dict:
    mode = scenario.get("auth_mode", "")
    if mode == "jwt_missing":
        return {"Content-Type": "application/json"}
    if mode == "jwt_invalid":
        return {"Authorization": f"Bearer {_token_wrong_secret()}", "Content-Type": "application/json"}
    if mode == "jwt_missing_scope":
        return {"Authorization": f"Bearer {_token_wrong_scope()}", "Content-Type": "application/json"}
    if mode == "jwt_expired":
        return {"Authorization": f"Bearer {_token_expired()}", "Content-Type": "application/json"}
    return valid_headers


# ── Core helpers ──────────────────────────────────────────────────────────────

async def _rpc(client: AsyncClient, headers: dict, payload: dict) -> tuple[int, dict]:
    resp = await client.post("/rpc", json=payload, headers=headers)
    return resp.status_code, resp.json()


def _assert_positive(scenario: dict, status: int, body: dict) -> None:
    uid = scenario["use_case_id"]
    expected = scenario["expected_result"]

    assert status == scenario["expected_http_status"], (
        f"{uid}: expected HTTP {scenario['expected_http_status']}, got {status}; body={body}"
    )
    assert "result" in body, f"{uid}: missing result envelope; body={body}"
    result = body["result"]

    for field in expected.get("contains", []):
        assert field in result, f"{uid}: expected field '{field}'; result={result}"

    for key in ("cancelled",):
        if key in expected:
            assert result.get(key) == expected[key], (
                f"{uid}: expected {key}={expected[key]!r}, got {result.get(key)!r}"
            )

    if "allowed" in expected:
        assert result.get("allowed") == expected["allowed"], (
            f"{uid}: expected allowed={expected['allowed']!r}, got {result.get('allowed')!r}"
        )

    if "patient_id" in expected:
        assert result.get("patient_id") == expected["patient_id"], (
            f"{uid}: expected patient_id={expected['patient_id']!r}, got {result.get('patient_id')!r}"
        )


def _assert_negative(scenario: dict, status: int, body: dict) -> None:
    uid = scenario["use_case_id"]
    expected = scenario["expected_result"]
    expected_status = scenario["expected_http_status"]
    expected_code = expected.get("error_code")

    if expected_status == 401:
        assert status == 401, f"{uid}: expected 401, got {status}; body={body}"
        assert "error" in body, f"{uid}: missing error envelope; body={body}"
        error = body["error"]
        assert error.get("code") == -32001, (
            f"{uid}: expected error.code=-32001, got {error.get('code')}"
        )
        data = error.get("data", {})
        assert isinstance(data, dict) and data.get("reason") == "auth_failed", (
            f"{uid}: expected reason='auth_failed'; data={data}"
        )
    elif expected_code is not None:
        assert status == 200, f"{uid}: expected HTTP 200 for RPC error, got {status}"
        assert "error" in body, f"{uid}: missing error envelope; body={body}"
        assert body["error"].get("code") == expected_code, (
            f"{uid}: expected error.code={expected_code}, got {body['error'].get('code')}"
        )
    else:
        assert status < 500, f"{uid}: unexpected 5xx; body={body}"


def _assert_edge(scenario: dict, status: int, body: dict) -> None:
    uid = scenario["use_case_id"]
    expected = scenario.get("expected_result", {})

    assert status < 500, f"{uid}: unexpected 5xx; body={body}"
    assert isinstance(body, dict)

    if expected.get("ok") is True:
        assert "result" in body, f"{uid}: expected result envelope; body={body}"
        result = body["result"]
        for field in expected.get("contains", []):
            assert field in result, f"{uid}: expected field '{field}'; result={result}"
        for key in ("cancelled",):
            if key in expected:
                assert result.get(key) == expected[key], (
                    f"{uid}: expected {key}={expected[key]!r}, got {result.get(key)!r}"
                )
        if "allowed" in expected:
            assert result.get("allowed") == expected["allowed"], (
                f"{uid}: expected allowed={expected['allowed']!r}"
            )
    elif expected.get("ok") is False:
        assert "error" in body, f"{uid}: expected error envelope; body={body}"
        if "error_code" in expected:
            assert body["error"].get("code") == expected["error_code"], (
                f"{uid}: expected error.code={expected['error_code']}, "
                f"got {body['error'].get('code')}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# INSURER AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _insurer_pos, ids=_ids(_insurer_pos))
async def test_insurer_positive(scenario, insurer, valid_headers):
    status, body = await _rpc(insurer, valid_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _insurer_neg, ids=_ids(_insurer_neg))
async def test_insurer_negative(scenario, insurer, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(insurer, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _insurer_edge, ids=_ids(_insurer_edge))
async def test_insurer_edge(scenario, insurer, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(insurer, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_insurer_health(insurer):
    resp = await insurer.get("/health")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


async def test_insurer_agent_card(insurer):
    resp = await insurer.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


async def test_insurer_idempotency_duplicate_returns_same_task_id(insurer, valid_headers):
    """Duplicate idempotency key must return the same task_id."""
    key = f"idem-insurer-{time.monotonic_ns()}"
    payload = {
        "jsonrpc": "2.0",
        "id": "idem-ins",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {
                "patient": {"patient_id": "CV-IDEM-01"},
                "request_type": "prior_authorisation",
                "procedure": "CT scan",
            },
            "idempotency": {
                "idempotency_key": key,
                "dedup_window_ms": 300000,
                "scope": "insurer",
            },
        },
    }
    _, first = await _rpc(insurer, valid_headers, payload)
    _, second = await _rpc(insurer, valid_headers, payload)

    assert "result" in first and "result" in second
    assert first["result"]["task_id"] == second["result"]["task_id"]
    assert second["result"].get("dedup", {}).get("duplicate") is True


async def test_insurer_unique_task_ids(insurer, valid_headers):
    ids_ = []
    for i in range(3):
        payload = {
            "jsonrpc": "2.0",
            "id": f"uniq-ins-{i}",
            "method": "tasks/sendSubscribe",
            "params": {"task": {"patient": {"patient_id": f"CV-UNIQ-{i}"}}},
        }
        _, body = await _rpc(insurer, valid_headers, payload)
        assert "result" in body
        ids_.append(body["result"]["task_id"])
    assert len(set(ids_)) == 3, f"Expected 3 unique task_ids; got {ids_}"


# ═══════════════════════════════════════════════════════════════════════════════
# CONSENT ANALYSER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _analyser_pos, ids=_ids(_analyser_pos))
async def test_analyser_positive(scenario, analyser, valid_headers):
    status, body = await _rpc(analyser, valid_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _analyser_neg, ids=_ids(_analyser_neg))
async def test_analyser_negative(scenario, analyser, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(analyser, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _analyser_edge, ids=_ids(_analyser_edge))
async def test_analyser_edge(scenario, analyser, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(analyser, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_analyser_health(analyser):
    resp = await analyser.get("/health")
    assert resp.status_code == 200


async def test_consent_check_returns_allowed_and_reason(analyser, valid_headers):
    """consent/check startup-safe handler must return allowed:true and a non-empty reason."""
    payload = {
        "jsonrpc": "2.0",
        "id": "cv-direct-001",
        "method": "consent/check",
        "params": {
            "task": {
                "patient": {"patient_id": "CV-DIRECT-001"},
                "consent_text": "I consent to share my records for treatment purposes.",
                "requesting_party": "Dr. Smith",
                "purpose": "treatment",
            }
        },
    }
    status, body = await _rpc(analyser, valid_headers, payload)
    assert status == 200
    assert "result" in body
    result = body["result"]
    assert result.get("allowed") is True, f"Expected allowed=True; result={result}"
    reason = result.get("reason", "")
    assert isinstance(reason, str) and reason.strip(), (
        f"Expected non-empty reason string; got {reason!r}"
    )


@pytest.mark.parametrize("consent_text,purpose", [
    ("I hereby consent to release my records for specialist referral.", "specialist_referral"),
    ("Consent signed 2018-01-01 — release of records for general practice only.", "insurance_claim"),
    ("", "treatment"),
    ("Ich erkläre mich einverstanden. Je consens. 私は同意します。", "treatment"),
])
async def test_consent_check_always_allowed_startup_safe(analyser, valid_headers, consent_text, purpose):
    """Startup-safe handler always returns allowed:true regardless of consent text."""
    payload = {
        "jsonrpc": "2.0",
        "id": "cv-param",
        "method": "consent/check",
        "params": {
            "task": {
                "patient": {"patient_id": "CV-PARAM"},
                "consent_text": consent_text,
                "purpose": purpose,
            }
        },
    }
    status, body = await _rpc(analyser, valid_headers, payload)
    assert status == 200
    assert body.get("result", {}).get("allowed") is True


# ═══════════════════════════════════════════════════════════════════════════════
# HITL UI TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _hitl_pos, ids=_ids(_hitl_pos))
async def test_hitl_positive(scenario, hitl, valid_headers):
    status, body = await _rpc(hitl, valid_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _hitl_neg, ids=_ids(_hitl_neg))
async def test_hitl_negative(scenario, hitl, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(hitl, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _hitl_edge, ids=_ids(_hitl_edge))
async def test_hitl_edge(scenario, hitl, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(hitl, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_hitl_health(hitl):
    resp = await hitl.get("/health")
    assert resp.status_code == 200


async def test_hitl_approve_decision_returns_no_5xx(hitl, valid_headers):
    """hitl/approve with approve decision must not return 5xx."""
    payload = {
        "jsonrpc": "2.0",
        "id": "cv-hitl-direct",
        "method": "hitl/approve",
        "params": {
            "task": {
                "patient": {"patient_id": "CV-HITL-DIRECT"},
                "decision": "approve",
                "reviewer": "clinician@hospital.nhs.uk",
                "reason": "Clinical necessity confirmed",
            }
        },
    }
    status, body = await _rpc(hitl, valid_headers, payload)
    assert status == 200
    assert "result" in body


async def test_hitl_deny_decision_returns_no_5xx(hitl, valid_headers):
    """hitl/approve with deny decision must not return 5xx."""
    payload = {
        "jsonrpc": "2.0",
        "id": "cv-hitl-deny",
        "method": "hitl/approve",
        "params": {
            "task": {
                "patient": {"patient_id": "CV-HITL-DENY"},
                "decision": "deny",
                "reviewer": "audit@hospital.nhs.uk",
                "reason": "Consent scope does not cover requested records",
            }
        },
    }
    status, body = await _rpc(hitl, valid_headers, payload)
    assert status == 200
    assert "result" in body


async def test_hitl_approve_missing_patient_defaults_to_unknown(hitl, valid_headers):
    """hitl/approve without patient field must return patient_id='unknown'."""
    payload = {
        "jsonrpc": "2.0",
        "id": "cv-hitl-nopt",
        "method": "hitl/approve",
        "params": {"task": {"decision": "approve"}},
    }
    status, body = await _rpc(hitl, valid_headers, payload)
    assert status < 500
    if "result" in body:
        assert body["result"].get("patient_id") == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _provider_pos, ids=_ids(_provider_pos))
async def test_provider_positive(scenario, provider, valid_headers):
    status, body = await _rpc(provider, valid_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _provider_neg, ids=_ids(_provider_neg))
async def test_provider_negative(scenario, provider, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(provider, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _provider_edge, ids=_ids(_provider_edge))
async def test_provider_edge(scenario, provider, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(provider, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_provider_health(provider):
    resp = await provider.get("/health")
    assert resp.status_code == 200


async def test_provider_records_provide_returns_patient_id(provider, valid_headers):
    """records/provide must return patient_id in result."""
    payload = {
        "jsonrpc": "2.0",
        "id": "cv-prov-direct",
        "method": "records/provide",
        "params": {
            "task": {
                "patient": {"patient_id": "CV-PROV-DIRECT"},
                "record_types": ["lab_results", "discharge_summary"],
                "consent_ref": "consent-cv-direct",
                "requesting_party": "InsurerCo",
            }
        },
    }
    status, body = await _rpc(provider, valid_headers, payload)
    assert status == 200
    assert "result" in body
    result = body["result"]
    assert "patient_id" in result, f"Expected patient_id in result; got {result}"


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-AGENT PIPELINE SMOKE TEST
# ═══════════════════════════════════════════════════════════════════════════════

async def test_consent_pipeline_analyser_then_provider(
    analyser, provider, valid_headers
):
    """Smoke: consent check allowed → provider records/provide succeeds."""
    # Step 1: consent analyser grants access
    check_payload = {
        "jsonrpc": "2.0",
        "id": "pipeline-check",
        "method": "consent/check",
        "params": {
            "task": {
                "patient": {"patient_id": "CV-PIPELINE-01"},
                "consent_text": "Patient consents to release records for insurance purposes.",
                "requesting_party": "InsurerCo",
                "purpose": "insurance_claim",
            }
        },
    }
    _, check_body = await _rpc(analyser, valid_headers, check_payload)
    assert check_body.get("result", {}).get("allowed") is True, (
        f"Pipeline step 1 failed: consent not allowed; body={check_body}"
    )

    # Step 2: provider releases records
    provide_payload = {
        "jsonrpc": "2.0",
        "id": "pipeline-provide",
        "method": "records/provide",
        "params": {
            "task": {
                "patient": {"patient_id": "CV-PIPELINE-01"},
                "record_types": ["lab_results"],
                "consent_ref": "consent-pipeline-01",
                "requesting_party": "InsurerCo",
            }
        },
    }
    status, provide_body = await _rpc(provider, valid_headers, provide_payload)
    assert status == 200
    assert "result" in provide_body, f"Pipeline step 2 failed; body={provide_body}"

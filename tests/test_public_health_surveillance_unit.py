"""In-process unit tests for the public-health-surveillance agent trio.

All three agents (hospital-reporter, osint-agent, central-surveillance) use
build_generic_demo_app(), loaded directly without importlib.
httpx ASGITransport routes requests in-process — no live services needed.

Test coverage:
  Hospital Reporter    — surveillance/report, tasks/sendSubscribe, tasks/get
  OSINT Agent          — osint/headlines (headlines list + source), tasks/sendSubscribe
  Central Surveillance — surveillance/synthesize, tasks/sendSubscribe, tasks/cancel

The startup-safe generic handler returns deterministic responses so tests
pass without OPENAI_API_KEY.
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
_DEMOS = _PROJECT_ROOT / "demos" / "public-health-surveillance"
_REPORTER_DIR = str(_DEMOS / "hospital-reporter" / "app")
_OSINT_DIR = str(_DEMOS / "osint-agent" / "app")
_CENTRAL_DIR = str(_DEMOS / "central-surveillance" / "app")

_MATRIX_FILE = _PROJECT_ROOT / "HelixCare" / "public_health_surveillance_unit_matrix.json"
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
_reporter_pos = _scenarios("positive", "hospital-reporter")
_reporter_neg = _scenarios("negative", "hospital-reporter")
_reporter_edge = _scenarios("edge", "hospital-reporter")

_osint_pos = _scenarios("positive", "osint-agent")
_osint_neg = _scenarios("negative", "osint-agent")
_osint_edge = _scenarios("edge", "osint-agent")

_central_pos = _scenarios("positive", "central-surveillance")
_central_neg = _scenarios("negative", "central-surveillance")
_central_edge = _scenarios("edge", "central-surveillance")


# ── Agent app fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _set_env():
    os.environ.setdefault("NEXUS_JWT_SECRET", _SECRET)


@pytest.fixture(scope="module")
def reporter_app():
    return build_generic_demo_app(default_name="hospital-reporter", app_dir=_REPORTER_DIR)


@pytest.fixture(scope="module")
def osint_app():
    return build_generic_demo_app(default_name="osint-agent", app_dir=_OSINT_DIR)


@pytest.fixture(scope="module")
def central_app():
    return build_generic_demo_app(default_name="central-surveillance", app_dir=_CENTRAL_DIR)


@pytest_asyncio.fixture
async def reporter(reporter_app):
    async with AsyncClient(
        transport=ASGITransport(app=reporter_app),
        base_url="http://hospital-reporter",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def osint(osint_app):
    async with AsyncClient(
        transport=ASGITransport(app=osint_app),
        base_url="http://osint-agent",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def central(central_app):
    async with AsyncClient(
        transport=ASGITransport(app=central_app),
        base_url="http://central-surveillance",
    ) as c:
        yield c


# ── Auth fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def valid_token() -> str:
    return mint_jwt("test-harness", _SECRET, scope="nexus:invoke")


@pytest.fixture(scope="module")
def valid_headers(valid_token) -> dict:
    return {"Authorization": f"Bearer {valid_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def reporter_token() -> str:
    # surveillance/report requires patient.read + observation.write per RBAC map.
    return mint_jwt(
        "test-harness",
        _SECRET,
        scope="nexus:invoke patient.read observation.write audit.read consent.read",
    )


@pytest.fixture(scope="module")
def reporter_headers(reporter_token) -> dict:
    return {"Authorization": f"Bearer {reporter_token}", "Content-Type": "application/json"}


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

    if expected.get("headlines_is_list"):
        headlines = result.get("headlines")
        assert isinstance(headlines, list), (
            f"{uid}: expected headlines to be a list; got {type(headlines).__name__}"
        )

    for key in ("cancelled",):
        if key in expected:
            assert result.get(key) == expected[key], (
                f"{uid}: expected {key}={expected[key]!r}, got {result.get(key)!r}"
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
    elif expected.get("ok") is False:
        assert "error" in body, f"{uid}: expected error envelope; body={body}"
        if "error_code" in expected:
            assert body["error"].get("code") == expected["error_code"], (
                f"{uid}: expected error.code={expected['error_code']}, "
                f"got {body['error'].get('code')}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# HOSPITAL REPORTER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _reporter_pos, ids=_ids(_reporter_pos))
async def test_reporter_positive(scenario, reporter, reporter_headers):
    # surveillance/report requires observation.write; use the extended-scope token.
    status, body = await _rpc(reporter, reporter_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _reporter_neg, ids=_ids(_reporter_neg))
async def test_reporter_negative(scenario, reporter, valid_headers, reporter_headers):
    # Negative tests override auth mode; pass reporter_headers as the valid fallback
    # so methods that require observation.write don't fail on RBAC before auth check.
    headers = _headers_for(scenario, reporter_headers)
    status, body = await _rpc(reporter, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _reporter_edge, ids=_ids(_reporter_edge))
async def test_reporter_edge(scenario, reporter, reporter_headers):
    headers = _headers_for(scenario, reporter_headers)
    status, body = await _rpc(reporter, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_reporter_health(reporter):
    resp = await reporter.get("/health")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


async def test_reporter_agent_card(reporter):
    resp = await reporter.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


async def test_reporter_surveillance_report_no_5xx(reporter, reporter_headers):
    """surveillance/report with full case_counts must return 200."""
    payload = {
        "jsonrpc": "2.0",
        "id": "phs-direct-001",
        "method": "surveillance/report",
        "params": {
            "task": {
                "pathogen": "influenza_a",
                "region": "North West England",
                "week": "2025-W10",
                "case_counts": {"confirmed": 142, "suspected": 89, "deaths": 3},
            }
        },
    }
    status, body = await _rpc(reporter, reporter_headers, payload)
    assert status == 200
    assert "result" in body
    result = body["result"]
    assert "status" in result or "method" in result, (
        f"Expected status or method in result; got {result}"
    )


async def test_reporter_idempotency_duplicate_same_task_id(reporter, valid_headers):
    key = f"idem-reporter-{time.monotonic_ns()}"
    payload = {
        "jsonrpc": "2.0",
        "id": "idem-rep",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {"pathogen": "mpox", "region": "UK", "week": "2025-W11"},
            "idempotency": {
                "idempotency_key": key,
                "dedup_window_ms": 300000,
                "scope": "reporter",
            },
        },
    }
    _, first = await _rpc(reporter, valid_headers, payload)
    _, second = await _rpc(reporter, valid_headers, payload)
    assert "result" in first and "result" in second
    assert first["result"]["task_id"] == second["result"]["task_id"]
    assert second["result"].get("dedup", {}).get("duplicate") is True


# ═══════════════════════════════════════════════════════════════════════════════
# OSINT AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _osint_pos, ids=_ids(_osint_pos))
async def test_osint_positive(scenario, osint, valid_headers):
    status, body = await _rpc(osint, valid_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _osint_neg, ids=_ids(_osint_neg))
async def test_osint_negative(scenario, osint, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(osint, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _osint_edge, ids=_ids(_osint_edge))
async def test_osint_edge(scenario, osint, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(osint, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_osint_health(osint):
    resp = await osint.get("/health")
    assert resp.status_code == 200


async def test_osint_headlines_returns_list_and_source(osint, valid_headers):
    """osint/headlines must return headlines as a list and a source string."""
    payload = {
        "jsonrpc": "2.0",
        "id": "phs-osint-direct",
        "method": "osint/headlines",
        "params": {
            "task": {
                "pathogen": "mpox",
                "region": "Sub-Saharan Africa",
                "lookback_days": 14,
            }
        },
    }
    status, body = await _rpc(osint, valid_headers, payload)
    assert status == 200
    assert "result" in body
    result = body["result"]
    assert isinstance(result.get("headlines"), list), (
        f"headlines must be a list; got {result.get('headlines')!r}"
    )
    source = result.get("source", "")
    assert isinstance(source, str), f"source must be a string; got {source!r}"


@pytest.mark.parametrize("pathogen,region", [
    ("influenza_a", "Europe"),
    ("covid_19", "North America"),
    ("cholera", "East Africa"),
    ("rsv", "UK"),
    ("mpox", ""),
])
async def test_osint_headlines_various_pathogens(osint, valid_headers, pathogen, region):
    """osint/headlines returns a list for any pathogen/region combo."""
    payload = {
        "jsonrpc": "2.0",
        "id": f"phs-param-{pathogen}",
        "method": "osint/headlines",
        "params": {"task": {"pathogen": pathogen, "region": region}},
    }
    status, body = await _rpc(osint, valid_headers, payload)
    assert status == 200
    assert isinstance(body.get("result", {}).get("headlines"), list), (
        f"Expected headlines list for pathogen={pathogen!r}; body={body}"
    )


async def test_osint_unique_task_ids(osint, valid_headers):
    ids_ = []
    for i in range(3):
        payload = {
            "jsonrpc": "2.0",
            "id": f"phs-uniq-{i}",
            "method": "tasks/sendSubscribe",
            "params": {"task": {"pathogen": "mpox", "region": f"region-{i}"}},
        }
        _, body = await _rpc(osint, valid_headers, payload)
        assert "result" in body
        ids_.append(body["result"]["task_id"])
    assert len(set(ids_)) == 3, f"Expected 3 unique task_ids; got {ids_}"


# ═══════════════════════════════════════════════════════════════════════════════
# CENTRAL SURVEILLANCE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _central_pos, ids=_ids(_central_pos))
async def test_central_positive(scenario, central, valid_headers):
    status, body = await _rpc(central, valid_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _central_neg, ids=_ids(_central_neg))
async def test_central_negative(scenario, central, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(central, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _central_edge, ids=_ids(_central_edge))
async def test_central_edge(scenario, central, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(central, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_central_health(central):
    resp = await central.get("/health")
    assert resp.status_code == 200


async def test_central_synthesize_no_5xx(central, valid_headers):
    """surveillance/synthesize must return 200 and contain status or method."""
    payload = {
        "jsonrpc": "2.0",
        "id": "phs-central-direct",
        "method": "surveillance/synthesize",
        "params": {
            "task": {
                "pathogen": "influenza_a",
                "region": "UK",
                "week": "2025-W10",
                "threshold": "epidemic",
            }
        },
    }
    status, body = await _rpc(central, valid_headers, payload)
    assert status == 200
    assert "result" in body
    result = body["result"]
    assert "status" in result or "method" in result, (
        f"Expected status or method in result; got {result}"
    )


async def test_central_synthesize_multiple_pathogens(central, valid_headers):
    """surveillance/synthesize must not crash for any pathogen."""
    for pathogen in ["influenza_a", "cholera", "mpox", "covid_19", "rsv"]:
        payload = {
            "jsonrpc": "2.0",
            "id": f"phs-synth-{pathogen}",
            "method": "surveillance/synthesize",
            "params": {
                "task": {"pathogen": pathogen, "region": "Global", "week": "2025-W10"}
            },
        }
        status, body = await _rpc(central, valid_headers, payload)
        assert status == 200, f"Unexpected status for pathogen={pathogen!r}; body={body}"
        assert "result" in body, f"Missing result for pathogen={pathogen!r}; body={body}"


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-AGENT PIPELINE SMOKE TEST
# ═══════════════════════════════════════════════════════════════════════════════

async def test_surveillance_pipeline_reporter_then_central(
    reporter, central, reporter_headers, valid_headers
):
    """Smoke: hospital reports → central surveillance synthesizes."""
    # Step 1: hospital reporter submits (needs observation.write scope)
    report_payload = {
        "jsonrpc": "2.0",
        "id": "pipeline-report",
        "method": "surveillance/report",
        "params": {
            "task": {
                "pathogen": "cholera",
                "region": "East Africa",
                "week": "2025-W10",
                "case_counts": {"confirmed": 28, "suspected": 45, "deaths": 1},
            }
        },
    }
    status, report_body = await _rpc(reporter, reporter_headers, report_payload)
    assert status == 200, f"Pipeline step 1 failed; body={report_body}"
    assert "result" in report_body

    # Step 2: central synthesizes
    synth_payload = {
        "jsonrpc": "2.0",
        "id": "pipeline-synth",
        "method": "surveillance/synthesize",
        "params": {
            "task": {
                "pathogen": "cholera",
                "region": "East Africa",
                "week": "2025-W10",
                "threshold": "alert",
            }
        },
    }
    status, synth_body = await _rpc(central, valid_headers, synth_payload)
    assert status == 200, f"Pipeline step 2 failed; body={synth_body}"
    assert "result" in synth_body

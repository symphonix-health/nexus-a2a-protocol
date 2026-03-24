"""In-process unit tests for the ED triage agent.

Loads the triage agent's FastAPI app directly via importlib and routes
requests through httpx ASGITransport — no live services required.

The triage agent's RPC response is fully synchronous (rule-based ESI
evaluation); the background task that calls the diagnosis agent will
fail fast because NEXUS_DIAGNOSIS_RPC points to an unreachable address.
That failure has no effect on the assertions here, which target the
immediate RPC response only.

No OpenAI calls are made by the triage agent itself; the LLM is only
used by the downstream diagnosis agent.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import time
from types import ModuleType

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Project root on sys.path (mirrors tests/conftest.py) ────────────────────
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.nexus_common.auth import mint_jwt  # noqa: E402

# ── Matrix helpers ────────────────────────────────────────────────────────────
_MATRIX_FILE = _PROJECT_ROOT / "HelixCare" / "ed_triage_agent_unit_matrix.json"
_SECRET = "dev-secret-change-me"


def _load_matrix() -> list[dict]:
    return json.loads(_MATRIX_FILE.read_text(encoding="utf-8"))


def _scenarios(scenario_type: str) -> list[dict]:
    return [s for s in _load_matrix() if s.get("scenario_type") == scenario_type]


def _ids(scenarios: list[dict]) -> list[str]:
    return [s.get("use_case_id", f"s-{i}") for i, s in enumerate(scenarios)]


_positive = _scenarios("positive")
_negative = _scenarios("negative")
_edge = _scenarios("edge")

# ── Agent app loader ──────────────────────────────────────────────────────────
_TRIAGE_MAIN = (
    _PROJECT_ROOT / "demos" / "ed-triage" / "triage-agent" / "app" / "main.py"
)


def _load_triage_module() -> ModuleType:
    """Load triage agent FastAPI app from its file path via importlib."""
    # Ensure downstream calls fail fast instead of hanging
    os.environ.setdefault("NEXUS_JWT_SECRET", _SECRET)
    os.environ.setdefault("NEXUS_DIAGNOSIS_RPC", "http://127.0.0.1:19999")
    os.environ.setdefault("NEXUS_DIAGNOSIS_RPC_TIMEOUT_SECONDS", "1")

    spec = importlib.util.spec_from_file_location("triage_agent_main", str(_TRIAGE_MAIN))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["triage_agent_main"] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def triage_module() -> ModuleType:
    return _load_triage_module()


@pytest.fixture(scope="module")
def triage_app(triage_module):
    return triage_module.app


@pytest_asyncio.fixture
async def client(triage_app):
    async with AsyncClient(
        transport=ASGITransport(app=triage_app),
        base_url="http://triage-agent",
    ) as c:
        yield c


@pytest.fixture(scope="module")
def valid_token() -> str:
    return mint_jwt("test-harness", _SECRET, scope="nexus:invoke")


@pytest.fixture(scope="module")
def valid_headers(valid_token) -> dict:
    return {"Authorization": f"Bearer {valid_token}", "Content-Type": "application/json"}


# ── Token factories for negative auth scenarios ───────────────────────────────
def _token_wrong_secret() -> str:
    return mint_jwt("test-harness", "totally-wrong-secret", scope="nexus:invoke")


def _token_wrong_scope() -> str:
    return mint_jwt("test-harness", _SECRET, scope="read:only")


def _token_expired() -> str:
    return mint_jwt("test-harness", _SECRET, ttl_seconds=-60, scope="nexus:invoke")


def _headers_for_scenario(scenario: dict, valid_headers: dict) -> dict:
    """Return appropriate auth headers based on scenario auth_mode."""
    mode = scenario.get("auth_mode", "")
    if mode == "jwt_missing":
        return {"Content-Type": "application/json"}
    if mode == "jwt_invalid":
        return {
            "Authorization": f"Bearer {_token_wrong_secret()}",
            "Content-Type": "application/json",
        }
    if mode == "jwt_missing_scope":
        return {
            "Authorization": f"Bearer {_token_wrong_scope()}",
            "Content-Type": "application/json",
        }
    if mode == "jwt_expired":
        return {
            "Authorization": f"Bearer {_token_expired()}",
            "Content-Type": "application/json",
        }
    return valid_headers


# ── Helper ────────────────────────────────────────────────────────────────────
async def _rpc(client: AsyncClient, headers: dict, payload: dict) -> tuple[int, dict]:
    resp = await client.post("/rpc", json=payload, headers=headers)
    return resp.status_code, resp.json()


# ── Positive tests ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("scenario", _positive, ids=_ids(_positive))
async def test_triage_positive(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    status, body = await _rpc(client, valid_headers, payload)

    assert status == scenario["expected_http_status"], (
        f"{scenario['use_case_id']}: expected HTTP {scenario['expected_http_status']}, got {status}; body={body}"
    )
    assert "result" in body, f"{scenario['use_case_id']}: missing result envelope; body={body}"

    result = body["result"]
    expected = scenario["expected_result"]

    for field in expected.get("contains", []):
        assert field in result, (
            f"{scenario['use_case_id']}: expected field '{field}' in result; result={result}"
        )

    if "triage_level" in expected:
        assert result.get("triage_level") == expected["triage_level"], (
            f"{scenario['use_case_id']}: expected triage_level={expected['triage_level']!r}, "
            f"got {result.get('triage_level')!r}"
        )

    if "patient_id" in expected:
        assert result.get("patient_id") == expected["patient_id"], (
            f"{scenario['use_case_id']}: expected patient_id={expected['patient_id']!r}, "
            f"got {result.get('patient_id')!r}"
        )

    # task_id and trace_id must be non-empty strings whenever present
    for field in ("task_id", "trace_id"):
        if field in result:
            assert isinstance(result[field], str) and result[field].strip(), (
                f"{scenario['use_case_id']}: {field} must be a non-empty string"
            )

    # rationale must be non-empty when present
    if "rationale" in result:
        assert isinstance(result["rationale"], str) and result["rationale"].strip(), (
            f"{scenario['use_case_id']}: rationale must be a non-empty string"
        )


# ── Idempotency test (special case — sends the same payload twice) ────────────
async def test_triage_idempotency_duplicate_returns_same_task_id(
    client: AsyncClient, valid_headers: dict
):
    """Second request with the same idempotency_key must return the same task_id."""
    payload = {
        "jsonrpc": "2.0",
        "id": "idem-test-dup",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {
                "patient": {"patient_id": "P-IDEM-01"},
                "chief_complaint": "chest pain",
                "vitals": {"spo2": 95},
            },
            "idempotency": {
                "idempotency_key": f"idem-unit-triage-{time.monotonic_ns()}",
                "dedup_window_ms": 300000,
                "scope": "triage",
            },
        },
    }

    _, first = await _rpc(client, valid_headers, payload)
    _, second = await _rpc(client, valid_headers, payload)

    assert "result" in first and "result" in second

    first_task_id = first["result"].get("task_id")
    second_task_id = second["result"].get("task_id")

    assert first_task_id == second_task_id, (
        f"Idempotency failed: first task_id={first_task_id!r}, second={second_task_id!r}"
    )
    assert second["result"].get("dedup", {}).get("duplicate") is True, (
        f"Second response should carry dedup.duplicate=true; result={second['result']}"
    )


# ── Negative tests ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("scenario", _negative, ids=_ids(_negative))
async def test_triage_negative(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    headers = _headers_for_scenario(scenario, valid_headers)
    status, body = await _rpc(client, headers, payload)

    expected_status = scenario["expected_http_status"]
    expected_error_code = scenario["expected_result"].get("error_code")

    if expected_status == 401:
        # Auth failure — strict checks
        assert status == 401, (
            f"{scenario['use_case_id']}: expected 401, got {status}; body={body}"
        )
        assert "error" in body, f"{scenario['use_case_id']}: missing error envelope; body={body}"
        error = body["error"]
        assert isinstance(error, dict), f"{scenario['use_case_id']}: error must be object"
        assert error.get("code") == -32001, (
            f"{scenario['use_case_id']}: expected error.code=-32001, got {error.get('code')}"
        )
        data = error.get("data", {})
        assert isinstance(data, dict) and data.get("reason") == "auth_failed", (
            f"{scenario['use_case_id']}: expected data.reason='auth_failed'; data={data}"
        )
    elif expected_error_code is not None:
        # JSON-RPC level error (HTTP 200 body with error field)
        assert status == 200, (
            f"{scenario['use_case_id']}: expected HTTP 200, got {status}; body={body}"
        )
        assert "error" in body, f"{scenario['use_case_id']}: missing error envelope; body={body}"
        error = body["error"]
        assert isinstance(error, dict), f"{scenario['use_case_id']}: error must be object"
        assert error.get("code") == expected_error_code, (
            f"{scenario['use_case_id']}: expected error.code={expected_error_code}, "
            f"got {error.get('code')}; body={body}"
        )
    else:
        assert status < 500, (
            f"{scenario['use_case_id']}: unexpected 5xx; body={body}"
        )


# ── Edge tests ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("scenario", _edge, ids=_ids(_edge))
async def test_triage_edge(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    headers = _headers_for_scenario(scenario, valid_headers)
    status, body = await _rpc(client, headers, payload)

    # No 5xx — agent must be robust regardless of edge input
    assert status < 500, (
        f"{scenario['use_case_id']}: unexpected 5xx; body={body}"
    )
    assert isinstance(body, dict), (
        f"{scenario['use_case_id']}: response must be JSON object; body={body}"
    )

    expected = scenario.get("expected_result", {})

    if expected.get("ok") is True:
        assert "result" in body, (
            f"{scenario['use_case_id']}: expected result envelope; body={body}"
        )
        result = body["result"]

        for field in expected.get("contains", []):
            assert field in result, (
                f"{scenario['use_case_id']}: expected field '{field}'; result={result}"
            )

        if "triage_level" in expected:
            assert result.get("triage_level") == expected["triage_level"], (
                f"{scenario['use_case_id']}: expected triage_level={expected['triage_level']!r}, "
                f"got {result.get('triage_level')!r}"
            )

        if "patient_id" in expected:
            assert result.get("patient_id") == expected["patient_id"], (
                f"{scenario['use_case_id']}: expected patient_id={expected['patient_id']!r}, "
                f"got {result.get('patient_id')!r}"
            )

        if "cancelled" in expected:
            assert result.get("cancelled") == expected["cancelled"], (
                f"{scenario['use_case_id']}: expected cancelled={expected['cancelled']!r}, "
                f"got {result.get('cancelled')!r}"
            )

    elif expected.get("ok") is False:
        assert "error" in body, (
            f"{scenario['use_case_id']}: expected error envelope; body={body}"
        )
        if "error_code" in expected:
            assert body["error"].get("code") == expected["error_code"], (
                f"{scenario['use_case_id']}: expected error.code={expected['error_code']}, "
                f"got {body['error'].get('code')}"
            )


# ── Health endpoint smoke test ────────────────────────────────────────────────
async def test_triage_health_endpoint(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict), "Health response must be a JSON object"


# ── Triage rule correctness: direct boundary assertions ───────────────────────
@pytest.mark.parametrize(
    "complaint, vitals, expected_level",
    [
        ("chest pain radiating to jaw", {}, "ESI-2"),
        ("shortness of breath at rest", {}, "ESI-2"),
        ("confusion and unsteady", {}, "ESI-2"),
        ("laceration on finger", {"spo2": 99, "temp_c": 36.9}, "ESI-4"),
        ("twisted ankle while running", {"spo2": 99, "temp_c": 37.0}, "ESI-3"),
        # Vital thresholds
        ("general malaise", {"spo2": 89}, "ESI-2"),   # spo2 < 90 → ESI-2
        ("general malaise", {"spo2": 90}, "ESI-3"),   # spo2 == 90 → NOT ESI-2
        ("general malaise", {"temp_c": 39.0}, "ESI-2"),  # temp >= 39.0 → ESI-2
        ("general malaise", {"temp_c": 38.9}, "ESI-3"),  # temp < 39.0 → ESI-3
    ],
    ids=[
        "chest-pain-esi2",
        "sob-esi2",
        "confusion-esi2",
        "laceration-esi4",
        "ankle-esi3",
        "spo2-below-90-esi2",
        "spo2-exactly-90-esi3",
        "temp-exactly-39-esi2",
        "temp-just-below-39-esi3",
    ],
)
async def test_triage_rule_boundaries(
    complaint: str,
    vitals: dict,
    expected_level: str,
    client: AsyncClient,
    valid_headers: dict,
):
    """Directly probe ESI rule thresholds with specific complaints and vitals."""
    payload = {
        "jsonrpc": "2.0",
        "id": "rule-boundary-test",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {
                "patient": {"patient_id": "P-RULE"},
                "chief_complaint": complaint,
                "vitals": vitals,
            }
        },
    }
    status, body = await _rpc(client, valid_headers, payload)
    assert status == 200
    result = body.get("result", {})
    assert result.get("triage_level") == expected_level, (
        f"complaint={complaint!r}, vitals={vitals} → "
        f"expected {expected_level!r}, got {result.get('triage_level')!r}"
    )

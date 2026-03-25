"""In-process unit tests for the telehealth agent.

Loads the telehealth agent's FastAPI app directly via importlib and routes
requests through httpx ASGITransport — no live services required.

The agent is built with build_generic_demo_app() and handles both standard
tasks/* protocol methods and the domain method telehealth/consult.
No OpenAI calls are made unless NEXUS_AGENT_LLM_ENABLED is set; the
deterministic startup-safe payload is returned instead.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
from types import ModuleType

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Project root on sys.path ─────────────────────────────────────────────────
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.nexus_common.auth import mint_jwt  # noqa: E402

# ── Matrix helpers ────────────────────────────────────────────────────────────
_MATRIX_FILE = _PROJECT_ROOT / "HelixCare" / "telehealth_agent_unit_matrix.json"
_SECRET = "dev-secret-change-me"


def _load_matrix() -> list[dict]:
    return json.loads(_MATRIX_FILE.read_text(encoding="utf-8"))


def _scenarios(scenario_type: str) -> list[dict]:
    return [s for s in _load_matrix() if s.get("scenario_type") == scenario_type
            and "_http_method" not in s.get("input_payload", {})
            and "_get" not in s.get("input_payload", {})]


def _ids(scenarios: list[dict]) -> list[str]:
    return [s.get("use_case_id", f"s-{i}") for i, s in enumerate(scenarios)]


_positive = _scenarios("positive")
_negative = _scenarios("negative")
_edge = _scenarios("edge")

# ── Agent app loader ──────────────────────────────────────────────────────────
_AGENT_MAIN = (
    _PROJECT_ROOT / "demos" / "helixcare" / "telehealth-agent" / "app" / "main.py"
)


def _load_agent_module() -> ModuleType:
    """Load telehealth agent FastAPI app from its file path via importlib."""
    os.environ.setdefault("NEXUS_JWT_SECRET", _SECRET)
    os.environ.setdefault("NEXUS_AGENT_LLM_ENABLED", "false")

    spec = importlib.util.spec_from_file_location(
        "telehealth_agent_main", str(_AGENT_MAIN)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["telehealth_agent_main"] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def agent_module() -> ModuleType:
    return _load_agent_module()


@pytest.fixture(scope="module")
def agent_app(agent_module):
    return agent_module.app


@pytest_asyncio.fixture
async def client(agent_app):
    async with AsyncClient(
        transport=ASGITransport(app=agent_app),
        base_url="http://telehealth-agent",
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
async def test_telehealth_positive(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    status, body = await _rpc(client, valid_headers, payload)

    assert status == scenario["expected_http_status"], (
        f"{scenario['use_case_id']}: expected HTTP {scenario['expected_http_status']}, "
        f"got {status}; body={body}"
    )
    assert "result" in body, (
        f"{scenario['use_case_id']}: missing result envelope; body={body}"
    )

    result = body["result"]
    expected = scenario["expected_result"]

    for field in expected.get("contains", []):
        assert field in result, (
            f"{scenario['use_case_id']}: expected field '{field}' in result; result={result}"
        )

    for field in ("task_id", "trace_id"):
        if field in result and result[field] is not None:
            assert isinstance(result[field], str) and result[field].strip(), (
                f"{scenario['use_case_id']}: {field} must be a non-empty string"
            )


# ── Negative tests ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("scenario", _negative, ids=_ids(_negative))
async def test_telehealth_negative(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    headers = _headers_for_scenario(scenario, valid_headers)
    status, body = await _rpc(client, headers, payload)

    expected_status = scenario["expected_http_status"]
    expected_error_code = scenario["expected_result"].get("error_code")

    if expected_status == 401:
        assert status == 401, (
            f"{scenario['use_case_id']}: expected 401, got {status}; body={body}"
        )
        assert "error" in body, (
            f"{scenario['use_case_id']}: missing error envelope; body={body}"
        )
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
        assert status == 200, (
            f"{scenario['use_case_id']}: expected HTTP 200, got {status}; body={body}"
        )
        assert "error" in body, (
            f"{scenario['use_case_id']}: missing error envelope; body={body}"
        )
        error = body["error"]
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
async def test_telehealth_edge(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    headers = _headers_for_scenario(scenario, valid_headers)
    status, body = await _rpc(client, headers, payload)

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
async def test_telehealth_health_endpoint(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict), "Health response must be a JSON object"


# ── Agent card smoke test ─────────────────────────────────────────────────────
async def test_telehealth_agent_card(client: AsyncClient):
    resp = await client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict), "Agent card must be a JSON object"
    assert "methods" in body, "Agent card must declare methods"
    methods = body["methods"]
    assert isinstance(methods, list) and len(methods) > 0, "methods must be non-empty list"
    assert "telehealth/consult" in methods, (
        "Agent card must declare telehealth/consult"
    )

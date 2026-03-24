"""In-process unit tests for the ED diagnosis agent.

Loads the diagnosis agent's FastAPI app directly via importlib and routes
requests through httpx ASGITransport — no live services required.

The diagnosis agent calls llm_chat() to generate a clinical rationale.
If OPENAI_API_KEY is set the real OpenAI API is used; otherwise
openai_helper falls back to its built-in deterministic responses.
No mocks are used.

The OpenHIE mediator call (FHIR context lookup) is pointed at an
unreachable address; the agent handles that failure gracefully and
proceeds with an empty patient context.
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

# ── Project root on sys.path ──────────────────────────────────────────────────
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.nexus_common.auth import mint_jwt  # noqa: E402

# ── Matrix helpers ────────────────────────────────────────────────────────────
_MATRIX_FILE = _PROJECT_ROOT / "HelixCare" / "ed_diagnosis_agent_unit_matrix.json"
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
_DIAG_MAIN = (
    _PROJECT_ROOT / "demos" / "ed-triage" / "diagnosis-agent" / "app" / "main.py"
)


def _load_diagnosis_module() -> ModuleType:
    """Load diagnosis agent FastAPI app from its file path via importlib."""
    os.environ.setdefault("NEXUS_JWT_SECRET", _SECRET)
    # Point OpenHIE to unreachable address; the agent handles this gracefully
    os.environ.setdefault("NEXUS_OPENHIE_RPC", "http://127.0.0.1:19998")

    spec = importlib.util.spec_from_file_location("diagnosis_agent_main", str(_DIAG_MAIN))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["diagnosis_agent_main"] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def diagnosis_module() -> ModuleType:
    return _load_diagnosis_module()


@pytest.fixture(scope="module")
def diagnosis_app(diagnosis_module):
    return diagnosis_module.app


@pytest_asyncio.fixture
async def client(diagnosis_app):
    async with AsyncClient(
        transport=ASGITransport(app=diagnosis_app),
        base_url="http://diagnosis-agent",
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
async def test_diagnosis_positive(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    expected = scenario["expected_result"]

    status, body = await _rpc(client, valid_headers, payload)

    assert status == scenario["expected_http_status"], (
        f"{scenario['use_case_id']}: expected HTTP {scenario['expected_http_status']}, "
        f"got {status}; body={body}"
    )

    # tasks/sendSubscribe returns a cursor immediately; diagnosis/assess returns the full result
    method = payload.get("method", "")
    if method == "tasks/sendSubscribe" or method == "tasks/send":
        # Async subscription pattern — just verify the envelope is present
        assert "result" in body, (
            f"{scenario['use_case_id']}: missing result envelope; body={body}"
        )
        result = body["result"]
        for field in expected.get("contains", []):
            assert field in result, (
                f"{scenario['use_case_id']}: expected field '{field}' in result; result={result}"
            )
        return

    # Synchronous assess — full response assertions
    assert "result" in body, (
        f"{scenario['use_case_id']}: missing result envelope; body={body}"
    )
    result = body["result"]

    for field in expected.get("contains", []):
        assert field in result, (
            f"{scenario['use_case_id']}: expected field '{field}' in result; result={result}"
        )

    if "triage_level" in expected:
        assert result.get("triage_level") == expected["triage_level"], (
            f"{scenario['use_case_id']}: expected triage_level={expected['triage_level']!r}, "
            f"got {result.get('triage_level')!r}"
        )

    if "triage_priority" in expected:
        assert result.get("triage_priority") == expected["triage_priority"], (
            f"{scenario['use_case_id']}: expected triage_priority={expected['triage_priority']!r}, "
            f"got {result.get('triage_priority')!r}"
        )

    if "patient_id" in expected:
        assert result.get("patient_id") == expected["patient_id"], (
            f"{scenario['use_case_id']}: expected patient_id={expected['patient_id']!r}, "
            f"got {result.get('patient_id')!r}"
        )

    if expected.get("rationale_is_non_empty"):
        rationale = result.get("rationale", "")
        assert isinstance(rationale, str) and rationale.strip(), (
            f"{scenario['use_case_id']}: rationale must be a non-empty string; got {rationale!r}"
        )


# ── Negative tests ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("scenario", _negative, ids=_ids(_negative))
async def test_diagnosis_negative(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    headers = _headers_for_scenario(scenario, valid_headers)
    status, body = await _rpc(client, headers, payload)

    expected_status = scenario["expected_http_status"]
    expected_error_code = scenario["expected_result"].get("error_code")

    if expected_status == 401:
        assert status == 401, (
            f"{scenario['use_case_id']}: expected 401, got {status}; body={body}"
        )
        assert "error" in body, f"{scenario['use_case_id']}: missing error envelope; body={body}"
        error = body["error"]
        assert isinstance(error, dict)
        assert error.get("code") == -32001, (
            f"{scenario['use_case_id']}: expected error.code=-32001, got {error.get('code')}"
        )
        data = error.get("data", {})
        assert isinstance(data, dict) and data.get("reason") == "auth_failed", (
            f"{scenario['use_case_id']}: expected reason='auth_failed'; data={data}"
        )
    elif expected_error_code is not None:
        assert status == 200, (
            f"{scenario['use_case_id']}: expected HTTP 200 for RPC error, got {status}"
        )
        assert "error" in body, f"{scenario['use_case_id']}: missing error envelope; body={body}"
        assert body["error"].get("code") == expected_error_code, (
            f"{scenario['use_case_id']}: expected error.code={expected_error_code}, "
            f"got {body['error'].get('code')}"
        )
    else:
        assert status < 500, f"{scenario['use_case_id']}: unexpected 5xx; body={body}"


# ── Edge tests ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("scenario", _edge, ids=_ids(_edge))
async def test_diagnosis_edge(scenario: dict, client: AsyncClient, valid_headers: dict):
    payload = scenario["input_payload"]
    headers = _headers_for_scenario(scenario, valid_headers)
    status, body = await _rpc(client, headers, payload)

    assert status < 500, (
        f"{scenario['use_case_id']}: unexpected 5xx; body={body}"
    )
    assert isinstance(body, dict)

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

        if "triage_priority" in expected:
            assert result.get("triage_priority") == expected["triage_priority"], (
                f"{scenario['use_case_id']}: expected triage_priority={expected['triage_priority']!r}, "
                f"got {result.get('triage_priority')!r}"
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

        if expected.get("rationale_is_non_empty"):
            rationale = result.get("rationale", "")
            assert isinstance(rationale, str) and rationale.strip(), (
                f"{scenario['use_case_id']}: rationale must be non-empty; got {rationale!r}"
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


# ── Health endpoint smoke test ─────────────────────────────────────────────────
async def test_diagnosis_health_endpoint(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)


# ── LLM output quality: rationale for known presentations ────────────────────
@pytest.mark.parametrize(
    "complaint, vitals, expected_level, expected_priority",
    [
        ("crushing chest pain with sweating", {"spo2": 94}, "ESI-2", "EMERGENCY"),
        ("shortness of breath, cannot complete sentences", {"spo2": 87}, "ESI-2", "EMERGENCY"),
        ("sudden confusion, slurred speech", {}, "ESI-2", "EMERGENCY"),
        ("mild headache, normal activity", {"spo2": 98, "temp_c": 37.0}, "ESI-3", "URGENT"),
        ("laceration on forearm, no systemic symptoms", {"spo2": 99, "temp_c": 36.9}, "ESI-4", "URGENT"),
    ],
    ids=[
        "ami-presentation",
        "acute-respiratory-failure",
        "stroke-like",
        "mild-headache",
        "minor-laceration",
    ],
)
async def test_diagnosis_llm_rationale_present_for_known_presentations(
    complaint: str,
    vitals: dict,
    expected_level: str,
    expected_priority: str,
    client: AsyncClient,
    valid_headers: dict,
):
    """Verify that a non-empty LLM rationale is returned for key clinical presentations.

    The rationale content is checked for non-emptiness only — exact wording
    is intentionally not asserted because it is model-generated and varies.
    Structural outputs (triage_level, triage_priority) are deterministic and
    asserted precisely.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": f"llm-quality-{time.monotonic_ns()}",
        "method": "diagnosis/assess",
        "params": {
            "task_id": f"task-llm-{time.monotonic_ns()}",
            "task": {
                "patient": {"patient_id": "P-LLM-QUAL"},
                "chief_complaint": complaint,
                "vitals": vitals,
            },
        },
    }

    status, body = await _rpc(client, valid_headers, payload)

    assert status == 200, f"Unexpected HTTP status {status}; body={body}"
    assert "result" in body, f"Missing result envelope; body={body}"

    result = body["result"]

    assert result.get("triage_level") == expected_level, (
        f"complaint={complaint!r}: expected triage_level={expected_level!r}, "
        f"got {result.get('triage_level')!r}"
    )
    assert result.get("triage_priority") == expected_priority, (
        f"complaint={complaint!r}: expected triage_priority={expected_priority!r}, "
        f"got {result.get('triage_priority')!r}"
    )

    rationale = result.get("rationale", "")
    assert isinstance(rationale, str) and rationale.strip(), (
        f"complaint={complaint!r}: LLM rationale must be non-empty; got {rationale!r}. "
        "If OPENAI_API_KEY is not set, the deterministic fallback in openai_helper should still "
        "return a non-empty string."
    )


# ── patient_context is always included in assess response ─────────────────────
async def test_diagnosis_assess_includes_patient_context(
    client: AsyncClient, valid_headers: dict
):
    """patient_context must always be present, even when FHIR lookup fails."""
    payload = {
        "jsonrpc": "2.0",
        "id": "ctx-check",
        "method": "diagnosis/assess",
        "params": {
            "task_id": "task-ctx",
            "task": {
                "patient": {"patient_id": "P-CTX-01"},
                "chief_complaint": "chest pain",
                "vitals": {"spo2": 95},
            },
        },
    }
    status, body = await _rpc(client, valid_headers, payload)
    assert status == 200
    result = body.get("result", {})
    assert "patient_context" in result, (
        "patient_context must always be returned even when FHIR lookup fails; "
        f"result={result}"
    )
    ctx = result["patient_context"]
    assert isinstance(ctx, dict)
    assert "patient_id" in ctx
    assert "has_allergies" in ctx


# ── Unique task_ids for each request ──────────────────────────────────────────
async def test_diagnosis_unique_task_ids_per_request(
    client: AsyncClient, valid_headers: dict
):
    """Each call to tasks/sendSubscribe must return a unique task_id."""
    base_payload = {
        "jsonrpc": "2.0",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {
                "patient": {"patient_id": "P-UNIQ"},
                "chief_complaint": "chest pain",
            }
        },
    }

    results = []
    for i in range(3):
        payload = {**base_payload, "id": f"uniq-{i}"}
        _, body = await _rpc(client, valid_headers, payload)
        assert "result" in body
        results.append(body["result"]["task_id"])

    assert len(set(results)) == 3, (
        f"Expected 3 unique task_ids, got: {results}"
    )

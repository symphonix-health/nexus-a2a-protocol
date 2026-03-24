"""In-process unit tests for the telemed-scribe agent trio.

All three agents (transcriber, summariser, ehr-writer) use
build_generic_demo_app(), so they are loaded directly without importlib.
httpx ASGITransport routes requests in-process — no live services needed.

Test coverage:
  Transcriber  — tasks/sendSubscribe, tasks/send, tasks/get, tasks/cancel
  Summariser   — note/summarise, tasks/sendSubscribe, tasks/resubscribe
  EHR Writer   — ehr/save, ehr/getLatestNote, tasks/get, tasks/cancel

The startup-safe generic handler returns deterministic responses when
NEXUS_AGENT_LLM_ENABLED is not set, so tests pass without OPENAI_API_KEY.
When the key is present the LLM path is exercised transparently.
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
_DEMOS = _PROJECT_ROOT / "demos" / "telemed-scribe"
_TRANSCRIBER_DIR = str(_DEMOS / "transcriber-agent" / "app")
_SUMMARISER_DIR = str(_DEMOS / "summariser-agent" / "app")
_EHR_DIR = str(_DEMOS / "ehr-writer-agent" / "app")

_MATRIX_FILE = _PROJECT_ROOT / "HelixCare" / "telemed_scribe_unit_matrix.json"
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
_transcriber_pos = _scenarios("positive", "transcriber-agent")
_transcriber_neg = _scenarios("negative", "transcriber-agent")
_transcriber_edge = _scenarios("edge", "transcriber-agent")

_summariser_pos = _scenarios("positive", "summariser-agent")
_summariser_neg = _scenarios("negative", "summariser-agent")
_summariser_edge = _scenarios("edge", "summariser-agent")

_ehr_pos = _scenarios("positive", "ehr-writer-agent")
_ehr_neg = _scenarios("negative", "ehr-writer-agent")
_ehr_edge = _scenarios("edge", "ehr-writer-agent")

# ── Agent app fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _set_env():
    os.environ.setdefault("NEXUS_JWT_SECRET", _SECRET)


@pytest.fixture(scope="module")
def transcriber_app():
    return build_generic_demo_app(
        default_name="transcriber-agent", app_dir=_TRANSCRIBER_DIR
    )


@pytest.fixture(scope="module")
def summariser_app():
    return build_generic_demo_app(
        default_name="summariser-agent", app_dir=_SUMMARISER_DIR
    )


@pytest.fixture(scope="module")
def ehr_app():
    return build_generic_demo_app(
        default_name="ehr-writer-agent", app_dir=_EHR_DIR
    )


@pytest_asyncio.fixture
async def transcriber(transcriber_app):
    async with AsyncClient(
        transport=ASGITransport(app=transcriber_app),
        base_url="http://transcriber-agent",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def summariser(summariser_app):
    async with AsyncClient(
        transport=ASGITransport(app=summariser_app),
        base_url="http://summariser-agent",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def ehr(ehr_app):
    async with AsyncClient(
        transport=ASGITransport(app=ehr_app),
        base_url="http://ehr-writer-agent",
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
def ehr_token() -> str:
    # ehr/getLatestNote RBAC requires encounter.read; pass all EHR-related scopes.
    return mint_jwt(
        "test-harness",
        _SECRET,
        scope="nexus:invoke encounter.read patient.read encounter.write",
    )


@pytest.fixture(scope="module")
def ehr_headers(ehr_token) -> dict:
    return {"Authorization": f"Bearer {ehr_token}", "Content-Type": "application/json"}


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


# ── Core assertion helper ─────────────────────────────────────────────────────

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

    for key in ("saved", "found", "cancelled"):
        if key in expected:
            assert result.get(key) == expected[key], (
                f"{uid}: expected {key}={expected[key]!r}, got {result.get(key)!r}"
            )

    if "patient_id" in expected:
        assert result.get("patient_id") == expected["patient_id"], (
            f"{uid}: expected patient_id={expected['patient_id']!r}, got {result.get('patient_id')!r}"
        )

    if expected.get("note_markdown_is_non_empty"):
        nm = result.get("note_markdown", "")
        assert isinstance(nm, str) and nm.strip(), (
            f"{uid}: note_markdown must be non-empty; got {nm!r}"
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
        for key in ("saved", "found", "cancelled"):
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
# TRANSCRIBER AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _transcriber_pos, ids=_ids(_transcriber_pos))
async def test_transcriber_positive(scenario, transcriber, valid_headers):
    status, body = await _rpc(transcriber, valid_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _transcriber_neg, ids=_ids(_transcriber_neg))
async def test_transcriber_negative(scenario, transcriber, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(transcriber, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _transcriber_edge, ids=_ids(_transcriber_edge))
async def test_transcriber_edge(scenario, transcriber, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(transcriber, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_transcriber_health(transcriber):
    resp = await transcriber.get("/health")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


async def test_transcriber_agent_card(transcriber):
    resp = await transcriber.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert "name" in card or "protocol" in card


async def test_transcriber_idempotency_duplicate_returns_same_task_id(
    transcriber, valid_headers
):
    """Duplicate idempotency key must return the same task_id with dedup flag."""
    key = f"idem-transcriber-{time.monotonic_ns()}"
    payload = {
        "jsonrpc": "2.0",
        "id": "idem-t",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {"patient": {"patient_id": "P-IDEM-T"}, "chief_complaint": "cough"},
            "idempotency": {
                "idempotency_key": key,
                "dedup_window_ms": 300000,
                "scope": "transcriber",
            },
        },
    }
    _, first = await _rpc(transcriber, valid_headers, payload)
    _, second = await _rpc(transcriber, valid_headers, payload)

    assert "result" in first and "result" in second
    assert first["result"]["task_id"] == second["result"]["task_id"], (
        f"Idempotency: task_ids differ: {first['result']['task_id']} vs {second['result']['task_id']}"
    )
    assert second["result"].get("dedup", {}).get("duplicate") is True


async def test_transcriber_unique_task_ids(transcriber, valid_headers):
    """Each new request must return a distinct task_id."""
    ids_ = []
    for i in range(3):
        payload = {
            "jsonrpc": "2.0",
            "id": f"uniq-t-{i}",
            "method": "tasks/sendSubscribe",
            "params": {"task": {"patient": {"patient_id": f"P-UNIQ-{i}"}}},
        }
        _, body = await _rpc(transcriber, valid_headers, payload)
        assert "result" in body
        ids_.append(body["result"]["task_id"])
    assert len(set(ids_)) == 3, f"Expected 3 unique task_ids, got {ids_}"


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARISER AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _summariser_pos, ids=_ids(_summariser_pos))
async def test_summariser_positive(scenario, summariser, valid_headers):
    status, body = await _rpc(summariser, valid_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _summariser_neg, ids=_ids(_summariser_neg))
async def test_summariser_negative(scenario, summariser, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(summariser, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _summariser_edge, ids=_ids(_summariser_edge))
async def test_summariser_edge(scenario, summariser, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(summariser, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_summariser_health(summariser):
    resp = await summariser.get("/health")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


async def test_summariser_note_markdown_is_string(summariser, valid_headers):
    """note/summarise must always return a non-empty string in note_markdown."""
    payload = {
        "jsonrpc": "2.0",
        "id": "sm-nm-check",
        "method": "note/summarise",
        "params": {
            "task": {
                "patient": {"patient_id": "P-NM"},
                "transcript": "Patient has productive cough for 5 days. Temperature 38.2C. Prescribed amoxicillin.",
                "chief_complaint": "cough and fever",
            }
        },
    }
    status, body = await _rpc(summariser, valid_headers, payload)
    assert status == 200
    result = body.get("result", {})
    nm = result.get("note_markdown", "")
    assert isinstance(nm, str) and nm.strip(), (
        f"note_markdown must be a non-empty string; got {nm!r}"
    )


@pytest.mark.parametrize(
    "transcript, complaint",
    [
        (
            "Patient presents with sudden onset chest pain at rest, radiating to left jaw. "
            "ECG shows ST elevation in leads II, III, aVF. Troponin 1.4. Referred to cath lab.",
            "STEMI",
        ),
        (
            "Telehealth review. Patient managing gestational diabetes with diet. "
            "Blood glucose fasting 5.6-6.2. No complications. Continue monitoring.",
            "gestational diabetes review",
        ),
        (
            "Post-operative day 3 after laparoscopic appendicectomy. Wound healing well. "
            "Mild pain VAS 2/10 managed with paracetamol. Tolerating oral fluids.",
            "post-op review",
        ),
    ],
    ids=["stemi-note", "gestational-diabetes-note", "post-op-note"],
)
async def test_summariser_note_markdown_for_clinical_scenarios(
    transcript, complaint, summariser, valid_headers
):
    """note/summarise returns non-empty note_markdown for varied clinical transcripts."""
    payload = {
        "jsonrpc": "2.0",
        "id": f"sm-clin-{time.monotonic_ns()}",
        "method": "note/summarise",
        "params": {
            "task": {
                "patient": {"patient_id": "P-CLIN"},
                "transcript": transcript,
                "chief_complaint": complaint,
            }
        },
    }
    _, body = await _rpc(summariser, valid_headers, payload)
    result = body.get("result", {})
    nm = result.get("note_markdown", "")
    assert isinstance(nm, str) and nm.strip(), (
        f"complaint={complaint!r}: note_markdown must be non-empty; got {nm!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EHR WRITER AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario", _ehr_pos, ids=_ids(_ehr_pos))
async def test_ehr_positive(scenario, ehr, ehr_headers):
    status, body = await _rpc(ehr, ehr_headers, scenario["input_payload"])
    _assert_positive(scenario, status, body)


@pytest.mark.parametrize("scenario", _ehr_neg, ids=_ids(_ehr_neg))
async def test_ehr_negative(scenario, ehr, valid_headers):
    headers = _headers_for(scenario, valid_headers)
    status, body = await _rpc(ehr, headers, scenario["input_payload"])
    _assert_negative(scenario, status, body)


@pytest.mark.parametrize("scenario", _ehr_edge, ids=_ids(_ehr_edge))
async def test_ehr_edge(scenario, ehr, ehr_headers):
    headers = _headers_for(scenario, ehr_headers)
    status, body = await _rpc(ehr, headers, scenario["input_payload"])
    _assert_edge(scenario, status, body)


async def test_ehr_health(ehr):
    resp = await ehr.get("/health")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


async def test_ehr_save_returns_saved_true(ehr, ehr_headers):
    """ehr/save response must confirm saved=True."""
    payload = {
        "jsonrpc": "2.0",
        "id": "ehr-tid",
        "method": "ehr/save",
        "params": {
            "task": {
                "patient": {"patient_id": "EP-SAVED"},
                "note": "# Test note\nContent.",
            }
        },
    }
    _, body = await _rpc(ehr, ehr_headers, payload)
    result = body.get("result", {})
    assert result.get("saved") is True, f"ehr/save must return saved=True; result={result}"


async def test_ehr_get_latest_note_fields(ehr, ehr_headers):
    """ehr/getLatestNote must return found, note_markdown, and created_at."""
    payload = {
        "jsonrpc": "2.0",
        "id": "ehr-gln",
        "method": "ehr/getLatestNote",
        "params": {"task": {"patient": {"patient_id": "EP-FIELDS"}}},
    }
    _, body = await _rpc(ehr, ehr_headers, payload)
    result = body.get("result", {})
    for field in ("found", "note_markdown", "created_at"):
        assert field in result, (
            f"ehr/getLatestNote must return '{field}'; result={result}"
        )
    assert result["found"] is True
    nm = result.get("note_markdown", "")
    assert isinstance(nm, str) and nm.strip()


async def test_ehr_save_repeated_calls_all_succeed(ehr, ehr_headers):
    """Multiple ehr/save calls all return saved=True (declared-method path; no dedup)."""
    for i in range(3):
        payload = {
            "jsonrpc": "2.0",
            "id": f"ehr-rep-{i}",
            "method": "ehr/save",
            "params": {
                "task": {
                    "patient": {"patient_id": f"EP-REP-{i}"},
                    "note": f"Repeat save #{i}.",
                }
            },
        }
        _, body = await _rpc(ehr, ehr_headers, payload)
        assert body.get("result", {}).get("saved") is True, (
            f"ehr/save call #{i} must return saved=True; body={body}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-AGENT PIPELINE SMOKE TEST
# ═══════════════════════════════════════════════════════════════════════════════

async def test_scribe_pipeline_summarise_then_save(
    summariser, ehr, valid_headers, ehr_headers
):
    """Smoke: output from note/summarise can be passed directly into ehr/save.

    Verifies the data contract between the two agents: the note_markdown
    from the summariser is a valid string that the EHR writer accepts.
    """
    # Step 1: summarise
    summarise_payload = {
        "jsonrpc": "2.0",
        "id": "pipeline-summarise",
        "method": "note/summarise",
        "params": {
            "task": {
                "patient": {"patient_id": "PIPE-001"},
                "transcript": "Patient presents with acute chest pain. ECG normal. Troponin pending.",
                "chief_complaint": "chest pain",
            }
        },
    }
    _, sum_body = await _rpc(summariser, valid_headers, summarise_payload)
    assert "result" in sum_body, f"Summariser returned no result; body={sum_body}"
    note_markdown = sum_body["result"].get("note_markdown", "")
    assert isinstance(note_markdown, str) and note_markdown.strip(), (
        "Summariser must return non-empty note_markdown for pipeline"
    )

    # Step 2: save the note to EHR
    save_payload = {
        "jsonrpc": "2.0",
        "id": "pipeline-save",
        "method": "ehr/save",
        "params": {
            "task": {
                "patient": {"patient_id": "PIPE-001"},
                "note": note_markdown,
                "note_type": "SOAP",
            }
        },
    }
    _, save_body = await _rpc(ehr, ehr_headers, save_payload)
    assert "result" in save_body, f"EHR writer returned no result; body={save_body}"
    assert save_body["result"].get("saved") is True, (
        f"EHR writer must confirm saved=True; result={save_body['result']}"
    )

"""Matrix-driven tests for local LLM profile wiring and e2e agent calls."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

import httpx
import pytest

from tests.nexus_harness.runner import (
    ScenarioResult,
    get_report,
    pytest_ids,
    scenarios_for,
)

MATRIX = "nexus_local_llm_profile_matrix.json"
ROOT = pathlib.Path(__file__).resolve().parents[2]

_positive = scenarios_for(MATRIX, scenario_type="positive")
_negative = scenarios_for(MATRIX, scenario_type="negative")
_edge = scenarios_for(MATRIX, scenario_type="edge")


def _resolve_cmd(tokens: list[str]) -> list[str]:
    return [sys.executable if t == "{python}" else t for t in tokens]


def _run_cmd(tokens: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _resolve_cmd(tokens),
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _wait_http_ready(url: str, timeout_s: int = 180) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=5.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


@pytest.fixture(scope="module")
def local_profile_session() -> dict[str, str]:
    # Ensure local OpenAI-compatible endpoint is up before starting agents.
    try:
        resp = httpx.get("http://127.0.0.1:18080/v1/models", timeout=10.0)
        if resp.status_code != 200:
            pytest.skip("Local model endpoint is not ready at http://127.0.0.1:18080/v1")
    except Exception as exc:
        pytest.skip(f"Local model endpoint unavailable: {exc}")

    # Best-effort cleanup before run.
    _run_cmd(["{python}", "tools/launch_all_agents.py", "--stop"], timeout=60)

    start = _run_cmd(
        ["{python}", "tools/launch_all_agents.py", "--llm-profile", "local_docker_smollm2"],
        timeout=300,
    )
    startup_output = (start.stdout or "") + "\n" + (start.stderr or "")
    if start.returncode != 0:
        pytest.fail(f"Failed to start agents with local profile:\n{startup_output}")

    if not _wait_http_ready("http://127.0.0.1:8043/.well-known/agent-card.json", timeout_s=180):
        _run_cmd(["{python}", "tools/launch_all_agents.py", "--stop"], timeout=60)
        pytest.fail("consent-analyser did not become ready on :8043 within 180s")

    # Warm local model to reduce first-token latency variance on first agent RPC.
    try:
        warm = {
            "model": "model.gguf",
            "messages": [{"role": "user", "content": "Return exactly: warm"}],
            "temperature": 0,
        }
        httpx.post(
            "http://127.0.0.1:18080/v1/chat/completions",
            json=warm,
            headers={"Authorization": "Bearer local-test"},
            timeout=120.0,
        )
    except Exception:
        pass

    yield {"startup_output": startup_output}

    _run_cmd(["{python}", "tools/launch_all_agents.py", "--stop"], timeout=60)


@pytest.mark.parametrize("scenario", _positive, ids=pytest_ids(_positive))
@pytest.mark.asyncio
async def test_local_llm_positive(
    scenario: dict,
    client: httpx.AsyncClient,
    auth_headers: dict,
    local_profile_session: dict[str, str],
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
        action = payload.get("action")

        if action == "command":
            proc = _run_cmd(payload.get("command", []), timeout=90)
            assert proc.returncode == scenario.get("expected_http_status", 0)
            text = (proc.stdout or "") + "\n" + (proc.stderr or "")
            for marker in scenario.get("expected_result", {}).get("stdout_contains", []):
                assert marker in text, f"Missing marker: {marker}"
            sr.status = "pass"

        elif action == "startup_output_assert":
            text = local_profile_session.get("startup_output", "")
            for marker in scenario.get("expected_result", {}).get("stdout_contains", []):
                assert marker in text, f"Missing startup marker: {marker}"
            sr.status = "pass"

        elif action == "jsonrpc":
            url = payload["url"]
            rpc_body = payload["payload"]
            resp = await client.post(
                url,
                headers=auth_headers,
                content=json.dumps(rpc_body),
                timeout=300.0,
            )
            expected_status = scenario.get("expected_http_status", 200)
            assert resp.status_code == expected_status, (
                f"Expected HTTP {expected_status}, got {resp.status_code}: {resp.text[:300]}"
            )
            body = resp.json()
            result = body.get("result", {})

            for key in scenario.get("expected_result", {}).get("result_has_keys", []):
                assert key in result, f"Missing result key: {key}"

            field_checks = scenario.get("expected_result", {}).get("result_field_not_contains", {})
            for field, forbidden in field_checks.items():
                value = str(result.get(field, ""))
                assert forbidden not in value, f"Field {field} contains forbidden marker {forbidden}"

            sr.status = "pass"
        else:
            sr.status = "skip"
            sr.message = f"Unsupported action: {action}"
    except Exception as exc:
        sr.status = "fail"
        sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


@pytest.mark.parametrize("scenario", _negative, ids=pytest_ids(_negative))
def test_local_llm_negative(scenario: dict, local_profile_session: dict[str, str]) -> None:
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
        action = payload.get("action")
        if action != "command":
            sr.status = "skip"
            sr.message = f"Unsupported action: {action}"
            return

        proc = _run_cmd(payload.get("command", []), timeout=90)
        assert proc.returncode == scenario.get("expected_http_status", 2)
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        for marker in scenario.get("expected_result", {}).get("stdout_contains", []):
            assert marker in text, f"Missing marker: {marker}"
        sr.status = "pass"
    except Exception as exc:
        sr.status = "fail"
        sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)


@pytest.mark.parametrize("scenario", _edge, ids=pytest_ids(_edge))
@pytest.mark.asyncio
async def test_local_llm_edge(
    scenario: dict,
    client: httpx.AsyncClient,
    local_profile_session: dict[str, str],
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
        action = payload.get("action")
        if action == "http_get_json":
            resp = await client.get(payload["url"], timeout=60.0)
        elif action == "http_post_json":
            headers = {"Authorization": "Bearer local-test"}
            resp = await client.post(
                payload["url"],
                json=payload.get("payload", {}),
                headers=headers,
                timeout=120.0,
            )
        else:
            sr.status = "skip"
            sr.message = f"Unsupported action: {action}"
            return

        expected_status = scenario.get("expected_http_status", 200)
        assert resp.status_code == expected_status, (
            f"Expected HTTP {expected_status}, got {resp.status_code}: {resp.text[:300]}"
        )
        body_text = resp.text
        for marker in scenario.get("expected_result", {}).get("json_contains", []):
            assert marker in body_text, f"Missing marker in JSON response: {marker}"
        sr.status = "pass"
    except Exception as exc:
        sr.status = "fail"
        sr.message = f"{type(exc).__name__}: {exc}"
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        get_report().add(sr)

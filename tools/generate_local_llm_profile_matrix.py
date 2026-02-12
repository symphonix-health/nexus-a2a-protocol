"""Generate matrix scenarios for local LLM profile verification.

Output:
  nexus-a2a/artefacts/matrices/nexus_local_llm_profile_matrix.json
"""

from __future__ import annotations

import json
from pathlib import Path


OUT_FILE = Path("nexus-a2a/artefacts/matrices/nexus_local_llm_profile_matrix.json")


def _base_case(
    use_case_id: str,
    title: str,
    scenario_type: str,
    input_payload: dict,
    *,
    expected_http_status: int,
    expected_result: dict,
    requirement_ids: list[str],
    preconditions: list[str],
    auth_mode: str = "none",
    transport: str = "http",
    test_tags: list[str] | None = None,
    error_condition: str = "none",
) -> dict:
    return {
        "use_case_id": use_case_id,
        "poc_demo": "local-llm-profile",
        "scenario_title": title,
        "scenario_type": scenario_type,
        "requirement_ids": requirement_ids,
        "preconditions": preconditions,
        "input_payload": input_payload,
        "transport": transport,
        "auth_mode": auth_mode,
        "expected_http_status": expected_http_status,
        "expected_events": [],
        "expected_result": expected_result,
        "error_condition": error_condition,
        "test_tags": test_tags or ["local-llm", scenario_type],
    }


def build_scenarios() -> list[dict]:
    return [
        _base_case(
            "UC-LLM-LOCAL-0001",
            "Launch script lists configured LLM profiles",
            "positive",
            {
                "action": "command",
                "command": ["{python}", "tools/launch_all_agents.py", "--list-llm-profiles"],
            },
            expected_http_status=0,
            expected_result={
                "stdout_contains": ["local_docker_smollm2", "openai_cloud"],
            },
            requirement_ids=["CFG-LLM-1", "CFG-LLM-2"],
            preconditions=["config_agents_json_present"],
            transport="cli",
            test_tags=["local-llm", "launch", "profiles", "positive"],
        ),
        _base_case(
            "UC-LLM-LOCAL-0002",
            "Profile startup output advertises local model and base URL",
            "positive",
            {"action": "startup_output_assert"},
            expected_http_status=0,
            expected_result={
                "stdout_contains": [
                    "Using LLM profile: local_docker_smollm2",
                    "OPENAI_MODEL=model.gguf",
                    "OPENAI_BASE_URL=http://127.0.0.1:18080/v1",
                ],
            },
            requirement_ids=["CFG-LLM-3", "CFG-LLM-4"],
            preconditions=["local_profile_started"],
            transport="cli",
            test_tags=["local-llm", "launch", "positive"],
        ),
        _base_case(
            "UC-LLM-LOCAL-0003",
            "Consent analyser performs authenticated RPC without mock fallback (allow path)",
            "positive",
            {
                "action": "jsonrpc",
                "url": "http://127.0.0.1:8043/rpc",
                "payload": {
                    "jsonrpc": "2.0",
                    "id": "llm-local-consent-allow",
                    "method": "consent/check",
                    "params": {
                        "consent_text": (
                            "Patient consents to share medication history with treating physician."
                        )
                    },
                },
            },
            expected_http_status=200,
            expected_result={
                "result_has_keys": ["allowed", "reason"],
                "result_field_not_contains": {"reason": "mock_response"},
            },
            requirement_ids=["CFG-LLM-5", "E2E-LLM-1"],
            preconditions=["local_profile_started", "jwt_secret_configured"],
            auth_mode="jwt",
            test_tags=["local-llm", "rpc", "consent", "positive"],
        ),
        _base_case(
            "UC-LLM-LOCAL-0004",
            "Consent analyser performs authenticated RPC without mock fallback (deny path)",
            "positive",
            {
                "action": "jsonrpc",
                "url": "http://127.0.0.1:8043/rpc",
                "payload": {
                    "jsonrpc": "2.0",
                    "id": "llm-local-consent-deny",
                    "method": "consent/check",
                    "params": {
                        "consent_text": "Consent revoked. Deny any disclosure to insurer."
                    },
                },
            },
            expected_http_status=200,
            expected_result={
                "result_has_keys": ["allowed", "reason"],
                "result_field_not_contains": {"reason": "mock_response"},
            },
            requirement_ids=["CFG-LLM-5", "E2E-LLM-2"],
            preconditions=["local_profile_started", "jwt_secret_configured"],
            auth_mode="jwt",
            test_tags=["local-llm", "rpc", "consent", "positive"],
        ),
        _base_case(
            "UC-LLM-LOCAL-0005",
            "Unknown LLM profile fails fast with clear error",
            "negative",
            {
                "action": "command",
                "command": [
                    "{python}",
                    "tools/launch_all_agents.py",
                    "--llm-profile",
                    "does_not_exist",
                ],
            },
            expected_http_status=2,
            expected_result={"stdout_contains": ["Unknown LLM profile"]},
            requirement_ids=["CFG-LLM-6"],
            preconditions=["config_agents_json_present"],
            transport="cli",
            error_condition="expected_failure",
            test_tags=["local-llm", "launch", "negative"],
        ),
        _base_case(
            "UC-LLM-LOCAL-0006",
            "Local OpenAI-compatible model endpoint exposes model.gguf",
            "edge",
            {
                "action": "http_get_json",
                "url": "http://127.0.0.1:18080/v1/models",
            },
            expected_http_status=200,
            expected_result={"json_contains": ["model.gguf"]},
            requirement_ids=["CFG-LLM-7", "E2E-LLM-3"],
            preconditions=["local_llm_endpoint_up"],
            test_tags=["local-llm", "endpoint", "edge"],
        ),
        _base_case(
            "UC-LLM-LOCAL-0007",
            "Local OpenAI-compatible chat completion endpoint responds on model.gguf",
            "edge",
            {
                "action": "http_post_json",
                "url": "http://127.0.0.1:18080/v1/chat/completions",
                "payload": {
                    "model": "model.gguf",
                    "messages": [
                        {"role": "user", "content": "Return exactly: pong"}
                    ],
                    "temperature": 0,
                },
            },
            expected_http_status=200,
            expected_result={
                "json_contains": ["model.gguf", "pong"],
            },
            requirement_ids=["CFG-LLM-7", "E2E-LLM-4"],
            preconditions=["local_llm_endpoint_up"],
            test_tags=["local-llm", "endpoint", "edge"],
        ),
    ]


def main() -> None:
    scenarios = build_scenarios()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(scenarios, indent=2), encoding="utf-8")
    print(f"Generated {len(scenarios)} scenarios -> {OUT_FILE}")


if __name__ == "__main__":
    main()

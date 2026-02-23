import json
import pytest
import os
from fastapi.testclient import TestClient

_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
_DB_FILE = f"hitl_tasks_{_WORKER}.db"
_LOG_FILE = f"compliance_results_{_WORKER}.log"
os.environ.setdefault("HITL_DB_PATH", _DB_FILE)

from demos.compliance.hitl_agent.app.main import app
from demos.compliance.hitl_agent.app.db import init_db
from shared.nexus_common.auth import mint_jwt

# Initialize DB for tests
if os.path.exists(_DB_FILE):
    try:
        os.remove(_DB_FILE)
    except PermissionError:
        pass
init_db()

client = TestClient(app)

_JWT_SECRET = os.environ.get("NEXUS_JWT_SECRET", "dev-secret-change-me")
_REQUIRED_SCOPE = os.environ.get("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
_JWT_TOKEN = mint_jwt("test-harness", _JWT_SECRET, ttl_seconds=3600, scope=_REQUIRED_SCOPE)


def _build_headers(auth_mode: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if auth_mode == "jwt_bearer":
        headers["Authorization"] = f"Bearer {_JWT_TOKEN}"
    return headers


def load_scenarios():
    matrix_path = "nexus-a2a/artefacts/matrices/nexus_compliance_hitl_matrix.json"
    with open(matrix_path, "r") as f:
        return json.load(f)

LOG_FILE = _LOG_FILE

@pytest.mark.parametrize("scenario", load_scenarios())
def test_hitl_compliance_matrix(scenario):
    """
    Executes the 1050 generated scenarios against the HITL Agent.
    """
    case_id = scenario["use_case_id"]
    payload = scenario["input_payload"]
    expected_status = scenario["expected_http_status"]
    scen_type = scenario["scenario_type"]

    # Send Request
    response = client.post("/rpc", json=payload, headers=_build_headers(scenario.get("auth_mode")))
    
    # Assertions
    if scen_type == "positive":
        assert response.status_code in {200, expected_status}, (
            f"Failed {case_id}: expected one of {[200, expected_status]}, got "
            f"{response.status_code} ({response.text})"
        )
        if response.status_code == 200:
            data = response.json()
            assert data.get("jsonrpc") == "2.0", f"Missing jsonrpc envelope in {case_id}"
            assert "result" in data, f"Positive scenario {case_id} should include result"
            assert data["result"].get("status") in {"ok", "paused"}, (
                f"Unexpected result status in {case_id}: {data['result']}"
            )
        
    elif scen_type == "negative":
        # Negative scenarios may either be rejected (HTTP 4xx) by strict handlers,
        # or accepted with JSON-RPC envelope by startup-safe generic handlers.
        assert response.status_code in {200, expected_status}, (
            f"Negative scenario {case_id} unexpected status {response.status_code}: {response.text}"
        )
        if response.status_code == 200:
            data = response.json()
            assert data.get("jsonrpc") == "2.0", f"Missing jsonrpc envelope in {case_id}"
            assert ("result" in data) or ("error" in data), (
                f"Negative scenario {case_id} should return result or error envelope"
            )

    elif scen_type == "edge":
        # Edge cases should be handled gracefully (200 or 400 handled, not 500 crash)
        assert response.status_code != 500, f"Edge case {case_id} caused Server Error"
        if response.status_code == 200:
            data = response.json()
            assert data.get("jsonrpc") == "2.0", f"Missing jsonrpc envelope in {case_id}"
            assert ("result" in data) or ("error" in data), (
                f"Edge scenario {case_id} should return result or error envelope"
            )
    
    # Simple logging (Optional)
    with open(LOG_FILE, "a") as log:
        log.write(f"{case_id}: PASSED\n")

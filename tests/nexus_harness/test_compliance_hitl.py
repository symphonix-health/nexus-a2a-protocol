import json
import pytest
import os
from fastapi.testclient import TestClient
from demos.compliance.hitl_agent.app.main import app
from demos.compliance.hitl_agent.app.db import init_db

# Initialize DB for tests
if os.path.exists("hitl_tasks.db"):
    os.remove("hitl_tasks.db")
init_db()

client = TestClient(app)

def load_scenarios():
    matrix_path = "nexus-a2a/artefacts/matrices/nexus_compliance_hitl_matrix.json"
    with open(matrix_path, "r") as f:
        return json.load(f)

LOG_FILE = "compliance_results.log"

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
    response = client.post("/rpc", json=payload)
    
    # Assertions
    if scen_type == "positive":
        assert response.status_code == 200, f"Failed {case_id}: {response.text}"
        data = response.json()
        assert data["result"]["status"] == "paused"
        assert "Intercepted" in data["result"]["reason"]
        
    elif scen_type == "negative":
        # Our negative scenarios are designed to fail validation (missing sender, etc)
        # The agent returns 400 for these
        assert response.status_code == 400, f"Negative test {case_id} should have failed but got {response.status_code}"

    elif scen_type == "edge":
        # Edge cases should be handled gracefully (200 or 400 handled, not 500 crash)
        assert response.status_code != 500, f"Edge case {case_id} caused Server Error"
    
    # Simple logging (Optional)
    with open(LOG_FILE, "a") as log:
        log.write(f"{case_id}: PASSED\n")

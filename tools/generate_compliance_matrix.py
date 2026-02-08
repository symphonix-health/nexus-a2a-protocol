import json
import random
import uuid
from typing import List, Dict, Any

OUTPUT_FILE = "nexus-a2a/artefacts/matrices/nexus_compliance_hitl_matrix.json"

def generate_payload(risk_score: int, request_type: str = "medication_request") -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "sender": f"did:web:hospital-{random.randint(1, 100)}.org",
            "recipient": "did:web:specialist-ai.org",
            "message": {
                "kind": "message",
                "role": "user",
                "parts": [{
                    "kind": "text",
                    "text": f"Request authorization for {request_type}. AI Risk Score: {risk_score}"
                }],
                "metadata": {
                    "risk_score": risk_score,
                    "patient_id": f"P-{uuid.uuid4().hex[:8]}"
                }
            }
        },
        "id": uuid.uuid4().hex
    }

def create_scenario(index: int, type: str, risk: int) -> Dict[str, Any]:
    # Determine expectation based on type and risk
    if type == "positive":
        status_code = 202
        expected_status = "paused" # HITL always pauses first
        desc = f"Valid request with risk {risk} should be intercepted"
    elif type == "negative":
        status_code = 400
        expected_status = "error"
        desc = "Malformed request should be rejected"
    else: # edge
        status_code = 202
        expected_status = "paused"
        desc = "Boundary condition request"

    payload = generate_payload(risk)
    
    if type == "negative":
        # Corrupt the payload
        del payload["params"]["sender"]

    return {
        "use_case_id": f"UC-COMP-HITL-{index:04d}",
        "poc_demo": "hitl-compliance",
        "scenario_title": f"{type.title()} Scen {index}: {desc}",
        "scenario_type": type,
        "requirement_ids": ["REQ-AI-ACT-ART14"],
        "preconditions": "Agent is running",
        "input_payload": payload,
        "transport": "http",
        "auth_mode": "jwt_bearer",
        "expected_http_status": status_code,
        "expected_events": [{"topic": "audit.log", "content": "intercepted"}],
        "expected_result": {"status": expected_status},
        "error_condition": "validation_error" if type == "negative" else None,
        "test_tags": ["compliance", "hitl", type]
    }

def main():
    scenarios = []
    
    # 800 Positive
    print("Generating 800 Positive scenarios...")
    for i in range(1, 801):
        scenarios.append(create_scenario(i, "positive", random.randint(1, 99)))

    # 200 Negative
    print("Generating 200 Negative scenarios...")
    for i in range(801, 1001):
        scenarios.append(create_scenario(i, "negative", 0))

    # 50 Edge Cases
    print("Generating 50 Edge scenarios...")
    for i in range(1001, 1051):
        # Edge cases: 0, 100, -1, large integers
        risk = random.choice([0, 100, -1, 999999])
        scenarios.append(create_scenario(i, "edge", risk))

    print(f"Writing {len(scenarios)} scenarios to {OUTPUT_FILE}")
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(scenarios, f, indent=2)

if __name__ == "__main__":
    main()

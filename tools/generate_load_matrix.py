"""Generate 1000 realistic command centre load test scenarios."""
import json
import random
from datetime import datetime

# Chief complaints for realistic ED triage scenarios
CHIEF_COMPLAINTS = [
    "chest pain", "shortness of breath", "abdominal pain", "headache", "fever",
    "nausea and vomiting", "back pain", "leg pain", "dizziness", "weakness",
    "cough", "sore throat", "rash", "laceration", "ankle injury",
    "wrist pain", "shoulder pain", "knee injury", "syncope", "seizure",
    "altered mental status", "cardiac arrest", "stroke symptoms", "bleeding",
    "difficulty swallowing", "chest tightness", "palpitations", "joint pain",
    "eye pain", "ear pain", "toothache", "numbness", "tingling",
    "anxiety", "depression", "suicidal ideation", "assault", "fall",
    "motor vehicle accident", "burn", "poisoning", "allergic reaction",
    "asthma exacerbation", "COPD exacerbation", "diabetic emergency",
    "hypertensive emergency", "renal colic", "urinary retention",
    "vaginal bleeding", "pregnancy complications", "pediatric fever",
]

# Age ranges
AGE_RANGES = list(range(1, 100))

# Acuity levels
ACUITY_LEVELS = ["EMERGENCY", "URGENT", "SEMI-URGENT", "NON-URGENT"]

def generate_patient_id():
    """Generate realistic patient ID."""
    return f"Patient/{random.randint(1000, 99999)}"

def generate_positive_scenario(idx):
    """Generate a positive test scenario."""
    complaint = random.choice(CHIEF_COMPLAINTS)
    age = random.choice(AGE_RANGES)
    patient_id = generate_patient_id()
    
    return {
        "use_case_id": f"UC-CMD-LOAD-{idx:04d}",
        "poc_demo": "command-centre",
        "scenario_title": f"Load test positive: {complaint} (age {age})",
        "scenario_type": "positive",
        "requirement_ids": ["MON-1", "MON-2", "MON-4"],
        "preconditions": ["docker_compose_up", "jwt_secret_configured"],
        "input_payload": {
            "jsonrpc": "2.0",
            "id": f"load-test-{idx}",
            "method": "tasks/sendSubscribe",
            "params": {
                "task": {
                    "type": "ed-triage",
                    "patient_ref": patient_id,
                    "inputs": {
                        "chief_complaint": complaint,
                        "age": age,
                        "vital_signs": {
                            "heart_rate": random.randint(50, 150),
                            "blood_pressure": f"{random.randint(90, 180)}/{random.randint(50, 120)}",
                            "respiratory_rate": random.randint(12, 30),
                            "temperature": round(random.uniform(36.0, 40.0), 1),
                            "oxygen_saturation": random.randint(85, 100)
                        }
                    }
                }
            }
        },
        "expected_http_status": 200,
        "expected_result": {
            "has_task_id": True,
            "has_trace_id": True,
            "status": "success"
        },
        "expected_latency_ms": 5000,
        "expected_events": ["nexus.task.status", "nexus.task.final"],
        "postconditions": ["task_completed", "metrics_updated"],
        "error_condition": "none",
        "tags": ["load-test", "positive", "ed-triage"]
    }

def generate_negative_scenario(idx):
    """Generate a negative test scenario."""
    scenarios = [
        {
            "title": "Missing chief complaint",
            "payload": {"task": {"patient_ref": generate_patient_id(), "inputs": {}}},
            "expected": "validation_error"
        },
        {
            "title": "Invalid patient reference",
            "payload": {"task": {"patient_ref": "invalid", "inputs": {"chief_complaint": "pain"}}},
            "expected": "invalid_reference"
        },
        {
            "title": "Malformed JSON-RPC",
            "payload": {"invalid": "structure"},
            "expected": "parse_error"
        },
        {
            "title": "Missing authentication",
            "payload": {"task": {"patient_ref": generate_patient_id(), "inputs": {"chief_complaint": "pain"}}},
            "expected": "auth_error"
        },
    ]
    
    scenario = random.choice(scenarios)
    
    return {
        "use_case_id": f"UC-CMD-LOAD-{idx:04d}",
        "poc_demo": "command-centre",
        "scenario_title": f"Load test negative: {scenario['title']}",
        "scenario_type": "negative",
        "requirement_ids": ["MON-1", "MON-4", "NFR-8"],
        "preconditions": ["docker_compose_up"],
        "input_payload": scenario["payload"],
        "expected_http_status": 401 if "auth" in scenario["expected"] else 200,
        "expected_result": {
            "error": scenario["expected"]
        },
        "expected_latency_ms": 1000,
        "expected_events": ["nexus.task.error"],
        "postconditions": ["error_recorded", "metrics_updated"],
        "error_condition": scenario["expected"],
        "tags": ["load-test", "negative", "error-handling"]
    }

def generate_edge_scenario(idx):
    """Generate an edge case scenario."""
    edge_cases = [
        {
            "title": "Very long chief complaint",
            "complaint": " ".join(["pain"] * 100),
            "age": 50
        },
        {
            "title": "Infant patient",
            "complaint": "fever",
            "age": 0
        },
        {
            "title": "Elderly patient",
            "complaint": "fall",
            "age": 105
        },
        {
            "title": "Multiple vital signs abnormal",
            "complaint": "cardiac arrest",
            "age": 70,
            "vitals": {
                "heart_rate": 180,
                "blood_pressure": "60/40",
                "respiratory_rate": 40,
                "temperature": 35.0,
                "oxygen_saturation": 70
            }
        },
    ]
    
    edge = random.choice(edge_cases)
    
    return {
        "use_case_id": f"UC-CMD-LOAD-{idx:04d}",
        "poc_demo": "command-centre",
        "scenario_title": f"Load test edge: {edge['title']}",
        "scenario_type": "edge",
        "requirement_ids": ["MON-1", "MON-2", "NFR-1"],
        "preconditions": ["docker_compose_up", "jwt_secret_configured"],
        "input_payload": {
            "jsonrpc": "2.0",
            "id": f"edge-{idx}",
            "method": "tasks/sendSubscribe",
            "params": {
                "task": {
                    "type": "ed-triage",
                    "patient_ref": generate_patient_id(),
                    "inputs": {
                        "chief_complaint": edge.get("complaint", "other"),
                        "age": edge.get("age", 50),
                        "vital_signs": edge.get("vitals", {
                            "heart_rate": 75,
                            "blood_pressure": "120/80",
                            "respiratory_rate": 16,
                            "temperature": 37.0,
                            "oxygen_saturation": 98
                        })
                    }
                }
            }
        },
        "expected_http_status": 200,
        "expected_result": {
            "has_task_id": True,
            "has_trace_id": True
        },
        "expected_latency_ms": 10000,
        "expected_events": ["nexus.task.status"],
        "postconditions": ["task_handled", "metrics_updated"],
        "error_condition": "handled_gracefully",
        "tags": ["load-test", "edge", "boundary-conditions"]
    }

def generate_scenarios():
    """Generate 1000 scenarios: 800 positive, 200 negative, 50 edge."""
    scenarios = []
    idx = 1
    
    # 800 positive scenarios (80%)
    for _ in range(800):
        scenarios.append(generate_positive_scenario(idx))
        idx += 1
    
    # 150 negative scenarios (15%)
    for _ in range(150):
        scenarios.append(generate_negative_scenario(idx))
        idx += 1
    
    # 50 edge scenarios (5%)
    for _ in range(50):
        scenarios.append(generate_edge_scenario(idx))
        idx += 1
    
    # Shuffle to mix scenario types
    random.shuffle(scenarios)
    
    return scenarios

if __name__ == "__main__":
    random.seed(42)  # Reproducible scenarios
    scenarios = generate_scenarios()
    
    output_file = "nexus-a2a/artefacts/matrices/nexus_command_centre_load_matrix.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2)
    
    print(f"Generated {len(scenarios)} scenarios")
    print(f"Positive: {len([s for s in scenarios if s['scenario_type'] == 'positive'])}")
    print(f"Negative: {len([s for s in scenarios if s['scenario_type'] == 'negative'])}")
    print(f"Edge: {len([s for s in scenarios if s['scenario_type'] == 'edge'])}")
    print(f"Saved to: {output_file}")

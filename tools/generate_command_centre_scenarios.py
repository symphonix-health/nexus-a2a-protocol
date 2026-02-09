#!/usr/bin/env python3
"""Generate 1000 unique realistic test scenarios for command centre monitoring."""
import json
import random
from datetime import datetime
from pathlib import Path

# Chief complaints for realistic variety
CHIEF_COMPLAINTS = [
    "chest pain", "shortness of breath", "abdominal pain", "severe headache",
    "dizziness", "fever", "nausea and vomiting", "back pain", "leg pain",
    "arm pain", "difficulty breathing", "rapid heartbeat", "weakness",
    "confusion", "seizure", "allergic reaction", "trauma", "fall",
    "motor vehicle accident", "laceration", "burn", "poisoning",
    "overdose", "psychiatric emergency", "pregnancy complications",
    "bleeding", "syncope", "palpitations", "cough", "sore throat",
    "ear pain", "eye pain", "dental pain", "joint pain", "rash",
    "urinary symptoms", "constipation", "diarrhea", "anxiety",
    "depression", "suicidal ideation", "altered mental status",
    "hypothermia", "hyperthermia", "dehydration", "malnutrition",
    "substance abuse", "alcohol intoxication", "drug seeking",
    "follow-up care", "medication refill", "wound check"
]

# Patient demographics
AGES = list(range(18, 95))
GENDERS = ["male", "female", "other"]
SEVERITIES = ["low", "medium", "high", "critical"]

# API endpoints to test
API_ENDPOINTS = [
    "/api/agents", "/api/topology", "/api/events", "/health",
    "/", "/colors.js", "/dashboard.js", "/styles.css"
]

# Event types
EVENT_TYPES = [
    "nexus.task.status", "nexus.task.accepted", "nexus.task.working",
    "nexus.task.final", "nexus.task.error", "nexus.task.cancelled"
]

# Error types for negative cases
ERROR_TYPES = [
    "connection_refused", "timeout", "invalid_token", "missing_header",
    "malformed_json", "invalid_method", "unauthorized", "forbidden",
    "not_found", "rate_limited", "internal_error", "service_unavailable"
]

def generate_scenario_id(index: int, type_: str) -> str:
    """Generate unique scenario ID."""
    prefix = {"positive": "POS", "negative": "NEG", "edge": "EDGE"}[type_]
    return f"UC-CMD-{prefix}-{index:04d}"

def generate_positive_scenario(index: int) -> dict:
    """Generate a positive test scenario."""
    scenario_types = [
        "agent_discovery", "health_check", "topology_query", "websocket_connect",
        "event_stream", "static_file", "metrics_update", "concurrent_tasks",
        "task_completion", "cross_agent_call"
    ]
    
    scenario_type = random.choice(scenario_types)
    complaint = random.choice(CHIEF_COMPLAINTS)
    age = random.choice(AGES)
    gender = random.choice(GENDERS)
    patient_id = f"Patient/{random.randint(1000, 999999)}"
    
    base = {
        "use_case_id": generate_scenario_id(index, "positive"),
        "scenario_title": f"{scenario_type.replace('_', ' ').title()} - {complaint} case",
        "poc_demo": "command-centre",
        "scenario_type": "positive",
        "requirement_ids": ["MON-1", "MON-2", "NFR-1"],
        "preconditions": "All agents running and healthy",
        "test_data_refs": [patient_id],
        "expected_http_status": 200,
        "error_condition": "none"
    }
    
    if scenario_type == "agent_discovery":
        base["input_payload"] = {
            "endpoint": "/api/agents",
            "method": "GET"
        }
        base["expected_result"] = {
            "agents_count": 3,
            "has_metrics": True,
            "status": "healthy"
        }
        base["acceptance_criteria"] = "All agents discovered with health metrics"
        
    elif scenario_type == "health_check":
        base["input_payload"] = {
            "endpoint": "/health",
            "method": "GET"
        }
        base["expected_result"] = {
            "status": "healthy",
            "has_timestamp": True
        }
        base["acceptance_criteria"] = "Health endpoint returns current status"
        
    elif scenario_type == "topology_query":
        base["input_payload"] = {
            "endpoint": "/api/topology",
            "method": "GET"
        }
        base["expected_result"] = {
            "nodes_count": 3,
            "has_edges": True
        }
        base["acceptance_criteria"] = "Topology shows all agent connections"
        
    elif scenario_type == "websocket_connect":
        base["input_payload"] = {
            "endpoint": "/api/events",
            "method": "WS",
            "agent": random.choice(["triage-agent", "diagnosis-agent", "openhie-mediator"])
        }
        base["expected_result"] = {
            "connection": "established",
            "receives_events": True
        }
        base["acceptance_criteria"] = "WebSocket connects and streams events"
        
    elif scenario_type == "event_stream":
        base["input_payload"] = {
            "task": {
                "patient_ref": patient_id,
                "inputs": {
                    "chief_complaint": complaint,
                    "age": age,
                    "gender": gender
                }
            }
        }
        base["expected_result"] = {
            "events_received": True,
            "event_types": ["accepted", "working", "final"]
        }
        base["acceptance_criteria"] = "Task events stream to dashboard"
        
    elif scenario_type == "static_file":
        endpoint = random.choice(["/", "/colors.js", "/dashboard.js", "/styles.css"])
        base["input_payload"] = {
            "endpoint": endpoint,
            "method": "GET"
        }
        base["expected_result"] = {
            "content_type": "text/html" if endpoint == "/" else "text/javascript" if ".js" in endpoint else "text/css"
        }
        base["acceptance_criteria"] = "Static files served correctly"
        
    elif scenario_type == "metrics_update":
        base["input_payload"] = {
            "task": {
                "patient_ref": patient_id,
                "inputs": {"chief_complaint": complaint}
            },
            "verify_metrics": True
        }
        base["expected_result"] = {
            "tasks_accepted": "incremented",
            "tasks_completed": "incremented",
            "latency_recorded": True
        }
        base["acceptance_criteria"] = "Metrics update after task completion"
        
    elif scenario_type == "concurrent_tasks":
        base["input_payload"] = {
            "concurrent_count": random.randint(5, 20),
            "task_template": {
                "patient_ref": patient_id,
                "inputs": {"chief_complaint": complaint}
            }
        }
        base["expected_result"] = {
            "all_completed": True,
            "throughput_increased": True
        }
        base["acceptance_criteria"] = "Multiple concurrent tasks processed"
        
    elif scenario_type == "task_completion":
        severity = random.choice(SEVERITIES)
        base["input_payload"] = {
            "task": {
                "patient_ref": patient_id,
                "inputs": {
                    "chief_complaint": complaint,
                    "severity": severity,
                    "age": age,
                    "gender": gender
                }
            }
        }
        base["expected_result"] = {
            "task_completed": True,
            "has_triage_priority": True,
            "has_rationale": True
        }
        base["acceptance_criteria"] = "Task completes with triage assessment"
        
    else:  # cross_agent_call
        base["input_payload"] = {
            "task": {
                "patient_ref": patient_id,
                "inputs": {"chief_complaint": complaint}
            },
            "verify_chain": ["triage-agent", "diagnosis-agent", "openhie-mediator"]
        }
        base["expected_result"] = {
            "all_agents_called": True,
            "chain_complete": True
        }
        base["acceptance_criteria"] = "Task flows through agent chain"
    
    return base

def generate_negative_scenario(index: int) -> dict:
    """Generate a negative test scenario."""
    error_type = random.choice(ERROR_TYPES)
    
    base = {
        "use_case_id": generate_scenario_id(index, "negative"),
        "scenario_title": f"Graceful handling of {error_type.replace('_', ' ')}",
        "poc_demo": "command-centre",
        "scenario_type": "negative",
        "requirement_ids": ["MON-1", "NFR-8"],
        "preconditions": f"Simulate {error_type}",
        "test_data_refs": [],
        "error_condition": error_type
    }
    
    if error_type in ["connection_refused", "timeout", "service_unavailable"]:
        base["input_payload"] = {
            "endpoint": "/api/agents",
            "method": "GET",
            "force_error": error_type
        }
        base["expected_http_status"] = 200  # Graceful degradation
        base["expected_result"] = {
            "agent_status": "unreachable",
            "other_agents_visible": True
        }
        base["acceptance_criteria"] = "Dashboard shows partial failure gracefully"
        
    elif error_type in ["invalid_token", "unauthorized", "forbidden"]:
        base["input_payload"] = {
            "endpoint": random.choice(API_ENDPOINTS),
            "method": "GET",
            "token": "invalid" if error_type == "invalid_token" else "expired"
        }
        base["expected_http_status"] = 401 if error_type in ["invalid_token", "unauthorized"] else 403
        base["expected_result"] = {
            "error": "authentication_failed"
        }
        base["acceptance_criteria"] = "Auth errors handled properly"
        
    elif error_type == "malformed_json":
        base["input_payload"] = {
            "endpoint": "/api/agents",
            "method": "POST",
            "body": "{invalid json"
        }
        base["expected_http_status"] = 400
        base["expected_result"] = {
            "error": "invalid_json"
        }
        base["acceptance_criteria"] = "Malformed requests rejected"
        
    elif error_type == "not_found":
        base["input_payload"] = {
            "endpoint": f"/api/nonexistent/{random.randint(1, 9999)}",
            "method": "GET"
        }
        base["expected_http_status"] = 404
        base["expected_result"] = {
            "error": "not_found"
        }
        base["acceptance_criteria"] = "404 for missing endpoints"
        
    elif error_type == "rate_limited":
        base["input_payload"] = {
            "endpoint": "/api/agents",
            "method": "GET",
            "burst_count": 1000
        }
        base["expected_http_status"] = 429
        base["expected_result"] = {
            "error": "rate_limit_exceeded"
        }
        base["acceptance_criteria"] = "Rate limiting active"
        
    else:  # internal_error
        base["input_payload"] = {
            "endpoint": "/api/agents",
            "method": "GET",
            "force_error": "internal"
        }
        base["expected_http_status"] = 500
        base["expected_result"] = {
            "error": "internal_server_error"
        }
        base["acceptance_criteria"] = "Server errors reported"
    
    return base

def generate_edge_scenario(index: int) -> dict:
    """Generate an edge case scenario."""
    edge_types = [
        "empty_complaint", "very_long_complaint", "special_chars",
        "concurrent_surge", "redis_disconnect", "agent_restart",
        "memory_pressure", "slow_response", "websocket_flood",
        "rapid_reconnect"
    ]
    
    edge_type = random.choice(edge_types)
    
    base = {
        "use_case_id": generate_scenario_id(index, "edge"),
        "scenario_title": f"Edge case: {edge_type.replace('_', ' ')}",
        "poc_demo": "command-centre",
        "scenario_type": "edge",
        "requirement_ids": ["MON-1", "NFR-7", "NFR-8"],
        "preconditions": f"Test {edge_type} condition",
        "test_data_refs": [],
        "expected_http_status": 200,
        "error_condition": "edge_case"
    }
    
    if edge_type == "empty_complaint":
        base["input_payload"] = {
            "task": {
                "patient_ref": f"Patient/{random.randint(1000, 999999)}",
                "inputs": {"chief_complaint": ""}
            }
        }
        base["expected_result"] = {
            "handled_gracefully": True,
            "default_behavior": True
        }
        base["acceptance_criteria"] = "Empty input handled"
        
    elif edge_type == "very_long_complaint":
        base["input_payload"] = {
            "task": {
                "patient_ref": f"Patient/{random.randint(1000, 999999)}",
                "inputs": {"chief_complaint": " ".join(CHIEF_COMPLAINTS) * 10}
            }
        }
        base["expected_result"] = {
            "handled_gracefully": True,
            "truncated_or_processed": True
        }
        base["acceptance_criteria"] = "Long input handled"
        
    elif edge_type == "special_chars":
        base["input_payload"] = {
            "task": {
                "patient_ref": f"Patient/{random.randint(1000, 999999)}",
                "inputs": {"chief_complaint": "üñíçödé 特殊字符 🏥💊"}
            }
        }
        base["expected_result"] = {
            "unicode_supported": True
        }
        base["acceptance_criteria"] = "Unicode characters handled"
        
    elif edge_type == "concurrent_surge":
        base["input_payload"] = {
            "concurrent_count": random.randint(50, 100),
            "duration_seconds": 10
        }
        base["expected_result"] = {
            "system_stable": True,
            "metrics_accurate": True
        }
        base["acceptance_criteria"] = "High load handled"
        
    elif edge_type == "redis_disconnect":
        base["input_payload"] = {
            "action": "stop_redis",
            "verify_fallback": True
        }
        base["expected_result"] = {
            "fallback_active": True,
            "agents_still_visible": True
        }
        base["acceptance_criteria"] = "Redis failure handled"
        
    elif edge_type == "agent_restart":
        base["input_payload"] = {
            "action": "restart_agent",
            "agent": random.choice(["triage-agent", "diagnosis-agent", "openhie-mediator"])
        }
        base["expected_result"] = {
            "agent_rediscovered": True,
            "status_updated": True
        }
        base["acceptance_criteria"] = "Agent restart detected"
        
    elif edge_type == "memory_pressure":
        base["input_payload"] = {
            "action": "simulate_memory_pressure",
            "concurrent_tasks": 200
        }
        base["expected_result"] = {
            "system_stable": True,
            "no_memory_leak": True
        }
        base["acceptance_criteria"] = "Memory efficient"
        
    elif edge_type == "slow_response":
        base["input_payload"] = {
            "action": "inject_delay",
            "delay_ms": random.randint(5000, 10000)
        }
        base["expected_result"] = {
            "timeout_handled": True,
            "ui_responsive": True
        }
        base["acceptance_criteria"] = "Slow responses handled"
        
    elif edge_type == "websocket_flood":
        base["input_payload"] = {
            "action": "flood_websocket",
            "message_count": 10000
        }
        base["expected_result"] = {
            "backpressure_applied": True,
            "no_crash": True
        }
        base["acceptance_criteria"] = "WebSocket flood handled"
        
    else:  # rapid_reconnect
        base["input_payload"] = {
            "action": "rapid_reconnect",
            "iterations": 100
        }
        base["expected_result"] = {
            "connections_stable": True,
            "no_resource_leak": True
        }
        base["acceptance_criteria"] = "Rapid reconnects handled"
    
    return base

def main():
    """Generate 1000 unique test scenarios."""
    scenarios = []
    
    # Generate 800 positive scenarios (80%)
    for i in range(1, 801):
        scenarios.append(generate_positive_scenario(i))
    
    # Generate 150 negative scenarios (15%)
    for i in range(1, 151):
        scenarios.append(generate_negative_scenario(i))
    
    # Generate 50 edge scenarios (5%)
    for i in range(1, 51):
        scenarios.append(generate_edge_scenario(i))
    
    # Shuffle to mix scenario types
    random.shuffle(scenarios)
    
    # Save to matrix file
    output_path = Path(__file__).parent.parent / "nexus-a2a" / "artefacts" / "matrices" / "nexus_command_centre_load_matrix.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated {len(scenarios)} unique test scenarios")
    print(f"   📁 Saved to: {output_path}")
    print(f"   📊 Breakdown:")
    print(f"      - Positive: {len([s for s in scenarios if s['scenario_type'] == 'positive'])}")
    print(f"      - Negative: {len([s for s in scenarios if s['scenario_type'] == 'negative'])}")
    print(f"      - Edge:     {len([s for s in scenarios if s['scenario_type'] == 'edge'])}")

if __name__ == "__main__":
    random.seed(42)  # Reproducible scenarios
    main()

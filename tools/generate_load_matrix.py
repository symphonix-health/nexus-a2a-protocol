"""Generate an expanded command-centre load matrix for hyperscale readiness gates."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

CHIEF_COMPLAINTS = [
    "chest pain",
    "shortness of breath",
    "abdominal pain",
    "headache",
    "fever",
    "nausea and vomiting",
    "back pain",
    "syncope",
    "palpitations",
    "stroke symptoms",
    "allergic reaction",
    "asthma exacerbation",
    "hypertensive emergency",
    "seizure",
    "altered mental status",
]

GATE_TAGS = ("gate:g0", "gate:g1", "gate:g2", "gate:g3", "gate:g4")
CONCURRENCY_PROFILES = (25, 50, 100, 250, 500, 1000, 2000, 10000, 100000, 500000, 2000000)
EDGE_SURGE_PROFILES = (500, 1000, 2000, 4000, 8000, 20000, 100000, 500000, 2000000)


def generate_patient_id() -> str:
    return f"Patient/{random.randint(1000, 99999999)}"


def _base_record(idx: int, scenario_type: str, title: str, gate_tag: str) -> dict:
    return {
        "use_case_id": f"UC-CMD-LOAD-{idx:05d}",
        "poc_demo": "command-centre",
        "scenario_title": title,
        "scenario_type": scenario_type,
        "requirement_ids": ["MON-1", "MON-2", "MON-4", "NFR-8"],
        "preconditions": ["docker_compose_up", "jwt_secret_configured"],
        "expected_http_status": 200,
        "error_condition": "none" if scenario_type == "positive" else "expected_failure",
        "test_tags": ["load-test", scenario_type, gate_tag],
    }


def generate_positive_scenario(idx: int) -> dict:
    complaint = random.choice(CHIEF_COMPLAINTS)
    age = random.randint(1, 99)
    patient_id = generate_patient_id()
    gate_tag = random.choice(GATE_TAGS)
    profile = random.choice(CONCURRENCY_PROFILES)
    mode = random.choice(("task", "concurrent", "api"))
    base = _base_record(
        idx,
        "positive",
        f"Positive load path: {complaint} age {age}",
        gate_tag,
    )

    if mode == "task":
        base["input_payload"] = {
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
                        "oxygen_saturation": random.randint(85, 100),
                    },
                },
            }
        }
        base["expected_result"] = {"has_task_id": True, "has_trace_id": True, "status": "success"}
        base["expected_latency_ms"] = 5000
        base["expected_events"] = ["nexus.task.status", "nexus.task.final"]
    elif mode == "concurrent":
        base["input_payload"] = {
            "concurrent_count": profile,
            "task_template": {
                "type": "ed-triage",
                "patient_ref": patient_id,
                "inputs": {"chief_complaint": complaint, "age": age},
            },
        }
        base["expected_result"] = {"all_completed": True, "throughput_increased": True}
        base["expected_latency_ms"] = 10000
        base["expected_events"] = ["nexus.task.status"]
    else:
        endpoint = random.choice(("/api/agents", "/api/topology", "/health"))
        base["input_payload"] = {"endpoint": endpoint, "method": "GET"}
        base["expected_result"] = {"status": "healthy"}
        base["expected_latency_ms"] = 1000
        base["expected_events"] = []

    base["postconditions"] = ["metrics_updated"]
    base["load_gate"] = {
        "gate_tag": gate_tag,
        "target_concurrency": profile,
        "target_rps": max(50, profile * 2),
    }
    return base


def generate_negative_scenario(idx: int) -> dict:
    gate_tag = random.choice(GATE_TAGS)
    case = random.choice(
        (
            ("Missing chief complaint", {"task": {"patient_ref": generate_patient_id(), "inputs": {}}}, 200, "validation_error"),
            (
                "Invalid patient reference",
                {"task": {"patient_ref": "invalid", "inputs": {"chief_complaint": "pain"}}},
                200,
                "invalid_reference",
            ),
            ("Malformed JSON-RPC", {"invalid": "structure"}, 200, "parse_error"),
            (
                "Missing authentication",
                {"task": {"patient_ref": generate_patient_id(), "inputs": {"chief_complaint": "pain"}}},
                401,
                "auth_error",
            ),
            ("Rate limit exceeded", {"endpoint": "/api/agents", "method": "GET", "burst_count": 2500}, 429, "rate_limit_exceeded"),
        )
    )
    title, payload, status, error = case
    base = _base_record(idx, "negative", f"Negative load path: {title}", gate_tag)
    base["input_payload"] = payload
    base["expected_http_status"] = status
    base["expected_result"] = {"error": error}
    base["expected_latency_ms"] = 1500
    base["expected_events"] = ["nexus.task.error"] if "task" in payload else []
    base["postconditions"] = ["error_recorded", "metrics_updated"]
    base["error_condition"] = error
    base["load_gate"] = {
        "gate_tag": gate_tag,
        "target_concurrency": random.choice(CONCURRENCY_PROFILES),
        "target_rps": random.choice((100, 250, 500, 1000)),
    }
    return base


def generate_edge_scenario(idx: int) -> dict:
    gate_tag = random.choice(GATE_TAGS)
    surge = random.choice(EDGE_SURGE_PROFILES)
    base = _base_record(
        idx,
        "edge",
        f"Edge load path: concurrency surge {surge}",
        gate_tag,
    )
    base["input_payload"] = {
        "concurrent_count": surge,
        "duration_seconds": random.choice((15, 30, 45, 60)),
        "task_template": {
            "type": "ed-triage",
            "patient_ref": generate_patient_id(),
            "inputs": {"chief_complaint": random.choice(CHIEF_COMPLAINTS), "age": random.randint(1, 99)},
        },
    }
    base["expected_result"] = {"system_stable": True, "metrics_accurate": True}
    base["expected_http_status"] = 200
    base["expected_latency_ms"] = 20000
    base["expected_events"] = ["nexus.task.status"]
    base["postconditions"] = ["task_handled", "metrics_updated"]
    base["error_condition"] = "handled_gracefully"
    base["load_gate"] = {
        "gate_tag": gate_tag,
        "target_concurrency": surge,
        "target_rps": max(1000, surge * 2),
    }
    return base


def generate_scenarios(positive: int, negative: int, edge: int) -> list[dict]:
    scenarios: list[dict] = []
    idx = 1
    for _ in range(positive):
        scenarios.append(generate_positive_scenario(idx))
        idx += 1
    for _ in range(negative):
        scenarios.append(generate_negative_scenario(idx))
        idx += 1
    for _ in range(edge):
        scenarios.append(generate_edge_scenario(idx))
        idx += 1
    random.shuffle(scenarios)
    return scenarios


def emit_gate_matrices(rows: list[dict], output_path: Path) -> None:
    gate_dir = output_path.parent / "gates"
    gate_dir.mkdir(parents=True, exist_ok=True)
    for gate in GATE_TAGS:
        gate_rows = [
            row
            for row in rows
            if gate in row.get("test_tags", [])
            or row.get("load_gate", {}).get("gate_tag") == gate
        ]
        gate_name = gate.replace(":", "_")
        gate_path = gate_dir / f"nexus_command_centre_load_matrix_{gate_name}.json"
        gate_path.write_text(json.dumps(gate_rows, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate expanded command-centre load matrix")
    parser.add_argument("--positive", type=int, default=5600)
    parser.add_argument("--negative", type=int, default=1050)
    parser.add_argument("--edge", type=int, default=350)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--emit-gates", action="store_true")
    parser.add_argument(
        "--output",
        default="nexus-a2a/artefacts/matrices/nexus_command_centre_load_matrix.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    scenarios = generate_scenarios(args.positive, args.negative, args.edge)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scenarios, indent=2), encoding="utf-8")
    if args.emit_gates:
        emit_gate_matrices(scenarios, output_path)

    print(f"Generated {len(scenarios)} scenarios")
    print(f"Positive: {args.positive}")
    print(f"Negative: {args.negative}")
    print(f"Edge: {args.edge}")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()

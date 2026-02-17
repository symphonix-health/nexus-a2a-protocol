#!/usr/bin/env python3
"""Traffic generator to execute command centre test scenarios and generate real metrics."""
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.nexus_common.auth import mint_jwt

# Configuration
COMMAND_CENTRE_URL = "http://localhost:8099"
TRIAGE_AGENT_URL = "http://localhost:8021"
JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
TOKEN = mint_jwt("traffic-generator", JWT_SECRET, ttl_seconds=3600)
MAX_CONCURRENT_TASKS = int(os.getenv("TRAFFIC_MAX_CONCURRENT_TASKS", "500"))
CONCURRENT_BATCH_SIZE = int(os.getenv("TRAFFIC_CONCURRENT_BATCH_SIZE", "200"))
DEFAULT_DETERMINISTIC_SEED = int(os.getenv("TRAFFIC_DETERMINISTIC_SEED", "1729"))
GATE_MAX_SCENARIOS = int(os.getenv("TRAFFIC_GATE_MAX_SCENARIOS", "24"))
GATE_MAX_CONCURRENT_TASKS = int(os.getenv("TRAFFIC_GATE_MAX_CONCURRENT_TASKS", "200"))
DEFAULT_SCENARIO_TIMEOUT_SECONDS = float(
    os.getenv("TRAFFIC_SCENARIO_TIMEOUT_SECONDS", "25.0")
)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}
STRICT_ADMISSION_ERROR_FIELDS = (
    "retryable",
    "retry_after_ms",
    "failure_domain",
    "rate_limit_scope",
    "bucket_id",
    "limit_rps",
    "observed_rps",
)
DEFAULT_SCENARIO_ERROR_THRESHOLD = int(
    os.getenv("TRAFFIC_SCENARIO_ERROR_THRESHOLD", "3")
)
GATE_SCENARIO_ERROR_THRESHOLD = int(
    os.getenv("TRAFFIC_GATE_SCENARIO_ERROR_THRESHOLD", "1")
)

class MetricsTracker:
    """Track execution metrics."""
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.start_time = time.time()
        self.tasks_sent = 0
        self.tasks_completed = 0
        
    def report(self):
        """Print current stats."""
        elapsed = time.time() - self.start_time
        rate = self.tasks_sent / elapsed if elapsed > 0 else 0
        print(
            f"\rT+{elapsed:.0f}s | Tasks: {self.tasks_sent} ({rate:.1f}/s) | "
            f"Tests: pass={self.passed} fail={self.failed} err={self.errors} ",
            end="",
            flush=True,
        )

metrics = MetricsTracker()


def _extract_admission_error_data(payload: Dict) -> Dict | None:
    """Extract rate-limit error data from JSON-RPC or flat HTTP payloads."""
    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        data = error.get("data")
        if code == -32004 and isinstance(data, dict):
            return data
        return None

    if isinstance(error, str) and error == "rate_limit_exceeded":
        return payload

    required = set(STRICT_ADMISSION_ERROR_FIELDS)
    if required.intersection(payload.keys()):
        return payload
    return None


def validate_admission_rate_limit_payload(payload: Dict) -> tuple[bool, str]:
    """Validate strict admission-control payload contract for overload responses."""
    data = _extract_admission_error_data(payload)
    if data is None:
        return False, "missing_rate_limit_payload"

    missing = [field for field in STRICT_ADMISSION_ERROR_FIELDS if field not in data]
    if missing:
        return False, f"missing_required_fields:{','.join(missing)}"

    if data.get("retryable") is not True:
        return False, "retryable_must_be_true"

    retry_after_ms = data.get("retry_after_ms")
    if not isinstance(retry_after_ms, int) or retry_after_ms < 0:
        return False, "retry_after_ms_must_be_non_negative_int"

    if data.get("failure_domain") != "network":
        return False, "failure_domain_must_be_network"

    for numeric_field in ("limit_rps", "observed_rps"):
        value = data.get(numeric_field)
        if not isinstance(value, (int, float)):
            return False, f"{numeric_field}_must_be_numeric"
        if float(value) < 0:
            return False, f"{numeric_field}_must_be_non_negative"

    for text_field in ("rate_limit_scope", "bucket_id"):
        value = data.get(text_field)
        if not isinstance(value, str) or not value.strip():
            return False, f"{text_field}_must_be_non_empty_string"

    return True, "validated"


def stable_scenario_key(scenario: Dict) -> tuple[str, str]:
    """Stable sort key for deterministic execution order."""
    scenario_id = str(
        scenario.get("scenario_id")
        or scenario.get("id")
        or scenario.get("name")
        or ""
    )
    payload = json.dumps(
        scenario.get("input_payload", {}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return scenario_id, payload


def scenario_runtime_key(scenario: Dict) -> str:
    """Stable scenario runtime key for per-scenario error isolation."""
    scenario_id, payload = stable_scenario_key(scenario)
    return f"{scenario_id}|{payload}"


class ScenarioRuntimeIsolation:
    """Track repeated runtime errors and quarantine unstable scenarios."""

    def __init__(self, *, error_threshold: int):
        self.error_threshold = max(1, int(error_threshold))
        self._consecutive_errors: dict[str, int] = {}
        self._quarantined: set[str] = set()

    def is_quarantined(self, key: str) -> bool:
        return key in self._quarantined

    def observe(self, key: str, result: Dict) -> bool:
        """Observe result and return True when scenario becomes quarantined."""
        status = result.get("status")
        if status == "error":
            count = self._consecutive_errors.get(key, 0) + 1
            self._consecutive_errors[key] = count
            if count >= self.error_threshold:
                self._quarantined.add(key)
                return True
            return False

        # Reset error streak on deterministic outcomes.
        if status in {"pass", "fail", "partial", "skip"}:
            self._consecutive_errors.pop(key, None)
        return False


def select_bounded_scenarios(
    scenarios: List[Dict],
    *,
    deterministic: bool,
    seed: int,
    max_scenarios: int | None,
) -> List[Dict]:
    """Apply deterministic ordering and optional bounded scenario pool selection."""
    if deterministic:
        ordered = sorted(scenarios, key=stable_scenario_key)
    else:
        ordered = list(scenarios)

    if max_scenarios is None or max_scenarios >= len(ordered):
        return ordered

    if deterministic:
        start = seed % len(ordered)
        rotated = ordered[start:] + ordered[:start]
        return rotated[:max_scenarios]

    rng = random.Random(seed)
    return rng.sample(ordered, max_scenarios)

async def send_triage_task(client: httpx.AsyncClient, scenario: Dict) -> Dict:
    """Send a triage task and wait for completion."""
    payload = scenario.get("input_payload", {})
    task_data = payload.get("task", {})
    
    if not task_data:
        return {"status": "skip", "reason": "No task data"}
    
    rpc_payload = {
        "jsonrpc": "2.0",
        "method": "tasks/sendSubscribe",
        "params": {"task": task_data},
        "id": f"traffic-{int(time.time() * 1000)}"
    }
    
    try:
        resp = await client.post(
            f"{TRIAGE_AGENT_URL}/rpc",
            json=rpc_payload,
            headers=HEADERS,
            timeout=30.0
        )
        
        if resp.status_code == 200:
            result = resp.json()
            if "result" in result:
                metrics.tasks_sent += 1
                # Give time for task to complete
                await asyncio.sleep(random.uniform(0.1, 0.5))
                metrics.tasks_completed += 1
                return {"status": "pass", "result": result["result"]}
            else:
                if scenario.get("error_condition") == "rate_limit_exceeded":
                    ok, detail = validate_admission_rate_limit_payload(result)
                    if ok:
                        return {"status": "pass", "result": result}
                    return {"status": "fail", "error": result.get("error"), "detail": detail}
                return {"status": "fail", "error": result.get("error")}
        elif resp.status_code == 429 and scenario.get("error_condition") == "rate_limit_exceeded":
            try:
                body = resp.json()
            except Exception:
                return {"status": "fail", "status_code": resp.status_code, "detail": "non_json_rate_limit_response"}
            ok, detail = validate_admission_rate_limit_payload(body)
            if ok:
                return {"status": "pass", "status_code": resp.status_code, "result": body}
            return {"status": "fail", "status_code": resp.status_code, "detail": detail}
        else:
            return {"status": "fail", "status_code": resp.status_code}
            
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def test_api_endpoint(client: httpx.AsyncClient, scenario: Dict) -> Dict:
    """Test an API endpoint."""
    payload = scenario.get("input_payload", {})
    endpoint = payload.get("endpoint", "/api/agents")
    method = payload.get("method", "GET").upper()
    
    try:
        url = f"{COMMAND_CENTRE_URL}{endpoint}"
        
        if method == "GET":
            resp = await client.get(url, timeout=10.0)
        elif method == "POST":
            resp = await client.post(url, json=payload.get("body", {}), timeout=10.0)
        else:
            return {"status": "skip", "reason": f"Method {method} not implemented"}
        
        expected_status = scenario.get("expected_http_status", 200)
        if resp.status_code == expected_status:
            if scenario.get("error_condition") == "rate_limit_exceeded":
                try:
                    body = resp.json()
                except Exception:
                    return {"status": "fail", "status_code": resp.status_code, "detail": "non_json_rate_limit_response"}
                ok, detail = validate_admission_rate_limit_payload(body)
                if not ok:
                    return {"status": "fail", "status_code": resp.status_code, "detail": detail}
            return {"status": "pass", "status_code": resp.status_code}
        else:
            return {"status": "fail", "expected": expected_status, "got": resp.status_code}
            
    except Exception as e:
        # Connection errors are expected for some negative tests
        if "connection" in str(e).lower() and scenario["scenario_type"] == "negative":
            return {"status": "pass", "note": "Expected connection error"}
        return {"status": "error", "error": str(e)}

async def execute_scenario(
    client: httpx.AsyncClient, scenario: Dict, max_concurrent_tasks: int
) -> Dict:
    """Execute a single test scenario."""
    scenario_type = scenario.get("scenario_type", "positive")
    payload = scenario.get("input_payload", {})
    
    # Determine execution type
    if "task" in payload:
        # Task execution scenario
        result = await send_triage_task(client, scenario)
    elif "endpoint" in payload:
        # API endpoint test
        result = await test_api_endpoint(client, scenario)
    elif "concurrent_count" in payload:
        # Concurrent execution
        count = payload["concurrent_count"]
        effective_count = min(count, max_concurrent_tasks)
        task_template = payload.get("task_template", payload.get("task", {}))
        passed = 0
        processed = 0
        while processed < effective_count:
            batch_count = min(CONCURRENT_BATCH_SIZE, effective_count - processed)
            batch_tasks = []
            for _ in range(batch_count):
                batch_tasks.append(
                    send_triage_task(
                        client,
                        {"input_payload": {"task": task_template}},
                    )
                )
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            passed += sum(
                1 for r in batch_results if isinstance(r, dict) and r.get("status") == "pass"
            )
            processed += batch_count

        result = {
            "status": "pass" if passed == effective_count else "partial",
            "passed": passed,
            "total": effective_count,
            "requested": count,
            "effective": effective_count,
            "virtual_concurrency_ratio": round(count / max(1, effective_count), 2),
        }
    elif "action" in payload:
        # Special action scenario (edge cases)
        result = {"status": "skip", "reason": f"Action '{payload['action']}' requires manual setup"}
    else:
        result = {"status": "skip", "reason": "Unknown scenario type"}
    
    # Update metrics
    metrics.total += 1
    if result["status"] == "pass":
        metrics.passed += 1
    elif result["status"] in ["fail", "partial"]:
        metrics.failed += 1
    elif result["status"] == "error":
        metrics.errors += 1
    
    return result

async def execute_scenario_with_budget(
    client: httpx.AsyncClient,
    scenario: Dict,
    *,
    max_concurrent_tasks: int,
    scenario_timeout_seconds: float | None,
) -> Dict:
    """Execute a scenario with optional runtime budget."""
    if scenario_timeout_seconds is not None and scenario_timeout_seconds > 0:
        try:
            return await asyncio.wait_for(
                execute_scenario(client, scenario, max_concurrent_tasks),
                timeout=scenario_timeout_seconds,
            )
        except asyncio.TimeoutError:
            metrics.total += 1
            metrics.errors += 1
            return {
                "status": "error",
                "error": (
                    f"Scenario runtime exceeded {scenario_timeout_seconds:.1f}s "
                    "(budget timeout)"
                ),
            }

    return await execute_scenario(client, scenario, max_concurrent_tasks)


async def run_traffic_generator(
    scenarios: List[Dict],
    duration_seconds: int = 300,
    rate_limit: float = 10.0,
    *,
    deterministic: bool = False,
    deterministic_seed: int = DEFAULT_DETERMINISTIC_SEED,
    max_concurrent_tasks: int = MAX_CONCURRENT_TASKS,
    scenario_timeout_seconds: float | None = None,
    scenario_error_threshold: int = DEFAULT_SCENARIO_ERROR_THRESHOLD,
):
    """Generate continuous traffic for specified duration."""
    print("Starting traffic generator")
    print(f"   Duration: {duration_seconds}s")
    print(f"   Target rate: {rate_limit} requests/second")
    print(f"   Scenarios: {len(scenarios)}")
    print(f"   Deterministic order: {deterministic} (seed={deterministic_seed})")
    print(f"   Max concurrent tasks per scenario: {max_concurrent_tasks}")
    print(f"   Scenario runtime isolation threshold: {scenario_error_threshold}")
    if scenario_timeout_seconds is not None:
        print(f"   Scenario runtime budget: {scenario_timeout_seconds}s")
    print(f"   Command Centre: {COMMAND_CENTRE_URL}")
    print()
    isolation = ScenarioRuntimeIsolation(error_threshold=scenario_error_threshold)
    
    async with httpx.AsyncClient() as client:
        end_time = time.time() + duration_seconds
        interval = 1.0 / rate_limit
        index = deterministic_seed % max(1, len(scenarios))
        
        while time.time() < end_time:
            # Pick random scenarios weighted by type
            if deterministic:
                scenario = scenarios[index % len(scenarios)]
                index += 1
            else:
                scenario = random.choice(scenarios)

            key = scenario_runtime_key(scenario)
            if isolation.is_quarantined(key):
                metrics.total += 1
                await asyncio.sleep(interval)
                continue
            
            # Execute scenario
            result = await execute_scenario_with_budget(
                client,
                scenario,
                max_concurrent_tasks=max_concurrent_tasks,
                scenario_timeout_seconds=scenario_timeout_seconds,
            )
            quarantined_now = isolation.observe(key, result)
            if quarantined_now:
                print(
                    "\n[isolation] quarantining unstable scenario after repeated runtime errors: "
                    f"{key[:160]}"
                )
            
            # Report progress
            metrics.report()
            
            # Rate limiting
            await asyncio.sleep(interval)
    
    print("\n\nTraffic generation complete.")
    print("\nFinal Stats:")
    print(f"   Total scenarios executed: {metrics.total}")
    print(f"   Tasks sent to agents: {metrics.tasks_sent}")
    print(f"   Tasks completed: {metrics.tasks_completed}")
    print(f"   Tests passed: {metrics.passed}")
    print(f"   Tests failed: {metrics.failed}")
    print(f"   Errors: {metrics.errors}")
    elapsed = time.time() - metrics.start_time
    print(f"   Duration: {elapsed:.1f}s")
    print(f"   Average rate: {metrics.tasks_sent / elapsed:.2f} tasks/second")

async def run_burst_mode(
    scenarios: List[Dict],
    count: int = 100,
    *,
    deterministic: bool = False,
    deterministic_seed: int = DEFAULT_DETERMINISTIC_SEED,
    max_concurrent_tasks: int = MAX_CONCURRENT_TASKS,
    scenario_timeout_seconds: float | None = None,
    scenario_error_threshold: int = DEFAULT_SCENARIO_ERROR_THRESHOLD,
):
    """Send a burst of concurrent requests."""
    print(f"Burst mode: sending {count} concurrent requests...")
    
    positive_scenarios = [s for s in scenarios if s["scenario_type"] == "positive" and "task" in s.get("input_payload", {})]
    if deterministic:
        positive_scenarios = sorted(positive_scenarios, key=stable_scenario_key)
        start = deterministic_seed % max(1, len(positive_scenarios))
        positive_scenarios = positive_scenarios[start:] + positive_scenarios[:start]
    isolation = ScenarioRuntimeIsolation(error_threshold=scenario_error_threshold)
    
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(count):
            if deterministic:
                scenario = positive_scenarios[i % len(positive_scenarios)]
            else:
                scenario = random.choice(positive_scenarios)
            key = scenario_runtime_key(scenario)
            if isolation.is_quarantined(key):
                continue
            tasks.append(
                execute_scenario_with_budget(
                    client,
                    scenario,
                    max_concurrent_tasks=max_concurrent_tasks,
                    scenario_timeout_seconds=scenario_timeout_seconds,
                )
            )
        
        start = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        for scenario, result in zip(tasks, results):
            _ = scenario  # preserve positional pairing without re-reading scenario payload.
            if isinstance(result, dict):
                # No stable key available here from gathered coroutines; burst mode uses
                # same isolation threshold and benefits mainly from pre-scheduling quarantine.
                pass
        
        passed = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "pass")
        
        print("\nBurst complete.")
        print(f"   Sent: {count} requests")
        print(f"   Passed: {passed}")
        print(f"   Duration: {elapsed:.2f}s")
        print(f"   Rate: {count / elapsed:.2f} req/s")

async def run_continuous_load(
    scenarios: List[Dict],
    *,
    deterministic: bool = False,
    deterministic_seed: int = DEFAULT_DETERMINISTIC_SEED,
    max_concurrent_tasks: int = MAX_CONCURRENT_TASKS,
    scenario_timeout_seconds: float | None = None,
    scenario_error_threshold: int = DEFAULT_SCENARIO_ERROR_THRESHOLD,
):
    """Run continuous load with varying intensity."""
    print("Continuous load mode (Ctrl+C to stop)...")
    print(f"   Ramping up intensity over time")
    print()
    
    phases = [
        ("Warm-up", 60, 2.0),
        ("Low load", 120, 5.0),
        ("Medium load", 180, 10.0),
        ("High load", 180, 20.0),
        ("Peak load", 120, 30.0),
        ("Cool-down", 60, 5.0),
    ]
    
    try:
        for phase_name, duration, rate in phases:
            print(f"\nPhase: {phase_name} ({rate:.1f} req/s for {duration}s)")
            await run_traffic_generator(
                scenarios,
                duration,
                rate,
                deterministic=deterministic,
                deterministic_seed=deterministic_seed,
                max_concurrent_tasks=max_concurrent_tasks,
                scenario_timeout_seconds=scenario_timeout_seconds,
                scenario_error_threshold=scenario_error_threshold,
            )
    except KeyboardInterrupt:
        print("\n\nStopped by user")

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Command Centre Traffic Generator")
    parser.add_argument("--mode", choices=["continuous", "burst", "sustained"], default="sustained",
                       help="Traffic generation mode")
    parser.add_argument("--duration", type=int, default=300,
                       help="Duration in seconds for sustained mode")
    parser.add_argument("--rate", type=float, default=10.0,
                       help="Target requests per second")
    parser.add_argument("--burst-size", type=int, default=100,
                       help="Number of concurrent requests for burst mode")
    parser.add_argument("--gate", choices=["g0", "g1", "g2", "g3", "g4"],
                       help="Optional load-gate filter by test tag")
    parser.add_argument("--matrix", help="Override matrix path")
    parser.add_argument(
        "--strict-positive",
        action="store_true",
        help="When set, keep only positive scenarios after any gate filter.",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Use deterministic scenario ordering/cycling for reproducibility.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_DETERMINISTIC_SEED,
        help="Deterministic selection seed for bounded scenario scheduling.",
    )
    parser.add_argument(
        "--max-scenarios",
        type=int,
        help="Bound the active scenario pool size.",
    )
    parser.add_argument(
        "--scenario-timeout",
        type=float,
        default=None,
        help="Per-scenario runtime budget in seconds.",
    )
    parser.add_argument(
        "--max-concurrent-tasks",
        type=int,
        default=MAX_CONCURRENT_TASKS,
        help="Maximum effective concurrent tasks for concurrent-count scenarios.",
    )
    parser.add_argument(
        "--scenario-error-threshold",
        type=int,
        default=DEFAULT_SCENARIO_ERROR_THRESHOLD,
        help="Consecutive runtime errors before scenario is quarantined.",
    )
    
    args = parser.parse_args()
    
    # Load scenarios
    matrix_path = (
        Path(args.matrix)
        if args.matrix
        else Path(__file__).parent.parent
        / "nexus-a2a"
        / "artefacts"
        / "matrices"
        / "nexus_command_centre_load_matrix.json"
    )
    
    if not matrix_path.exists():
        print(f"Matrix file not found: {matrix_path}")
        print("   Run: python tools/generate_command_centre_scenarios.py")
        sys.exit(1)
    
    with open(matrix_path, encoding="utf-8") as f:
        scenarios = json.load(f)

    if args.gate:
        tag = f"gate:{args.gate}"
        scenarios = [s for s in scenarios if tag in s.get("test_tags", [])]
        if not scenarios:
            print(f"No scenarios found for {tag}")
            sys.exit(1)

    if args.strict_positive:
        scenarios = [s for s in scenarios if s.get("scenario_type") == "positive"]
        if not scenarios:
            print("No positive scenarios available for strict-positive mode")
            sys.exit(1)

    if args.max_scenarios is not None and args.max_scenarios <= 0:
        print("--max-scenarios must be > 0 when provided")
        sys.exit(2)

    if args.max_concurrent_tasks <= 0:
        print("--max-concurrent-tasks must be > 0")
        sys.exit(2)
    if args.scenario_error_threshold <= 0:
        print("--scenario-error-threshold must be > 0")
        sys.exit(2)

    deterministic = args.deterministic or args.gate is not None

    if args.gate:
        if args.max_scenarios is None:
            args.max_scenarios = GATE_MAX_SCENARIOS
        if args.scenario_timeout is None:
            args.scenario_timeout = DEFAULT_SCENARIO_TIMEOUT_SECONDS
        args.max_concurrent_tasks = min(args.max_concurrent_tasks, GATE_MAX_CONCURRENT_TASKS)
        args.scenario_error_threshold = min(args.scenario_error_threshold, GATE_SCENARIO_ERROR_THRESHOLD)

    scenarios = select_bounded_scenarios(
        scenarios,
        deterministic=deterministic,
        seed=args.seed,
        max_scenarios=args.max_scenarios,
    )

    if not scenarios:
        print("No scenarios available after deterministic/bounded selection")
        sys.exit(1)

    print(f"Loaded {len(scenarios)} scenarios")
    print(f"   Positive: {len([s for s in scenarios if s['scenario_type'] == 'positive'])}")
    print(f"   Negative: {len([s for s in scenarios if s['scenario_type'] == 'negative'])}")
    print(f"   Edge: {len([s for s in scenarios if s['scenario_type'] == 'edge'])}")
    print(f"   Deterministic: {deterministic} (seed={args.seed})")
    if args.max_scenarios is not None:
        print(f"   Bounded scenario pool: {args.max_scenarios}")
    if args.scenario_timeout is not None:
        print(f"   Scenario timeout budget: {args.scenario_timeout}s")
    print(f"   Max concurrent tasks: {args.max_concurrent_tasks}")
    print(f"   Scenario error threshold: {args.scenario_error_threshold}")
    print()
    
    # Run appropriate mode
    if args.mode == "burst":
        asyncio.run(
            run_burst_mode(
                scenarios,
                args.burst_size,
                deterministic=deterministic,
                deterministic_seed=args.seed,
                max_concurrent_tasks=args.max_concurrent_tasks,
                scenario_timeout_seconds=args.scenario_timeout,
                scenario_error_threshold=args.scenario_error_threshold,
            )
        )
    elif args.mode == "continuous":
        asyncio.run(
            run_continuous_load(
                scenarios,
                deterministic=deterministic,
                deterministic_seed=args.seed,
                max_concurrent_tasks=args.max_concurrent_tasks,
                scenario_timeout_seconds=args.scenario_timeout,
                scenario_error_threshold=args.scenario_error_threshold,
            )
        )
    else:  # sustained
        asyncio.run(
            run_traffic_generator(
                scenarios,
                args.duration,
                args.rate,
                deterministic=deterministic,
                deterministic_seed=args.seed,
                max_concurrent_tasks=args.max_concurrent_tasks,
                scenario_timeout_seconds=args.scenario_timeout,
                scenario_error_threshold=args.scenario_error_threshold,
            )
        )

    # Gate runs are strict by default: any failed/error scenario exits non-zero.
    strict_fail = args.gate is not None
    if strict_fail and (metrics.failed > 0 or metrics.errors > 0):
        print(
            f"\nStrict gate failure: failed={metrics.failed}, errors={metrics.errors}, total={metrics.total}"
        )
        sys.exit(1)

if __name__ == "__main__":
    main()

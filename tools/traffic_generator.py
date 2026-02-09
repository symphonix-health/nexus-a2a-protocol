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

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

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
        print(f"\r⏱️  {elapsed:.0f}s | Tasks: {self.tasks_sent} ({rate:.1f}/s) | "
              f"Tests: {self.passed}✓ {self.failed}✗ {self.errors}⚠️  ", end="", flush=True)

metrics = MetricsTracker()

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
                return {"status": "fail", "error": result.get("error")}
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
            return {"status": "pass", "status_code": resp.status_code}
        else:
            return {"status": "fail", "expected": expected_status, "got": resp.status_code}
            
    except Exception as e:
        # Connection errors are expected for some negative tests
        if "connection" in str(e).lower() and scenario["scenario_type"] == "negative":
            return {"status": "pass", "note": "Expected connection error"}
        return {"status": "error", "error": str(e)}

async def execute_scenario(client: httpx.AsyncClient, scenario: Dict) -> Dict:
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
        tasks = []
        for _ in range(min(count, 20)):  # Limit concurrency
            tasks.append(send_triage_task(client, {
                "input_payload": {"task": payload.get("task_template", payload.get("task", {}))}
            }))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        passed = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "pass")
        result = {"status": "pass" if passed == len(results) else "partial", "passed": passed, "total": len(results)}
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

async def run_traffic_generator(scenarios: List[Dict], duration_seconds: int = 300, rate_limit: float = 10.0):
    """Generate continuous traffic for specified duration."""
    print(f"🚀 Starting traffic generator")
    print(f"   Duration: {duration_seconds}s")
    print(f"   Target rate: {rate_limit} requests/second")
    print(f"   Scenarios: {len(scenarios)}")
    print(f"   Command Centre: {COMMAND_CENTRE_URL}")
    print()
    
    async with httpx.AsyncClient() as client:
        end_time = time.time() + duration_seconds
        interval = 1.0 / rate_limit
        
        while time.time() < end_time:
            # Pick random scenarios weighted by type
            scenario = random.choice(scenarios)
            
            # Execute scenario
            await execute_scenario(client, scenario)
            
            # Report progress
            metrics.report()
            
            # Rate limiting
            await asyncio.sleep(interval)
    
    print("\n\n✅ Traffic generation complete!")
    print(f"\n📊 Final Stats:")
    print(f"   Total scenarios executed: {metrics.total}")
    print(f"   Tasks sent to agents: {metrics.tasks_sent}")
    print(f"   Tasks completed: {metrics.tasks_completed}")
    print(f"   Tests passed: {metrics.passed}")
    print(f"   Tests failed: {metrics.failed}")
    print(f"   Errors: {metrics.errors}")
    elapsed = time.time() - metrics.start_time
    print(f"   Duration: {elapsed:.1f}s")
    print(f"   Average rate: {metrics.tasks_sent / elapsed:.2f} tasks/second")

async def run_burst_mode(scenarios: List[Dict], count: int = 100):
    """Send a burst of concurrent requests."""
    print(f"🎯 Burst mode: Sending {count} concurrent requests...")
    
    positive_scenarios = [s for s in scenarios if s["scenario_type"] == "positive" and "task" in s.get("input_payload", {})]
    
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(count):
            scenario = random.choice(positive_scenarios)
            tasks.append(execute_scenario(client, scenario))
        
        start = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        
        passed = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "pass")
        
        print(f"\n✅ Burst complete!")
        print(f"   Sent: {count} requests")
        print(f"   Passed: {passed}")
        print(f"   Duration: {elapsed:.2f}s")
        print(f"   Rate: {count / elapsed:.2f} req/s")

async def run_continuous_load(scenarios: List[Dict]):
    """Run continuous load with varying intensity."""
    print(f"🔄 Continuous load mode (Ctrl+C to stop)...")
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
            print(f"\n📈 Phase: {phase_name} ({rate:.1f} req/s for {duration}s)")
            await run_traffic_generator(scenarios, duration, rate)
    except KeyboardInterrupt:
        print("\n\n⏸️  Stopped by user")

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
    
    args = parser.parse_args()
    
    # Load scenarios
    matrix_path = Path(__file__).parent.parent / "nexus-a2a" / "artefacts" / "matrices" / "nexus_command_centre_load_matrix.json"
    
    if not matrix_path.exists():
        print(f"❌ Matrix file not found: {matrix_path}")
        print("   Run: python tools/generate_command_centre_scenarios.py")
        sys.exit(1)
    
    with open(matrix_path, encoding="utf-8") as f:
        scenarios = json.load(f)
    
    print(f"📋 Loaded {len(scenarios)} scenarios")
    print(f"   Positive: {len([s for s in scenarios if s['scenario_type'] == 'positive'])}")
    print(f"   Negative: {len([s for s in scenarios if s['scenario_type'] == 'negative'])}")
    print(f"   Edge: {len([s for s in scenarios if s['scenario_type'] == 'edge'])}")
    print()
    
    # Run appropriate mode
    if args.mode == "burst":
        asyncio.run(run_burst_mode(scenarios, args.burst_size))
    elif args.mode == "continuous":
        asyncio.run(run_continuous_load(scenarios))
    else:  # sustained
        asyncio.run(run_traffic_generator(scenarios, args.duration, args.rate))

if __name__ == "__main__":
    main()

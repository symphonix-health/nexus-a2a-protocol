#!/usr/bin/env python3
"""Comprehensive HelixCare scenario runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GATEWAY_URL = "http://localhost:8100"


def _python_executable() -> str:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _resolve_gateway_url(gateway_arg: str | None) -> str | None:
    value = gateway_arg if gateway_arg is not None else os.getenv("NEXUS_ON_DEMAND_GATEWAY_URL")
    if not value:
        return None
    return value.strip().rstrip("/")


def _parse_gateway_port(gateway_url: str) -> int:
    parsed = urlparse(gateway_url)
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def check_ports(required_ports: list[int]) -> list[int]:
    """Return the subset of required ports that are currently listening."""
    try:
        result = subprocess.run(
            ["netstat", "-an"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        text = result.stdout
    except Exception:
        return []

    running: list[int] = []
    for port in required_ports:
        if f":{port} " in text:
            running.append(port)
    return running


def start_command_centre_monitor() -> subprocess.Popen | None:
    """Start the Command Centre monitor in background."""
    try:
        monitor_cmd = [_python_executable(), "tools/monitor_command_centre.py"]
        print("Starting Command Centre monitor...")
        return subprocess.Popen(
            monitor_cmd,
            cwd=str(ROOT),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except Exception as exc:
        print(f"Could not start monitor: {exc}")
        return None


async def run_scenario_batch(
    scenarios: list[str],
    batch_name: str,
    *,
    gateway_url: str | None,
    retry_mode: str | None,
) -> list[dict]:
    """Run a batch of scenarios and return per-scenario results."""
    print(f"\nRunning {batch_name} ({len(scenarios)} scenarios)")

    results: list[dict] = []
    start_time = time.time()

    for scenario_name in scenarios:
        scenario_start = time.time()
        cmd = [_python_executable(), "tools/helixcare_scenarios.py", "--run", scenario_name]
        if retry_mode:
            cmd.extend(["--retry-mode", retry_mode])
        if gateway_url:
            cmd.extend(["--gateway", gateway_url])

        print(f"  Running: {scenario_name}")

        try:
            child_env = os.environ.copy()
            child_env.setdefault("PYTHONUTF8", "1")
            result = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(ROOT),
                env=child_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            duration = time.time() - scenario_start

            if result.returncode == 0:
                print(f"  PASSED ({duration:.1f}s)")
                status = "PASSED"
            else:
                print(f"  FAILED ({duration:.1f}s)")
                stdout_text = stdout.decode(errors="replace").strip()
                stderr_text = stderr.decode(errors="replace").strip()
                if stderr_text:
                    print(f"  STDERR: {stderr_text}")
                elif stdout_text:
                    print(f"  STDOUT: {stdout_text}")
                status = "FAILED"

            results.append(
                {
                    "scenario": scenario_name,
                    "status": status,
                    "duration": round(duration, 1),
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception as exc:
            duration = time.time() - scenario_start
            print(f"  ERROR ({duration:.1f}s): {exc}")
            results.append(
                {
                    "scenario": scenario_name,
                    "status": "ERROR",
                    "duration": round(duration, 1),
                    "error": str(exc),
                    "timestamp": datetime.now().isoformat(),
                }
            )

    total_duration = time.time() - start_time
    print(f"  Batch completed in {total_duration:.1f}s")
    return results


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run all HelixCare scenario batches")
    parser.add_argument(
        "--gateway",
        nargs="?",
        const=DEFAULT_GATEWAY_URL,
        help=f"Route scenario RPC through on-demand gateway (default: {DEFAULT_GATEWAY_URL})",
    )
    parser.add_argument(
        "--retry-mode",
        choices=["strict-zero", "balanced", "fast"],
        help="Retry profile passthrough",
    )
    args = parser.parse_args()

    gateway_url = _resolve_gateway_url(args.gateway)

    print("HelixCare Comprehensive Scenario Runner")
    print("=" * 60)
    if args.retry_mode:
        print(f"Retry profile: {args.retry_mode}")
    if gateway_url:
        print(f"On-demand gateway mode: {gateway_url}")

    if gateway_url:
        required_ports = [_parse_gateway_port(gateway_url), 8099]
    else:
        required_ports = [8021, 8022, 8024, 8025, 8026, 8027, 8028, 8029, 8099]

    running_ports = check_ports(required_ports)
    if len(running_ports) < len(required_ports):
        missing = [port for port in required_ports if port not in running_ports]
        print(f"Some services may not be running. Missing ports: {missing}")
        if gateway_url:
            print(
                "Start gateway with: "
                ".\\.venv\\Scripts\\python.exe -m uvicorn "
                "shared.on_demand_gateway.app.main:app --host 0.0.0.0 --port 8100"
            )
        else:
            print("Start agents with: .\\.venv\\Scripts\\python.exe tools/launch_all_agents.py")
        response = input("Continue anyway? (y/N): ")
        if response.strip().lower() != "y":
            return 2

    monitor_process = start_command_centre_monitor()

    batches = {
        "Cardiac and Respiratory": ["chest_pain_cardiac", "pediatric_asthma_exacerbation"],
        "Trauma and Orthopedic": ["orthopedic_fracture", "trauma_motor_vehicle_accident"],
        "Infectious Diseases": ["pediatric_fever_sepsis", "infectious_disease_outbreak"],
        "Mental Health and Chronic": [
            "mental_health_crisis",
            "geriatric_confusion",
            "chronic_diabetes_complication",
        ],
        "Obstetric and Complex": ["obstetric_emergency"],
    }

    all_results: list[dict] = []
    total_start_time = time.time()

    print("\nRunning all scenario batches...")
    print("=" * 60)

    for batch_name, scenarios in batches.items():
        batch_results = await run_scenario_batch(
            scenarios,
            batch_name,
            gateway_url=gateway_url,
            retry_mode=args.retry_mode,
        )
        all_results.extend(batch_results)
        await asyncio.sleep(2)

    total_duration = time.time() - total_start_time
    passed = sum(1 for row in all_results if row["status"] == "PASSED")
    total = len(all_results)
    failed = total - passed

    print("\n" + "=" * 60)
    print("SCENARIO RUN RESULTS")
    print("=" * 60)
    print(f"Total Scenarios: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed / total) * 100:.1f}%")
    print(f"Total Duration: {total_duration:.1f}s")
    print(f"Average per Scenario: {total_duration / total:.1f}s")

    results_file = ROOT / f"scenario_results_{int(time.time())}.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "summary": {
                    "total_scenarios": total,
                    "passed": passed,
                    "failed": failed,
                    "success_rate": round((passed / total) * 100, 1),
                    "total_duration": round(total_duration, 1),
                    "average_duration": round(total_duration / total, 1),
                    "timestamp": datetime.now().isoformat(),
                },
                "results": all_results,
            },
            f,
            indent=2,
        )

    print(f"\nDetailed results saved to: {results_file}")

    if monitor_process:
        print("Close the Command Centre monitor window when done")
        monitor_process.wait()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

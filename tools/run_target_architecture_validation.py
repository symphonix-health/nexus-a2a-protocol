#!/usr/bin/env python3
"""Run protocol-core and agent-integration validation as separate phases.

This script enforces the architectural separation of:
- protocol/runtime correctness tests
- demo-agent integration tests
- load-gate traffic sweeps
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "target_architecture_validation.json"

PROTOCOL_TEST_TARGETS = [
    "tests/test_nexus_protocol_contracts.py",
    "tests/test_hyperscale_load_matrix.py",
    "tests/test_architecture_boundaries.py",
    "tests/test_scale_profile_v1_1.py",
]

INTEGRATION_CORE_TEST_TARGETS = [
    "tests/nexus_harness/test_protocol_core.py",
    "tests/nexus_harness/test_protocol_streaming.py",
    "tests/nexus_harness/test_protocol_multitransport.py",
    "tests/nexus_harness/test_ed_triage.py",
    "tests/nexus_harness/test_telemed_scribe.py",
    "tests/nexus_harness/test_consent_verification.py",
    "tests/nexus_harness/test_public_health_surveillance.py",
]

INTEGRATION_COMMAND_CENTRE_TARGET = "tests/nexus_harness/test_command_centre.py"


def run_step(name: str, cmd: list[str], timeout: int) -> dict:
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = round(time.time() - t0, 2)
        return {
            "name": name,
            "command": cmd,
            "returncode": proc.returncode,
            "duration_s": duration,
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
            "passed": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        duration = round(time.time() - t0, 2)
        stdout = exc.stdout[-4000:] if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr[-4000:] if isinstance(exc.stderr, str) else ""
        return {
            "name": name,
            "command": cmd,
            "returncode": -9,
            "duration_s": duration,
            "stdout_tail": stdout,
            "stderr_tail": (stderr + f"\nTIMEOUT after {timeout}s").strip(),
            "passed": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run target-architecture validation suites")
    parser.add_argument("--skip-launch", action="store_true")
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--protocol-timeout", type=int, default=1800)
    parser.add_argument("--integration-timeout", type=int, default=3600)
    parser.add_argument("--load-duration", type=int, default=30)
    parser.add_argument("--load-rate", type=float, default=25.0)
    parser.add_argument("--gate-seed", type=int, default=1729)
    parser.add_argument("--gate-max-scenarios", type=int, default=24)
    parser.add_argument("--gate-scenario-timeout", type=float, default=25.0)
    parser.add_argument("--gate-max-concurrent-tasks", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ.setdefault("NEXUS_JWT_SECRET", "dev-secret-change-me")
    os.environ["NEXUS_HEALTH_LATENCY_DEGRADED_MS"] = "180000"
    report: dict = {
        "generated_at_epoch": int(time.time()),
        "steps": [],
        "overall_passed": True,
    }

    try:
        if not args.skip_launch:
            report["steps"].append(
                run_step(
                    "preclean_stop_agents",
                    [sys.executable, "tools/launch_all_agents.py", "--stop"],
                    timeout=120,
                )
            )

        report["steps"].append(
            run_step(
                "generate_load_matrix",
                [sys.executable, "tools/generate_load_matrix.py", "--emit-gates"],
                timeout=300,
            )
        )

        if not args.skip_launch:
            report["steps"].append(
                run_step(
                    "launch_agents",
                    [sys.executable, "tools/launch_all_agents.py", "--with-backend"],
                    timeout=300,
                )
            )

        report["steps"].append(
            run_step(
                "protocol_tests",
                [sys.executable, "-m", "pytest", *PROTOCOL_TEST_TARGETS, "-q"],
                timeout=args.protocol_timeout,
            )
        )
        report["steps"].append(
            run_step(
                "scale_profile_conformance",
                [sys.executable, "tools/run_scale_profile_conformance.py"],
                timeout=300,
            )
        )

        report["steps"].append(
            run_step(
                "integration_tests_core",
                [sys.executable, "-m", "pytest", *INTEGRATION_CORE_TEST_TARGETS, "-q", "--tb=short"],
                timeout=args.integration_timeout,
            )
        )

        if not args.skip_launch:
            report["steps"].append(
                run_step(
                    "restart_agents_for_command_centre_stop",
                    [sys.executable, "tools/launch_all_agents.py", "--stop"],
                    timeout=120,
                )
            )
            report["steps"].append(
                run_step(
                    "restart_agents_for_command_centre_launch",
                    [sys.executable, "tools/launch_all_agents.py", "--with-backend"],
                    timeout=300,
                )
            )

        report["steps"].append(
            run_step(
                "integration_tests_command_centre",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    INTEGRATION_COMMAND_CENTRE_TARGET,
                    "-q",
                    "--tb=short",
                ],
                timeout=min(args.integration_timeout, 1800),
            )
        )

        if not args.skip_load:
            if not args.skip_launch:
                report["steps"].append(
                    run_step(
                        "restart_agents_for_load_stop",
                        [sys.executable, "tools/launch_all_agents.py", "--stop"],
                        timeout=120,
                    )
                )
                report["steps"].append(
                    run_step(
                        "restart_agents_for_load_launch",
                        [sys.executable, "tools/launch_all_agents.py", "--with-backend"],
                        timeout=300,
                    )
                )

            gate_timeout = max(
                600,
                int(args.load_duration + max(args.gate_scenario_timeout, 1.0) + 120),
            )
            for gate in ("g0", "g1", "g2", "g3", "g4"):
                report["steps"].append(
                    run_step(
                        f"load_gate_{gate}",
                        [
                            sys.executable,
                            "tools/traffic_generator.py",
                            "--mode",
                            "sustained",
                            "--duration",
                            str(args.load_duration),
                            "--rate",
                            str(args.load_rate),
                            "--gate",
                            gate,
                            "--strict-positive",
                            "--deterministic",
                            "--seed",
                            str(args.gate_seed),
                            "--max-scenarios",
                            str(args.gate_max_scenarios),
                            "--scenario-timeout",
                            str(args.gate_scenario_timeout),
                            "--max-concurrent-tasks",
                            str(args.gate_max_concurrent_tasks),
                        ],
                        timeout=gate_timeout,
                    )
                )
    finally:
        if not args.skip_launch:
            report["steps"].append(
                run_step(
                    "stop_agents",
                    [sys.executable, "tools/launch_all_agents.py", "--stop"],
                    timeout=120,
                )
            )

        report["overall_passed"] = all(step.get("passed", False) for step in report["steps"])
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

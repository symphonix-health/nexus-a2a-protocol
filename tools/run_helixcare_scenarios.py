#!/usr/bin/env python3
"""
HelixCare Scenario Runner

Simple script to run patient journey scenarios for testing and demonstration.
"""

import argparse
import asyncio
import os
import subprocess
from urllib.parse import urlparse

from additional_scenarios import ADDITIONAL_SCENARIOS
from helixcare_scenarios import RETRY_MODE_CONFIGS, SCENARIOS
from scenario_coverage import build_coverage_report


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


def check_agents_running(gateway_url: str | None = None):
    """Check if all required agents are running."""
    if gateway_url:
        required_ports = [_parse_gateway_port(gateway_url), 8099]
    else:
        required_ports = [
            8021,
            8022,
            8024,
            8025,
            8026,
            8027,
            8028,
            8029,
            8034,
            8035,
            8036,
            8037,
            8038,
            8099,
        ]
    running = []

    for port in required_ports:
        try:
            result = subprocess.run(["netstat", "-an"], capture_output=True, text=True, timeout=5)
            if f":{port} " in result.stdout:
                running.append(port)
        except Exception:
            pass

    return running


def start_command_centre_monitor():
    """Start the Command Centre monitor in background."""
    try:
        monitor_cmd = [r".\.venv\Scripts\python.exe", "tools/monitor_command_centre.py"]
        print("📊 Starting Command Centre monitor...")
        return subprocess.Popen(
            monitor_cmd, cwd=r"C:\nexus-a2a-protocol", creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    except Exception as e:
        print(f"⚠️  Could not start monitor: {e}")
        return None


async def run_scenario(
    scenario_name: str,
    retry_mode: str | None = None,
    gateway_url: str | None = None,
):
    """Run a specific scenario."""
    cmd = [r".\.venv\Scripts\python.exe", "tools/helixcare_scenarios.py", "--run", scenario_name]
    if retry_mode:
        cmd.extend(["--retry-mode", retry_mode])
    if gateway_url:
        cmd.extend(["--gateway", gateway_url])

    print(f"🏥 Running scenario: {scenario_name}")
    print(f"   ↳ Command: {' '.join(cmd)}")
    try:
        child_env = os.environ.copy()
        child_env.setdefault("PYTHONUTF8", "1")
        result = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=r"C:\nexus-a2a-protocol",
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()

        if result.returncode == 0:
            print(f"✅ Scenario '{scenario_name}' completed successfully")
            print(stdout.decode())
        else:
            print(f"❌ Scenario '{scenario_name}' failed")
            print("STDOUT:", stdout.decode())
            print("STDERR:", stderr.decode())

    except Exception as e:
        print(f"❌ Error running scenario '{scenario_name}': {e}")


async def main():
    """Main runner function."""
    parser = argparse.ArgumentParser(description="Run all HelixCare scenarios via orchestrator")
    parser.add_argument(
        "--retry-mode",
        choices=sorted(RETRY_MODE_CONFIGS.keys()),
        help="Retry profile passthrough for scenario runner",
    )
    parser.add_argument(
        "--gateway",
        nargs="?",
        const="http://localhost:8100",
        help="Route scenario RPC via on-demand gateway URL.",
    )
    args = parser.parse_args()
    gateway_url = _resolve_gateway_url(args.gateway)

    print("🚀 HelixCare Scenario Runner")
    print("=" * 50)
    if args.retry_mode:
        print(f"⚙ Passthrough retry profile: {args.retry_mode}")
    if gateway_url:
        print(f"⚙ On-demand gateway mode: {gateway_url}")

    # Check if agents are running
    running_ports = check_agents_running(gateway_url=gateway_url)
    if gateway_url:
        required_ports = [_parse_gateway_port(gateway_url), 8099]
    else:
        required_ports = [
            8021,
            8022,
            8024,
            8025,
            8026,
            8027,
            8028,
            8029,
            8034,
            8035,
            8036,
            8037,
            8038,
            8099,
        ]

    if len(running_ports) < len(required_ports):
        missing = [p for p in required_ports if p not in running_ports]
        print(f"⚠️  Some agents may not be running. Missing ports: {missing}")
        if gateway_url:
            print(
                "💡 Start gateway with: "
                ".\\.venv\\Scripts\\python.exe -m uvicorn "
                "shared.on_demand_gateway.app.main:app --host 0.0.0.0 --port 8100"
            )
        else:
            print("💡 Start agents with: .\\.venv\\Scripts\\python.exe tools/launch_all_agents.py")
        input("Press Enter to continue anyway, or Ctrl+C to exit...")

    # Start Command Centre monitor
    monitor_process = start_command_centre_monitor()
    if monitor_process:
        print("📊 Command Centre monitor started (check new console window)")

    # Run canonical + additive variant scenarios
    combined_scenarios = SCENARIOS + ADDITIONAL_SCENARIOS
    coverage = build_coverage_report(combined_scenarios)
    if coverage.missing_agents:
        missing = sorted(coverage.missing_agents)
        print("❌ Scenario suite is missing configured agents:")
        print("   " + ", ".join(missing))
        print("💡 Add workflows so full suite touches all configured agents")
        raise SystemExit(2)

    print(
        "✅ Scenario coverage gate passed "
        "("
        f"{len(coverage.covered_agents)}"
        "/"
        f"{len(coverage.expected_agents)}"
        " agents)"
    )
    scenarios = [scenario.name for scenario in combined_scenarios]

    print(f"\n🏥 Running {len(scenarios)} patient journey scenarios...")
    print("Each scenario will exercise different agent combinations")
    print("Monitor the Command Centre for real-time activity")
    print("=" * 50)

    for scenario in scenarios:
        await run_scenario(scenario, retry_mode=args.retry_mode, gateway_url=gateway_url)
        print()  # Blank line between scenarios

    print("🎉 All scenarios completed!")
    print("Check the Command Centre monitor for detailed activity logs")

    if monitor_process:
        print("💡 Close the monitor window when done")
        monitor_process.wait()


if __name__ == "__main__":
    asyncio.run(main())

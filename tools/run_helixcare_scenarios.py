#!/usr/bin/env python3
"""
HelixCare Scenario Runner

Simple script to run patient journey scenarios for testing and demonstration.
"""

import asyncio
import subprocess

from additional_scenarios import ADDITIONAL_SCENARIOS
from helixcare_scenarios import SCENARIOS


def check_agents_running():
    """Check if all required agents are running."""
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
        except:
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


async def run_scenario(scenario_name: str):
    """Run a specific scenario."""
    cmd = [r".\.venv\Scripts\python.exe", "tools/helixcare_scenarios.py", "--run", scenario_name]

    print(f"🏥 Running scenario: {scenario_name}")
    try:
        result = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=r"C:\nexus-a2a-protocol",
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
    print("🚀 HelixCare Scenario Runner")
    print("=" * 50)

    # Check if agents are running
    running_ports = check_agents_running()
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
        print("💡 Start agents with: .\\.venv\\Scripts\\python.exe tools/launch_all_agents.py")
        input("Press Enter to continue anyway, or Ctrl+C to exit...")

    # Start Command Centre monitor
    monitor_process = start_command_centre_monitor()
    if monitor_process:
        print("📊 Command Centre monitor started (check new console window)")

    # Run canonical + additive variant scenarios
    scenarios = [scenario.name for scenario in SCENARIOS + ADDITIONAL_SCENARIOS]

    print(f"\n🏥 Running {len(scenarios)} patient journey scenarios...")
    print("Each scenario will exercise different agent combinations")
    print("Monitor the Command Centre for real-time activity")
    print("=" * 50)

    for scenario in scenarios:
        await run_scenario(scenario)
        print()  # Blank line between scenarios

    print("🎉 All scenarios completed!")
    print("Check the Command Centre monitor for detailed activity logs")

    if monitor_process:
        print("💡 Close the monitor window when done")
        monitor_process.wait()


if __name__ == "__main__":
    asyncio.run(main())

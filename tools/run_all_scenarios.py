#!/usr/bin/env python3
"""
Comprehensive HelixCare Scenario Runner

Runs all patient journey scenarios with monitoring and reporting.
"""

import asyncio
import subprocess
import sys
import time
import json
from datetime import datetime
from pathlib import Path

def check_agents_running():
    """Check if all required agents are running."""
    required_ports = [8021, 8022, 8024, 8025, 8026, 8027, 8028, 8029, 8099]
    running = []

    for port in required_ports:
        try:
            result = subprocess.run(
                ["netstat", "-an"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if f":{port} " in result.stdout:
                running.append(port)
        except:
            pass

    return running

def start_command_centre_monitor():
    """Start the Command Centre monitor in background."""
    try:
        monitor_cmd = [
            r".\.venv\Scripts\python.exe",
            "tools/monitor_command_centre.py"
        ]
        print("📊 Starting Command Centre monitor...")
        return subprocess.Popen(
            monitor_cmd,
            cwd=r"C:\nexus-a2a-protocol",
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    except Exception as e:
        print(f"⚠️  Could not start monitor: {e}")
        return None

async def run_scenario_batch(scenarios: List[str], batch_name: str):
    """Run a batch of scenarios."""
    print(f"\n🏥 Running {batch_name} ({len(scenarios)} scenarios)")

    results = []
    start_time = time.time()

    for scenario_name in scenarios:
        scenario_start = time.time()

        cmd = [
            r".\.venv\Scripts\python.exe",
            "tools/helixcare_scenarios.py",
            "--run", scenario_name
        ]

        print(f"   Running: {scenario_name}")

        try:
            result = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=r"C:\nexus-a2a-protocol",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            duration = time.time() - scenario_start

            if result.returncode == 0:
                status = "✅ PASSED"
                print(f"   {status} ({duration:.1f}s)")
            else:
                status = "❌ FAILED"
                print(f"   {status} ({duration:.1f}s)")
                print(f"   Error: {stderr.decode().strip()}")

            results.append({
                "scenario": scenario_name,
                "status": "PASSED" if result.returncode == 0 else "FAILED",
                "duration": round(duration, 1),
                "timestamp": datetime.now().isoformat()
            })

        except Exception as e:
            duration = time.time() - scenario_start
            print(f"   ❌ ERROR ({duration:.1f}s): {e}")
            results.append({
                "scenario": scenario_name,
                "status": "ERROR",
                "duration": round(duration, 1),
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })

    total_duration = time.time() - start_time
    print(f"   Batch completed in {total_duration:.1f}s")

    return results

async def main():
    """Main runner function."""
    print("🚀 HelixCare Comprehensive Scenario Runner")
    print("=" * 60)

    # Check if agents are running
    running_ports = check_agents_running()
    required_ports = [8021, 8022, 8024, 8025, 8026, 8027, 8028, 8029, 8099]

    if len(running_ports) < len(required_ports):
        missing = [p for p in required_ports if p not in running_ports]
        print(f"⚠️  Some agents may not be running. Missing ports: {missing}")
        print("💡 Start agents with: .\.venv\Scripts\python.exe tools/launch_all_agents.py")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return

    # Start Command Centre monitor
    monitor_process = start_command_centre_monitor()

    # Define scenario batches
    batches = {
        "Cardiac & Respiratory": ["chest_pain_cardiac", "pediatric_asthma_exacerbation"],
        "Trauma & Orthopedic": ["orthopedic_fracture", "trauma_motor_vehicle_accident"],
        "Infectious Diseases": ["pediatric_fever_sepsis", "infectious_disease_outbreak"],
        "Mental Health & Chronic": ["mental_health_crisis", "geriatric_confusion", "chronic_diabetes_complication"],
        "Obstetric & Complex": ["obstetric_emergency"]
    }

    all_results = []
    total_start_time = time.time()

    print("\n🏥 Running all scenario batches...")
    print("Monitor the Command Centre for real-time activity")
    print("=" * 60)

    for batch_name, scenarios in batches.items():
        batch_results = await run_scenario_batch(scenarios, batch_name)
        all_results.extend(batch_results)

        # Brief pause between batches
        await asyncio.sleep(2)

    # Generate report
    total_duration = time.time() - total_start_time
    passed = sum(1 for r in all_results if r["status"] == "PASSED")
    total = len(all_results)

    print("\n" + "=" * 60)
    print("📊 SCENARIO RUN RESULTS")
    print("=" * 60)
    print(f"Total Scenarios: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    print(f"Total Duration: {total_duration:.1f}s")
    print(f"Average per Scenario: {total_duration/total:.1f}s")

    # Save detailed results
    results_file = f"scenario_results_{int(time.time())}.json"
    with open(results_file, "w") as f:
        json.dump({
            "summary": {
                "total_scenarios": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round((passed/total)*100, 1),
                "total_duration": round(total_duration, 1),
                "average_duration": round(total_duration/total, 1),
                "timestamp": datetime.now().isoformat()
            },
            "results": all_results
        }, f, indent=2)

    print(f"\n💾 Detailed results saved to: {results_file}")

    if monitor_process:
        print("\n💡 Close the Command Centre monitor window when done")
        monitor_process.wait()

if __name__ == "__main__":
    asyncio.run(main())

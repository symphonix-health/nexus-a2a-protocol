#!/usr/bin/env python3
"""
HelixCare Scenario Manager

Comprehensive tool for managing, saving, and running patient journey scenarios.
"""

import json
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Import scenario definitions
from helixcare_scenarios import SCENARIOS as BASE_SCENARIOS
from additional_scenarios import ADDITIONAL_SCENARIOS

ALL_SCENARIOS = BASE_SCENARIOS + ADDITIONAL_SCENARIOS

def save_scenarios_to_json(filename: str = "tools/helixcare_all_scenarios.json"):
    """Save all scenarios to a JSON file."""
    scenarios_data = []
    for scenario in ALL_SCENARIOS:
        scenario_dict = {
            "name": scenario.name,
            "description": scenario.description,
            "patient_profile": scenario.patient_profile,
            "journey_steps": scenario.journey_steps,
            "expected_duration": scenario.expected_duration,
            "created_at": datetime.now().isoformat(),
            "version": "1.0"
        }
        scenarios_data.append(scenario_dict)

    with open(filename, "w", encoding='utf-8') as f:
        json.dump(scenarios_data, f, indent=2, ensure_ascii=False)

    print(f"💾 Saved {len(scenarios_data)} scenarios to {filename}")

def save_scenario_summaries(filename: str = "tools/scenario_summaries.md"):
    """Save scenario summaries to a markdown file."""
    with open(filename, "w", encoding='utf-8') as f:
        f.write("# HelixCare Patient Journey Scenarios\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Total Scenarios: {len(ALL_SCENARIOS)}\n\n")

        f.write("## Scenario Overview\n\n")
        for i, scenario in enumerate(ALL_SCENARIOS, 1):
            f.write(f"### {i}. {scenario.name.replace('_', ' ').title()}\n\n")
            f.write(f"**Description:** {scenario.description}\n\n")
            f.write(f"**Patient Profile:**\n")
            f.write(f"- Age: {scenario.patient_profile['age']}\n")
            f.write(f"- Gender: {scenario.patient_profile['gender']}\n")
            f.write(f"- Chief Complaint: {scenario.patient_profile['chief_complaint']}\n")
            f.write(f"- Urgency: {scenario.patient_profile['urgency']}\n\n")

            f.write(f"**Journey Steps:** {len(scenario.journey_steps)}\n\n")
            for j, step in enumerate(scenario.journey_steps, 1):
                agent_name = step['agent'].replace('_', ' ').title()
                f.write(f"{j}. **{agent_name}** - {step['method']}\n")

            f.write(f"\n**Expected Duration:** ~{scenario.expected_duration} seconds\n\n")
            f.write("---\n\n")

        f.write("## Agent Coverage\n\n")
        agents_used = set()
        for scenario in ALL_SCENARIOS:
            for step in scenario.journey_steps:
                agents_used.add(step['agent'])

        f.write("The following agents are exercised across all scenarios:\n\n")
        for agent in sorted(agents_used):
            agent_name = agent.replace('_', ' ').title()
            f.write(f"- **{agent_name}**\n")

        f.write(f"\n**Total Agents:** {len(agents_used)}\n")

    print(f"📝 Saved scenario summaries to {filename}")

def create_scenario_runner_script(filename: str = "tools/run_all_scenarios.py"):
    """Create a comprehensive scenario runner script."""
    script_content = '''#!/usr/bin/env python3
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
    print(f"\\n🏥 Running {batch_name} ({len(scenarios)} scenarios)")

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
        print("💡 Start agents with: .\\.venv\\Scripts\\python.exe tools/launch_all_agents.py")
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

    print("\\n🏥 Running all scenario batches...")
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

    print("\\n" + "=" * 60)
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

    print(f"\\n💾 Detailed results saved to: {results_file}")

    if monitor_process:
        print("\\n💡 Close the Command Centre monitor window when done")
        monitor_process.wait()

if __name__ == "__main__":
    asyncio.run(main())
'''

    with open(filename, "w", encoding='utf-8') as f:
        f.write(script_content)

    print(f"🏃 Created comprehensive runner script: {filename}")

def create_scenario_validator(filename: str = "tools/validate_scenarios.py"):
    """Create a scenario validation script."""
    script_content = '''#!/usr/bin/env python3
"""
HelixCare Scenario Validator

Validates scenario definitions and checks agent availability.
"""

import json
import asyncio
import httpx
from pathlib import Path

async def validate_scenario_structure(scenario_data: dict) -> bool:
    """Validate scenario JSON structure."""
    required_fields = ["name", "description", "patient_profile", "journey_steps", "expected_duration"]

    for field in required_fields:
        if field not in scenario_data:
            print(f"❌ Missing required field: {field}")
            return False

    # Validate patient profile
    profile_required = ["age", "gender", "chief_complaint", "urgency"]
    for field in profile_required:
        if field not in scenario_data["patient_profile"]:
            print(f"❌ Missing patient profile field: {field}")
            return False

    # Validate journey steps
    for i, step in enumerate(scenario_data["journey_steps"]):
        step_required = ["agent", "method", "params"]
        for field in step_required:
            if field not in step:
                print(f"❌ Step {i+1}: Missing required field: {field}")
                return False

    return True

async def check_agent_availability(base_urls: dict) -> dict:
    """Check if agents are responding."""
    results = {}

    for agent_name, url in base_urls.items():
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/health")
                if response.status_code == 200:
                    results[agent_name] = "✅ Available"
                else:
                    results[agent_name] = f"⚠️  Status {response.status_code}"
        except Exception as e:
            results[agent_name] = f"❌ Unavailable: {str(e)}"

    return results

def main():
    """Main validation function."""
    print("🔍 HelixCare Scenario Validator")
    print("=" * 40)

    # Load scenarios
    scenarios_file = "tools/helixcare_all_scenarios.json"
    if not Path(scenarios_file).exists():
        print(f"❌ Scenarios file not found: {scenarios_file}")
        return

    with open(scenarios_file, "r", encoding='utf-8') as f:
        scenarios = json.load(f)

    print(f"📋 Loaded {len(scenarios)} scenarios")

    # Validate structure
    print("\\n🔍 Validating scenario structures...")
    valid_count = 0
    for scenario in scenarios:
        if asyncio.run(validate_scenario_structure(scenario)):
            valid_count += 1
        else:
            print(f"❌ Invalid scenario: {scenario.get('name', 'Unknown')}")

    print(f"✅ Valid scenarios: {valid_count}/{len(scenarios)}")

    # Check agent availability
    base_urls = {
        "triage": "http://localhost:8021",
        "diagnosis": "http://localhost:8022",
        "imaging": "http://localhost:8024",
        "pharmacy": "http://localhost:8025",
        "bed_manager": "http://localhost:8026",
        "discharge": "http://localhost:8027",
        "followup": "http://localhost:8028",
        "coordinator": "http://localhost:8029",
        "command_centre": "http://localhost:8099"
    }

    print("\\n🔍 Checking agent availability...")
    agent_status = asyncio.run(check_agent_availability(base_urls))

    for agent, status in agent_status.items():
        print(f"   {agent.replace('_', ' ').title()}: {status}")

    available_count = sum(1 for s in agent_status.values() if s.startswith("✅"))
    print(f"\\n✅ Available agents: {available_count}/{len(agent_status)}")

    # Summary
    print("\\n" + "=" * 40)
    if valid_count == len(scenarios) and available_count == len(agent_status):
        print("🎉 All validations passed! Ready to run scenarios.")
    else:
        print("⚠️  Some validations failed. Check output above.")

if __name__ == "__main__":
    main()
'''

    with open(filename, "w", encoding='utf-8') as f:
        f.write(script_content)

    print(f"✅ Created validator script: {filename}")

def main():
    """Main scenario management function."""
    print("🗂️  HelixCare Scenario Manager")
    print("=" * 40)

    # Save all scenarios to JSON
    save_scenarios_to_json()

    # Save scenario summaries
    save_scenario_summaries()

    # Create runner scripts
    create_scenario_runner_script()
    create_scenario_validator()

    print("\n📁 Files created:")
    print("  • tools/helixcare_all_scenarios.json - All scenario definitions")
    print("  • tools/scenario_summaries.md - Human-readable scenario summaries")
    print("  • tools/run_all_scenarios.py - Comprehensive scenario runner")
    print("  • tools/validate_scenarios.py - Scenario and agent validation")

    print(f"\n📊 Total scenarios saved: {len(ALL_SCENARIOS)}")
    print("🏥 Scenarios cover diverse medical conditions and agent interactions")
    print("🚀 Ready for testing and demonstration!")

if __name__ == "__main__":
    main()
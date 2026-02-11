#!/usr/bin/env python3
"""
Test all HelixCare scenarios with real-time Command Centre monitoring.

This script runs all 10 patient journey scenarios and monitors the Command Centre
for real-time updates.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def test_scenario_connectivity():
    """Test if scenarios can connect to agents."""
    import httpx

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

    print("🔍 Testing agent connectivity...")
    connected = []
    failed = []

    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in base_urls.items():
            try:
                response = await client.get(f"{url}/.well-known/health")
                if response.status_code == 200:
                    connected.append(name)
                    print(f"✅ {name}: {url} - CONNECTED")
                else:
                    failed.append(name)
                    print(f"❌ {name}: {url} - HTTP {response.status_code}")
            except Exception as e:
                failed.append(name)
                print(f"❌ {name}: {url} - ERROR: {str(e)[:50]}...")

    return connected, failed

async def run_single_scenario(scenario_name: str):
    """Run a single scenario from the JSON file."""
    print(f"\n🏥 Running scenario: {scenario_name}")

    try:
        # Load scenario from JSON
        with open("tools/helixcare_all_scenarios.json", "r") as f:
            all_scenarios = json.load(f)

        scenario_data = None
        for scenario in all_scenarios:
            if scenario["name"] == scenario_name:
                scenario_data = scenario
                break

        if not scenario_data:
            print(f"❌ Scenario '{scenario_name}' not found")
            return False

        # Import and run the scenario
        from tools.helixcare_scenarios import PatientScenario, run_scenario

        scenario = PatientScenario(
            name=scenario_data["name"],
            description=scenario_data["description"],
            patient_profile=scenario_data["patient_profile"],
            journey_steps=scenario_data["journey_steps"],
            expected_duration=scenario_data.get("expected_duration", 60)
        )

        await run_scenario(scenario)
        print(f"✅ Scenario '{scenario_name}' completed successfully")
        return True

    except Exception as e:
        print(f"❌ Error running scenario '{scenario_name}': {e}")
        return False

async def run_additional_scenario(scenario_name: str):
    """Run a scenario from additional_scenarios.py."""
    print(f"\n🏥 Running additional scenario: {scenario_name}")

    try:
        # Import the additional scenarios module
        import importlib.util
        spec = importlib.util.spec_from_file_location("additional_scenarios", "tools/additional_scenarios.py")
        additional_scenarios = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(additional_scenarios)

        # Find the scenario
        scenario_data = None
        for scenario in additional_scenarios.SCENARIOS:
            if scenario.name == scenario_name:
                scenario_data = scenario
                break

        if not scenario_data:
            print(f"❌ Additional scenario '{scenario_name}' not found")
            return False

        await additional_scenarios.run_scenario(scenario_data)
        print(f"✅ Additional scenario '{scenario_name}' completed successfully")
        return True

    except Exception as e:
        print(f"❌ Error running additional scenario '{scenario_name}': {e}")
        return False

async def main():
    """Main test function."""
    print("🚀 HelixCare Scenario Testing Suite")
    print("=" * 60)

    # Test connectivity first
    connected, failed = await test_scenario_connectivity()

    if failed:
        print(f"\n⚠️  Warning: {len(failed)} agents not accessible: {', '.join(failed)}")
        print("💡 Some scenarios may fail. Start agents with: python tools/launch_all_agents.py")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("❌ Test cancelled")
            return

    # Define all scenarios to test
    base_scenarios = [
        "chest_pain_cardiac",
        "pediatric_fever_sepsis",
        "orthopedic_fracture",
        "geriatric_confusion",
        "obstetric_emergency"
    ]

    additional_scenarios = [
        "mental_health_crisis",
        "chronic_diabetes_complication",
        "trauma_motor_vehicle_accident",
        "infectious_disease_outbreak",
        "pediatric_asthma_exacerbation"
    ]

    all_scenarios = base_scenarios + additional_scenarios

    print(f"\n🏥 Testing {len(all_scenarios)} patient journey scenarios...")
    print("Monitor the Command Centre at http://localhost:8099 for real-time updates")
    print("=" * 60)

    results = []

    # Run base scenarios
    for scenario in base_scenarios:
        success = await run_single_scenario(scenario)
        results.append((scenario, success))
        await asyncio.sleep(2)  # Brief pause between scenarios

    # Run additional scenarios
    for scenario in additional_scenarios:
        success = await run_additional_scenario(scenario)
        results.append((scenario, success))
        await asyncio.sleep(2)  # Brief pause between scenarios

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)

    successful = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]

    print(f"✅ Successful scenarios: {len(successful)}/{len(results)}")
    print(f"❌ Failed scenarios: {len(failed)}/{len(results)}")

    if successful:
        print("\n✅ PASSED:")
        for name, _ in successful:
            print(f"   • {name}")

    if failed:
        print("\n❌ FAILED:")
        for name, _ in failed:
            print(f"   • {name}")

    print("
🎯 Check the Command Centre at http://localhost:8099"    print("📋 View detailed logs in the Command Centre interface"
    if len(successful) == len(results):
        print("🎉 ALL SCENARIOS PASSED!")
        return 0
    else:
        print(f"⚠️  {len(failed)} scenarios failed - check agent connectivity")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
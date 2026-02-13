#!/usr/bin/env python3
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
    print("\n🔍 Validating scenario structures...")
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

    print("\n🔍 Checking agent availability...")
    agent_status = asyncio.run(check_agent_availability(base_urls))

    for agent, status in agent_status.items():
        print(f"   {agent.replace('_', ' ').title()}: {status}")

    available_count = sum(1 for s in agent_status.values() if s.startswith("✅"))
    print(f"\n✅ Available agents: {available_count}/{len(agent_status)}")

    # Summary
    print("\n" + "=" * 40)
    if valid_count == len(scenarios) and available_count == len(agent_status):
        print("🎉 All validations passed! Ready to run scenarios.")
    else:
        print("⚠️  Some validations failed. Check output above.")

if __name__ == "__main__":
    main()

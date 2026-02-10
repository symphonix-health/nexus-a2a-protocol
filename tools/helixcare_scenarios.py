#!/usr/bin/env python3
"""
HelixCare Patient Journey Scenarios Library

A collection of realistic patient visit scenarios that exercise different
paths through the HelixCare AI Hospital system. Each scenario tests
different combinations of agents and workflows.
"""

import asyncio
import json
import time
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, List
from dataclasses import dataclass

# Add the project root to Python path to import shared modules
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.nexus_common.auth import mint_jwt

# Configuration
BASE_URLS = {
    "triage": "http://localhost:8021",
    "diagnosis": "http://localhost:8022",
    "imaging": "http://localhost:8024",
    "pharmacy": "http://localhost:8025",
    "bed_manager": "http://localhost:8026",
    "discharge": "http://localhost:8027",
    "followup": "http://localhost:8028",
    "coordinator": "http://localhost:8029"
}

@dataclass
class PatientScenario:
    """Represents a complete patient journey scenario."""
    name: str
    description: str
    patient_profile: Dict[str, Any]
    journey_steps: List[Dict[str, Any]]
    expected_duration: int  # seconds

def create_jwt_token(subject: str = "test-patient-scenario") -> str:
    """Create JWT token for authentication."""
    return mint_jwt(subject, "dev-secret-change-me")

async def make_jsonrpc_call(url: str, method: str, params: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """Make a JSON-RPC call to an agent."""
    headers = {
        "Authorization": f"Bearer {create_jwt_token()}",
        "Content-Type": "application/json"
    }

    payload = {
        "jsonrpc": "2.0",
        "id": task_id,
        "method": method,
        "params": params
    }

    print(f"📞 Calling {url}/rpc - Method: {method}")
    print(f"   Params: {json.dumps(params, indent=2)}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(f"{url}/rpc", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            print(f"   ✅ Response: {json.dumps(result, indent=2)}")
            return result
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return {"error": str(e)}

# Define comprehensive patient scenarios
SCENARIOS = [
    PatientScenario(
        name="chest_pain_cardiac",
        description="Adult male with chest pain - suspected cardiac event",
        patient_profile={
            "age": 55,
            "gender": "male",
            "chief_complaint": "Severe chest pain, shortness of breath",
            "urgency": "high"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Severe chest pain, shortness of breath, nausea",
                    "vital_signs": {"blood_pressure": "160/95", "heart_rate": 110, "temperature": 98.6, "oxygen_saturation": 95, "respiratory_rate": 22},
                    "chief_complaint": "Chest pain for 2 hours",
                    "arrival_time": datetime.now().isoformat()
                },
                "delay": 2
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Severe chest pain, shortness of breath, nausea",
                    "vital_signs": {"blood_pressure": "160/95", "heart_rate": 110, "temperature": 98.6, "oxygen_saturation": 95, "respiratory_rate": 22},
                    "differential_diagnosis": ["Acute Coronary Syndrome", "Pulmonary Embolism", "Pneumothorax"]
                },
                "delay": 3
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "chest_xray", "priority": "urgent", "indication": "Rule out pneumothorax, pulmonary edema"},
                        {"type": "ecg", "priority": "urgent", "indication": "Evaluate for ST changes, arrhythmias"}
                    ]
                },
                "delay": 4
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Aspirin", "dose": "325mg", "route": "oral", "frequency": "once", "indication": "Antiplatelet therapy"},
                        {"drug": "Nitroglycerin", "dose": "0.4mg", "route": "sublingual", "frequency": "as needed", "indication": "Chest pain relief"}
                    ],
                    "allergies": ["Penicillin"],
                    "renal_function": "Normal"
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "emergency",
                    "required_monitoring": "telemetry",
                    "estimated_los": "2-3 days",
                    "special_requirements": ["Cardiac monitoring", "Frequent vital signs"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "cardiac_chest_pain",
                    "current_phase": "diagnostic_workup",
                    "coordination_tasks": ["Monitor cardiac enzymes", "Consult cardiology", "Schedule stress test"],
                    "risk_level": "high"
                },
                "delay": 3
            },
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "discharge_diagnosis": "Unstable Angina",
                    "discharge_disposition": "home",
                    "followup_instructions": ["Follow up with cardiology in 1 week", "Continue aspirin 325mg daily"]
                },
                "delay": 2
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {"type": "cardiology_clinic", "when": (datetime.now() + timedelta(days=7)).isoformat(), "purpose": "Follow-up after unstable angina"},
                        {"type": "stress_test", "when": (datetime.now() + timedelta(days=14)).isoformat(), "purpose": "Risk stratification"}
                    ]
                },
                "delay": 2
            }
        ],
        expected_duration=25
    ),

    PatientScenario(
        name="pediatric_fever_sepsis",
        description="Child with high fever - suspected sepsis workup",
        patient_profile={
            "age": 3,
            "gender": "female",
            "chief_complaint": "High fever, lethargy, poor feeding",
            "urgency": "high"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "High fever, lethargy, poor feeding, irritability",
                    "vital_signs": {"blood_pressure": "85/50", "heart_rate": 160, "temperature": 103.5, "oxygen_saturation": 97, "respiratory_rate": 35},
                    "chief_complaint": "Fever for 3 days, worsening lethargy",
                    "arrival_time": datetime.now().isoformat()
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "High fever, lethargy, poor feeding, irritability",
                    "vital_signs": {"blood_pressure": "85/50", "heart_rate": 160, "temperature": 103.5, "oxygen_saturation": 97, "respiratory_rate": 35},
                    "differential_diagnosis": ["Sepsis", "Viral infection", "Urinary tract infection", "Pneumonia"]
                },
                "delay": 2
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "chest_xray", "priority": "urgent", "indication": "Rule out pneumonia"},
                        {"type": "abdominal_ultrasound", "priority": "urgent", "indication": "Evaluate for UTI, appendicitis"}
                    ]
                },
                "delay": 3
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Ceftriaxone", "dose": "50mg/kg", "route": "IV", "frequency": "once", "indication": "Empiric antibiotic therapy"},
                        {"drug": "Acetaminophen", "dose": "15mg/kg", "route": "rectal", "frequency": "q4-6h PRN", "indication": "Fever control"}
                    ],
                    "allergies": [],
                    "renal_function": "Normal",
                    "weight_kg": 15
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "emergency",
                    "required_monitoring": "continuous",
                    "estimated_los": "3-5 days",
                    "special_requirements": ["Pediatric monitoring", "Isolation precautions", "Frequent vital signs"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "pediatric_sepsis",
                    "current_phase": "sepsis_workup",
                    "coordination_tasks": ["Blood cultures", "Lumbar puncture", "Pediatric ICU consult", "Fluid resuscitation"],
                    "risk_level": "critical"
                },
                "delay": 3
            }
        ],
        expected_duration=18
    ),

    PatientScenario(
        name="orthopedic_fracture",
        description="Adult with extremity fracture - orthopedic evaluation",
        patient_profile={
            "age": 28,
            "gender": "male",
            "chief_complaint": "Left leg pain after fall",
            "urgency": "medium"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Severe left leg pain, deformity, inability to bear weight",
                    "vital_signs": {"blood_pressure": "130/80", "heart_rate": 85, "temperature": 98.2, "oxygen_saturation": 99, "respiratory_rate": 16},
                    "chief_complaint": "Fell from ladder, left leg injury",
                    "arrival_time": datetime.now().isoformat()
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Severe left leg pain, deformity, inability to bear weight",
                    "vital_signs": {"blood_pressure": "130/80", "heart_rate": 85, "temperature": 98.2, "oxygen_saturation": 99, "respiratory_rate": 16},
                    "differential_diagnosis": ["Tibia/fibula fracture", "Ankle fracture", "Soft tissue injury"]
                },
                "delay": 2
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "xray_left_leg", "priority": "urgent", "indication": "Evaluate for fracture"},
                        {"type": "xray_left_ankle", "priority": "urgent", "indication": "Complete extremity evaluation"}
                    ]
                },
                "delay": 3
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Oxycodone", "dose": "5-10mg", "route": "oral", "frequency": "q4-6h PRN", "indication": "Pain control"},
                        {"drug": "Ibuprofen", "dose": "600mg", "route": "oral", "frequency": "q8h", "indication": "Inflammation reduction"}
                    ],
                    "allergies": ["Codeine"],
                    "renal_function": "Normal"
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "elective",
                    "required_monitoring": "standard",
                    "estimated_los": "1-2 days",
                    "special_requirements": ["Orthopedic precautions", "Crutches training"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "orthopedic_fracture",
                    "current_phase": "post_operative",
                    "coordination_tasks": ["Orthopedic consult", "Physical therapy evaluation", "Pain management"],
                    "risk_level": "medium"
                },
                "delay": 2
            },
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "discharge_diagnosis": "Closed tibia fracture",
                    "discharge_disposition": "home",
                    "followup_instructions": ["Orthopedic clinic in 1 week", "Non-weight bearing for 3 weeks", "DVT prophylaxis"]
                },
                "delay": 2
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {"type": "orthopedic_clinic", "when": (datetime.now() + timedelta(days=7)).isoformat(), "purpose": "Cast check and wound care"},
                        {"type": "physical_therapy", "when": (datetime.now() + timedelta(days=14)).isoformat(), "purpose": "Mobility assessment"}
                    ]
                },
                "delay": 2
            }
        ],
        expected_duration=20
    ),

    PatientScenario(
        name="geriatric_confusion",
        description="Elderly patient with acute confusion - delirium workup",
        patient_profile={
            "age": 78,
            "gender": "female",
            "chief_complaint": "Sudden confusion and agitation",
            "urgency": "high"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Acute confusion, agitation, disorientation, hallucinations",
                    "vital_signs": {"blood_pressure": "145/85", "heart_rate": 95, "temperature": 99.1, "oxygen_saturation": 94, "respiratory_rate": 20},
                    "chief_complaint": "Sudden change in mental status",
                    "arrival_time": datetime.now().isoformat()
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Acute confusion, agitation, disorientation, hallucinations",
                    "vital_signs": {"blood_pressure": "145/85", "heart_rate": 95, "temperature": 99.1, "oxygen_saturation": 94, "respiratory_rate": 20},
                    "differential_diagnosis": ["Urinary tract infection", "Medication toxicity", "Metabolic disturbance", "Stroke"]
                },
                "delay": 3
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "ct_head", "priority": "urgent", "indication": "Rule out stroke, mass lesion"},
                        {"type": "chest_xray", "priority": "routine", "indication": "Rule out pneumonia"}
                    ]
                },
                "delay": 4
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Haloperidol", "dose": "0.5-1mg", "route": "IV", "frequency": "q2-4h PRN", "indication": "Agitation control"},
                        {"drug": "Lorazepam", "dose": "0.5mg", "route": "IV", "frequency": "q4-6h PRN", "indication": "Anxiety reduction"}
                    ],
                    "allergies": ["Aspirin"],
                    "renal_function": "Mild impairment",
                    "current_medications": ["Warfarin", "Metoprolol", "Lisinopril", "Simvastatin"]
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "emergency",
                    "required_monitoring": "continuous",
                    "estimated_los": "3-7 days",
                    "special_requirements": ["Fall precautions", "1:1 sitter", "Delirium protocol"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "geriatric_delirium",
                    "current_phase": "diagnostic_workup",
                    "coordination_tasks": ["Comprehensive geriatric assessment", "Family meeting", "Discharge planning"],
                    "risk_level": "high"
                },
                "delay": 3
            }
        ],
        expected_duration=22
    ),

    PatientScenario(
        name="obstetric_emergency",
        description="Pregnant patient with vaginal bleeding - obstetric emergency",
        patient_profile={
            "age": 32,
            "gender": "female",
            "chief_complaint": "Vaginal bleeding in pregnancy",
            "urgency": "critical"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Heavy vaginal bleeding, abdominal pain, lightheadedness",
                    "vital_signs": {"blood_pressure": "95/60", "heart_rate": 115, "temperature": 98.0, "oxygen_saturation": 98, "respiratory_rate": 24},
                    "chief_complaint": "Bleeding at 28 weeks gestation",
                    "arrival_time": datetime.now().isoformat()
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Heavy vaginal bleeding, abdominal pain, lightheadedness",
                    "vital_signs": {"blood_pressure": "95/60", "heart_rate": 115, "temperature": 98.0, "oxygen_saturation": 98, "respiratory_rate": 24},
                    "differential_diagnosis": ["Placental abruption", "Placenta previa", "Vasa previa", "Uterine rupture"]
                },
                "delay": 2
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "obstetric_ultrasound", "priority": "emergent", "indication": "Evaluate placental position, fetal well-being"},
                        {"type": "fetal_monitoring", "priority": "emergent", "indication": "Continuous fetal heart rate monitoring"}
                    ]
                },
                "delay": 3
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Betamethasone", "dose": "12mg", "route": "IM", "frequency": "twice 24h apart", "indication": "Fetal lung maturity"},
                        {"drug": "Magnesium sulfate", "dose": "4g IV load", "route": "IV", "frequency": "once", "indication": "Neuroprotection"}
                    ],
                    "allergies": [],
                    "renal_function": "Normal",
                    "pregnancy_status": "28 weeks gestation"
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "emergency",
                    "required_monitoring": "intensive",
                    "estimated_los": "variable",
                    "special_requirements": ["Labor and delivery", "Fetal monitoring", "OB emergency team"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "obstetric_emergency",
                    "current_phase": "acute_management",
                    "coordination_tasks": ["Maternal-fetal medicine consult", "Neonatal team notification", "Blood bank preparation"],
                    "risk_level": "critical"
                },
                "delay": 3
            }
        ],
        expected_duration=18
    )
]

async def run_scenario(scenario: PatientScenario) -> None:
    """Execute a complete patient scenario."""
    patient_id = f"PAT-{int(time.time())}-{scenario.name}"
    visit_id = f"VISIT-{int(time.time())}-{scenario.name}"

    print(f"🏥 Starting Scenario: {scenario.name}")
    print(f"   Description: {scenario.description}")
    print(f"   Patient ID: {patient_id}")
    print(f"   Visit ID: {visit_id}")
    print(f"   Profile: {scenario.patient_profile}")
    print("=" * 80)

    for i, step in enumerate(scenario.journey_steps, 1):
        print(f"\nStep {i}/{len(scenario.journey_steps)}: {step['agent'].upper()}")

        # Add patient and visit IDs to all steps
        step_params = step['params'].copy()
        step_params['patient_id'] = patient_id
        step_params['visit_id'] = visit_id

        task_id = f"{visit_id}-{step['agent']}-{i}"

        result = await make_jsonrpc_call(
            BASE_URLS[step['agent']],
            step['method'],
            step_params,
            task_id
        )

        if 'delay' in step:
            await asyncio.sleep(step['delay'])

    print(f"\n✅ Scenario '{scenario.name}' completed!")
    print(f"   Duration: ~{scenario.expected_duration} seconds")
    print("=" * 80)

async def run_multiple_scenarios(scenario_names: List[str] = None, parallel: bool = False) -> None:
    """Run multiple scenarios."""
    if scenario_names is None:
        scenarios_to_run = SCENARIOS
    else:
        scenarios_to_run = [s for s in SCENARIOS if s.name in scenario_names]

    if not scenarios_to_run:
        print("❌ No matching scenarios found")
        return

    print(f"🚀 Running {len(scenarios_to_run)} scenario(s)")
    print(f"   Mode: {'Parallel' if parallel else 'Sequential'}")

    if parallel:
        tasks = [run_scenario(scenario) for scenario in scenarios_to_run]
        await asyncio.gather(*tasks)
    else:
        for scenario in scenarios_to_run:
            await run_scenario(scenario)
            # Brief pause between scenarios
            await asyncio.sleep(5)

async def list_scenarios() -> None:
    """List all available scenarios."""
    print("📋 Available HelixCare Patient Scenarios:")
    print("=" * 80)

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"{i:2d}. {scenario.name}")
        print(f"    {scenario.description}")
        print(f"    Patient: {scenario.patient_profile['age']}yo {scenario.patient_profile['gender']}, {scenario.patient_profile['chief_complaint']}")
        print(f"    Steps: {len(scenario.journey_steps)}, Duration: ~{scenario.expected_duration}s")
        print()

def save_scenarios_to_file() -> None:
    """Save all scenarios to a JSON file for later use."""
    scenarios_data = []
    for scenario in SCENARIOS:
        scenario_dict = {
            "name": scenario.name,
            "description": scenario.description,
            "patient_profile": scenario.patient_profile,
            "journey_steps": scenario.journey_steps,
            "expected_duration": scenario.expected_duration
        }
        scenarios_data.append(scenario_dict)

    with open("tools/helixcare_scenarios.json", "w") as f:
        json.dump(scenarios_data, f, indent=2, default=str)

    print("💾 Scenarios saved to tools/helixcare_scenarios.json")

async def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(description="HelixCare Patient Journey Scenarios")
    parser.add_argument("--list", action="store_true", help="List all available scenarios")
    parser.add_argument("--run", nargs="*", help="Run specific scenario(s) by name")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--parallel", action="store_true", help="Run scenarios in parallel")
    parser.add_argument("--save", action="store_true", help="Save scenarios to JSON file")

    args = parser.parse_args()

    if args.save:
        save_scenarios_to_file()
        return

    if args.list:
        await list_scenarios()
        return

    scenarios_to_run = []
    if args.run:
        scenarios_to_run = args.run
    elif args.all:
        scenarios_to_run = [s.name for s in SCENARIOS]

    if scenarios_to_run:
        await run_multiple_scenarios(scenarios_to_run, args.parallel)
    else:
        print("Use --list to see available scenarios")
        print("Use --run <name> to run specific scenarios")
        print("Use --all to run all scenarios")
        print("Use --save to save scenarios to file")

if __name__ == "__main__":
    asyncio.run(main())
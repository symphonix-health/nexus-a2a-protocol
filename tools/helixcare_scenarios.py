#!/usr/bin/env python3
"""HelixCare canonical patient-visit scenarios (definitive set of 10)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.nexus_common.auth import mint_jwt

BASE_URLS = {
    "triage": "http://localhost:8021",
    "diagnosis": "http://localhost:8022",
    "imaging": "http://localhost:8024",
    "pharmacy": "http://localhost:8025",
    "bed_manager": "http://localhost:8026",
    "discharge": "http://localhost:8027",
    "followup": "http://localhost:8028",
    "coordinator": "http://localhost:8029",
    "primary_care": "http://localhost:8034",
    "specialty_care": "http://localhost:8035",
    "telehealth": "http://localhost:8036",
    "home_visit": "http://localhost:8037",
    "ccm": "http://localhost:8038",
}


@dataclass
class PatientScenario:
    """Represents a complete patient journey scenario."""

    name: str
    description: str
    patient_profile: dict[str, Any]
    journey_steps: list[dict[str, Any]]
    expected_duration: int


def create_jwt_token(subject: str = "test-patient-scenario") -> str:
    return mint_jwt(subject, "dev-secret-change-me")


async def make_jsonrpc_call(
    url: str,
    method: str,
    params: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {create_jwt_token()}",
        "Content-Type": "application/json",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": task_id,
        "method": method,
        "params": params,
    }

    print(f"📞 Calling {url}/rpc - Method: {method}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{url}/rpc",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            print("   ✅ Response received")
            return result
        except Exception as exc:
            print(f"   ❌ Error: {exc}")
            return {"error": str(exc)}


def _step(
    agent: str,
    method: str,
    params: dict[str, Any],
    delay: int = 1,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "method": method,
        "params": params,
        "delay": delay,
    }


def _future(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()


SCENARIOS = [
    PatientScenario(
        name="primary_care_outpatient_in_person",
        description="In-person primary care visit with assessment, treatment, and checkout.",
        patient_profile={
            "age": 47,
            "gender": "female",
            "chief_complaint": "Fatigue and elevated blood pressure follow-up",
            "urgency": "medium",
        },
        journey_steps=[
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "in_person", "complaint": "fatigue and hypertension follow-up"},
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "fatigue, headaches",
                    "differential_diagnosis": ["Hypertension", "Anemia", "Thyroid dysfunction"],
                },
                2,
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {
                    "task": {
                        "med_plan": ["Lisinopril"],
                        "allergies": [],
                        "current_medications": ["Metformin"],
                    }
                },
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "primary_care",
                            "when": _future(30),
                            "purpose": "BP and lab review",
                        }
                    ]
                },
                1,
            ),
        ],
        expected_duration=12,
    ),
    PatientScenario(
        name="specialty_outpatient_clinic",
        description="Specialty clinic workflow with referral triage and diagnostics.",
        patient_profile={
            "age": 61,
            "gender": "male",
            "chief_complaint": "Progressive exertional chest discomfort",
            "urgency": "high",
        },
        journey_steps=[
            _step(
                "specialty_care",
                "specialty_care/manage_referral",
                {"specialty": "cardiology", "reason": "exertional angina assessment"},
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "exertional chest discomfort",
                    "differential_diagnosis": ["Stable angina", "GERD", "Aortic stenosis"],
                },
                2,
            ),
            _step(
                "imaging",
                "tasks/sendSubscribe",
                {
                    "orders": [
                        {"type": "ecg", "priority": "urgent", "indication": "cardiac rhythm"},
                        {
                            "type": "stress_echo",
                            "priority": "routine",
                            "indication": "ischemia workup",
                        },
                    ]
                },
                2,
            ),
            _step(
                "coordinator",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "journey_type": "specialty_outpatient",
                        "coordination_tasks": [
                            "Prior authorization",
                            "Procedure scheduling",
                            "PCP communication",
                        ],
                    }
                },
                2,
            ),
        ],
        expected_duration=14,
    ),
    PatientScenario(
        name="telehealth_video_consult",
        description="Video telehealth consult with identity/location verification and remote plan.",
        patient_profile={
            "age": 35,
            "gender": "female",
            "chief_complaint": "Migraine follow-up",
            "urgency": "low",
        },
        journey_steps=[
            _step(
                "telehealth",
                "telehealth/consult",
                {"modality": "video", "location_verified": True, "consent_documented": True},
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "recurrent migraines, photophobia",
                    "differential_diagnosis": ["Migraine", "Medication overuse headache"],
                },
                2,
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {"task": {"med_plan": ["Ibuprofen"], "allergies": [], "current_medications": []}},
                1,
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "telehealth",
                            "when": _future(14),
                            "purpose": "response to treatment",
                        }
                    ]
                },
                1,
            ),
        ],
        expected_duration=10,
    ),
    PatientScenario(
        name="telehealth_audio_only_followup",
        description="Audio-only telehealth follow-up with escalation guardrails.",
        patient_profile={
            "age": 73,
            "gender": "male",
            "chief_complaint": "Medication side-effect review",
            "urgency": "low",
        },
        journey_steps=[
            _step(
                "telehealth",
                "telehealth/consult",
                {"modality": "audio_only", "location_verified": True, "consent_documented": True},
            ),
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "audio_only", "complaint": "dizziness after medication change"},
            ),
            _step(
                "pharmacy", "pharmacy/check_interactions", {"drugs": ["Lisinopril", "Ibuprofen"]}, 1
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "in_person_primary_care",
                            "when": _future(7),
                            "purpose": "orthostatic vitals and exam",
                        }
                    ]
                },
                1,
            ),
        ],
        expected_duration=9,
    ),
    PatientScenario(
        name="home_visit_house_call",
        description="Home-based primary care visit including environment and safety assessment.",
        patient_profile={
            "age": 84,
            "gender": "female",
            "chief_complaint": "Frailty and recurrent falls",
            "urgency": "medium",
        },
        journey_steps=[
            _step(
                "home_visit",
                "home_visit/dispatch",
                {"home_safety_screen": True, "caregiver_present": True},
            ),
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "home", "complaint": "falls and mobility decline"},
                2,
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {
                    "task": {
                        "med_plan": ["Acetaminophen"],
                        "allergies": [],
                        "current_medications": ["Warfarin"],
                    }
                },
                1,
            ),
            _step(
                "coordinator",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "journey_type": "home_visit",
                        "coordination_tasks": [
                            "Home health referral",
                            "DME order",
                            "Falls prevention education",
                        ],
                    }
                },
                2,
            ),
        ],
        expected_duration=15,
    ),
    PatientScenario(
        name="chronic_care_management_monthly",
        description="Longitudinal CCM monthly cycle with care-plan update and coordination.",
        patient_profile={
            "age": 69,
            "gender": "male",
            "chief_complaint": "CCM monthly review for diabetes and CHF",
            "urgency": "low",
        },
        journey_steps=[
            _step(
                "ccm",
                "ccm/monthly_review",
                {"conditions": ["Diabetes", "CHF"], "monthly_minutes": 25},
            ),
            _step(
                "primary_care",
                "primary_care/manage_visit",
                {"visit_mode": "care_management", "complaint": "goal and plan review"},
                1,
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "ccm_touchpoint",
                            "when": _future(30),
                            "purpose": "next monthly review",
                        }
                    ]
                },
                1,
            ),
            _step(
                "pharmacy",
                "pharmacy/check_interactions",
                {"drugs": ["Metformin", "Lisinopril", "Aspirin"]},
                1,
            ),
        ],
        expected_duration=11,
    ),
    PatientScenario(
        name="emergency_department_treat_and_release",
        description="ED flow resulting in treatment and safe discharge.",
        patient_profile={
            "age": 29,
            "gender": "male",
            "chief_complaint": "Acute asthma exacerbation",
            "urgency": "high",
        },
        journey_steps=[
            _step(
                "triage",
                "tasks/sendSubscribe",
                {
                    "symptoms": "wheezing and dyspnea",
                    "chief_complaint": "asthma flare",
                    "arrival_time": datetime.now().isoformat(),
                },
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "wheezing and dyspnea",
                    "differential_diagnosis": ["Asthma exacerbation", "Pneumonia", "Pneumothorax"],
                },
                2,
            ),
            _step(
                "imaging",
                "tasks/sendSubscribe",
                {
                    "orders": [
                        {
                            "type": "chest_xray",
                            "priority": "urgent",
                            "indication": "rule out alternative pathology",
                        }
                    ]
                },
                2,
            ),
            _step(
                "pharmacy",
                "tasks/sendSubscribe",
                {"task": {"med_plan": ["Albuterol", "Prednisone"], "allergies": []}},
                1,
            ),
            _step(
                "discharge",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "discharge_diagnosis": "Asthma exacerbation",
                        "discharge_disposition": "home",
                    }
                },
                1,
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {"type": "primary_care", "when": _future(3), "purpose": "post-ED check"}
                    ]
                },
                1,
            ),
        ],
        expected_duration=16,
    ),
    PatientScenario(
        name="emergency_department_to_inpatient_admission",
        description="ED flow that escalates to inpatient admission.",
        patient_profile={
            "age": 57,
            "gender": "female",
            "chief_complaint": "Chest pain and diaphoresis",
            "urgency": "critical",
        },
        journey_steps=[
            _step(
                "triage",
                "tasks/sendSubscribe",
                {
                    "symptoms": "severe chest pain",
                    "chief_complaint": "possible ACS",
                    "arrival_time": datetime.now().isoformat(),
                },
            ),
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "chest pain and dyspnea",
                    "differential_diagnosis": [
                        "Acute coronary syndrome",
                        "PE",
                        "Aortic dissection",
                    ],
                },
                2,
            ),
            _step(
                "imaging",
                "tasks/sendSubscribe",
                {
                    "orders": [
                        {"type": "ecg", "priority": "emergent", "indication": "ST changes"},
                        {
                            "type": "chest_xray",
                            "priority": "urgent",
                            "indication": "alternate diagnosis",
                        },
                    ]
                },
                2,
            ),
            _step(
                "bed_manager",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "admission_type": "emergency",
                        "required_monitoring": "telemetry",
                        "estimated_los": "2-4 days",
                    }
                },
                1,
            ),
            _step(
                "coordinator",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "journey_type": "ed_to_inpatient",
                        "coordination_tasks": ["Cardiology consult", "Inpatient handoff"],
                    }
                },
                1,
            ),
        ],
        expected_duration=14,
    ),
    PatientScenario(
        name="inpatient_admission_and_daily_rounds",
        description="Inpatient episode focusing on admission, medication safety, and daily review.",
        patient_profile={
            "age": 72,
            "gender": "male",
            "chief_complaint": "Community acquired pneumonia with hypoxia",
            "urgency": "high",
        },
        journey_steps=[
            _step(
                "bed_manager",
                "admission/assign_bed",
                {"task": {"unit_pref": "Ward", "decision": "admit"}},
            ),
            _step(
                "pharmacy",
                "tasks/sendSubscribe",
                {"task": {"med_plan": ["Amoxicillin", "Oxygen"], "allergies": []}},
                1,
            ),
            _step(
                "coordinator",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "journey_type": "inpatient_stay",
                        "coordination_tasks": ["Daily rounds", "Consult sync", "Care-plan update"],
                    }
                },
                2,
            ),
            _step("ccm", "ccm/monthly_review", {"conditions": ["COPD"], "monthly_minutes": 20}, 1),
        ],
        expected_duration=12,
    ),
    PatientScenario(
        name="inpatient_discharge_transition",
        description="Discharge and transition-of-care workflow to outpatient follow-up.",
        patient_profile={
            "age": 66,
            "gender": "female",
            "chief_complaint": "Discharge readiness after CHF admission",
            "urgency": "medium",
        },
        journey_steps=[
            _step(
                "discharge",
                "tasks/sendSubscribe",
                {
                    "task": {
                        "discharge_diagnosis": "Heart failure exacerbation",
                        "discharge_disposition": "home",
                        "followup_instructions": ["Daily weights", "Low sodium diet"],
                    }
                },
            ),
            _step(
                "pharmacy",
                "pharmacy/recommend",
                {
                    "task": {
                        "med_plan": ["Lisinopril", "Aspirin"],
                        "allergies": [],
                        "current_medications": ["Ibuprofen"],
                    }
                },
                1,
            ),
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "cardiology",
                            "when": _future(7),
                            "purpose": "post-discharge visit",
                        },
                        {
                            "type": "primary_care",
                            "when": _future(14),
                            "purpose": "transition of care",
                        },
                    ]
                },
                1,
            ),
            _step("ccm", "ccm/monthly_review", {"conditions": ["CHF"], "monthly_minutes": 22}, 1),
        ],
        expected_duration=11,
    ),
]


def _load_additional_scenarios() -> list[PatientScenario]:
    """Lazily load additive variants to avoid eager circular imports."""
    try:
        from additional_scenarios import ADDITIONAL_SCENARIOS

        return list(ADDITIONAL_SCENARIOS)
    except Exception:
        try:
            from tools.additional_scenarios import ADDITIONAL_SCENARIOS

            return list(ADDITIONAL_SCENARIOS)
        except Exception:
            return []


async def run_scenario(scenario: PatientScenario) -> None:
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
        step_params = step["params"].copy()
        step_params["patient_id"] = patient_id
        step_params["visit_id"] = visit_id
        task_id = f"{visit_id}-{step['agent']}-{i}"

        await make_jsonrpc_call(
            BASE_URLS[step["agent"]],
            step["method"],
            step_params,
            task_id,
        )

        if "delay" in step:
            await asyncio.sleep(step["delay"])

    print(f"\n✅ Scenario '{scenario.name}' completed!")
    print(f"   Duration: ~{scenario.expected_duration} seconds")
    print("=" * 80)


async def run_multiple_scenarios(
    scenario_names: list[str] | None = None,
    parallel: bool = False,
) -> None:
    if scenario_names is None:
        scenarios_to_run = SCENARIOS
    else:
        combined = SCENARIOS + _load_additional_scenarios()
        scenarios_to_run = [s for s in combined if s.name in scenario_names]

    if not scenarios_to_run:
        print("❌ No matching scenarios found")
        return

    print(f"🚀 Running {len(scenarios_to_run)} scenario(s)")
    print(f"   Mode: {'Parallel' if parallel else 'Sequential'}")

    if parallel:
        await asyncio.gather(*(run_scenario(s) for s in scenarios_to_run))
        return

    for scenario in scenarios_to_run:
        await run_scenario(scenario)
        await asyncio.sleep(2)


async def list_scenarios() -> None:
    print("📋 Canonical HelixCare Patient Visit Scenarios (10):")
    print("=" * 80)
    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"{i:2d}. {scenario.name}")
        print(f"    {scenario.description}")
        print(
            "    Patient: "
            f"{scenario.patient_profile['age']}yo "
            f"{scenario.patient_profile['gender']}, "
            f"{scenario.patient_profile['chief_complaint']}"
        )
        print(f"    Steps: {len(scenario.journey_steps)}, Duration: ~{scenario.expected_duration}s")
        print()


def save_scenarios_to_file() -> None:
    scenarios_data: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        scenarios_data.append(
            {
                "name": scenario.name,
                "description": scenario.description,
                "patient_profile": scenario.patient_profile,
                "journey_steps": scenario.journey_steps,
                "expected_duration": scenario.expected_duration,
            }
        )

    with open("tools/helixcare_scenarios.json", "w", encoding="utf-8") as f:
        json.dump(scenarios_data, f, indent=2, default=str)

    print("💾 Scenarios saved to tools/helixcare_scenarios.json")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="HelixCare Patient Visit Scenarios",
    )
    parser.add_argument("--list", action="store_true", help="List all scenarios")
    parser.add_argument("--run", nargs="*", help="Run specific scenario(s)")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--parallel", action="store_true", help="Run in parallel")
    parser.add_argument("--save", action="store_true", help="Save scenarios to JSON")

    args = parser.parse_args()

    if args.save:
        save_scenarios_to_file()
        return
    if args.list:
        await list_scenarios()
        return

    scenarios_to_run: list[str] = []
    if args.run:
        scenarios_to_run = args.run
    elif args.all:
        scenarios_to_run = [s.name for s in SCENARIOS]

    if scenarios_to_run:
        await run_multiple_scenarios(scenarios_to_run, args.parallel)
        return

    print("Use --list to see available scenarios")
    print("Use --run <name> to run specific scenarios")
    print("Use --all to run all scenarios")
    print("Use --save to save scenarios to file")


if __name__ == "__main__":
    asyncio.run(main())

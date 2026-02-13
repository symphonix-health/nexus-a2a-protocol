#!/usr/bin/env python3
"""Additive HelixCare scenario variants.

These scenarios are intentionally additive to the canonical patient-visit 10.
They preserve the previous realistic, condition-driven pathways.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

try:
    from helixcare_scenarios import PatientScenario, run_scenario
except Exception:
    from tools.helixcare_scenarios import PatientScenario, run_scenario


def _future(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()


ADDITIONAL_SCENARIOS: list[PatientScenario] = [
    PatientScenario(
        name="chest_pain_cardiac",
        description="Adult with severe chest pain and suspected acute coronary syndrome.",
        patient_profile={
            "age": 55,
            "gender": "male",
            "chief_complaint": "Severe chest pain with dyspnea",
            "urgency": "high",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "severe chest pain, nausea, shortness of breath",
                    "vital_signs": {
                        "blood_pressure": "160/95",
                        "heart_rate": 110,
                        "oxygen_saturation": 95,
                    },
                    "chief_complaint": "chest pain for 2 hours",
                },
                "delay": 2,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "severe chest pain, dyspnea",
                    "differential_diagnosis": [
                        "Acute coronary syndrome",
                        "Pulmonary embolism",
                        "Aortic dissection",
                    ],
                },
                "delay": 2,
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "ecg", "priority": "emergent", "indication": "ST changes"},
                        {
                            "type": "chest_xray",
                            "priority": "urgent",
                            "indication": "alternate thoracic causes",
                        },
                    ]
                },
                "delay": 2,
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "med_plan": ["Aspirin", "Nitroglycerin"],
                        "allergies": ["Penicillin"],
                    }
                },
                "delay": 1,
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "emergency",
                        "required_monitoring": "telemetry",
                        "estimated_los": "2-3 days",
                    }
                },
                "delay": 1,
            },
        ],
        expected_duration=18,
    ),
    PatientScenario(
        name="pediatric_fever_sepsis",
        description="Child with high fever and lethargy requiring sepsis workup.",
        patient_profile={
            "age": 3,
            "gender": "female",
            "chief_complaint": "High fever and poor feeding",
            "urgency": "high",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "high fever, lethargy, irritability",
                    "vital_signs": {
                        "blood_pressure": "85/50",
                        "heart_rate": 160,
                        "temperature": 103.5,
                    },
                    "chief_complaint": "worsening fever for 3 days",
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "high fever, lethargy",
                    "differential_diagnosis": ["Sepsis", "Pneumonia", "UTI"],
                },
                "delay": 2,
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "med_plan": ["Ceftriaxone", "Acetaminophen"],
                        "allergies": [],
                    }
                },
                "delay": 1,
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "emergency",
                        "required_monitoring": "continuous",
                        "special_requirements": ["Pediatric monitoring"],
                    }
                },
                "delay": 1,
            },
        ],
        expected_duration=14,
    ),
    PatientScenario(
        name="orthopedic_fracture",
        description="Extremity fracture workflow with imaging, pain control, and follow-up.",
        patient_profile={
            "age": 28,
            "gender": "male",
            "chief_complaint": "Left leg pain after fall",
            "urgency": "medium",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "severe leg pain, deformity",
                    "chief_complaint": "fall from ladder",
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "leg pain and inability to bear weight",
                    "differential_diagnosis": ["Tibia fracture", "Ankle fracture"],
                },
                "delay": 1,
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "xray_left_leg", "priority": "urgent", "indication": "fracture"}
                    ]
                },
                "delay": 1,
            },
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "discharge_diagnosis": "Closed tibial fracture",
                        "discharge_disposition": "home",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {
                            "type": "orthopedic_clinic",
                            "when": _future(7),
                            "purpose": "fracture follow-up",
                        }
                    ]
                },
                "delay": 1,
            },
        ],
        expected_duration=12,
    ),
    PatientScenario(
        name="geriatric_confusion",
        description="Elderly patient with acute confusion and delirium-focused pathway.",
        patient_profile={
            "age": 78,
            "gender": "female",
            "chief_complaint": "Sudden confusion and agitation",
            "urgency": "high",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "acute confusion, agitation",
                    "chief_complaint": "mental status change",
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "delirium and disorientation",
                    "differential_diagnosis": ["UTI", "Medication toxicity", "Stroke"],
                },
                "delay": 2,
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "ct_head", "priority": "urgent", "indication": "rule out stroke"}
                    ]
                },
                "delay": 1,
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {"admission_type": "emergency", "required_monitoring": "continuous"}
                },
                "delay": 1,
            },
        ],
        expected_duration=13,
    ),
    PatientScenario(
        name="obstetric_emergency",
        description="Pregnancy bleeding emergency with urgent maternal/fetal coordination.",
        patient_profile={
            "age": 32,
            "gender": "female",
            "chief_complaint": "Bleeding at 28 weeks gestation",
            "urgency": "critical",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "heavy vaginal bleeding, abdominal pain",
                    "chief_complaint": "obstetric emergency",
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "bleeding in 3rd trimester",
                    "differential_diagnosis": ["Placental abruption", "Placenta previa"],
                },
                "delay": 1,
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "obstetric_ultrasound",
                            "priority": "emergent",
                            "indication": "placental and fetal assessment",
                        }
                    ]
                },
                "delay": 1,
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "emergency",
                        "required_monitoring": "intensive",
                        "special_requirements": ["Labor and delivery", "fetal monitoring"],
                    }
                },
                "delay": 1,
            },
        ],
        expected_duration=12,
    ),
    PatientScenario(
        name="mental_health_crisis",
        description="Acute psychiatric crisis with safety and inpatient behavioral health planning.",
        patient_profile={
            "age": 35,
            "gender": "male",
            "chief_complaint": "Suicidal thoughts",
            "urgency": "critical",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "suicidal ideation, severe depression",
                    "safety_concern": "high",
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "hopelessness, insomnia",
                    "differential_diagnosis": ["Major depressive disorder", "Bipolar disorder"],
                },
                "delay": 2,
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "involuntary",
                        "required_monitoring": "continuous",
                        "special_requirements": ["Psych unit", "suicide precautions"],
                    }
                },
                "delay": 1,
            },
        ],
        expected_duration=10,
    ),
    PatientScenario(
        name="chronic_diabetes_complication",
        description="Diabetic foot complication needing multidisciplinary inpatient planning.",
        patient_profile={
            "age": 62,
            "gender": "female",
            "chief_complaint": "Foot ulcer with infection",
            "urgency": "medium",
        },
        journey_steps=[
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "foot ulcer, drainage, redness",
                    "differential_diagnosis": ["Diabetic foot infection", "Osteomyelitis"],
                },
                "delay": 2,
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "foot_xray",
                            "priority": "urgent",
                            "indication": "evaluate bone involvement",
                        }
                    ]
                },
                "delay": 1,
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "med_plan": ["Vancomycin", "Insulin glargine"],
                        "allergies": ["Penicillin"],
                    }
                },
                "delay": 1,
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {"type": "podiatry", "when": _future(7), "purpose": "wound reassessment"}
                    ]
                },
                "delay": 1,
            },
        ],
        expected_duration=12,
    ),
    PatientScenario(
        name="trauma_motor_vehicle_accident",
        description="Polytrauma workflow from high-speed MVC.",
        patient_profile={
            "age": 25,
            "gender": "male",
            "chief_complaint": "Multiple traumatic injuries",
            "urgency": "critical",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "head, chest, abdominal pain",
                    "trauma_activation": "level_1",
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "polytrauma",
                    "differential_diagnosis": ["TBI", "Hemothorax", "Splenic injury"],
                },
                "delay": 1,
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "ct_head", "priority": "emergent", "indication": "TBI"},
                        {
                            "type": "ct_chest_abdomen_pelvis",
                            "priority": "emergent",
                            "indication": "multi-system trauma",
                        },
                    ]
                },
                "delay": 2,
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {"admission_type": "trauma", "required_monitoring": "intensive_care"}
                },
                "delay": 1,
            },
        ],
        expected_duration=13,
    ),
    PatientScenario(
        name="infectious_disease_outbreak",
        description="Respiratory outbreak case requiring isolation and public health escalation.",
        patient_profile={
            "age": 45,
            "gender": "female",
            "chief_complaint": "Fever, cough, hypoxia",
            "urgency": "high",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "fever, productive cough, dyspnea",
                    "isolation_required": "airborne",
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "acute respiratory illness",
                    "differential_diagnosis": ["COVID-19", "Influenza", "Bacterial pneumonia"],
                },
                "delay": 2,
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "chest_xray",
                            "priority": "urgent",
                            "indication": "pneumonia assessment",
                        }
                    ]
                },
                "delay": 1,
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "emergency",
                        "required_monitoring": "continuous",
                        "special_requirements": ["Negative pressure room", "airborne PPE"],
                    }
                },
                "delay": 1,
            },
        ],
        expected_duration=12,
    ),
    PatientScenario(
        name="pediatric_asthma_exacerbation",
        description="Severe pediatric asthma exacerbation with acute stabilization and follow-up.",
        patient_profile={
            "age": 8,
            "gender": "male",
            "chief_complaint": "Severe wheeze and shortness of breath",
            "urgency": "high",
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "severe wheeze and dyspnea",
                    "vital_signs": {"oxygen_saturation": 85, "respiratory_rate": 45},
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "acute asthma symptoms",
                    "differential_diagnosis": ["Asthma exacerbation", "Pneumonia"],
                },
                "delay": 1,
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "med_plan": ["Albuterol", "Methylprednisolone"],
                        "allergies": [],
                    }
                },
                "delay": 1,
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {
                            "type": "pulmonology",
                            "when": _future(7),
                            "purpose": "asthma control review",
                        }
                    ]
                },
                "delay": 1,
            },
        ],
        expected_duration=11,
    ),
]


async def run_additional_scenarios() -> None:
    """Run all additive variant scenarios."""
    if not ADDITIONAL_SCENARIOS:
        print("ℹ️ No additional scenarios configured")
        return

    print(f"🚀 Running {len(ADDITIONAL_SCENARIOS)} additive variant scenarios")
    for scenario in ADDITIONAL_SCENARIOS:
        await run_scenario(scenario)


if __name__ == "__main__":
    asyncio.run(run_additional_scenarios())

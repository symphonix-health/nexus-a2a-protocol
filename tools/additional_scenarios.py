#!/usr/bin/env python3
"""
Additional HelixCare Patient Journey Scenarios

Specialized scenarios covering mental health, chronic conditions,
and complex multi-system cases.
"""

import asyncio
import json
import time
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
    import httpx

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

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(f"{url}/rpc", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return {"error": str(e)}

# Additional specialized scenarios
ADDITIONAL_SCENARIOS = [
    PatientScenario(
        name="mental_health_crisis",
        description="Adult with acute mental health crisis - suicidal ideation",
        patient_profile={
            "age": 35,
            "gender": "male",
            "chief_complaint": "Suicidal thoughts, severe depression",
            "urgency": "critical"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Suicidal ideation, hopelessness, insomnia, weight loss",
                    "vital_signs": {"blood_pressure": "120/80", "heart_rate": 88, "temperature": 98.4, "oxygen_saturation": 98, "respiratory_rate": 18},
                    "chief_complaint": "Threatening suicide, needs immediate help",
                    "arrival_time": datetime.now().isoformat(),
                    "safety_concern": "high"
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Suicidal ideation, hopelessness, insomnia, weight loss",
                    "vital_signs": {"blood_pressure": "120/80", "heart_rate": 88, "temperature": 98.4, "oxygen_saturation": 98, "respiratory_rate": 18},
                    "differential_diagnosis": ["Major Depressive Disorder", "Bipolar Disorder", "Substance-induced mood disorder"],
                    "psychiatric_history": "Previous suicide attempt 2 years ago"
                },
                "delay": 3
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Sertraline", "dose": "50mg", "route": "oral", "frequency": "daily", "indication": "Antidepressant therapy"},
                        {"drug": "Lorazepam", "dose": "0.5mg", "route": "oral", "frequency": "q8h PRN", "indication": "Anxiety reduction"}
                    ],
                    "allergies": [],
                    "renal_function": "Normal",
                    "psychotropic_history": "Previous SSRI use"
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "involuntary",
                    "required_monitoring": "continuous",
                    "estimated_los": "5-10 days",
                    "special_requirements": ["Psychiatric unit", "1:1 observation", "Suicide precautions", "No sharps"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "mental_health_crisis",
                    "current_phase": "crisis_stabilization",
                    "coordination_tasks": ["Psychiatry consult", "Social work evaluation", "Safety plan development", "Family meeting"],
                    "risk_level": "critical"
                },
                "delay": 3
            }
        ],
        expected_duration=16
    ),

    PatientScenario(
        name="chronic_diabetes_complication",
        description="Diabetic patient with foot ulcer - chronic disease complication",
        patient_profile={
            "age": 62,
            "gender": "female",
            "chief_complaint": "Diabetic foot ulcer, increasing pain",
            "urgency": "medium"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Foot ulcer with drainage, increasing pain, redness",
                    "vital_signs": {"blood_pressure": "145/85", "heart_rate": 82, "temperature": 99.2, "oxygen_saturation": 96, "respiratory_rate": 16},
                    "chief_complaint": "Diabetic foot ulcer worsening",
                    "arrival_time": datetime.now().isoformat()
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Foot ulcer with drainage, increasing pain, redness",
                    "vital_signs": {"blood_pressure": "145/85", "heart_rate": 82, "temperature": 99.2, "oxygen_saturation": 96, "respiratory_rate": 16},
                    "differential_diagnosis": ["Diabetic foot infection", "Charcot foot", "Peripheral vascular disease"],
                    "chronic_conditions": ["Type 2 Diabetes (15 years)", "Hypertension", "Diabetic retinopathy"]
                },
                "delay": 3
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "foot_xray", "priority": "urgent", "indication": "Evaluate for osteomyelitis"},
                        {"type": "doppler_ultrasound", "priority": "urgent", "indication": "Assess vascular status"}
                    ]
                },
                "delay": 4
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Vancomycin", "dose": "15mg/kg", "route": "IV", "frequency": "q8h", "indication": "Empiric antibiotic for diabetic foot infection"},
                        {"drug": "Insulin glargine", "dose": "30 units", "route": "subcutaneous", "frequency": "daily", "indication": "Diabetes management"}
                    ],
                    "allergies": ["Penicillin"],
                    "renal_function": "Moderate impairment",
                    "current_medications": ["Metformin", "Lisinopril", "Aspirin", "Atorvastatin"]
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "urgent",
                    "required_monitoring": "standard",
                    "estimated_los": "7-14 days",
                    "special_requirements": ["Wound care", "Offloading", "Diabetes management", "Nutrition consult"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "chronic_diabetes_complication",
                    "current_phase": "infection_control",
                    "coordination_tasks": ["Podiatry consult", "Wound care team", "Diabetes education", "Home health setup"],
                    "risk_level": "high"
                },
                "delay": 3
            },
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "discharge_diagnosis": "Diabetic foot ulcer with infection",
                    "discharge_disposition": "skilled_nursing_facility",
                    "followup_instructions": ["Daily wound care", "Blood glucose monitoring", "Podiatry follow-up in 1 week"]
                },
                "delay": 2
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {"type": "podiatry_clinic", "when": (datetime.now() + timedelta(days=7)).isoformat(), "purpose": "Wound reassessment"},
                        {"type": "endocrinology_clinic", "when": (datetime.now() + timedelta(days=14)).isoformat(), "purpose": "Diabetes management review"}
                    ]
                },
                "delay": 2
            }
        ],
        expected_duration=25
    ),

    PatientScenario(
        name="trauma_motor_vehicle_accident",
        description="Multiple trauma from motor vehicle accident - polytrauma",
        patient_profile={
            "age": 25,
            "gender": "male",
            "chief_complaint": "Multiple injuries from MVC",
            "urgency": "critical"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Head injury, chest pain, abdominal pain, multiple fractures",
                    "vital_signs": {"blood_pressure": "110/70", "heart_rate": 110, "temperature": 97.8, "oxygen_saturation": 94, "respiratory_rate": 24},
                    "chief_complaint": "High-speed MVC, ejected from vehicle",
                    "arrival_time": datetime.now().isoformat(),
                    "trauma_activation": "level_1"
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Head injury, chest pain, abdominal pain, multiple fractures",
                    "vital_signs": {"blood_pressure": "110/70", "heart_rate": 110, "temperature": 97.8, "oxygen_saturation": 94, "respiratory_rate": 24},
                    "differential_diagnosis": ["Traumatic brain injury", "Hemothorax", "Splenic rupture", "Pelvic fracture"],
                    "injury_mechanism": "High-speed MVC with ejection"
                },
                "delay": 2
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "ct_head", "priority": "emergent", "indication": "Traumatic brain injury evaluation"},
                        {"type": "ct_chest_abdomen_pelvis", "priority": "emergent", "indication": "Multi-system trauma evaluation"},
                        {"type": "pelvis_xray", "priority": "emergent", "indication": "Pelvic fracture assessment"}
                    ]
                },
                "delay": 3
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Fentanyl", "dose": "100mcg", "route": "IV", "frequency": "once", "indication": "Pain control"},
                        {"drug": "Rocuronium", "dose": "50mg", "route": "IV", "frequency": "once", "indication": "Rapid sequence intubation"},
                        {"drug": "Tranexamic acid", "dose": "1g", "route": "IV", "frequency": "once", "indication": "Trauma hemorrhage control"}
                    ],
                    "allergies": [],
                    "renal_function": "Normal"
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "trauma",
                    "required_monitoring": "intensive_care",
                    "estimated_los": "7-14 days",
                    "special_requirements": ["Trauma ICU", "Ventilator management", "Multiple surgical teams", "Family support"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "polytrauma_mvc",
                    "current_phase": "acute_resuscitation",
                    "coordination_tasks": ["Trauma surgery", "Neurosurgery", "Orthopedic surgery", "Rehabilitation planning"],
                    "risk_level": "critical"
                },
                "delay": 3
            }
        ],
        expected_duration=18
    ),

    PatientScenario(
        name="infectious_disease_outbreak",
        description="Patient with suspected infectious disease during outbreak",
        patient_profile={
            "age": 45,
            "gender": "female",
            "chief_complaint": "Fever, cough, respiratory distress",
            "urgency": "high"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "High fever, productive cough, shortness of breath, myalgia",
                    "vital_signs": {"blood_pressure": "125/75", "heart_rate": 105, "temperature": 102.8, "oxygen_saturation": 88, "respiratory_rate": 28},
                    "chief_complaint": "Acute respiratory illness during outbreak",
                    "arrival_time": datetime.now().isoformat(),
                    "isolation_required": "airborne"
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "High fever, productive cough, shortness of breath, myalgia",
                    "vital_signs": {"blood_pressure": "125/75", "heart_rate": 105, "temperature": 102.8, "oxygen_saturation": 88, "respiratory_rate": 28},
                    "differential_diagnosis": ["COVID-19", "Influenza", "Bacterial pneumonia", "Other respiratory viruses"],
                    "epidemiology": "Recent travel to outbreak area"
                },
                "delay": 3
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "chest_xray", "priority": "urgent", "indication": "Evaluate for pneumonia"},
                        {"type": "ct_chest", "priority": "urgent", "indication": "Detailed lung assessment"}
                    ]
                },
                "delay": 4
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Remdesivir", "dose": "200mg", "route": "IV", "frequency": "once", "indication": "Antiviral therapy"},
                        {"drug": "Dexamethasone", "dose": "6mg", "route": "IV", "frequency": "daily", "indication": "Anti-inflammatory therapy"},
                        {"drug": "Enoxaparin", "dose": "40mg", "route": "subcutaneous", "frequency": "daily", "indication": "DVT prophylaxis"}
                    ],
                    "allergies": [],
                    "renal_function": "Normal"
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "emergency",
                    "required_monitoring": "continuous",
                    "estimated_los": "5-10 days",
                    "special_requirements": ["Negative pressure room", "Airborne isolation", "PPE for all staff", "Infection control protocols"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "infectious_disease_outbreak",
                    "current_phase": "isolation_management",
                    "coordination_tasks": ["Infectious disease consult", "Public health notification", "Contact tracing", "Resource allocation"],
                    "risk_level": "high"
                },
                "delay": 3
            }
        ],
        expected_duration=20
    ),

    PatientScenario(
        name="pediatric_asthma_exacerbation",
        description="Child with severe asthma exacerbation",
        patient_profile={
            "age": 8,
            "gender": "male",
            "chief_complaint": "Severe shortness of breath, wheezing",
            "urgency": "high"
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Severe wheezing, shortness of breath, chest tightness, coughing",
                    "vital_signs": {"blood_pressure": "110/70", "heart_rate": 140, "temperature": 98.6, "oxygen_saturation": 85, "respiratory_rate": 45},
                    "chief_complaint": "Asthma attack not responding to home treatment",
                    "arrival_time": datetime.now().isoformat()
                },
                "delay": 1
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Severe wheezing, shortness of breath, chest tightness, coughing",
                    "vital_signs": {"blood_pressure": "110/70", "heart_rate": 140, "temperature": 98.6, "oxygen_saturation": 85, "respiratory_rate": 45},
                    "differential_diagnosis": ["Acute asthma exacerbation", "Bronchiolitis", "Foreign body aspiration", "Pneumonia"],
                    "asthma_history": "Moderate persistent asthma, multiple prior ED visits"
                },
                "delay": 2
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "chest_xray", "priority": "urgent", "indication": "Rule out pneumothorax, pneumonia"}
                    ]
                },
                "delay": 3
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "medication_orders": [
                        {"drug": "Albuterol", "dose": "2.5mg", "route": "nebulized", "frequency": "q20min x 3", "indication": "Bronchodilation"},
                        {"drug": "Ipratropium", "dose": "250mcg", "route": "nebulized", "frequency": "q20min x 3", "indication": "Bronchodilation"},
                        {"drug": "Methylprednisolone", "dose": "2mg/kg", "route": "IV", "frequency": "once", "indication": "Anti-inflammatory therapy"}
                    ],
                    "allergies": [],
                    "renal_function": "Normal",
                    "weight_kg": 28,
                    "asthma_medications": ["Fluticasone", "Albuterol PRN"]
                },
                "delay": 2
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "admission_type": "emergency",
                    "required_monitoring": "continuous",
                    "estimated_los": "1-3 days",
                    "special_requirements": ["Pediatric unit", "Continuous pulse oximetry", "Asthma education", "Peak flow monitoring"]
                },
                "delay": 2
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "journey_type": "pediatric_asthma",
                    "current_phase": "acute_management",
                    "coordination_tasks": ["Pulmonology consult", "Asthma education", "Home nebulizer setup", "School action plan"],
                    "risk_level": "high"
                },
                "delay": 3
            },
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "discharge_diagnosis": "Acute asthma exacerbation",
                    "discharge_disposition": "home",
                    "followup_instructions": ["Continue albuterol as prescribed", "Complete steroid course", "Follow up with pulmonology in 1 week"]
                },
                "delay": 2
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {"type": "pulmonology_clinic", "when": (datetime.now() + timedelta(days=7)).isoformat(), "purpose": "Asthma control assessment"},
                        {"type": "primary_care", "when": (datetime.now() + timedelta(days=14)).isoformat(), "purpose": "Routine follow-up"}
                    ]
                },
                "delay": 2
            }
        ],
        expected_duration=22
    )
]

async def run_additional_scenarios():
    """Run all additional scenarios."""
    print("🚀 Running Additional HelixCare Scenarios")
    print("=" * 50)

    for scenario in ADDITIONAL_SCENARIOS:
        patient_id = f"PAT-{int(time.time())}-{scenario.name}"
        visit_id = f"VISIT-{int(time.time())}-{scenario.name}"

        print(f"\n🏥 Scenario: {scenario.name}")
        print(f"   {scenario.description}")
        print(f"   Patient: {scenario.patient_profile}")

        for i, step in enumerate(scenario.journey_steps, 1):
            print(f"   Step {i}: {step['agent']}")

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

        print(f"   ✅ Completed (~{scenario.expected_duration}s)")

    print("\n🎉 All additional scenarios completed!")

if __name__ == "__main__":
    asyncio.run(run_additional_scenarios())
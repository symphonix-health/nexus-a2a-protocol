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
        medical_history={
            "past_medical_history": ["Hypertension", "Hyperlipidemia", "GERD"],
            "medications": [
                "Amlodipine 10 mg daily",
                "Rosuvastatin 20 mg nightly",
                "Omeprazole 20 mg daily",
            ],
            "allergies": ["Penicillin (hives)"],
            "social_history": {
                "tobacco": "current smoker (1 pack/day)",
                "alcohol": "weekend use",
                "substances": "denies illicit drug use",
            },
            "family_history": ["Mother with coronary artery disease"],
            "review_of_systems": {
                "cardiac": "Crushing substernal chest pain with nausea and diaphoresis",
                "respiratory": "Shortness of breath without productive cough",
            },
            "vital_signs": {
                "blood_pressure": "160/95",
                "heart_rate": 110,
                "respiratory_rate": 24,
                "oxygen_saturation": 95,
                "temperature_c": 36.9,
            },
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
        medical_history={
            "past_medical_history": ["Full-term birth", "Recurrent otitis media"],
            "medications": ["None"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "household": "lives with parents and older sibling",
                "daycare": "attends daycare 5 days/week",
                "immunizations": "up to date per schedule",
            },
            "family_history": ["No significant family history"],
            "review_of_systems": {
                "constitutional": "High fever x3 days, decreased oral intake, listless",
                "gastrointestinal": "No vomiting, mild diarrhea",
            },
            "vital_signs": {
                "blood_pressure": "85/50",
                "heart_rate": 160,
                "respiratory_rate": 36,
                "oxygen_saturation": 96,
                "temperature_c": 39.7,
            },
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
        medical_history={
            "past_medical_history": ["No chronic illness"],
            "medications": ["None"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "social",
                "occupation": "Carpenter",
                "mechanism": "fell from 3-metre ladder onto concrete",
            },
            "family_history": ["No significant family history"],
            "review_of_systems": {
                "musculoskeletal": "Left lower leg deformity, unable to bear weight",
                "neurologic": "Sensation intact distally, capillary refill < 2 s",
            },
            "vital_signs": {
                "blood_pressure": "138/82",
                "heart_rate": 98,
                "respiratory_rate": 18,
                "oxygen_saturation": 99,
                "temperature_c": 36.8,
            },
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
        medical_history={
            "past_medical_history": ["Alzheimer disease (mild)", "Hypertension", "Osteoporosis", "Recurrent UTI"],
            "medications": [
                "Donepezil 10 mg daily",
                "Amlodipine 5 mg daily",
                "Calcium-vitamin D supplement",
            ],
            "allergies": ["Sulfonamides (rash)"],
            "social_history": {
                "living_situation": "assisted-living facility",
                "tobacco": "never",
                "alcohol": "none",
                "baseline_cognition": "oriented x2 at baseline",
            },
            "family_history": ["Sister with Alzheimer disease"],
            "review_of_systems": {
                "neurologic": "Acute disorientation, agitation, incoherent speech",
                "genitourinary": "New-onset urinary incontinence, cloudy urine",
            },
            "vital_signs": {
                "blood_pressure": "158/90",
                "heart_rate": 94,
                "respiratory_rate": 20,
                "oxygen_saturation": 96,
                "temperature_c": 38.2,
            },
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
        medical_history={
            "past_medical_history": ["Gestational diabetes (current pregnancy)", "Previous C-section (2019)"],
            "medications": ["Prenatal vitamins", "Insulin aspart per sliding scale"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "none during pregnancy",
                "parity": "G3P1011",
                "gestational_age": "28 weeks 3 days",
            },
            "family_history": ["Mother with gestational diabetes"],
            "review_of_systems": {
                "obstetric": "Sudden onset painless bright-red vaginal bleeding",
                "cardiovascular": "Mild lightheadedness, no syncope",
            },
            "vital_signs": {
                "blood_pressure": "100/62",
                "heart_rate": 118,
                "respiratory_rate": 22,
                "oxygen_saturation": 97,
                "temperature_c": 36.9,
            },
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
        medical_history={
            "past_medical_history": ["Major depressive disorder", "Generalized anxiety disorder", "Previous suicide attempt (2021)"],
            "medications": [
                "Sertraline 150 mg daily",
                "Lorazepam 0.5 mg PRN",
            ],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "occasional",
                "alcohol": "increased recently (4-5 drinks/day)",
                "substances": "denies",
                "living_situation": "lives alone, recently separated",
                "employment": "unemployed for 3 months",
            },
            "family_history": ["Brother with bipolar disorder", "Father completed suicide"],
            "review_of_systems": {
                "psychiatric": "Hopelessness, insomnia, anhedonia, active suicidal ideation with plan",
                "constitutional": "Weight loss 5 kg over 4 weeks, poor self-care",
            },
            "vital_signs": {
                "blood_pressure": "128/80",
                "heart_rate": 88,
                "respiratory_rate": 16,
                "oxygen_saturation": 99,
                "temperature_c": 36.6,
            },
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
        medical_history={
            "past_medical_history": [
                "Type 2 diabetes (15 years)",
                "Diabetic peripheral neuropathy",
                "Hypertension",
                "Chronic kidney disease stage 3a",
            ],
            "medications": [
                "Insulin glargine 30 units nightly",
                "Metformin 1000 mg BID",
                "Lisinopril 20 mg daily",
            ],
            "allergies": ["Penicillin (anaphylaxis)"],
            "social_history": {
                "tobacco": "former smoker (10 pack-years)",
                "alcohol": "none",
                "occupation": "Retired teacher",
                "mobility": "uses walker, limited sensation in feet",
            },
            "family_history": ["Mother with type 2 diabetes", "Father with peripheral artery disease"],
            "review_of_systems": {
                "integumentary": "Right plantar ulcer with purulent drainage, surrounding erythema",
                "musculoskeletal": "Right foot pain on weight-bearing",
            },
            "vital_signs": {
                "blood_pressure": "148/86",
                "heart_rate": 88,
                "respiratory_rate": 18,
                "oxygen_saturation": 97,
                "temperature_c": 38.1,
            },
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
        medical_history={
            "past_medical_history": ["No chronic illness"],
            "medications": ["None"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "social",
                "occupation": "University student",
                "mechanism": "unrestrained driver, head-on collision at ~80 km/h",
            },
            "family_history": ["No significant family history"],
            "review_of_systems": {
                "neurologic": "GCS 12 (E3 V4 M5), no lateralizing signs",
                "cardiovascular": "Tachycardic, weak peripheral pulses",
                "abdominal": "Diffuse tenderness, guarding LUQ",
            },
            "vital_signs": {
                "blood_pressure": "88/56",
                "heart_rate": 128,
                "respiratory_rate": 26,
                "oxygen_saturation": 92,
                "temperature_c": 36.2,
            },
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
        medical_history={
            "past_medical_history": ["Type 2 diabetes", "Obesity"],
            "medications": ["Metformin 1000 mg BID"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "occupation": "School administrator",
                "exposure": "recent close contact with multiple symptomatic coworkers",
                "vaccination_status": "influenza overdue",
            },
            "family_history": ["Father with COPD"],
            "review_of_systems": {
                "respiratory": "Productive cough, dyspnea, pleuritic discomfort",
                "constitutional": "Fever, fatigue, myalgias",
            },
            "vital_signs": {
                "blood_pressure": "132/78",
                "heart_rate": 112,
                "respiratory_rate": 30,
                "oxygen_saturation": 89,
                "temperature_c": 39.1,
            },
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
        medical_history={
            "past_medical_history": ["Asthma", "Atopic dermatitis"],
            "medications": ["Albuterol inhaler PRN", "Fluticasone inhaler daily"],
            "allergies": ["Peanut allergy", "Dust mite allergy"],
            "social_history": {
                "household": "lives with parents",
                "triggers": ["viral URI", "exercise", "seasonal pollen"],
                "secondhand_smoke": "none",
            },
            "family_history": ["Mother with asthma"],
            "review_of_systems": {
                "respiratory": "Severe wheeze, chest tightness, accessory muscle use",
                "constitutional": "No persistent high fever",
            },
            "vital_signs": {
                "blood_pressure": "102/64",
                "heart_rate": 138,
                "respiratory_rate": 45,
                "oxygen_saturation": 85,
                "temperature_c": 37.3,
            },
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
    PatientScenario(
        name="regional_hie_referral_exchange",
        description="ED-to-regional referral with OpenHIE mediation and coordinator handoff.",
        patient_profile={
            "age": 52,
            "gender": "male",
            "chief_complaint": "TIA symptoms requiring cross-network referral",
            "urgency": "high",
        },
        medical_history={
            "past_medical_history": ["Atrial fibrillation", "Hypertension", "Hyperlipidemia"],
            "medications": [
                "Apixaban 5 mg BID",
                "Metoprolol 50 mg BID",
                "Atorvastatin 40 mg nightly",
            ],
            "allergies": ["Iodine contrast (mild hives)"],
            "social_history": {
                "tobacco": "former smoker (20 pack-years, quit 5 yrs ago)",
                "alcohol": "occasional",
                "occupation": "Long-haul truck driver",
            },
            "family_history": ["Mother with stroke at age 68"],
            "review_of_systems": {
                "neurologic": "Right-sided weakness and speech difficulty (resolved after 45 min)",
                "cardiovascular": "Irregular heart rhythm at baseline",
            },
            "vital_signs": {
                "blood_pressure": "162/96",
                "heart_rate": 92,
                "respiratory_rate": 18,
                "oxygen_saturation": 98,
                "temperature_c": 36.7,
            },
        },
        journey_steps=[
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "transient unilateral weakness, slurred speech",
                    "chief_complaint": "possible TIA",
                },
                "delay": 1,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "neurologic deficit resolved",
                    "differential_diagnosis": ["TIA", "Stroke mimic", "Migraine aura"],
                },
                "delay": 1,
            },
            {
                "agent": "openhie_mediator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "exchange_type": "cross_org_referral",
                        "payload": "neurology referral summary",
                        "destination": "regional_neuro_centre",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "journey_type": "regional_referral",
                        "coordination_tasks": [
                            "Referral transport",
                            "Records reconciliation",
                            "Receiving team handoff",
                        ],
                    }
                },
                "delay": 1,
            },
        ],
        expected_duration=12,
    ),
    PatientScenario(
        name="telemed_scribe_documentation_chain",
        description="Telemedicine encounter routed through transcriber, summariser, and EHR writer agents.",
        patient_profile={
            "age": 41,
            "gender": "female",
            "chief_complaint": "Persistent sinus pain after URI",
            "urgency": "medium",
        },
        medical_history={
            "past_medical_history": ["Allergic rhinitis", "Migraine"],
            "medications": ["Cetirizine 10 mg daily", "Sumatriptan 50 mg PRN"],
            "allergies": ["Amoxicillin (GI upset)"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "occasional",
                "occupation": "Remote software developer",
            },
            "family_history": ["Mother with chronic sinusitis"],
            "review_of_systems": {
                "ent": "Bilateral facial pressure, purulent nasal discharge x10 days",
                "neurologic": "Frontal headache worse when leaning forward",
            },
            "vital_signs": {
                "blood_pressure": "122/76",
                "heart_rate": 78,
                "respiratory_rate": 16,
                "oxygen_saturation": 99,
                "temperature_c": 37.4,
            },
        },
        journey_steps=[
            {
                "agent": "telehealth",
                "method": "telehealth/consult",
                "params": {
                    "modality": "video",
                    "location_verified": True,
                    "consent_documented": True,
                },
                "delay": 1,
            },
            {
                "agent": "transcriber",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "media_type": "audio",
                        "source": "telemed_consult_stream",
                        "expected_output": "verbatim_transcript",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "summariser",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "input": "transcript",
                        "style": "SOAP",
                        "focus": ["assessment", "plan", "follow_up"],
                    }
                },
                "delay": 1,
            },
            {
                "agent": "ehr_writer",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "document_type": "encounter_note",
                        "target_system": "EHR",
                        "validation": "coding_and_completeness",
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
                            "type": "primary_care",
                            "when": _future(10),
                            "purpose": "sinus symptom re-evaluation",
                        }
                    ]
                },
                "delay": 1,
            },
        ],
        expected_duration=13,
    ),
    PatientScenario(
        name="consent_and_payer_authorization",
        description="Consent verification and payer pre-authorization with HITL adjudication.",
        patient_profile={
            "age": 58,
            "gender": "female",
            "chief_complaint": "MRI authorization for persistent radiculopathy",
            "urgency": "medium",
        },
        medical_history={
            "past_medical_history": ["Lumbar disc herniation L4-L5", "Hypertension", "Fibromyalgia"],
            "medications": [
                "Gabapentin 300 mg TID",
                "Naproxen 500 mg BID",
                "Losartan 50 mg daily",
            ],
            "allergies": ["Codeine (nausea)"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "rare",
                "occupation": "Librarian (limited lifting tolerance)",
            },
            "family_history": ["Father with degenerative disc disease"],
            "review_of_systems": {
                "musculoskeletal": "Left-sided radicular pain L4 dermatomal distribution",
                "neurologic": "Diminished ankle reflex left, positive SLR left",
            },
            "vital_signs": {
                "blood_pressure": "136/82",
                "heart_rate": 74,
                "respiratory_rate": 16,
                "oxygen_saturation": 99,
                "temperature_c": 36.6,
            },
        },
        journey_steps=[
            {
                "agent": "provider_agent",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "request_type": "prior_auth",
                        "service": "lumbar_spine_mri",
                        "clinical_justification": "failed conservative therapy",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "insurer_agent",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "policy_check": "benefit_and_medical_necessity",
                        "member_tier": "commercial",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "consent_analyser",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "consent_scope": "diagnostic_imaging_and_data_sharing",
                        "jurisdiction": "state_and_federal",
                        "hipaa_minimum_necessary": True,
                    }
                },
                "delay": 1,
            },
            {
                "agent": "hitl_ui",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "review_reason": "coverage_policy_exception",
                        "required_actions": ["document rationale", "approve_or_deny"],
                    }
                },
                "delay": 1,
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "mri_lumbar_spine",
                            "priority": "routine",
                            "indication": "lumbar radiculopathy",
                        }
                    ]
                },
                "delay": 1,
            },
        ],
        expected_duration=14,
    ),
    PatientScenario(
        name="notifiable_outbreak_public_health_loop",
        description="Hospital case escalated to public health surveillance with OSINT corroboration.",
        patient_profile={
            "age": 46,
            "gender": "male",
            "chief_complaint": "Severe febrile respiratory illness with cluster exposure",
            "urgency": "high",
        },
        medical_history={
            "past_medical_history": ["Chronic obstructive pulmonary disease", "Former TB (treated 2015)"],
            "medications": ["Tiotropium inhaler daily", "Salbutamol inhaler PRN"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "former smoker (25 pack-years, quit 3 yrs ago)",
                "alcohol": "occasional",
                "occupation": "Meat-processing plant worker",
                "exposure": "co-workers with similar symptoms over 2 weeks",
            },
            "family_history": ["No significant family history"],
            "review_of_systems": {
                "respiratory": "Productive cough, dyspnea at rest, pleuritic chest pain",
                "constitutional": "Fever, rigors, night sweats, 3 kg weight loss",
            },
            "vital_signs": {
                "blood_pressure": "124/78",
                "heart_rate": 106,
                "respiratory_rate": 28,
                "oxygen_saturation": 90,
                "temperature_c": 39.4,
            },
        },
        journey_steps=[
            {
                "agent": "hospital_reporter",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "report_type": "notifiable_condition",
                        "facility_signal": "respiratory_cluster",
                        "severity": "high",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "osint_agent",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "query": "regional respiratory outbreak mentions",
                        "time_window_hours": 72,
                    }
                },
                "delay": 1,
            },
            {
                "agent": "central_surveillance",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "fusion_inputs": ["hospital_report", "osint_signal"],
                        "action": "risk_scoring_and_alerting",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "isolation",
                        "required_monitoring": "continuous",
                        "special_requirements": ["negative_pressure_room"],
                    }
                },
                "delay": 1,
            },
        ],
        expected_duration=11,
    ),
    # ── Clinician Avatar Interview Scenario ──────────────────────────────
    PatientScenario(
        name="clinician_avatar_consultation",
        description="Clinician avatar conducts a Calgary-Cambridge structured interview with a chest-pain patient.",
        patient_profile={
            "age": 54,
            "gender": "male",
            "chief_complaint": "Intermittent chest tightness with exertion",
            "urgency": "high",
        },
        medical_history={
            "past_medical_history": [
                "Hypertension",
                "Hyperlipidemia",
                "Prediabetes",
            ],
            "medications": [
                "Amlodipine 10 mg daily",
                "Rosuvastatin 10 mg nightly",
            ],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "former smoker (10 pack-years, quit 2 yrs ago)",
                "alcohol": "1-2 beers on weekends",
                "occupation": "Construction foreman",
                "exercise": "reduced due to chest symptoms",
            },
            "family_history": ["Father with MI at age 58", "Mother with type 2 diabetes"],
            "review_of_systems": {
                "cardiac": "Substernal tightness on exertion, relieved by rest within 5 min",
                "respiratory": "No cough or dyspnea at rest",
                "constitutional": "No fever, no weight loss",
            },
            "vital_signs": {
                "blood_pressure": "148/90",
                "heart_rate": 82,
                "respiratory_rate": 18,
                "oxygen_saturation": 97,
                "temperature_c": 36.7,
            },
        },
        journey_steps=[
            # 1 — Triage to establish context and urgency
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "intermittent exertional chest tightness",
                    "vital_signs": {
                        "blood_pressure": "148/90",
                        "heart_rate": 82,
                        "oxygen_saturation": 97,
                    },
                    "chief_complaint": "chest tightness with exertion over 3 weeks",
                },
                "delay": 2,
            },
            # 2 — Avatar starts a structured clinical interview
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": "Intermittent chest tightness with exertion",
                        "age": 54,
                        "gender": "male",
                        "urgency": "high",
                    },
                    "persona": "senior_cardiologist",
                },
                "delay": 2,
            },
            # 3 — Patient describes symptom onset (avatar progresses interview)
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "{{avatar_session_id}}",
                    "message": "It started about three weeks ago. I get this tight feeling across my chest when I'm climbing stairs or lifting heavy things at work. It goes away when I sit down for a few minutes.",
                },
                "delay": 2,
            },
            # 4 — Patient answers follow-up about radiation and associations
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "{{avatar_session_id}}",
                    "message": "Sometimes it goes into my left arm and jaw. I also feel a bit nauseous when it happens. No sweating though.",
                },
                "delay": 2,
            },
            # 5 — Diagnosis agent processes gathered findings
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "exertional chest tightness with left arm and jaw radiation, nausea",
                    "differential_diagnosis": [
                        "Stable angina",
                        "Unstable angina",
                        "GERD",
                        "Musculoskeletal chest pain",
                    ],
                },
                "delay": 2,
            },
            # 6 — Imaging workup
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {"type": "ecg", "priority": "urgent", "indication": "exertional chest pain"},
                        {
                            "type": "stress_echo",
                            "priority": "routine",
                            "indication": "ischemia workup",
                        },
                    ]
                },
                "delay": 2,
            },
            # 7 — Pharmacy
            {
                "agent": "pharmacy",
                "method": "pharmacy/recommend",
                "params": {
                    "task": {
                        "med_plan": ["Aspirin 81 mg", "Nitroglycerin SL PRN"],
                        "allergies": [],
                        "current_medications": ["Amlodipine", "Rosuvastatin"],
                    }
                },
                "delay": 1,
            },
            # 8 — Follow-up scheduling
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {
                            "type": "cardiology",
                            "when": _future(7),
                            "purpose": "stress echo results review and risk stratification",
                        }
                    ]
                },
                "delay": 1,
            },
        ],
        expected_duration=18,
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

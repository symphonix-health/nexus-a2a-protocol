#!/usr/bin/env python3
"""Additive HelixCare scenario variants.

These scenarios are intentionally additive to the canonical patient-visit 10.
They preserve the previous realistic, condition-driven pathways.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

try:
    from helixcare_scenarios import PatientScenario, enrich_scenario_handoff_contracts, run_scenario
except Exception:
    from tools.helixcare_scenarios import (
        PatientScenario,
        enrich_scenario_handoff_contracts,
        run_scenario,
    )


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
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": "Severe chest pain with dyspnea",
                        "age": 55,
                        "gender": "male",
                        "urgency": "high",
                    },
                    "persona": "senior_cardiologist",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": "Cardiologist assessment after ED triage for suspected ACS",
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "The pain hit me like a truck about two hours ago. Crushing feeling right here in my chest with nausea. I smoke a pack a day and my mom had heart problems.",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Patient describes classic ACS presentation with risk factors",
                },
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
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Diagnosis follows cardiologist clinical interview",
                },
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
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "Emergent imaging for suspected ACS",
                },
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
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "ACS protocol medications based on diagnosis",
                },
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
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["imaging"],
                    "clinical_rationale": "Telemetry bed admission after cardiac workup",
                },
            },
        ],
        expected_duration=22,
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
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": "High fever and poor feeding",
                        "age": 3,
                        "gender": "female",
                        "urgency": "high",
                    },
                    "persona": "pediatrician",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": ("Pediatrician evaluates febrile child after triage"),
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": ("$ctx.agent_outputs.clinician_avatar.session_id"),
                    "message": (
                        "She has had a fever for three days and won't"
                        " eat. She's been very floppy and irritable."
                        " She goes to daycare and other kids were sick."
                    ),
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": (
                        "Parent describes illness trajectory and exposure history"
                    ),
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "high fever, lethargy",
                    "differential_diagnosis": ["Sepsis", "Pneumonia", "UTI"],
                },
                "delay": 2,
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Diagnosis after pediatric clinical interview"),
                },
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
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": ("Empiric antibiotics after sepsis workup"),
                },
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
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["pharmacy"],
                    "clinical_rationale": ("Pediatric admission for monitoring"),
                },
            },
        ],
        expected_duration=18,
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
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": "Left leg pain after fall",
                        "age": 28,
                        "gender": "male",
                        "urgency": "medium",
                    },
                    "persona": "orthopedic_surgeon",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": ("Orthopedist assesses mechanism and deformity"),
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": ("$ctx.agent_outputs.clinician_avatar.session_id"),
                    "message": (
                        "I fell from a three-metre ladder at work"
                        " and landed on my left leg. I heard a"
                        " crack and I can't put any weight on it."
                    ),
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Patient describes mechanism and weight-bearing status"),
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "leg pain and inability to bear weight",
                    "differential_diagnosis": [
                        "Tibia fracture",
                        "Ankle fracture",
                    ],
                },
                "delay": 1,
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Diagnosis after orthopedic examination"),
                },
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "xray_left_leg",
                            "priority": "urgent",
                            "indication": "fracture",
                        }
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": ("X-ray to confirm fracture pattern"),
                },
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
                "handoff_policy": {
                    "required_predecessors": ["imaging"],
                    "clinical_rationale": (
                        "Discharge after imaging confirms non-operative fracture"
                    ),
                },
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
                "handoff_policy": {
                    "required_predecessors": ["discharge"],
                    "clinical_rationale": ("Orthopedic follow-up after discharge"),
                },
            },
        ],
        expected_duration=16,
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
            "past_medical_history": [
                "Alzheimer disease (mild)",
                "Hypertension",
                "Osteoporosis",
                "Recurrent UTI",
            ],
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
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": "Acute confusion",
                        "age": 78,
                        "gender": "female",
                        "urgency": "high",
                    },
                    "persona": "geriatrician",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": ("Geriatrician evaluates delirium after triage"),
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": ("$ctx.agent_outputs.clinician_avatar.session_id"),
                    "message": (
                        "She has been very confused since"
                        " yesterday. She keeps calling for her"
                        " late husband and doesn't recognise the"
                        " staff. She also seems to have a new"
                        " urine smell."
                    ),
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Caregiver describes baseline change and new symptoms"),
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "delirium and disorientation",
                    "differential_diagnosis": [
                        "UTI",
                        "Medication toxicity",
                        "Stroke",
                    ],
                },
                "delay": 2,
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Diagnosis after geriatrician interview"),
                },
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "ct_head",
                            "priority": "urgent",
                            "indication": "rule out stroke",
                        }
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": ("CT head to exclude acute stroke"),
                },
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "emergency",
                        "required_monitoring": "continuous",
                    }
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["imaging"],
                    "clinical_rationale": ("Admission for monitoring and delirium workup"),
                },
            },
        ],
        expected_duration=17,
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
            "past_medical_history": [
                "Gestational diabetes (current pregnancy)",
                "Previous C-section (2019)",
            ],
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
                    "symptoms": ("heavy vaginal bleeding, abdominal pain"),
                    "chief_complaint": "obstetric emergency",
                },
                "delay": 1,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": ("Vaginal bleeding at 28 weeks"),
                        "age": 32,
                        "gender": "female",
                        "urgency": "critical",
                    },
                    "persona": "obstetrician",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": (
                        "Obstetrician urgent assessment of antepartum hemorrhage"
                    ),
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": ("$ctx.agent_outputs.clinician_avatar.session_id"),
                    "message": (
                        "The bleeding started suddenly about"
                        " an hour ago with no pain. I soaked"
                        " through two pads. I had a C-section"
                        " with my first and this pregnancy has"
                        " been complicated by diabetes."
                    ),
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": (
                        "Patient describes onset, volume, and obstetric history"
                    ),
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "bleeding in 3rd trimester",
                    "differential_diagnosis": [
                        "Placental abruption",
                        "Placenta previa",
                    ],
                },
                "delay": 1,
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Diagnosis after obstetrician clinical assessment"),
                },
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "obstetric_ultrasound",
                            "priority": "emergent",
                            "indication": ("placental and fetal assessment"),
                        }
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": ("Emergent ultrasound for placental localisation"),
                },
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "emergency",
                        "required_monitoring": "intensive",
                        "special_requirements": [
                            "Labor and delivery",
                            "fetal monitoring",
                        ],
                    }
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["imaging"],
                    "clinical_rationale": ("L&D admission with continuous fetal monitoring"),
                },
            },
        ],
        expected_duration=16,
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
            "past_medical_history": [
                "Major depressive disorder",
                "Generalized anxiety disorder",
                "Previous suicide attempt (2021)",
            ],
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
                    "symptoms": ("suicidal ideation, severe depression"),
                    "safety_concern": "high",
                },
                "delay": 1,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": "Suicidal ideation",
                        "age": 35,
                        "gender": "male",
                        "urgency": "critical",
                    },
                    "persona": "psychiatrist",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": ("Psychiatrist safety assessment after triage"),
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": ("$ctx.agent_outputs.clinician_avatar.session_id"),
                    "message": (
                        "I can't do this any more. My wife"
                        " left three months ago, I lost my"
                        " job, and I've been drinking more."
                        " I have a plan but I came here"
                        " because I promised my brother."
                    ),
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Patient discloses risk factors and safety plan"),
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "hopelessness, insomnia",
                    "differential_diagnosis": [
                        "Major depressive disorder",
                        "Bipolar disorder",
                    ],
                },
                "delay": 2,
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Diagnosis after psychiatrist risk assessment"),
                },
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "involuntary",
                        "required_monitoring": "continuous",
                        "special_requirements": [
                            "Psych unit",
                            "suicide precautions",
                        ],
                    }
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": ("Involuntary admission with continuous observation"),
                },
            },
        ],
        expected_duration=15,
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
            "family_history": [
                "Mother with type 2 diabetes",
                "Father with peripheral artery disease",
            ],
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
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": ("Infected diabetic foot ulcer"),
                        "age": 62,
                        "gender": "female",
                        "urgency": "medium",
                    },
                    "persona": "endocrinologist",
                },
                "delay": 2,
                "handoff_policy": {
                    "clinical_rationale": ("Endocrinologist assesses diabetic foot complication"),
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": ("$ctx.agent_outputs.clinician_avatar.session_id"),
                    "message": (
                        "I noticed the sore on the bottom of"
                        " my right foot about two weeks ago."
                        " It started oozing yesterday and my"
                        " foot is swollen and red. I can barely"
                        " feel my feet because of the neuropathy."
                    ),
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Patient describes ulcer timeline and neuropathy"),
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": ("foot ulcer, drainage, redness"),
                    "differential_diagnosis": [
                        "Diabetic foot infection",
                        "Osteomyelitis",
                    ],
                },
                "delay": 2,
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Diagnosis after endocrinologist clinical review"),
                },
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "foot_xray",
                            "priority": "urgent",
                            "indication": ("evaluate bone involvement"),
                        }
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": ("X-ray to rule out osteomyelitis"),
                },
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "med_plan": [
                            "Vancomycin",
                            "Insulin glargine",
                        ],
                        "allergies": ["Penicillin"],
                    }
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["imaging"],
                    "clinical_rationale": ("IV antibiotics avoiding penicillin allergy"),
                },
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {
                            "type": "podiatry",
                            "when": _future(7),
                            "purpose": "wound reassessment",
                        }
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["pharmacy"],
                    "clinical_rationale": ("Podiatry follow-up for wound reassessment"),
                },
            },
        ],
        expected_duration=17,
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
                    "symptoms": ("head, chest, abdominal pain"),
                    "trauma_activation": "level_1",
                },
                "delay": 1,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": ("Polytrauma from high-speed MVC"),
                        "age": 25,
                        "gender": "male",
                        "urgency": "critical",
                    },
                    "persona": "trauma_surgeon",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": (
                        "Trauma surgeon leads primary survey after level-1 activation"
                    ),
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": ("$ctx.agent_outputs.clinician_avatar.session_id"),
                    "message": (
                        "I was driving and another car came"
                        " straight at me. I wasn't wearing"
                        " my seatbelt. My head hurts, my"
                        " chest hurts, and my stomach is"
                        " really sore."
                    ),
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Patient describes mechanism and injury pattern"),
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "polytrauma",
                    "differential_diagnosis": [
                        "TBI",
                        "Hemothorax",
                        "Splenic injury",
                    ],
                },
                "delay": 1,
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Diagnosis after trauma surgeon primary survey"),
                },
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "orders": [
                        {
                            "type": "ct_head",
                            "priority": "emergent",
                            "indication": "TBI",
                        },
                        {
                            "type": "ct_chest_abdomen_pelvis",
                            "priority": "emergent",
                            "indication": ("multi-system trauma"),
                        },
                    ]
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": ("Pan-scan for polytrauma assessment"),
                },
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "admission_type": "trauma",
                        "required_monitoring": ("intensive_care"),
                    }
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "optional_predecessors": ["imaging"],
                    "clinical_rationale": ("ICU admission for polytrauma monitoring"),
                },
            },
        ],
        expected_duration=17,
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
                    "vital_signs": {
                        "oxygen_saturation": 85,
                        "respiratory_rate": 45,
                    },
                },
                "delay": 1,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "patient_case": {
                        "chief_complaint": ("Severe wheezing, accessory muscle use"),
                        "age": 8,
                        "gender": "male",
                        "urgency": "high",
                    },
                    "persona": "pediatrician",
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": ("Pediatrician assesses severity of asthma exacerbation"),
                },
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": ("$ctx.agent_outputs.clinician_avatar.session_id"),
                    "message": (
                        "He caught a cold at school and his"
                        " breathing got really bad overnight."
                        " We used his rescue inhaler four"
                        " times but it's not helping. He can"
                        " barely talk right now."
                    ),
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": (
                        "Parent reports trigger, rescue inhaler use, and distress"
                    ),
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "acute asthma symptoms",
                    "differential_diagnosis": [
                        "Asthma exacerbation",
                        "Pneumonia",
                    ],
                },
                "delay": 1,
                "handoff_policy": {
                    "optional_predecessors": ["clinician_avatar"],
                    "clinical_rationale": ("Diagnosis after pediatrician assessment"),
                },
            },
            {
                "agent": "pharmacy",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "med_plan": [
                            "Albuterol",
                            "Methylprednisolone",
                        ],
                        "allergies": [],
                    }
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": ("Bronchodilator and systemic steroid per protocol"),
                },
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {
                            "type": "pulmonology",
                            "when": _future(7),
                            "purpose": ("asthma control review"),
                        }
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["pharmacy"],
                    "clinical_rationale": ("Pulmonology follow-up for asthma management review"),
                },
            },
        ],
        expected_duration=16,
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
            "past_medical_history": [
                "Lumbar disc herniation L4-L5",
                "Hypertension",
                "Fibromyalgia",
            ],
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
        name="new_patient_registration_to_consult",
        description=(
            "First-time patient journey with provider-side registration, insurance eligibility "
            "verification, and assisted enrollment before clinical consultation."
        ),
        patient_profile={
            "age": 33,
            "gender": "female",
            "chief_complaint": "Persistent lower abdominal pain and dizziness",
            "urgency": "medium",
        },
        medical_history={
            "past_medical_history": ["Iron deficiency anemia (history)"],
            "medications": ["Ferrous sulfate (intermittent use)"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "none",
                "occupation": "Market trader",
                "residence": "Kisumu County",
            },
            "family_history": ["Mother with hypertension"],
            "review_of_systems": {
                "gastrointestinal": "Intermittent cramping lower abdominal pain for 5 days",
                "constitutional": "Fatigue and light-headedness, no documented fever",
            },
            "vital_signs": {
                "blood_pressure": "108/66",
                "heart_rate": 98,
                "respiratory_rate": 18,
                "oxygen_saturation": 99,
                "temperature_c": 36.9,
            },
        },
        journey_steps=[
            {
                "agent": "provider_agent",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "request_type": "patient_registration_lookup",
                        "country": "kenya",
                        "lookup_keys": ["national_id", "mobile_number", "date_of_birth"],
                        "on_not_found": "assisted_enrollment",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "hitl_ui",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "review_reason": "registration_not_found",
                        "required_actions": [
                            "verify_identity_documents",
                            "capture_demographics",
                            "confirm_guardian_or_next_of_kin",
                        ],
                    }
                },
                "delay": 1,
            },
            {
                "agent": "insurer_agent",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "policy_check": "eligibility_and_activation",
                        "coverage_program": "social_health_insurance",
                        "require_active_insurance": True,
                        "on_inactive_or_missing": "enrollment_support_and_pending_coverage",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "consent_analyser",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "consent_scope": "registration_and_clinical_data_sharing",
                        "jurisdiction": "kenya",
                        "minimum_necessary": True,
                    }
                },
                "delay": 1,
            },
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "lower abdominal pain, dizziness",
                    "chief_complaint": "new patient post-registration intake",
                    "financial_clearance_state": "insured_or_pending",
                },
                "delay": 1,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "persona_id": "P026",
                    "country": "kenya",
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "Persistent lower abdominal pain and dizziness",
                            "age": 33,
                            "gender": "female",
                            "urgency": "medium",
                        }
                    },
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "The pain started five days ago and comes in waves. I've also felt dizzy when I stand up quickly.",
                },
                "delay": 2,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "lower abdominal pain, dizziness, fatigue",
                    "differential_diagnosis": [
                        "Pelvic inflammatory disease",
                        "Urinary tract infection",
                        "Anemia-related symptomatic dizziness",
                    ],
                },
                "delay": 2,
            },
            {
                "agent": "pharmacy",
                "method": "pharmacy/recommend",
                "params": {
                    "task": {
                        "med_plan": ["Oral rehydration", "Empiric analgesia pending labs"],
                        "allergies": [],
                        "current_medications": ["Ferrous sulfate"],
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
                            "when": _future(7),
                            "purpose": "symptom review and insurance activation confirmation",
                        }
                    ]
                },
                "delay": 1,
            },
        ],
        expected_duration=17,
    ),
    PatientScenario(
        name="registration_failed_urgent_clinical_override",
        description=(
            "Negative-path journey where registration and coverage verification fail, but "
            "urgent clinical override permits emergency treatment while coverage remains pending."
        ),
        patient_profile={
            "age": 41,
            "gender": "male",
            "chief_complaint": "Severe chest pain and shortness of breath",
            "urgency": "critical",
        },
        medical_history={
            "past_medical_history": ["Hypertension"],
            "medications": ["Amlodipine 5 mg daily"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "former smoker",
                "alcohol": "rare",
                "occupation": "Driver",
                "residence": "Nairobi County",
            },
            "family_history": ["Father with myocardial infarction before age 60"],
            "review_of_systems": {
                "cardiac": "Sudden severe central chest pain radiating to left arm",
                "respiratory": "Dyspnea with diaphoresis",
            },
            "vital_signs": {
                "blood_pressure": "162/96",
                "heart_rate": 118,
                "respiratory_rate": 26,
                "oxygen_saturation": 93,
                "temperature_c": 36.8,
            },
        },
        journey_steps=[
            {
                "agent": "provider_agent",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "request_type": "patient_registration_lookup",
                        "country": "kenya",
                        "lookup_keys": ["national_id", "mobile_number", "date_of_birth"],
                        "simulated_result": "not_found",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "insurer_agent",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "policy_check": "eligibility_and_activation",
                        "coverage_program": "social_health_insurance",
                        "require_active_insurance": True,
                        "simulated_result": "inactive_or_missing",
                    }
                },
                "delay": 1,
            },
            {
                "agent": "hitl_ui",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "review_reason": "registration_and_coverage_failure_urgent_case",
                        "required_actions": [
                            "approve_urgent_clinical_override",
                            "record_financial_counselling_required",
                            "set_coverage_state_pending",
                        ],
                    }
                },
                "delay": 1,
            },
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "severe chest pain, dyspnea, diaphoresis",
                    "chief_complaint": "urgent care override after registration failure",
                    "clinical_override": True,
                    "financial_clearance_state": "pending",
                },
                "delay": 1,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "persona_id": "P026",
                    "country": "kenya",
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "Severe chest pain and shortness of breath",
                            "age": 41,
                            "gender": "male",
                            "urgency": "critical",
                        }
                    },
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "The chest pain started suddenly an hour ago and is getting worse. I feel sweaty and cannot catch my breath.",
                },
                "delay": 2,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "acute chest pain, dyspnea, diaphoresis",
                    "differential_diagnosis": [
                        "Acute coronary syndrome",
                        "Pulmonary embolism",
                        "Aortic dissection",
                    ],
                },
                "delay": 2,
            },
            {
                "agent": "pharmacy",
                "method": "pharmacy/recommend",
                "params": {
                    "task": {
                        "med_plan": ["Aspirin loading dose", "Oxygen support"],
                        "allergies": [],
                        "current_medications": ["Amlodipine"],
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
                        "billing_status": "pending_coverage_override",
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
                            "type": "financial_counselling",
                            "when": _future(1),
                            "purpose": "complete enrollment and activate insurance",
                        }
                    ]
                },
                "delay": 1,
            },
        ],
        expected_duration=18,
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
            "past_medical_history": [
                "Chronic obstructive pulmonary disease",
                "Former TB (treated 2015)",
            ],
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
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "It started about three weeks ago. I get this tight feeling across my chest when I'm climbing stairs or lifting heavy things at work. It goes away when I sit down for a few minutes.",
                },
                "delay": 2,
            },
            # 4 — Patient answers follow-up about radiation and associations
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
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
                        {
                            "type": "ecg",
                            "priority": "urgent",
                            "indication": "exertional chest pain",
                        },
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

enrich_scenario_handoff_contracts(ADDITIONAL_SCENARIOS)


# ── Persona-Aware Scenarios ────────────────────────────────────────────────────
# These scenarios exercise the persona registry and IAM system.  Each one uses
# a specific persona_id from config/personas.json and targets a different country
# context, care setting, or clinical domain.

PERSONA_SCENARIOS: list[PatientScenario] = [
    # ── 1. UK GP consultation (P002) ─────────────────────────────────────────
    PatientScenario(
        name="clinician_avatar_uk_gp_consultation",
        description=(
            "UK primary-care consultation via the Clinician Avatar using the GP persona (P002). "
            "Patient presents with persistent cough and breathlessness — the avatar interviews "
            "using Calgary-Cambridge, then delegates diagnosis."
        ),
        patient_profile={
            "age": 38,
            "gender": "female",
            "chief_complaint": "Persistent cough for 3 weeks",
            "urgency": "low",
        },
        medical_history={
            "past_medical_history": ["Seasonal asthma (childhood)", "No current medications"],
            "medications": ["Salbutamol PRN (rarely used)"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "occasional",
                "occupation": "Teacher",
                "exercise": "regular",
            },
            "family_history": ["Father with COPD"],
            "review_of_systems": {
                "respiratory": "Dry cough, no haemoptysis, worse at night",
                "constitutional": "Mild fatigue, no fevers, no weight loss",
            },
            "vital_signs": {
                "blood_pressure": "118/72",
                "heart_rate": 74,
                "respiratory_rate": 14,
                "oxygen_saturation": 99,
                "temperature_c": 36.6,
            },
        },
        journey_steps=[
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "persona_id": "P002",
                    "country": "uk",
                    "care_setting": "primary_care",
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "Persistent cough for 3 weeks",
                            "age": 38,
                            "gender": "female",
                            "urgency": "low",
                        }
                    },
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "I've had this dry cough for about three weeks. It keeps me up at night.",
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "No blood. I had childhood asthma but haven't needed my inhaler in years.",
                },
                "delay": 2,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "persistent dry cough, 3 weeks, nocturnal, no haemoptysis",
                    "differential_diagnosis": [
                        "Asthma exacerbation",
                        "GORD",
                        "Post-nasal drip",
                        "ACE inhibitor cough",
                    ],
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "GP delegates to diagnosis after avatar history taking",
                },
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {"type": "primary_care", "when": _future(14), "purpose": "Cough review"},
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "GP follow-up after diagnostic workup",
                },
            },
        ],
        expected_duration=12,
    ),
    # ── 2. USA Attending Physician (P014) — Chest pain ACS pathway ───────────
    PatientScenario(
        name="clinician_avatar_usa_attending_acs",
        description=(
            "USA hospital consultation using the Attending Physician persona (P014). "
            "Patient presents with suspected ACS — avatar uses SOCRATES framework, "
            "then delegates to diagnosis and imaging."
        ),
        patient_profile={
            "age": 62,
            "gender": "male",
            "chief_complaint": "Severe crushing chest pain radiating to left arm",
            "urgency": "high",
        },
        medical_history={
            "past_medical_history": ["Hypertension", "Type 2 diabetes", "Hyperlipidaemia"],
            "medications": ["Lisinopril 10 mg", "Metformin 1000 mg BID", "Atorvastatin 40 mg"],
            "allergies": ["Aspirin (GI intolerance — can use alternative)"],
            "social_history": {
                "tobacco": "former smoker (quit 5 years ago)",
                "alcohol": "social",
                "occupation": "Retired engineer",
            },
            "family_history": ["Father had MI at age 58"],
            "review_of_systems": {
                "cardiac": "Crushing substernal pain 7/10, radiation to left arm, diaphoresis",
                "respiratory": "Mild dyspnoea, no cough",
                "neurological": "No syncope, no focal deficits",
            },
            "vital_signs": {
                "blood_pressure": "158/96",
                "heart_rate": 104,
                "respiratory_rate": 22,
                "oxygen_saturation": 94,
                "temperature_c": 37.1,
            },
        },
        journey_steps=[
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "persona_id": "P014",
                    "country": "usa",
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "Severe crushing chest pain radiating to left arm",
                            "age": 62,
                            "gender": "male",
                            "urgency": "high",
                        }
                    },
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "The pain started about 45 minutes ago. It feels like an elephant on my chest.",
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "It's going into my left arm and I feel sweaty and short of breath.",
                },
                "delay": 2,
            },
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "crushing chest pain, left arm radiation, diaphoresis, dyspnoea",
                    "vital_signs": {
                        "blood_pressure": "158/96",
                        "heart_rate": 104,
                        "oxygen_saturation": 94,
                    },
                    "chief_complaint": "suspected ACS",
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Attending physician escalates to ED triage after avatar assessment",
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "ACS presentation",
                    "differential_diagnosis": [
                        "STEMI",
                        "NSTEMI",
                        "Unstable angina",
                        "Aortic dissection",
                    ],
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": "USA attending delegates diagnosis with STEMI protocol",
                },
            },
        ],
        expected_duration=14,
    ),
    # ── 3. Kenya Medical Officer (P026) — Paediatric fever/malaria ────────────
    PatientScenario(
        name="clinician_avatar_kenya_medical_officer",
        description=(
            "Kenya health facility consultation using the Medical Officer persona (P026). "
            "Paediatric patient with high fever and vomiting — potential malaria or typhoid."
        ),
        patient_profile={
            "age": 7,
            "gender": "male",
            "chief_complaint": "High fever for 2 days and vomiting",
            "urgency": "high",
        },
        medical_history={
            "past_medical_history": ["No chronic illness", "Malaria episode 1 year ago"],
            "medications": [],
            "allergies": [],
            "social_history": {
                "tobacco": "N/A",
                "alcohol": "N/A",
                "school": "Grade 2",
                "area": "Rural Kisumu County, near Lake Victoria",
            },
            "family_history": ["No significant family history reported"],
            "review_of_systems": {
                "constitutional": "Fever 39.8°C, chills, rigors, poor appetite for 2 days",
                "gastrointestinal": "Vomited twice this morning, no diarrhoea",
                "neurological": "Alert but irritable, no neck stiffness, no seizures",
            },
            "vital_signs": {
                "blood_pressure": "90/60",
                "heart_rate": 128,
                "respiratory_rate": 26,
                "oxygen_saturation": 96,
                "temperature_c": 39.8,
            },
        },
        journey_steps=[
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "persona_id": "P026",
                    "country": "kenya",
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "High fever for 2 days and vomiting",
                            "age": 7,
                            "gender": "male",
                            "urgency": "high",
                        }
                    },
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "My son has had fever for two days, he won't eat and vomited this morning.",
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "We live near the lake. He had malaria last year. We are worried.",
                },
                "delay": 2,
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "paediatric fever 2 days, vomiting, malaria exposure risk",
                    "differential_diagnosis": [
                        "Plasmodium falciparum malaria",
                        "Typhoid fever",
                        "Bacterial sepsis",
                    ],
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Medical officer delegates diagnosis with malaria protocol for endemic area",
                },
            },
            {
                "agent": "pharmacy",
                "method": "pharmacy/recommend",
                "params": {
                    "task": {
                        "med_plan": ["Artemether-lumefantrine (first-line malaria)"],
                        "allergies": [],
                        "current_medications": [],
                        "weight_kg": 22,
                    }
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "ACT treatment recommendation per Kenya MOH malaria guidelines",
                },
            },
        ],
        expected_duration=10,
    ),
    # ── 4. UK Telehealth Clinician (P048) — Remote follow-up ─────────────────
    PatientScenario(
        name="clinician_avatar_telehealth_uk_followup",
        description=(
            "UK telehealth consultation using the Telehealth Clinician persona (P048). "
            "Post-discharge remote follow-up for a frailty patient — avatar interviews "
            "then escalates care plan update to CCM agent."
        ),
        patient_profile={
            "age": 78,
            "gender": "female",
            "chief_complaint": "Post-discharge follow-up — mobility and medication review",
            "urgency": "low",
        },
        medical_history={
            "past_medical_history": [
                "Atrial fibrillation",
                "Osteoporosis",
                "Mild cognitive impairment",
            ],
            "medications": [
                "Apixaban 5 mg BID",
                "Alendronate 70 mg weekly",
                "Donepezil 5 mg daily",
            ],
            "allergies": ["NSAIDs (GI bleed history)"],
            "social_history": {
                "tobacco": "never",
                "alcohol": "rarely",
                "occupation": "Retired",
                "living": "Lives alone; daughter nearby",
                "care": "Morning carer visits daily",
            },
            "family_history": ["Daughter manages health proxy"],
            "review_of_systems": {
                "musculoskeletal": "Hip pain improving, walking with frame",
                "neurological": "Mild confusion in evenings (sundowning)",
                "cardiac": "No palpitations, no syncope",
            },
            "vital_signs": {
                "blood_pressure": "134/80",
                "heart_rate": 72,
                "respiratory_rate": 16,
                "oxygen_saturation": 97,
                "temperature_c": 36.5,
            },
        },
        journey_steps=[
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "persona_id": "P048",
                    "country": "uk",
                    "care_setting": "telehealth",
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "Post-discharge follow-up — mobility and medication review",
                            "age": 78,
                            "gender": "female",
                            "urgency": "low",
                        }
                    },
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "I'm managing alright but still need the frame to walk. The hip is less painful.",
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "I'm a bit confused in the evenings but the carer comes in the morning.",
                },
                "delay": 2,
            },
            {
                "agent": "ccm_agent" if False else "care_coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "care_plan_update": {
                        "patient_id": "frailty-telehealth-001",
                        "actions": [
                            "physiotherapy referral",
                            "medication compliance check",
                            "cognitive review",
                        ],
                    }
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Telehealth clinician escalates care plan update after remote assessment",
                },
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {
                            "type": "telehealth",
                            "when": _future(28),
                            "purpose": "4-week telehealth review",
                        },
                        {
                            "type": "memory_clinic",
                            "when": _future(42),
                            "purpose": "Cognitive assessment",
                        },
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["care_coordinator"],
                    "clinical_rationale": "Telehealth follow-up schedule with memory clinic referral",
                },
            },
        ],
        expected_duration=14,
    ),
    # ── 5. Psychiatrist (P065) — Mental health assessment ─────────────────────
    PatientScenario(
        name="clinician_avatar_psychiatrist_mental_health",
        description=(
            "Mental health consultation using the Psychiatrist persona (P065). "
            "Patient with depressive episode and anxiety — avatar uses Calgary-Cambridge "
            "with trauma-informed approach, then delegates to care coordinator."
        ),
        patient_profile={
            "age": 29,
            "gender": "female",
            "chief_complaint": "Persistent low mood and anxiety for 6 months",
            "urgency": "medium",
        },
        medical_history={
            "past_medical_history": [
                "Generalised anxiety disorder (diagnosed 3 years ago)",
                "No psychosis history",
            ],
            "medications": ["Sertraline 50 mg daily (6 weeks)"],
            "allergies": ["No known drug allergies"],
            "social_history": {
                "tobacco": "occasional",
                "alcohol": "none",
                "occupation": "Graphic designer (currently on sick leave)",
                "living": "Lives with partner",
                "support": "Partner supportive; limited family contact",
            },
            "family_history": ["Mother with depression"],
            "review_of_systems": {
                "psychiatric": "Low mood, anhedonia, poor sleep, reduced concentration, occasional passive SI (no plan)",
                "anxiety": "Generalised worry, social withdrawal, avoidance behaviours",
                "somatic": "Fatigue, poor appetite, no significant weight change",
            },
            "vital_signs": {
                "blood_pressure": "112/70",
                "heart_rate": 82,
                "respiratory_rate": 14,
                "oxygen_saturation": 99,
                "temperature_c": 36.5,
            },
            "risk_assessment": {
                "suicidal_ideation": "passive, no plan, no intent",
                "self_harm": "none current",
                "protective_factors": ["partner, employment goal", "therapy engagement"],
            },
        },
        journey_steps=[
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "persona_id": "P065",
                    "country": "uk",
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "Persistent low mood and anxiety for 6 months",
                            "age": 29,
                            "gender": "female",
                            "urgency": "medium",
                        }
                    },
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "I've been feeling really low and can't seem to enjoy anything anymore. It's been months.",
                },
                "delay": 2,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "The anxiety is the worst part. I stopped going out. I feel hopeless sometimes but I wouldn't hurt myself.",
                },
                "delay": 2,
            },
            {
                "agent": "care_coordinator",
                "method": "tasks/sendSubscribe",
                "params": {
                    "care_plan": {
                        "type": "mental_health",
                        "interventions": [
                            "CBT referral",
                            "medication review at 8 weeks",
                            "crisis plan",
                        ],
                        "risk_level": "moderate",
                        "escalation_trigger": "active SI or plan",
                    }
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Psychiatrist delegates care coordination after risk stratification",
                },
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {
                            "type": "psychiatry",
                            "when": _future(14),
                            "purpose": "Medication review + risk reassessment",
                        },
                        {"type": "cbt", "when": _future(21), "purpose": "First CBT session"},
                    ]
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["care_coordinator"],
                    "clinical_rationale": "Psychiatric follow-up schedule with therapy referral",
                },
            },
        ],
        expected_duration=16,
        negative_class=None,
    ),
    # ── 6. Multi-agent delegation chain — IAM-aware chest pain ───────────────
    PatientScenario(
        name="multi_agent_delegation_chest_pain_iam",
        description=(
            "Demonstrates the full delegation chain for a chest pain scenario with IAM persona context. "
            "Avatar (P001) → Care Coordinator (P021) → Triage (P004) → Diagnosis (P001) → Imaging (P005). "
            "Tests that each handoff respects persona scopes and delegation policy."
        ),
        patient_profile={
            "age": 55,
            "gender": "male",
            "chief_complaint": "Crushing chest pain, 45 minutes, radiation to jaw",
            "urgency": "critical",
        },
        medical_history={
            "past_medical_history": ["Hypertension", "Hypercholesterolaemia"],
            "medications": ["Amlodipine 10 mg", "Atorvastatin 40 mg"],
            "allergies": ["Penicillin"],
            "social_history": {"tobacco": "current smoker", "alcohol": "moderate"},
            "family_history": ["Father — MI aged 52"],
            "review_of_systems": {
                "cardiac": "Crushing central chest pain 9/10, jaw radiation, diaphoresis, nausea",
                "respiratory": "Severe dyspnoea at rest",
            },
            "vital_signs": {
                "blood_pressure": "100/65",
                "heart_rate": 115,
                "respiratory_rate": 28,
                "oxygen_saturation": 91,
                "temperature_c": 37.2,
            },
            "iam_context": {
                "initiating_agent": "clinician_avatar_agent",
                "initiating_persona": "P001",
                "delegation_chain": [
                    "clinician_avatar_agent → care_coordinator",
                    "care_coordinator → triage_agent",
                    "triage_agent → diagnosis_agent",
                    "diagnosis_agent → imaging_agent",
                ],
                "max_delegation_depth": 3,
            },
        },
        journey_steps=[
            {
                "agent": "clinician_avatar",
                "method": "avatar/start_session",
                "params": {
                    "persona_id": "P001",
                    "country": "uk",
                    "patient_case": {
                        "patient_profile": {
                            "chief_complaint": "Crushing chest pain, 45 minutes, radiation to jaw",
                            "age": 55,
                            "gender": "male",
                            "urgency": "critical",
                        }
                    },
                },
                "delay": 1,
            },
            {
                "agent": "clinician_avatar",
                "method": "avatar/patient_message",
                "params": {
                    "session_id": "$ctx.agent_outputs.clinician_avatar.session_id",
                    "message": "It came on suddenly 45 minutes ago — crushing, going to my jaw. I feel faint.",
                },
                "delay": 1,
            },
            {
                "agent": "triage",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "STEMI presentation — chest pain, jaw radiation, haemodynamic compromise",
                    "vital_signs": {
                        "blood_pressure": "100/65",
                        "heart_rate": 115,
                        "oxygen_saturation": 91,
                    },
                    "persona_context": {
                        "initiating_persona": "P001",
                        "delegated_by": "clinician_avatar_agent",
                    },
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["clinician_avatar"],
                    "clinical_rationale": "Avatar Consultant Physician escalates via STEMI protocol; delegation depth 1",
                },
            },
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {
                    "symptoms": "Suspected STEMI",
                    "differential_diagnosis": ["STEMI", "Type 2 MI", "Aortic dissection"],
                    "persona_context": {"persona": "P001", "delegation_depth": 2},
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["triage"],
                    "clinical_rationale": "Diagnosis agent (Consultant Physician) activated; delegation depth 2",
                },
            },
            {
                "agent": "imaging",
                "method": "tasks/sendSubscribe",
                "params": {
                    "imaging_request": {"type": "CXR + Echo", "urgency": "STAT"},
                    "persona_context": {"persona": "P005", "delegation_depth": 3},
                },
                "delay": 2,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "Radiologist persona activated by Diagnosis; max delegation depth 3",
                },
            },
            {
                "agent": "pharmacy",
                "method": "pharmacy/recommend",
                "params": {
                    "task": {
                        "med_plan": [
                            "Aspirin 300 mg loading",
                            "Heparin infusion",
                            "GTN sublingual",
                        ],
                        "allergies": ["Penicillin"],
                        "persona_context": {"persona": "P007"},
                    }
                },
                "delay": 1,
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "clinical_rationale": "STEMI pharmacotherapy per ACS protocol; Pharmacist persona (P007)",
                },
            },
        ],
        expected_duration=12,
    ),
]

# Enrich persona scenarios with handoff contracts
enrich_scenario_handoff_contracts(PERSONA_SCENARIOS)

# Merge persona scenarios into the main ADDITIONAL_SCENARIOS list so they are
# picked up by TestScenarioCatalog and the run_additional_scenarios runner.
ADDITIONAL_SCENARIOS.extend(PERSONA_SCENARIOS)


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

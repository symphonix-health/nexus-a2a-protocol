#!/usr/bin/env python3
"""Generate 300 clinical pathway personalisation test scenarios.

Produces 3 JSON files × 100 scenarios each in BulletTrain canonical format:
  - scenarios_heart_failure_copd.json   (HF + COPD pathways)
  - scenarios_diabetes_sepsis.json      (T2DM + Sepsis pathways)
  - scenarios_maternal_cross_pathway.json (Maternal + cross-pathway)

Each file has 85% positive, 10% negative, 5% edge-case ratios.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
SCENARIOS_DIR.mkdir(exist_ok=True)


def _scenario(
    *,
    usecaseid: str,
    component: str,
    scenario: str,
    testtype: str,
    priority: str,
    pathway_id: str,
    patient_age: int,
    patient_gender: str,
    chief_complaint: str,
    conditions: list[dict] | None = None,
    medications: list[dict] | None = None,
    allergies: list[dict] | None = None,
    observations: list[dict] | None = None,
    vital_signs: dict | None = None,
    frailty_score: str = "",
    social_history: dict | None = None,
    encounters: list[dict] | None = None,
    expected_outcome: str = "personalised_pathway_returned",
    expected_modifications: list[str] | None = None,
    expected_safety_alerts: list[str] | None = None,
    notes: str = "",
) -> dict:
    """Build a single scenario in BulletTrain canonical JSON format."""
    conditions = conditions or []
    medications = medications or []
    allergies = allergies or []
    observations = observations or []
    vital_signs = vital_signs or {}
    social_history = social_history or {}
    encounters = encounters or []
    expected_modifications = expected_modifications or []
    expected_safety_alerts = expected_safety_alerts or []

    input_data = {
        "pathway_id": pathway_id,
        "patient_context": {
            "demographics": {
                "patient_id": f"SIM-{usecaseid}",
                "age": patient_age,
                "gender": patient_gender,
            },
            "chief_complaint": chief_complaint,
            "conditions": conditions,
            "medications": medications,
            "allergies": allergies,
            "observations": observations,
            "vital_signs": vital_signs,
            "frailty_score": frailty_score,
            "social_history": social_history,
            "encounters": encounters,
        },
    }

    return {
        "usecaseid": usecaseid,
        "component": component,
        "scenario": scenario,
        "testtype": testtype,
        "priority": priority,
        "inputdata": json.dumps(input_data, separators=(",", ":")),
        "expectedoutcome": {
            "status": expected_outcome,
            "modifications": expected_modifications,
            "safety_alerts": expected_safety_alerts,
        },
        "pre_conditions": f"Pathway {pathway_id} loaded in repository",
        "post_conditions": "Personalised pathway returned with audit trail",
        "dependencies": "clinical-pathways engine",
        "performancemetrics": "response_time < 500ms",
        "securitycontext": "PHI redacted for AI processing",
        "compliancetags": "NICE,GDPR,Caldicott",
        "notes": notes,
        "requestresponsejourney": {
            "request": {
                "fields_required": ["pathway_id", "patient_context"],
                "example_payload": input_data,
            },
            "response": {
                "expected_fields": [
                    "personalised_pathway",
                    "explainability_report",
                    "modifications",
                    "confidence_level",
                    "safety_alerts",
                ],
                "validation_checks": [
                    f"Outcome is {expected_outcome}",
                    *(f"Modification {m} present" for m in expected_modifications),
                    *(f"Safety alert {a} raised" for a in expected_safety_alerts),
                ],
            },
            "journey_steps": [
                "1. Patient context assembled",
                "2. Pathway loaded from repository",
                "3. Personalisation rules evaluated",
                "4. Safety guardrails checked",
                "5. Personalised pathway built",
                "6. Audit trail recorded",
            ],
        },
        "operationtype": "personalise",
    }


# ════════════════════════════════════════════════════════════════════
# FILE 1: Heart Failure + COPD (100 scenarios)
# ════════════════════════════════════════════════════════════════════

def generate_hf_copd() -> list[dict]:
    scenarios = []
    sid = 0

    # ── POSITIVE (85) ────────────────────────────────────────────

    # 1-10: Simple suspected HF — standard pathway, no modifications
    for i in range(1, 11):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Suspected HF standard workup (age {45+i})",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng106-heart-failure",
            patient_age=45 + i, patient_gender="male" if i % 2 == 0 else "female",
            chief_complaint="breathlessness",
            observations=[{"code": "nt_pro_bnp", "value": 500 + i * 50, "unit": "ng/L"}],
        ))

    # 11-20: Known HF, stable, dual therapy
    for i in range(1, 11):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Stable HF on dual therapy (age {55+i})",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng106-heart-failure",
            patient_age=55 + i, patient_gender="male",
            chief_complaint="routine review",
            conditions=[{"code": "heart_failure", "display": "Chronic heart failure"}],
            medications=[
                {"code": "ramipril", "display": "Ramipril 5mg", "dose": "5mg", "frequency": "daily"},
                {"code": "bisoprolol", "display": "Bisoprolol 5mg", "dose": "5mg", "frequency": "daily"},
            ],
            observations=[
                {"code": "nt_pro_bnp", "value": 800.0, "unit": "ng/L"},
                {"code": "egfr", "value": 65.0, "unit": "mL/min/1.73m2"},
            ],
        ))

    # 21-30: HF + CKD → renal-safe modification
    for i in range(1, 11):
        sid += 1
        egfr_val = 25 + i * 2
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"HF with CKD eGFR={egfr_val} renal-safe path",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng106-heart-failure",
            patient_age=65 + i, patient_gender="male" if i % 3 != 0 else "female",
            chief_complaint="breathlessness",
            conditions=[
                {"code": "heart_failure", "display": "Chronic heart failure"},
                {"code": "ckd_stage_3", "display": "CKD Stage 3"},
            ],
            medications=[
                {"code": "ramipril", "display": "Ramipril 5mg"},
                {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
                {"code": "furosemide", "display": "Furosemide 40mg"},
            ],
            observations=[
                {"code": "egfr", "value": float(egfr_val), "unit": "mL/min/1.73m2"},
                {"code": "nt_pro_bnp", "value": 1200.0, "unit": "ng/L"},
            ],
            expected_modifications=["sequence_changed", "urgency_elevated"],
        ))

    # 31-40: HF + polypharmacy → medication review
    for i in range(1, 11):
        sid += 1
        med_count = 6 + i % 5
        meds = [{"code": f"med_{j}", "display": f"Medication {j}"} for j in range(med_count)]
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"HF polypharmacy ({med_count} meds) review trigger",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng106-heart-failure",
            patient_age=70 + i % 10, patient_gender="female" if i % 2 == 0 else "male",
            chief_complaint="breathlessness",
            conditions=[
                {"code": "heart_failure", "display": "Chronic heart failure"},
                {"code": "hypertension", "display": "Hypertension"},
            ],
            medications=meds,
            observations=[{"code": "nt_pro_bnp", "value": 900.0, "unit": "ng/L"}],
            expected_modifications=["sequence_changed"],
        ))

    # 41-50: HF + frailty → community follow-up
    for i in range(1, 11):
        sid += 1
        frailty = "moderate" if i <= 5 else "severe"
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"HF with {frailty} frailty adapted follow-up",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng106-heart-failure",
            patient_age=78 + i % 5, patient_gender="female" if i % 2 == 0 else "male",
            chief_complaint="fatigue",
            conditions=[{"code": "heart_failure", "display": "Chronic heart failure"}],
            medications=[
                {"code": "ramipril", "display": "Ramipril 5mg"},
                {"code": "furosemide", "display": "Furosemide 40mg"},
            ],
            observations=[{"code": "nt_pro_bnp", "value": 1500.0, "unit": "ng/L"}],
            frailty_score=frailty,
            expected_modifications=["follow_up_adapted"],
        ))

    # 51-55: Simple COPD — standard pathway
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Suspected COPD standard spirometry workup",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng115-copd",
            patient_age=50 + i * 2, patient_gender="male" if i % 2 == 0 else "female",
            chief_complaint="chronic cough",
            observations=[{"code": "fev1_percent", "value": float(55 + i * 5), "unit": "%"}],
        ))

    # 56-60: Known COPD stable review
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Stable COPD on inhaler therapy review",
            testtype="Positive", priority="P2",
            pathway_id="nice-ng115-copd",
            patient_age=60 + i, patient_gender="male",
            chief_complaint="routine review",
            conditions=[{"code": "copd", "display": "COPD"}],
            medications=[
                {"code": "salbutamol", "display": "Salbutamol inhaler"},
                {"code": "tiotropium", "display": "Tiotropium inhaler"},
            ],
            observations=[{"code": "fev1_percent", "value": float(45 + i * 3), "unit": "%"}],
        ))

    # 61-65: COPD + CHF comorbidity → safety override
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"COPD with HF comorbidity safety adaptation",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng115-copd",
            patient_age=68 + i, patient_gender="male",
            chief_complaint="worsening breathlessness",
            conditions=[
                {"code": "copd", "display": "COPD"},
                {"code": "heart_failure", "display": "Chronic heart failure"},
            ],
            medications=[
                {"code": "salbutamol", "display": "Salbutamol inhaler"},
                {"code": "tiotropium", "display": "Tiotropium inhaler"},
                {"code": "ramipril", "display": "Ramipril 5mg"},
            ],
            observations=[{"code": "fev1_percent", "value": 40.0, "unit": "%"}],
            expected_modifications=["safety_override", "urgency_elevated"],
        ))

    # 66-70: COPD severe
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Severe COPD FEV1={25+i*2}% management",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng115-copd",
            patient_age=55 + i, patient_gender="female",
            chief_complaint="breathlessness",
            conditions=[{"code": "copd", "display": "COPD"}],
            medications=[{"code": "salbutamol", "display": "Salbutamol inhaler"}],
            observations=[{"code": "fev1_percent", "value": float(25 + i * 2), "unit": "%"}],
        ))

    # 71-75: HF + transport barrier → telehealth follow-up
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"HF with transport barrier telehealth adaptation",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng106-heart-failure",
            patient_age=60 + i, patient_gender="female",
            chief_complaint="ankle swelling",
            conditions=[{"code": "heart_failure", "display": "Chronic heart failure"}],
            medications=[
                {"code": "ramipril", "display": "Ramipril 5mg"},
                {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
            ],
            observations=[{"code": "nt_pro_bnp", "value": 700.0, "unit": "ng/L"}],
            social_history={"transport_access": "poor"},
            expected_modifications=["follow_up_adapted"],
        ))

    # 76-80: HF + multiple comorbidities
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"HF multi-morbid (DM2, AF, HTN) complex path",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng106-heart-failure",
            patient_age=72 + i, patient_gender="male",
            chief_complaint="breathlessness",
            conditions=[
                {"code": "heart_failure", "display": "Chronic heart failure"},
                {"code": "type_2_diabetes", "display": "Type 2 diabetes"},
                {"code": "hypertension", "display": "Hypertension"},
                {"code": "atrial_fibrillation", "display": "Atrial fibrillation"},
            ],
            medications=[
                {"code": "ramipril", "display": "Ramipril 5mg"},
                {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
                {"code": "metformin", "display": "Metformin 500mg"},
                {"code": "warfarin", "display": "Warfarin 5mg"},
                {"code": "atorvastatin", "display": "Atorvastatin 80mg"},
            ],
            observations=[
                {"code": "egfr", "value": 50.0, "unit": "mL/min/1.73m2"},
                {"code": "nt_pro_bnp", "value": 1600.0, "unit": "ng/L"},
                {"code": "hba1c", "value": 55.0, "unit": "mmol/mol"},
            ],
            frailty_score="moderate",
            expected_modifications=["sequence_changed", "follow_up_adapted"],
        ))

    # 81-85: COPD exacerbation history
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"COPD frequent exacerbation management",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng115-copd",
            patient_age=62 + i, patient_gender="male" if i <= 3 else "female",
            chief_complaint="worsening breathlessness",
            conditions=[{"code": "copd", "display": "COPD"}],
            medications=[
                {"code": "salbutamol", "display": "Salbutamol inhaler"},
                {"code": "tiotropium", "display": "Tiotropium inhaler"},
                {"code": "beclometasone", "display": "Beclometasone inhaler"},
            ],
            observations=[{"code": "fev1_percent", "value": 35.0, "unit": "%"}],
        ))

    # ── NEGATIVE (10) ────────────────────────────────────────────

    # 86-90: Patient doesn't meet entry criteria
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-NEG-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Paediatric patient on HF pathway (age {10+i})",
            testtype="Negative", priority="P2",
            pathway_id="nice-ng106-heart-failure",
            patient_age=10 + i, patient_gender="male",
            chief_complaint="headache",
            notes="Patient does not meet HF pathway entry criteria",
        ))

    # 91-95: COPD pathway with no respiratory symptoms
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"HF-NEG-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"COPD pathway no respiratory symptoms",
            testtype="Negative", priority="P2",
            pathway_id="nice-ng115-copd",
            patient_age=55 + i, patient_gender="female",
            chief_complaint="knee pain",
            conditions=[{"code": "osteoarthritis", "display": "Osteoarthritis"}],
            notes="No respiratory condition or symptoms",
        ))

    # ── EDGE CASES (5) ───────────────────────────────────────────

    # 96: HF + critical potassium + CKD4 + massive polypharmacy
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"HF-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="HF critical K+ 6.2 CKD4 11 meds extreme complexity",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_age=82, patient_gender="male",
        chief_complaint="breathlessness",
        conditions=[
            {"code": "heart_failure", "display": "Chronic heart failure"},
            {"code": "ckd_stage_4", "display": "CKD Stage 4"},
        ],
        medications=[
            {"code": "ramipril", "display": "Ramipril 5mg"},
            {"code": "spironolactone", "display": "Spironolactone 25mg"},
            {"code": "furosemide", "display": "Furosemide 40mg"},
            {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
            {"code": "atorvastatin", "display": "Atorvastatin 80mg"},
            {"code": "metformin", "display": "Metformin 500mg"},
            {"code": "warfarin", "display": "Warfarin 5mg"},
            {"code": "amlodipine", "display": "Amlodipine 5mg"},
            {"code": "omeprazole", "display": "Omeprazole 20mg"},
            {"code": "paracetamol", "display": "Paracetamol 1g PRN"},
            {"code": "aspirin", "display": "Aspirin 75mg"},
        ],
        allergies=[{"substance": "penicillin", "category": "medication", "severity": "severe"}],
        observations=[
            {"code": "potassium", "value": 6.2, "unit": "mmol/L"},
            {"code": "egfr", "value": 12.0, "unit": "mL/min/1.73m2"},
            {"code": "nt_pro_bnp", "value": 3500.0, "unit": "ng/L"},
        ],
        frailty_score="very_severe",
        expected_modifications=["safety_override", "contraindication_flagged", "intensity_reduced"],
        expected_safety_alerts=["critical_potassium", "critical_egfr"],
    ))

    # 97: COPD + HF + CKD — triple comorbidity
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"HF-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="COPD-HF-CKD triple comorbidity severe frailty",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng115-copd",
        patient_age=75, patient_gender="female",
        chief_complaint="worsening breathlessness",
        conditions=[
            {"code": "copd", "display": "COPD"},
            {"code": "heart_failure", "display": "Chronic heart failure"},
            {"code": "ckd_stage_3", "display": "CKD Stage 3"},
        ],
        medications=[
            {"code": "salbutamol", "display": "Salbutamol"},
            {"code": "tiotropium", "display": "Tiotropium"},
            {"code": "ramipril", "display": "Ramipril"},
            {"code": "bisoprolol", "display": "Bisoprolol"},
            {"code": "furosemide", "display": "Furosemide"},
            {"code": "spironolactone", "display": "Spironolactone"},
        ],
        observations=[
            {"code": "fev1_percent", "value": 28.0, "unit": "%"},
            {"code": "egfr", "value": 35.0, "unit": "mL/min/1.73m2"},
            {"code": "nt_pro_bnp", "value": 2200.0, "unit": "ng/L"},
        ],
        frailty_score="severe",
        expected_modifications=["safety_override", "urgency_elevated", "intensity_reduced"],
    ))

    # 98: Very young adult with HF
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"HF-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Young adult age 19 suspected HF unusual presentation",
        testtype="Edge", priority="P1",
        pathway_id="nice-ng106-heart-failure",
        patient_age=19, patient_gender="female",
        chief_complaint="breathlessness",
        observations=[{"code": "nt_pro_bnp", "value": 600.0, "unit": "ng/L"}],
    ))

    # 99: HF + language barrier
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"HF-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="HF with language barrier interpreter needed",
        testtype="Edge", priority="P1",
        pathway_id="nice-ng106-heart-failure",
        patient_age=70, patient_gender="male",
        chief_complaint="breathlessness",
        conditions=[{"code": "heart_failure", "display": "Chronic heart failure"}],
        medications=[
            {"code": "ramipril", "display": "Ramipril 5mg"},
            {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
        ],
        observations=[{"code": "nt_pro_bnp", "value": 1000.0, "unit": "ng/L"}],
        social_history={"language_barrier": True, "interpreter_needed": True},
        expected_modifications=["activity_added"],
    ))

    # 100: Empty observations — minimal context
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"HF-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Minimal context no observations no conditions",
        testtype="Edge", priority="P2",
        pathway_id="nice-ng106-heart-failure",
        patient_age=60, patient_gender="unknown",
        chief_complaint="breathlessness",
    ))

    return scenarios


# ════════════════════════════════════════════════════════════════════
# FILE 2: Diabetes + Sepsis (100 scenarios)
# ════════════════════════════════════════════════════════════════════

def generate_dm_sepsis() -> list[dict]:
    scenarios = []
    sid = 0

    # ── POSITIVE (85) ────────────────────────────────────────────

    # 1-10: Simple T2DM — standard pathway
    for i in range(1, 11):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"T2DM standard review HbA1c={50+i}",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=40 + i * 2, patient_gender="male" if i % 2 == 0 else "female",
            chief_complaint="diabetes review",
            conditions=[{"code": "type_2_diabetes", "display": "Type 2 diabetes"}],
            medications=[{"code": "metformin", "display": "Metformin 500mg"}],
            observations=[
                {"code": "hba1c", "value": float(50 + i), "unit": "mmol/mol"},
                {"code": "egfr", "value": 80.0, "unit": "mL/min/1.73m2"},
            ],
        ))

    # 11-20: T2DM + CKD → metformin contraindication
    for i in range(1, 11):
        sid += 1
        egfr_val = 19 + i
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"T2DM CKD4 eGFR={egfr_val} metformin contraindicated",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=60 + i, patient_gender="male",
            chief_complaint="diabetes review",
            conditions=[
                {"code": "type_2_diabetes", "display": "Type 2 diabetes"},
                {"code": "ckd_stage_4", "display": "CKD Stage 4"},
            ],
            medications=[
                {"code": "metformin", "display": "Metformin 1g"},
                {"code": "gliclazide", "display": "Gliclazide 80mg"},
            ],
            observations=[
                {"code": "hba1c", "value": float(65 + i), "unit": "mmol/mol"},
                {"code": "egfr", "value": float(egfr_val), "unit": "mL/min/1.73m2"},
            ],
            expected_modifications=["contraindication_flagged", "activity_added"],
        ))

    # 21-30: T2DM + foot ulcer → MDT referral
    for i in range(1, 11):
        sid += 1
        hba1c_val = 60 + i * 3
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"T2DM active foot ulcer MDT referral HbA1c={hba1c_val}",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=55 + i, patient_gender="male" if i % 3 != 0 else "female",
            chief_complaint="foot ulcer review",
            conditions=[
                {"code": "type_2_diabetes", "display": "Type 2 diabetes"},
                {"code": "diabetic_foot_ulcer", "display": "Active diabetic foot ulcer"},
            ],
            medications=[
                {"code": "metformin", "display": "Metformin 1g"},
                {"code": "atorvastatin", "display": "Atorvastatin 80mg"},
            ],
            observations=[
                {"code": "hba1c", "value": float(hba1c_val), "unit": "mmol/mol"},
                {"code": "egfr", "value": 55.0, "unit": "mL/min/1.73m2"},
            ],
            expected_modifications=["activity_added", "urgency_elevated"],
        ))

    # 31-40: T2DM at glycaemic target
    for i in range(1, 11):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"T2DM at target HbA1c={42+i%5} annual review",
            testtype="Positive", priority="P2",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=45 + i, patient_gender="female" if i % 2 == 0 else "male",
            chief_complaint="annual review",
            conditions=[{"code": "type_2_diabetes", "display": "Type 2 diabetes"}],
            medications=[{"code": "metformin", "display": "Metformin 500mg"}],
            observations=[
                {"code": "hba1c", "value": float(42 + i % 5), "unit": "mmol/mol"},
                {"code": "egfr", "value": 90.0, "unit": "mL/min/1.73m2"},
            ],
        ))

    # 41-45: Suspected sepsis — red flag
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Sepsis red flag hypotension BP={80+i} lactate={2.5+i*0.3:.1f}",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng51-sepsis",
            patient_age=55 + i * 3, patient_gender="female" if i % 2 == 0 else "male",
            chief_complaint="fever",
            conditions=[{"code": "pneumonia", "display": "Pneumonia"}],
            observations=[{"code": "lactate", "value": round(2.5 + i * 0.3, 1), "unit": "mmol/L"}],
            vital_signs={
                "heart_rate": 115 + i * 5,
                "systolic_bp": 80 + i,
                "temperature": round(38.5 + i * 0.2, 1),
                "respiratory_rate": 22 + i,
                "spo2": 94 - i,
            },
        ))

    # 46-50: Sepsis + penicillin allergy
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Sepsis with severe penicillin allergy alt antibiotics",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng51-sepsis",
            patient_age=45 + i * 5, patient_gender="male",
            chief_complaint="suspected infection",
            conditions=[{"code": "urinary_tract_infection", "display": "UTI"}],
            allergies=[{"substance": "penicillin", "category": "medication", "reaction": "anaphylaxis", "severity": "severe"}],
            observations=[{"code": "lactate", "value": 2.2, "unit": "mmol/L"}],
            vital_signs={
                "heart_rate": 100, "systolic_bp": 95,
                "temperature": 38.8, "respiratory_rate": 20, "spo2": 96,
            },
            expected_modifications=["contraindication_flagged"],
        ))

    # 51-55: Sepsis + HF → cautious fluids
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Sepsis with HF cautious fluid resuscitation",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng51-sepsis",
            patient_age=70 + i, patient_gender="male" if i <= 3 else "female",
            chief_complaint="fever",
            conditions=[
                {"code": "pneumonia", "display": "Pneumonia"},
                {"code": "heart_failure", "display": "Chronic heart failure"},
            ],
            medications=[
                {"code": "ramipril", "display": "Ramipril 5mg"},
                {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
                {"code": "furosemide", "display": "Furosemide 40mg"},
            ],
            observations=[{"code": "lactate", "value": 3.0, "unit": "mmol/L"}],
            vital_signs={
                "heart_rate": 110, "systolic_bp": 88,
                "temperature": 39.0, "respiratory_rate": 24, "spo2": 92,
            },
            expected_modifications=["safety_override"],
        ))

    # 56-60: Sepsis + immunocompromised
    for i in range(1, 6):
        sid += 1
        immuno = ["immunocompromised", "chemotherapy", "organ_transplant", "hiv", "immunosuppression"]
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Sepsis immunocompromised ({immuno[i-1]}) escalation",
            testtype="Positive", priority="P0",
            pathway_id="nice-ng51-sepsis",
            patient_age=50 + i * 4, patient_gender="female" if i % 2 == 0 else "male",
            chief_complaint="fever",
            conditions=[{"code": immuno[i - 1], "display": immuno[i - 1].replace("_", " ").title()}],
            observations=[{"code": "lactate", "value": round(1.8 + i * 0.2, 1), "unit": "mmol/L"}],
            vital_signs={
                "heart_rate": 95 + i * 5, "systolic_bp": 100,
                "temperature": 38.3, "respiratory_rate": 18, "spo2": 97,
            },
            expected_modifications=["intensity_increased", "urgency_elevated"],
        ))

    # 61-65: Sepsis amber flag
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Sepsis amber flag moderate risk workup",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng51-sepsis",
            patient_age=40 + i * 5, patient_gender="male",
            chief_complaint="fever",
            conditions=[{"code": "cellulitis", "display": "Cellulitis"}],
            observations=[{"code": "lactate", "value": 1.5, "unit": "mmol/L"}],
            vital_signs={
                "heart_rate": 95, "systolic_bp": 105,
                "temperature": 38.5, "respiratory_rate": 18, "spo2": 97,
            },
        ))

    # 66-70: Sepsis low risk
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Sepsis low risk standard community management",
            testtype="Positive", priority="P2",
            pathway_id="nice-ng51-sepsis",
            patient_age=30 + i * 5, patient_gender="female",
            chief_complaint="suspected infection",
            conditions=[{"code": "uti", "display": "UTI"}],
            vital_signs={
                "heart_rate": 80, "systolic_bp": 120,
                "temperature": 37.8, "respiratory_rate": 16, "spo2": 98,
            },
        ))

    # 71-75: T2DM + statin allergy
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"T2DM with statin allergy CV risk management",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=52 + i, patient_gender="male" if i <= 3 else "female",
            chief_complaint="diabetes review",
            conditions=[
                {"code": "type_2_diabetes", "display": "Type 2 diabetes"},
                {"code": "hypertension", "display": "Hypertension"},
            ],
            medications=[
                {"code": "metformin", "display": "Metformin 500mg"},
                {"code": "ramipril", "display": "Ramipril 10mg"},
            ],
            allergies=[{"substance": "statin", "category": "medication", "reaction": "myalgia", "severity": "moderate"}],
            observations=[
                {"code": "hba1c", "value": 55.0, "unit": "mmol/mol"},
                {"code": "egfr", "value": 70.0, "unit": "mL/min/1.73m2"},
            ],
        ))

    # 76-80: T2DM + polypharmacy
    for i in range(1, 6):
        sid += 1
        med_count = 10 + i
        meds = [{"code": f"med_{j}", "display": f"Medication {j}"} for j in range(med_count)]
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"T2DM polypharmacy ({med_count} meds) review trigger",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=68 + i, patient_gender="female",
            chief_complaint="diabetes review",
            conditions=[
                {"code": "type_2_diabetes", "display": "Type 2 diabetes"},
                {"code": "hypertension", "display": "Hypertension"},
                {"code": "osteoarthritis", "display": "Osteoarthritis"},
            ],
            medications=meds,
            observations=[
                {"code": "hba1c", "value": 60.0, "unit": "mmol/mol"},
                {"code": "egfr", "value": 55.0, "unit": "mL/min/1.73m2"},
            ],
            expected_modifications=["sequence_changed"],
        ))

    # 81-85: T2DM newly diagnosed
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"T2DM newly diagnosed HbA1c={55+i*2} initial management",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=35 + i * 3, patient_gender="male" if i % 2 == 0 else "female",
            chief_complaint="new diagnosis",
            conditions=[{"code": "type_2_diabetes", "display": "Type 2 diabetes"}],
            observations=[
                {"code": "hba1c", "value": float(55 + i * 2), "unit": "mmol/mol"},
                {"code": "egfr", "value": 95.0, "unit": "mL/min/1.73m2"},
            ],
        ))

    # ── NEGATIVE (10) ────────────────────────────────────────────

    # 86-90: Paediatric on T2DM pathway
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-NEG-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Paediatric age {12+i} on adult T2DM pathway",
            testtype="Negative", priority="P2",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=12 + i, patient_gender="male",
            chief_complaint="polyuria",
            observations=[{"code": "hba1c", "value": 65.0, "unit": "mmol/mol"}],
            notes="Paediatric patient — adult T2DM pathway may not apply",
        ))

    # 91-95: Sepsis — normal vitals, no infection
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"DM-NEG-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Normal vitals no infection markers on sepsis pathway",
            testtype="Negative", priority="P2",
            pathway_id="nice-ng51-sepsis",
            patient_age=30 + i * 5, patient_gender="female",
            chief_complaint="headache",
            vital_signs={
                "heart_rate": 72, "systolic_bp": 125,
                "temperature": 36.8, "respiratory_rate": 14, "spo2": 99,
            },
            notes="No infection markers — sepsis pathway not indicated",
        ))

    # ── EDGE CASES (5) ───────────────────────────────────────────

    # 96: T2DM + CKD5 + foot ulcer + very high HbA1c
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"DM-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="T2DM CKD5 foot ulcer HbA1c=95 max complexity",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng28-diabetes-type2",
        patient_age=72, patient_gender="male",
        chief_complaint="foot ulcer review",
        conditions=[
            {"code": "type_2_diabetes", "display": "Type 2 diabetes"},
            {"code": "ckd_stage_5", "display": "CKD Stage 5"},
            {"code": "diabetic_foot_ulcer", "display": "Active diabetic foot ulcer"},
        ],
        medications=[
            {"code": "metformin", "display": "Metformin 1g"},
            {"code": "gliclazide", "display": "Gliclazide 80mg"},
            {"code": "ramipril", "display": "Ramipril 10mg"},
            {"code": "atorvastatin", "display": "Atorvastatin 80mg"},
            {"code": "aspirin", "display": "Aspirin 75mg"},
            {"code": "insulin_glargine", "display": "Insulin Glargine"},
            {"code": "omeprazole", "display": "Omeprazole 20mg"},
            {"code": "amlodipine", "display": "Amlodipine 10mg"},
            {"code": "pregabalin", "display": "Pregabalin 150mg"},
            {"code": "ferrous_sulphate", "display": "Ferrous Sulphate"},
            {"code": "doxazosin", "display": "Doxazosin 4mg"},
        ],
        allergies=[{"substance": "penicillin", "category": "medication", "reaction": "rash", "severity": "moderate"}],
        observations=[
            {"code": "hba1c", "value": 95.0, "unit": "mmol/mol"},
            {"code": "egfr", "value": 10.0, "unit": "mL/min/1.73m2"},
            {"code": "potassium", "value": 5.8, "unit": "mmol/L"},
        ],
        frailty_score="severe",
        expected_modifications=["contraindication_flagged", "activity_added", "urgency_elevated", "safety_override", "intensity_reduced"],
        expected_safety_alerts=["critical_egfr", "high_potassium"],
    ))

    # 97: Sepsis + septic shock (lactate > 4)
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"DM-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Septic shock lactate=5.5 BP=70 consciousness V",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng51-sepsis",
        patient_age=65, patient_gender="female",
        chief_complaint="confusion",
        conditions=[{"code": "pneumonia", "display": "Pneumonia"}],
        observations=[{"code": "lactate", "value": 5.5, "unit": "mmol/L"}],
        vital_signs={
            "heart_rate": 140, "systolic_bp": 70,
            "temperature": 39.5, "respiratory_rate": 30,
            "spo2": 88, "consciousness": "responds_to_voice",
        },
        expected_modifications=["urgency_elevated"],
        expected_safety_alerts=["critical_lactate"],
    ))

    # 98: Sepsis + HF + penicillin allergy + immunocompromised
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"DM-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Sepsis HF immunocompromised penicillin allergy compound risk",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng51-sepsis",
        patient_age=58, patient_gender="male",
        chief_complaint="fever",
        conditions=[
            {"code": "pneumonia", "display": "Pneumonia"},
            {"code": "heart_failure", "display": "Chronic heart failure"},
            {"code": "immunocompromised", "display": "Immunocompromised"},
        ],
        medications=[
            {"code": "ramipril", "display": "Ramipril 5mg"},
            {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
            {"code": "prednisolone", "display": "Prednisolone 5mg"},
        ],
        allergies=[{"substance": "penicillin", "category": "medication", "reaction": "anaphylaxis", "severity": "severe"}],
        observations=[{"code": "lactate", "value": 3.8, "unit": "mmol/L"}],
        vital_signs={
            "heart_rate": 125, "systolic_bp": 82,
            "temperature": 39.2, "respiratory_rate": 26, "spo2": 91,
        },
        expected_modifications=["safety_override", "contraindication_flagged", "intensity_increased", "urgency_elevated"],
    ))

    # 99: T2DM — critical hypokalaemia
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"DM-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="T2DM critical hypokalaemia K+=2.8",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng28-diabetes-type2",
        patient_age=55, patient_gender="female",
        chief_complaint="diabetes review",
        conditions=[{"code": "type_2_diabetes", "display": "Type 2 diabetes"}],
        medications=[
            {"code": "metformin", "display": "Metformin 500mg"},
            {"code": "gliclazide", "display": "Gliclazide 80mg"},
            {"code": "furosemide", "display": "Furosemide 40mg"},
        ],
        observations=[
            {"code": "hba1c", "value": 62.0, "unit": "mmol/mol"},
            {"code": "egfr", "value": 50.0, "unit": "mL/min/1.73m2"},
            {"code": "potassium", "value": 2.8, "unit": "mmol/L"},
        ],
        expected_modifications=["safety_override"],
        expected_safety_alerts=["critical_potassium"],
    ))

    # 100: T2DM — minimal data
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"DM-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="T2DM minimal data no observations unknown gender",
        testtype="Edge", priority="P2",
        pathway_id="nice-ng28-diabetes-type2",
        patient_age=42, patient_gender="unknown",
        chief_complaint="",
        conditions=[{"code": "type_2_diabetes", "display": "Type 2 diabetes"}],
    ))

    return scenarios


# ════════════════════════════════════════════════════════════════════
# FILE 3: Maternal + Cross-Pathway (100 scenarios)
# ════════════════════════════════════════════════════════════════════

def generate_maternal_cross() -> list[dict]:
    scenarios = []
    sid = 0

    # ── POSITIVE (85) ────────────────────────────────────────────

    # 1-10: Simple low-risk pregnancy
    for i in range(1, 11):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Low-risk pregnancy booking age {22+i}",
            testtype="Positive", priority="P1",
            pathway_id="who-maternal-anc",
            patient_age=22 + i, patient_gender="female",
            chief_complaint="pregnancy booking",
            conditions=[{"code": "pregnancy", "display": "Pregnancy"}],
            medications=[{"code": "folic_acid", "display": "Folic Acid 400mcg"}],
            observations=[{"code": "bmi", "value": float(22 + i), "unit": "kg/m2"}],
        ))

    # 11-20: Pregnancy + advanced maternal age
    for i in range(1, 11):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Advanced maternal age {40+i} increased monitoring",
            testtype="Positive", priority="P0",
            pathway_id="who-maternal-anc",
            patient_age=40 + i, patient_gender="female",
            chief_complaint="pregnancy booking",
            conditions=[{"code": "pregnancy", "display": "Pregnancy"}],
            medications=[{"code": "folic_acid", "display": "Folic Acid 400mcg"}],
            observations=[{"code": "bmi", "value": float(25 + i), "unit": "kg/m2"}],
            expected_modifications=["intensity_increased"],
        ))

    # 21-30: Pregnancy + pre-eclampsia history
    for i in range(1, 11):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Pregnancy pre-eclampsia history high-risk ANC",
            testtype="Positive", priority="P0",
            pathway_id="who-maternal-anc",
            patient_age=28 + i, patient_gender="female",
            chief_complaint="pregnancy booking",
            conditions=[
                {"code": "pregnancy", "display": "Pregnancy"},
                {"code": "pre_eclampsia", "display": "Previous pre-eclampsia"},
            ],
            medications=[{"code": "folic_acid", "display": "Folic Acid 400mcg"}],
            observations=[{"code": "bmi", "value": float(24 + i), "unit": "kg/m2"}],
            expected_modifications=["activity_added", "intensity_increased"],
        ))

    # 31-35: Pregnancy + GDM
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Pregnancy gestational diabetes BMI={35+i}",
            testtype="Positive", priority="P1",
            pathway_id="who-maternal-anc",
            patient_age=33 + i, patient_gender="female",
            chief_complaint="pregnancy booking",
            conditions=[
                {"code": "pregnancy", "display": "Pregnancy"},
                {"code": "gestational_diabetes", "display": "Gestational diabetes"},
            ],
            medications=[
                {"code": "folic_acid", "display": "Folic Acid 400mcg"},
                {"code": "metformin", "display": "Metformin 500mg"},
            ],
            observations=[{"code": "bmi", "value": float(35 + i), "unit": "kg/m2"}],
        ))

    # 36-40: Pregnancy + hypertension
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Pregnancy with chronic hypertension monitoring",
            testtype="Positive", priority="P1",
            pathway_id="who-maternal-anc",
            patient_age=30 + i, patient_gender="female",
            chief_complaint="pregnancy booking",
            conditions=[
                {"code": "pregnancy", "display": "Pregnancy"},
                {"code": "hypertension", "display": "Hypertension"},
            ],
            medications=[
                {"code": "labetalol", "display": "Labetalol 100mg"},
                {"code": "folic_acid", "display": "Folic Acid 400mcg"},
            ],
            observations=[{"code": "bmi", "value": 28.0, "unit": "kg/m2"}],
        ))

    # 41-50: Cross-pathway — HF with various contexts
    for i in range(1, 11):
        sid += 1
        mods = []
        frailty = ""
        social = {}
        encounters = []
        if i <= 3:
            social = {"language_barrier": True, "interpreter_needed": True}
            mods = ["activity_added"]
            note = "language barrier"
        elif i <= 6:
            encounters = [
                {"encounter_id": f"E{j}", "encounter_type": "inpatient", "date": f"2026-0{j}-15T00:00:00", "reason": "HF exacerbation"}
                for j in range(1, 4)
            ]
            mods = ["intensity_increased"]
            note = "recurrent admissions"
        else:
            frailty = "moderate"
            mods = ["follow_up_adapted"]
            note = "moderate frailty"
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Cross-pathway HF {note}",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng106-heart-failure",
            patient_age=60 + i * 2, patient_gender="male" if i % 2 == 0 else "female",
            chief_complaint="breathlessness",
            conditions=[{"code": "heart_failure", "display": "Chronic heart failure"}],
            medications=[
                {"code": "ramipril", "display": "Ramipril 5mg"},
                {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
            ],
            observations=[{"code": "nt_pro_bnp", "value": float(900 + i * 100), "unit": "ng/L"}],
            frailty_score=frailty,
            social_history=social,
            encounters=encounters,
            expected_modifications=mods,
        ))

    # 51-60: Cross-pathway — COPD with various modifications
    for i in range(1, 11):
        sid += 1
        meds = [{"code": f"med_{j}", "display": f"Medication {j}"} for j in range(3 if i <= 5 else 12)]
        mods = [] if i <= 5 else ["sequence_changed"]
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Cross-pathway COPD {'standard' if i<=5 else 'polypharmacy'}",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng115-copd",
            patient_age=55 + i, patient_gender="male" if i <= 5 else "female",
            chief_complaint="breathlessness",
            conditions=[{"code": "copd", "display": "COPD"}],
            medications=meds,
            observations=[{"code": "fev1_percent", "value": float(50 + i), "unit": "%"}],
            expected_modifications=mods,
        ))

    # 61-65: Cross-pathway — Sepsis various presentations
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Cross-pathway sepsis varied acuity presentation",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng51-sepsis",
            patient_age=35 + i * 7, patient_gender="male" if i % 2 == 0 else "female",
            chief_complaint="fever",
            conditions=[{"code": "pneumonia", "display": "Pneumonia"}],
            observations=[{"code": "lactate", "value": round(1.5 + i * 0.3, 1), "unit": "mmol/L"}],
            vital_signs={
                "heart_rate": 90 + i * 5, "systolic_bp": 110 - i * 3,
                "temperature": round(38.0 + i * 0.2, 1),
                "respiratory_rate": 18 + i, "spo2": 96 - i,
            },
        ))

    # 66-70: Cross-pathway — T2DM stable
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Cross-pathway T2DM stable annual review",
            testtype="Positive", priority="P2",
            pathway_id="nice-ng28-diabetes-type2",
            patient_age=50 + i * 3, patient_gender="female",
            chief_complaint="annual review",
            conditions=[{"code": "type_2_diabetes", "display": "Type 2 diabetes"}],
            medications=[
                {"code": "metformin", "display": "Metformin 500mg"},
                {"code": "atorvastatin", "display": "Atorvastatin 80mg"},
            ],
            observations=[
                {"code": "hba1c", "value": float(45 + i), "unit": "mmol/mol"},
                {"code": "egfr", "value": float(75 + i), "unit": "mL/min/1.73m2"},
            ],
        ))

    # 71-75: Pregnancy + advanced age + pre-eclampsia (dual risk)
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Pregnancy age {41+i} pre-eclampsia dual risk",
            testtype="Positive", priority="P0",
            pathway_id="who-maternal-anc",
            patient_age=41 + i, patient_gender="female",
            chief_complaint="pregnancy booking",
            conditions=[
                {"code": "pregnancy", "display": "Pregnancy"},
                {"code": "pre_eclampsia", "display": "Previous pre-eclampsia"},
            ],
            medications=[
                {"code": "folic_acid", "display": "Folic Acid 400mcg"},
                {"code": "aspirin", "display": "Aspirin 150mg"},
            ],
            observations=[{"code": "bmi", "value": float(30 + i), "unit": "kg/m2"}],
            expected_modifications=["intensity_increased", "activity_added"],
        ))

    # 76-80: Cross-pathway — HF + allergy (non-penicillin)
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Cross-pathway HF with aspirin allergy",
            testtype="Positive", priority="P1",
            pathway_id="nice-ng106-heart-failure",
            patient_age=58 + i * 2, patient_gender="male",
            chief_complaint="breathlessness",
            conditions=[{"code": "heart_failure", "display": "Chronic heart failure"}],
            medications=[{"code": "ramipril", "display": "Ramipril 5mg"}],
            allergies=[{"substance": "aspirin", "category": "medication", "reaction": "urticaria", "severity": "mild"}],
            observations=[{"code": "nt_pro_bnp", "value": float(600 + i * 100), "unit": "ng/L"}],
        ))

    # 81-85: Pregnancy multiparous standard
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-POS-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Multiparous pregnancy standard ANC",
            testtype="Positive", priority="P2",
            pathway_id="who-maternal-anc",
            patient_age=28 + i, patient_gender="female",
            chief_complaint="pregnancy booking",
            conditions=[{"code": "pregnancy", "display": "Pregnancy"}],
            medications=[
                {"code": "folic_acid", "display": "Folic Acid 400mcg"},
                {"code": "vitamin_d", "display": "Vitamin D 1000IU"},
            ],
            observations=[{"code": "bmi", "value": float(23 + i), "unit": "kg/m2"}],
        ))

    # ── NEGATIVE (10) ────────────────────────────────────────────

    # 86-90: Non-pregnant patient on maternal pathway
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-NEG-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Non-pregnant female on maternal ANC pathway",
            testtype="Negative", priority="P2",
            pathway_id="who-maternal-anc",
            patient_age=25 + i, patient_gender="female",
            chief_complaint="abdominal pain",
            notes="No pregnancy condition — maternal pathway not appropriate",
        ))

    # 91-95: Male patient on maternal pathway
    for i in range(1, 6):
        sid += 1
        scenarios.append(_scenario(
            usecaseid=f"MAT-NEG-{sid:03d}", component="PathwayPersonaliser",
            scenario=f"Male patient on maternal ANC pathway",
            testtype="Negative", priority="P2",
            pathway_id="who-maternal-anc",
            patient_age=30 + i, patient_gender="male",
            chief_complaint="abdominal pain",
            notes="Male patient — maternal pathway not applicable",
        ))

    # ── EDGE CASES (5) ───────────────────────────────────────────

    # 96: Pregnancy age 50 + multiple comorbidities
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"MAT-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Pregnancy age 50 GDM HTN pre-eclampsia max complexity",
        testtype="Edge", priority="P0",
        pathway_id="who-maternal-anc",
        patient_age=50, patient_gender="female",
        chief_complaint="pregnancy booking",
        conditions=[
            {"code": "pregnancy", "display": "Pregnancy"},
            {"code": "pre_eclampsia", "display": "Previous pre-eclampsia"},
            {"code": "gestational_diabetes", "display": "Gestational diabetes"},
            {"code": "hypertension", "display": "Hypertension"},
        ],
        medications=[
            {"code": "labetalol", "display": "Labetalol 200mg"},
            {"code": "metformin", "display": "Metformin 500mg"},
            {"code": "aspirin", "display": "Aspirin 150mg"},
            {"code": "folic_acid", "display": "Folic Acid 5mg"},
            {"code": "insulin_glargine", "display": "Insulin Glargine"},
        ],
        observations=[{"code": "bmi", "value": 42.0, "unit": "kg/m2"}],
        expected_modifications=["intensity_increased", "activity_added"],
    ))

    # 97: Patient spanning all 5 pathways
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"MAT-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Multi-domain HF-COPD-DM2-CKD spanning all pathways",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_age=70, patient_gender="male",
        chief_complaint="breathlessness",
        conditions=[
            {"code": "heart_failure", "display": "Chronic heart failure"},
            {"code": "copd", "display": "COPD"},
            {"code": "type_2_diabetes", "display": "Type 2 diabetes"},
            {"code": "ckd_stage_3", "display": "CKD Stage 3"},
        ],
        medications=[
            {"code": "ramipril", "display": "Ramipril 5mg"},
            {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
            {"code": "metformin", "display": "Metformin 500mg"},
            {"code": "salbutamol", "display": "Salbutamol"},
            {"code": "tiotropium", "display": "Tiotropium"},
            {"code": "atorvastatin", "display": "Atorvastatin 80mg"},
            {"code": "furosemide", "display": "Furosemide 40mg"},
            {"code": "spironolactone", "display": "Spironolactone 25mg"},
            {"code": "warfarin", "display": "Warfarin 5mg"},
            {"code": "omeprazole", "display": "Omeprazole 20mg"},
            {"code": "amlodipine", "display": "Amlodipine 5mg"},
            {"code": "paracetamol", "display": "Paracetamol 1g PRN"},
        ],
        allergies=[{"substance": "penicillin", "category": "medication", "reaction": "rash", "severity": "moderate"}],
        observations=[
            {"code": "egfr", "value": 38.0, "unit": "mL/min/1.73m2"},
            {"code": "nt_pro_bnp", "value": 2800.0, "unit": "ng/L"},
            {"code": "hba1c", "value": 62.0, "unit": "mmol/mol"},
            {"code": "fev1_percent", "value": 35.0, "unit": "%"},
            {"code": "potassium", "value": 5.4, "unit": "mmol/L"},
        ],
        frailty_score="severe",
        expected_modifications=["sequence_changed", "urgency_elevated", "follow_up_adapted", "intensity_reduced"],
    ))

    # 98: Triple whammy drug interaction
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"MAT-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Triple whammy ACEi+MRA+NSAID drug interaction",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng106-heart-failure",
        patient_age=68, patient_gender="female",
        chief_complaint="breathlessness",
        conditions=[
            {"code": "heart_failure", "display": "Chronic heart failure"},
            {"code": "osteoarthritis", "display": "Osteoarthritis"},
        ],
        medications=[
            {"code": "ramipril", "display": "Ramipril 5mg"},
            {"code": "spironolactone", "display": "Spironolactone 25mg"},
            {"code": "ibuprofen", "display": "Ibuprofen 400mg"},
            {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
        ],
        observations=[
            {"code": "nt_pro_bnp", "value": 1200.0, "unit": "ng/L"},
            {"code": "egfr", "value": 55.0, "unit": "mL/min/1.73m2"},
        ],
        expected_modifications=["safety_override"],
        expected_safety_alerts=["triple_whammy_interaction"],
    ))

    # 99: Empty everything — absolute minimum context
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"MAT-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Absolute minimum context no data",
        testtype="Edge", priority="P2",
        pathway_id="nice-ng106-heart-failure",
        patient_age=50, patient_gender="unknown",
        chief_complaint="",
    ))

    # 100: Maximum acuity sepsis with every complication
    sid += 1
    scenarios.append(_scenario(
        usecaseid=f"MAT-EDGE-{sid:03d}", component="PathwayPersonaliser",
        scenario="Maximum acuity sepsis HF immunocompromised CKD4 all risks",
        testtype="Edge", priority="P0",
        pathway_id="nice-ng51-sepsis",
        patient_age=78, patient_gender="male",
        chief_complaint="confusion",
        conditions=[
            {"code": "pneumonia", "display": "Pneumonia"},
            {"code": "heart_failure", "display": "Chronic heart failure"},
            {"code": "immunocompromised", "display": "Immunocompromised"},
            {"code": "ckd_stage_4", "display": "CKD Stage 4"},
        ],
        medications=[
            {"code": "ramipril", "display": "Ramipril 5mg"},
            {"code": "bisoprolol", "display": "Bisoprolol 5mg"},
            {"code": "prednisolone", "display": "Prednisolone 5mg"},
            {"code": "metformin", "display": "Metformin 500mg"},
            {"code": "furosemide", "display": "Furosemide 40mg"},
        ],
        allergies=[{"substance": "penicillin", "category": "medication", "reaction": "anaphylaxis", "severity": "severe"}],
        observations=[
            {"code": "lactate", "value": 6.0, "unit": "mmol/L"},
            {"code": "egfr", "value": 18.0, "unit": "mL/min/1.73m2"},
            {"code": "potassium", "value": 6.5, "unit": "mmol/L"},
        ],
        vital_signs={
            "heart_rate": 145, "systolic_bp": 65,
            "temperature": 40.1, "respiratory_rate": 32,
            "spo2": 85, "consciousness": "responds_to_pain",
        },
        frailty_score="very_severe",
        expected_modifications=["safety_override", "contraindication_flagged", "intensity_increased", "urgency_elevated"],
        expected_safety_alerts=["critical_lactate", "critical_egfr", "critical_potassium"],
    ))

    return scenarios


def write_json(filename: str, scenarios: list[dict]) -> None:
    filepath = SCENARIOS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2, ensure_ascii=False)

    # Validate counts
    pos = sum(1 for s in scenarios if s["testtype"] == "Positive")
    neg = sum(1 for s in scenarios if s["testtype"] == "Negative")
    edge = sum(1 for s in scenarios if s["testtype"] == "Edge")
    total = len(scenarios)
    print(f"  {filename}: {total} scenarios (Positive={pos}, Negative={neg}, Edge={edge})")
    assert total == 100, f"Expected 100 scenarios, got {total}"
    assert pos == 85, f"Expected 85 positive, got {pos}"
    assert neg == 10, f"Expected 10 negative, got {neg}"
    assert edge == 5, f"Expected 5 edge, got {edge}"


def main():
    print("Generating clinical pathway test scenarios (JSON format)...")
    write_json("scenarios_heart_failure_copd.json", generate_hf_copd())
    write_json("scenarios_diabetes_sepsis.json", generate_dm_sepsis())
    write_json("scenarios_maternal_cross_pathway.json", generate_maternal_cross())
    print(f"\nAll 300 scenarios generated in {SCENARIOS_DIR}")


if __name__ == "__main__":
    main()

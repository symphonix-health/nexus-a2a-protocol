"""Generate 100 integration test scenarios for pathway-to-agent wiring.

Tests the full flow: PathwayPersonaliser → Adapters → BulletTrain agent input.

Distribution: 85 positive, 10 negative, 5 edge cases.
14-column JSON format aligned to BulletTrain reduced_json_matrices pattern.

Each scenario tests a specific adapter pathway:
  - to_diagnostic_context       (DiagnosticReasoningAgent)
  - to_treatment_context        (TreatmentRecommendationAgent)
  - to_prescribing_guard        (SafePrescribingAgent)
  - to_referral_request         (ReferralAgent)
  - to_investigation_plan       (InvestigationPlannerAgent)
  - to_imaging_request          (ImagingAgent)
  - to_discharge_plan           (DischargeAgent)
  - to_continuity_request       (ContinuityAgent)
  - to_chat_context             (ChatAssistant)
  - to_apex_risk_input          (APEXRiskStratification)
  - orchestrator.orchestrate    (Full pipeline)
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_scenarios() -> list[dict]:
    scenarios: list[dict] = []
    seq = 0

    # ════════════════════════════════════════════════════════════════════
    # POSITIVE SCENARIOS (85 total)
    # ════════════════════════════════════════════════════════════════════

    # ── Diagnostic Reasoning Agent (POS-001 to POS-010) ─────────────
    diagnostic_cases = [
        {
            "title": "HF patient — standard diagnostic routing",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 72, "gender": "male",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "HF+CKD — dual agent strategy (safety override)",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "ramipril", "status": "active"}],
            "age": 68, "gender": "female",
            "expected_strategy": "dual_agent",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "COPD — standard diagnostic with chief complaint",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [],
            "age": 65, "gender": "male",
            "chief_complaint": "worsening breathlessness",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "DM2 — diagnostic context with multiple meds",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [
                {"code": "metformin", "status": "active"},
                {"code": "gliclazide", "status": "active"},
            ],
            "age": 55, "gender": "female",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "Sepsis — urgency elevated diagnostic",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "vital_signs": {"heart_rate": 120, "systolic_bp": 85},
            "age": 45, "gender": "male",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "Sepsis + immunocompromised — critical escalation",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [
                {"code": "sepsis_suspected", "status": "active"},
                {"code": "immunocompromised", "status": "active"},
            ],
            "medications": [{"code": "prednisolone", "status": "active"}],
            "age": 58, "gender": "male",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "Maternal — standard antenatal diagnostic",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 28, "gender": "female",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "HF frail patient — diagnostic with frailty context",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "furosemide", "status": "active"}],
            "age": 85, "gender": "female",
            "frailty_score": "severe",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "COPD+CHF — multi-morbidity diagnostic",
            "pathway_id": "nice-ng115-copd",
            "conditions": [
                {"code": "copd", "status": "active"},
                {"code": "heart_failure", "status": "active"},
            ],
            "medications": [
                {"code": "salbutamol", "status": "active"},
                {"code": "bisoprolol", "status": "active"},
            ],
            "age": 70, "gender": "male",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
        {
            "title": "DM2+CKD — renal-aware diagnostic",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "ckd_stage_3", "status": "active"},
            ],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 62, "gender": "male",
            "expected_strategy": "chain_of_thought",
            "expected_keys": ["intent", "context", "patient_id", "strategy"],
        },
    ]

    for case in diagnostic_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "diagnostic_context", case,
            adapter="to_diagnostic_context",
            expected_output={
                "has_strategy": True,
                "expected_strategy": case["expected_strategy"],
                "expected_keys": case["expected_keys"],
                "context_has_pathway_id": True,
                "context_has_safety_warnings": True,
            },
        ))

    # ── Treatment Recommendation Agent (POS-011 to POS-020) ─────────
    treatment_cases = [
        {
            "title": "HF standard treatment — no contraindications",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 68, "gender": "male",
            "diagnosis": "heart failure with reduced ejection fraction",
            "expected_has_contraindications": False,
        },
        {
            "title": "HF+CKD — contraindicated medications flagged",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "spironolactone", "status": "active"}],
            "age": 75, "gender": "female",
            "diagnosis": "heart failure with CKD",
            "expected_has_contraindications": True,
        },
        {
            "title": "DM2 standard treatment context",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 52, "gender": "male",
            "diagnosis": "type 2 diabetes mellitus",
            "expected_has_contraindications": False,
        },
        {
            "title": "DM2+CKD — metformin contraindication",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 66, "gender": "female",
            "diagnosis": "type 2 diabetes with renal impairment",
            "expected_has_contraindications": True,
        },
        {
            "title": "Sepsis treatment — penicillin allergy",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "allergies": [{"substance": "penicillin", "category": "medication", "severity": "severe"}],
            "age": 40, "gender": "male",
            "diagnosis": "suspected sepsis",
            "expected_has_contraindications": True,
        },
        {
            "title": "COPD treatment with deviation register",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [{"code": "salbutamol", "status": "active"}],
            "age": 60, "gender": "female",
            "diagnosis": "COPD exacerbation",
            "expected_has_contraindications": False,
        },
        {
            "title": "Sepsis+HF — cautious fluid treatment",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [
                {"code": "sepsis_suspected", "status": "active"},
                {"code": "heart_failure", "status": "active"},
            ],
            "medications": [{"code": "furosemide", "status": "active"}],
            "age": 72, "gender": "male",
            "diagnosis": "sepsis with heart failure",
            "expected_has_contraindications": False,
        },
        {
            "title": "HF treatment — polypharmacy context",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [
                {"code": "ramipril", "status": "active"},
                {"code": "bisoprolol", "status": "active"},
                {"code": "furosemide", "status": "active"},
                {"code": "spironolactone", "status": "active"},
                {"code": "aspirin", "status": "active"},
                {"code": "atorvastatin", "status": "active"},
            ],
            "age": 78, "gender": "male",
            "diagnosis": "heart failure",
            "expected_has_contraindications": False,
        },
        {
            "title": "Maternal treatment — pre-eclampsia history",
            "pathway_id": "who-maternal-anc",
            "conditions": [
                {"code": "pregnancy", "status": "active"},
                {"code": "pre_eclampsia_history", "status": "inactive"},
            ],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 35, "gender": "female",
            "diagnosis": "pregnancy with pre-eclampsia risk",
            "expected_has_contraindications": False,
        },
        {
            "title": "COPD+CHF — comorbidity treatment context",
            "pathway_id": "nice-ng115-copd",
            "conditions": [
                {"code": "copd", "status": "active"},
                {"code": "heart_failure", "status": "active"},
            ],
            "medications": [
                {"code": "salbutamol", "status": "active"},
                {"code": "bisoprolol", "status": "active"},
            ],
            "age": 69, "gender": "male",
            "diagnosis": "COPD with heart failure",
            "expected_has_contraindications": False,
        },
    ]

    for case in treatment_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "treatment_context", case,
            adapter="to_treatment_context",
            expected_output={
                "has_diagnosis": True,
                "has_patient_context": True,
                "has_contraindication_list": True,
                "has_deviation_summary": True,
                "expected_has_contraindications": case["expected_has_contraindications"],
            },
        ))

    # ── Safe Prescribing Agent (POS-021 to POS-028) ─────────────────
    prescribing_cases = [
        {
            "title": "HF — prescribe ramipril (allowed)",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [],
            "age": 65, "gender": "male",
            "med_name": "ramipril", "dose": 5, "freq": "once daily",
            "expected_excluded": False,
        },
        {
            "title": "HF+CKD4 — prescribe spironolactone (flagged)",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [],
            "age": 70, "gender": "female",
            "med_name": "spironolactone", "dose": 25, "freq": "once daily",
            "expected_excluded": False,
        },
        {
            "title": "DM2 — prescribe metformin (allowed)",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [],
            "age": 50, "gender": "male",
            "med_name": "metformin", "dose": 500, "freq": "twice daily",
            "expected_excluded": False,
        },
        {
            "title": "DM2+CKD4 — prescribe metformin (contraindicated)",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [],
            "age": 63, "gender": "female",
            "med_name": "metformin", "dose": 500, "freq": "twice daily",
            "expected_excluded": False,
        },
        {
            "title": "Sepsis — prescribe amoxicillin (penicillin allergy)",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "allergies": [{"substance": "penicillin", "category": "medication", "severity": "severe"}],
            "age": 42, "gender": "male",
            "med_name": "amoxicillin", "dose": 500, "freq": "three times daily",
            "expected_excluded": False,
        },
        {
            "title": "COPD — prescribe salbutamol (allowed)",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [],
            "age": 58, "gender": "female",
            "med_name": "salbutamol", "dose": 100, "freq": "as needed",
            "expected_excluded": False,
        },
        {
            "title": "HF — prescribe atorvastatin (allowed)",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "ramipril", "status": "active"}],
            "age": 67, "gender": "male",
            "med_name": "atorvastatin", "dose": 20, "freq": "once daily",
            "expected_excluded": False,
        },
        {
            "title": "Maternal — prescribe aspirin (pre-eclampsia prevention)",
            "pathway_id": "who-maternal-anc",
            "conditions": [
                {"code": "pregnancy", "status": "active"},
                {"code": "pre_eclampsia_history", "status": "inactive"},
            ],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 36, "gender": "female",
            "med_name": "aspirin", "dose": 150, "freq": "once daily",
            "expected_excluded": False,
        },
    ]

    for case in prescribing_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "prescribing_guard", case,
            adapter="to_prescribing_guard",
            expected_output={
                "has_order": True,
                "has_pathway_guard": True,
                "expected_excluded": case["expected_excluded"],
            },
        ))

    # ── Referral Agent (POS-029 to POS-035) ─────────────────────────
    referral_cases = [
        {
            "title": "HF+CKD — nephrology referral",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "ramipril", "status": "active"}],
            "age": 72, "gender": "male",
        },
        {
            "title": "DM2 — foot ulcer MDT referral",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "diabetic_foot_ulcer", "status": "active"},
            ],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 64, "gender": "male",
        },
        {
            "title": "COPD+CHF — cardiology referral",
            "pathway_id": "nice-ng115-copd",
            "conditions": [
                {"code": "copd", "status": "active"},
                {"code": "heart_failure", "status": "active"},
            ],
            "medications": [{"code": "salbutamol", "status": "active"}],
            "age": 71, "gender": "female",
        },
        {
            "title": "DM2+CKD — renal referral",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "ckd_stage_3", "status": "active"},
            ],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 59, "gender": "female",
        },
        {
            "title": "HF standard — no referral needed",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 66, "gender": "male",
        },
        {
            "title": "Maternal advanced age — consultant referral",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 42, "gender": "female",
        },
        {
            "title": "Sepsis immunocompromised — ID specialist referral",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [
                {"code": "sepsis_suspected", "status": "active"},
                {"code": "immunocompromised", "status": "active"},
            ],
            "medications": [{"code": "prednisolone", "status": "active"}],
            "age": 55, "gender": "male",
        },
    ]

    for case in referral_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "referral_request", case,
            adapter="to_referral_request",
            expected_output={
                "has_patient_id": True,
                "has_pathway_id": True,
                "has_referrals_list": True,
            },
        ))

    # ── Investigation Planner (POS-036 to POS-042) ──────────────────
    investigation_cases = [
        {
            "title": "HF — BNP and echocardiogram investigations",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [],
            "age": 70, "gender": "male",
        },
        {
            "title": "DM2 — HbA1c and renal function",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 55, "gender": "female",
        },
        {
            "title": "COPD — spirometry and blood gas",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [],
            "age": 63, "gender": "male",
        },
        {
            "title": "Sepsis — blood cultures and lactate",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "age": 48, "gender": "female",
        },
        {
            "title": "Maternal — routine antenatal bloods",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 30, "gender": "female",
        },
        {
            "title": "HF+CKD — renal-safe investigation plan",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "furosemide", "status": "active"}],
            "age": 74, "gender": "female",
        },
        {
            "title": "DM2+CKD — modified investigation panel",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "ckd_stage_3", "status": "active"},
            ],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 61, "gender": "male",
        },
    ]

    for case in investigation_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "investigation_plan", case,
            adapter="to_investigation_plan",
            expected_output={
                "has_patient_context": True,
                "has_guideline_topic": True,
                "has_investigations_list": True,
            },
        ))

    # ── Discharge Agent (POS-043 to POS-049) ────────────────────────
    discharge_cases = [
        {
            "title": "HF — standard discharge plan",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 67, "gender": "male",
        },
        {
            "title": "HF frail — adapted follow-up discharge",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "furosemide", "status": "active"}],
            "age": 88, "gender": "female",
            "frailty_score": "severe",
        },
        {
            "title": "COPD — discharge with self-management plan",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [{"code": "salbutamol", "status": "active"}],
            "age": 62, "gender": "male",
        },
        {
            "title": "DM2 — discharge with monitoring schedule",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 54, "gender": "female",
        },
        {
            "title": "Sepsis — post-sepsis discharge planning",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "age": 50, "gender": "male",
        },
        {
            "title": "Transport barrier — telephone follow-up discharge",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "ramipril", "status": "active"}],
            "age": 76, "gender": "female",
            "social_history": {"transport_barrier": True},
        },
        {
            "title": "Language barrier — interpreter discharge plan",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 48, "gender": "male",
            "social_history": {"language_barrier": True, "preferred_language": "ar"},
        },
    ]

    for case in discharge_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "discharge_plan", case,
            adapter="to_discharge_plan",
            expected_output={
                "has_patient": True,
                "has_pathway_context": True,
                "has_discharge_activities": True,
            },
        ))

    # ── Continuity Agent (POS-050 to POS-055) ───────────────────────
    continuity_cases = [
        {
            "title": "HF frail — increased monitoring continuity",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "furosemide", "status": "active"}],
            "age": 84, "gender": "female",
            "frailty_score": "severe",
        },
        {
            "title": "COPD frequent exacerbator — enhanced follow-up",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [{"code": "salbutamol", "status": "active"}],
            "age": 68, "gender": "male",
            "encounters": [
                {"encounter_type": "emergency", "date": "2025-06-01"},
                {"encounter_type": "emergency", "date": "2025-09-15"},
                {"encounter_type": "emergency", "date": "2026-01-10"},
            ],
        },
        {
            "title": "DM2 — transport barrier adapted monitoring",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 72, "gender": "male",
            "social_history": {"transport_barrier": True},
        },
        {
            "title": "HF recurrent admissions — escalated continuity",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 78, "gender": "male",
            "encounters": [
                {"encounter_type": "inpatient", "date": "2025-08-01"},
                {"encounter_type": "inpatient", "date": "2025-11-15"},
                {"encounter_type": "inpatient", "date": "2026-02-01"},
            ],
        },
        {
            "title": "Maternal — antenatal continuity schedule",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 32, "gender": "female",
        },
        {
            "title": "HF standard — no monitoring changes",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 60, "gender": "male",
        },
    ]

    for case in continuity_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "continuity_request", case,
            adapter="to_continuity_request",
            expected_output={
                "has_task_type": True,
                "has_patient_id": True,
                "has_context": True,
            },
        ))

    # ── Chat Assistant (POS-056 to POS-060) ─────────────────────────
    chat_cases = [
        {
            "title": "HF — full chat context with deviations",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "ramipril", "status": "active"}],
            "age": 73, "gender": "male",
        },
        {
            "title": "DM2 — standard chat context",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 52, "gender": "female",
        },
        {
            "title": "Sepsis — safety warnings in chat",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "allergies": [{"substance": "penicillin", "category": "medication", "severity": "severe"}],
            "age": 45, "gender": "male",
        },
        {
            "title": "COPD — chat with reasoning chain",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [{"code": "salbutamol", "status": "active"}],
            "age": 61, "gender": "male",
        },
        {
            "title": "Maternal — antenatal chat context",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 29, "gender": "female",
        },
    ]

    for case in chat_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "chat_context", case,
            adapter="to_chat_context",
            expected_output={
                "has_pathway_personalisation": True,
                "has_encounter_journey_summary": True,
                "has_reasoning_chain": True,
            },
        ))

    # ── APEX Risk Stratification (POS-061 to POS-067) ───────────────
    apex_cases = [
        {
            "title": "HF high confidence — low risk modifier",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 65, "gender": "male",
            "expected_risk_modifier": 0.0,
        },
        {
            "title": "HF+CKD medium confidence — elevated risk",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "ramipril", "status": "active"}],
            "age": 71, "gender": "female",
            "expected_risk_modifier": 0.15,
        },
        {
            "title": "DM2 standard — no risk elevation",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 53, "gender": "male",
            "expected_risk_modifier": 0.0,
        },
        {
            "title": "Sepsis — safety warnings risk input",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "age": 50, "gender": "male",
            "expected_risk_modifier": 0.0,
        },
        {
            "title": "DM2+CKD — contraindication risk elevation",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 64, "gender": "female",
            "expected_risk_modifier": 0.15,
        },
        {
            "title": "COPD standard — baseline risk",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [],
            "age": 60, "gender": "male",
            "expected_risk_modifier": 0.0,
        },
        {
            "title": "Maternal — standard pregnancy risk baseline",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 28, "gender": "female",
            "expected_risk_modifier": 0.0,
        },
    ]

    for case in apex_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "apex_risk_input", case,
            adapter="to_apex_risk_input",
            expected_output={
                "has_patient_id": True,
                "has_predictors": True,
                "has_confidence_risk_modifier": True,
            },
        ))

    # ── Full Orchestrator (POS-068 to POS-085) ──────────────────────
    orchestrator_cases = [
        {
            "title": "HF standard — full pipeline",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 66, "gender": "male",
            "min_agents": 4,
        },
        {
            "title": "HF+CKD — multi-agent dispatch with safety",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "ramipril", "status": "active"}],
            "age": 74, "gender": "female",
            "min_agents": 4,
        },
        {
            "title": "DM2 — diabetes pipeline",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 51, "gender": "male",
            "min_agents": 4,
        },
        {
            "title": "COPD — respiratory pipeline",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [{"code": "salbutamol", "status": "active"}],
            "age": 59, "gender": "female",
            "min_agents": 4,
        },
        {
            "title": "Sepsis — emergency pipeline",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "age": 44, "gender": "male",
            "min_agents": 4,
        },
        {
            "title": "Maternal — antenatal pipeline",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 31, "gender": "female",
            "min_agents": 4,
        },
        {
            "title": "HF polypharmacy — medication review pipeline",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [
                {"code": "ramipril", "status": "active"},
                {"code": "bisoprolol", "status": "active"},
                {"code": "furosemide", "status": "active"},
                {"code": "spironolactone", "status": "active"},
                {"code": "aspirin", "status": "active"},
                {"code": "atorvastatin", "status": "active"},
            ],
            "age": 77, "gender": "male",
            "min_agents": 4,
        },
        {
            "title": "DM2+foot ulcer — MDT pipeline",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "diabetic_foot_ulcer", "status": "active"},
            ],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 63, "gender": "male",
            "min_agents": 4,
        },
        {
            "title": "COPD+CHF — dual-pathway pipeline",
            "pathway_id": "nice-ng115-copd",
            "conditions": [
                {"code": "copd", "status": "active"},
                {"code": "heart_failure", "status": "active"},
            ],
            "medications": [
                {"code": "salbutamol", "status": "active"},
                {"code": "bisoprolol", "status": "active"},
            ],
            "age": 69, "gender": "male",
            "min_agents": 4,
        },
        {
            "title": "Sepsis+penicillin allergy — safe pipeline",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "allergies": [{"substance": "penicillin", "category": "medication", "severity": "severe"}],
            "age": 38, "gender": "female",
            "min_agents": 4,
        },
        {
            "title": "Sepsis+HF — cautious fluid pipeline",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [
                {"code": "sepsis_suspected", "status": "active"},
                {"code": "heart_failure", "status": "active"},
            ],
            "medications": [{"code": "furosemide", "status": "active"}],
            "age": 73, "gender": "male",
            "min_agents": 4,
        },
        {
            "title": "Maternal advanced age — enhanced pipeline",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 43, "gender": "female",
            "min_agents": 4,
        },
        {
            "title": "HF frail — intensity-adapted pipeline",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "furosemide", "status": "active"}],
            "age": 86, "gender": "female",
            "frailty_score": "severe",
            "min_agents": 4,
        },
        {
            "title": "DM2+CKD — renal-safe pipeline",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [
                {"code": "diabetes_type2", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
            ],
            "medications": [{"code": "metformin", "status": "active"}],
            "age": 65, "gender": "female",
            "min_agents": 4,
        },
        {
            "title": "Sepsis immunocompromised — critical pipeline",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [
                {"code": "sepsis_suspected", "status": "active"},
                {"code": "immunocompromised", "status": "active"},
            ],
            "medications": [{"code": "prednisolone", "status": "active"}],
            "age": 56, "gender": "male",
            "min_agents": 4,
        },
        {
            "title": "HF language barrier — adapted pipeline",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 69, "gender": "male",
            "social_history": {"language_barrier": True, "preferred_language": "ur"},
            "min_agents": 4,
        },
        {
            "title": "Maternal pre-eclampsia — enhanced pipeline",
            "pathway_id": "who-maternal-anc",
            "conditions": [
                {"code": "pregnancy", "status": "active"},
                {"code": "pre_eclampsia_history", "status": "inactive"},
            ],
            "medications": [{"code": "folic_acid", "status": "active"}],
            "age": 34, "gender": "female",
            "min_agents": 4,
        },
        {
            "title": "COPD frequent exacerbator — enhanced pipeline",
            "pathway_id": "nice-ng115-copd",
            "conditions": [{"code": "copd", "status": "active"}],
            "medications": [{"code": "salbutamol", "status": "active"}],
            "age": 67, "gender": "male",
            "encounters": [
                {"encounter_type": "emergency", "date": "2025-07-01"},
                {"encounter_type": "emergency", "date": "2025-12-01"},
                {"encounter_type": "emergency", "date": "2026-02-15"},
            ],
            "min_agents": 4,
        },
    ]

    for case in orchestrator_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "POS", "orchestrator", case,
            adapter="orchestrate",
            expected_output={
                "has_pathway": True,
                "has_dispatches": True,
                "has_integrated_plan": True,
                "min_agents_dispatched": case["min_agents"],
            },
        ))

    # ════════════════════════════════════════════════════════════════════
    # NEGATIVE SCENARIOS (10 total)
    # ════════════════════════════════════════════════════════════════════

    negative_cases = [
        {
            "title": "Non-existent pathway — adapter should handle None",
            "pathway_id": "nice-ng999-nonexistent",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [],
            "age": 55, "gender": "male",
            "adapter": "orchestrate",
            "expected_error": "pathway_not_found",
        },
        {
            "title": "Empty patient context — diagnostic adapter",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [],
            "medications": [],
            "age": 50, "gender": "unknown",
            "adapter": "to_diagnostic_context",
            "expected_error": "no_conditions",
        },
        {
            "title": "No medications — prescribing guard with empty profile",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [],
            "age": 45, "gender": "male",
            "adapter": "to_prescribing_guard",
            "expected_error": "no_error_expected",
            "med_name": "unknown_drug_xyz", "dose": 100, "freq": "once daily",
        },
        {
            "title": "Inactive condition only — treatment context",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "resolved"}],
            "medications": [],
            "age": 60, "gender": "female",
            "adapter": "to_treatment_context",
            "expected_error": "no_active_conditions",
        },
        {
            "title": "Invalid allergy format — graceful handling",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "allergies": [{"substance": "", "category": "medication", "severity": "moderate"}],
            "age": 40, "gender": "male",
            "adapter": "to_treatment_context",
            "expected_error": "empty_substance",
        },
        {
            "title": "Extreme age — boundary patient (age 0)",
            "pathway_id": "nice-ng28-diabetes-type2",
            "conditions": [{"code": "diabetes_type2", "status": "active"}],
            "medications": [],
            "age": 0, "gender": "unknown",
            "adapter": "to_diagnostic_context",
            "expected_error": "boundary_age",
        },
        {
            "title": "Extreme age — boundary patient (age 120)",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [],
            "age": 120, "gender": "female",
            "adapter": "to_diagnostic_context",
            "expected_error": "boundary_age",
        },
        {
            "title": "Maximum medications — polypharmacy limit",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": f"med_{i}", "status": "active"} for i in range(20)],
            "age": 80, "gender": "male",
            "adapter": "to_treatment_context",
            "expected_error": "extreme_polypharmacy",
        },
        {
            "title": "All conditions resolved — no active pathway match",
            "pathway_id": "nice-ng115-copd",
            "conditions": [
                {"code": "copd", "status": "resolved"},
                {"code": "asthma", "status": "resolved"},
            ],
            "medications": [],
            "age": 55, "gender": "female",
            "adapter": "to_investigation_plan",
            "expected_error": "no_active_conditions",
        },
        {
            "title": "Conflicting allergies — multiple severe allergies",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "allergies": [
                {"substance": "penicillin", "category": "medication", "severity": "severe"},
                {"substance": "cephalosporin", "category": "medication", "severity": "severe"},
                {"substance": "sulfonamide", "category": "medication", "severity": "severe"},
            ],
            "age": 35, "gender": "male",
            "adapter": "to_treatment_context",
            "expected_error": "multiple_severe_allergies",
        },
    ]

    for case in negative_cases:
        seq += 1
        scenarios.append(_make_scenario(
            seq, "NEG", case["adapter"], case,
            adapter=case["adapter"],
            expected_output={
                "status": "negative_test",
                "expected_error": case["expected_error"],
                "should_not_crash": True,
            },
        ))

    # ════════════════════════════════════════════════════════════════════
    # EDGE CASE SCENARIOS (5 total)
    # ════════════════════════════════════════════════════════════════════

    edge_cases = [
        {
            "title": "All 5 pathways simultaneously — max comorbidity",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [
                {"code": "heart_failure", "status": "active"},
                {"code": "copd", "status": "active"},
                {"code": "diabetes_type2", "status": "active"},
                {"code": "ckd_stage_4", "status": "active"},
                {"code": "sepsis_suspected", "status": "active"},
            ],
            "medications": [
                {"code": "ramipril", "status": "active"},
                {"code": "bisoprolol", "status": "active"},
                {"code": "metformin", "status": "active"},
                {"code": "salbutamol", "status": "active"},
                {"code": "furosemide", "status": "active"},
            ],
            "allergies": [{"substance": "penicillin", "category": "medication", "severity": "severe"}],
            "age": 75, "gender": "male",
            "frailty_score": "severe",
            "adapter": "orchestrate",
        },
        {
            "title": "Neonatal age with maternal pathway — boundary",
            "pathway_id": "who-maternal-anc",
            "conditions": [{"code": "pregnancy", "status": "active"}],
            "medications": [],
            "age": 14, "gender": "female",
            "adapter": "to_diagnostic_context",
        },
        {
            "title": "100-year-old with every social barrier",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [
                {"code": "ramipril", "status": "active"},
                {"code": "bisoprolol", "status": "active"},
                {"code": "furosemide", "status": "active"},
            ],
            "age": 100, "gender": "female",
            "frailty_score": "very_severe",
            "social_history": {
                "language_barrier": True,
                "transport_barrier": True,
                "preferred_language": "bn",
            },
            "adapter": "orchestrate",
        },
        {
            "title": "Simultaneous allergies to all antibiotic classes",
            "pathway_id": "nice-ng51-sepsis",
            "conditions": [{"code": "sepsis_suspected", "status": "active"}],
            "medications": [],
            "allergies": [
                {"substance": "penicillin", "category": "medication", "severity": "severe"},
                {"substance": "cephalosporin", "category": "medication", "severity": "severe"},
                {"substance": "macrolide", "category": "medication", "severity": "severe"},
                {"substance": "fluoroquinolone", "category": "medication", "severity": "severe"},
            ],
            "age": 47, "gender": "female",
            "adapter": "to_treatment_context",
        },
        {
            "title": "Zero-modification pathway — no deviations",
            "pathway_id": "nice-ng106-heart-failure",
            "conditions": [{"code": "heart_failure", "status": "active"}],
            "medications": [{"code": "bisoprolol", "status": "active"}],
            "age": 60, "gender": "male",
            "adapter": "to_chat_context",
        },
    ]

    for case in edge_cases:
        seq += 1
        adapter = case.get("adapter", "orchestrate")
        scenarios.append(_make_scenario(
            seq, "EDGE", adapter, case,
            adapter=adapter,
            expected_output={
                "status": "edge_test",
                "should_not_crash": True,
                "should_produce_output": True,
            },
        ))

    return scenarios


def _make_scenario(
    seq: int,
    scenario_type: str,
    domain: str,
    case: dict,
    *,
    adapter: str,
    expected_output: dict,
) -> dict:
    """Build a single 14-column JSON scenario."""
    prefix = {"POS": "POS", "NEG": "NEG", "EDGE": "EDGE"}[scenario_type]
    scenario_id = f"INT-{prefix}-{seq:03d}"

    # Build patient context
    patient_context = {
        "demographics": {
            "patient_id": f"PAT-INT-{seq:04d}",
            "age": case.get("age", 50),
            "gender": case.get("gender", "unknown"),
        },
        "conditions": case.get("conditions", []),
        "medications": case.get("medications", []),
        "allergies": case.get("allergies", []),
        "observations": case.get("observations", []),
        "vital_signs": case.get("vital_signs", {}),
        "social_history": case.get("social_history", {}),
        "encounters": case.get("encounters", []),
        "chief_complaint": case.get("chief_complaint", ""),
    }
    if case.get("frailty_score"):
        patient_context["frailty_score"] = case["frailty_score"]

    # Build input data
    input_data = {
        "pathway_id": case["pathway_id"],
        "patient_context": patient_context,
        "adapter": adapter,
    }
    if case.get("med_name"):
        input_data["medication"] = {
            "name": case["med_name"],
            "dose_mg": case.get("dose", 100),
            "frequency": case.get("freq", "once daily"),
        }
    if case.get("diagnosis"):
        input_data["diagnosis"] = case["diagnosis"]
    if case.get("chief_complaint"):
        input_data["chief_complaint"] = case["chief_complaint"]

    return {
        "usecaseid": scenario_id,
        "poc_demo": f"integration_{domain}",
        "scenariotitle": case["title"],
        "scenariotype": scenario_type.lower(),
        "requirementids": f"INT-{domain.upper()}",
        "preconditions": f"Pathway {case['pathway_id']} loaded; patient context assembled",
        "inputdata": json.dumps(input_data),
        "transport": "in-process",
        "authmode": "service-account",
        "expectedhttpstatus": 200 if scenario_type == "POS" else (
            404 if expected_output.get("expected_error") == "pathway_not_found" else 200
        ),
        "expectedevents": json.dumps([f"{adapter}_invoked"]),
        "expectedoutcome": expected_output,
        "errorcondition": expected_output.get("expected_error", ""),
        "testtags": json.dumps([
            scenario_type.lower(),
            domain,
            adapter,
            case["pathway_id"],
        ]),
        "use_case_ref": adapter,
        "operationtype": "integration",
    }


if __name__ == "__main__":
    scenarios = generate_scenarios()

    # Validate distribution
    pos_count = sum(1 for s in scenarios if s["scenariotype"] == "pos")
    neg_count = sum(1 for s in scenarios if s["scenariotype"] == "neg")
    edge_count = sum(1 for s in scenarios if s["scenariotype"] == "edge")

    print(f"Generated {len(scenarios)} integration scenarios:")
    print(f"  Positive: {pos_count}")
    print(f"  Negative: {neg_count}")
    print(f"  Edge:     {edge_count}")

    assert len(scenarios) == 100, f"Expected 100, got {len(scenarios)}"
    assert pos_count == 85, f"Expected 85 positive, got {pos_count}"
    assert neg_count == 10, f"Expected 10 negative, got {neg_count}"
    assert edge_count == 5, f"Expected 5 edge, got {edge_count}"

    output_path = Path(__file__).parent / "scenarios" / "scenarios_integration.json"
    output_path.write_text(
        json.dumps(scenarios, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWritten to {output_path}")

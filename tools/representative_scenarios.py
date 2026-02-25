#!/usr/bin/env python3
"""Expanded representative HelixCare scenarios for realistic care coordination.

The core 25 scenarios remain the mandatory safety baseline. This module adds a
larger, generation-driven corpus to improve representativeness across:
- care settings and transfer points
- risk bands
- operational pressure contexts
- communication/accessibility support needs
- clinical handoff negative cases
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any

try:
    from helixcare_scenarios import (
        PatientScenario,
        enrich_scenario_handoff_contracts,
        run_scenario,
    )
except Exception:
    from tools.helixcare_scenarios import (
        PatientScenario,
        enrich_scenario_handoff_contracts,
        run_scenario,
    )


OPERATIONAL_CONTEXTS: list[dict[str, Any]] = [
    {
        "code": "weekday_in_hours",
        "label": "weekday in-hours",
        "staffing": "standard",
        "service_pressure": "normal",
        "delay_bias": 1,
        "variance_band": "low",
    },
    {
        "code": "weekday_overnight",
        "label": "weekday overnight",
        "staffing": "reduced",
        "service_pressure": "high",
        "delay_bias": 2,
        "variance_band": "medium",
    },
    {
        "code": "weekend_day",
        "label": "weekend daytime",
        "staffing": "reduced",
        "service_pressure": "high",
        "delay_bias": 2,
        "variance_band": "medium",
    },
    {
        "code": "winter_pressure",
        "label": "winter surge pressure",
        "staffing": "strained",
        "service_pressure": "extreme",
        "delay_bias": 3,
        "variance_band": "high",
    },
]


COMMUNICATION_PROFILES: list[dict[str, str]] = [
    {
        "code": "standard",
        "label": "Standard communication",
        "needs": "Standard verbal and written communication.",
    },
    {
        "code": "interpreter_urdu",
        "label": "Urdu interpreter",
        "needs": "Professional Urdu interpreter required for all key decisions.",
    },
    {
        "code": "bsl_interpreter",
        "label": "BSL interpreter",
        "needs": "BSL interpreter required for consent and discharge counselling.",
    },
    {
        "code": "cognitive_support",
        "label": "Cognitive support",
        "needs": "Easy-read materials with family/carer involvement required.",
    },
]


RISK_VITALS: dict[str, dict[str, Any]] = {
    "low": {
        "blood_pressure": "124/76",
        "heart_rate": 74,
        "respiratory_rate": 16,
        "oxygen_saturation": 98,
        "temperature_c": 36.7,
    },
    "medium": {
        "blood_pressure": "136/82",
        "heart_rate": 92,
        "respiratory_rate": 20,
        "oxygen_saturation": 95,
        "temperature_c": 37.3,
    },
    "high": {
        "blood_pressure": "102/64",
        "heart_rate": 116,
        "respiratory_rate": 24,
        "oxygen_saturation": 93,
        "temperature_c": 38.2,
    },
}


POSITIVE_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "slug": "ed_sepsis_alert",
        "template": "acute_admission",
        "care_setting": "ed_to_inpatient",
        "risk_band": "high",
        "persona": "emergency_physician",
        "age": 68,
        "gender": "female",
        "chief_complaint": "Fever, confusion, and low blood pressure",
        "urgency": "high",
        "symptoms": "fever, confusion, hypotension",
        "differential": ["Sepsis", "UTI", "Pneumonia"],
        "imaging_orders": ["chest_xray"],
        "med_plan": ["IV broad-spectrum antibiotics", "Fluid resuscitation"],
        "history": ["CKD stage 3", "Hypertension"],
        "receiving_team": "acute_medical_unit",
    },
    {
        "slug": "ed_acs_rulein",
        "template": "acute_admission",
        "care_setting": "ed_to_cardiology",
        "risk_band": "high",
        "persona": "emergency_physician",
        "age": 59,
        "gender": "male",
        "chief_complaint": "Crushing central chest pain",
        "urgency": "high",
        "symptoms": "chest pain radiating to jaw, diaphoresis",
        "differential": ["Acute coronary syndrome", "PE", "Aortic dissection"],
        "imaging_orders": ["ecg", "chest_xray"],
        "med_plan": ["Aspirin", "GTN", "Anticoagulation review"],
        "history": ["Hyperlipidaemia", "Type 2 diabetes"],
        "receiving_team": "cardiology_team",
    },
    {
        "slug": "ed_stroke_pathway",
        "template": "acute_admission",
        "care_setting": "ed_to_stroke_unit",
        "risk_band": "high",
        "persona": "stroke_consultant",
        "age": 74,
        "gender": "female",
        "chief_complaint": "Acute facial droop and slurred speech",
        "urgency": "high",
        "symptoms": "facial droop, unilateral weakness, dysarthria",
        "differential": ["Ischaemic stroke", "TIA", "Intracranial bleed"],
        "imaging_orders": ["ct_head"],
        "med_plan": ["Antiplatelet pathway", "BP optimisation"],
        "history": ["Atrial fibrillation", "Hypertension"],
        "receiving_team": "stroke_unit",
    },
    {
        "slug": "ed_pediatric_asthma",
        "template": "acute_admission",
        "care_setting": "ed_to_paediatric_ward",
        "risk_band": "high",
        "persona": "paediatrician",
        "age": 7,
        "gender": "male",
        "chief_complaint": "Acute wheeze with increased work of breathing",
        "urgency": "high",
        "symptoms": "wheeze, tachypnoea, accessory muscle use",
        "differential": ["Acute asthma exacerbation", "Viral wheeze"],
        "imaging_orders": ["chest_xray"],
        "med_plan": ["Nebulised bronchodilator", "Oral steroid"],
        "history": ["Known asthma", "Eczema"],
        "receiving_team": "paediatric_respiratory_team",
    },
    {
        "slug": "ed_aki_dehydration",
        "template": "acute_admission",
        "care_setting": "ed_to_renal",
        "risk_band": "medium",
        "persona": "acute_physician",
        "age": 72,
        "gender": "male",
        "chief_complaint": "Reduced urine output and dizziness",
        "urgency": "high",
        "symptoms": "oliguria, dizziness, poor oral intake",
        "differential": ["AKI", "Hypovolaemia", "Sepsis"],
        "imaging_orders": ["renal_ultrasound"],
        "med_plan": ["IV fluids", "Medication hold review"],
        "history": ["Heart failure", "CKD stage 2"],
        "receiving_team": "renal_team",
    },
    {
        "slug": "ed_oncology_neutropenic_fever",
        "template": "acute_admission",
        "care_setting": "ed_to_oncology",
        "risk_band": "high",
        "persona": "oncology_registrar",
        "age": 53,
        "gender": "female",
        "chief_complaint": "Fever after recent chemotherapy",
        "urgency": "high",
        "symptoms": "fever, rigors, mucositis",
        "differential": ["Neutropenic sepsis", "Line infection"],
        "imaging_orders": ["chest_xray"],
        "med_plan": ["Neutropenic sepsis IV antibiotics", "Fluids"],
        "history": ["Breast cancer on chemotherapy"],
        "receiving_team": "oncology_team",
    },
    {
        "slug": "inpatient_copd_d2a",
        "template": "inpatient_discharge",
        "care_setting": "inpatient_to_discharge_to_assess",
        "risk_band": "medium",
        "persona": "respiratory_consultant",
        "age": 76,
        "gender": "male",
        "chief_complaint": "COPD exacerbation recovery review",
        "urgency": "medium",
        "symptoms": "improved breathlessness post treatment",
        "differential": ["Resolved COPD exacerbation"],
        "med_plan": ["Inhaler optimisation", "Rescue pack"],
        "history": ["COPD", "Ex-smoker 40 pack-years"],
        "receiving_team": "community_respiratory_team",
        "followup_type": "respiratory",
        "followup_days": 5,
    },
    {
        "slug": "inpatient_frailty_rehab",
        "template": "inpatient_discharge",
        "care_setting": "inpatient_to_reablement",
        "risk_band": "high",
        "persona": "geriatrician",
        "age": 84,
        "gender": "female",
        "chief_complaint": "Post-fall frailty discharge planning",
        "urgency": "medium",
        "symptoms": "deconditioning and mobility decline",
        "differential": ["Frailty syndrome", "Orthostatic hypotension"],
        "med_plan": ["Falls-risk medication review"],
        "history": ["Frailty", "Mild cognitive impairment"],
        "receiving_team": "reablement_team",
        "followup_type": "frailty_clinic",
        "followup_days": 7,
    },
    {
        "slug": "inpatient_postop_recovery",
        "template": "inpatient_discharge",
        "care_setting": "surgical_ward_to_community",
        "risk_band": "medium",
        "persona": "surgical_registrar",
        "age": 46,
        "gender": "female",
        "chief_complaint": "Post-operative discharge after appendicectomy",
        "urgency": "medium",
        "symptoms": "improving pain, tolerating diet",
        "differential": ["Routine post-op recovery"],
        "med_plan": ["Analgesia taper", "Wound care plan"],
        "history": ["No major chronic conditions"],
        "receiving_team": "district_nursing_team",
        "followup_type": "surgical",
        "followup_days": 10,
    },
    {
        "slug": "inpatient_postpartum_hypertension",
        "template": "inpatient_discharge",
        "care_setting": "maternity_to_community_midwifery",
        "risk_band": "high",
        "persona": "obstetrician",
        "age": 33,
        "gender": "female",
        "chief_complaint": "Postpartum hypertension review",
        "urgency": "medium",
        "symptoms": "headache improving after BP management",
        "differential": ["Postpartum hypertension"],
        "med_plan": ["Labetalol plan", "BP monitoring instructions"],
        "history": ["Pre-eclampsia in pregnancy"],
        "receiving_team": "community_midwifery_team",
        "followup_type": "postnatal",
        "followup_days": 2,
    },
    {
        "slug": "community_diabetes_ccm",
        "template": "community_coordination",
        "care_setting": "community_to_primary",
        "risk_band": "low",
        "persona": "diabetes_specialist",
        "age": 61,
        "gender": "male",
        "chief_complaint": "Diabetes control and medication adherence",
        "urgency": "low",
        "symptoms": "suboptimal glucose logs and fatigue",
        "differential": ["Poor glycaemic control", "Medication side effects"],
        "med_plan": ["Metformin review", "GLP-1 optimisation review"],
        "history": ["Type 2 diabetes", "Hypertension"],
        "receiving_team": "primary_care_team",
        "followup_type": "diabetes_nurse",
        "followup_days": 14,
    },
    {
        "slug": "community_heart_failure_virtual_ward",
        "template": "community_coordination",
        "care_setting": "virtual_ward_to_specialty",
        "risk_band": "medium",
        "persona": "heart_failure_consultant",
        "age": 79,
        "gender": "male",
        "chief_complaint": "Heart failure symptom drift in virtual ward",
        "urgency": "medium",
        "symptoms": "weight gain and ankle swelling",
        "differential": ["Fluid overload", "Medication non-adherence"],
        "med_plan": ["Diuretic adjustment", "Renal function monitoring"],
        "history": ["Heart failure", "CKD stage 3"],
        "receiving_team": "heart_failure_team",
        "followup_type": "heart_failure",
        "followup_days": 3,
    },
    {
        "slug": "community_mental_health_relapse",
        "template": "community_coordination",
        "care_setting": "mental_health_crisis_to_community",
        "risk_band": "high",
        "persona": "psychiatrist",
        "age": 38,
        "gender": "female",
        "chief_complaint": "Anxiety relapse with sleep deprivation",
        "urgency": "high",
        "symptoms": "escalating anxiety, panic episodes, poor sleep",
        "differential": ["Anxiety relapse", "Medication withdrawal"],
        "med_plan": ["Medication reconciliation", "Crisis plan reinforcement"],
        "history": ["Generalised anxiety disorder", "Depression"],
        "receiving_team": "community_mental_health_team",
        "followup_type": "mental_health",
        "followup_days": 2,
    },
    {
        "slug": "community_palliative_home_support",
        "template": "community_coordination",
        "care_setting": "home_visit_to_palliative_support",
        "risk_band": "high",
        "persona": "palliative_consultant",
        "age": 82,
        "gender": "female",
        "chief_complaint": "Symptom control and carer support at home",
        "urgency": "medium",
        "symptoms": "pain breakthrough and reduced oral intake",
        "differential": ["Cancer pain flare", "Dehydration risk"],
        "med_plan": ["Breakthrough analgesia plan", "Antiemetic support"],
        "history": ["Metastatic cancer", "Chronic pain"],
        "receiving_team": "community_palliative_team",
        "followup_type": "palliative",
        "followup_days": 2,
    },
]


NEGATIVE_ARCHETYPES: list[dict[str, str]] = [
    {
        "slug": "missing_discharge_summary",
        "care_setting": "inpatient_to_discharge_to_assess",
        "expected_escalation": "unsafe_discharge_prevented",
        "expected_safe_outcome": "block_until_discharge_summary_present",
    },
    {
        "slug": "med_rec_incomplete",
        "care_setting": "inpatient_to_discharge_to_assess",
        "expected_escalation": "unsafe_discharge_prevented",
        "expected_safe_outcome": "block_until_medication_reconciliation_complete",
    },
    {
        "slug": "handover_missing_outstanding_tests",
        "care_setting": "ed_to_inpatient",
        "expected_escalation": "missing_handover_contract",
        "expected_safe_outcome": "block_until_outstanding_test_owner_assigned",
    },
    {
        "slug": "no_senior_escalation_after_deterioration",
        "care_setting": "inpatient_to_discharge_to_assess",
        "expected_escalation": "senior_review_required",
        "expected_safe_outcome": "block_discharge_and_trigger_urgent_review",
    },
    {
        "slug": "communication_needs_not_met",
        "care_setting": "inpatient_to_discharge_to_assess",
        "expected_escalation": "missing_handover_contract",
        "expected_safe_outcome": "block_until_accessibility_needs_documented",
    },
    {
        "slug": "followup_not_arranged",
        "care_setting": "discharge_to_community_followup",
        "expected_escalation": "unsafe_discharge_prevented",
        "expected_safe_outcome": "block_until_followup_responsibility_assigned",
    },
]


NEGATIVE_CONTEXT_CODES = ("weekday_overnight", "weekend_day", "winter_pressure")


def _future(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()


def _stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _step(
    agent: str,
    method: str,
    params: dict[str, Any],
    *,
    delay: int = 1,
    handoff_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    step: dict[str, Any] = {
        "agent": agent,
        "method": method,
        "params": params,
        "delay": delay,
    }
    if handoff_policy:
        step["handoff_policy"] = handoff_policy
    return step


def _policy(
    required_predecessors: list[str],
    rationale: str,
    *,
    optional_predecessors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "required_predecessors": required_predecessors,
        "optional_predecessors": optional_predecessors or [],
        "criticality": "clinical",
        "fallback_mode": "block_escalate",
        "max_wait_seconds": 900,
        "clinical_rationale": rationale,
    }


def _handover_payload(
    blueprint: dict[str, Any],
    context: dict[str, Any],
    communication: dict[str, str],
    *,
    recommendation: str,
    outstanding_tasks: list[str],
) -> dict[str, Any]:
    return {
        "situation": f"{blueprint['chief_complaint']} during {context['label']} operations.",
        "background": (
            f"{blueprint['description'] if 'description' in blueprint else blueprint['chief_complaint']}; "
            f"risk band {blueprint['risk_band']}."
        ),
        "assessment": f"Current assessment supports {blueprint['care_setting']} transition.",
        "recommendation": recommendation,
        "plan": f"Continue pathway ownership with {blueprint['receiving_team']}.",
        "outstanding_tasks": outstanding_tasks,
        "communication_needs": communication["needs"],
    }


def _scenario_profile(
    *,
    name: str,
    context: dict[str, Any],
    risk_band: str,
    care_setting: str,
    communication_code: str,
    scenario_class: str,
    failure_mode: str | None = None,
) -> dict[str, Any]:
    axes: dict[str, Any] = {
        "operational_context": context["code"],
        "risk_band": risk_band,
        "care_setting": care_setting,
        "communication_profile": communication_code,
        "scenario_class": scenario_class,
    }
    if failure_mode:
        axes["failure_mode"] = failure_mode
    return {
        "seed": _stable_seed(name),
        "variance_band": context["variance_band"],
        "allowed_branches": ["nominal", "handoff_delay", "context_gap", "staffing_delay"],
        "representative_axes": axes,
    }


def _patient_profile(
    blueprint: dict[str, Any],
    context: dict[str, Any],
    communication: dict[str, str],
) -> dict[str, Any]:
    profile = {
        "age": blueprint["age"],
        "gender": blueprint["gender"],
        "chief_complaint": blueprint["chief_complaint"],
        "urgency": blueprint["urgency"],
        "operational_context": context["code"],
        "service_pressure": context["service_pressure"],
        "communication_profile": communication["code"],
        "communication_support": communication["needs"],
        "vital_signs": dict(RISK_VITALS[blueprint["risk_band"]]),
    }
    return profile


def _medical_history(
    blueprint: dict[str, Any],
    communication: dict[str, str],
) -> dict[str, Any]:
    return {
        "past_medical_history": list(blueprint["history"]),
        "medications": list(blueprint["med_plan"]),
        "allergies": ["No known drug allergies"],
        "communication_needs": communication["needs"],
    }

def _acute_admission_steps(
    blueprint: dict[str, Any],
    context: dict[str, Any],
    communication: dict[str, str],
) -> list[dict[str, Any]]:
    delay = int(context["delay_bias"])
    handover = _handover_payload(
        blueprint,
        context,
        communication,
        recommendation=f"Escalate to {blueprint['receiving_team']} for active management.",
        outstanding_tasks=["Confirm outstanding labs ownership", "Acknowledge receiving team handoff"],
    )
    return [
        _step(
            "triage",
            "tasks/sendSubscribe",
            {
                "symptoms": blueprint["symptoms"],
                "chief_complaint": blueprint["chief_complaint"],
                "operational_context": context["code"],
                "communication_support": communication["needs"],
                "vital_signs": dict(RISK_VITALS[blueprint["risk_band"]]),
            },
            delay=delay,
        ),
        _step(
            "clinician_avatar",
            "avatar/start_session",
            {
                "patient_case": {
                    "chief_complaint": blueprint["chief_complaint"],
                    "age": blueprint["age"],
                    "gender": blueprint["gender"],
                    "urgency": blueprint["urgency"],
                    "communication_needs": communication["needs"],
                },
                "persona": blueprint["persona"],
            },
            delay=delay,
            handoff_policy=_policy(["triage"], "Senior review starts after triage prioritisation."),
        ),
        _step(
            "diagnosis",
            "tasks/sendSubscribe",
            {
                "symptoms": blueprint["symptoms"],
                "differential_diagnosis": list(blueprint["differential"]),
            },
            delay=delay,
            handoff_policy=_policy(
                ["clinician_avatar"],
                "Diagnostic reasoning follows clinician interview and triage context.",
            ),
        ),
        _step(
            "imaging",
            "tasks/sendSubscribe",
            {"orders": [{"type": order, "priority": "urgent"} for order in blueprint["imaging_orders"]]},
            delay=delay,
            handoff_policy=_policy(["diagnosis"], "Urgent imaging requested after diagnostic review."),
        ),
        _step(
            "pharmacy",
            "pharmacy/recommend",
            {
                "task": {
                    "med_plan": list(blueprint["med_plan"]),
                    "allergies": ["No known drug allergies"],
                }
            },
            delay=delay,
            handoff_policy=_policy(["diagnosis"], "Medication plan reconciled against diagnosis."),
        ),
        _step(
            "bed_manager",
            "tasks/sendSubscribe",
            {
                "task": {
                    "admission_type": "emergency",
                    "required_monitoring": "enhanced",
                    "special_requirements": [blueprint["receiving_team"]],
                },
                "care_transition": {
                    "handover_owner": "ed_registrar",
                    "receiving_team": blueprint["receiving_team"],
                    "followup_responsibility": blueprint["receiving_team"],
                    "receiving_provider_notified": True,
                    "handover": handover,
                },
            },
            delay=delay,
            handoff_policy=_policy(
                ["diagnosis"],
                "Admission handoff must include structured transfer details.",
                optional_predecessors=["imaging", "pharmacy"],
            ),
        ),
        _step(
            "specialty_care",
            "tasks/sendSubscribe",
            {
                "task": {
                    "specialty": blueprint["receiving_team"],
                    "priority": "urgent",
                    "indication": blueprint["chief_complaint"],
                }
            },
            delay=delay,
            handoff_policy=_policy(["bed_manager"], "Receiving specialty assumes ownership after admission handoff."),
        ),
        _step(
            "coordinator",
            "tasks/sendSubscribe",
            {
                "task": {
                    "pathway": blueprint["care_setting"],
                    "operational_context": context["code"],
                },
                "care_transition": {
                    "handover_owner": "care_coordinator",
                    "receiving_team": blueprint["receiving_team"],
                    "followup_responsibility": blueprint["receiving_team"],
                    "receiving_provider_notified": True,
                    "handover": handover,
                },
            },
            delay=delay,
            handoff_policy=_policy(
                ["specialty_care"],
                "Care coordinator confirms transfer ownership and outstanding tasks.",
            ),
        ),
    ]


def _inpatient_discharge_steps(
    blueprint: dict[str, Any],
    context: dict[str, Any],
    communication: dict[str, str],
) -> list[dict[str, Any]]:
    delay = int(context["delay_bias"])
    handover = _handover_payload(
        blueprint,
        context,
        communication,
        recommendation="Proceed with coordinated discharge and documented follow-up.",
        outstanding_tasks=["Confirm GP summary sent", "Ensure community follow-up booked"],
    )
    followup_when = _future(int(blueprint["followup_days"]))
    return [
        _step(
            "bed_manager",
            "tasks/sendSubscribe",
            {
                "task": {
                    "admission_type": "inpatient_stepdown",
                    "required_monitoring": "routine",
                }
            },
            delay=delay,
        ),
        _step(
            "clinician_avatar",
            "avatar/start_session",
            {
                "patient_case": {
                    "chief_complaint": blueprint["chief_complaint"],
                    "age": blueprint["age"],
                    "gender": blueprint["gender"],
                    "urgency": blueprint["urgency"],
                    "communication_needs": communication["needs"],
                },
                "persona": blueprint["persona"],
            },
            delay=delay,
            handoff_policy=_policy(["bed_manager"], "Discharge readiness review after ward status update."),
        ),
        _step(
            "diagnosis",
            "tasks/sendSubscribe",
            {"symptoms": blueprint["symptoms"], "differential_diagnosis": list(blueprint["differential"])},
            delay=delay,
            handoff_policy=_policy(["clinician_avatar"], "Clinical review confirms transfer readiness."),
        ),
        _step(
            "pharmacy",
            "pharmacy/recommend",
            {"task": {"med_plan": list(blueprint["med_plan"]), "allergies": ["No known drug allergies"]}},
            delay=delay,
            handoff_policy=_policy(["diagnosis"], "Medicines reconciliation completed before discharge."),
        ),
        _step(
            "discharge",
            "tasks/sendSubscribe",
            {
                "task": {
                    "discharge_summary": (
                        f"{blueprint['chief_complaint']} stabilised; transition to {blueprint['receiving_team']}."
                    ),
                    "medication_reconciliation_complete": True,
                    "medications_on_discharge": list(blueprint["med_plan"]),
                },
                "care_transition": {
                    "handover_owner": "discharging_clinician",
                    "receiving_team": blueprint["receiving_team"],
                    "followup_responsibility": blueprint["receiving_team"],
                    "receiving_provider_notified": True,
                    "handover": handover,
                },
            },
            delay=delay,
            handoff_policy=_policy(
                ["pharmacy"],
                "Discharge only after summary, meds reconciliation, and receiving-team notification.",
            ),
        ),
        _step(
            "followup",
            "tasks/sendSubscribe",
            {
                "followup_schedule": [
                    {
                        "type": blueprint["followup_type"],
                        "when": followup_when,
                        "purpose": f"Post-discharge review for {blueprint['chief_complaint']}",
                    }
                ],
                "care_transition": {
                    "handover_owner": "discharge_coordinator",
                    "receiving_team": blueprint["receiving_team"],
                    "followup_responsibility": blueprint["receiving_team"],
                    "receiving_provider_notified": True,
                    "handover": handover,
                },
            },
            delay=delay,
            handoff_policy=_policy(
                ["discharge"],
                "Follow-up scheduling confirms post-discharge ownership.",
            ),
        ),
        _step(
            "coordinator",
            "tasks/sendSubscribe",
            {
                "task": {"pathway": "discharge_transition", "context": context["code"]},
                "care_transition": {
                    "handover_owner": "care_coordinator",
                    "receiving_team": blueprint["receiving_team"],
                    "followup_responsibility": blueprint["receiving_team"],
                    "receiving_provider_notified": True,
                    "handover": handover,
                },
            },
            delay=delay,
            handoff_policy=_policy(
                ["followup"],
                "Coordinator confirms complete transfer-of-care packet and responsibilities.",
            ),
        ),
    ]


def _community_coordination_steps(
    blueprint: dict[str, Any],
    context: dict[str, Any],
    communication: dict[str, str],
) -> list[dict[str, Any]]:
    delay = int(context["delay_bias"])
    handover = _handover_payload(
        blueprint,
        context,
        communication,
        recommendation=f"Continue community plan with {blueprint['receiving_team']}.",
        outstanding_tasks=["Confirm follow-up attendance", "Document accessibility support completion"],
    )
    followup_when = _future(int(blueprint["followup_days"]))
    return [
        _step(
            "home_visit",
            "tasks/sendSubscribe",
            {
                "visit_reason": blueprint["chief_complaint"],
                "operational_context": context["code"],
                "communication_support": communication["needs"],
            },
            delay=delay,
        ),
        _step(
            "telehealth",
            "telehealth/consult",
            {
                "patient_case": {
                    "chief_complaint": blueprint["chief_complaint"],
                    "urgency": blueprint["urgency"],
                },
                "communication_needs": communication["needs"],
            },
            delay=delay,
            handoff_policy=_policy(
                ["home_visit"],
                "Telehealth escalation follows initial community/home assessment.",
            ),
        ),
        _step(
            "primary_care",
            "tasks/sendSubscribe",
            {"complaint": blueprint["chief_complaint"], "care_context": blueprint["care_setting"]},
            delay=delay,
            handoff_policy=_policy(["telehealth"], "Primary care assumes review after telehealth triage."),
        ),
        _step(
            "ccm",
            "tasks/sendSubscribe",
            {"task": {"condition_focus": list(blueprint["differential"]), "minutes": 20}},
            delay=delay,
            handoff_policy=_policy(["primary_care"], "Chronic care plan refreshed after primary review."),
        ),
        _step(
            "pharmacy",
            "pharmacy/recommend",
            {"task": {"med_plan": list(blueprint["med_plan"]), "allergies": ["No known drug allergies"]}},
            delay=delay,
            handoff_policy=_policy(["primary_care"], "Medication review aligned with care-plan update."),
        ),
        _step(
            "followup",
            "tasks/sendSubscribe",
            {
                "followup_schedule": [
                    {
                        "type": blueprint["followup_type"],
                        "when": followup_when,
                        "purpose": f"Care coordination review for {blueprint['chief_complaint']}",
                    }
                ],
                "care_transition": {
                    "handover_owner": "care_coordinator",
                    "receiving_team": blueprint["receiving_team"],
                    "followup_responsibility": blueprint["receiving_team"],
                    "receiving_provider_notified": True,
                    "handover": handover,
                },
            },
            delay=delay,
            handoff_policy=_policy(["pharmacy"], "Follow-up booking confirms receiving-team ownership."),
        ),
        _step(
            "coordinator",
            "tasks/sendSubscribe",
            {
                "task": {"pathway": "community_coordination", "context": context["code"]},
                "care_transition": {
                    "handover_owner": "care_coordinator",
                    "receiving_team": blueprint["receiving_team"],
                    "followup_responsibility": blueprint["receiving_team"],
                    "receiving_provider_notified": True,
                    "handover": handover,
                },
            },
            delay=delay,
            handoff_policy=_policy(
                ["followup"],
                "Coordinator closes loop on communication and continuity tasks.",
            ),
        ),
    ]


def _build_positive_scenarios() -> list[PatientScenario]:
    scenarios: list[PatientScenario] = []
    for blueprint_index, blueprint in enumerate(POSITIVE_BLUEPRINTS):
        for context_index, context in enumerate(OPERATIONAL_CONTEXTS):
            communication = COMMUNICATION_PROFILES[
                (blueprint_index + context_index) % len(COMMUNICATION_PROFILES)
            ]
            name = (
                f"rep_{blueprint['slug']}__{context['code']}__"
                f"{communication['code']}"
            )
            description = (
                f"Representative {blueprint['care_setting']} journey under "
                f"{context['label']} conditions with {communication['label']}."
            )

            if blueprint["template"] == "acute_admission":
                steps = _acute_admission_steps(blueprint, context, communication)
            elif blueprint["template"] == "inpatient_discharge":
                steps = _inpatient_discharge_steps(blueprint, context, communication)
            else:
                steps = _community_coordination_steps(blueprint, context, communication)

            scenarios.append(
                PatientScenario(
                    name=name,
                    description=description,
                    patient_profile=_patient_profile(blueprint, context, communication),
                    medical_history=_medical_history(blueprint, communication),
                    journey_steps=steps,
                    expected_duration=12 + int(context["delay_bias"]) * 3,
                    simulation_profile=_scenario_profile(
                        name=name,
                        context=context,
                        risk_band=blueprint["risk_band"],
                        care_setting=blueprint["care_setting"],
                        communication_code=communication["code"],
                        scenario_class="positive",
                    ),
                )
            )
    return scenarios


def _negative_step_bundle(
    *,
    archetype: dict[str, str],
    context: dict[str, Any],
    communication: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    delay = int(context["delay_bias"])
    base_profile = {
        "age": 70,
        "gender": "female",
        "chief_complaint": archetype["slug"].replace("_", " "),
        "urgency": "high",
        "operational_context": context["code"],
        "service_pressure": context["service_pressure"],
        "communication_profile": communication["code"],
        "communication_support": communication["needs"],
        "vital_signs": {
            "blood_pressure": "122/74",
            "heart_rate": 88,
            "respiratory_rate": 18,
            "oxygen_saturation": 96,
            "temperature_c": 37.0,
        },
    }
    base_history = {
        "past_medical_history": ["COPD", "Hypertension"],
        "medications": ["Lisinopril", "Tiotropium"],
        "allergies": ["No known drug allergies"],
        "communication_needs": communication["needs"],
    }

    if archetype["slug"] == "handover_missing_outstanding_tests":
        steps = [
            _step(
                "diagnosis",
                "tasks/sendSubscribe",
                {
                    "symptoms": "chest pain with pending troponin",
                    "differential_diagnosis": ["Acute coronary syndrome"],
                },
                delay=delay,
            ),
            _step(
                "bed_manager",
                "tasks/sendSubscribe",
                {
                    "task": {"admission_type": "emergency"},
                    "care_transition": {
                        "handover_owner": "ed_registrar",
                        "receiving_team": "inpatient_team",
                        "followup_responsibility": "inpatient_team",
                        "receiving_provider_notified": True,
                        "handover": {
                            "situation": "ED transfer with pending diagnostics",
                            "background": "High-risk chest pain assessment underway",
                            "assessment": "Requires telemetry admission",
                            "recommendation": "Continue serial markers",
                            "plan": "Admit and review",
                            "communication_needs": communication["needs"],
                        },
                    },
                },
                delay=delay,
                handoff_policy=_policy(
                    ["diagnosis"],
                    "Pending results require explicit outstanding task ownership before transfer.",
                ),
            ),
        ]
        return steps, base_profile, base_history

    handover = {
        "situation": "Inpatient discharge transition",
        "background": "Admission has reached nominal discharge stage",
        "assessment": "Clinically improved for potential discharge",
        "recommendation": "Complete transfer checklist before discharge",
        "plan": "Community monitoring and follow-up",
        "outstanding_tasks": ["Notify GP and community team"],
        "communication_needs": communication["needs"],
    }
    task = {
        "discharge_summary": "Prepared summary",
        "medication_reconciliation_complete": True,
        "medications_on_discharge": ["Medication A", "Medication B"],
    }
    transition = {
        "handover_owner": "discharging_clinician",
        "receiving_team": "community_care_team",
        "followup_responsibility": "primary_care_team",
        "receiving_provider_notified": True,
        "handover": handover,
    }

    if archetype["slug"] == "missing_discharge_summary":
        task["discharge_summary"] = ""
    elif archetype["slug"] == "med_rec_incomplete":
        task["medication_reconciliation_complete"] = False
    elif archetype["slug"] == "communication_needs_not_met":
        handover["communication_needs"] = ""
    elif archetype["slug"] == "followup_not_arranged":
        transition["followup_responsibility"] = ""
    elif archetype["slug"] == "no_senior_escalation_after_deterioration":
        unstable = {
            "blood_pressure": "84/50",
            "heart_rate": 138,
            "respiratory_rate": 30,
            "oxygen_saturation": 89,
            "temperature_c": 39.2,
        }
        base_profile["vital_signs"] = unstable
        base_history["vital_signs"] = unstable

    steps = [
        _step(
            "discharge",
            "tasks/sendSubscribe",
            {
                "task": task,
                "care_transition": transition,
                "vital_signs": base_profile["vital_signs"],
            },
            delay=delay,
        )
    ]
    if archetype["slug"] == "followup_not_arranged":
        steps.append(
            _step(
                "followup",
                "tasks/sendSubscribe",
                {
                    "followup_schedule": [
                        {
                            "type": "primary_care",
                            "when": _future(7),
                            "purpose": "",
                        }
                    ]
                },
                delay=delay,
            )
        )
    return steps, base_profile, base_history


def _build_negative_scenarios() -> list[PatientScenario]:
    scenarios: list[PatientScenario] = []
    context_lookup = {entry["code"]: entry for entry in OPERATIONAL_CONTEXTS}
    for archetype_index, archetype in enumerate(NEGATIVE_ARCHETYPES):
        for context_index, context_code in enumerate(NEGATIVE_CONTEXT_CODES):
            context = context_lookup[context_code]
            communication = COMMUNICATION_PROFILES[
                (archetype_index + context_index + 1) % len(COMMUNICATION_PROFILES)
            ]
            name = f"rep_negative_{archetype['slug']}__{context['code']}"
            steps, profile, history = _negative_step_bundle(
                archetype=archetype,
                context=context,
                communication=communication,
            )
            scenarios.append(
                PatientScenario(
                    name=name,
                    description=(
                        f"Clinical negative handoff case ({archetype['slug']}) under "
                        f"{context['label']} conditions."
                    ),
                    patient_profile=profile,
                    medical_history=history,
                    journey_steps=steps,
                    expected_duration=8 + int(context["delay_bias"]) * 2,
                    negative_class="clinical_handoff",
                    expected_escalation=archetype["expected_escalation"],
                    expected_safe_outcome=archetype["expected_safe_outcome"],
                    simulation_profile=_scenario_profile(
                        name=name,
                        context=context,
                        risk_band="high",
                        care_setting=archetype["care_setting"],
                        communication_code=communication["code"],
                        scenario_class="clinical_negative",
                        failure_mode=archetype["slug"],
                    ),
                )
            )
    return scenarios


REPRESENTATIVE_SCENARIOS: list[PatientScenario] = (
    _build_positive_scenarios() + _build_negative_scenarios()
)

enrich_scenario_handoff_contracts(REPRESENTATIVE_SCENARIOS)


async def run_representative_scenarios(limit: int | None = None) -> None:
    """Run representative scenarios sequentially for smoke validation."""
    selected = REPRESENTATIVE_SCENARIOS if limit is None else REPRESENTATIVE_SCENARIOS[: max(0, limit)]
    for scenario in selected:
        await run_scenario(scenario)


if __name__ == "__main__":
    asyncio.run(run_representative_scenarios())

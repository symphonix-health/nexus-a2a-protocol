#!/usr/bin/env python3
"""Clinical-negative patient journey scenarios for transfer-of-care safety tests.

These scenarios intentionally represent unsafe handoff conditions that should
result in blocked + escalated outcomes, not silent continuation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

try:
    from helixcare_scenarios import PatientScenario, enrich_scenario_handoff_contracts
except Exception:
    from tools.helixcare_scenarios import PatientScenario, enrich_scenario_handoff_contracts


def _future(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()


CLINICAL_NEGATIVE_SCENARIOS: list[PatientScenario] = [
    PatientScenario(
        name="negative_missing_discharge_summary",
        description="Unsafe discharge attempt with missing summary and receiving-provider notification.",
        patient_profile={
            "age": 71,
            "gender": "female",
            "chief_complaint": "Discharge after COPD exacerbation",
            "urgency": "medium",
        },
        journey_steps=[
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "discharge_diagnosis": "COPD exacerbation",
                        "medication_reconciliation_complete": True,
                    },
                    "care_transition": {
                        "receiving_provider_notified": False,
                        "followup_responsibility": "primary_care_team",
                        "handover": {
                            "situation": "Ready for home discharge",
                            "background": "Admitted for COPD exacerbation",
                            "assessment": "Improved oxygenation",
                            "recommendation": "Continue inhalers",
                            "plan": "Community follow-up",
                            "outstanding_tasks": ["Send summary"],
                            "communication_needs": "Standard",
                        },
                    },
                },
                "handoff_policy": {
                    "criticality": "clinical",
                    "fallback_mode": "block_escalate",
                    "required_handover_fields": [
                        "handover.situation",
                        "handover.background",
                        "handover.assessment",
                        "handover.recommendation",
                        "handover.plan",
                        "handover.outstanding_tasks",
                        "handover.communication_needs",
                    ],
                    "escalation_path": ["care_coordinator", "senior_clinician", "hitl_ui"],
                    "max_wait_seconds": 900,
                    "clinical_rationale": "Do not discharge without complete transition documentation",
                },
            }
        ],
        expected_duration=6,
        negative_class="clinical_handoff",
        expected_escalation="discharge_guardrail_breach",
        expected_safe_outcome="block_and_escalate_with_hitl_task",
        simulation_profile={"variance_band": "medium"},
    ),
    PatientScenario(
        name="negative_med_rec_incomplete",
        description="Medication reconciliation missing at transfer point.",
        patient_profile={
            "age": 66,
            "gender": "male",
            "chief_complaint": "Post-sepsis discharge transition",
            "urgency": "high",
        },
        journey_steps=[
            {
                "agent": "pharmacy",
                "method": "pharmacy/recommend",
                "params": {"task": {"med_plan": ["Levofloxacin"], "allergies": []}},
            },
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "discharge_summary": "Prepared",
                        "medication_reconciliation_complete": False,
                    },
                    "care_transition": {
                        "receiving_provider_notified": True,
                        "followup_responsibility": "community_matron",
                    },
                },
            },
        ],
        expected_duration=8,
        negative_class="clinical_handoff",
        expected_escalation="discharge_guardrail_breach",
        expected_safe_outcome="block_until_med_rec_complete",
        simulation_profile={"variance_band": "medium"},
    ),
    PatientScenario(
        name="negative_handover_missing_outstanding_tests",
        description="Transfer without ownership of pending diagnostics.",
        patient_profile={
            "age": 58,
            "gender": "female",
            "chief_complaint": "ED chest pain with pending troponin",
            "urgency": "high",
        },
        journey_steps=[
            {
                "agent": "diagnosis",
                "method": "tasks/sendSubscribe",
                "params": {"symptoms": "chest pain", "differential_diagnosis": ["ACS"]},
            },
            {
                "agent": "bed_manager",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {"admission_type": "emergency"},
                    "care_transition": {
                        "handover": {
                            "situation": "ED to telemetry admission",
                            "background": "Chest pain workup ongoing",
                            "assessment": "High-risk symptoms",
                            "recommendation": "Telemetry monitoring",
                            "plan": "Serial troponin testing",
                            "communication_needs": "Standard",
                        }
                    },
                },
                "handoff_policy": {
                    "required_predecessors": ["diagnosis"],
                    "required_handover_fields": [
                        "handover.situation",
                        "handover.background",
                        "handover.assessment",
                        "handover.recommendation",
                        "handover.plan",
                        "handover.outstanding_tasks",
                        "handover.communication_needs",
                    ],
                    "fallback_mode": "block_escalate",
                    "clinical_rationale": "Pending tests must have explicit ownership",
                },
            },
        ],
        expected_duration=8,
        negative_class="clinical_handoff",
        expected_escalation="structured_handover_gap",
        expected_safe_outcome="block_and_assign_outstanding_results_owner",
        simulation_profile={"variance_band": "medium"},
    ),
    PatientScenario(
        name="negative_no_senior_escalation_after_nonresponse",
        description="Physiological deterioration present but pathway attempts routine discharge.",
        patient_profile={
            "age": 74,
            "gender": "male",
            "chief_complaint": "Post-infection discharge reassessment",
            "urgency": "high",
            "vital_signs": {
                "blood_pressure": "88/54",
                "heart_rate": 132,
                "respiratory_rate": 28,
                "oxygen_saturation": 89,
                "temperature_c": 39.1,
            },
        },
        journey_steps=[
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "discharge_summary": "Draft summary",
                        "medication_reconciliation_complete": True,
                    },
                    "care_transition": {
                        "receiving_provider_notified": True,
                        "followup_responsibility": "primary_care_team",
                    },
                },
            }
        ],
        expected_duration=5,
        negative_class="clinical_handoff",
        expected_escalation="senior_review_required",
        expected_safe_outcome="block_discharge_and_trigger_urgent_review",
        simulation_profile={"variance_band": "high"},
    ),
    PatientScenario(
        name="negative_communication_needs_not_documented",
        description="Transfer attempted without communication/accessibility needs.",
        patient_profile={
            "age": 43,
            "gender": "female",
            "chief_complaint": "Post-operative discharge with interpreter need",
            "urgency": "medium",
        },
        journey_steps=[
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "discharge_summary": "Summary prepared",
                        "medication_reconciliation_complete": True,
                    },
                    "care_transition": {
                        "receiving_provider_notified": True,
                        "followup_responsibility": "surgical_clinic",
                        "handover": {
                            "situation": "Post-op day 3 discharge",
                            "background": "Laparoscopic cholecystectomy",
                            "assessment": "Recovering well",
                            "recommendation": "Routine follow-up",
                            "plan": "Review in clinic",
                            "outstanding_tasks": ["Wound check"],
                            "communication_needs": "",
                        },
                    },
                },
            }
        ],
        expected_duration=5,
        negative_class="clinical_handoff",
        expected_escalation="structured_handover_gap",
        expected_safe_outcome="block_until_accessibility_needs_documented",
        simulation_profile={"variance_band": "medium"},
    ),
    PatientScenario(
        name="negative_followup_not_arranged",
        description="Discharge completed without follow-up ownership and appointment pathway.",
        patient_profile={
            "age": 62,
            "gender": "male",
            "chief_complaint": "Heart failure discharge transition",
            "urgency": "medium",
        },
        journey_steps=[
            {
                "agent": "discharge",
                "method": "tasks/sendSubscribe",
                "params": {
                    "task": {
                        "discharge_summary": "HF discharge summary",
                        "medication_reconciliation_complete": True,
                    },
                    "care_transition": {
                        "receiving_provider_notified": True,
                        "followup_responsibility": "",
                        "handover": {
                            "situation": "HF symptoms improved",
                            "background": "Recent admission for fluid overload",
                            "assessment": "Stable at discharge",
                            "recommendation": "Continue diuretics",
                            "plan": "Outpatient follow-up required",
                            "outstanding_tasks": ["Schedule HF clinic"],
                            "communication_needs": "Large-print materials",
                        },
                    },
                },
            },
            {
                "agent": "followup",
                "method": "tasks/sendSubscribe",
                "params": {
                    "followup_schedule": [
                        {
                            "type": "cardiology",
                            "when": _future(7),
                            "purpose": "",
                        }
                    ]
                },
                "handoff_policy": {
                    "required_predecessors": ["discharge"],
                    "required_handover_fields": [
                        "handover.situation",
                        "handover.background",
                        "handover.assessment",
                        "handover.recommendation",
                        "handover.plan",
                        "handover.outstanding_tasks",
                        "handover.communication_needs",
                    ],
                    "fallback_mode": "block_escalate",
                    "clinical_rationale": "Follow-up ownership required at discharge transition",
                },
            },
        ],
        expected_duration=8,
        negative_class="clinical_handoff",
        expected_escalation="discharge_guardrail_breach",
        expected_safe_outcome="block_and_create_safety_net_followup_task",
        simulation_profile={"variance_band": "medium"},
    ),
]

enrich_scenario_handoff_contracts(CLINICAL_NEGATIVE_SCENARIOS)


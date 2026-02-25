"""Unit tests for NHS/NICE transfer-of-care guardrails."""

from __future__ import annotations

from shared.nexus_common.clinical_handoff_rules import (
    apply_nhs_guardrails,
    evaluate_deterioration_escalation,
    evaluate_discharge_guardrails,
    evaluate_structured_handover,
)


def test_structured_handover_missing_fields_blocks() -> None:
    step = {
        "agent": "bed_manager",
        "method": "tasks/sendSubscribe",
        "params": {"care_transition": {"handover": {"situation": "ED to ward"}}},
    }
    policy = {"required_handover_fields": ["handover.situation", "handover.plan"]}
    result = evaluate_structured_handover(step, policy, {})
    assert result.allowed is False
    assert result.reason_code == "missing_handover_contract"
    assert "handover.plan" in result.missing_fields
    assert "NICE-QS174-Statement4" in result.guideline_refs


def test_discharge_guardrail_blocks_when_med_rec_missing() -> None:
    step = {
        "agent": "discharge",
        "method": "tasks/sendSubscribe",
        "params": {
            "task": {"discharge_summary": "ready"},
            "care_transition": {"receiving_provider_notified": True, "followup_responsibility": "pcp"},
        },
    }
    result = evaluate_discharge_guardrails(step, {})
    assert result.allowed is False
    assert result.reason_code == "unsafe_discharge_prevented"
    assert "medication_reconciliation" in result.reason
    assert "NICE-NG27" in result.guideline_refs


def test_deterioration_blocks_discharge() -> None:
    step = {"agent": "discharge", "method": "tasks/sendSubscribe", "params": {}}
    ctx = {
        "patient_profile": {
            "vital_signs": {
                "blood_pressure": "84/50",
                "heart_rate": 136,
                "respiratory_rate": 30,
                "oxygen_saturation": 88,
                "temperature_c": 39.3,
            }
        }
    }
    result = evaluate_deterioration_escalation(step, ctx)
    assert result.allowed is False
    assert result.reason_code == "senior_review_required"
    assert result.senior_review_deadline is not None


def test_apply_guardrails_merges_refs_and_blocks_on_first_failure() -> None:
    step = {
        "agent": "discharge",
        "method": "tasks/sendSubscribe",
        "params": {"task": {"discharge_summary": "draft"}},
    }
    policy = {"required_handover_fields": ["handover.situation"]}
    result = apply_nhs_guardrails(step, policy, {"handover": {}})
    assert result.allowed is False
    assert result.reason_code in {"missing_handover_contract", "unsafe_discharge_prevented"}
    assert result.guideline_refs


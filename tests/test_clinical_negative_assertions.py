"""Tests for clinical-negative harness assertions."""

from __future__ import annotations

from tests.nexus_harness.clinical_negative_assertions import assert_clinical_negative_trace
from tests.nexus_harness.runner import assert_clinical_negative_outcome


def test_assert_clinical_negative_trace_accepts_blocked_escalated():
    trace = {
        "handover_contract_status": "blocked",
        "escalation_trigger": "discharge_guardrail_breach",
        "safe_fallback_taken": True,
        "delegation_chain": [
            {
                "state": "blocked_escalated",
                "reason_code": "discharge_guardrail_breach",
                "escalation_target": "hitl_ui",
            }
        ],
    }
    assert_clinical_negative_trace(
        trace,
        expected_escalation="discharge_guardrail_breach",
        expected_safe_outcome="block_and_escalate_with_hitl_task",
    )


def test_runner_assert_clinical_negative_outcome_accepts_blocked_escalated():
    scenario = {
        "use_case_id": "HC-NEG-001",
        "negative_class": "clinical_handoff",
        "expected_escalation": "discharge_guardrail_breach",
        "expected_safe_outcome": "block_and_escalate_with_hitl_task",
    }
    trace = {
        "handover_contract_status": "blocked",
        "escalation_trigger": "discharge_guardrail_breach",
        "delegation_chain": [
            {
                "state": "blocked_escalated",
                "reason_code": "discharge_guardrail_breach",
                "escalation_target": "hitl_ui",
            }
        ],
    }
    assert_clinical_negative_outcome(scenario, trace_run=trace)

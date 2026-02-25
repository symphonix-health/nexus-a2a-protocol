"""Tests for the clinical delegation engine safety state machine."""

from __future__ import annotations

from tools.delegation import (
    DelegationMonitor,
    HandoffPolicy,
    HandoffResult,
    build_delegation_context,
    validate_handoff,
)


class TestValidateHandoff:
    def test_no_policy_allows(self):
        result = validate_handoff(None, {}, set(), set())
        assert result.allowed is True
        assert result.state == "allowed"

    def test_missing_predecessor_defaults_block_escalate(self):
        policy = HandoffPolicy(required_predecessors=["triage"])
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is False
        assert result.state == "blocked_escalated"
        assert result.reason_code == "missing_required_predecessor"
        assert result.escalation_required is True
        assert result.escalation_target == "care_coordinator"

    def test_skip_requires_administrative_criticality(self):
        policy = HandoffPolicy(
            required_predecessors=["identity_check"],
            fallback_mode="skip",
            criticality="administrative",
        )
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is False
        assert result.skipped is True
        assert result.state == "skipped"

    def test_skip_on_clinical_is_upgraded_to_block(self):
        policy = HandoffPolicy(
            required_predecessors=["diagnosis"],
            fallback_mode="skip",
            criticality="clinical",
        )
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is False
        assert result.state == "blocked_escalated"

    def test_retry_mode_returns_retry_pending(self):
        policy = HandoffPolicy(
            required_predecessors=["triage"],
            fallback_mode="retry_then_escalate",
            max_wait_seconds=30,
        )
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is False
        assert result.state == "retry_pending"
        assert result.retry_after_seconds == 30.0
        assert result.escalation_required is False

    def test_reroute_state_is_emitted_when_branch_present(self):
        policy = HandoffPolicy(
            required_predecessors=["diagnosis"],
            fallback_mode="reroute",
            safe_fallback_branch="manual_followup_queue",
        )
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is False
        assert result.state == "rerouted"
        assert result.safe_fallback_taken is True

    def test_degraded_allow_mode(self):
        policy = HandoffPolicy(
            required_predecessors=["diagnosis"],
            fallback_mode="degraded_allow",
        )
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is True
        assert result.state == "degraded_allowed"
        assert result.escalation_required is True

    def test_required_context_missing_is_blocked(self):
        policy = HandoffPolicy(required_context_keys=["patient_profile.age"])
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is False
        assert result.state == "blocked_escalated"
        assert result.reason_code == "missing_required_context"
        assert "patient_profile.age" in result.missing_context_keys

    def test_required_handover_fields_missing(self):
        policy = HandoffPolicy(required_handover_fields=["handover.situation", "handover.plan"])
        ctx = {"handover": {"situation": "ED transfer"}}
        result = validate_handoff(policy, ctx, set(), set())
        assert result.allowed is False
        assert result.reason_code == "missing_handover_contract"
        assert "handover.plan" in result.missing_handover_fields

    def test_dict_policy_is_supported(self):
        policy = {
            "required_predecessors": ["triage"],
            "fallback_mode": "block_escalate",
            "criticality": "clinical",
            "guideline_refs": ["NICE-QS174-Statement4"],
        }
        result = validate_handoff(policy, {}, {"triage"}, set())
        assert result.allowed is True
        assert "NICE-QS174-Statement4" in result.guideline_refs


class TestBuildDelegationContext:
    def test_context_includes_extended_fields(self):
        step = {"agent": "discharge", "method": "tasks/sendSubscribe"}
        policy = HandoffPolicy(
            required_predecessors=["pharmacy"],
            required_handover_fields=["handover.situation"],
            escalation_path=["care_coordinator", "senior_clinician"],
            max_wait_seconds=600,
            fallback_mode="block_escalate",
            criticality="clinical",
        )
        ctx = {"agent_outputs": {"pharmacy": {"ok": True}}}
        result = build_delegation_context(step, ctx, policy)
        assert result["delegating_to"] == "discharge"
        assert result["criticality"] == "clinical"
        assert result["required_handover_fields"] == ["handover.situation"]
        assert result["fallback_mode"] == "block_escalate"
        assert "pharmacy" in result["predecessor_outputs"]


class TestDelegationMonitor:
    def test_to_chain_contains_state_and_escalation(self):
        monitor = DelegationMonitor()
        monitor.record_handoff(
            "_start",
            "discharge",
            1,
            HandoffResult(
                allowed=False,
                state="blocked_escalated",
                reason_code="unsafe_discharge_prevented",
                reason="Unsafe discharge blocked",
                escalation_required=True,
                escalation_target="senior_clinician",
                guideline_refs=["NICE-NG27"],
            ),
            "Discharge guardrail failed",
        )
        chain = monitor.to_chain()
        assert len(chain) == 1
        assert chain[0]["state"] == "blocked_escalated"
        assert chain[0]["reason_code"] == "unsafe_discharge_prevented"
        assert chain[0]["escalation_target"] == "senior_clinician"
        assert chain[0]["guideline_refs"] == ["NICE-NG27"]

    def test_skipped_and_failed_counts(self):
        monitor = DelegationMonitor()
        monitor.record_handoff(
            "_start",
            "admin",
            1,
            HandoffResult(allowed=False, skipped=True, state="skipped", reason_code="missing_required_context"),
        )
        monitor.record_handoff(
            "admin",
            "diagnosis",
            2,
            HandoffResult(
                allowed=False,
                skipped=False,
                state="blocked_escalated",
                reason_code="missing_required_predecessor",
            ),
        )
        assert monitor.skipped_count == 1
        assert monitor.failed_count == 1


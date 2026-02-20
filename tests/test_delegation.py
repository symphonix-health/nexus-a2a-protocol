"""Tests for the clinical delegation engine.

Covers handoff validation, context building, and delegation monitoring.
"""

from __future__ import annotations

from tools.delegation import (
    DelegationMonitor,
    HandoffPolicy,
    HandoffResult,
    build_delegation_context,
    validate_handoff,
)

# ── validate_handoff ───────────────────────────────────────────────


class TestValidateHandoff:
    """Tests for ``validate_handoff``."""

    def test_no_policy_always_allowed(self):
        result = validate_handoff(None, {}, set(), set())
        assert result.allowed is True
        assert result.skipped is False

    def test_all_predecessors_met(self):
        policy = HandoffPolicy(required_predecessors=["triage"])
        result = validate_handoff(policy, {}, {"triage"}, set())
        assert result.allowed is True

    def test_missing_predecessor_skip(self):
        policy = HandoffPolicy(
            required_predecessors=["triage"],
            fallback_action="skip",
        )
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is False
        assert result.skipped is True
        assert "triage" in result.missing_predecessors

    def test_missing_predecessor_fail(self):
        policy = HandoffPolicy(
            required_predecessors=["triage"],
            fallback_action="fail",
        )
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is False
        assert result.skipped is False
        assert "triage" in result.missing_predecessors

    def test_missing_predecessor_stub_allows(self):
        policy = HandoffPolicy(
            required_predecessors=["triage"],
            fallback_action="stub",
        )
        result = validate_handoff(policy, {}, set(), set())
        assert result.allowed is True

    def test_failed_predecessor_reported(self):
        policy = HandoffPolicy(
            required_predecessors=["triage"],
            fallback_action="skip",
        )
        result = validate_handoff(
            policy,
            {},
            set(),
            {"triage"},
        )
        assert result.allowed is False
        assert result.skipped is True
        assert "failed" in result.reason.lower()

    def test_optional_predecessors_ignored(self):
        policy = HandoffPolicy(
            required_predecessors=["triage"],
            optional_predecessors=["imaging"],
        )
        result = validate_handoff(policy, {}, {"triage"}, set())
        assert result.allowed is True

    def test_required_context_key_present(self):
        policy = HandoffPolicy(
            required_context_keys=["patient_profile.age"],
        )
        ctx = {"patient_profile": {"age": 42}}
        result = validate_handoff(policy, ctx, set(), set())
        assert result.allowed is True

    def test_required_context_key_missing_skip(self):
        policy = HandoffPolicy(
            required_context_keys=["patient_profile.lab_results"],
            fallback_action="skip",
        )
        ctx = {"patient_profile": {"age": 42}}
        result = validate_handoff(policy, ctx, set(), set())
        assert result.allowed is False
        assert result.skipped is True
        assert "lab_results" in result.reason

    def test_required_context_key_missing_fail(self):
        policy = HandoffPolicy(
            required_context_keys=["agent_outputs.triage.score"],
            fallback_action="fail",
        )
        ctx = {"agent_outputs": {}}
        result = validate_handoff(policy, ctx, set(), set())
        assert result.allowed is False
        assert result.skipped is False

    def test_dict_policy_accepted(self):
        policy_dict = {
            "required_predecessors": ["diagnosis"],
            "fallback_action": "skip",
            "clinical_rationale": "Pharmacy after diagnosis",
        }
        result = validate_handoff(
            policy_dict,
            {},
            {"diagnosis"},
            set(),
        )
        assert result.allowed is True

    def test_dict_policy_with_extra_keys(self):
        policy_dict = {
            "required_predecessors": ["triage"],
            "fallback_action": "fail",
            "some_future_key": True,
        }
        result = validate_handoff(
            policy_dict,
            {},
            {"triage"},
            set(),
        )
        assert result.allowed is True

    def test_multiple_required_all_met(self):
        policy = HandoffPolicy(
            required_predecessors=["triage", "diagnosis"],
        )
        result = validate_handoff(
            policy,
            {},
            {"triage", "diagnosis"},
            set(),
        )
        assert result.allowed is True

    def test_multiple_required_partial_met(self):
        policy = HandoffPolicy(
            required_predecessors=["triage", "diagnosis"],
            fallback_action="skip",
        )
        result = validate_handoff(
            policy,
            {},
            {"triage"},
            set(),
        )
        assert result.allowed is False
        assert "diagnosis" in result.missing_predecessors


# ── build_delegation_context ───────────────────────────────────────


class TestBuildDelegationContext:
    """Tests for ``build_delegation_context``."""

    def test_basic_context(self):
        step = {"agent": "diagnosis", "method": "tasks/sendSubscribe"}
        ctx = {"agent_outputs": {"triage": {"score": 3}}}
        result = build_delegation_context(step, ctx, None)
        assert result["delegating_to"] == "diagnosis"
        assert result["method"] == "tasks/sendSubscribe"

    def test_with_policy(self):
        step = {"agent": "pharmacy", "method": "pharmacy/recommend"}
        policy = HandoffPolicy(
            required_predecessors=["diagnosis"],
            clinical_rationale="Medication after diagnosis",
        )
        ctx = {
            "agent_outputs": {
                "diagnosis": {"dx": "Pneumonia"},
            },
        }
        result = build_delegation_context(step, ctx, policy)
        assert result["clinical_rationale"] == "Medication after diagnosis"
        assert "diagnosis" in result["predecessor_outputs"]
        assert result["predecessor_outputs"]["diagnosis"]["dx"] == "Pneumonia"

    def test_with_dict_policy(self):
        step = {"agent": "imaging", "method": "tasks/sendSubscribe"}
        policy_dict = {
            "required_predecessors": ["diagnosis"],
            "optional_predecessors": ["triage"],
            "clinical_rationale": "Imaging after dx",
        }
        ctx = {
            "agent_outputs": {
                "triage": {"acuity": 2},
                "diagnosis": {"dx": "Fracture"},
            },
        }
        result = build_delegation_context(step, ctx, policy_dict)
        assert "triage" in result["predecessor_outputs"]
        assert "diagnosis" in result["predecessor_outputs"]


# ── DelegationMonitor ──────────────────────────────────────────────


class TestDelegationMonitor:
    """Tests for ``DelegationMonitor``."""

    def test_record_handoff(self):
        monitor = DelegationMonitor()
        hr = HandoffResult(allowed=True)
        event = monitor.record_handoff(
            "_start",
            "triage",
            1,
            hr,
            "Initial triage step",
        )
        assert event.from_agent == "_start"
        assert event.to_agent == "triage"
        assert event.handoff_allowed is True
        assert event.clinical_rationale == "Initial triage step"

    def test_to_chain(self):
        monitor = DelegationMonitor()
        monitor.record_handoff(
            "_start",
            "triage",
            1,
            HandoffResult(allowed=True),
        )
        monitor.record_handoff(
            "triage",
            "diagnosis",
            2,
            HandoffResult(allowed=True),
        )
        chain = monitor.to_chain()
        assert len(chain) == 2
        assert chain[0]["from"] == "_start"
        assert chain[1]["to"] == "diagnosis"

    def test_skipped_count(self):
        monitor = DelegationMonitor()
        monitor.record_handoff(
            "_start",
            "triage",
            1,
            HandoffResult(allowed=True),
        )
        monitor.record_handoff(
            "triage",
            "avatar",
            2,
            HandoffResult(allowed=False, skipped=True, reason="skipped"),
        )
        assert monitor.skipped_count == 1
        assert monitor.failed_count == 0

    def test_failed_count(self):
        monitor = DelegationMonitor()
        monitor.record_handoff(
            "triage",
            "diagnosis",
            1,
            HandoffResult(allowed=False, reason="blocked"),
        )
        assert monitor.failed_count == 1
        assert monitor.skipped_count == 0

    def test_step_timer(self):
        monitor = DelegationMonitor()
        monitor.start_step_timer()
        import time

        time.sleep(0.01)
        elapsed = monitor.stop_step_timer()
        assert elapsed > 0
        # Second stop should return 0
        assert monitor.stop_step_timer() == 0.0

    def test_empty_chain(self):
        monitor = DelegationMonitor()
        assert monitor.to_chain() == []
        assert monitor.skipped_count == 0
        assert monitor.failed_count == 0

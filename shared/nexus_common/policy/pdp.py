"""Policy Decision Point (PDP) for patient-level IAM controls."""

from __future__ import annotations

import os
from functools import lru_cache

from .models import PolicyDecision, PolicyObligation, PolicyRequest
from .pip import InMemoryPolicyInformationProvider, get_policy_information_provider

_VALID_POLICY_MODES = {"off", "shadow", "enforce"}


def policy_mode() -> str:
    mode = os.getenv("NEXUS_POLICY_MODE", "off").strip().lower()
    if mode not in _VALID_POLICY_MODES:
        return "off"
    return mode


def apply_policy_mode(decision: PolicyDecision, *, mode: str | None = None) -> PolicyDecision:
    """Apply runtime policy mode semantics to a base decision."""
    selected_mode = mode or policy_mode()
    decision.mode = selected_mode
    if selected_mode == "off":
        return PolicyDecision(
            allowed=True,
            reasons=[],
            obligations=decision.obligations,
            mode="off",
            policy_version=decision.policy_version,
            enforced=False,
            shadow_denied=False,
        )
    if selected_mode == "shadow" and not decision.allowed:
        decision.shadow_denied = True
        decision.allowed = True
        decision.enforced = False
        return decision
    decision.enforced = selected_mode == "enforce"
    return decision


class PolicyDecisionPoint:
    """Evaluate patient-level authorization constraints."""

    def __init__(self, pip: InMemoryPolicyInformationProvider) -> None:
        self._pip = pip

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        obligations: list[PolicyObligation] = [
            PolicyObligation(
                code="audit_required",
                detail={"resource": request.resource, "action": request.action},
            )
        ]
        reasons: list[str] = []

        patient_policy = self._pip.for_patient(request.patient_id)

        if request.break_glass:
            obligations.append(
                PolicyObligation(
                    code="break_glass_audit",
                    detail={
                        "actor": request.agent_actor,
                        "human_actor": request.human_actor,
                        "reason": request.break_glass_reason or "",
                    },
                )
            )

        if request.patient_id:
            if not patient_policy.consent_granted and not request.break_glass:
                reasons.append("consent_denied")

            if patient_policy.care_team:
                allowed_actors = set(patient_policy.care_team)
                if request.agent_actor not in allowed_actors and request.human_actor not in allowed_actors:
                    if not request.break_glass:
                        reasons.append("care_team_mismatch")

            allowed_pou = set(patient_policy.allowed_purposes_of_use)
            if allowed_pou and request.purpose_of_use and request.purpose_of_use not in allowed_pou:
                if not request.break_glass:
                    reasons.append("purpose_of_use_not_allowed")

            if patient_policy.requires_break_glass and not request.break_glass:
                reasons.append("break_glass_required")
                obligations.append(PolicyObligation(code="hitl_required"))

        if request.break_glass:
            if not patient_policy.break_glass_allowed:
                reasons.append("break_glass_not_allowed")
            if not str(request.break_glass_reason or "").strip():
                reasons.append("break_glass_reason_required")

        if patient_policy.redaction_profile:
            obligations.append(
                PolicyObligation(
                    code="apply_redaction_profile",
                    detail={"profile": patient_policy.redaction_profile},
                )
            )

        return PolicyDecision(
            allowed=not reasons,
            reasons=reasons,
            obligations=obligations,
            mode=policy_mode(),
            policy_version="patient-policy-v1",
            enforced=policy_mode() == "enforce",
            shadow_denied=False,
        )


@lru_cache(maxsize=1)
def get_policy_decision_point() -> PolicyDecisionPoint:
    return PolicyDecisionPoint(get_policy_information_provider())


def reload_policy_decision_point() -> PolicyDecisionPoint:
    from .pip import reload_policy_information_provider

    reload_policy_information_provider()
    get_policy_decision_point.cache_clear()
    return get_policy_decision_point()

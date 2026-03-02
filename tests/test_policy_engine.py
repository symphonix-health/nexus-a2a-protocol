from __future__ import annotations

from shared.nexus_common.policy.models import PolicyDecision, PolicyObligation, PolicyRequest
from shared.nexus_common.policy.pdp import PolicyDecisionPoint, apply_policy_mode
from shared.nexus_common.policy.pip import InMemoryPolicyInformationProvider


def test_apply_policy_mode_shadow_keeps_request_flowing() -> None:
    decision = PolicyDecision(
        allowed=False,
        reasons=["consent_denied"],
        obligations=[PolicyObligation(code="audit_required")],
        mode="enforce",
    )
    out = apply_policy_mode(decision, mode="shadow")
    assert out.allowed is True
    assert out.shadow_denied is True
    assert out.enforced is False
    assert out.reasons == ["consent_denied"]


def test_pdp_denies_when_consent_not_granted_and_no_break_glass() -> None:
    pip = InMemoryPolicyInformationProvider(
        {
            "patients": {
                "p1": {
                    "consent_granted": False,
                    "care_team": ["triage_agent"],
                }
            }
        }
    )
    pdp = PolicyDecisionPoint(pip)
    req = PolicyRequest(
        method="triage/assess",
        action="assess",
        resource="triage",
        patient_id="p1",
        agent_actor="triage_agent",
        purpose_of_use="Treatment",
    )
    decision = pdp.evaluate(req)
    assert decision.allowed is False
    assert "consent_denied" in decision.reasons


def test_pdp_denies_when_care_team_check_fails() -> None:
    pip = InMemoryPolicyInformationProvider(
        {
            "patients": {
                "p2": {
                    "consent_granted": True,
                    "care_team": ["care_coordinator"],
                }
            }
        }
    )
    pdp = PolicyDecisionPoint(pip)
    req = PolicyRequest(
        method="care/coordinate",
        action="coordinate",
        resource="care",
        patient_id="p2",
        agent_actor="triage_agent",
        purpose_of_use="Treatment",
    )
    decision = pdp.evaluate(req)
    assert decision.allowed is False
    assert "care_team_mismatch" in decision.reasons


def test_pdp_break_glass_requires_reason_and_patient_allows_override() -> None:
    pip = InMemoryPolicyInformationProvider(
        {
            "patients": {
                "p3": {
                    "consent_granted": False,
                    "care_team": [],
                    "break_glass_allowed": True,
                    "requires_break_glass": True,
                }
            }
        }
    )
    pdp = PolicyDecisionPoint(pip)
    req = PolicyRequest(
        method="fhir/get",
        action="get",
        resource="fhir",
        patient_id="p3",
        agent_actor="triage_agent",
        purpose_of_use="Treatment",
        break_glass=True,
        break_glass_reason="",
    )
    decision = pdp.evaluate(req)
    assert decision.allowed is False
    assert "break_glass_reason_required" in decision.reasons

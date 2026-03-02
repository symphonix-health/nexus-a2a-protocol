"""Typed policy request and decision models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyObligation:
    code: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": dict(self.detail)}


@dataclass
class PolicyRequest:
    method: str
    action: str
    resource: str
    patient_id: str | None = None
    encounter_id: str | None = None
    agent_actor: str | None = None
    human_actor: str | None = None
    effective_persona: str | None = None
    purpose_of_use: str | None = None
    break_glass: bool = False
    break_glass_reason: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "action": self.action,
            "resource": self.resource,
            "patient_id": self.patient_id,
            "encounter_id": self.encounter_id,
            "agent_actor": self.agent_actor,
            "human_actor": self.human_actor,
            "effective_persona": self.effective_persona,
            "purpose_of_use": self.purpose_of_use,
            "break_glass": self.break_glass,
            "break_glass_reason": self.break_glass_reason,
            "claims": dict(self.claims),
        }


@dataclass
class PolicyDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    obligations: list[PolicyObligation] = field(default_factory=list)
    mode: str = "off"
    policy_version: str = "patient-policy-v1"
    enforced: bool = True
    shadow_denied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "obligations": [item.to_dict() for item in self.obligations],
            "mode": self.mode,
            "policy_version": self.policy_version,
            "enforced": self.enforced,
            "shadow_denied": self.shadow_denied,
        }

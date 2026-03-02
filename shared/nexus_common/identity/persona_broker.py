"""Persona resolution broker for agent and delegated human identity context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .agent_identity import AgentIdentity, get_agent_identity
from .persona_registry import Persona, get_persona_registry


class PersonaResolutionError(ValueError):
    """Raised when requested persona assumption violates configured policy."""


@dataclass
class PersonaContext:
    """Effective actor context after persona mapping."""

    agent_principal: str | None
    agent_id: str | None
    effective_persona_id: str | None
    effective_persona_name: str | None
    human_actor: str | None
    purpose_of_use: str | None
    iam_groups: list[str] = field(default_factory=list)
    delegated_scopes: list[str] = field(default_factory=list)
    source: str = "unknown"
    warnings: list[str] = field(default_factory=list)

    def to_claims_patch(self) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if self.agent_principal:
            patch["agent_principal"] = self.agent_principal
        if self.agent_id:
            patch["agent_id"] = self.agent_id
        if self.effective_persona_id:
            patch["persona_id"] = self.effective_persona_id
            patch["effective_persona"] = self.effective_persona_id
        if self.effective_persona_name:
            patch["persona_name"] = self.effective_persona_name
        if self.human_actor:
            patch["on_behalf_of"] = self.human_actor
            patch["human_actor"] = self.human_actor
        if self.purpose_of_use:
            patch["purpose_of_use"] = self.purpose_of_use
        if self.iam_groups:
            patch["groups"] = list(self.iam_groups)
        if self.delegated_scopes and "scopes" not in patch:
            patch["delegated_scopes"] = list(self.delegated_scopes)
        return patch


def _allowed_personas(identity: AgentIdentity) -> set[str]:
    allowed = {identity.primary_persona_id}
    allowed.update(identity.alternate_persona_ids.values())
    return {p for p in allowed if p}


def _resolve_human_actor(claims: Mapping[str, Any], explicit_human_actor: str | None) -> str | None:
    if explicit_human_actor:
        return explicit_human_actor
    for key in ("on_behalf_of", "obo", "human_actor", "delegated_by"):
        raw = str(claims.get(key) or "").strip()
        if raw:
            return raw
    return None


def resolve_persona_context(
    claims: Mapping[str, Any],
    *,
    agent_principal: str | None = None,
    requested_persona_id: str | None = None,
    human_actor: str | None = None,
    strict: bool = False,
) -> PersonaContext:
    """Resolve effective persona and human delegation context.

    Behavior:
    - prefer explicit requested persona, then token persona, then agent primary persona.
    - validate persona assumption against agent registry when agent identity is known.
    - when strict=True and registry lookups fail, raise PersonaResolutionError.
    """
    registry = get_persona_registry()

    token_agent = (
        str(
            claims.get("agent_id")
            or claims.get("agent_principal")
            or claims.get("sub")
            or ""
        ).strip()
        or None
    )
    effective_agent = agent_principal or token_agent

    identity: AgentIdentity | None = None
    warnings: list[str] = []
    if effective_agent:
        try:
            identity = get_agent_identity(effective_agent)
        except KeyError:
            warnings.append(f"unknown_agent:{effective_agent}")
            if strict:
                raise PersonaResolutionError(f"Unknown agent principal '{effective_agent}'")
    elif strict:
        raise PersonaResolutionError("Agent principal required for strict persona mapping")

    token_persona = str(claims.get("persona_id") or claims.get("effective_persona") or "").strip() or None
    selected_persona = requested_persona_id or token_persona
    source = "token"
    if not selected_persona and identity is not None:
        selected_persona = identity.primary_persona_id
        source = "agent_default"
    elif requested_persona_id:
        source = "requested"

    if selected_persona and identity is not None:
        allowed = _allowed_personas(identity)
        if selected_persona not in allowed:
            msg = (
                f"Agent '{identity.agent_id}' is not allowed to assume persona '{selected_persona}'"
            )
            if strict:
                raise PersonaResolutionError(msg)
            warnings.append(f"persona_not_allowed:{selected_persona}")

    persona: Persona | None = None
    if selected_persona:
        persona = registry.get(selected_persona)
        if persona is None:
            if strict:
                raise PersonaResolutionError(f"Unknown persona_id '{selected_persona}'")
            warnings.append(f"unknown_persona:{selected_persona}")

    resolved_human_actor = _resolve_human_actor(claims, human_actor)
    purpose_of_use = (
        str(claims.get("purpose_of_use") or "").strip()
        or (identity.purpose_of_use if identity else None)
        or (str(persona.iam.get("purpose_of_use")) if persona else None)
        or None
    )

    return PersonaContext(
        agent_principal=effective_agent,
        agent_id=identity.agent_id if identity else effective_agent,
        effective_persona_id=persona.persona_id if persona else selected_persona,
        effective_persona_name=persona.name if persona else None,
        human_actor=resolved_human_actor,
        purpose_of_use=purpose_of_use,
        iam_groups=list(identity.iam_groups) if identity else [],
        delegated_scopes=list(identity.delegated_scopes) if identity else [],
        source=source,
        warnings=warnings,
    )

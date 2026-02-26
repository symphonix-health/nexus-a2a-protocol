"""RBAC enforcement for NEXUS-A2A Protocol.

Provides scope-based access control, persona-level checks, and per-method
RBAC assessment.  All enforcement is deterministic and auditable.

Scope matching rules
--------------------
1. Exact match: ``patient.read`` matches ``patient.read``.
2. Universal wildcard: ``*.*`` covers every scope.
3. fnmatch glob: ``patient.*`` covers ``patient.read`` and ``patient.write``;
   ``system/*.read`` covers ``system/admin.read``.
4. Namespace prefix: ``system/*`` covers ``system/admin.read`` (any sub-resource
   under the *system* namespace).

Usage::

    from shared.nexus_common.rbac import enforce_rbac, RBACError, check_scope

    # Single-scope predicate
    if check_scope(granted_scopes, "patient.read"):
        ...

    # Strict enforcement (raises RBACError on failure)
    try:
        ctx = enforce_rbac(
            token_claims,
            required_scopes=["patient.read", "encounter.write"],
        )
    except RBACError as exc:
        raise HTTPException(status_code=403, detail=exc.to_dict())
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger("nexus.rbac")

# ── Sensitivity tier ordering ─────────────────────────────────────────────────
_TIER_ORDER: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "medium-high": 2,
    "high": 3,
}


# ── Exception ─────────────────────────────────────────────────────────────────


class RBACError(Exception):
    """Raised when an RBAC check fails."""

    def __init__(
        self,
        message: str,
        *,
        required: list[str] | None = None,
        granted: list[str] | None = None,
        persona_id: str | None = None,
        agent_id: str | None = None,
        bulletrain_role: str | None = None,
    ) -> None:
        super().__init__(message)
        self.required = required or []
        self.granted = granted or []
        self.persona_id = persona_id
        self.agent_id = agent_id
        self.bulletrain_role = bulletrain_role

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "rbac_denied",
            "message": str(self),
            "required": self.required,
            "granted": self.granted,
            "persona_id": self.persona_id,
            "agent_id": self.agent_id,
            "bulletrain_role": self.bulletrain_role,
        }


# ── Scope matching ────────────────────────────────────────────────────────────


def check_scope(granted_scopes: list[str], required_scope: str) -> bool:
    """Return True if *required_scope* is covered by any scope in *granted_scopes*.

    Matching is wildcard-aware (see module docstring for rules).
    """
    required = str(required_scope).strip()
    for raw in granted_scopes:
        granted = str(raw).strip()
        # Universal wildcard
        if granted in {"*.*", "*"}:
            return True
        # Exact match
        if granted == required:
            return True
        # fnmatch glob (handles patient.*, system/*.read, etc.)
        # Use fnmatchcase for case-sensitive matching on all platforms.
        if fnmatch.fnmatchcase(required, granted):
            return True
        # Namespace prefix: "system/*" covers "system/admin.read"
        if granted.endswith("/*"):
            namespace = granted[:-1]          # "system/"
            if required.startswith(namespace):
                return True
    return False


def check_scopes(granted_scopes: list[str], required_scopes: list[str]) -> list[str]:
    """Return the subset of *required_scopes* NOT covered by *granted_scopes*.

    An empty list means all required scopes are satisfied.
    """
    return [s for s in required_scopes if not check_scope(granted_scopes, s)]


# ── Token claims extraction ───────────────────────────────────────────────────


def extract_persona_scopes(token_claims: dict[str, Any]) -> list[str]:
    """Pull a list of FHIR/clinical scopes from decoded JWT claims.

    Handles three common layouts:

    * ``scopes`` (list) — persona-extended token from :func:`mint_persona_jwt`.
    * ``scope`` (space-separated string) — standard OAuth2 JWT.
    * ``nexus_scopes`` (list) — alternate key used by some issuers.
    """
    # List-valued "scopes" (persona JWT)
    scopes_claim = token_claims.get("scopes")
    if isinstance(scopes_claim, list):
        return [str(s) for s in scopes_claim if s]
    # space-separated "scope" string
    scope_str = token_claims.get("scope") or token_claims.get("nexus_scopes") or ""
    if isinstance(scope_str, str) and scope_str.strip():
        return [s for s in scope_str.split() if s != "nexus:invoke"]
    if isinstance(scope_str, list):
        return [str(s) for s in scope_str if s and s != "nexus:invoke"]
    return []


# ── RBACContext ───────────────────────────────────────────────────────────────


@dataclass
class RBACContext:
    """Summarises a completed RBAC assessment."""

    allowed: bool
    persona_id: str | None
    bulletrain_role: str | None
    granted_scopes: list[str]
    required_scopes: list[str]
    missing_scopes: list[str]
    purpose_of_use: str | None
    data_sensitivity: str | None
    agent_id: str | None = None
    method: str | None = None
    denied_reason: str | None = None
    audit_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "persona_id": self.persona_id,
            "bulletrain_role": self.bulletrain_role,
            "granted_scopes": self.granted_scopes,
            "required_scopes": self.required_scopes,
            "missing_scopes": self.missing_scopes,
            "purpose_of_use": self.purpose_of_use,
            "data_sensitivity": self.data_sensitivity,
            "agent_id": self.agent_id,
            "method": self.method,
            "denied_reason": self.denied_reason,
            "audit_tags": self.audit_tags,
        }


# ── Core enforcement ──────────────────────────────────────────────────────────


def enforce_rbac(
    token_claims: dict[str, Any],
    *,
    required_scopes: list[str] | None = None,
    permitted_bulletrain_roles: list[str] | None = None,
    permitted_purposes_of_use: list[str] | None = None,
    minimum_sensitivity_tier: str | None = None,
    agent_id: str | None = None,
) -> RBACContext:
    """Enforce persona-level RBAC from a decoded JWT token.

    Parameters
    ----------
    token_claims:
        Decoded JWT payload (returned by ``verify_jwt`` / ``verify_service_auth``).
    required_scopes:
        All scopes that must be present in the token.  Wildcard-aware.
    permitted_bulletrain_roles:
        If provided, the token's ``bulletrain_role`` claim must be one of these.
    permitted_purposes_of_use:
        If provided, the token's ``purpose_of_use`` must be one of these.
    minimum_sensitivity_tier:
        If provided, the token's ``data_sensitivity`` must meet or exceed this
        tier (Low < Medium < Medium-High < High).
    agent_id:
        Caller agent identifier — used for scope fallback and audit logging.

    Returns
    -------
    RBACContext
        On success.  Raises :class:`RBACError` on any enforcement failure.
    """
    persona_id = str(token_claims.get("persona_id") or "").strip() or None
    bulletrain_role = str(token_claims.get("bulletrain_role") or "").strip() or None
    purpose_of_use = str(token_claims.get("purpose_of_use") or "").strip() or None
    data_sensitivity = str(token_claims.get("data_sensitivity") or "").strip() or None
    # Build the full effective scope set: base JWT scopes (e.g. nexus:invoke)
    # plus FHIR/clinical scopes extracted from persona claims.
    _base_scope = token_claims.get("scope") or ""
    _base_scopes: list[str] = (
        [s for s in _base_scope.split() if s]
        if isinstance(_base_scope, str)
        else ([str(s) for s in _base_scope if s] if isinstance(_base_scope, list) else [])
    )
    granted_scopes = _base_scopes + [
        s for s in extract_persona_scopes(token_claims) if s not in _base_scopes
    ]

    ctx = RBACContext(
        allowed=False,
        persona_id=persona_id,
        bulletrain_role=bulletrain_role,
        granted_scopes=list(granted_scopes),
        required_scopes=list(required_scopes or []),
        missing_scopes=[],
        purpose_of_use=purpose_of_use,
        data_sensitivity=data_sensitivity,
        agent_id=agent_id,
    )

    # 1. Bulletrain role check ────────────────────────────────────────────────
    if permitted_bulletrain_roles:
        if not bulletrain_role or bulletrain_role not in permitted_bulletrain_roles:
            ctx.denied_reason = (
                f"bulletrain_role '{bulletrain_role}' not in {permitted_bulletrain_roles}"
            )
            raise RBACError(
                ctx.denied_reason,
                required=list(permitted_bulletrain_roles),
                granted=[bulletrain_role] if bulletrain_role else [],
                persona_id=persona_id,
                agent_id=agent_id,
                bulletrain_role=bulletrain_role,
            )
        ctx.audit_tags.append(f"role:{bulletrain_role}")

    # 2. Purpose-of-use check ─────────────────────────────────────────────────
    if permitted_purposes_of_use:
        if not purpose_of_use or purpose_of_use not in permitted_purposes_of_use:
            ctx.denied_reason = (
                f"purpose_of_use '{purpose_of_use}' not in {permitted_purposes_of_use}"
            )
            raise RBACError(
                ctx.denied_reason,
                required=list(permitted_purposes_of_use),
                granted=[purpose_of_use] if purpose_of_use else [],
                persona_id=persona_id,
                agent_id=agent_id,
                bulletrain_role=bulletrain_role,
            )
        ctx.audit_tags.append(f"pou:{purpose_of_use}")

    # 3. Sensitivity tier check ───────────────────────────────────────────────
    if minimum_sensitivity_tier:
        required_tier = _TIER_ORDER.get(minimum_sensitivity_tier.lower(), -1)
        granted_tier = _TIER_ORDER.get((data_sensitivity or "").lower(), -1)
        if granted_tier < required_tier:
            ctx.denied_reason = (
                f"data_sensitivity '{data_sensitivity}' below minimum '{minimum_sensitivity_tier}'"
            )
            raise RBACError(
                ctx.denied_reason,
                required=[minimum_sensitivity_tier],
                granted=[data_sensitivity] if data_sensitivity else [],
                persona_id=persona_id,
                agent_id=agent_id,
                bulletrain_role=bulletrain_role,
            )
        ctx.audit_tags.append(f"sensitivity:{data_sensitivity or 'unset'}")

    # 4. Scope check ──────────────────────────────────────────────────────────
    if required_scopes:
        # nexus:invoke is a protocol-level scope verified by verify_jwt before
        # RBAC is called; exclude it from FHIR/clinical scope comparisons.
        effective_granted = [s for s in granted_scopes if s != "nexus:invoke"]

        # Fallback: if the token carries no FHIR scopes (bare nexus:invoke),
        # use the agent's registered delegated_scopes from agent_personas.json.
        if not effective_granted and agent_id:
            try:
                from .identity import get_agent_identity  # lazy import

                identity = get_agent_identity(agent_id)
                effective_granted = list(identity.delegated_scopes)
                ctx.granted_scopes = effective_granted
                ctx.audit_tags.append("scope_source:agent_registry")
            except (KeyError, ImportError, Exception):
                pass

        missing = check_scopes(effective_granted, required_scopes)
        ctx.missing_scopes = missing

        if missing:
            ctx.denied_reason = f"Missing required scopes: {missing}"
            raise RBACError(
                ctx.denied_reason,
                required=list(required_scopes),
                granted=effective_granted,
                persona_id=persona_id,
                agent_id=agent_id,
                bulletrain_role=bulletrain_role,
            )
        ctx.audit_tags.append(f"scopes_ok:{len(required_scopes)}")

    ctx.allowed = True
    LOGGER.debug(
        "RBAC allowed agent=%s persona=%s role=%s tags=%s",
        agent_id,
        persona_id,
        bulletrain_role,
        ctx.audit_tags,
    )
    return ctx


# ── Method → minimum scope requirements ──────────────────────────────────────

# Maps well-known RPC method names (or prefixes) to the minimum set of FHIR /
# clinical scopes required to invoke them.  Agents may enforce additional
# method-specific requirements on top of these baseline requirements.
_METHOD_SCOPE_REQUIREMENTS: dict[str, list[str]] = {
    # Core A2A task protocol — any authenticated caller
    "tasks/send":            ["nexus:invoke"],
    "tasks/sendSubscribe":   ["nexus:invoke"],
    "tasks/get":             ["nexus:invoke"],
    "tasks/cancel":          ["nexus:invoke"],
    "tasks/resubscribe":     ["nexus:invoke"],
    # Triage
    "triage/assess":         ["patient.read", "encounter.write"],
    "triage/prioritise":     ["patient.read", "encounter.write"],
    # Diagnosis
    "diagnosis/analyse":     ["patient.read", "observation.read", "encounter.write"],
    "diagnosis/differential":["patient.read", "observation.read"],
    # Imaging
    "imaging/order":         ["patient.read", "diagnosticreport.write"],
    "imaging/report":        ["patient.read", "diagnosticreport.write"],
    # Pharmacy
    "pharmacy/check":        ["patient.read", "medicationrequest.read"],
    "pharmacy/dispense":     ["patient.read", "medicationrequest.write"],
    # Bed management
    "bed/assign":            ["patient.read", "encounter.write"],
    "bed/query":             ["patient.read"],
    # Discharge
    "discharge/prepare":     ["patient.read", "encounter.write", "medicationrequest.read"],
    "discharge/confirm":     ["patient.read", "encounter.write"],
    # Follow-up / care coordination
    "followup/schedule":     ["patient.read", "appointment.write"],
    "care/coordinate":       ["patient.read", "encounter.read"],
    # Avatar / consultation
    "avatar/start_session":  ["patient.read", "encounter.write"],
    "avatar/patient_message":["patient.read", "encounter.write"],
    "avatar/list_personas":  ["patient.read"],
    # Consent & governance
    "consent/check":         ["consent.read"],
    "consent/record":        ["consent.write"],
    "consent/verify":        ["consent.read"],
    # Audit
    "audit/query":           ["audit.read"],
    "audit/log":             ["audit.read"],
    # EHR
    "ehr/save":              ["patient.read", "encounter.write"],
    "ehr/getLatestNote":     ["patient.read", "encounter.read"],
    "ehr/write":             ["patient.read", "encounter.write"],
    # FHIR connector
    "fhir/get":              ["patient.read"],
    "fhir/post":             ["patient.write"],
    "fhir/put":              ["patient.write"],
    # HL7 integration
    "hl7/receive":           ["system/*.read"],
    "hl7/send":              ["system/*.write"],
    # Telemed / scribe
    "summarise":             ["encounter.read", "observation.read"],
    "transcribe":            ["encounter.write"],
    "scribe/summarise":      ["encounter.read", "observation.read"],
    "scribe/transcribe":     ["encounter.write"],
    # Surveillance / public health
    "surveillance/report":   ["patient.read", "observation.write"],
    "surveillance/analyse":  ["observation.read"],
    "osint/scan":            ["system/*.read"],
    "osint/analyse":         ["system/*.read"],
    # Billing / consent verification
    "billing/verify":        ["patient.read", "consent.read"],
    "billing/submit":        ["patient.read"],
}


def get_method_required_scopes(method: str) -> list[str]:
    """Return the minimum required scopes for *method*.

    Resolution order:
    1. Exact match in ``_METHOD_SCOPE_REQUIREMENTS``.
    2. Prefix match (e.g. ``triage/`` prefix → ``triage/assess`` scopes).
    3. Default: ``["nexus:invoke"]`` for unknown / generic methods.
    """
    m = str(method or "").strip()
    # Exact match
    exact = _METHOD_SCOPE_REQUIREMENTS.get(m)
    if exact is not None:
        return list(exact)
    # Prefix match
    m_lower = m.lower()
    for key, scopes in _METHOD_SCOPE_REQUIREMENTS.items():
        prefix = key.rstrip("*").rstrip("/").lower()
        if m_lower == prefix or m_lower.startswith(prefix + "/"):
            return list(scopes)
    return ["nexus:invoke"]


# ── Holistic method-level assessment ─────────────────────────────────────────


def assess_method_rbac(
    agent_id: str,
    method: str,
    token_claims: dict[str, Any],
) -> RBACContext:
    """Holistic RBAC check for an agent receiving a JSON-RPC call.

    Combines:

    * Per-method minimum scope requirements (from :data:`_METHOD_SCOPE_REQUIREMENTS`).
    * Persona bulletrain-role validation (when persona claims are present in *token_claims*).
    * Purpose-of-use validation (when present).

    For bare ``nexus:invoke`` tokens (no persona claims), scope enforcement
    falls back to the agent's registered ``delegated_scopes`` from
    ``config/agent_personas.json``.

    Parameters
    ----------
    agent_id:
        The receiving agent's identifier (e.g. ``"triage_agent"``).
    method:
        The JSON-RPC method being invoked (e.g. ``"triage/assess"``).
    token_claims:
        Decoded JWT payload.

    Returns
    -------
    RBACContext
        On success.  Raises :class:`RBACError` on denial.
    """
    required_scopes = get_method_required_scopes(method)

    # Strip bare nexus:invoke — it is verified by the auth gate (verify_jwt /
    # verify_service_auth) before assess_method_rbac is ever called.  Only FHIR
    # and clinical scopes require persona-level RBAC enforcement.
    persona_required = [s for s in required_scopes if s != "nexus:invoke"]

    # When persona_required is empty the method only needs nexus:invoke (e.g.
    # tasks/get, tasks/cancel) — pass an empty required list so enforce_rbac
    # skips the scope check and returns success for any valid authenticated token.
    ctx = enforce_rbac(
        token_claims,
        required_scopes=persona_required,
        agent_id=agent_id,
    )
    ctx.method = method
    return ctx

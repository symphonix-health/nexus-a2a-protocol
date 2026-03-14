"""GHARRA trust validation for Nexus route admission.

Validates that GHARRA-resolved agent records satisfy trust requirements
before Nexus opens a transport connection.  This module does NOT perform
discovery — it validates metadata already resolved by BulletTrain via GHARRA.

Trust checks:
1. Agent record is active
2. Agent name exists and is well-formed (.health namespace)
3. Namespace delegation chain is valid (zone → trust_anchor)
4. Trust anchors match known/configured anchors
5. JWKS URI is well-formed (when present)
6. Certificate-bound token rules are satisfiable
7. Thumbprint policy is consistent
8. Policy tags allow the requested operation
9. Jurisdiction / data-residency constraints are satisfied
10. Federated records have validated trust anchors
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse
from typing import Any

from .gharra_models import GharraAuthentication, GharraRecord

logger = logging.getLogger(__name__)

# Regex for valid .health namespace names:
# <agent>.<org>.<country>.health  (minimum 3 segments ending in .health)
_HEALTH_NAME_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?){2,}\.health$"
)

# Minimum zone depth: <org>.<country>.health (or just <country>.health)
_ZONE_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?)*\.health$"
)

# Valid thumbprint policies
_VALID_THUMBPRINT_POLICIES = {"", "cnf.x5t#S256"}


def _env_set(name: str) -> set[str]:
    """Load a comma-separated env var into a set of stripped tokens."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return set()
    return {token.strip() for token in raw.split(",") if token.strip()}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class GharraTrustError(Exception):
    """Raised when GHARRA trust validation fails."""

    def __init__(self, message: str, *, check: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.check = check
        self.details = details or {}


# ---------------------------------------------------------------------------
# Individual validation checks
# ---------------------------------------------------------------------------


def validate_agent_name(agent_name: str) -> list[str]:
    """Validate that the agent name conforms to .health namespace rules.

    Returns a list of failure reasons (empty = valid).
    """
    reasons: list[str] = []
    if not agent_name:
        reasons.append("agent_name is empty")
        return reasons

    # Allow relaxed names when strict namespace validation is off
    if not _env_bool("NEXUS_GHARRA_STRICT_NAMESPACE", False):
        return reasons

    name_lower = agent_name.lower()
    if not _HEALTH_NAME_RE.match(name_lower):
        reasons.append(
            f"agent_name '{agent_name}' does not match .health namespace pattern "
            "(<agent>.<org>.<country>.health)"
        )
    return reasons


def validate_zone_delegation(agent_name: str, zone: str, trust_anchor: str) -> list[str]:
    """Validate that the zone delegation chain is consistent.

    Checks:
    - zone is non-empty and well-formed
    - agent_name belongs to (ends with) the zone
    - trust_anchor is a parent zone or the zone itself
    """
    reasons: list[str] = []
    if not zone:
        reasons.append("zone is empty")
        return reasons

    zone_lower = zone.lower()
    name_lower = agent_name.lower() if agent_name else ""

    # Zone format validation (relaxed unless strict)
    if _env_bool("NEXUS_GHARRA_STRICT_NAMESPACE", False):
        if not _ZONE_RE.match(zone_lower):
            reasons.append(f"zone '{zone}' does not match .health zone pattern")

    # Agent name must belong to zone (name ends with .zone or name == zone)
    if name_lower and zone_lower:
        if not name_lower.endswith(f".{zone_lower}") and name_lower != zone_lower:
            reasons.append(
                f"agent_name '{agent_name}' does not belong to zone '{zone}'"
            )

    # Trust anchor must be a parent of or equal to the zone
    if trust_anchor:
        anchor_lower = trust_anchor.lower()
        if not zone_lower.endswith(f".{anchor_lower}") and zone_lower != anchor_lower:
            reasons.append(
                f"trust_anchor '{trust_anchor}' is not a parent of zone '{zone}'"
            )
    else:
        reasons.append("trust_anchor is empty")

    return reasons


def validate_trust_anchors(trust_anchor: str) -> list[str]:
    """Validate that the trust anchor is in the set of known/allowed anchors.

    Known anchors are loaded from NEXUS_GHARRA_TRUSTED_ANCHORS env var.
    If the env var is unset, all anchors are accepted (open trust model for dev).
    """
    reasons: list[str] = []
    trusted = _env_set("NEXUS_GHARRA_TRUSTED_ANCHORS")
    if not trusted:
        # Open trust in dev mode — no anchor restrictions
        return reasons

    if not trust_anchor:
        reasons.append("trust_anchor is empty but trusted anchors are configured")
        return reasons

    # Check if trust_anchor matches or is a child of any trusted anchor
    anchor_lower = trust_anchor.lower()
    for known in trusted:
        known_lower = known.lower()
        if anchor_lower == known_lower or anchor_lower.endswith(f".{known_lower}"):
            return reasons

    reasons.append(
        f"trust_anchor '{trust_anchor}' is not in trusted set: {sorted(trusted)}"
    )
    return reasons


def validate_jwks_uri(jwks_uri: str | None) -> list[str]:
    """Validate that the JWKS URI (when present) is well-formed HTTPS.

    Returns a list of failure reasons (empty = valid or absent).
    """
    reasons: list[str] = []
    if not jwks_uri:
        return reasons

    try:
        parsed = urlparse(jwks_uri)
    except Exception:
        reasons.append(f"jwks_uri '{jwks_uri}' is not a valid URL")
        return reasons

    if parsed.scheme not in ("https", "http"):
        reasons.append(f"jwks_uri scheme must be https (got '{parsed.scheme}')")

    if not parsed.hostname:
        reasons.append("jwks_uri has no hostname")

    # In strict mode, require HTTPS
    if _env_bool("NEXUS_GHARRA_STRICT_JWKS", False) and parsed.scheme != "https":
        reasons.append("jwks_uri must use HTTPS in strict mode")

    return reasons


def validate_thumbprint_policy(auth: GharraAuthentication) -> list[str]:
    """Validate that the thumbprint_policy value is recognized.

    The only supported policy is cnf.x5t#S256 (RFC 8705).
    """
    reasons: list[str] = []
    policy = auth.thumbprint_policy
    if policy and policy not in _VALID_THUMBPRINT_POLICIES:
        reasons.append(
            f"unrecognized thumbprint_policy '{policy}'; "
            f"supported: {sorted(_VALID_THUMBPRINT_POLICIES - {''})}"
        )

    # If thumbprint_policy is set, cert_bound_tokens should be required
    if policy == "cnf.x5t#S256" and not auth.cert_bound_tokens_required:
        reasons.append(
            "thumbprint_policy is 'cnf.x5t#S256' but cert_bound_tokens_required is false"
        )

    return reasons


def validate_cert_binding(
    auth: GharraAuthentication,
    *,
    local_mtls_available: bool = False,
    local_cert_thumbprint: str | None = None,
) -> list[str]:
    """Validate that certificate-bound token requirements can be satisfied.

    This checks whether Nexus can satisfy the target agent's auth requirements.
    """
    reasons: list[str] = []

    if auth.mtls_required and not local_mtls_available:
        if _env_bool("NEXUS_GHARRA_ENFORCE_MTLS", False):
            reasons.append(
                "target agent requires mTLS but local mTLS identity is not available"
            )

    if auth.cert_bound_tokens_required:
        if not local_cert_thumbprint and _env_bool("NEXUS_CERT_BOUND_TOKENS_REQUIRED", False):
            reasons.append(
                "target agent requires cert-bound tokens (cnf.x5t#S256) "
                "but no local certificate thumbprint is available"
            )

    return reasons


def validate_policy_tags(
    policy_tags: tuple[str, ...] | list[str],
    *,
    method: str | None = None,
) -> list[str]:
    """Validate that policy tags allow the requested operation.

    Denied tags are loaded from NEXUS_GHARRA_DENIED_TAGS env var.
    Required tags are loaded from NEXUS_GHARRA_REQUIRED_TAGS env var.
    """
    reasons: list[str] = []
    tags_set = {str(t).lower() for t in policy_tags}

    denied = _env_set("NEXUS_GHARRA_DENIED_TAGS")
    if denied:
        blocked = tags_set & {d.lower() for d in denied}
        if blocked:
            reasons.append(f"policy_tags {sorted(blocked)} are denied by local policy")

    required = _env_set("NEXUS_GHARRA_REQUIRED_TAGS")
    if required:
        missing = {r.lower() for r in required} - tags_set
        if missing:
            reasons.append(f"required policy_tags {sorted(missing)} are missing")

    return reasons


def validate_jurisdiction(
    jurisdiction: str,
    policy_tags: tuple[str, ...] | list[str],
) -> list[str]:
    """Validate jurisdiction / data-residency constraints.

    NEXUS_GHARRA_ALLOWED_JURISDICTIONS: comma-separated set of allowed jurisdictions.
    If unset, all jurisdictions are allowed (open model).

    When a GHARRA record declares "phi" in policy_tags, jurisdiction enforcement
    is stricter — the jurisdiction MUST be in the allowed set.
    """
    reasons: list[str] = []
    allowed = _env_set("NEXUS_GHARRA_ALLOWED_JURISDICTIONS")
    if not allowed:
        return reasons

    tags_set = {str(t).lower() for t in policy_tags}

    if not jurisdiction:
        # PHI agents without jurisdiction should be denied when restrictions exist
        if "phi" in tags_set:
            reasons.append(
                "agent handles PHI but declares no jurisdiction; "
                "cannot verify data-residency compliance"
            )
        return reasons

    jurisdiction_lower = jurisdiction.lower()
    allowed_lower = {j.lower() for j in allowed}
    if jurisdiction_lower not in allowed_lower:
        reasons.append(
            f"jurisdiction '{jurisdiction}' is not in allowed set: {sorted(allowed)}"
        )

    return reasons


def validate_record_status(record: GharraRecord) -> list[str]:
    """Validate that the GHARRA record is active."""
    reasons: list[str] = []
    if record.status != "active":
        reasons.append(f"GHARRA record status is '{record.status}', expected 'active'")
    return reasons


def validate_federation(record: GharraRecord) -> list[str]:
    """Validate trust for federated records.

    Federated agents (from a peer GHARRA registry) require trust anchor
    validation to proceed.
    """
    reasons: list[str] = []
    if record.federated:
        # Federated records must have a trust anchor that is known
        anchor_reasons = validate_trust_anchors(record.trust_anchor)
        if anchor_reasons:
            reasons.append("federated agent failed trust anchor validation")
            reasons.extend(anchor_reasons)
    return reasons


# ---------------------------------------------------------------------------
# Composite validation
# ---------------------------------------------------------------------------


def validate_gharra_record(
    record: GharraRecord,
    *,
    local_mtls_available: bool = False,
    local_cert_thumbprint: str | None = None,
    method: str | None = None,
) -> tuple[list[str], list[str]]:
    """Run all GHARRA trust validation checks on a record.

    Returns (reasons, warnings) — reasons is hard denials, warnings are advisory.
    Empty reasons = all checks passed.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    reasons.extend(validate_record_status(record))
    reasons.extend(validate_agent_name(record.agent_name))
    reasons.extend(
        validate_zone_delegation(record.agent_name, record.zone, record.trust_anchor)
    )
    reasons.extend(validate_trust_anchors(record.trust_anchor))

    # JWKS URI: warn in relaxed mode, deny in strict
    jwks_issues = validate_jwks_uri(record.authentication.jwks_uri)
    if _env_bool("NEXUS_GHARRA_STRICT_JWKS", False):
        reasons.extend(jwks_issues)
    else:
        warnings.extend(jwks_issues)

    # Thumbprint policy consistency
    tp_issues = validate_thumbprint_policy(record.authentication)
    if _env_bool("NEXUS_GHARRA_STRICT_THUMBPRINT", False):
        reasons.extend(tp_issues)
    else:
        warnings.extend(tp_issues)

    reasons.extend(
        validate_cert_binding(
            record.authentication,
            local_mtls_available=local_mtls_available,
            local_cert_thumbprint=local_cert_thumbprint,
        )
    )
    reasons.extend(validate_policy_tags(record.policy_tags, method=method))
    reasons.extend(validate_jurisdiction(record.jurisdiction, record.policy_tags))
    reasons.extend(validate_federation(record))

    return reasons, warnings

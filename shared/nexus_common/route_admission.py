"""GHARRA-aware route admission for Nexus transport layer.

This module implements the route admission gate that validates GHARRA metadata
before Nexus opens a transport connection to a target agent.

Nexus remains a transport and routing layer — it does NOT perform discovery or
registry lookups.  BulletTrain resolves agents via GHARRA and passes the record
to Nexus.  This module validates the record.

Route admission checks (in order):
1. Record status is active
2. Agent name is valid (.health namespace)
3. Namespace delegation is valid (zone chain)
4. Trust anchors match configured anchors
5. JWKS URI is well-formed
6. Thumbprint policy is consistent
7. Certificate-bound token rules are satisfied
8. Policy tags allow the operation
9. Jurisdiction / data-residency is allowed
10. Federated records have validated trust anchors
11. Protocol is nexus-a2a and version is compatible
12. Feature flags are supported
13. Transport endpoint is non-empty
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from .audit import AuditLogEntry, env_audit_logger
from .gharra_models import (
    GharraRecord,
    GharraRecordCache,
    RouteAdmissionResult,
    RouteDescriptor,
    get_record_cache,
    parse_gharra_record,
)
from .gharra_trust import validate_gharra_record
from .otel import start_span
from .scale_profile import SUPPORTED_FEATURE_FLAGS

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class RouteAdmissionError(Exception):
    """Raised when route admission is denied."""

    def __init__(self, message: str, *, result: RouteAdmissionResult) -> None:
        super().__init__(message)
        self.result = result


# ---------------------------------------------------------------------------
# Protocol & feature compatibility
# ---------------------------------------------------------------------------

def _validate_protocol_compatibility(record: GharraRecord) -> list[str]:
    """Check that the target agent speaks a compatible protocol and version."""
    reasons: list[str] = []
    transport = record.transport

    if transport.protocol != "nexus-a2a":
        reasons.append(
            f"unsupported protocol '{transport.protocol}', expected 'nexus-a2a'"
        )

    if transport.protocol_versions:
        supported = {"1.0", "1.1"}
        compatible = set(transport.protocol_versions) & supported
        if not compatible:
            reasons.append(
                f"no compatible protocol version: target supports "
                f"{list(transport.protocol_versions)}, local supports {sorted(supported)}"
            )

    return reasons


def _validate_feature_compatibility(record: GharraRecord) -> tuple[list[str], list[str]]:
    """Check that required feature flags are supported locally.

    Returns (reasons, warnings).
    """
    reasons: list[str] = []
    warnings: list[str] = []
    if not record.transport.feature_flags:
        return reasons, warnings

    unsupported = set(record.transport.feature_flags) - SUPPORTED_FEATURE_FLAGS
    if unsupported:
        if _env_bool("NEXUS_GHARRA_STRICT_FEATURES", False):
            reasons.append(
                f"unsupported feature flags: {sorted(unsupported)}"
            )
        else:
            warnings.append(
                f"target agent declares unsupported features: {sorted(unsupported)}"
            )
    return reasons, warnings


# ---------------------------------------------------------------------------
# Route descriptor builder
# ---------------------------------------------------------------------------

def _build_route_descriptor(record: GharraRecord) -> RouteDescriptor:
    """Build a RouteDescriptor from a validated GHARRA record."""
    return RouteDescriptor(
        agent_name=record.agent_name,
        zone=record.zone,
        trust_anchor=record.trust_anchor,
        endpoint=record.transport.endpoint,
        policy_tags=record.policy_tags,
        protocol_versions=record.transport.protocol_versions,
        feature_flags=record.transport.feature_flags,
        capabilities=record.capabilities,
        jurisdiction=record.jurisdiction,
        federated=record.federated,
    )


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

def _build_telemetry_attributes(
    *,
    record: GharraRecord,
    result: RouteAdmissionResult,
    session_id: str | None = None,
    route_source: str | None = None,
) -> dict[str, Any]:
    """Build OTel span attributes for route admission telemetry."""
    attrs: dict[str, Any] = {
        "route.source": route_source or "nexus-gateway",
        "route.target": record.transport.endpoint,
        "route.agent_name": record.agent_name,
        "route.zone": record.zone,
        "route.trust_anchor": record.trust_anchor,
        "route.policy_result": result.policy_result,
        "route.admitted": result.admitted,
        "route.check_duration_ms": result.check_duration_ms,
    }
    if session_id:
        attrs["route.session_id"] = session_id
    if record.jurisdiction:
        attrs["route.jurisdiction"] = record.jurisdiction
    if record.federated:
        attrs["route.federated"] = True
    if result.reasons:
        attrs["route.deny_reasons"] = ",".join(result.reasons)
    if result.warnings:
        attrs["route.warnings"] = ",".join(result.warnings)
    return attrs


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def _audit_route_decision(
    result: RouteAdmissionResult,
    *,
    route_source: str | None = None,
    session_id: str | None = None,
    method: str | None = None,
) -> None:
    """Emit an audit log entry for a route admission decision."""
    if not _env_bool("NEXUS_AUDIT_DECISIONS", False):
        return
    try:
        audit_logger = env_audit_logger()
        audit_logger.log(
            AuditLogEntry(
                actor=route_source or "nexus-gateway",
                action="route_admission",
                resource=result.agent_name,
                outcome="success" if result.admitted else "denied",
                reason="; ".join(result.reasons) if result.reasons else None,
                method=method,
            )
        )
    except Exception:
        logger.debug("Failed to emit route admission audit log", exc_info=True)


# ---------------------------------------------------------------------------
# Scale-profile extension
# ---------------------------------------------------------------------------

def build_gharra_scale_extension(record: GharraRecord) -> dict[str, Any]:
    """Build a scale-profile extension block from GHARRA routing metadata.

    This can be injected into the JSON-RPC params.scale_profile to carry
    GHARRA context through the request lifecycle.
    """
    return {
        "gharra": {
            "agent_name": record.agent_name,
            "zone": record.zone,
            "trust_anchor": record.trust_anchor,
            "jurisdiction": record.jurisdiction,
            "federated": record.federated,
            "protocol_versions": list(record.transport.protocol_versions),
            "feature_flags": list(record.transport.feature_flags),
        }
    }


# ---------------------------------------------------------------------------
# Core admission evaluation
# ---------------------------------------------------------------------------

def evaluate_route_admission(
    record: GharraRecord,
    *,
    local_mtls_available: bool = False,
    local_cert_thumbprint: str | None = None,
    method: str | None = None,
    session_id: str | None = None,
    route_source: str | None = None,
) -> RouteAdmissionResult:
    """Evaluate route admission for a GHARRA-resolved agent record.

    This is the main entry point for route admission checks.
    Returns a RouteAdmissionResult (always — does not raise).
    """
    t0 = time.monotonic()
    reasons: list[str] = []
    warnings: list[str] = []

    # 1-10: Core GHARRA trust validation
    trust_reasons, trust_warnings = validate_gharra_record(
        record,
        local_mtls_available=local_mtls_available,
        local_cert_thumbprint=local_cert_thumbprint,
        method=method,
    )
    reasons.extend(trust_reasons)
    warnings.extend(trust_warnings)

    # 11: Protocol compatibility
    reasons.extend(_validate_protocol_compatibility(record))

    # 12: Feature flag compatibility
    feature_reasons, feature_warnings = _validate_feature_compatibility(record)
    reasons.extend(feature_reasons)
    warnings.extend(feature_warnings)

    # 13: Transport endpoint must be non-empty
    if not record.transport.endpoint:
        reasons.append("transport endpoint is empty")

    admitted = len(reasons) == 0
    policy_result = "admit" if admitted else "deny"
    if admitted and warnings:
        policy_result = "warn"

    descriptor = _build_route_descriptor(record) if admitted else None
    check_duration_ms = (time.monotonic() - t0) * 1000.0

    result = RouteAdmissionResult(
        admitted=admitted,
        agent_name=record.agent_name,
        zone=record.zone,
        trust_anchor=record.trust_anchor,
        reasons=reasons,
        warnings=warnings,
        policy_result=policy_result,
        descriptor=descriptor,
        check_duration_ms=check_duration_ms,
    )

    # Emit telemetry span
    telemetry_attrs = _build_telemetry_attributes(
        record=record,
        result=result,
        session_id=session_id,
        route_source=route_source,
    )
    with start_span("gharra.route_admission", attributes=telemetry_attrs):
        if admitted:
            logger.info(
                "Route admitted: %s → %s (zone=%s, anchor=%s, %.1fms)",
                route_source or "nexus",
                record.agent_name,
                record.zone,
                record.trust_anchor,
                check_duration_ms,
            )
        else:
            logger.warning(
                "Route denied: %s → %s: %s (%.1fms)",
                route_source or "nexus",
                record.agent_name,
                "; ".join(reasons),
                check_duration_ms,
            )

    if warnings:
        logger.info(
            "Route admission warnings for %s: %s",
            record.agent_name,
            "; ".join(warnings),
        )

    # Emit audit log
    _audit_route_decision(result, route_source=route_source, session_id=session_id, method=method)

    # Cache admitted records
    if admitted:
        get_record_cache().put(record)

    return result


def evaluate_route_admission_from_dict(
    gharra_data: dict[str, Any],
    *,
    local_mtls_available: bool = False,
    local_cert_thumbprint: str | None = None,
    method: str | None = None,
    session_id: str | None = None,
    route_source: str | None = None,
    use_cache: bool = True,
) -> RouteAdmissionResult:
    """Parse a GHARRA record dict and evaluate route admission.

    Convenience wrapper for callers that receive raw dicts from BulletTrain.
    When use_cache=True, returns a cached admission for recently-validated records.
    """
    agent_name = str(gharra_data.get("agent_name") or gharra_data.get("name") or "").strip()

    if use_cache and agent_name:
        cached_record = get_record_cache().get(agent_name)
        if cached_record is not None:
            logger.debug("Using cached GHARRA record for %s", agent_name)
            return RouteAdmissionResult(
                admitted=True,
                agent_name=cached_record.agent_name,
                zone=cached_record.zone,
                trust_anchor=cached_record.trust_anchor,
                policy_result="admit",
                descriptor=_build_route_descriptor(cached_record),
                check_duration_ms=0.0,
            )

    record = parse_gharra_record(gharra_data)
    return evaluate_route_admission(
        record,
        local_mtls_available=local_mtls_available,
        local_cert_thumbprint=local_cert_thumbprint,
        method=method,
        session_id=session_id,
        route_source=route_source,
    )


def enforce_route_admission(
    record: GharraRecord,
    *,
    local_mtls_available: bool = False,
    local_cert_thumbprint: str | None = None,
    method: str | None = None,
    session_id: str | None = None,
    route_source: str | None = None,
) -> RouteAdmissionResult:
    """Evaluate and enforce route admission — raises RouteAdmissionError on deny.

    Use this in gateway proxy paths where denial should abort the request.
    """
    result = evaluate_route_admission(
        record,
        local_mtls_available=local_mtls_available,
        local_cert_thumbprint=local_cert_thumbprint,
        method=method,
        session_id=session_id,
        route_source=route_source,
    )
    if not result.admitted:
        raise RouteAdmissionError(
            f"Route denied to {record.agent_name}: {'; '.join(result.reasons)}",
            result=result,
        )
    return result

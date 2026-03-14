"""GHARRA (Global Healthcare Agent Registry & Routing Authority) data models.

These models represent the metadata Nexus receives from GHARRA via BulletTrain
to validate route admission.  Nexus does NOT own discovery or registry logic —
it only validates trust and routing metadata before opening a connection.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GharraAuthentication:
    """Authentication requirements declared in a GHARRA agent record."""

    mtls_required: bool = False
    jwks_uri: str | None = None
    cert_bound_tokens_required: bool = False
    thumbprint_policy: str = ""  # e.g. "cnf.x5t#S256"


@dataclass(frozen=True)
class GharraTransport:
    """Transport metadata from a GHARRA agent record."""

    endpoint: str = ""
    protocol: str = "nexus-a2a"
    protocol_versions: tuple[str, ...] = ("1.0",)
    feature_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class GharraRecord:
    """Resolved GHARRA agent record passed to Nexus for route admission.

    BulletTrain resolves the agent via GHARRA and passes this record.
    Nexus validates it before opening a transport connection.
    """

    agent_name: str
    zone: str
    trust_anchor: str
    transport: GharraTransport
    authentication: GharraAuthentication
    capabilities: tuple[str, ...] = ()
    policy_tags: tuple[str, ...] = ()
    jurisdiction: str = ""
    status: str = "active"
    federated: bool = False
    last_verified_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "zone": self.zone,
            "trust_anchor": self.trust_anchor,
            "transport": {
                "endpoint": self.transport.endpoint,
                "protocol": self.transport.protocol,
                "protocol_versions": list(self.transport.protocol_versions),
                "feature_flags": list(self.transport.feature_flags),
            },
            "authentication": {
                "mtls_required": self.authentication.mtls_required,
                "jwks_uri": self.authentication.jwks_uri,
                "cert_bound_tokens_required": self.authentication.cert_bound_tokens_required,
                "thumbprint_policy": self.authentication.thumbprint_policy,
            },
            "capabilities": list(self.capabilities),
            "policy_tags": list(self.policy_tags),
            "jurisdiction": self.jurisdiction,
            "status": self.status,
            "federated": self.federated,
            "last_verified_at": self.last_verified_at,
        }


@dataclass(frozen=True)
class RouteDescriptor:
    """Extended route descriptor carrying GHARRA metadata alongside Nexus routing info."""

    agent_name: str
    zone: str
    trust_anchor: str
    endpoint: str = ""
    policy_tags: tuple[str, ...] = ()
    protocol_versions: tuple[str, ...] = ()
    feature_flags: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    jurisdiction: str = ""
    federated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "zone": self.zone,
            "trust_anchor": self.trust_anchor,
            "endpoint": self.endpoint,
            "policy_tags": list(self.policy_tags),
            "protocol_versions": list(self.protocol_versions),
            "feature_flags": list(self.feature_flags),
            "capabilities": list(self.capabilities),
            "jurisdiction": self.jurisdiction,
            "federated": self.federated,
        }


@dataclass
class RouteAdmissionResult:
    """Outcome of GHARRA-based route admission checks."""

    admitted: bool
    agent_name: str
    zone: str
    trust_anchor: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    policy_result: str = "admit"  # "admit" | "deny" | "warn"
    descriptor: RouteDescriptor | None = None
    check_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "admitted": self.admitted,
            "agent_name": self.agent_name,
            "zone": self.zone,
            "trust_anchor": self.trust_anchor,
            "reasons": self.reasons,
            "policy_result": self.policy_result,
            "descriptor": self.descriptor.to_dict() if self.descriptor else None,
            "check_duration_ms": round(self.check_duration_ms, 2),
        }
        if self.warnings:
            d["warnings"] = self.warnings
        return d


# ---------------------------------------------------------------------------
# TTL-based record cache
# ---------------------------------------------------------------------------

class GharraRecordCache:
    """In-memory TTL cache for parsed GHARRA records.

    Prevents re-parsing and re-validating the same record within the TTL window.
    Thread-safe for single-process use (GIL-protected dict ops).
    """

    def __init__(self, ttl_seconds: float = 60.0, max_entries: int = 1024) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._cache: dict[str, tuple[GharraRecord, float]] = {}

    def get(self, agent_name: str) -> GharraRecord | None:
        entry = self._cache.get(agent_name)
        if entry is None:
            return None
        record, expires_at = entry
        if time.monotonic() > expires_at:
            self._cache.pop(agent_name, None)
            return None
        return record

    def put(self, record: GharraRecord) -> None:
        if len(self._cache) >= self._max:
            self._evict_expired()
        if len(self._cache) >= self._max:
            # Evict oldest entry
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key, None)
        self._cache[record.agent_name] = (record, time.monotonic() + self._ttl)

    def invalidate(self, agent_name: str) -> None:
        self._cache.pop(agent_name, None)

    def clear(self) -> None:
        self._cache.clear()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired:
            self._cache.pop(k, None)

    @property
    def size(self) -> int:
        return len(self._cache)


# Module-level singleton cache
_default_cache = GharraRecordCache()


def get_record_cache() -> GharraRecordCache:
    """Return the module-level GHARRA record cache."""
    return _default_cache


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_gharra_record(data: dict[str, Any]) -> GharraRecord:
    """Parse a GHARRA agent record dict (as received from BulletTrain) into a GharraRecord."""
    transport_raw = data.get("transport") or {}
    auth_raw = data.get("authentication") or {}

    transport = GharraTransport(
        endpoint=str(transport_raw.get("endpoint") or "").strip(),
        protocol=str(transport_raw.get("protocol") or "nexus-a2a").strip(),
        protocol_versions=tuple(str(v) for v in (transport_raw.get("protocol_versions") or ["1.0"])),
        feature_flags=tuple(str(f) for f in (transport_raw.get("feature_flags") or [])),
    )
    authentication = GharraAuthentication(
        mtls_required=bool(auth_raw.get("mtls_required")),
        jwks_uri=str(auth_raw.get("jwks_uri") or "").strip() or None,
        cert_bound_tokens_required=bool(auth_raw.get("cert_bound_tokens_required")),
        thumbprint_policy=str(auth_raw.get("thumbprint_policy") or "").strip(),
    )

    return GharraRecord(
        agent_name=str(data.get("agent_name") or data.get("name") or "").strip(),
        zone=str(data.get("zone") or "").strip(),
        trust_anchor=str(data.get("trust_anchor") or "").strip(),
        transport=transport,
        authentication=authentication,
        capabilities=tuple(str(c) for c in (data.get("capabilities") or [])),
        policy_tags=tuple(str(t) for t in (data.get("policy_tags") or [])),
        jurisdiction=str(data.get("jurisdiction") or "").strip(),
        status=str(data.get("status") or "active").strip(),
        federated=bool(data.get("federated")),
        last_verified_at=str(data.get("last_verified_at") or "").strip() or None,
    )

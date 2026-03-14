"""Tests for GHARRA route admission logic."""

from __future__ import annotations

import pytest

from shared.nexus_common.gharra_models import (
    GharraAuthentication,
    GharraRecord,
    GharraRecordCache,
    GharraTransport,
    RouteDescriptor,
    parse_gharra_record,
)
from shared.nexus_common.route_admission import (
    RouteAdmissionError,
    build_gharra_scale_extension,
    enforce_route_admission,
    evaluate_route_admission,
    evaluate_route_admission_from_dict,
)


def _make_record(**overrides) -> GharraRecord:
    defaults = dict(
        agent_name="patient-registry.nhs.uk.health",
        zone="nhs.uk.health",
        trust_anchor="uk.health",
        transport=GharraTransport(
            endpoint="https://router.nhs.uk/a2a/patient-registry",
            protocol="nexus-a2a",
            protocol_versions=("1.0", "1.1"),
            feature_flags=("routing.v1",),
        ),
        authentication=GharraAuthentication(
            mtls_required=False,
            jwks_uri="https://auth.nhs.uk/.well-known/jwks.json",
            cert_bound_tokens_required=False,
        ),
        capabilities=("FHIR.Patient.read",),
        policy_tags=("phi", "uk-only"),
        jurisdiction="UK",
        status="active",
        federated=False,
    )
    defaults.update(overrides)
    return GharraRecord(**defaults)


def _make_dict(**overrides) -> dict:
    base: dict = {
        "agent_name": "patient-registry.nhs.uk.health",
        "zone": "nhs.uk.health",
        "trust_anchor": "uk.health",
        "transport": {
            "endpoint": "https://router.nhs.uk/a2a/patient-registry",
            "protocol": "nexus-a2a",
            "protocol_versions": ["1.0", "1.1"],
            "feature_flags": ["routing.v1"],
        },
        "authentication": {
            "mtls_required": False,
            "jwks_uri": "https://auth.nhs.uk/.well-known/jwks.json",
            "cert_bound_tokens_required": False,
        },
        "capabilities": ["FHIR.Patient.read"],
        "policy_tags": ["phi", "uk-only"],
        "jurisdiction": "UK",
        "status": "active",
        "federated": False,
    }
    base.update(overrides)
    return base


def _clean_env(monkeypatch):
    """Clear all GHARRA env vars."""
    for var in (
        "NEXUS_GHARRA_STRICT_NAMESPACE",
        "NEXUS_GHARRA_TRUSTED_ANCHORS",
        "NEXUS_GHARRA_DENIED_TAGS",
        "NEXUS_GHARRA_REQUIRED_TAGS",
        "NEXUS_GHARRA_STRICT_FEATURES",
        "NEXUS_GHARRA_ALLOWED_JURISDICTIONS",
        "NEXUS_GHARRA_STRICT_JWKS",
        "NEXUS_GHARRA_STRICT_THUMBPRINT",
        "NEXUS_AUDIT_DECISIONS",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# evaluate_route_admission
# ---------------------------------------------------------------------------


class TestEvaluateRouteAdmission:
    def test_admit_valid_record(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record()
        result = evaluate_route_admission(record)
        assert result.admitted is True
        assert result.policy_result == "admit"
        assert result.descriptor is not None
        assert result.descriptor.agent_name == record.agent_name
        assert result.descriptor.zone == "nhs.uk.health"
        assert result.descriptor.endpoint == record.transport.endpoint
        assert result.check_duration_ms >= 0

    def test_descriptor_carries_capabilities(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(capabilities=("FHIR.Patient.read",))
        result = evaluate_route_admission(record)
        assert result.admitted
        assert "FHIR.Patient.read" in result.descriptor.capabilities

    def test_descriptor_carries_jurisdiction(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(jurisdiction="UK")
        result = evaluate_route_admission(record)
        assert result.descriptor.jurisdiction == "UK"

    def test_deny_inactive_status(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(status="revoked")
        result = evaluate_route_admission(record)
        assert result.admitted is False
        assert result.policy_result == "deny"
        assert any("revoked" in r for r in result.reasons)

    def test_deny_empty_endpoint(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(
            transport=GharraTransport(
                endpoint="",
                protocol="nexus-a2a",
                protocol_versions=("1.0",),
            )
        )
        result = evaluate_route_admission(record)
        assert result.admitted is False
        assert any("endpoint" in r for r in result.reasons)

    def test_deny_unsupported_protocol(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(
            transport=GharraTransport(
                endpoint="https://example.com/rpc",
                protocol="grpc",
                protocol_versions=("1.0",),
            )
        )
        result = evaluate_route_admission(record)
        assert result.admitted is False
        assert any("protocol" in r for r in result.reasons)

    def test_deny_incompatible_version(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(
            transport=GharraTransport(
                endpoint="https://example.com/rpc",
                protocol="nexus-a2a",
                protocol_versions=("99.0",),
            )
        )
        result = evaluate_route_admission(record)
        assert result.admitted is False
        assert any("version" in r for r in result.reasons)

    def test_deny_untrusted_anchor(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("NEXUS_GHARRA_TRUSTED_ANCHORS", "uk.health")
        record = _make_record(
            trust_anchor="ru.health",
            zone="org.ru.health",
            agent_name="agent.org.ru.health",
        )
        result = evaluate_route_admission(record)
        assert result.admitted is False

    def test_deny_zone_mismatch(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(
            agent_name="agent.us.health",
            zone="nhs.uk.health",
        )
        result = evaluate_route_admission(record)
        assert result.admitted is False
        assert any("does not belong" in r for r in result.reasons)

    def test_deny_policy_tags(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("NEXUS_GHARRA_DENIED_TAGS", "restricted")
        record = _make_record(policy_tags=("phi", "restricted"))
        result = evaluate_route_admission(record)
        assert result.admitted is False

    def test_strict_features_deny(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("NEXUS_GHARRA_STRICT_FEATURES", "true")
        record = _make_record(
            transport=GharraTransport(
                endpoint="https://example.com/rpc",
                protocol="nexus-a2a",
                protocol_versions=("1.0",),
                feature_flags=("unknown.feature.v99",),
            )
        )
        result = evaluate_route_admission(record)
        assert result.admitted is False

    def test_feature_warning_not_deny_default(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(
            transport=GharraTransport(
                endpoint="https://example.com/rpc",
                protocol="nexus-a2a",
                protocol_versions=("1.0",),
                feature_flags=("unknown.feature.v99",),
            )
        )
        result = evaluate_route_admission(record)
        assert result.admitted is True
        assert result.policy_result == "warn"
        assert len(result.warnings) >= 1

    def test_deny_jurisdiction(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", "UK")
        record = _make_record(jurisdiction="US")
        result = evaluate_route_admission(record)
        assert result.admitted is False
        assert any("jurisdiction" in r for r in result.reasons)

    def test_check_duration_populated(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record()
        result = evaluate_route_admission(record)
        assert result.check_duration_ms >= 0


# ---------------------------------------------------------------------------
# evaluate_route_admission_from_dict
# ---------------------------------------------------------------------------


class TestEvaluateFromDict:
    def test_admit_from_dict(self, monkeypatch):
        _clean_env(monkeypatch)
        result = evaluate_route_admission_from_dict(
            _make_dict(), use_cache=False,
        )
        assert result.admitted is True

    def test_deny_from_dict(self, monkeypatch):
        _clean_env(monkeypatch)
        result = evaluate_route_admission_from_dict(
            _make_dict(status="inactive"), use_cache=False,
        )
        assert result.admitted is False

    def test_name_field_alias(self, monkeypatch):
        _clean_env(monkeypatch)
        data = _make_dict()
        data["name"] = data.pop("agent_name")
        result = evaluate_route_admission_from_dict(
            data, use_cache=False,
        )
        assert result.admitted is True
        assert result.agent_name == "patient-registry.nhs.uk.health"

    def test_capabilities_parsed(self, monkeypatch):
        _clean_env(monkeypatch)
        data = _make_dict(capabilities=["FHIR.Patient.read", "triage"])
        result = evaluate_route_admission_from_dict(
            data, use_cache=False,
        )
        assert result.admitted
        assert "triage" in result.descriptor.capabilities


# ---------------------------------------------------------------------------
# enforce_route_admission
# ---------------------------------------------------------------------------


class TestEnforceRouteAdmission:
    def test_enforce_passes(self, monkeypatch):
        _clean_env(monkeypatch)
        result = enforce_route_admission(_make_record())
        assert result.admitted is True

    def test_enforce_raises_on_deny(self, monkeypatch):
        _clean_env(monkeypatch)
        with pytest.raises(RouteAdmissionError) as exc_info:
            enforce_route_admission(_make_record(status="revoked"))
        assert "revoked" in str(exc_info.value)
        assert exc_info.value.result.admitted is False


# ---------------------------------------------------------------------------
# parse_gharra_record
# ---------------------------------------------------------------------------


class TestParseGharraRecord:
    def test_round_trip(self):
        data = _make_dict()
        record = parse_gharra_record(data)
        assert record.agent_name == data["agent_name"]
        assert record.zone == "nhs.uk.health"
        assert record.transport.endpoint == data["transport"]["endpoint"]
        assert record.transport.protocol == "nexus-a2a"
        assert "1.0" in record.transport.protocol_versions
        assert record.authentication.jwks_uri is not None
        assert "phi" in record.policy_tags
        assert record.jurisdiction == "UK"
        assert "FHIR.Patient.read" in record.capabilities

    def test_minimal_record(self):
        data = {
            "agent_name": "test",
            "zone": "test.health",
            "trust_anchor": "test.health",
        }
        record = parse_gharra_record(data)
        assert record.agent_name == "test"
        assert record.transport.protocol == "nexus-a2a"
        assert record.capabilities == ()
        assert record.jurisdiction == ""

    def test_to_dict_round_trip(self):
        data = _make_dict()
        record = parse_gharra_record(data)
        output = record.to_dict()
        assert output["agent_name"] == data["agent_name"]
        assert output["capabilities"] == data["capabilities"]
        assert output["jurisdiction"] == data["jurisdiction"]

    def test_thumbprint_policy_parsed(self):
        data = _make_dict()
        data["authentication"]["thumbprint_policy"] = "cnf.x5t#S256"
        record = parse_gharra_record(data)
        assert record.authentication.thumbprint_policy == "cnf.x5t#S256"


# ---------------------------------------------------------------------------
# GharraRecordCache
# ---------------------------------------------------------------------------


class TestGharraRecordCache:
    def test_put_and_get(self):
        cache = GharraRecordCache(ttl_seconds=60.0)
        record = _make_record()
        cache.put(record)
        assert cache.get(record.agent_name) is record

    def test_miss_returns_none(self):
        cache = GharraRecordCache()
        assert cache.get("nonexistent") is None

    def test_invalidate(self):
        cache = GharraRecordCache()
        record = _make_record()
        cache.put(record)
        cache.invalidate(record.agent_name)
        assert cache.get(record.agent_name) is None

    def test_clear(self):
        cache = GharraRecordCache()
        cache.put(_make_record())
        cache.clear()
        assert cache.size == 0

    def test_max_entries_eviction(self):
        cache = GharraRecordCache(max_entries=2)
        r1 = _make_record(agent_name="a.nhs.uk.health")
        r2 = _make_record(agent_name="b.nhs.uk.health")
        r3 = _make_record(agent_name="c.nhs.uk.health")
        cache.put(r1)
        cache.put(r2)
        cache.put(r3)
        assert cache.size <= 2

    def test_expired_entry_returns_none(self):
        cache = GharraRecordCache(ttl_seconds=-1.0)
        record = _make_record()
        cache.put(record)
        # Negative TTL means always expired
        assert cache.get(record.agent_name) is None


# ---------------------------------------------------------------------------
# RouteDescriptor
# ---------------------------------------------------------------------------


class TestRouteDescriptor:
    def test_to_dict(self):
        desc = RouteDescriptor(
            agent_name="test.nhs.uk.health",
            zone="nhs.uk.health",
            trust_anchor="uk.health",
            endpoint="https://example.com/rpc",
            policy_tags=("phi",),
            protocol_versions=("1.0",),
            feature_flags=("routing.v1",),
            capabilities=("FHIR.Patient.read",),
            jurisdiction="UK",
            federated=False,
        )
        d = desc.to_dict()
        assert d["agent_name"] == "test.nhs.uk.health"
        assert d["endpoint"] == "https://example.com/rpc"
        assert d["jurisdiction"] == "UK"
        assert "phi" in d["policy_tags"]
        assert "FHIR.Patient.read" in d["capabilities"]


# ---------------------------------------------------------------------------
# RouteAdmissionResult
# ---------------------------------------------------------------------------


class TestRouteAdmissionResult:
    def test_to_dict_admit(self, monkeypatch):
        _clean_env(monkeypatch)
        result = evaluate_route_admission(_make_record())
        d = result.to_dict()
        assert d["admitted"] is True
        assert d["policy_result"] == "admit"
        assert d["descriptor"] is not None
        assert d["check_duration_ms"] >= 0

    def test_to_dict_deny(self, monkeypatch):
        _clean_env(monkeypatch)
        result = evaluate_route_admission(_make_record(status="inactive"))
        d = result.to_dict()
        assert d["admitted"] is False
        assert d["descriptor"] is None
        assert len(d["reasons"]) > 0

    def test_to_dict_with_warnings(self, monkeypatch):
        _clean_env(monkeypatch)
        record = _make_record(
            transport=GharraTransport(
                endpoint="https://example.com/rpc",
                protocol="nexus-a2a",
                protocol_versions=("1.0",),
                feature_flags=("unknown.v1",),
            )
        )
        result = evaluate_route_admission(record)
        d = result.to_dict()
        assert d["admitted"] is True
        assert "warnings" in d
        assert len(d["warnings"]) > 0


# ---------------------------------------------------------------------------
# build_gharra_scale_extension
# ---------------------------------------------------------------------------


class TestBuildGharraScaleExtension:
    def test_basic_extension(self):
        record = _make_record()
        ext = build_gharra_scale_extension(record)
        assert "gharra" in ext
        g = ext["gharra"]
        assert g["agent_name"] == record.agent_name
        assert g["zone"] == record.zone
        assert g["trust_anchor"] == record.trust_anchor
        assert g["jurisdiction"] == "UK"
        assert g["federated"] is False
        assert "1.0" in g["protocol_versions"]

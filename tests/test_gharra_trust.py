"""Tests for GHARRA trust validation (shared/nexus_common/gharra_trust.py)."""

from __future__ import annotations

from shared.nexus_common.gharra_models import (
    GharraAuthentication,
    GharraRecord,
    GharraTransport,
)
from shared.nexus_common.gharra_trust import (
    validate_agent_name,
    validate_cert_binding,
    validate_federation,
    validate_gharra_record,
    validate_jwks_uri,
    validate_jurisdiction,
    validate_policy_tags,
    validate_record_status,
    validate_thumbprint_policy,
    validate_trust_anchors,
    validate_zone_delegation,
)


def _make_record(**overrides) -> GharraRecord:
    """Helper to build a valid GharraRecord with sensible defaults."""
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


# ---------------------------------------------------------------------------
# validate_agent_name
# ---------------------------------------------------------------------------


class TestValidateAgentName:
    def test_non_empty_name_relaxed_mode(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_STRICT_NAMESPACE", raising=False)
        assert validate_agent_name("patient-registry.nhs.uk.health") == []

    def test_empty_name(self):
        reasons = validate_agent_name("")
        assert len(reasons) == 1
        assert "empty" in reasons[0]

    def test_valid_health_namespace_strict(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_STRICT_NAMESPACE", "true")
        assert validate_agent_name("patient-registry.nhs.uk.health") == []

    def test_invalid_namespace_strict(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_STRICT_NAMESPACE", "true")
        reasons = validate_agent_name("just-an-agent")
        assert len(reasons) == 1
        assert ".health" in reasons[0]

    def test_short_name_strict(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_STRICT_NAMESPACE", "true")
        reasons = validate_agent_name("agent.health")
        assert len(reasons) >= 1

    def test_relaxed_any_nonempty(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_STRICT_NAMESPACE", raising=False)
        assert validate_agent_name("local-triage") == []

    def test_deep_namespace_strict(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_STRICT_NAMESPACE", "true")
        assert validate_agent_name("radiology.st-thomas.nhs.uk.health") == []


# ---------------------------------------------------------------------------
# validate_zone_delegation
# ---------------------------------------------------------------------------


class TestValidateZoneDelegation:
    def test_valid_delegation(self):
        assert validate_zone_delegation(
            "patient-registry.nhs.uk.health", "nhs.uk.health", "uk.health"
        ) == []

    def test_empty_zone(self):
        reasons = validate_zone_delegation("agent.nhs.uk.health", "", "uk.health")
        assert any("zone is empty" in r for r in reasons)

    def test_agent_not_in_zone(self):
        reasons = validate_zone_delegation(
            "agent.different.us.health", "nhs.uk.health", "uk.health"
        )
        assert any("does not belong to zone" in r for r in reasons)

    def test_trust_anchor_not_parent_of_zone(self):
        reasons = validate_zone_delegation(
            "agent.nhs.uk.health", "nhs.uk.health", "ke.health"
        )
        assert any("not a parent of zone" in r for r in reasons)

    def test_empty_trust_anchor(self):
        reasons = validate_zone_delegation(
            "agent.nhs.uk.health", "nhs.uk.health", ""
        )
        assert any("trust_anchor is empty" in r for r in reasons)

    def test_zone_equals_anchor(self):
        assert validate_zone_delegation(
            "agent.uk.health", "uk.health", "uk.health"
        ) == []

    def test_deep_delegation(self):
        assert validate_zone_delegation(
            "mri.radiology.st-thomas.nhs.uk.health",
            "st-thomas.nhs.uk.health",
            "nhs.uk.health",
        ) == []


# ---------------------------------------------------------------------------
# validate_trust_anchors
# ---------------------------------------------------------------------------


class TestValidateTrustAnchors:
    def test_open_trust_when_no_env(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_TRUSTED_ANCHORS", raising=False)
        assert validate_trust_anchors("anything.health") == []

    def test_anchor_in_trusted_set(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_TRUSTED_ANCHORS", "uk.health,ke.health")
        assert validate_trust_anchors("uk.health") == []

    def test_child_of_trusted_anchor(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_TRUSTED_ANCHORS", "uk.health")
        assert validate_trust_anchors("nhs.uk.health") == []

    def test_anchor_not_in_set(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_TRUSTED_ANCHORS", "uk.health")
        reasons = validate_trust_anchors("us.health")
        assert len(reasons) == 1
        assert "not in trusted set" in reasons[0]

    def test_empty_anchor_with_trusted_set(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_TRUSTED_ANCHORS", "uk.health")
        reasons = validate_trust_anchors("")
        assert len(reasons) == 1

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_TRUSTED_ANCHORS", "UK.Health")
        assert validate_trust_anchors("uk.health") == []


# ---------------------------------------------------------------------------
# validate_jwks_uri
# ---------------------------------------------------------------------------


class TestValidateJwksUri:
    def test_none_is_valid(self):
        assert validate_jwks_uri(None) == []

    def test_empty_is_valid(self):
        assert validate_jwks_uri("") == []

    def test_valid_https(self):
        assert validate_jwks_uri("https://auth.nhs.uk/.well-known/jwks.json") == []

    def test_valid_http(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_STRICT_JWKS", raising=False)
        assert validate_jwks_uri("http://auth.local/jwks") == []

    def test_http_denied_in_strict(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_STRICT_JWKS", "true")
        reasons = validate_jwks_uri("http://auth.local/jwks")
        assert any("HTTPS" in r for r in reasons)

    def test_invalid_scheme(self):
        reasons = validate_jwks_uri("ftp://auth.nhs.uk/jwks")
        assert any("scheme" in r for r in reasons)

    def test_no_hostname(self):
        reasons = validate_jwks_uri("https://")
        assert any("hostname" in r for r in reasons)


# ---------------------------------------------------------------------------
# validate_thumbprint_policy
# ---------------------------------------------------------------------------


class TestValidateThumbprintPolicy:
    def test_empty_policy_valid(self):
        auth = GharraAuthentication(thumbprint_policy="")
        assert validate_thumbprint_policy(auth) == []

    def test_cnf_x5t_valid_with_cert_bound(self):
        auth = GharraAuthentication(
            thumbprint_policy="cnf.x5t#S256",
            cert_bound_tokens_required=True,
        )
        assert validate_thumbprint_policy(auth) == []

    def test_cnf_x5t_without_cert_bound_warns(self):
        auth = GharraAuthentication(
            thumbprint_policy="cnf.x5t#S256",
            cert_bound_tokens_required=False,
        )
        reasons = validate_thumbprint_policy(auth)
        assert any("cert_bound_tokens_required" in r for r in reasons)

    def test_unknown_policy(self):
        auth = GharraAuthentication(thumbprint_policy="dpop.jkt")
        reasons = validate_thumbprint_policy(auth)
        assert any("unrecognized" in r for r in reasons)


# ---------------------------------------------------------------------------
# validate_cert_binding
# ---------------------------------------------------------------------------


class TestValidateCertBinding:
    def test_no_requirements(self):
        auth = GharraAuthentication()
        assert validate_cert_binding(auth) == []

    def test_mtls_required_not_available(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_ENFORCE_MTLS", "true")
        auth = GharraAuthentication(mtls_required=True)
        reasons = validate_cert_binding(auth, local_mtls_available=False)
        assert any("mTLS" in r for r in reasons)

    def test_mtls_required_available(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_ENFORCE_MTLS", "true")
        auth = GharraAuthentication(mtls_required=True)
        assert validate_cert_binding(auth, local_mtls_available=True) == []

    def test_cert_bound_no_thumbprint(self, monkeypatch):
        monkeypatch.setenv("NEXUS_CERT_BOUND_TOKENS_REQUIRED", "true")
        auth = GharraAuthentication(cert_bound_tokens_required=True)
        reasons = validate_cert_binding(auth, local_cert_thumbprint=None)
        assert any("cnf.x5t#S256" in r for r in reasons)

    def test_cert_bound_with_thumbprint(self, monkeypatch):
        monkeypatch.setenv("NEXUS_CERT_BOUND_TOKENS_REQUIRED", "true")
        auth = GharraAuthentication(cert_bound_tokens_required=True)
        assert validate_cert_binding(auth, local_cert_thumbprint="abc123") == []

    def test_mtls_not_enforced_by_default(self):
        auth = GharraAuthentication(mtls_required=True)
        assert validate_cert_binding(auth, local_mtls_available=False) == []


# ---------------------------------------------------------------------------
# validate_policy_tags
# ---------------------------------------------------------------------------


class TestValidatePolicyTags:
    def test_no_restrictions(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_DENIED_TAGS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_REQUIRED_TAGS", raising=False)
        assert validate_policy_tags(("phi", "uk-only")) == []

    def test_denied_tags(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_DENIED_TAGS", "restricted,classified")
        reasons = validate_policy_tags(("phi", "restricted"))
        assert any("denied" in r for r in reasons)

    def test_required_tags_present(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_REQUIRED_TAGS", "phi")
        assert validate_policy_tags(("phi", "uk-only")) == []

    def test_required_tags_missing(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_REQUIRED_TAGS", "phi,clinical")
        reasons = validate_policy_tags(("uk-only",))
        assert any("missing" in r for r in reasons)

    def test_case_insensitive_denied(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_DENIED_TAGS", "Restricted")
        reasons = validate_policy_tags(("restricted",))
        assert any("denied" in r for r in reasons)


# ---------------------------------------------------------------------------
# validate_jurisdiction
# ---------------------------------------------------------------------------


class TestValidateJurisdiction:
    def test_no_restrictions(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", raising=False)
        assert validate_jurisdiction("UK", ("phi",)) == []

    def test_allowed_jurisdiction(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", "UK,EU")
        assert validate_jurisdiction("UK", ("phi",)) == []

    def test_disallowed_jurisdiction(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", "UK,EU")
        reasons = validate_jurisdiction("US", ("phi",))
        assert any("not in allowed set" in r for r in reasons)

    def test_phi_no_jurisdiction_denied(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", "UK,EU")
        reasons = validate_jurisdiction("", ("phi",))
        assert any("no jurisdiction" in r for r in reasons)

    def test_no_phi_no_jurisdiction_ok(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", "UK,EU")
        assert validate_jurisdiction("", ("clinical",)) == []

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", "uk")
        assert validate_jurisdiction("UK", ()) == []


# ---------------------------------------------------------------------------
# validate_record_status
# ---------------------------------------------------------------------------


class TestValidateRecordStatus:
    def test_active(self):
        record = _make_record(status="active")
        assert validate_record_status(record) == []

    def test_inactive(self):
        record = _make_record(status="inactive")
        reasons = validate_record_status(record)
        assert any("inactive" in r for r in reasons)

    def test_revoked(self):
        record = _make_record(status="revoked")
        reasons = validate_record_status(record)
        assert any("revoked" in r for r in reasons)

    def test_suspended(self):
        record = _make_record(status="suspended")
        reasons = validate_record_status(record)
        assert len(reasons) == 1


# ---------------------------------------------------------------------------
# validate_federation
# ---------------------------------------------------------------------------


class TestValidateFederation:
    def test_non_federated(self):
        record = _make_record(federated=False)
        assert validate_federation(record) == []

    def test_federated_trusted_anchor(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_TRUSTED_ANCHORS", raising=False)
        record = _make_record(federated=True, trust_anchor="uk.health")
        assert validate_federation(record) == []

    def test_federated_untrusted_anchor(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_TRUSTED_ANCHORS", "uk.health")
        record = _make_record(federated=True, trust_anchor="ru.health")
        reasons = validate_federation(record)
        assert any("federated" in r for r in reasons)


# ---------------------------------------------------------------------------
# validate_gharra_record (full composite check)
# ---------------------------------------------------------------------------


class TestValidateGharraRecord:
    def test_valid_record(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_STRICT_NAMESPACE", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_TRUSTED_ANCHORS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_DENIED_TAGS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_REQUIRED_TAGS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", raising=False)
        record = _make_record()
        reasons, warnings = validate_gharra_record(record)
        assert reasons == []

    def test_multiple_failures(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_TRUSTED_ANCHORS", "uk.health")
        monkeypatch.delenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", raising=False)
        record = _make_record(
            agent_name="",
            zone="",
            trust_anchor="unknown.health",
            status="inactive",
        )
        reasons, warnings = validate_gharra_record(record)
        assert len(reasons) >= 3

    def test_valid_strict_mode(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_STRICT_NAMESPACE", "true")
        monkeypatch.delenv("NEXUS_GHARRA_TRUSTED_ANCHORS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_DENIED_TAGS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_REQUIRED_TAGS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", raising=False)
        record = _make_record()
        reasons, warnings = validate_gharra_record(record)
        assert reasons == []

    def test_jwks_warning_relaxed(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_STRICT_JWKS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_TRUSTED_ANCHORS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", raising=False)
        record = _make_record(
            authentication=GharraAuthentication(jwks_uri="ftp://bad/jwks")
        )
        reasons, warnings = validate_gharra_record(record)
        assert reasons == []
        assert any("scheme" in w for w in warnings)

    def test_jwks_strict_denial(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_STRICT_JWKS", "true")
        monkeypatch.delenv("NEXUS_GHARRA_TRUSTED_ANCHORS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", raising=False)
        record = _make_record(
            authentication=GharraAuthentication(jwks_uri="ftp://bad/jwks")
        )
        reasons, warnings = validate_gharra_record(record)
        assert any("scheme" in r for r in reasons)

    def test_jurisdiction_denial(self, monkeypatch):
        monkeypatch.setenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", "UK")
        monkeypatch.delenv("NEXUS_GHARRA_TRUSTED_ANCHORS", raising=False)
        record = _make_record(jurisdiction="US")
        reasons, warnings = validate_gharra_record(record)
        assert any("jurisdiction" in r for r in reasons)

    def test_thumbprint_warning_relaxed(self, monkeypatch):
        monkeypatch.delenv("NEXUS_GHARRA_STRICT_THUMBPRINT", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_TRUSTED_ANCHORS", raising=False)
        monkeypatch.delenv("NEXUS_GHARRA_ALLOWED_JURISDICTIONS", raising=False)
        record = _make_record(
            authentication=GharraAuthentication(
                thumbprint_policy="cnf.x5t#S256",
                cert_bound_tokens_required=False,
            )
        )
        reasons, warnings = validate_gharra_record(record)
        assert reasons == []
        assert any("cert_bound_tokens_required" in w for w in warnings)

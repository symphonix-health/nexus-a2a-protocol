"""Policy Enforcement Tests.

Verify that policy restrictions returned by GHARRA are enforced:
  - region restriction
  - protocol requirement
  - authentication requirement
  - PHI export constraints
  - data classification
  - Transfer Impact Assessments (Mitigation 1.1)
  - Rule governance manifests (Mitigation 2.1)
  - Report tamper-proofing (Mitigation 4.3)

These tests validate that GHARRA policy tags are present on agent records
and that the system respects policy constraints during resolution and routing.
"""

from __future__ import annotations

import hashlib

import httpx
import pytest

from harness.gharra_resolver import GharraResolver
from harness.signalbox_driver import SignalBoxDriver


# ── Region / Residency Restrictions ─────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_eu_residency(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent has EU residency restriction."""
    agent = await gharra.get_agent(triage_agent_id)
    residency = agent.policy_tags.get("residency", [])
    assert "EU" in residency, f"Expected EU residency, got: {residency}"


@pytest.mark.asyncio
async def test_radiology_us_residency(gharra: GharraResolver, radiology_agent_id: str):
    """US Radiology agent has US-only residency."""
    agent = await gharra.get_agent(radiology_agent_id)
    residency = agent.policy_tags.get("residency", [])
    assert "US" in residency, f"Expected US residency, got: {residency}"


@pytest.mark.asyncio
async def test_radiology_prohibited_regions(gharra: GharraResolver, radiology_agent_id: str):
    """US Radiology agent prohibits CN and RU regions."""
    agent = await gharra.get_agent(radiology_agent_id)
    prohibited = agent.policy_tags.get("prohibited_regions", [])
    assert "CN" in prohibited, f"Expected CN prohibited, got: {prohibited}"
    assert "RU" in prohibited, f"Expected RU prohibited, got: {prohibited}"


@pytest.mark.asyncio
async def test_pathology_eu_de_residency(gharra: GharraResolver, pathology_agent_id: str):
    """DE Pathology agent has EU+DE residency restriction."""
    agent = await gharra.get_agent(pathology_agent_id)
    residency = agent.policy_tags.get("residency", [])
    assert "EU" in residency
    assert "DE" in residency


# ── PHI Export Constraints ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_phi_not_allowed(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent does not allow PHI export."""
    agent = await gharra.get_agent(triage_agent_id)
    assert agent.policy_tags.get("phi_allowed") is False


@pytest.mark.asyncio
async def test_referral_phi_allowed(gharra: GharraResolver, referral_agent_id: str):
    """GB Referral agent allows PHI."""
    agent = await gharra.get_agent(referral_agent_id)
    assert agent.policy_tags.get("phi_allowed") is True


@pytest.mark.asyncio
async def test_pathology_phi_not_allowed(gharra: GharraResolver, pathology_agent_id: str):
    """DE Pathology agent does not allow PHI export."""
    agent = await gharra.get_agent(pathology_agent_id)
    assert agent.policy_tags.get("phi_allowed") is False


# ── Data Classification ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_data_classification(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent has 'confidential' data classification."""
    agent = await gharra.get_agent(triage_agent_id)
    assert agent.policy_tags.get("data_classification") == "confidential"


@pytest.mark.asyncio
async def test_referral_data_classification(gharra: GharraResolver, referral_agent_id: str):
    """GB Referral agent has 'restricted' data classification."""
    agent = await gharra.get_agent(referral_agent_id)
    assert agent.policy_tags.get("data_classification") == "restricted"


# ── Purpose of Use ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_purpose_of_use(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent allows 'treatment' purpose only."""
    agent = await gharra.get_agent(triage_agent_id)
    purposes = agent.policy_tags.get("purpose_of_use", [])
    assert "treatment" in purposes
    assert "research" not in purposes


@pytest.mark.asyncio
async def test_referral_purpose_of_use(gharra: GharraResolver, referral_agent_id: str):
    """GB Referral agent allows both 'treatment' and 'research'."""
    agent = await gharra.get_agent(referral_agent_id)
    purposes = agent.policy_tags.get("purpose_of_use", [])
    assert "treatment" in purposes
    assert "research" in purposes


# ── Protocol Requirements ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_protocol_nexus(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent requires nexus-a2a-jsonrpc protocol."""
    agent = await gharra.get_agent(triage_agent_id)
    protocols = agent.capabilities.get("protocols", [])
    assert "nexus-a2a-jsonrpc" in protocols


@pytest.mark.asyncio
async def test_referral_protocol_rest(gharra: GharraResolver, referral_agent_id: str):
    """GB Referral agent uses http-rest protocol."""
    agent = await gharra.get_agent(referral_agent_id)
    protocols = agent.capabilities.get("protocols", [])
    assert "http-rest" in protocols


# ── Authentication Requirements ────────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_mtls_required(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent requires mTLS."""
    agent = await gharra.get_agent(triage_agent_id)
    assert agent.trust.get("mtls_required") is True


@pytest.mark.asyncio
async def test_triage_dpop_binding(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent uses DPoP token binding."""
    agent = await gharra.get_agent(triage_agent_id)
    assert agent.trust.get("token_binding") == "dpop"


@pytest.mark.asyncio
async def test_triage_cert_thumbprint(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent has certificate thumbprint pinned."""
    agent = await gharra.get_agent(triage_agent_id)
    thumbprints = agent.trust.get("cert_thumbprints", [])
    assert len(thumbprints) > 0, "Must have at least one cert thumbprint"
    assert thumbprints[0].startswith("sha256:")


# ── Attestations ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_attestation(gharra: GharraResolver, triage_agent_id: str):
    """IE Triage agent has ISO27001 attestation from BSI."""
    agent = await gharra.get_agent(triage_agent_id)
    raw = agent.raw
    attestations = raw.get("attestations", [])
    assert len(attestations) > 0, "Must have at least one attestation"
    iso_att = attestations[0]
    assert iso_att.get("type") == "ISO27001"
    assert iso_att.get("issuer") == "BSI"


# ── Cross-cutting: all agents have required policy fields ──────────────

@pytest.mark.asyncio
async def test_all_agents_have_policy_tags(
    gharra: GharraResolver,
    triage_agent_id: str,
    referral_agent_id: str,
    radiology_agent_id: str,
    pathology_agent_id: str,
):
    """Every canonical agent has residency and phi_allowed policy tags."""
    for agent_id in [
        triage_agent_id,
        referral_agent_id,
        radiology_agent_id,
        pathology_agent_id,
    ]:
        agent = await gharra.get_agent(agent_id)
        assert "residency" in agent.policy_tags, f"{agent_id} missing residency"
        assert "phi_allowed" in agent.policy_tags, f"{agent_id} missing phi_allowed"


# =========================================================================
# Mitigation 1.1 -- Transfer Impact Assessment (TIA)
# =========================================================================


class TestTransferImpactAssessment:
    """Verify the TIA engine evaluates cross-border transfers correctly."""

    @pytest.mark.asyncio
    async def test_tia_intra_eu(self, gharra_url: str):
        """Intra-EU transfer (IE->DE) is permitted with low risk."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/tia/IE/DE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["permitted"] is True
        assert data["risk_level"] == "low"
        assert data["legal_basis"] == "intra_eu_eea"
        assert "Art. 44" in data["gdpr_article"]

    @pytest.mark.asyncio
    async def test_tia_eu_to_adequacy(self, gharra_url: str):
        """EU->adequacy country (IE->GB) is permitted under Art. 45."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/tia/IE/GB")
        assert resp.status_code == 200
        data = resp.json()
        assert data["permitted"] is True
        assert data["legal_basis"] == "adequacy_decision"
        assert "Art. 45" in data["gdpr_article"]

    @pytest.mark.asyncio
    async def test_tia_eu_to_nonadequacy_blocked(self, gharra_url: str):
        """EU->non-adequate country (IE->CN) is blocked without override."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/tia/IE/CN")
        assert resp.status_code == 200
        data = resp.json()
        assert data["permitted"] is False
        assert data["risk_level"] == "blocked"
        assert len(data["required_safeguards"]) > 0

    @pytest.mark.asyncio
    async def test_tia_eu_to_nonadequacy_with_scc(self, gharra_url: str):
        """EU->non-adequate with SCC override is permitted (medium risk)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/policy-engine/tia/IE/CN",
                params={"override": "SCC-2021/914"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["permitted"] is True
        assert data["risk_level"] == "medium"
        assert data["legal_basis"] == "scc"
        assert len(data["supplementary_measures"]) > 0

    @pytest.mark.asyncio
    async def test_tia_non_eu_source(self, gharra_url: str):
        """Non-EU source (US->CN) is always permitted (GDPR does not apply)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/tia/US/CN")
        assert resp.status_code == 200
        data = resp.json()
        assert data["permitted"] is True
        assert data["legal_basis"] == "non_eu_source"

    @pytest.mark.asyncio
    async def test_tia_same_jurisdiction(self, gharra_url: str):
        """Same jurisdiction (IE->IE) is trivially permitted."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/tia/IE/IE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["permitted"] is True
        assert data["legal_basis"] == "same_jurisdiction"

    @pytest.mark.asyncio
    async def test_tia_cross_registry(self, gharra_gb_url: str):
        """TIA endpoint works on sovereign registries too."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/policy-engine/tia/GB/IE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["permitted"] is True


# =========================================================================
# Mitigation 2.1 -- Policy Rule Governance
# =========================================================================


class TestRuleGovernance:
    """Verify rule governance manifests are complete and well-structured."""

    @pytest.mark.asyncio
    async def test_manifest_endpoint_returns_rules(self, gharra_url: str):
        """Rule manifest endpoint returns the full rule chain."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/rules/manifest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 9, f"Expected >= 9 rules, got {data['count']}"
        assert len(data["rules"]) == data["count"]

    @pytest.mark.asyncio
    async def test_manifest_rules_have_governance(self, gharra_url: str):
        """Every rule in the manifest has version, author, and effective_date."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/rules/manifest")
        data = resp.json()
        for rule in data["rules"]:
            assert rule["version"], f"{rule['rule_class']} missing version"
            assert rule["author"], f"{rule['rule_class']} missing author"
            assert rule["effective_date"], f"{rule['rule_class']} missing effective_date"

    @pytest.mark.asyncio
    async def test_manifest_contains_expected_rules(self, gharra_url: str):
        """Manifest contains all expected rule classes."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/rules/manifest")
        data = resp.json()
        rule_classes = {r["rule_class"] for r in data["rules"]}
        expected = {
            "AuthenticatedAccessRule",
            "EmergencyBreakGlassRule",
            "PHIBlockRule",
            "SovereigntyRule",
            "ConsentGateRule",
            "CrossBorderDataResidencyRule",
            "DataResidencyEnforcementRule",
            "PurposeOfUseValidationRule",
            "DefaultPermitReadRule",
        }
        for cls in expected:
            assert cls in rule_classes, f"Missing rule class: {cls}"

    @pytest.mark.asyncio
    async def test_manifest_legal_references(self, gharra_url: str):
        """Key rules have legal references populated."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/policy-engine/rules/manifest")
        data = resp.json()
        rules_by_class = {r["rule_class"]: r for r in data["rules"]}

        cb = rules_by_class["CrossBorderDataResidencyRule"]
        assert "GDPR" in cb["legal_reference"]
        assert "Schrems II" in cb["legal_reference"]

        bg = rules_by_class["EmergencyBreakGlassRule"]
        assert "GDPR" in bg["legal_reference"] or "HIPAA" in bg["legal_reference"]

    @pytest.mark.asyncio
    async def test_manifest_cross_registry(self, gharra_gb_url: str):
        """Rule manifest is available on sovereign registries."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/policy-engine/rules/manifest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 9


# =========================================================================
# Mitigation 4.3 -- Report Tamper-Proofing
# =========================================================================


class TestReportTamperProofing:
    """Verify report hash anchoring to the transparency ledger."""

    @pytest.mark.asyncio
    async def test_anchor_report_hash(self, gharra_url: str):
        """Anchoring a report hash returns a ledger sequence number."""
        test_hash = hashlib.sha256(b"test-report-content").hexdigest()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/ledger/anchor-report",
                params={"report_hash": test_hash, "report_type": "test"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["anchored"] is True
        assert data["report_hash"] == test_hash
        assert data["ledger_seq"] > 0

    @pytest.mark.asyncio
    async def test_verify_report_endpoint(self, gharra_url: str):
        """Verify-report endpoint responds with anchored count."""
        test_hash = hashlib.sha256(b"verify-test").hexdigest()
        async with httpx.AsyncClient() as client:
            # First anchor
            await client.post(
                f"{gharra_url}/v1/admin/ledger/anchor-report",
                params={"report_hash": test_hash, "report_type": "test"},
            )
            # Then verify
            resp = await client.get(
                f"{gharra_url}/v1/admin/ledger/verify-report",
                params={"report_hash": test_hash},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["anchored_entries_count"] > 0

    @pytest.mark.asyncio
    async def test_audit_export_has_report_hash(self, gharra_url: str):
        """The audit export endpoint includes a report_hash for tamper detection."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/ledger/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "report_hash" in data
        assert len(data["report_hash"]) == 64  # SHA-256 hex length

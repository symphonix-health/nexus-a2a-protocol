"""Policy-Aware Routing Tests (Sprint 4 — Capability 2).

Validates that the GHARRA ABAC policy engine enforces:
  - GDPR Art. 44-49 cross-border data residency adequacy
  - Consent-gated routing with purpose-of-use validation
  - Data residency zone enforcement
  - Emergency break-glass override of policy gates
  - Policy decision audit logging to transparency ledger
  - GDPR adequacy lookup API

Standards tested:
  - GDPR Art. 44-45 (Adequacy decisions)
  - GDPR Art. 46 (Appropriate safeguards: SCCs, BCRs)
  - GDPR Art. 49 (Derogations for emergencies)
  - GDPR Art. 5(1)(b) (Purpose limitation)
  - NIST SP 800-162 (ABAC)
  - ISO 27001 A.12.4 (Logging and monitoring)

Test topology:
  GHARRA Root (IE, port 8400) — hosts IE, GB, US, DE, IN, JP agents
  Test agents:
    - gharra://ie/agents/triage-e2e         (IE, EU, treatment)
    - gharra://gb/agents/referral-e2e       (GB, adequate, treatment+research)
    - gharra://us/agents/radiology-e2e      (US, non-EU non-adequate)
    - gharra://in/agents/diagnostics-e2e    (IN, non-adequate)
    - gharra://jp/agents/telemedicine-e2e   (JP, adequate)
    - gharra://ie/agents/consent-gate-e2e   (IE, consent_required, treatment only)
"""

from __future__ import annotations

import uuid

import httpx


# ── Helpers ─────────────────────────────────────────────────────────────


def _get(base_url: str, path: str, params: dict | None = None) -> httpx.Response:
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        return client.get(path, params=params or {})


def _post(base_url: str, path: str, json: dict | None = None) -> httpx.Response:
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        return client.post(
            path,
            json=json or {},
            headers={"X-Idempotency-Key": str(uuid.uuid4())},
        )


# ── GDPR Adequacy API ──────────────────────────────────────────────────


class TestGDPRAdequacyAPI:
    """Verify the GDPR adequacy lookup endpoint."""

    def test_intra_eu_adequate(self, gharra_url: str):
        """IE→DE (both EU) should be adequate."""
        resp = _get(gharra_url, "/v1/policy-engine/adequacy/IE/DE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adequate"] is True
        assert data["source_in_eu_eea"] is True
        assert data["target_in_eu_eea"] is True
        assert "Art. 44" in data["gdpr_article"]

    def test_eu_to_adequate_country(self, gharra_url: str):
        """IE→JP (JP has adequacy decision) should be adequate."""
        resp = _get(gharra_url, "/v1/policy-engine/adequacy/IE/JP")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adequate"] is True
        assert data["target_has_adequacy_decision"] is True
        assert "Art. 45" in data["gdpr_article"]

    def test_eu_to_gb_adequate(self, gharra_url: str):
        """IE→GB (post-Brexit adequacy) should be adequate."""
        resp = _get(gharra_url, "/v1/policy-engine/adequacy/IE/GB")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adequate"] is True
        assert data["target_has_adequacy_decision"] is True

    def test_eu_to_non_adequate_blocked(self, gharra_url: str):
        """IE→IN (no adequacy decision) should not be adequate."""
        resp = _get(gharra_url, "/v1/policy-engine/adequacy/IE/IN")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adequate"] is False
        assert "blocked" in data["gdpr_article"].lower() or "44" in data["gdpr_article"]

    def test_eu_to_us_not_adequate(self, gharra_url: str):
        """IE→US (no EU adequacy decision) should not be adequate."""
        resp = _get(gharra_url, "/v1/policy-engine/adequacy/IE/US")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adequate"] is False

    def test_non_eu_source_always_ok(self, gharra_url: str):
        """US→IN (non-EU source) — GDPR doesn't apply, should be adequate."""
        resp = _get(gharra_url, "/v1/policy-engine/adequacy/US/IN")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adequate"] is True
        assert data["source_in_eu_eea"] is False

    def test_same_jurisdiction(self, gharra_url: str):
        """IE→IE (same jurisdiction) should always be adequate."""
        resp = _get(gharra_url, "/v1/policy-engine/adequacy/IE/IE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adequate"] is True


# ── Cross-Border Routing Policy ────────────────────────────────────────


class TestCrossBorderRoutingPolicy:
    """Verify GDPR cross-border data residency enforcement in routing."""

    def test_eu_to_eu_routing_permitted(self, gharra_url: str):
        """Routing from IE registry to IE agent should be permitted."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://ie/agents/triage-e2e",
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:policy-test:001",
            },
        })
        assert resp.status_code == 200, f"EU→EU routing should succeed: {resp.text}"
        data = resp.json()
        assert data["resolved_target"] == "gharra://ie/agents/triage-e2e"

    def test_eu_to_adequate_routing_permitted(self, gharra_url: str):
        """Routing from IE registry to JP agent (adequate) should be permitted."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://jp/agents/telemedicine-e2e",
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:policy-test:002",
            },
        })
        assert resp.status_code == 200, f"EU→JP (adequate) routing should succeed: {resp.text}"

    def test_eu_to_gb_routing_permitted(self, gharra_url: str):
        """Routing from IE registry to GB agent (adequate) should be permitted."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://gb/agents/referral-e2e",
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:policy-test:003",
            },
        })
        assert resp.status_code == 200, f"EU→GB routing should succeed: {resp.text}"

    def test_eu_to_non_adequate_blocked(self, gharra_url: str):
        """Routing from IE registry to IN agent (no adequacy) should be blocked."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://in/agents/diagnostics-e2e",
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:policy-test:004",
            },
        })
        assert resp.status_code == 403, (
            f"EU→IN routing should be blocked (GDPR Art. 44-45): {resp.status_code} {resp.text}"
        )
        assert "adequacy" in resp.json()["detail"].lower() or "GDPR" in resp.json()["detail"]

    def test_eu_to_us_blocked(self, gharra_url: str):
        """Routing from IE registry to US agent (no adequacy) should be blocked."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://us/agents/radiology-e2e",
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:policy-test:005",
            },
        })
        assert resp.status_code == 403, (
            f"EU→US routing should be blocked: {resp.status_code} {resp.text}"
        )

    def test_eu_to_non_adequate_with_scc_override(self, gharra_url: str):
        """EU→IN with SCC adequacy override should be permitted."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://in/agents/diagnostics-e2e",
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:policy-test:006",
                "adequacy_override": "SCC-2021/914",
            },
        })
        assert resp.status_code == 200, (
            f"EU→IN with SCC override should succeed: {resp.status_code} {resp.text}"
        )


# ── Consent-Gated Routing ─────────────────────────────────────────────


class TestConsentGatedRouting:
    """Verify consent proof and purpose-of-use validation."""

    def test_consent_required_without_proof(self, gharra_url: str):
        """Routing to consent-required agent without consent proof should fail."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://ie/agents/consent-gate-e2e",
            "purpose": {
                "purpose_of_use": "treatment",
                # No consent_proof
            },
        })
        assert resp.status_code == 403, (
            f"Should require consent proof: {resp.status_code} {resp.text}"
        )
        assert "consent" in resp.json()["detail"].lower()

    def test_consent_required_with_proof(self, gharra_url: str):
        """Routing to consent-required agent with valid consent proof should succeed."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://ie/agents/consent-gate-e2e",
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:policy-test:consent-001",
            },
        })
        assert resp.status_code == 200, (
            f"Should succeed with consent proof: {resp.status_code} {resp.text}"
        )

    def test_wrong_purpose_blocked(self, gharra_url: str):
        """Routing with wrong purpose_of_use should be blocked."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://ie/agents/consent-gate-e2e",
            "purpose": {
                "purpose_of_use": "marketing",  # Agent only accepts "treatment"
                "consent_proof": "urn:consent:policy-test:consent-002",
            },
        })
        assert resp.status_code == 403, (
            f"Wrong purpose should be blocked: {resp.status_code} {resp.text}"
        )
        detail = resp.json()["detail"].lower()
        assert "purpose" in detail or "marketing" in detail

    def test_no_purpose_blocked_when_required(self, gharra_url: str):
        """Routing without purpose to agent that requires it should be blocked."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://ie/agents/consent-gate-e2e",
            # No purpose at all
        })
        assert resp.status_code == 403, (
            f"Missing purpose should be blocked: {resp.status_code} {resp.text}"
        )


# ── Emergency Break-Glass ─────────────────────────────────────────────


class TestEmergencyBreakGlass:
    """Verify emergency break-glass overrides policy gates."""

    def test_emergency_overrides_gdpr_block(self, gharra_url: str):
        """Emergency routing to non-adequate jurisdiction should succeed."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://in/agents/diagnostics-e2e",
            "workload": {
                "priority": "emergency",
            },
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:emergency:vital-interest",
            },
        })
        assert resp.status_code == 200, (
            f"Emergency should override GDPR block: {resp.status_code} {resp.text}"
        )

    def test_emergency_overrides_consent_gate(self, gharra_url: str):
        """Emergency routing without consent proof should succeed."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "gharra://ie/agents/consent-gate-e2e",
            "workload": {
                "priority": "emergency",
            },
        })
        assert resp.status_code == 200, (
            f"Emergency should override consent gate: {resp.status_code} {resp.text}"
        )


# ── Policy Evaluation API ─────────────────────────────────────────────


class TestPolicyEvaluationAPI:
    """Verify the policy evaluation endpoint for dry-run testing."""

    def test_evaluate_permit(self, gharra_url: str):
        """Policy evaluation for EU→EU routing should return permit."""
        resp = _post(gharra_url, "/v1/policy-engine/evaluate", {
            "subject_identity": "test-caller",
            "subject_jurisdiction": "IE",
            "action": "route",
            "target_agent_id": "gharra://ie/agents/triage-e2e",
            "purpose_of_use": "treatment",
            "consent_proof": "urn:consent:eval:001",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "permit"
        assert data["target_jurisdiction"] == "IE"

    def test_evaluate_deny_gdpr(self, gharra_url: str):
        """Policy evaluation for EU→IN routing should return deny (GDPR)."""
        resp = _post(gharra_url, "/v1/policy-engine/evaluate", {
            "subject_identity": "test-caller",
            "subject_jurisdiction": "IE",
            "action": "route",
            "target_agent_id": "gharra://in/agents/diagnostics-e2e",
            "purpose_of_use": "treatment",
            "consent_proof": "urn:consent:eval:002",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "deny"
        assert "adequacy" in data["reason"].lower() or "GDPR" in data["reason"]

    def test_evaluate_deny_purpose(self, gharra_url: str):
        """Policy evaluation with wrong purpose should return deny."""
        resp = _post(gharra_url, "/v1/policy-engine/evaluate", {
            "subject_identity": "test-caller",
            "subject_jurisdiction": "IE",
            "action": "route",
            "target_agent_id": "gharra://ie/agents/consent-gate-e2e",
            "purpose_of_use": "marketing",
            "consent_proof": "urn:consent:eval:003",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "deny"
        assert "purpose" in data["reason"].lower()

    def test_evaluate_with_adequacy_override(self, gharra_url: str):
        """Policy evaluation with SCC override should return permit."""
        resp = _post(gharra_url, "/v1/policy-engine/evaluate", {
            "subject_identity": "test-caller",
            "subject_jurisdiction": "IE",
            "action": "route",
            "target_agent_id": "gharra://in/agents/diagnostics-e2e",
            "purpose_of_use": "treatment",
            "consent_proof": "urn:consent:eval:004",
            "adequacy_override": "SCC-2021/914",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "permit"


# ── Policy Decision Audit Trail ───────────────────────────────────────


class TestPolicyDecisionAudit:
    """Verify policy decisions are logged for compliance."""

    def test_decisions_logged_in_memory(self, gharra_url: str):
        """Policy decisions should appear in the in-memory audit log."""
        # First, trigger a policy evaluation
        _post(gharra_url, "/v1/policy-engine/evaluate", {
            "subject_identity": "audit-test-caller",
            "action": "route",
            "target_agent_id": "gharra://ie/agents/triage-e2e",
            "purpose_of_use": "treatment",
            "consent_proof": "urn:consent:audit:001",
        })

        # Query the decision log
        resp = _get(gharra_url, "/v1/policy-engine/decisions", {"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0
        # Should have at least one decision from our evaluation
        subjects = [d["subject"] for d in data["decisions"]]
        assert any("audit-test-caller" in s for s in subjects)

    def test_decisions_logged_to_ledger(self, gharra_url: str):
        """Policy decisions should be logged to the transparency ledger."""
        # Trigger a policy evaluation (this logs to ledger via evaluate_and_log)
        _post(gharra_url, "/v1/policy-engine/evaluate", {
            "subject_identity": "ledger-audit-caller",
            "subject_jurisdiction": "IE",
            "action": "route",
            "target_agent_id": "gharra://ie/agents/triage-e2e",
            "purpose_of_use": "treatment",
            "consent_proof": "urn:consent:audit:002",
        })

        # Check that the ledger has policy decision entries
        resp = _get(gharra_url, "/v1/admin/ledger/entries", {
            "limit": 50,
            "operation": "policy.route.permit",
        })
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        policy_entries = [e for e in entries if e.get("operation", "").startswith("policy.")]
        assert len(policy_entries) > 0, (
            f"No policy decision entries in ledger. All entries: {entries[:5]}"
        )

    def test_deny_decisions_logged(self, gharra_url: str):
        """Deny decisions should also appear in the ledger."""
        # Trigger a deny decision
        _post(gharra_url, "/v1/policy-engine/evaluate", {
            "subject_identity": "deny-audit-caller",
            "subject_jurisdiction": "IE",
            "action": "route",
            "target_agent_id": "gharra://in/agents/diagnostics-e2e",
            "purpose_of_use": "treatment",
            "consent_proof": "urn:consent:audit:003",
        })

        # Check for deny entries in ledger
        resp = _get(gharra_url, "/v1/admin/ledger/entries", {
            "limit": 50,
            "operation": "policy.route.deny",
        })
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        deny_entries = [e for e in entries if "deny" in e.get("operation", "")]
        assert len(deny_entries) > 0, (
            f"No deny decision entries in ledger"
        )

    def test_filter_decisions_by_action(self, gharra_url: str):
        """Policy decision log can be filtered by action type."""
        resp = _get(gharra_url, "/v1/policy-engine/decisions", {
            "action": "route",
            "limit": 10,
        })
        assert resp.status_code == 200
        data = resp.json()
        for d in data["decisions"]:
            assert d["action"] == "route"

    def test_filter_decisions_by_outcome(self, gharra_url: str):
        """Policy decision log can be filtered by decision outcome."""
        resp = _get(gharra_url, "/v1/policy-engine/decisions", {
            "decision": "deny",
            "limit": 10,
        })
        assert resp.status_code == 200
        data = resp.json()
        for d in data["decisions"]:
            assert d["decision"] == "deny"

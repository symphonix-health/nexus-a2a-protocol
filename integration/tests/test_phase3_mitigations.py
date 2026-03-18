"""Phase 3 Risk Mitigation Integration Tests.

Mitigations covered:
  1.2 -- Rate Limit Circuit Breaker (status + federation breakers)
  2.2 -- Automated PHI Remediation (redact + preserve structure)
  3.3 -- Cross-Registry Event Replay (ledger replay + correlation)
  6.1 -- Compliance Dashboard (aggregated governance metrics)
  6.3 -- Automated Conformance Reporting (live system checks)

Standards:
  - RFC 6585 (Rate Limit HTTP Status Codes)
  - GDPR Art. 25 (Data protection by design)
  - HIPAA 45 CFR 164.514 (De-identification)
  - ISO 27001 A.12.4, A.18.2 (Logging, compliance reviews)
  - EU AI Act Art. 9, 12 (Risk management, record-keeping)
  - NIST SP 800-53, 800-184, 800-188
"""

from __future__ import annotations

import httpx
import pytest


# =========================================================================
# Mitigation 1.2 -- Rate Limit Circuit Breaker
# =========================================================================


class TestRateLimitCircuitBreaker:
    """Verify rate limit status and circuit breaker observability."""

    @pytest.mark.asyncio
    async def test_rate_limit_status_endpoint_exists(self, gharra_url: str):
        """The rate-limit/status endpoint exists and returns 200."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/rate-limit/status")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_status_contains_fields(self, gharra_url: str):
        """Status response contains rate_limit_enabled and circuit_breakers."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/rate-limit/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "rate_limit_enabled" in data
        assert "circuit_breakers" in data
        assert "circuit_breaker_count" in data
        assert isinstance(data["circuit_breakers"], list)

    @pytest.mark.asyncio
    async def test_rate_limit_status_disabled_in_integration(self, gharra_url: str):
        """Rate limiting is disabled in integration env (GHARRA_RATE_LIMIT_ENABLED=false)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/rate-limit/status")
        assert resp.status_code == 200
        data = resp.json()
        # Integration harness disables rate limiting
        assert data["rate_limit_enabled"] is False

    @pytest.mark.asyncio
    async def test_rate_limit_status_gb_sovereign(self, gharra_gb_url: str):
        """Rate limit status accessible on GB sovereign registry."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/admin/rate-limit/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "rate_limit_enabled" in data

    @pytest.mark.asyncio
    async def test_rate_limit_status_us_sovereign(self, gharra_us_url: str):
        """Rate limit status accessible on US sovereign registry."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_us_url}/v1/admin/rate-limit/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "rate_limit_enabled" in data


# =========================================================================
# Mitigation 2.2 -- Automated PHI Remediation
# =========================================================================


class TestAutomatedPHIRemediation:
    """Verify automated PHI redaction preserves structure, removes PHI."""

    @pytest.mark.asyncio
    async def test_remediate_endpoint_exists(self, gharra_url: str):
        """The /remediate endpoint exists and accepts POST."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/remediate",
                json={"agent_id": "test", "payload": {"status": "active"}},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_remediate_structural_fields(self, gharra_url: str):
        """Structural PHI fields are redacted."""
        payload = {
            "patient_name": "John Doe",
            "date_of_birth": "1990-01-15",
            "status": "active",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/remediate",
                json={"agent_id": "test-struct", "payload": payload},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_detected"] is True
        assert data["redaction_count"] >= 2
        cleaned = data["remediated_payload"]
        assert cleaned["patient_name"] == "[REDACTED]"
        assert cleaned["date_of_birth"] == "[REDACTED]"
        # Non-PHI preserved
        assert cleaned["status"] == "active"

    @pytest.mark.asyncio
    async def test_remediate_format_regex_ssn(self, gharra_url: str):
        """US SSN patterns are redacted from free text."""
        payload = {
            "notes": "Patient SSN is 123-45-6789 for insurance.",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/remediate",
                json={"agent_id": "test-ssn", "payload": payload},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_detected"] is True
        # SSN should be replaced
        assert "123-45-6789" not in data["remediated_payload"]["notes"]
        assert "[REDACTED:" in data["remediated_payload"]["notes"]

    @pytest.mark.asyncio
    async def test_remediate_format_regex_email(self, gharra_url: str):
        """Email addresses are redacted from free text."""
        payload = {
            "referral": "Contact at john.doe@hospital.nhs.uk for details.",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/remediate",
                json={"agent_id": "test-email", "payload": payload},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_detected"] is True
        assert "john.doe@hospital.nhs.uk" not in data["remediated_payload"]["referral"]

    @pytest.mark.asyncio
    async def test_remediate_clean_payload_unchanged(self, gharra_url: str):
        """Clean payload with no PHI is returned unchanged."""
        payload = {
            "capability": "imaging",
            "protocol": "fhir-r4",
            "jurisdiction": "GB",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/remediate",
                json={"agent_id": "test-clean", "payload": payload},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_detected"] is False
        assert data["redaction_count"] == 0
        assert data["remediated_payload"] == payload

    @pytest.mark.asyncio
    async def test_remediate_mixed_payload(self, gharra_url: str):
        """Mixed payload with both PHI and non-PHI fields."""
        payload = {
            "patient_name": "Jane Doe",
            "ssn": "987-65-4321",
            "capability": "triage",
            "protocol": "a2a",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/remediate",
                json={"agent_id": "test-mixed", "payload": payload},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_detected"] is True
        cleaned = data["remediated_payload"]
        assert cleaned["patient_name"] == "[REDACTED]"
        assert cleaned["ssn"] == "[REDACTED]"
        assert cleaned["capability"] == "triage"
        assert cleaned["protocol"] == "a2a"

    @pytest.mark.asyncio
    async def test_remediate_returns_layers(self, gharra_url: str):
        """Remediation response includes triggered layers."""
        payload = {
            "patient_name": "Test Patient",
            "notes": "SSN 111-22-3333",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/remediate",
                json={"agent_id": "test-layers", "payload": payload},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "structural" in data["layers_triggered"]
        assert "format_regex" in data["layers_triggered"]

    @pytest.mark.asyncio
    async def test_remediate_nhs_number(self, gharra_url: str):
        """NHS number patterns are redacted."""
        payload = {
            "notes": "NHS number: 943 476 5919",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/remediate",
                json={"agent_id": "test-nhs", "payload": payload},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_detected"] is True
        assert "943 476 5919" not in data["remediated_payload"]["notes"]

    @pytest.mark.asyncio
    async def test_remediate_cross_registry_gb(self, gharra_gb_url: str):
        """Remediation endpoint works on sovereign registries."""
        payload = {"patient_name": "Test GB", "status": "active"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_gb_url}/v1/policy-engine/remediate",
                json={"agent_id": "test-gb", "payload": payload},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_detected"] is True
        assert data["remediated_payload"]["patient_name"] == "[REDACTED]"


# =========================================================================
# Mitigation 3.3 -- Cross-Registry Event Replay
# =========================================================================


class TestCrossRegistryEventReplay:
    """Verify cross-registry event replay from the transparency ledger."""

    @pytest.mark.asyncio
    async def test_gharra_event_replay_endpoint(self, gharra_url: str):
        """GHARRA event replay endpoint exists and returns events."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/events/replay")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "event_count" in data
        assert isinstance(data["events"], list)

    @pytest.mark.asyncio
    async def test_event_replay_has_registry_id(self, gharra_url: str):
        """Replay response includes the source registry_id."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/events/replay")
        assert resp.status_code == 200
        data = resp.json()
        assert "registry_id" in data
        assert data["registry_id"] != ""

    @pytest.mark.asyncio
    async def test_event_replay_with_limit(self, gharra_url: str):
        """Replay respects the limit parameter."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/events/replay",
                params={"limit": 5},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_count"] <= 5

    @pytest.mark.asyncio
    async def test_event_replay_with_after_seq(self, gharra_url: str):
        """Replay supports cursor-based pagination via after_seq."""
        async with httpx.AsyncClient() as client:
            # First page
            resp1 = await client.get(
                f"{gharra_url}/v1/admin/events/replay",
                params={"limit": 3},
            )
        assert resp1.status_code == 200
        data1 = resp1.json()
        if data1["event_count"] > 0:
            to_seq = data1["to_seq"]
            # Second page
            async with httpx.AsyncClient() as client:
                resp2 = await client.get(
                    f"{gharra_url}/v1/admin/events/replay",
                    params={"after_seq": to_seq, "limit": 3},
                )
            assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_event_replay_operation_filter(self, gharra_url: str):
        """Replay supports filtering by operation type."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/events/replay",
                params={"operation": "agent.registered"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "filters_applied" in data
        assert data["filters_applied"]["operation"] == "agent.registered"

    @pytest.mark.asyncio
    async def test_event_replay_gb_sovereign(self, gharra_gb_url: str):
        """Event replay accessible on GB sovereign registry."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/admin/events/replay")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data

    @pytest.mark.asyncio
    async def test_event_replay_us_sovereign(self, gharra_us_url: str):
        """Event replay accessible on US sovereign registry."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_us_url}/v1/admin/events/replay")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data

    @pytest.mark.asyncio
    async def test_nexus_event_store_replay_endpoint(self, nexus_url: str):
        """Nexus event store replay endpoint exists."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{nexus_url}/api/event-store/replay")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data


# =========================================================================
# Mitigation 6.1 -- Compliance Dashboard
# =========================================================================


class TestComplianceDashboard:
    """Verify the compliance dashboard aggregates governance metrics."""

    @pytest.mark.asyncio
    async def test_compliance_dashboard_exists(self, gharra_url: str):
        """The compliance dashboard endpoint exists and returns 200."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_compliance_dashboard_agent_metrics(self, gharra_url: str):
        """Dashboard includes agent coverage metrics (DID, LEI)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        agents = data["agents"]
        assert "total" in agents
        assert "with_did_uri" in agents
        assert "with_organisation_lei" in agents
        assert "did_coverage_pct" in agents
        assert "lei_coverage_pct" in agents
        assert agents["total"] > 0

    @pytest.mark.asyncio
    async def test_compliance_dashboard_ledger_integrity(self, gharra_url: str):
        """Dashboard includes ledger integrity status."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        ledger = data["ledger"]
        assert "chain_valid" in ledger
        assert ledger["chain_valid"] is True
        assert "total_entries" in ledger
        assert ledger["total_entries"] > 0

    @pytest.mark.asyncio
    async def test_compliance_dashboard_policy_enforcement(self, gharra_url: str):
        """Dashboard includes policy enforcement statistics."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        pe = data["policy_enforcement"]
        assert "total_enforcement_events" in pe
        assert "phi_remediation_events" in pe
        assert "gdpr_erasure_events" in pe

    @pytest.mark.asyncio
    async def test_compliance_dashboard_federation(self, gharra_url: str):
        """Dashboard includes federation event count."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "federation" in data
        assert "cross_registry_events" in data["federation"]

    @pytest.mark.asyncio
    async def test_compliance_dashboard_attestations(self, gharra_url: str):
        """Dashboard includes attestation health metrics."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        att = data["attestations"]
        assert "total" in att
        assert "expiring_within_30_days" in att

    @pytest.mark.asyncio
    async def test_compliance_dashboard_has_registry_id(self, gharra_url: str):
        """Dashboard includes the registry identity."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "registry_id" in data
        assert data["registry_id"] != ""

    @pytest.mark.asyncio
    async def test_compliance_dashboard_gb_sovereign(self, gharra_gb_url: str):
        """Compliance dashboard accessible on GB sovereign."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agents"]["total"] > 0

    @pytest.mark.asyncio
    async def test_compliance_dashboard_rate_limiting(self, gharra_url: str):
        """Dashboard includes rate limiting status."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/compliance/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "rate_limiting" in data
        assert "enabled" in data["rate_limiting"]


# =========================================================================
# Mitigation 6.3 -- Automated Conformance Reporting
# =========================================================================


class TestAutomatedConformanceReporting:
    """Verify automated conformance report generation."""

    @pytest.mark.asyncio
    async def test_conformance_report_exists(self, gharra_url: str):
        """The conformance report endpoint exists and returns 200."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_conformance_report_summary(self, gharra_url: str):
        """Report includes a conformance summary with pass/fail counts."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        summary = data["conformance_summary"]
        assert "total_controls" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "warnings" in summary
        assert "conformance_pct" in summary
        assert summary["total_controls"] >= 8

    @pytest.mark.asyncio
    async def test_conformance_report_controls_list(self, gharra_url: str):
        """Report includes individual control check results."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        controls = data["controls"]
        assert len(controls) >= 8
        for control in controls:
            assert "control_id" in control
            assert "control_name" in control
            assert "standard" in control
            assert "status" in control
            assert control["status"] in ("pass", "fail", "warn", "info")
            assert "detail" in control

    @pytest.mark.asyncio
    async def test_conformance_report_phi_detection_passes(self, gharra_url: str):
        """PHI detection pipeline control passes in conformance report."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        phi_control = next(
            (c for c in data["controls"] if c["control_id"] == "MIT-2.3"), None
        )
        assert phi_control is not None, "MIT-2.3 control missing from report"
        assert phi_control["status"] == "pass"

    @pytest.mark.asyncio
    async def test_conformance_report_ledger_integrity_passes(self, gharra_url: str):
        """Ledger integrity control passes in conformance report."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        ledger_control = next(
            (c for c in data["controls"] if c["control_id"] == "MIT-3.2"), None
        )
        assert ledger_control is not None, "MIT-3.2 control missing from report"
        assert ledger_control["status"] == "pass"

    @pytest.mark.asyncio
    async def test_conformance_report_remediation_passes(self, gharra_url: str):
        """PHI remediation control passes in conformance report."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        rem_control = next(
            (c for c in data["controls"] if c["control_id"] == "MIT-2.2"), None
        )
        assert rem_control is not None, "MIT-2.2 control missing from report"
        assert rem_control["status"] == "pass"

    @pytest.mark.asyncio
    async def test_conformance_report_has_report_hash(self, gharra_url: str):
        """Report includes a tamper-proof SHA-256 hash."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "report_hash" in data
        assert len(data["report_hash"]) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_conformance_report_has_timestamp(self, gharra_url: str):
        """Report includes generation timestamp."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "generated_at" in data

    @pytest.mark.asyncio
    async def test_conformance_report_gb_sovereign(self, gharra_gb_url: str):
        """Conformance report available on GB sovereign."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_gb_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["conformance_summary"]["total_controls"] >= 8

    @pytest.mark.asyncio
    async def test_conformance_report_high_conformance(self, gharra_url: str):
        """Root registry achieves high conformance percentage."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/compliance/conformance-report"
            )
        assert resp.status_code == 200
        data = resp.json()
        # All core controls should pass
        assert data["conformance_summary"]["conformance_pct"] >= 75.0

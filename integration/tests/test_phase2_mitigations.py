"""Phase 2 Risk Mitigation Integration Tests.

Mitigations covered:
  2.3 -- Multi-Layer PHI Detection Pipeline
  1.3 -- Runtime Enforcement Proxy (advisory + enforce modes)
  5.2 -- Three-Layer Identifier Standard (DID + LEI + UUID v7)
  3.2 -- Durable Event Sourcing (tasks/replay)

Standards:
  - GDPR Art. 25, 32 (Data protection by design)
  - HIPAA 45 CFR 164.312 (Technical safeguards)
  - W3C DID Core v1.0
  - ISO 17442 (Legal Entity Identifier)
  - RFC 9562 (UUID v7)
"""

from __future__ import annotations

import re
import uuid

import httpx
import pytest


# =========================================================================
# Mitigation 2.3 -- Multi-Layer PHI Detection Pipeline
# =========================================================================


class TestMultiLayerPHIDetection:
    """Verify the three-layer PHI detection pipeline on GHARRA gateway."""

    @pytest.mark.asyncio
    async def test_phi_structural_field_scan_blocks(self, gharra_url: str):
        """Layer 1: structural field-name scan detects PHI fields."""
        payload = {
            "patient_name": "John Doe",
            "date_of_birth": "1990-01-15",
            "medical_record_number": "MRN-12345",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-phi-scan",
                    "payload": payload,
                    "policy_tags": {"phi_allowed": False, "residency": ["EU"]},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        # PHI should be detected
        assert data["phi_classification"] != "none"
        assert data["phi_confidence"] > 0

    @pytest.mark.asyncio
    async def test_phi_format_regex_ssn(self, gharra_url: str):
        """Layer 3: format regex detects US SSN patterns."""
        payload = {
            "notes": "Patient SSN is 123-45-6789 for insurance verification.",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-ssn-scan",
                    "payload": payload,
                    "policy_tags": {"phi_allowed": False},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_confidence"] > 0
        assert len(data["phi_layers"]) > 0

    @pytest.mark.asyncio
    async def test_phi_format_regex_nhs_number(self, gharra_url: str):
        """Layer 3: format regex detects NHS number patterns."""
        payload = {
            "notes": "NHS number: 943 476 5919",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-nhs-scan",
                    "payload": payload,
                    "policy_tags": {"phi_allowed": False},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_confidence"] > 0

    @pytest.mark.asyncio
    async def test_phi_format_regex_email(self, gharra_url: str):
        """Layer 3: format regex detects email addresses as PII."""
        payload = {
            "referral_notes": "Contact patient at john.doe@hospital.nhs.uk",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-email-scan",
                    "payload": payload,
                    "policy_tags": {"phi_allowed": False},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["phi_confidence"] > 0

    @pytest.mark.asyncio
    async def test_clean_payload_no_phi(self, gharra_url: str):
        """Clean payload without PHI indicators passes cleanly."""
        payload = {
            "status": "active",
            "capability": "imaging",
            "protocol": "fhir-r4",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-clean",
                    "payload": payload,
                    "policy_tags": {"phi_allowed": False},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True


# =========================================================================
# Mitigation 1.3 -- Runtime Enforcement Proxy
# =========================================================================


class TestEnforcementProxy:
    """Verify the enforcement proxy validates payloads against policy tags."""

    @pytest.mark.asyncio
    async def test_enforce_endpoint_exists(self, gharra_url: str):
        """The /enforce endpoint exists and accepts POST."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-agent",
                    "payload": {"hello": "world"},
                    "policy_tags": {},
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_enforce_advisory_mode_allows(self, gharra_url: str):
        """In advisory mode (default), violations are logged but allowed."""
        payload = {
            "patient_name": "Jane Doe",
            "ssn": "123-45-6789",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-advisory",
                    "payload": payload,
                    "policy_tags": {"phi_allowed": False},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        # Advisory mode: allowed is True even with violations
        assert data["enforcement_mode"] == "advisory"
        assert data["allowed"] is True

    @pytest.mark.asyncio
    async def test_enforce_returns_phi_details(self, gharra_url: str):
        """Enforcement response includes PHI classification details."""
        payload = {
            "medical_record_number": "MRN-99887",
            "diagnosis": "Type 2 Diabetes",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-phi-details",
                    "payload": payload,
                    "policy_tags": {"phi_allowed": False},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "phi_classification" in data
        assert "phi_confidence" in data
        assert "phi_layers" in data

    @pytest.mark.asyncio
    async def test_enforce_purpose_of_use_violation(self, gharra_url: str):
        """Purpose-of-use mismatch is flagged as a violation."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-purpose",
                    "payload": {"purpose": "marketing"},
                    "policy_tags": {
                        "phi_allowed": True,
                        "purpose_of_use": ["treatment"],
                    },
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        # Should flag purpose-of-use violation
        assert len(data["violations"]) > 0

    @pytest.mark.asyncio
    async def test_enforce_cross_registry_gb(self, gharra_gb_url: str):
        """Enforcement endpoint exists on sovereign registries."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_gb_url}/v1/policy-engine/enforce",
                json={
                    "agent_id": "test-gb",
                    "payload": {"hello": "world"},
                    "policy_tags": {},
                },
            )
        assert resp.status_code == 200


# =========================================================================
# Mitigation 5.2 -- Three-Layer Identifier Standard
# =========================================================================


class TestThreeLayerIdentifiers:
    """Verify DID URI, Organisation LEI, and UUID v7 correlation IDs."""

    @pytest.mark.asyncio
    async def test_agent_has_did_uri(self, gharra_url: str):
        """Seeded triage agent has a W3C DID URI (did:web:...)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/agents/gharra://ie/agents/triage-e2e"
            )
        assert resp.status_code == 200
        data = resp.json()
        did = data.get("did_uri")
        assert did is not None, "Agent must have did_uri field"
        assert did.startswith("did:web:"), f"DID must start with did:web:, got {did}"

    @pytest.mark.asyncio
    async def test_agent_has_organisation_lei(self, gharra_url: str):
        """Seeded triage agent has an ISO 17442 LEI."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/agents/gharra://ie/agents/triage-e2e"
            )
        assert resp.status_code == 200
        data = resp.json()
        lei = data.get("organisation_lei")
        assert lei is not None, "Agent must have organisation_lei field"
        # LEI is 20-character alphanumeric
        assert len(lei) == 20, f"LEI must be 20 chars, got {len(lei)}"
        assert lei.isalnum(), f"LEI must be alphanumeric, got {lei}"

    @pytest.mark.asyncio
    async def test_did_uri_format_valid(self, gharra_url: str):
        """DID URI follows W3C did:web method syntax."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/agents/gharra://gb/agents/referral-e2e"
            )
        assert resp.status_code == 200
        data = resp.json()
        did = data.get("did_uri", "")
        # did:web:<domain>:agents:<id>
        assert re.match(r"^did:web:[a-z0-9\.\-]+:", did), (
            f"DID format invalid: {did}"
        )

    @pytest.mark.asyncio
    async def test_registration_accepts_did_lei(self, gharra_url: str):
        """Agent registration accepts did_uri and organisation_lei fields."""
        agent_id = f"gharra://ie/agents/did-test-{uuid.uuid4().hex[:8]}"
        payload = {
            "agent_id": agent_id,
            "display_name": "DID Test Agent",
            "jurisdiction": "IE",
            "did_uri": "did:web:gharra.health:ie:agents:did-test",
            "organisation_lei": "635400LNPK21HAK3CH18",
            "endpoints": [
                {"url": "https://localhost:9999/test", "protocol": "http-rest"}
            ],
            "capabilities": {"protocols": ["http-rest"]},
        }
        idem_key = f"idem-did-{uuid.uuid4().hex[:8]}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/agents",
                json=payload,
                headers={"X-Idempotency-Key": idem_key},
            )
        assert resp.status_code in (200, 201), (
            f"Registration failed: {resp.status_code} {resp.text}"
        )
        data = resp.json()
        assert data.get("did_uri") == "did:web:gharra.health:ie:agents:did-test"
        assert data.get("organisation_lei") == "635400LNPK21HAK3CH18"

        # Cleanup
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{gharra_url}/v1/admin/erasure",
                json={"agent_id": agent_id},
            )

    @pytest.mark.asyncio
    async def test_gb_sovereign_has_did(self, gharra_gb_url: str):
        """GB sovereign agents have DID URIs."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_gb_url}/v1/agents/gharra://gb/agents/nhs-triage-e2e"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("did_uri") is not None

    @pytest.mark.asyncio
    async def test_us_sovereign_has_did(self, gharra_us_url: str):
        """US sovereign agents have DID URIs."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_us_url}/v1/agents/gharra://us/agents/mayo-imaging-e2e"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("did_uri") is not None


# =========================================================================
# Mitigation 3.2 -- Durable Event Sourcing
# =========================================================================


class TestDurableEventSourcing:
    """Verify the durable event store and tasks/replay endpoint."""

    @pytest.mark.asyncio
    async def test_event_store_status(self, nexus_url: str):
        """The event store status endpoint reports enabled state."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{nexus_url}/api/event-store/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data

    @pytest.mark.asyncio
    async def test_replay_unknown_task_returns_error(self, nexus_url: str):
        """Replay for an unknown task_id returns a JSON-RPC error."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{nexus_url}/rpc/triage/replay",
                json={
                    "jsonrpc": "2.0",
                    "id": "test-1",
                    "method": "tasks/replay",
                    "params": {
                        "task_id": f"nonexistent-{uuid.uuid4().hex[:8]}",
                    },
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32001

    @pytest.mark.asyncio
    async def test_replay_requires_task_id(self, nexus_url: str):
        """Replay without task_id returns JSON-RPC invalid params error."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{nexus_url}/rpc/triage/replay",
                json={
                    "jsonrpc": "2.0",
                    "id": "test-2",
                    "method": "tasks/replay",
                    "params": {},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32602

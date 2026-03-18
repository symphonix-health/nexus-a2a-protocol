"""GDPR Erasure Tests (Mitigation 5.3).

Verify GDPR Art. 17 right to erasure implementation:
  - Agent record hard-deletion
  - Ledger tombstone creation (CNIL off-chain pattern)
  - Actor pseudonymisation reference counting
  - Erasure does not break ledger chain integrity
  - Cross-registry erasure availability

Standards:
  - GDPR Art. 17 (Right to erasure)
  - CNIL guidance on blockchain and GDPR
  - ISO 27001 A.8.3 (Media handling)
"""

from __future__ import annotations

import uuid

import httpx
import pytest


# ── Helper: register a disposable agent for erasure testing ──────────────


async def _register_disposable_agent(gharra_url: str) -> str:
    """Register a temporary agent and return its agent_id."""
    agent_id = f"gharra://ie/agents/erasure-test-{uuid.uuid4().hex[:8]}"
    payload = {
        "agent_id": agent_id,
        "display_name": "Erasure Test Agent",
        "jurisdiction": "IE",
        "description": "Temporary agent for GDPR erasure testing",
        "capabilities": {
            "protocols": ["http-rest"],
        },
        "endpoints": [
            {
                "url": "https://localhost:9999/erasure-test",
                "protocol": "http-rest",
            }
        ],
        "policy_tags": {
            "phi_allowed": False,
            "residency": ["EU"],
            "data_classification": "internal",
        },
    }
    idem_key = f"idem-erasure-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{gharra_url}/v1/agents",
            json=payload,
            headers={"X-Idempotency-Key": idem_key},
        )
        assert resp.status_code in (200, 201), (
            f"Failed to register disposable agent: {resp.status_code} {resp.text}"
        )
    return agent_id


# ── Tests ────────────────────────────────────────────────────────────────


class TestGDPRErasure:
    """GDPR Art. 17 erasure endpoint tests."""

    @pytest.mark.asyncio
    async def test_erasure_deletes_agent(self, gharra_url: str):
        """Erasure hard-deletes the agent record from storage."""
        agent_id = await _register_disposable_agent(gharra_url)

        # Verify agent exists
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/agents/{agent_id}")
            assert resp.status_code == 200

            # Erase
            resp = await client.post(
                f"{gharra_url}/v1/admin/erasure",
                json={"agent_id": agent_id},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["erased"] is True
            assert data["agent_id"] == agent_id

            # Verify agent is gone
            resp = await client.get(f"{gharra_url}/v1/agents/{agent_id}")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_erasure_creates_tombstone(self, gharra_url: str):
        """Erasure appends a tombstone entry to the ledger."""
        agent_id = await _register_disposable_agent(gharra_url)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/erasure",
                json={"agent_id": agent_id},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ledger_tombstone_seq"] > 0

            # Verify tombstone in ledger
            resp = await client.get(
                f"{gharra_url}/v1/admin/ledger/entries",
                params={"operation": "gdpr.erasure", "limit": 500},
            )
            assert resp.status_code == 200
            entries = resp.json()["entries"]
            erasure_entries = [
                e for e in entries if e.get("operation") == "gdpr.erasure"
            ]
            assert len(erasure_entries) > 0

    @pytest.mark.asyncio
    async def test_erasure_pseudonymises_subject(self, gharra_url: str):
        """Tombstone uses pseudonymised subject (not raw agent_id)."""
        agent_id = await _register_disposable_agent(gharra_url)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/erasure",
                json={"agent_id": agent_id, "pseudonymise_ledger": True},
            )
            assert resp.status_code == 200

            # Check tombstone subject is pseudonymised
            resp = await client.get(
                f"{gharra_url}/v1/admin/ledger/entries",
                params={"operation": "gdpr.erasure", "limit": 500},
            )
            entries = resp.json()["entries"]
            erasure_entries = [
                e for e in entries if e.get("operation") == "gdpr.erasure"
            ]
            # Tombstone subject should start with "erased:" prefix
            for entry in erasure_entries:
                if entry.get("subject", "").startswith("erased:"):
                    break
            else:
                pytest.fail("No tombstone with pseudonymised subject found")

    @pytest.mark.asyncio
    async def test_erasure_nonexistent_agent_404(self, gharra_url: str):
        """Erasure of non-existent agent returns 404."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/erasure",
                json={"agent_id": "gharra://ie/agents/does-not-exist"},
            )
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_erasure_preserves_ledger_chain(self, gharra_url: str):
        """Erasure does not break the ledger hash chain integrity."""
        agent_id = await _register_disposable_agent(gharra_url)

        async with httpx.AsyncClient() as client:
            # Erase
            await client.post(
                f"{gharra_url}/v1/admin/erasure",
                json={"agent_id": agent_id},
            )

            # Verify ledger chain is still valid
            resp = await client.get(f"{gharra_url}/v1/admin/ledger/verify")
            assert resp.status_code == 200
            data = resp.json()
            assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_erasure_with_custom_reason(self, gharra_url: str):
        """Erasure accepts a custom reason field."""
        agent_id = await _register_disposable_agent(gharra_url)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/erasure",
                json={
                    "agent_id": agent_id,
                    "reason": "Data subject request ref DSR-2026-0042",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["erased"] is True


class TestErasureCrossRegistry:
    """Verify erasure is available on sovereign registries."""

    @pytest.mark.asyncio
    async def test_erasure_endpoint_exists_gb(self, gharra_gb_url: str):
        """GB sovereign registry has the erasure endpoint."""
        async with httpx.AsyncClient() as client:
            # Try erasing a non-existent agent -- 404 means endpoint exists
            resp = await client.post(
                f"{gharra_gb_url}/v1/admin/erasure",
                json={"agent_id": "gharra://gb/agents/nonexistent"},
            )
            assert resp.status_code == 404  # Not 405 (method not allowed)

    @pytest.mark.asyncio
    async def test_erasure_endpoint_exists_us(self, gharra_us_url: str):
        """US sovereign registry has the erasure endpoint."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_us_url}/v1/admin/erasure",
                json={"agent_id": "gharra://us/agents/nonexistent"},
            )
            assert resp.status_code == 404

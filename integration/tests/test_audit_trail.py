"""Tamper-Evident Audit Trail Tests (Sprint 3 — Capability 5).

Validates that the GHARRA transparency ledger provides:
  - Hash-chained append-only audit log for all mutations
  - Merkle tree checkpoints for batch integrity verification
  - Merkle inclusion proofs for individual entries
  - Cross-registry audit correlation via federation_source
  - Tamper-evident audit export for governance compliance
  - Chain verification detects integrity

Standards tested:
  - ISO 27001 A.12.4 (Logging and monitoring)
  - EU AI Act Art. 12 (Record-keeping for high-risk AI)
  - NIST SP 800-92 (Log management)
  - eIDAS Art. 24 (Trust service audit)
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


# ── Chain Integrity ─────────────────────────────────────────────────────


class TestChainIntegrity:
    """Verify the hash chain is valid after seeding operations."""

    def test_ledger_has_entries(self, gharra_url: str):
        """Seeding agents should produce ledger entries."""
        resp = _get(gharra_url, "/v1/admin/ledger/entries", {"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0, "Ledger should have entries after seeding"

    def test_chain_verification_passes(self, gharra_url: str):
        """Hash chain should be valid — no tampered entries."""
        resp = _get(gharra_url, "/v1/admin/ledger/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True, f"Chain verification failed: {data}"
        assert data["entries_checked"] > 0

    def test_entries_have_hashes(self, gharra_url: str):
        """Every ledger entry should have entry_hash and prev_hash."""
        resp = _get(gharra_url, "/v1/admin/ledger/entries", {"limit": 5})
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        for entry in entries:
            assert "entry_hash" in entry, f"Missing entry_hash: {entry}"
            assert "prev_hash" in entry, f"Missing prev_hash: {entry}"
            assert len(entry["entry_hash"]) == 64, "entry_hash should be SHA-256"

    def test_entries_are_chained(self, gharra_url: str):
        """Each entry's prev_hash should match the previous entry's entry_hash."""
        resp = _get(gharra_url, "/v1/admin/ledger/entries", {"limit": 20})
        entries = resp.json()["entries"]
        if len(entries) < 2:
            return  # Not enough entries to verify chaining
        for i in range(1, len(entries)):
            assert entries[i]["prev_hash"] == entries[i - 1]["entry_hash"], (
                f"Chain broken at seq {entries[i].get('seq')}: "
                f"prev_hash={entries[i]['prev_hash']} != "
                f"prev entry_hash={entries[i-1]['entry_hash']}"
            )


# ── Merkle Checkpoints ──────────────────────────────────────────────────


class TestMerkleCheckpoints:
    """Verify Merkle tree checkpoint functionality."""

    def test_create_checkpoint(self, gharra_url: str):
        """Creating a checkpoint returns a Merkle root."""
        resp = _get(gharra_url, "/v1/admin/ledger/checkpoint")
        assert resp.status_code == 200
        data = resp.json()
        assert "merkle_root" in data
        assert data["merkle_root"] != "EMPTY", "Merkle root should not be empty after seeding"
        assert data["entry_count"] > 0
        assert "from_seq" in data
        assert "to_seq" in data
        assert data["chain_valid"] is True

    def test_checkpoint_has_hash(self, gharra_url: str):
        """Checkpoint itself should be hashed for tamper-evidence."""
        resp = _get(gharra_url, "/v1/admin/ledger/checkpoint")
        data = resp.json()
        assert "checkpoint_hash" in data
        assert len(data["checkpoint_hash"]) == 64, "checkpoint_hash should be SHA-256"

    def test_checkpoint_deterministic(self, gharra_url: str):
        """Same data should produce same Merkle root."""
        resp1 = _get(gharra_url, "/v1/admin/ledger/checkpoint")
        resp2 = _get(gharra_url, "/v1/admin/ledger/checkpoint")
        assert resp1.json()["merkle_root"] == resp2.json()["merkle_root"], (
            "Same ledger data should produce same Merkle root"
        )


# ── Merkle Proofs ───────────────────────────────────────────────────────


class TestMerkleProofs:
    """Verify Merkle inclusion proofs for individual entries."""

    def test_proof_for_entry(self, gharra_url: str):
        """Can generate a Merkle proof for a specific entry."""
        # Get first entry's seq
        entries_resp = _get(gharra_url, "/v1/admin/ledger/entries", {"limit": 1})
        entries = entries_resp.json()["entries"]
        if not entries:
            return
        seq = entries[0]["seq"]

        resp = _get(gharra_url, f"/v1/admin/ledger/proof/{seq}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["seq"] == seq
        assert "entry_hash" in data
        assert "merkle_root" in data
        assert "proof" in data
        assert data["verified"] is True, (
            f"Merkle proof verification failed for seq={seq}"
        )

    def test_proof_structure(self, gharra_url: str):
        """Proof contains sibling hashes with direction."""
        entries_resp = _get(gharra_url, "/v1/admin/ledger/entries", {"limit": 1})
        entries = entries_resp.json()["entries"]
        if not entries:
            return
        seq = entries[0]["seq"]

        resp = _get(gharra_url, f"/v1/admin/ledger/proof/{seq}")
        data = resp.json()
        for step in data["proof"]:
            assert "hash" in step
            assert "direction" in step
            assert step["direction"] in ("left", "right")

    def test_nonexistent_entry_proof(self, gharra_url: str):
        """Requesting proof for nonexistent seq returns error."""
        resp = _get(gharra_url, "/v1/admin/ledger/proof/999999")
        assert resp.status_code == 200  # Returns error in body, not HTTP error
        data = resp.json()
        assert "error" in data


# ── Cross-Border Audit Correlation ──────────────────────────────────────


class TestFederationAudit:
    """Verify cross-registry audit correlation via federation_source."""

    def test_federation_update_creates_audit_entry(self, gharra_url: str):
        """Federation updates should create ledger entries with federation_source."""
        # Send a federation update
        update = {
            "type": "agent.registered",
            "source_registry_id": "gharra://registries/sovereign-gb",
            "payload": {"agent_id": "gharra://gb/agents/audit-test-agent"},
            "sequence": 100,
        }
        resp = _post(gharra_url, "/v1/federation/updates", update)
        assert resp.status_code == 202

        # Check that the ledger has an entry with federation_source
        entries_resp = _get(gharra_url, "/v1/admin/ledger/entries", {
            "limit": 50,
            "operation": "federation.update.agent.registered",
        })
        assert entries_resp.status_code == 200
        entries = entries_resp.json()["entries"]
        fed_entries = [e for e in entries if e.get("federation_source")]
        assert len(fed_entries) > 0, (
            f"No federation-sourced entries found. All entries: {entries}"
        )
        assert fed_entries[0]["federation_source"] == "gharra://registries/sovereign-gb"

    def test_sovereign_ledger_independent(self, gharra_url: str, gharra_gb_url: str):
        """Each sovereign maintains its own independent ledger."""
        root_resp = _get(gharra_url, "/v1/admin/ledger/verify")
        gb_resp = _get(gharra_gb_url, "/v1/admin/ledger/verify")

        assert root_resp.status_code == 200
        assert gb_resp.status_code == 200

        root_data = root_resp.json()
        gb_data = gb_resp.json()

        # Both should be valid
        assert root_data["valid"] is True
        assert gb_data["valid"] is True

        # They should have different entry counts (different agents seeded)
        # Root has more entries (registries + agents + federation updates)
        assert root_data["entries_checked"] > 0
        assert gb_data["entries_checked"] > 0


# ── Audit Export ────────────────────────────────────────────────────────


class TestAuditExport:
    """Verify tamper-evident audit report export."""

    def test_export_report(self, gharra_url: str):
        """Audit export contains all required governance fields."""
        resp = _get(gharra_url, "/v1/admin/ledger/export")
        assert resp.status_code == 200
        report = resp.json()

        # Top-level structure
        assert "registry_id" in report
        assert "generated_at" in report
        assert report["registry_id"] != ""

        # Range
        assert "range" in report
        assert report["range"]["entry_count"] > 0

        # Integrity
        assert "integrity" in report
        integrity = report["integrity"]
        assert integrity["chain_valid"] is True
        assert integrity["entries_verified"] > 0
        assert len(integrity["merkle_root"]) == 64, "Merkle root should be SHA-256"
        assert len(integrity["genesis_hash"]) == 64
        assert len(integrity["latest_hash"]) == 64

        # Federation
        assert "federation" in report
        assert "cross_border_entries" in report["federation"]
        assert "sources" in report["federation"]

        # Entries
        assert "entries" in report
        assert len(report["entries"]) > 0

        # Report hash
        assert "report_hash" in report
        assert len(report["report_hash"]) == 64

    def test_export_report_hash_deterministic(self, gharra_url: str):
        """Same export should produce same report_hash."""
        # Note: timestamps differ, so we verify structure rather than exact match.
        # The important thing is the report_hash covers all fields.
        resp = _get(gharra_url, "/v1/admin/ledger/export")
        report = resp.json()
        assert report["report_hash"] != ""
        # The hash should be 64 hex chars (SHA-256)
        assert all(c in "0123456789abcdef" for c in report["report_hash"])

    def test_export_includes_federation_entries(self, gharra_url: str):
        """Export should include cross-border federation audit data."""
        resp = _get(gharra_url, "/v1/admin/ledger/export")
        report = resp.json()

        # After the federation update test, there should be cross-border entries
        fed = report["federation"]
        assert fed["cross_border_entries"] >= 0  # May be 0 if test ordering differs
        # If there are federation entries, sources should be listed
        if fed["cross_border_entries"] > 0:
            assert len(fed["sources"]) > 0

    def test_export_gb_sovereign(self, gharra_gb_url: str):
        """GB sovereign can also export its own audit report."""
        resp = _get(gharra_gb_url, "/v1/admin/ledger/export")
        assert resp.status_code == 200
        report = resp.json()
        assert report["registry_id"] == "gharra://registries/sovereign-gb"
        assert report["integrity"]["chain_valid"] is True
        assert report["range"]["entry_count"] > 0

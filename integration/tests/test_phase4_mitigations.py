"""Phase 4 Risk Mitigation Integration Tests.

Mitigations covered:
  3.1 -- Conflict-Free Replicated State (version vectors + conflict detection)
  4.1 -- Automated Scale Simulation (capacity estimation from live state)
  4.2 -- Capacity Planning (resource projection + recommendations)
  5.1 -- Zero-Trust Credential Rotation (trust anchor + attestation health)
  6.2 -- Regulatory Change Tracking (framework changes + impact assessment)

Standards:
  - Shapiro et al. CRDTs (2011)
  - ISO 25010 (Performance efficiency)
  - NIST SP 800-57 (Key Management)
  - ISO 27001 A.18.1 (Compliance with legal requirements)
  - EU AI Act Art. 9 (Risk management system)
"""

from __future__ import annotations

import httpx
import pytest


# =========================================================================
# Mitigation 3.1 -- Conflict-Free Replicated State
# =========================================================================


class TestConflictFreeReplicatedState:
    """Verify CRDT version vector endpoints and conflict detection."""

    @pytest.mark.asyncio
    async def test_version_vectors_endpoint(self, gharra_url: str):
        """Version vectors endpoint exists and returns 200."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/crdt/version-vectors")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_version_vectors_contains_agents(self, gharra_url: str):
        """Version vectors response lists all agents with versions."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/crdt/version-vectors")
        assert resp.status_code == 200
        data = resp.json()
        assert "vectors" in data
        assert "vector_count" in data
        assert data["vector_count"] > 0
        # Each vector has required fields
        for v in data["vectors"]:
            assert "agent_id" in v
            assert "version" in v
            assert "jurisdiction" in v

    @pytest.mark.asyncio
    async def test_version_vectors_has_registry_id(self, gharra_url: str):
        """Version vectors response includes registry identity."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/crdt/version-vectors")
        assert resp.status_code == 200
        data = resp.json()
        assert "registry_id" in data
        assert data["registry_id"] != ""
        assert "consistency_model" in data

    @pytest.mark.asyncio
    async def test_version_vectors_no_conflicts_in_clean_state(self, gharra_url: str):
        """Clean registry has no version conflicts."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/crdt/version-vectors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflicts_detected"] == 0

    @pytest.mark.asyncio
    async def test_detect_conflicts_endpoint(self, gharra_url: str):
        """Conflict detection endpoint accepts remote vectors."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/crdt/detect-conflicts",
                json={"remote_vectors": []},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "conflict_count" in data
        assert data["conflict_count"] == 0

    @pytest.mark.asyncio
    async def test_detect_conflicts_identifies_divergence(self, gharra_url: str):
        """Conflict detection identifies version divergence."""
        # Send a remote vector with a mismatched version
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/crdt/detect-conflicts",
                json={
                    "remote_vectors": [
                        {
                            "agent_id": "gharra://ie/agents/triage-e2e",
                            "version": "fake-version-that-wont-match",
                            "registry_id": "gharra://registries/remote-test",
                        }
                    ]
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflict_count"] == 1
        assert data["conflicts"][0]["agent_id"] == "gharra://ie/agents/triage-e2e"
        assert data["conflicts"][0]["resolution"] == "last-writer-wins"

    @pytest.mark.asyncio
    async def test_detect_conflicts_in_sync(self, gharra_url: str):
        """Conflict detection reports in-sync for matching versions."""
        # First get the real version
        async with httpx.AsyncClient() as client:
            vv_resp = await client.get(f"{gharra_url}/v1/admin/crdt/version-vectors")
        vectors = vv_resp.json()["vectors"]
        if vectors:
            real_vector = vectors[0]
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{gharra_url}/v1/admin/crdt/detect-conflicts",
                    json={
                        "remote_vectors": [
                            {
                                "agent_id": real_vector["agent_id"],
                                "version": real_vector["version"],
                                "registry_id": "gharra://registries/remote-test",
                            }
                        ]
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["in_sync"] == 1
            assert data["conflict_count"] == 0

    @pytest.mark.asyncio
    async def test_version_vectors_gb_sovereign(self, gharra_gb_url: str):
        """Version vectors accessible on GB sovereign."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/admin/crdt/version-vectors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["vector_count"] > 0


# =========================================================================
# Mitigation 4.1 -- Automated Scale Simulation
# =========================================================================


class TestAutomatedScaleSimulation:
    """Verify scale simulation estimates from live registry state."""

    @pytest.mark.asyncio
    async def test_scale_simulate_endpoint(self, gharra_url: str):
        """Scale simulation endpoint exists and returns 200."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{gharra_url}/v1/admin/scale/simulate", json={})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_scale_simulate_current_state(self, gharra_url: str):
        """Simulation includes current state metrics."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{gharra_url}/v1/admin/scale/simulate", json={})
        assert resp.status_code == 200
        data = resp.json()
        current = data["current_state"]
        assert "agents" in current
        assert "jurisdictions" in current
        assert "ledger_entries" in current
        assert current["agents"] > 0

    @pytest.mark.asyncio
    async def test_scale_simulate_estimates(self, gharra_url: str):
        """Simulation returns capacity estimates."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{gharra_url}/v1/admin/scale/simulate", json={})
        assert resp.status_code == 200
        data = resp.json()
        estimates = data["estimates"]
        assert "scale_factor" in estimates
        assert "discovery_latency_ms" in estimates
        assert "federation_latency_ms" in estimates
        assert "estimated_max_concurrent" in estimates
        assert estimates["scale_factor"] > 0

    @pytest.mark.asyncio
    async def test_scale_simulate_custom_target(self, gharra_url: str):
        """Simulation accepts custom target scale parameters."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/scale/simulate",
                json={
                    "target_agents": 500000,
                    "target_jurisdictions": 100,
                    "concurrent_requests": 1000,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_scale"]["agents"] == 500000
        assert data["risk_count"] > 0  # Should flag risks at this scale

    @pytest.mark.asyncio
    async def test_scale_simulate_risks(self, gharra_url: str):
        """High-scale simulation identifies risks."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/scale/simulate",
                json={"target_agents": 200000, "concurrent_requests": 600},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "risks" in data
        risk_types = [r["risk"] for r in data["risks"]]
        assert "storage_bottleneck" in risk_types or "concurrency_limit" in risk_types

    @pytest.mark.asyncio
    async def test_scale_simulate_gb_sovereign(self, gharra_gb_url: str):
        """Scale simulation accessible on GB sovereign."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{gharra_gb_url}/v1/admin/scale/simulate", json={})
        assert resp.status_code == 200


# =========================================================================
# Mitigation 4.2 -- Capacity Planning
# =========================================================================


class TestCapacityPlanning:
    """Verify capacity planning report generation."""

    @pytest.mark.asyncio
    async def test_capacity_plan_endpoint(self, gharra_url: str):
        """Capacity planning endpoint exists and returns 200."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/capacity/plan")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_capacity_plan_current_usage(self, gharra_url: str):
        """Capacity plan includes current usage metrics."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/capacity/plan")
        assert resp.status_code == 200
        data = resp.json()
        usage = data["current_usage"]
        assert "total_agents" in usage
        assert "agents_by_jurisdiction" in usage
        assert "total_registries" in usage
        assert "total_ledger_entries" in usage
        assert "estimated_storage_mb" in usage
        assert usage["total_agents"] > 0

    @pytest.mark.asyncio
    async def test_capacity_plan_limits(self, gharra_url: str):
        """Capacity plan includes system limits."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/capacity/plan")
        assert resp.status_code == 200
        data = resp.json()
        limits = data["capacity_limits"]
        assert "max_agents_sqlite" in limits
        assert "max_ledger_entries_recommended" in limits
        assert limits["max_agents_sqlite"] > 0

    @pytest.mark.asyncio
    async def test_capacity_plan_headroom(self, gharra_url: str):
        """Capacity plan includes headroom metrics."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/capacity/plan")
        assert resp.status_code == 200
        data = resp.json()
        headroom = data["headroom"]
        assert "agent_slots_remaining" in headroom
        assert "storage_headroom_pct" in headroom
        assert headroom["agent_slots_remaining"] > 0

    @pytest.mark.asyncio
    async def test_capacity_plan_recommendations(self, gharra_url: str):
        """Capacity plan includes recommendations list."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/capacity/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
        assert "recommendation_count" in data
        assert isinstance(data["recommendations"], list)

    @pytest.mark.asyncio
    async def test_capacity_plan_gb_sovereign(self, gharra_gb_url: str):
        """Capacity plan accessible on GB sovereign."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/admin/capacity/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_usage"]["total_agents"] > 0


# =========================================================================
# Mitigation 5.1 -- Zero-Trust Credential Rotation
# =========================================================================


class TestZeroTrustCredentialRotation:
    """Verify credential status and rotation check endpoints."""

    @pytest.mark.asyncio
    async def test_credential_status_endpoint(self, gharra_url: str):
        """Credential status endpoint exists and returns 200."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/credentials/status")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_credential_status_trust_anchors(self, gharra_url: str):
        """Credential status includes trust anchor health."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/credentials/status")
        assert resp.status_code == 200
        data = resp.json()
        ta = data["trust_anchors"]
        assert "total" in ta
        assert "active" in ta
        assert "expired" in ta
        assert "expiring_within_30_days" in ta

    @pytest.mark.asyncio
    async def test_credential_status_agent_credentials(self, gharra_url: str):
        """Credential status includes agent credential metrics."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/credentials/status")
        assert resp.status_code == 200
        data = resp.json()
        creds = data["agent_credentials"]
        assert "total_agents" in creds
        assert "with_jwks_uri" in creds
        assert "with_mtls" in creds
        assert creds["total_agents"] > 0

    @pytest.mark.asyncio
    async def test_credential_status_rotation_needed(self, gharra_url: str):
        """Credential status includes rotation recommendations."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/credentials/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "rotation_needed" in data
        assert "rotation_action_count" in data
        assert isinstance(data["rotation_needed"], list)

    @pytest.mark.asyncio
    async def test_rotation_check_known_agent(self, gharra_url: str):
        """Rotation check validates a known agent's credentials."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/credentials/rotate-check",
                json={
                    "agent_id": "gharra://ie/agents/triage-e2e",
                    "rotation_type": "jwks",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "gharra://ie/agents/triage-e2e"
        assert "safe_to_rotate" in data
        assert "checks" in data
        assert len(data["checks"]) >= 3

    @pytest.mark.asyncio
    async def test_rotation_check_unknown_agent(self, gharra_url: str):
        """Rotation check rejects unknown agent."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/credentials/rotate-check",
                json={
                    "agent_id": "gharra://ie/agents/nonexistent-agent",
                    "rotation_type": "jwks",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["safe_to_rotate"] is False

    @pytest.mark.asyncio
    async def test_credential_status_gb_sovereign(self, gharra_gb_url: str):
        """Credential status accessible on GB sovereign."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/admin/credentials/status")
        assert resp.status_code == 200


# =========================================================================
# Mitigation 6.2 -- Regulatory Change Tracking
# =========================================================================


class TestRegulatoryChangeTracking:
    """Verify regulatory change recording, listing, and impact assessment."""

    @pytest.mark.asyncio
    async def test_record_regulatory_change(self, gharra_url: str):
        """Record a regulatory change successfully."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{gharra_url}/v1/admin/regulatory/changes",
                json={
                    "framework": "GDPR",
                    "change_type": "amendment",
                    "jurisdiction": "EU",
                    "effective_date": "2026-06-01",
                    "description": "Updated cross-border transfer adequacy list",
                    "impact_assessment": "Requires review of TIA assessments",
                    "affected_mitigations": ["1.1", "2.3"],
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["framework"] == "GDPR"
        assert data["status"] == "recorded"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_regulatory_changes(self, gharra_url: str):
        """List regulatory changes returns recorded entries."""
        # Record a change first
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{gharra_url}/v1/admin/regulatory/changes",
                json={
                    "framework": "EU AI Act",
                    "change_type": "new_regulation",
                    "jurisdiction": "EU",
                    "effective_date": "2026-08-01",
                    "description": "High-risk AI system requirements effective",
                    "affected_mitigations": ["6.1", "6.3"],
                },
            )
            resp = await client.get(f"{gharra_url}/v1/admin/regulatory/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert "changes" in data
        assert data["total_count"] > 0

    @pytest.mark.asyncio
    async def test_list_regulatory_changes_filter_framework(self, gharra_url: str):
        """List regulatory changes with framework filter."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/regulatory/changes",
                params={"framework": "GDPR"},
            )
        assert resp.status_code == 200
        data = resp.json()
        for change in data["changes"]:
            assert change["framework"] == "GDPR"

    @pytest.mark.asyncio
    async def test_regulatory_impact_assessment(self, gharra_url: str):
        """Impact assessment cross-references changes against mitigations."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_url}/v1/admin/regulatory/impact")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_active_mitigations" in data
        assert data["total_active_mitigations"] == 18
        assert "affected_mitigations" in data
        assert "unaffected_mitigations" in data

    @pytest.mark.asyncio
    async def test_regulatory_impact_identifies_affected(self, gharra_url: str):
        """Impact assessment shows mitigations affected by recorded changes."""
        # Record a change with specific affected mitigations
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{gharra_url}/v1/admin/regulatory/changes",
                json={
                    "framework": "HIPAA",
                    "change_type": "guidance",
                    "jurisdiction": "US",
                    "effective_date": "2026-07-01",
                    "description": "Updated PHI de-identification guidance",
                    "affected_mitigations": ["2.2", "2.3"],
                },
            )
            resp = await client.get(f"{gharra_url}/v1/admin/regulatory/impact")
        assert resp.status_code == 200
        data = resp.json()
        assert data["affected_count"] > 0

    @pytest.mark.asyncio
    async def test_regulatory_change_logged_to_ledger(self, gharra_url: str):
        """Regulatory changes are logged to the transparency ledger."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{gharra_url}/v1/admin/events/replay",
                params={"operation": "regulatory.change_recorded"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_count"] > 0

    @pytest.mark.asyncio
    async def test_regulatory_changes_gb_sovereign(self, gharra_gb_url: str):
        """Regulatory changes endpoint accessible on GB sovereign."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/admin/regulatory/changes")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_regulatory_impact_gb_sovereign(self, gharra_gb_url: str):
        """Regulatory impact assessment accessible on GB sovereign."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{gharra_gb_url}/v1/admin/regulatory/impact")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_active_mitigations"] == 18

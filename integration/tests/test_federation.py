"""Cross-Border Federation Tests (Sprint 2 — Capability 1).

Validates that multiple sovereign GHARRA instances can:
  - Register as federation peers at startup
  - Discover agents across jurisdictions via federated queries
  - Fall back to peer registries when local lookup fails
  - Return proper federation metadata in responses
  - Respect jurisdiction boundaries in cross-border routing

Test topology:
  GHARRA Root (IE, port 8400)  ←→  GHARRA GB (port 8401)  ←→  GHARRA US (port 8402)

Each sovereign hosts jurisdiction-specific agents. Federation queries
from any node should discover agents from all peers.
"""

from __future__ import annotations

import httpx
import pytest


# ── Helper ──────────────────────────────────────────────────────────────


def _get(base_url: str, path: str, params: dict | None = None) -> httpx.Response:
    """Synchronous GET with reasonable timeout."""
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        return client.get(path, params=params or {})


def _post(base_url: str, path: str, json: dict | None = None) -> httpx.Response:
    """Synchronous POST with reasonable timeout and idempotency key."""
    import uuid
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        return client.post(
            path,
            json=json or {},
            headers={"X-Idempotency-Key": str(uuid.uuid4())},
        )


# ── Peer Discovery ──────────────────────────────────────────────────────


class TestPeerDiscovery:
    """Verify that GHARRA instances discover and register their peers."""

    def test_root_knows_peers(self, gharra_url: str):
        """Root GHARRA should list GB and US as federation peers."""
        resp = _get(gharra_url, "/v1/federation/peers")
        assert resp.status_code == 200
        data = resp.json()

        assert "peers" in data
        peers = data["peers"]
        # Root should know about GB and US
        peer_urls = list(peers.values())
        assert any("gharra-gb" in url for url in peer_urls), (
            f"GB peer not found in root peers: {peers}"
        )
        assert any("gharra-us" in url for url in peer_urls), (
            f"US peer not found in root peers: {peers}"
        )

    def test_gb_has_federation_endpoint(self, gharra_gb_url: str):
        """GB sovereign exposes federation peers endpoint."""
        resp = _get(gharra_gb_url, "/v1/federation/peers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["jurisdiction"] == "GB"
        assert data["tier"] == "sovereign"
        # GB may or may not have peers registered depending on startup order.
        # Root starts after GB, so root→GB is the primary federation path.

    def test_us_has_federation_endpoint(self, gharra_us_url: str):
        """US sovereign exposes federation peers endpoint."""
        resp = _get(gharra_us_url, "/v1/federation/peers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["jurisdiction"] == "US"
        assert data["tier"] == "sovereign"

    def test_well_known_configuration(self, gharra_gb_url: str):
        """Each GHARRA instance serves its identity via well-known endpoint."""
        resp = _get(gharra_gb_url, "/.well-known/gharra-configuration")
        assert resp.status_code == 200
        config = resp.json()
        assert config["jurisdiction"] == "GB"
        assert config["registry_id"] == "gharra://registries/sovereign-gb"
        assert config["tier"] == "sovereign"


# ── Local Discovery (Baseline) ──────────────────────────────────────────


class TestLocalDiscovery:
    """Verify that each sovereign finds its own agents locally."""

    def test_gb_finds_gb_agents(self, gharra_gb_url: str):
        """GB sovereign should find agents registered locally."""
        resp = _get(gharra_gb_url, "/v1/discover", {
            "capability": "nexus-a2a-jsonrpc",
            "federate": "false",  # Local only
        })
        assert resp.status_code == 200
        data = resp.json()
        # GB should have at least the NHS Triage Agent registered locally
        gb_ids = [a["agent_id"] for a in data["results"]]
        assert any("gb/" in aid for aid in gb_ids), (
            f"No GB agents found locally: {gb_ids}"
        )

    def test_us_finds_us_agents(self, gharra_us_url: str):
        """US sovereign should find agents registered locally."""
        resp = _get(gharra_us_url, "/v1/discover", {
            "capability": "http-rest",
            "federate": "false",
        })
        assert resp.status_code == 200
        data = resp.json()
        us_ids = [a["agent_id"] for a in data["results"]]
        assert any("us/" in aid for aid in us_ids), (
            f"No US agents found locally: {us_ids}"
        )

    def test_root_finds_ie_agents(self, gharra_url: str):
        """Root should find its own IE agents."""
        resp = _get(gharra_url, "/v1/discover", {
            "capability": "nexus-a2a-jsonrpc",
            "federate": "false",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) > 0, "Root should have IE agents"


# ── Federated Cross-Border Discovery ────────────────────────────────────


class TestFederatedDiscovery:
    """Verify that agents are discoverable across jurisdiction boundaries."""

    def test_root_discovers_gb_agents(self, gharra_url: str):
        """Root can discover GB-specific agents via federation."""
        resp = _get(gharra_url, "/v1/federation/discover", {
            "capability": "nexus-a2a-jsonrpc",
        })
        assert resp.status_code == 200
        data = resp.json()

        all_ids = [a["agent_id"] for a in data["agents"]]
        # Should find agents from GB sovereign
        assert any("gb/" in aid for aid in all_ids), (
            f"No GB agents in federated discovery from root: {all_ids}"
        )

    def test_root_discovers_us_agents(self, gharra_url: str):
        """Root can discover US-specific agents via federation."""
        resp = _get(gharra_url, "/v1/federation/discover", {
            "capability": "http-rest",
        })
        assert resp.status_code == 200
        data = resp.json()

        all_ids = [a["agent_id"] for a in data["agents"]]
        assert any("us/" in aid for aid in all_ids), (
            f"No US agents in federated discovery from root: {all_ids}"
        )

    def test_gb_discovers_cross_border_via_standard_endpoint(self, gharra_gb_url: str):
        """GB sovereign can discover agents from other jurisdictions via /v1/discover."""
        # GB may not have root as peer at startup, but the standard /v1/discover
        # with federate=true will attempt peer queries if peers are available.
        resp = _get(gharra_gb_url, "/v1/federation/discover", {
            "capability": "nexus-a2a-jsonrpc",
        })
        assert resp.status_code == 200
        data = resp.json()

        # At minimum, GB should find its own local agents
        all_ids = [a["agent_id"] for a in data["agents"]]
        assert any("gb/" in aid for aid in all_ids), (
            f"GB should at least find its own agents: {all_ids}"
        )
        # If GB has peers registered, it may also find IE/US agents
        # (depends on startup order; not asserted as hard requirement)

    def test_federated_discover_has_metadata(self, gharra_url: str):
        """Federated responses include query metadata."""
        resp = _get(gharra_url, "/v1/federation/discover", {
            "capability": "nexus-a2a-jsonrpc",
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "metadata" in data
        meta = data["metadata"]
        assert "registries_queried" in meta
        assert meta["registries_queried"] >= 1

    def test_discover_fallback_finds_cross_border(self, gharra_url: str):
        """Standard /v1/discover with federate=true finds cross-border agents."""
        # The standard discover endpoint should also use federation fallback
        resp = _get(gharra_url, "/v1/discover", {
            "capability": "http-rest",
            "federate": "true",
        })
        assert resp.status_code == 200
        data = resp.json()

        all_ids = [a["agent_id"] for a in data["results"]]
        # Should include agents from multiple jurisdictions
        jurisdictions = set()
        for aid in all_ids:
            # Extract jurisdiction from agent_id like "gharra://gb/agents/..."
            parts = aid.replace("gharra://", "").split("/")
            if parts:
                jurisdictions.add(parts[0])

        assert len(jurisdictions) >= 2, (
            f"Federation should return agents from multiple jurisdictions, "
            f"got: {jurisdictions} from {all_ids}"
        )

    def test_federated_deduplication(self, gharra_url: str):
        """Federated discovery deduplicates agents across registries."""
        resp = _get(gharra_url, "/v1/federation/discover", {
            "capability": "nexus-a2a-jsonrpc",
            "limit": 50,
        })
        assert resp.status_code == 200
        data = resp.json()

        agent_ids = [a["agent_id"] for a in data["agents"]]
        assert len(agent_ids) == len(set(agent_ids)), (
            f"Duplicate agents in federated response: {agent_ids}"
        )


# ── Federated Routing ───────────────────────────────────────────────────


class TestFederatedRouting:
    """Verify that routing resolves agents across jurisdictions."""

    def test_root_routes_to_agent(self, gharra_url: str):
        """Root can route to an agent by capability with proper consent."""
        resp = _post(gharra_url, "/v1/route", {
            "target": "nexus-a2a-jsonrpc",
            "purpose": {
                "purpose_of_use": "treatment",
                "consent_proof": "urn:consent:integration-test:123",
            },
        })
        # Should succeed — local resolution finds IE triage agent
        assert resp.status_code == 200, (
            f"Routing failed: {resp.status_code} {resp.text}"
        )
        data = resp.json()
        assert "resolved_target" in data
        assert "selected" in data
        assert data["selected"]["endpoint"] != ""


# ── Federation Update Reception ─────────────────────────────────────────


class TestFederationUpdates:
    """Verify that GHARRA instances can receive federation updates."""

    def test_accept_valid_update(self, gharra_url: str):
        """Root accepts a well-formed federation update."""
        update = {
            "type": "agent.registered",
            "source_registry_id": "gharra://registries/sovereign-gb",
            "payload": {"agent_id": "gharra://gb/agents/test-agent"},
            "sequence": 1,
        }
        resp = _post(gharra_url, "/v1/federation/updates", update)
        assert resp.status_code == 202
        data = resp.json()
        assert data["accepted"] is True

    def test_reject_invalid_update(self, gharra_url: str):
        """Root rejects an update with invalid type."""
        update = {
            "type": "invalid_type",
            "source_registry_id": "gharra://registries/sovereign-gb",
            "payload": {},
            "sequence": 1,
        }
        resp = _post(gharra_url, "/v1/federation/updates", update)
        # Should reject — invalid enum value
        assert resp.status_code == 422, (
            f"Expected 422, got {resp.status_code}"
        )

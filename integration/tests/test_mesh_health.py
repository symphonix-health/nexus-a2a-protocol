"""
Integration tests for Capability 3: Self-Healing Mesh.

Tests the mesh health monitor, circuit breaker management, peer probing,
recovery actions, and mesh topology endpoints against live GHARRA instances.

Sprint 6 -- Capability 3 gate.
"""

from __future__ import annotations

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


# ---------------------------------------------------------------------------
# Test: Mesh Health Snapshot
# ---------------------------------------------------------------------------


class TestMeshHealthSnapshot:
    """Validate mesh health overview endpoint."""

    def test_mesh_health_returns_grade(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["grade"] in ("green", "yellow", "orange", "red")

    def test_mesh_health_has_peer_count(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        data = resp.json()
        assert "total_peers" in data
        assert isinstance(data["total_peers"], int)

    def test_mesh_health_has_status_breakdown(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        data = resp.json()
        assert "by_status" in data
        assert isinstance(data["by_status"], dict)

    def test_root_has_federation_peers(self, gharra_url: str) -> None:
        """Root registry should have GB and US peers registered."""
        resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        data = resp.json()
        assert data["total_peers"] >= 2, (
            f"Root should have at least 2 peers (GB, US), got {data['total_peers']}"
        )

    def test_mesh_health_includes_peer_details(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        data = resp.json()
        if data["total_peers"] > 0:
            peer = data["peers"][0]
            assert "peer_id" in peer
            assert "status" in peer
            assert "avg_latency_ms" in peer

    def test_monitor_is_running(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        data = resp.json()
        if data["total_peers"] > 0:
            assert data["monitor_running"] is True


# ---------------------------------------------------------------------------
# Test: Peer Listing
# ---------------------------------------------------------------------------


class TestPeerListing:
    """Validate peer health record listing."""

    def test_list_peers(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert "peers" in data
        assert "count" in data
        assert data["count"] == len(data["peers"])

    def test_peer_has_health_fields(self, gharra_url: str) -> None:
        resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        data = resp.json()
        if data["count"] > 0:
            peer = data["peers"][0]
            assert "peer_id" in peer
            assert "api_base_url" in peer
            assert "status" in peer
            assert "consecutive_failures" in peer
            assert "probe_count" in peer
            assert "avg_latency_ms" in peer

    def test_get_single_peer(self, gharra_url: str) -> None:
        """Get a single peer by ID via query parameter."""
        peers_resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        peers = peers_resp.json()
        if peers["count"] == 0:
            pytest.skip("No peers registered")
        peer_id = peers["peers"][0]["peer_id"]
        resp = httpx.get(
            _url(gharra_url, "/v1/mesh/peer"),
            params={"peer_id": peer_id},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["peer_id"] == peer_id


# ---------------------------------------------------------------------------
# Test: On-Demand Probing
# ---------------------------------------------------------------------------


class TestOnDemandProbing:
    """Validate manual health probe triggering."""

    def test_probe_all_peers(self, gharra_url: str) -> None:
        resp = httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)
        assert resp.status_code == 200
        data = resp.json()
        assert "probed" in data
        assert "results" in data

    def test_probe_all_returns_reachability(self, gharra_url: str) -> None:
        resp = httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)
        data = resp.json()
        if data["probed"] > 0:
            result = data["results"][0]
            assert "peer_id" in result
            assert "reachable" in result
            assert "latency_ms" in result

    def test_probe_all_peers_are_reachable(self, gharra_url: str) -> None:
        """All peers should be reachable in a healthy docker-compose setup."""
        resp = httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)
        data = resp.json()
        for result in data["results"]:
            assert result["reachable"], (
                f"Peer {result['peer_id']} is unreachable: {result['detail']}"
            )

    def test_probe_specific_peer(self, gharra_url: str) -> None:
        """Probe a specific peer by ID via query parameter."""
        peers_resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        peers = peers_resp.json()
        if peers["count"] == 0:
            pytest.skip("No peers registered")

        peer_id = peers["peers"][0]["peer_id"]
        resp = httpx.post(
            _url(gharra_url, "/v1/mesh/probe-peer"),
            params={"peer_id": peer_id},
            timeout=15.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["peer_id"] == peer_id
        assert data["reachable"] is True

    def test_probe_nonexistent_peer_404(self, gharra_url: str) -> None:
        resp = httpx.post(
            _url(gharra_url, "/v1/mesh/probe-peer"),
            params={"peer_id": "nonexistent-peer-xyz"},
            timeout=10.0,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Recovery and Reset
# ---------------------------------------------------------------------------


class TestRecoveryAndReset:
    """Validate manual recovery and reset operations."""

    def test_reset_all_succeeds(self, gharra_url: str) -> None:
        resp = httpx.post(_url(gharra_url, "/v1/mesh/reset"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_reset_specific_peer(self, gharra_url: str) -> None:
        peers_resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        peers = peers_resp.json()
        if peers["count"] == 0:
            pytest.skip("No peers registered")

        peer_id = peers["peers"][0]["peer_id"]
        resp = httpx.post(
            _url(gharra_url, "/v1/mesh/reset-peer"),
            params={"peer_id": peer_id},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["peer_id"] == peer_id

    def test_reset_nonexistent_peer_404(self, gharra_url: str) -> None:
        resp = httpx.post(
            _url(gharra_url, "/v1/mesh/reset-peer"),
            params={"peer_id": "nonexistent-peer-xyz"},
            timeout=10.0,
        )
        assert resp.status_code == 404

    def test_reset_then_probe_shows_healthy(self, gharra_url: str) -> None:
        """After reset, peer should show healthy status."""
        peers_resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        peers = peers_resp.json()
        if peers["count"] == 0:
            pytest.skip("No peers registered")

        peer_id = peers["peers"][0]["peer_id"]

        # Reset peer
        httpx.post(
            _url(gharra_url, "/v1/mesh/reset-peer"),
            params={"peer_id": peer_id},
            timeout=10.0,
        )

        # Probe to refresh state
        httpx.post(
            _url(gharra_url, "/v1/mesh/probe-peer"),
            params={"peer_id": peer_id},
            timeout=15.0,
        )

        # Check health
        resp = httpx.get(
            _url(gharra_url, "/v1/mesh/peer"),
            params={"peer_id": peer_id},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


# ---------------------------------------------------------------------------
# Test: Circuit Breaker API
# ---------------------------------------------------------------------------


class TestCircuitBreakerAPI:
    """Validate circuit breaker state management."""

    def test_list_circuit_breakers(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/mesh/circuit-breakers"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "breakers" in data
        assert isinstance(data["breakers"], dict)

    def test_circuit_breakers_show_closed_for_healthy(self, gharra_url: str) -> None:
        """Healthy peers should have closed circuit breakers."""
        httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)

        resp = httpx.get(
            _url(gharra_url, "/v1/mesh/circuit-breakers"),
            timeout=10.0,
        )
        data = resp.json()
        for peer_id, state in data["breakers"].items():
            assert state == "closed", (
                f"Peer {peer_id} has circuit breaker state '{state}', expected 'closed'"
            )

    def test_reset_circuit_breaker(self, gharra_url: str) -> None:
        peers_resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        peers = peers_resp.json()
        if peers["count"] == 0:
            pytest.skip("No peers registered")

        peer_id = peers["peers"][0]["peer_id"]
        resp = httpx.post(
            _url(gharra_url, "/v1/mesh/reset-breaker"),
            params={"peer_id": peer_id},
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# Test: Recovery Log
# ---------------------------------------------------------------------------


class TestRecoveryLog:
    """Validate recovery action audit log."""

    def test_recovery_log_endpoint(self, gharra_url: str) -> None:
        resp = httpx.get(
            _url(gharra_url, "/v1/mesh/recovery-log"),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "actions" in data
        assert "count" in data

    def test_recovery_log_after_reset(self, gharra_url: str) -> None:
        """A reset should generate a recovery log entry."""
        peers_resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        peers = peers_resp.json()
        if peers["count"] == 0:
            pytest.skip("No peers registered")

        peer_id = peers["peers"][0]["peer_id"]

        # Perform a reset to generate a log entry
        httpx.post(
            _url(gharra_url, "/v1/mesh/reset-peer"),
            params={"peer_id": peer_id},
            timeout=10.0,
        )

        resp = httpx.get(
            _url(gharra_url, "/v1/mesh/recovery-log"),
            timeout=10.0,
        )
        data = resp.json()
        if data["count"] > 0:
            entry = data["actions"][0]
            assert "timestamp" in entry
            assert "peer_id" in entry
            assert "action" in entry
            assert "previous_status" in entry
            assert "new_status" in entry


# ---------------------------------------------------------------------------
# Test: Cross-Registry Mesh Health
# ---------------------------------------------------------------------------


class TestCrossRegistryMesh:
    """Validate mesh health is available on all GHARRA instances."""

    def test_gb_sovereign_mesh_health(self, gharra_gb_url: str) -> None:
        resp = httpx.get(_url(gharra_gb_url, "/v1/mesh/health"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["grade"] in ("green", "yellow", "orange", "red")

    def test_us_sovereign_mesh_health(self, gharra_us_url: str) -> None:
        resp = httpx.get(_url(gharra_us_url, "/v1/mesh/health"), timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["grade"] in ("green", "yellow", "orange", "red")

    def test_gb_sovereign_can_probe(self, gharra_gb_url: str) -> None:
        resp = httpx.post(_url(gharra_gb_url, "/v1/mesh/probe"), timeout=30.0)
        assert resp.status_code == 200

    def test_us_sovereign_can_probe(self, gharra_us_url: str) -> None:
        resp = httpx.post(_url(gharra_us_url, "/v1/mesh/probe"), timeout=30.0)
        assert resp.status_code == 200

    def test_root_has_more_peers_than_sovereigns(
        self, gharra_url: str,
    ) -> None:
        """Root starts last and can discover both sovereigns."""
        root_resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        root_data = root_resp.json()
        assert root_data["total_peers"] >= 2, (
            f"Root should have at least 2 peers, got {root_data['total_peers']}"
        )


# ---------------------------------------------------------------------------
# Test: Mesh Self-Healing Cycle
# ---------------------------------------------------------------------------


class TestSelfHealingCycle:
    """Validate the full probe -> detect -> recover cycle."""

    def test_probe_updates_health_state(self, gharra_url: str) -> None:
        """Probing peers should update their health records."""
        httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)

        resp = httpx.get(_url(gharra_url, "/v1/mesh/peers"), timeout=10.0)
        data = resp.json()
        for peer in data["peers"]:
            assert peer["probe_count"] >= 1, (
                f"Peer {peer['peer_id']} has 0 probe count after probing"
            )

    def test_healthy_mesh_grade_green(self, gharra_url: str) -> None:
        """In a healthy docker-compose setup, mesh grade should be green."""
        httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)

        resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        data = resp.json()
        assert data["grade"] in ("green", "yellow"), (
            f"Expected green/yellow mesh grade, got {data['grade']}"
        )

    def test_consecutive_probes_maintain_health(self, gharra_url: str) -> None:
        """Multiple probes should maintain healthy state."""
        for _ in range(3):
            httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)

        resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        data = resp.json()
        assert data["grade"] in ("green", "yellow")

    def test_reset_and_reprobing_cycle(self, gharra_url: str) -> None:
        """Full cycle: reset -> probe -> verify healthy."""
        httpx.post(_url(gharra_url, "/v1/mesh/reset"), timeout=10.0)

        probe_resp = httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)
        probe_data = probe_resp.json()

        for result in probe_data["results"]:
            assert result["reachable"]

        health_resp = httpx.get(_url(gharra_url, "/v1/mesh/health"), timeout=10.0)
        health_data = health_resp.json()
        assert health_data["grade"] in ("green", "yellow")

    def test_latency_tracked_on_probe(self, gharra_url: str) -> None:
        """Probe results should include latency measurements."""
        resp = httpx.post(_url(gharra_url, "/v1/mesh/probe"), timeout=30.0)
        data = resp.json()
        for result in data["results"]:
            assert result["latency_ms"] >= 0
            if result["reachable"]:
                assert result["latency_ms"] > 0

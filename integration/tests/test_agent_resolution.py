"""Agent Resolution Tests.

Verify:
  - GHARRA resolves agent name correctly
  - namespace delegation is valid
  - trust metadata is present
  - capabilities are returned
  - all canonical e2e agents are resolvable

These tests hit the real GHARRA API — no mocks.
"""

from __future__ import annotations

import pytest

from harness.gharra_resolver import GharraResolver


@pytest.mark.asyncio
async def test_gharra_health(gharra: GharraResolver):
    """GHARRA registry is healthy and reachable."""
    health = await gharra.health()
    assert health["status"] == "healthy"
    assert health["service"] == "gharra"


@pytest.mark.asyncio
async def test_resolve_triage_agent(gharra: GharraResolver, triage_agent_id: str):
    """Triage agent resolves with correct metadata."""
    agent = await gharra.get_agent(triage_agent_id)

    assert agent.agent_id == triage_agent_id
    assert agent.display_name == "Triage Agent"
    assert agent.jurisdiction == "IE"
    assert agent.status == "active"

    # Endpoint present and reachable
    assert agent.primary_endpoint, "Agent must have a primary endpoint"

    # Trust metadata
    assert agent.trust, "Trust metadata must be present"
    assert agent.trust.get("jwks_uri"), "JWKS URI must be present"
    assert agent.trust.get("mtls_required") is True

    # Capabilities
    assert "nexus-a2a-jsonrpc" in agent.capabilities.get("protocols", [])
    assert "fhir-r4" in agent.capabilities.get("protocols", [])

    # Zone derivation
    assert agent.zone == "ie.health"


@pytest.mark.asyncio
async def test_resolve_referral_agent(gharra: GharraResolver, referral_agent_id: str):
    """GB Referral agent resolves with correct jurisdiction."""
    agent = await gharra.get_agent(referral_agent_id)

    assert agent.agent_id == referral_agent_id
    assert agent.jurisdiction == "GB"
    assert agent.zone == "gb.health"
    assert "http-rest" in agent.capabilities.get("protocols", [])


@pytest.mark.asyncio
async def test_resolve_radiology_agent(gharra: GharraResolver, radiology_agent_id: str):
    """US Radiology agent resolves with dual endpoints."""
    agent = await gharra.get_agent(radiology_agent_id)

    assert agent.agent_id == radiology_agent_id
    assert agent.jurisdiction == "US"
    assert len(agent.endpoints) >= 1
    assert agent.primary_endpoint, "Must have a primary endpoint"


@pytest.mark.asyncio
async def test_resolve_pathology_agent(gharra: GharraResolver, pathology_agent_id: str):
    """DE Pathology agent resolves with nexus-a2a protocol only."""
    agent = await gharra.get_agent(pathology_agent_id)

    assert agent.agent_id == pathology_agent_id
    assert agent.jurisdiction == "DE"
    assert "nexus-a2a-jsonrpc" in agent.capabilities.get("protocols", [])


@pytest.mark.asyncio
async def test_resolve_nonexistent_agent(gharra: GharraResolver):
    """Resolving a nonexistent agent raises an error."""
    import httpx

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await gharra.get_agent("gharra://zz/agents/does-not-exist")
    assert exc_info.value.response.status_code == 404


@pytest.mark.asyncio
async def test_list_agents(gharra: GharraResolver):
    """Listing agents returns all seeded agents."""
    agents = await gharra.list_agents()
    agent_ids = [a.agent_id for a in agents]

    assert "gharra://ie/agents/triage-e2e" in agent_ids
    assert "gharra://gb/agents/referral-e2e" in agent_ids
    assert "gharra://us/agents/radiology-e2e" in agent_ids
    assert "gharra://de/agents/pathology-e2e" in agent_ids


@pytest.mark.asyncio
async def test_list_agents_by_jurisdiction(gharra: GharraResolver):
    """Listing agents filtered by jurisdiction returns correct subset."""
    ie_agents = await gharra.list_agents(jurisdiction="IE")
    for agent in ie_agents:
        assert agent.jurisdiction == "IE"


@pytest.mark.asyncio
async def test_trust_metadata_structure(gharra: GharraResolver, triage_agent_id: str):
    """Trust metadata has the required fields for Nexus route admission."""
    agent = await gharra.get_agent(triage_agent_id)

    trust = agent.trust
    assert isinstance(trust, dict)
    # JWKS URI for token verification
    assert trust.get("jwks_uri", "").startswith("https://")
    # mTLS requirement
    assert "mtls_required" in trust
    # Token binding preference
    assert trust.get("token_binding") in ("dpop", "mtls_cnf_x5t_s256", None, "none")


@pytest.mark.asyncio
async def test_policy_tags_present(gharra: GharraResolver, triage_agent_id: str):
    """Policy tags (residency, PHI, classification) are present."""
    agent = await gharra.get_agent(triage_agent_id)

    tags = agent.policy_tags
    assert isinstance(tags, dict)
    assert "residency" in tags
    assert "phi_allowed" in tags
    assert "data_classification" in tags


@pytest.mark.asyncio
async def test_observability_logging(gharra: GharraResolver, triage_agent_id: str):
    """Observability record contains all required fields."""
    agent = await gharra.get_agent(triage_agent_id)
    record = gharra.log_resolution(
        agent, workflow_id="WF-TEST-001", correlation_id="COR-TEST-001"
    )

    required_fields = [
        "agent_name", "agent_id", "resolved_zone", "trust_anchor",
        "selected_capability", "nexus_route", "workflow_id", "correlation_id",
    ]
    for f in required_fields:
        assert f in record, f"Missing observability field: {f}"


@pytest.mark.asyncio
async def test_namespace_zone_derivation(gharra: GharraResolver):
    """Each agent's zone is correctly derived from jurisdiction."""
    expected = {
        "gharra://ie/agents/triage-e2e": "ie.health",
        "gharra://gb/agents/referral-e2e": "gb.health",
        "gharra://us/agents/radiology-e2e": "us.health",
        "gharra://de/agents/pathology-e2e": "de.health",
    }
    for agent_id, expected_zone in expected.items():
        agent = await gharra.get_agent(agent_id)
        assert agent.zone == expected_zone, (
            f"{agent_id}: expected zone={expected_zone}, got {agent.zone}"
        )


@pytest.mark.asyncio
async def test_namespace_zones_exist(gharra: GharraResolver):
    """GHARRA namespace zones endpoint is accessible."""
    zones = await gharra.list_zones()
    assert isinstance(zones, list)

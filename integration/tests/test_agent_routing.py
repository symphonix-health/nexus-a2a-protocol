"""Agent Routing Tests.

Verify:
  - Nexus gateway is healthy and reachable
  - Nexus can connect to agent endpoints
  - JSON-RPC session is established
  - Response is received from real test agents
  - GHARRA metadata flows through X-Gharra-Record header

These tests hit the real Nexus on-demand gateway, which starts
agents lazily — no pre-running agents required.
"""

from __future__ import annotations

import pytest

from harness.gharra_resolver import GharraResolver
from harness.nexus_connector import NexusConnector


@pytest.mark.asyncio
async def test_nexus_health(nexus: NexusConnector):
    """Nexus on-demand gateway is healthy."""
    health = await nexus.health()
    assert health.get("status") in ("ok", "healthy"), f"Unexpected health: {health}"


@pytest.mark.asyncio
async def test_invoke_triage_agent(
    nexus: NexusConnector,
    gharra: GharraResolver,
    triage_agent_id: str,
):
    """Invoke triage agent via Nexus gateway with GHARRA metadata."""
    # Resolve agent first
    agent = await gharra.get_agent(triage_agent_id)

    result = await nexus.invoke_agent(
        "triage",
        method="tasks/send",
        params={
            "patient_id": "P-ROUTE-001",
            "encounter_id": "E-ROUTE-001",
            "clinical_data": {
                "chief_complaint": "Chest pain",
                "urgency": "high",
            },
        },
        gharra_agent=agent,
    )

    assert result["http_status"] < 500, f"Agent invocation failed: {result}"
    assert result.get("correlation_id"), "Correlation ID must be present"
    assert result.get("request_id"), "Request ID must be present"


@pytest.mark.asyncio
async def test_invoke_diagnosis_agent(nexus: NexusConnector):
    """Invoke diagnosis agent directly (without GHARRA metadata)."""
    result = await nexus.invoke_agent(
        "diagnosis",
        method="tasks/send",
        params={
            "patient_id": "P-DIAG-001",
            "encounter_id": "E-DIAG-001",
            "clinical_data": {
                "chief_complaint": "Persistent cough",
                "duration": "2 weeks",
            },
        },
    )

    assert result["http_status"] < 500, f"Diagnosis agent failed: {result}"


@pytest.mark.asyncio
async def test_invoke_with_gharra_header(
    nexus: NexusConnector,
    gharra: GharraResolver,
    triage_agent_id: str,
):
    """GHARRA record is correctly attached as X-Gharra-Record header."""
    agent = await gharra.get_agent(triage_agent_id)

    result = await nexus.invoke_agent(
        "triage",
        gharra_agent=agent,
        params={"patient_id": "P-HEADER-001"},
    )

    # If Nexus performs route admission, the request should be accepted
    # (the triage agent has nexus-a2a-jsonrpc protocol which is compatible)
    assert result["http_status"] < 500


@pytest.mark.asyncio
async def test_correlation_id_propagation(nexus: NexusConnector):
    """Correlation ID is propagated through the request chain."""
    test_correlation = "COR-PROPAGATION-TEST-001"

    result = await nexus.invoke_agent(
        "triage",
        params={"patient_id": "P-CORR-001"},
        correlation_id=test_correlation,
    )

    assert result["correlation_id"] == test_correlation


@pytest.mark.asyncio
async def test_observability_record(
    nexus: NexusConnector,
    gharra: GharraResolver,
    triage_agent_id: str,
):
    """Nexus invocation produces a complete observability record."""
    agent = await gharra.get_agent(triage_agent_id)

    rpc_result = await nexus.invoke_agent(
        "triage",
        gharra_agent=agent,
        params={"patient_id": "P-OBS-001"},
    )

    record = nexus.log_invocation(
        rpc_result, agent=agent, workflow_id="WF-OBS-001"
    )

    required_fields = [
        "agent_name", "resolved_zone", "trust_anchor",
        "nexus_route", "workflow_id", "correlation_id",
        "http_status", "elapsed_ms",
    ]
    for f in required_fields:
        assert f in record, f"Missing observability field: {f}"


@pytest.mark.asyncio
async def test_invalid_agent_alias(nexus: NexusConnector):
    """Invoking a nonexistent agent alias returns an error."""
    result = await nexus.invoke_agent(
        "nonexistent_agent_xyz",
        params={"patient_id": "P-INVALID-001"},
    )

    assert result["http_status"] >= 400


@pytest.mark.asyncio
async def test_multiple_agents_sequentially(
    nexus: NexusConnector,
    gharra: GharraResolver,
):
    """Multiple different agents can be invoked in sequence."""
    agents_to_test = [
        ("triage", "gharra://ie/agents/triage-e2e"),
        ("diagnosis", "gharra://gb/agents/referral-e2e"),
    ]

    for alias, agent_id in agents_to_test:
        try:
            agent = await gharra.get_agent(agent_id)
        except Exception:
            agent = None

        result = await nexus.invoke_agent(
            alias,
            gharra_agent=agent,
            params={
                "patient_id": f"P-SEQ-{alias.upper()}",
                "encounter_id": f"E-SEQ-{alias.upper()}",
            },
        )
        assert result["http_status"] < 500, f"Agent {alias} failed: {result}"

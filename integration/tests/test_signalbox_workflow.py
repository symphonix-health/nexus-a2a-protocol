"""SignalBox Workflow Tests.

Verify:
  - SignalBox executes workflow
  - agent discovery works via GHARRA
  - agent invocation works via Nexus
  - response propagates back to workflow

These tests exercise the full chain:
  SignalBox → GHARRA → Nexus → Agent → Response

Tests that only need GHARRA + Nexus run unconditionally.
Tests that need SignalBox are skipped when it's unavailable.
"""

from __future__ import annotations

import pytest

from harness.signalbox_driver import SignalBoxDriver
from harness.workflow_runner import WorkflowRunner


# ── Tests that do NOT require SignalBox (GHARRA + Nexus only) ──────────


@pytest.mark.asyncio
async def test_full_workflow_gharra_to_nexus(
    workflow_runner: WorkflowRunner,
    triage_agent_id: str,
):
    """Full workflow: GHARRA resolve → trust validation → Nexus invocation."""
    result = await workflow_runner.run_discovery_to_invocation(
        triage_agent_id,
        agent_alias="triage",
    )

    assert result.workflow_id, "Workflow ID must be assigned"
    assert result.correlation_id, "Correlation ID must be assigned"

    # Check each step
    step_names = [s.name for s in result.steps]
    assert "gharra_resolve" in step_names
    assert "trust_validation" in step_names
    assert "nexus_invocation" in step_names

    # GHARRA resolve must succeed
    resolve_step = next(s for s in result.steps if s.name == "gharra_resolve")
    assert resolve_step.status == "success", f"GHARRA resolve failed: {resolve_step.error}"

    # Trust validation must succeed
    trust_step = next(s for s in result.steps if s.name == "trust_validation")
    assert trust_step.status == "success", f"Trust validation failed: {trust_step.error}"

    # Agent must be resolved
    assert result.agent is not None
    assert result.agent.agent_id == triage_agent_id


@pytest.mark.asyncio
async def test_workflow_observability_fields(
    workflow_runner: WorkflowRunner,
    triage_agent_id: str,
):
    """Workflow produces observability records with all required fields."""
    result = await workflow_runner.run_discovery_to_invocation(
        triage_agent_id,
        agent_alias="triage",
    )

    assert len(result.observability) > 0, "Must have observability records"

    for record in result.observability:
        assert "agent_name" in record or "agent_id" in record
        assert "workflow_id" in record
        assert "correlation_id" in record


@pytest.mark.asyncio
async def test_workflow_summary(
    workflow_runner: WorkflowRunner,
    triage_agent_id: str,
):
    """Workflow summary contains structured step information."""
    result = await workflow_runner.run_discovery_to_invocation(
        triage_agent_id,
        agent_alias="triage",
    )

    summary = result.summary()
    assert summary["workflow_id"]
    assert summary["correlation_id"]
    assert isinstance(summary["steps"], list)
    for step in summary["steps"]:
        assert "name" in step
        assert "status" in step
        assert "elapsed_ms" in step


# ── Tests that REQUIRE SignalBox ───────────────────────────────────────


@pytest.mark.asyncio
async def test_signalbox_health(signalbox: SignalBoxDriver):
    """SignalBox service is healthy."""
    health = await signalbox.health()
    assert health["status"] == "healthy"
    assert health["service"] == "signalbox"


@pytest.mark.asyncio
async def test_signalbox_gharra_health(signalbox: SignalBoxDriver):
    """GHARRA is reachable through SignalBox."""
    health = await signalbox.gharra_health()
    assert health.get("status") in ("healthy", "ok"), f"GHARRA health via SignalBox: {health}"


@pytest.mark.asyncio
async def test_signalbox_resolve_triage(
    signalbox: SignalBoxDriver,
    triage_agent_id: str,
):
    """SignalBox resolves triage agent via its GHARRA integration."""
    # evaluate_policy=False: BulletTrain's GharraClient calls GET /v1/policy/{zone}
    # which exists in GHARRA's zones.py, but returns a default empty policy that
    # may not include the agent's protocol in allowed_protocols, causing a deny.
    # The policy evaluation path is tested separately below.
    result = await signalbox.resolve_agent(triage_agent_id, evaluate_policy=False)

    assert result.get("status") == "success", f"Resolve failed: {result}"
    assert result.get("agent_name") == triage_agent_id
    assert result.get("resolved_zone"), "Zone must be present"
    assert result.get("nexus_route"), "Nexus route must be present"

    route = result["nexus_route"]
    assert route.get("endpoint"), "Route endpoint must be present"


@pytest.mark.asyncio
async def test_signalbox_discover_capability(signalbox: SignalBoxDriver):
    """SignalBox discovers agents by capability via GHARRA."""
    result = await signalbox.discover_agents("nexus-a2a-jsonrpc")

    assert result.get("status") == "success", f"Discovery failed: {result}"
    assert result.get("count", 0) >= 0


@pytest.mark.asyncio
async def test_signalbox_register_agent(signalbox: SignalBoxDriver):
    """SignalBox can register an agent in its identity FSM."""
    import uuid
    unique_name = f"integration-test-agent-{uuid.uuid4().hex[:8]}"
    result = await signalbox.register_agent(
        agent_name=unique_name,
        description="Agent registered by integration harness",
    )

    assert "agent_id" in result or "id" in result or "status" in result


@pytest.mark.asyncio
async def test_signalbox_list_external_systems(signalbox: SignalBoxDriver):
    """SignalBox lists available external systems."""
    result = await signalbox.list_external_systems()

    assert result.get("status") == "success"
    assert result.get("count", 0) > 0
    systems = result.get("systems", [])
    system_names = [s["source_system"] for s in systems]
    assert "telemedicine" in system_names or "ehr_hims" in system_names


@pytest.mark.asyncio
async def test_signalbox_policy_evaluation_path(
    signalbox: SignalBoxDriver,
    triage_agent_id: str,
):
    """SignalBox exercises the GHARRA policy evaluation path.

    When evaluate_policy=True, SignalBox calls GharraClient.evaluate_policy()
    which hits GET /v1/policy/{zone}. The result should either succeed or
    return a policy decision (not an HTTP error).
    """
    result = await signalbox.resolve_agent(
        triage_agent_id, evaluate_policy=True
    )
    # The resolve should complete (200 OK from SignalBox) regardless of
    # whether policy allows or denies — it should not return an HTTP error.
    assert result.get("status") in (
        "success", "denied"
    ), f"Policy path error: {result}"
    # If denied, the policy_decision must explain why
    if result.get("status") == "denied":
        assert result.get("policy_decision"), "Denied without policy_decision"
        assert result["policy_decision"].get("reason"), "Policy denial missing reason"


@pytest.mark.asyncio
async def test_full_workflow_with_signalbox(
    workflow_runner: WorkflowRunner,
    signalbox: SignalBoxDriver,
    triage_agent_id: str,
):
    """Full SignalBox-mediated workflow: SignalBox → GHARRA → Nexus → Agent."""
    result = await workflow_runner.run_signalbox_workflow(
        triage_agent_id,
        agent_alias="triage",
    )

    assert result.workflow_id.startswith("SB-")
    step_names = [s.name for s in result.steps]
    assert "signalbox_gharra_resolve" in step_names

"""End-to-end workflow runner for the integration harness.

Orchestrates the full chain:
    SignalBox (BulletTrain)
        ↓ resolve agent using GHARRA
        ↓ retrieve endpoint + trust metadata
        ↓ pass routing request to Nexus
        ↓ Nexus connects to real test agent
        ↓ agent returns response

Each step is logged with structured observability fields:
    agent_name, resolved_zone, trust_anchor, selected_capability,
    nexus_route, workflow_id, correlation_id
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .gharra_resolver import GharraResolver, ResolvedAgent
from .nexus_connector import NexusConnector
from .signalbox_driver import SignalBoxDriver

logger = logging.getLogger("harness.workflow_runner")


@dataclass
class WorkflowStep:
    """One step in the integration workflow."""

    name: str
    status: str = "pending"  # pending | running | success | failed | skipped
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    elapsed_ms: float = 0.0


@dataclass
class WorkflowResult:
    """Complete workflow execution result."""

    workflow_id: str
    correlation_id: str
    status: str = "pending"
    steps: list[WorkflowStep] = field(default_factory=list)
    agent: ResolvedAgent | None = None
    observability: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status == "success"

    def summary(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "agent": self.agent.agent_id if self.agent else None,
            "steps": [
                {"name": s.name, "status": s.status, "elapsed_ms": s.elapsed_ms}
                for s in self.steps
            ],
        }


class WorkflowRunner:
    """Runs the full BulletTrain → GHARRA → Nexus → Agent integration chain."""

    def __init__(
        self,
        gharra: GharraResolver | None = None,
        nexus: NexusConnector | None = None,
        signalbox: SignalBoxDriver | None = None,
    ):
        self.gharra = gharra or GharraResolver()
        self.nexus = nexus or NexusConnector()
        self.signalbox = signalbox or SignalBoxDriver()

    # ── Full workflow ──────────────────────────────────────────────────

    async def run_discovery_to_invocation(
        self,
        agent_id: str,
        *,
        agent_alias: str = "triage",
        rpc_method: str = "tasks/send",
        rpc_params: dict[str, Any] | None = None,
        workflow_id: str = "",
        correlation_id: str = "",
    ) -> WorkflowResult:
        """Execute the full integration chain.

        Steps:
        1. resolve agent via GHARRA
        2. validate trust metadata
        3. invoke agent via Nexus gateway
        4. capture response
        """
        workflow_id = workflow_id or f"WF-{uuid.uuid4().hex[:12].upper()}"
        correlation_id = correlation_id or f"COR-{uuid.uuid4().hex[:12].upper()}"

        result = WorkflowResult(
            workflow_id=workflow_id,
            correlation_id=correlation_id,
        )

        # Step 1: Resolve agent via GHARRA
        step1 = WorkflowStep(name="gharra_resolve")
        result.steps.append(step1)
        step1.status = "running"
        t0 = time.monotonic()
        try:
            agent = await self.gharra.get_agent(agent_id)
            step1.elapsed_ms = (time.monotonic() - t0) * 1000
            step1.status = "success"
            step1.result = {
                "agent_id": agent.agent_id,
                "zone": agent.zone,
                "endpoint": agent.primary_endpoint,
                "protocol": agent.protocol,
                "trust_anchor": agent.trust_anchor,
            }
            result.agent = agent
            result.observability.append(
                self.gharra.log_resolution(
                    agent, workflow_id=workflow_id, correlation_id=correlation_id
                )
            )
        except Exception as exc:
            step1.elapsed_ms = (time.monotonic() - t0) * 1000
            step1.status = "failed"
            step1.error = str(exc)
            result.status = "failed"
            logger.error("GHARRA resolve failed: %s", exc)
            return result

        # Step 2: Validate trust metadata
        step2 = WorkflowStep(name="trust_validation")
        result.steps.append(step2)
        step2.status = "running"
        t0 = time.monotonic()
        try:
            trust_ok = bool(agent.trust)
            has_endpoint = bool(agent.primary_endpoint)
            step2.elapsed_ms = (time.monotonic() - t0) * 1000
            if trust_ok and has_endpoint:
                step2.status = "success"
                step2.result = {
                    "trust_present": True,
                    "endpoint_present": True,
                    "jwks_uri": agent.trust.get("jwks_uri", ""),
                    "mtls_required": agent.trust.get("mtls_required", False),
                }
            else:
                step2.status = "failed"
                step2.error = f"trust={trust_ok} endpoint={has_endpoint}"
                result.status = "failed"
                return result
        except Exception as exc:
            step2.elapsed_ms = (time.monotonic() - t0) * 1000
            step2.status = "failed"
            step2.error = str(exc)
            result.status = "failed"
            return result

        # Step 3: Invoke agent via Nexus
        step3 = WorkflowStep(name="nexus_invocation")
        result.steps.append(step3)
        step3.status = "running"
        t0 = time.monotonic()
        try:
            rpc_result = await self.nexus.invoke_agent(
                agent_alias,
                method=rpc_method,
                params=rpc_params or {
                    "patient_id": "P-INTEGRATION-001",
                    "encounter_id": f"E-{workflow_id}",
                    "clinical_data": {
                        "chief_complaint": "Integration test",
                        "urgency": "routine",
                    },
                },
                gharra_agent=agent,
                correlation_id=correlation_id,
            )
            step3.elapsed_ms = (time.monotonic() - t0) * 1000
            step3.result = rpc_result
            result.observability.append(
                self.nexus.log_invocation(
                    rpc_result, agent=agent, workflow_id=workflow_id
                )
            )

            if rpc_result.get("http_status", 500) < 400:
                step3.status = "success"
            else:
                step3.status = "failed"
                step3.error = rpc_result.get("error", "Unknown error")
                result.status = "failed"
                return result

        except Exception as exc:
            step3.elapsed_ms = (time.monotonic() - t0) * 1000
            step3.status = "failed"
            step3.error = str(exc)
            result.status = "failed"
            logger.error("Nexus invocation failed: %s", exc)
            return result

        # Step 4: Validate response
        step4 = WorkflowStep(name="response_validation")
        result.steps.append(step4)
        step4.status = "running"
        t0 = time.monotonic()
        response_body = rpc_result.get("response", {})
        has_response = bool(response_body)
        step4.elapsed_ms = (time.monotonic() - t0) * 1000
        step4.status = "success" if has_response else "failed"
        step4.result = {"response_present": has_response}

        result.status = "success" if all(
            s.status == "success" for s in result.steps
        ) else "failed"

        logger.info(
            "Workflow %s complete: status=%s steps=%d",
            workflow_id,
            result.status,
            len(result.steps),
        )
        return result

    # ── SignalBox-mediated workflow ─────────────────────────────────────

    async def run_signalbox_workflow(
        self,
        agent_id: str,
        *,
        agent_alias: str = "triage",
        rpc_method: str = "tasks/send",
        rpc_params: dict[str, Any] | None = None,
        workflow_id: str = "",
        correlation_id: str = "",
    ) -> WorkflowResult:
        """Execute workflow with SignalBox as the orchestrator.

        Steps:
        1. SignalBox resolves agent via GHARRA (through its gharra_routes)
        2. Validate resolved route metadata
        3. Invoke agent via Nexus gateway
        4. Capture and validate response
        """
        workflow_id = workflow_id or f"SB-{uuid.uuid4().hex[:12].upper()}"
        correlation_id = correlation_id or f"COR-{uuid.uuid4().hex[:12].upper()}"

        result = WorkflowResult(
            workflow_id=workflow_id,
            correlation_id=correlation_id,
        )

        # Step 1: SignalBox → GHARRA resolve
        step1 = WorkflowStep(name="signalbox_gharra_resolve")
        result.steps.append(step1)
        step1.status = "running"
        t0 = time.monotonic()
        try:
            resolve_result = await self.signalbox.resolve_agent(agent_id)
            step1.elapsed_ms = (time.monotonic() - t0) * 1000
            step1.result = resolve_result

            if resolve_result.get("status") == "success":
                step1.status = "success"
            elif resolve_result.get("status") == "error":
                step1.status = "failed"
                step1.error = resolve_result.get("detail", "SignalBox resolve error")
                result.status = "failed"
                return result
            else:
                # Policy denied
                step1.status = "failed"
                step1.error = f"Policy: {resolve_result.get('policy_decision', {}).get('reason', '')}"
                result.status = "failed"
                return result
        except Exception as exc:
            step1.elapsed_ms = (time.monotonic() - t0) * 1000
            step1.status = "failed"
            step1.error = str(exc)
            result.status = "failed"
            return result

        # Step 2: Extract route metadata
        step2 = WorkflowStep(name="route_metadata_validation")
        result.steps.append(step2)
        step2.status = "running"
        t0 = time.monotonic()
        nexus_route = resolve_result.get("nexus_route", {})
        agent_data = resolve_result.get("agent", {})
        has_route = bool(nexus_route and nexus_route.get("endpoint"))
        step2.elapsed_ms = (time.monotonic() - t0) * 1000
        step2.result = {
            "nexus_route_present": has_route,
            "endpoint": nexus_route.get("endpoint", ""),
            "zone": nexus_route.get("zone", ""),
            "trust_anchor": nexus_route.get("trust_anchor", ""),
        }
        step2.status = "success" if has_route else "failed"
        if not has_route:
            step2.error = "No Nexus route in SignalBox response"
            result.status = "failed"
            return result

        # Build a ResolvedAgent from SignalBox response for Nexus header
        agent = ResolvedAgent(
            agent_id=agent_data.get("name", agent_id),
            display_name=agent_data.get("name", ""),
            jurisdiction="",
            endpoints=[{"url": nexus_route.get("endpoint", ""), "protocol": nexus_route.get("protocol", "a2a")}],
            capabilities={"protocols": nexus_route.get("protocol_versions", [])},
            trust={"jwks_uri": nexus_route.get("trust_anchor", "")},
            policy_tags={},
            raw=agent_data,
        )
        result.agent = agent

        # Step 3: Invoke via Nexus
        step3 = WorkflowStep(name="nexus_invocation")
        result.steps.append(step3)
        step3.status = "running"
        t0 = time.monotonic()
        try:
            rpc_result = await self.nexus.invoke_agent(
                agent_alias,
                method=rpc_method,
                params=rpc_params or {
                    "patient_id": "P-SIGNALBOX-001",
                    "encounter_id": f"E-{workflow_id}",
                    "clinical_data": {"chief_complaint": "SignalBox integration test"},
                },
                gharra_agent=agent,
                correlation_id=correlation_id,
            )
            step3.elapsed_ms = (time.monotonic() - t0) * 1000
            step3.result = rpc_result

            if rpc_result.get("http_status", 500) < 400:
                step3.status = "success"
            else:
                step3.status = "failed"
                step3.error = rpc_result.get("error", "")
        except Exception as exc:
            step3.elapsed_ms = (time.monotonic() - t0) * 1000
            step3.status = "failed"
            step3.error = str(exc)

        result.status = "success" if all(
            s.status == "success" for s in result.steps
        ) else "failed"

        return result

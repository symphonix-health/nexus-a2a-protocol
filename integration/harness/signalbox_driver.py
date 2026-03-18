"""SignalBox driver for the integration harness.

Drives BulletTrain's SignalBox service to orchestrate end-to-end workflows
that flow through GHARRA resolution and Nexus routing.

Key endpoints exercised:
  POST /api/signalbox/gharra/resolve     — resolve agent via GHARRA
  POST /api/signalbox/gharra/discover    — discover agents by capability
  GET  /api/signalbox/gharra/health      — GHARRA health check
  POST /api/signalbox/identity/register  — register an orchestration agent
  POST /api/signalbox/identity/transition — transition agent persona
  POST /api/signalbox/external/orchestrate — full external orchestration
  GET  /api/signalbox/external/systems   — list external systems

These routes are defined in:
  - services/signalbox/gharra_routes.py
  - services/signalbox/external_routes.py
  - services/signalbox/identity_routes.py
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

import httpx

logger = logging.getLogger("harness.signalbox_driver")

SIGNALBOX_BASE_URL = os.getenv("SIGNALBOX_BASE_URL", "http://localhost:8221")


class SignalBoxDriver:
    """HTTP client for SignalBox orchestration endpoints."""

    def __init__(self, base_url: str | None = None, timeout: float = 15.0):
        self._base_url = (base_url or SIGNALBOX_BASE_URL).rstrip("/")
        self._timeout = timeout

    # ── Health ──────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self._base_url}/health")
            return resp.json()

    # ── GHARRA integration (via SignalBox) ─────────────────────────────

    async def gharra_health(self) -> dict[str, Any]:
        """Check GHARRA health through SignalBox proxy."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/api/signalbox/gharra/health"
            )
            return resp.json()

    async def resolve_agent(
        self,
        agent_name: str,
        *,
        evaluate_policy: bool = True,
        requires_phi_export: bool = False,
    ) -> dict[str, Any]:
        """Resolve an agent through SignalBox → GHARRA.

        This exercises the full integration path:
        SignalBox → GharraClient → GHARRA API → agent record + trust + policy.
        """
        payload = {
            "agent_name": agent_name,
            "evaluate_policy": evaluate_policy,
            "requires_phi_export": requires_phi_export,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/signalbox/gharra/resolve",
                json=payload,
            )
            if resp.status_code >= 400:
                return {
                    "status": "error",
                    "http_status": resp.status_code,
                    "detail": resp.text[:500],
                }
            return resp.json()

    async def discover_agents(
        self,
        capability: str,
        region: str | None = None,
    ) -> dict[str, Any]:
        """Discover agents by capability through SignalBox → GHARRA."""
        payload: dict[str, Any] = {"capability": capability}
        if region:
            payload["region"] = region
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/signalbox/gharra/discover",
                json=payload,
            )
            if resp.status_code >= 400:
                return {
                    "status": "error",
                    "http_status": resp.status_code,
                    "detail": resp.text[:500],
                }
            return resp.json()

    # ── Identity management ────────────────────────────────────────────

    async def register_agent(
        self,
        agent_name: str,
        description: str = "Integration test agent",
    ) -> dict[str, Any]:
        """Register an agent in SignalBox's identity FSM."""
        payload = {
            "agent_name": agent_name,
            "description": description,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/signalbox/identity/register",
                json=payload,
            )
            return resp.json()

    async def transition_agent(
        self,
        agent_id: str,
        target_persona: str,
        trigger: str = "integration_test",
        reason: str = "Integration harness workflow",
    ) -> dict[str, Any]:
        """Transition an agent to a target persona."""
        payload = {
            "agent_id": agent_id,
            "target_state": target_persona,
            "trigger": trigger,
            "reason": reason,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/signalbox/identity/transition",
                json=payload,
            )
            return resp.json()

    async def get_agent_state(self, agent_id: str) -> dict[str, Any]:
        """Get current FSM state for an agent."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/api/signalbox/identity/state",
                params={"agent_id": agent_id},
            )
            return resp.json()

    # ── External orchestration ─────────────────────────────────────────

    async def orchestrate(
        self,
        source_system: str,
        workflow: str,
        task: str,
        *,
        persona: str | None = None,
        trigger: str = "user_command",
        reason: str = "Integration test workflow",
        correlation_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Trigger a full external orchestration workflow.

        This is the highest-level integration point: SignalBox registers
        an agent, transitions persona, executes the task, and optionally
        calls an external simulator.
        """
        payload: dict[str, Any] = {
            "source_system": source_system,
            "workflow": workflow,
            "task": task,
            "trigger": trigger,
            "reason": reason,
            "correlation_id": correlation_id or str(uuid.uuid4()),
            "metadata": metadata or {},
        }
        if persona:
            payload["persona"] = persona

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/signalbox/external/orchestrate",
                json=payload,
            )
            return resp.json()

    async def list_external_systems(self) -> dict[str, Any]:
        """List available external systems."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/api/signalbox/external/systems"
            )
            return resp.json()

    # ── Governance ─────────────────────────────────────────────────────

    async def get_capabilities(self) -> dict[str, Any]:
        """Get SignalBox governance capabilities."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/api/signalbox/governance/capabilities"
            )
            return resp.json()

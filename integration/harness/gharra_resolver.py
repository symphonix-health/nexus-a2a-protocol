"""GHARRA agent resolver for the integration harness.

Queries the real GHARRA registry to:
  - discover agents by capability
  - resolve agent records by ID
  - retrieve trust metadata and policy tags
  - build Nexus route metadata

This module talks directly to the GHARRA HTTP API (port 8400) and does
NOT use the BulletTrain GharraClient — it validates GHARRA independently
before testing the full BulletTrain → GHARRA → Nexus chain.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("harness.gharra_resolver")

GHARRA_BASE_URL = os.getenv("GHARRA_BASE_URL", "http://localhost:8400")


@dataclass
class ResolvedAgent:
    """Resolved agent record from GHARRA."""

    agent_id: str
    display_name: str
    jurisdiction: str
    endpoints: list[dict[str, Any]]
    capabilities: dict[str, Any]
    trust: dict[str, Any]
    policy_tags: dict[str, Any]
    status: str = "active"
    version: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def primary_endpoint(self) -> str:
        if not self.endpoints:
            return ""
        sorted_eps = sorted(self.endpoints, key=lambda e: e.get("priority", 100))
        return sorted_eps[0].get("url", "")

    @property
    def protocol(self) -> str:
        if not self.endpoints:
            return "http-rest"
        sorted_eps = sorted(self.endpoints, key=lambda e: e.get("priority", 100))
        return sorted_eps[0].get("protocol", "http-rest")

    @property
    def zone(self) -> str:
        return f"{self.jurisdiction.lower()}.health"

    @property
    def trust_anchor(self) -> str:
        return self.trust.get("jwks_uri", "")


class GharraResolver:
    """Direct HTTP client for the GHARRA registry API."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self._base_url = (base_url or GHARRA_BASE_URL).rstrip("/")
        self._timeout = timeout

    # ── Health ──────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/health")
            return resp.json()

    # ── Agent CRUD ─────────────────────────────────────────────────────

    async def get_agent(self, agent_id: str) -> ResolvedAgent:
        """GET /v1/agents/{agent_id} — resolve a single agent record."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/v1/agents/{agent_id}")
            resp.raise_for_status()
            data = resp.json()
            return self._parse_agent(data)

    async def list_agents(
        self, jurisdiction: str | None = None, limit: int = 200
    ) -> list[ResolvedAgent]:
        """GET /v1/agents — list registered agents."""
        params: dict[str, str] = {"limit": str(limit)}
        if jurisdiction:
            params["jurisdiction"] = jurisdiction
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/v1/agents", params=params
            )
            resp.raise_for_status()
            data = resp.json()
            agents_raw = data.get("agents", [])
            return [self._parse_agent(a) for a in agents_raw]

    # ── Discovery ──────────────────────────────────────────────────────

    async def discover_by_capability(
        self,
        capability: str,
        jurisdiction: str | None = None,
        protocol: str | None = None,
    ) -> list[ResolvedAgent]:
        """GET /v1/discover?capability=... — capability-based discovery."""
        params: dict[str, str] = {"capability": capability}
        if jurisdiction:
            params["jurisdiction"] = jurisdiction
        if protocol:
            params["protocol"] = protocol
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/v1/discover", params=params
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            return [self._parse_agent(a) for a in results]

    # ── Routing advisory ───────────────────────────────────────────────

    async def get_routing_advisory(
        self, agent_id: str
    ) -> dict[str, Any]:
        """POST /v1/route — get routing advisory + trust bundle."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/v1/route",
                json={"agent_id": agent_id},
            )
            resp.raise_for_status()
            return resp.json()

    # ── Trust ──────────────────────────────────────────────────────────

    async def get_trust_bundle(self, subject_id: str) -> dict[str, Any]:
        """GET /v1/trust/bundles/{subject_id} — trust material."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/v1/trust/bundles/{subject_id}"
            )
            if resp.status_code == 404:
                return {"status": "not_found", "subject_id": subject_id}
            resp.raise_for_status()
            return resp.json()

    # ── Zones ──────────────────────────────────────────────────────────

    async def list_zones(self) -> list[dict[str, Any]]:
        """GET /v1/zones — namespace zones."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/v1/zones")
            resp.raise_for_status()
            data = resp.json()
            return data.get("zones", data) if isinstance(data, dict) else data

    # ── Observability helper ──────────────────────────────────────────

    def log_resolution(
        self, agent: ResolvedAgent, *, workflow_id: str = "", correlation_id: str = ""
    ) -> dict[str, Any]:
        """Build structured observability record for a resolved agent."""
        record = {
            "agent_name": agent.display_name,
            "agent_id": agent.agent_id,
            "resolved_zone": agent.zone,
            "trust_anchor": agent.trust_anchor,
            "selected_capability": list(agent.capabilities.get("protocols", [])),
            "nexus_route": agent.primary_endpoint,
            "workflow_id": workflow_id,
            "correlation_id": correlation_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        logger.info(
            "Resolved agent=%s zone=%s endpoint=%s",
            agent.agent_id,
            agent.zone,
            agent.primary_endpoint,
        )
        return record

    # ── Internal ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_agent(data: dict[str, Any]) -> ResolvedAgent:
        return ResolvedAgent(
            agent_id=data.get("agent_id", ""),
            display_name=data.get("display_name", ""),
            jurisdiction=data.get("jurisdiction", ""),
            endpoints=data.get("endpoints", []),
            capabilities=data.get("capabilities", {}),
            trust=data.get("trust", {}),
            policy_tags=data.get("policy_tags", {}),
            status=data.get("status", "active"),
            version=data.get("version", ""),
            raw=data,
        )

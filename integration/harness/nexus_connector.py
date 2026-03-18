"""Nexus-A2A connector for the integration harness.

Sends JSON-RPC 2.0 requests to the Nexus on-demand gateway, optionally
attaching GHARRA metadata via the X-Gharra-Record header so that Nexus
can enforce route admission.

This module reuses the same protocol and header conventions already
implemented in the Nexus repository:
  - ``shared/nexus_common/route_admission.py``
  - ``shared/nexus_common/gharra_models.py``
  - ``shared/on_demand_gateway/app/main.py``
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import httpx
import jwt

from .gharra_resolver import ResolvedAgent

logger = logging.getLogger("harness.nexus_connector")

NEXUS_GATEWAY_URL = os.getenv("NEXUS_GATEWAY_URL", "http://localhost:8100")
NEXUS_JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "integration-test-secret")


def _mint_jwt(
    subject: str = "integration-harness",
    scope: str = "nexus:invoke",
    secret: str | None = None,
) -> str:
    """Mint an HS256 JWT for Nexus authentication."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + 3600,
        "scope": scope,
    }
    return jwt.encode(payload, secret or NEXUS_JWT_SECRET, algorithm="HS256")


def _build_gharra_header(agent: ResolvedAgent) -> str:
    """Build the X-Gharra-Record header value from a resolved agent."""
    record = {
        "agent_name": agent.agent_id,
        "name": agent.display_name,
        "zone": agent.zone,
        "trust_anchor": agent.trust_anchor,
        "status": agent.status,
        "jurisdiction": agent.jurisdiction,
        "capabilities": list(agent.capabilities.get("protocols", [])),
        "policy_tags": list(agent.policy_tags.keys()) if isinstance(agent.policy_tags, dict) else [],
        "transport": {
            "endpoint": agent.primary_endpoint,
            "protocol": "nexus-a2a",
            "protocol_versions": ["1.0"],
            "feature_flags": [],
        },
        "authentication": {
            "mtls_required": agent.trust.get("mtls_required", False),
            "jwks_uri": agent.trust.get("jwks_uri", ""),
            "cert_bound_tokens_required": False,
            "thumbprint_policy": "",
        },
    }
    return json.dumps(record)


class NexusConnector:
    """JSON-RPC 2.0 client for the Nexus on-demand gateway."""

    def __init__(
        self,
        gateway_url: str | None = None,
        jwt_secret: str | None = None,
        timeout: float = 45.0,
    ):
        self._gateway_url = (gateway_url or NEXUS_GATEWAY_URL).rstrip("/")
        self._jwt_secret = jwt_secret or NEXUS_JWT_SECRET
        self._timeout = timeout

    # ── Health ──────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self._gateway_url}/health")
            return resp.json()

    # ── JSON-RPC invocation ────────────────────────────────────────────

    async def invoke_agent(
        self,
        agent_alias: str,
        *,
        method: str = "tasks/send",
        params: dict[str, Any] | None = None,
        gharra_agent: ResolvedAgent | None = None,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request to an agent via the Nexus gateway.

        Args:
            agent_alias: The agent alias (e.g. "triage", "diagnosis").
            method: JSON-RPC method name.
            params: JSON-RPC params object.
            gharra_agent: Optional GHARRA-resolved agent for X-Gharra-Record.
            correlation_id: Distributed tracing correlation ID.

        Returns:
            Full JSON-RPC response dict.
        """
        correlation_id = correlation_id or str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": request_id,
        }

        token = _mint_jwt(secret=self._jwt_secret)
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Correlation-ID": correlation_id,
        }

        if gharra_agent:
            headers["X-Gharra-Record"] = _build_gharra_header(gharra_agent)
            headers["X-Session-ID"] = correlation_id

        url = f"{self._gateway_url}/rpc/{agent_alias}"
        start = time.monotonic()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)

        elapsed_ms = (time.monotonic() - start) * 1000

        logger.info(
            "Nexus RPC: agent=%s method=%s status=%d elapsed=%.1fms correlation=%s",
            agent_alias,
            method,
            resp.status_code,
            elapsed_ms,
            correlation_id,
        )

        result: dict[str, Any] = {
            "http_status": resp.status_code,
            "elapsed_ms": round(elapsed_ms, 2),
            "correlation_id": correlation_id,
            "request_id": request_id,
            "agent_alias": agent_alias,
        }

        if resp.status_code < 400:
            try:
                result["response"] = resp.json()
            except Exception:
                result["response"] = {"raw": resp.text[:500]}
        else:
            result["error"] = resp.text[:500]

        return result

    # ── Agent card discovery ───────────────────────────────────────────

    async def get_agent_card(self, agent_alias: str) -> dict[str, Any]:
        """Fetch /.well-known/agent-card.json for a running agent."""
        # The on-demand gateway proxies to the agent's port
        # For direct agent access we'd need the port; through gateway we use /rpc
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._gateway_url}/api/agents"
            )
            if resp.status_code < 400:
                return resp.json()
            return {"status": "unavailable", "http_status": resp.status_code}

    # ── Observability ──────────────────────────────────────────────────

    def log_invocation(
        self,
        result: dict[str, Any],
        *,
        agent: ResolvedAgent | None = None,
        workflow_id: str = "",
    ) -> dict[str, Any]:
        """Build observability record for a Nexus invocation."""
        record = {
            "agent_name": agent.display_name if agent else result.get("agent_alias", ""),
            "resolved_zone": agent.zone if agent else "",
            "trust_anchor": agent.trust_anchor if agent else "",
            "selected_capability": list(agent.capabilities.get("protocols", [])) if agent else [],
            "nexus_route": f"{self._gateway_url}/rpc/{result.get('agent_alias', '')}",
            "workflow_id": workflow_id,
            "correlation_id": result.get("correlation_id", ""),
            "http_status": result.get("http_status", 0),
            "elapsed_ms": result.get("elapsed_ms", 0),
        }
        return record

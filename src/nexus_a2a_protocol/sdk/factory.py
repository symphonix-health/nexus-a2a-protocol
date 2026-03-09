"""Environment-driven transport factory for simulation and Nexus runtimes."""

from __future__ import annotations

import os

from .auth import resolve_jwt_token
from .http_sse_transport import HttpSseTransport
from .simulation_transport import SimulationTransport
from .transport import AgentTransport
from .types import TransportError
from .websocket_transport import WebSocketTransport


class TransportFactory:
    """Factory for constructing SDK transport implementations from env."""

    @staticmethod
    def from_env(mode: str | None = None) -> AgentTransport:
        selected = (mode or os.getenv("AGENT_TRANSPORT", "simulation")).strip().lower()

        if selected == "simulation":
            return SimulationTransport(
                agent_id=os.getenv("NEXUS_SIM_AGENT_ID", "simulation-agent"),
            )

        token = resolve_jwt_token()

        if selected == "http_sse":
            base_url = os.getenv("NEXUS_ROUTER_URL", "http://localhost:9000").strip().rstrip("/")
            return HttpSseTransport(
                base_url=base_url,
                token=token,
                timeout=float(os.getenv("NEXUS_TRANSPORT_TIMEOUT_SECONDS", "30")),
                agent_id=os.getenv("NEXUS_AGENT_ID", "nexus-agent"),
            )

        if selected == "websocket":
            rpc_url = os.getenv("NEXUS_ROUTER_RPC_URL", "http://localhost:9000/rpc").strip()
            ws_template = os.getenv(
                "NEXUS_WS_URL_TEMPLATE",
                "ws://localhost:9000/ws/{task_id}?token={token}",
            ).strip()
            return WebSocketTransport(
                rpc_url=rpc_url,
                ws_url_template=ws_template,
                token=token,
                timeout=float(os.getenv("NEXUS_TRANSPORT_TIMEOUT_SECONDS", "30")),
                agent_id=os.getenv("NEXUS_AGENT_ID", "nexus-agent"),
            )

        raise TransportError(
            f"Unsupported transport mode '{selected}'. Expected one of: simulation, http_sse, websocket"
        )

"""Async HTTP JSON-RPC client for inter-agent communication."""

from __future__ import annotations

from typing import Any

import httpx

from .protocol import CorrelationContext, IdempotencyContext, ScenarioContext


async def jsonrpc_call(
    url: str,
    token: str,
    method: str,
    params: dict[str, Any],
    id_: str,
    timeout: float = 30.0,
    scenario_context: ScenarioContext | dict[str, Any] | None = None,
    correlation: CorrelationContext | dict[str, Any] | None = None,
    idempotency: IdempotencyContext | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an async JSON-RPC 2.0 call to another NEXUS agent."""
    request_params: dict[str, Any] = dict(params)

    if scenario_context is not None:
        request_params["scenario_context"] = (
            scenario_context.to_dict()
            if hasattr(scenario_context, "to_dict")
            else dict(scenario_context)
        )
    if correlation is not None:
        request_params["correlation"] = (
            correlation.to_dict() if hasattr(correlation, "to_dict") else dict(correlation)
        )
    if idempotency is not None:
        request_params["idempotency"] = (
            idempotency.to_dict() if hasattr(idempotency, "to_dict") else dict(idempotency)
        )

    payload = {"jsonrpc": "2.0", "id": id_, "method": method, "params": request_params}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    trace_id = request_params.get("correlation", {}).get("trace_id")
    if trace_id:
        headers["X-Nexus-Trace-Id"] = str(trace_id)

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()

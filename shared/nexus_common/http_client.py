"""Async HTTP JSON-RPC client for inter-agent communication.

Uses shared AsyncClient instances keyed by runtime transport settings to avoid
per-request socket churn at higher concurrency.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import httpx

from .a2a_http import build_outbound_headers
from .otel import start_span
from .protocol import CorrelationContext, IdempotencyContext, ScenarioContext
from .trace_context import inject_trace_context

ClientKey = tuple[float, int, int, float, bool]
_clients_lock = threading.Lock()
_clients: dict[ClientKey, httpx.AsyncClient] = {}


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except Exception:
        return default


def _client_key(timeout: float) -> ClientKey:
    max_connections = _env_int("NEXUS_HTTP_MAX_CONNECTIONS", 2048)
    max_keepalive = _env_int("NEXUS_HTTP_MAX_KEEPALIVE", 1024)
    keepalive_expiry = _env_float("NEXUS_HTTP_KEEPALIVE_EXPIRY_SECONDS", 30.0)
    http2_enabled = os.getenv("NEXUS_HTTP2", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return (timeout, max_connections, max_keepalive, keepalive_expiry, http2_enabled)


def _get_client(timeout: float) -> httpx.AsyncClient:
    key = _client_key(timeout)
    with _clients_lock:
        existing = _clients.get(key)
        if existing is not None:
            return existing
        limits = httpx.Limits(
            max_connections=key[1],
            max_keepalive_connections=key[2],
            keepalive_expiry=key[3],
        )
        client = httpx.AsyncClient(timeout=timeout, limits=limits, http2=key[4])
        _clients[key] = client
        return client


async def close_http_clients() -> None:
    """Close all shared AsyncClient instances.

    Useful for graceful shutdown hooks in long-running processes.
    """
    with _clients_lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        try:
            await client.aclose()
        except Exception:
            pass


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
    correlation_payload: dict[str, Any] | None = None

    if scenario_context is not None:
        request_params["scenario_context"] = (
            scenario_context.to_dict()
            if hasattr(scenario_context, "to_dict")
            else dict(scenario_context)
        )
    if correlation is not None:
        correlation_payload = (
            correlation.to_dict() if hasattr(correlation, "to_dict") else dict(correlation)
        )
        request_params["correlation"] = correlation_payload
    if idempotency is not None:
        request_params["idempotency"] = (
            idempotency.to_dict() if hasattr(idempotency, "to_dict") else dict(idempotency)
        )

    payload = {"jsonrpc": "2.0", "id": id_, "method": method, "params": request_params}
    trace_id = None
    traceparent = None
    tracestate = None
    if isinstance(correlation_payload, dict):
        trace_id = str(correlation_payload.get("trace_id") or "").strip() or None
        traceparent = str(correlation_payload.get("traceparent") or "").strip() or None
        tracestate = str(correlation_payload.get("tracestate") or "").strip() or None

    headers = build_outbound_headers(
        token=token,
        traceparent=traceparent,
        tracestate=tracestate,
    )
    if not traceparent:
        inject_trace_context(
            headers,
            trace_id=trace_id,
            tracestate=tracestate,
        )
    if trace_id:
        headers["X-Nexus-Trace-Id"] = str(trace_id)

    client = _get_client(timeout)
    with start_span(
        "nexus.http.jsonrpc_call",
        {
            "jsonrpc.method": method,
            "server.address": url,
        },
    ):
        r = await client.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

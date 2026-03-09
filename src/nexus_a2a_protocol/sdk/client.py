"""HTTP helpers for SDK transports and compatibility shims."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from .streaming import parse_sse_chunk
from .types import TaskEvent, TransportError



def _auth_headers(token: str | None = None, *, accept_sse: bool = False) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if accept_sse:
        headers["Accept"] = "text/event-stream"
    return headers



def _extract_rpc_error(payload: dict[str, Any]) -> tuple[int | None, str, Any | None]:
    error = payload.get("error")
    if not isinstance(error, dict):
        return None, "", None
    code = error.get("code") if isinstance(error.get("code"), int) else None
    message = str(error.get("message") or "RPC error")
    data = error.get("data")
    return code, message, data


async def fetch_agent_card(
    base_url: str,
    token: str | None,
    *,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    created = client is None
    if created:
        client = httpx.AsyncClient(timeout=timeout)
    assert client is not None
    try:
        resp = await client.get(url, headers=_auth_headers(token))
        resp.raise_for_status()
        return resp.json()
    finally:
        if created:
            await client.aclose()


async def probe_agent_health(
    base_url: str,
    token: str | None,
    *,
    timeout: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/health"
    created = client is None
    if created:
        client = httpx.AsyncClient(timeout=timeout)
    assert client is not None
    try:
        resp = await client.get(url, headers=_auth_headers(token))
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "unreachable", "error": str(exc)}
    finally:
        if created:
            await client.aclose()


async def nexus_rpc_call(
    base_url: str,
    method: str,
    params: dict[str, Any],
    token: str | None,
    *,
    request_id: str,
    timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    rpc_url = f"{base_url.rstrip('/')}/rpc"
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }
    created = client is None
    if created:
        client = httpx.AsyncClient(timeout=timeout)
    assert client is not None

    try:
        resp = await client.post(rpc_url, json=payload, headers=_auth_headers(token))
        data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
        if resp.status_code >= 400:
            code, message, details = _extract_rpc_error(data if isinstance(data, dict) else {})
            raise TransportError(
                message or f"HTTP {resp.status_code}",
                code=code,
                http_status=resp.status_code,
                details=details or data,
            )
        if isinstance(data, dict) and "error" in data:
            code, message, details = _extract_rpc_error(data)
            raise TransportError(message or "RPC error", code=code, details=details)
        if not isinstance(data, dict):
            raise TransportError("RPC response must be a JSON object", http_status=resp.status_code)
        return data
    finally:
        if created:
            await client.aclose()


async def consume_sse_stream(
    base_url: str,
    task_id: str,
    token: str | None,
    *,
    timeout: float = 120.0,
    client: httpx.AsyncClient | None = None,
    agent_id: str = "unknown-agent",
) -> AsyncIterator[TaskEvent]:
    url = f"{base_url.rstrip('/')}/events/{task_id}"
    created = client is None
    if created:
        client = httpx.AsyncClient(timeout=timeout)
    assert client is not None

    try:
        async with client.stream("GET", url, headers=_auth_headers(token, accept_sse=True)) as resp:
            if resp.status_code >= 400:
                raise TransportError(
                    f"SSE stream failed with HTTP {resp.status_code}",
                    http_status=resp.status_code,
                )
            buffer = ""
            async for text in resp.aiter_text():
                buffer += text
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    evt = parse_sse_chunk(frame, task_id=task_id, agent_id=agent_id)
                    if evt is None:
                        continue
                    yield evt
                    if evt.is_terminal:
                        return
    finally:
        if created:
            await client.aclose()

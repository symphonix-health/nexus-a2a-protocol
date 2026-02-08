"""Async HTTP JSON-RPC client for inter-agent communication."""

from __future__ import annotations

from typing import Any, Dict

import httpx


async def jsonrpc_call(
    url: str,
    token: str,
    method: str,
    params: Dict[str, Any],
    id_: str,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Make an async JSON-RPC 2.0 call to another NEXUS agent."""
    payload = {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()

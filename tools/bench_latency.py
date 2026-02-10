#!/usr/bin/env python3
"""Simple latency benchmark tool for NEXUS agents.

Measures GET /health and optional JSON-RPC calls across a list of agent URLs.
Writes JSON summary to bench_latency.json.

Usage:
  python tools/bench_latency.py --urls http://localhost:8021,http://localhost:8022 --rpc tasks/send
  # Or rely on AGENT_URLS env (comma-separated)

Notes:
- /health latency is a good baseline across all agents.
- For /rpc, the method is attempted with an empty params dict; failures are skipped.
- Authorization: Uses NEXUS_JWT_SECRET to mint HS256 tokens unless AUTH_MODE=rs256
  in which case you must provide a valid Bearer token via --token.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
from typing import List, Dict, Any

import httpx

from shared.nexus_common.auth import mint_jwt


def _split_urls(s: str) -> List[str]:
    return [u.strip() for u in s.split(",") if u.strip()]


def _hdrs(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _time_get(client: httpx.AsyncClient, url: str, token: str | None) -> float:
    import time
    t0 = time.perf_counter()
    r = await client.get(f"{url}/health", headers=_hdrs(token))
    r.raise_for_status()
    return (time.perf_counter() - t0) * 1000.0


async def _time_rpc(client: httpx.AsyncClient, url: str, token: str | None, method: str) -> float | None:
    import time
    payload = {"jsonrpc": "2.0", "id": "bench", "method": method, "params": {}}
    t0 = time.perf_counter()
    r = await client.post(f"{url}/rpc", headers=_hdrs(token), content=json.dumps(payload))
    # Accept 200 with result or JSON-RPC error; skip if HTTP error
    if r.status_code != 200:
        return None
    return (time.perf_counter() - t0) * 1000.0


def _summarize(samples: List[float]) -> Dict[str, Any]:
    if not samples:
        return {"count": 0}
    return {
        "count": len(samples),
        "min_ms": round(min(samples), 2),
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(statistics.quantiles(samples, n=100)[94], 2) if len(samples) >= 20 else None,
        "max_ms": round(max(samples), 2),
        "avg_ms": round(sum(samples) / len(samples), 2),
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", help="Comma-separated agent base URLs", default=os.getenv("AGENT_URLS", ""))
    ap.add_argument("--rpc", help="Optional JSON-RPC method to test", default=None)
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--token", help="Bearer token to use (required when AUTH_MODE=rs256)")
    args = ap.parse_args()

    urls = _split_urls(args.urls) if args.urls else []
    if not urls:
        print("No URLs provided. Use --urls or set AGENT_URLS env.")
        return 2

    token = args.token
    auth_mode = os.getenv("AUTH_MODE", "hs256").lower()
    if not token and auth_mode != "rs256":
        secret = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
        token = mint_jwt("bench-client", secret)

    results: Dict[str, Any] = {"auth_mode": auth_mode, "agents": {}}

    async with httpx.AsyncClient(timeout=15.0) as client:
        for base in urls:
            # health
            health_samples: List[float] = []
            sem = asyncio.Semaphore(args.concurrency)

            async def run_health():
                async with sem:
                    try:
                        ms = await _time_get(client, base, token)
                        health_samples.append(ms)
                    except Exception:
                        pass

            await asyncio.gather(*[run_health() for _ in range(args.runs)])

            # rpc
            rpc_samples: List[float] = []
            if args.rpc:
                async def run_rpc():
                    async with sem:
                        try:
                            ms = await _time_rpc(client, base, token, args.rpc)
                            if ms is not None:
                                rpc_samples.append(ms)
                        except Exception:
                            pass
                await asyncio.gather(*[run_rpc() for _ in range(args.runs)])

            results["agents"][base] = {
                "health": _summarize(health_samples),
                "rpc": _summarize(rpc_samples) if args.rpc else None,
            }

    with open("bench_latency.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print("Latency benchmark written to bench_latency.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

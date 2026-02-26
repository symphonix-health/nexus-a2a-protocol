"""Command Centre — Real-time monitoring dashboard for NEXUS-A2A agent networks.

Provides:
- Agent discovery and health polling
- Real-time event streaming via WebSocket
- Metrics aggregation with heatmap data
- Topology visualization support
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.command-centre")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI(title="command-centre", description="NEXUS-A2A Agent Monitoring Dashboard")

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
UPDATE_INTERVAL_MS = int(os.getenv("UPDATE_INTERVAL_MS", "5000"))
# Cap concurrent agent health checks (avoid spawning N HTTP requests simultaneously)
POLL_CONCURRENCY = int(os.getenv("CC_POLL_CONCURRENCY", "6"))
# Re-fetch the (mostly static) agent card at most once per this many seconds
CARD_CACHE_TTL_S = float(os.getenv("CC_CARD_CACHE_TTL_S", "60.0"))
# Max simultaneous WebSocket dashboard clients
WS_MAX_CLIENTS = int(os.getenv("CC_WS_MAX_CLIENTS", "20"))
# Per-agent health/card request timeout
AGENT_FETCH_TIMEOUT = float(os.getenv("CC_AGENT_FETCH_TIMEOUT", "5.0"))

# In-memory agent state
agent_states: dict[str, dict[str, Any]] = {}
# Card data cached separately so it can be excluded from high-frequency WS broadcasts
_card_cache: dict[str, tuple[float, dict[str, Any]]] = {}
scenario_catalog: list[dict[str, Any]] = []
lock = asyncio.Lock()
poll_task_started = False
first_poll_cycle_completed = False

# ── Trace Store ───────────────────────────────────────────────────────
TRACE_STORE_MAX = 200
trace_store: OrderedDict[str, dict[str, Any]] = OrderedDict()
trace_lock = asyncio.Lock()
TRACE_STORE_FILE = Path(
    os.getenv(
        "COMMAND_CENTRE_TRACE_STORE_FILE",
        str(Path(__file__).resolve().parents[3] / "temp" / "command_centre_trace_store.json"),
    )
)

# ── WebSocket Client Registry ────────────────────────────────────────
ws_clients: set[WebSocket] = set()


def _slim_agent_snapshot() -> list[dict[str, Any]]:
    """Compact agent snapshot — excludes large card payload for WS broadcasts."""
    return [
        {
            "name": s.get("name", ""),
            "url": s.get("url", ""),
            "status": s.get("status", "unknown"),
            "health_score": s.get("health_score", 0.5),
            "metrics": s.get("metrics", {}),
            "last_seen": s.get("last_seen", ""),
        }
        for s in agent_states.values()
    ]


class DevNoCacheStaticFiles(StaticFiles):
    """Static file handler that disables browser caching for rapid UI iteration."""

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


def _load_agent_urls_from_config() -> list[str]:
    """Load agent URLs from repo config/agents.json as a local-dev fallback."""
    try:
        repo_root = Path(__file__).resolve().parents[3]
        config_path = repo_root / "config" / "agents.json"
        if not config_path.is_file():
            return []

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        agents_by_group = raw.get("agents", {})
        if not isinstance(agents_by_group, dict):
            return []

        urls: list[str] = []
        for _, group in agents_by_group.items():
            if not isinstance(group, dict):
                continue

            for _, agent_info in group.items():
                if not isinstance(agent_info, dict):
                    continue

                port = agent_info.get("port")
                if isinstance(port, int) and port > 0:
                    urls.append(f"http://localhost:{port}")

        # Preserve order while removing duplicates
        return list(dict.fromkeys(urls))
    except Exception as exc:
        logger.warning(f"Failed to load agent URLs from config/agents.json: {exc}")
        return []


def _resolve_agent_urls() -> list[str]:
    """Resolve monitored agent URLs from env first, then config fallback."""
    env_urls = [url.strip() for url in os.getenv("AGENT_URLS", "").split(",") if url.strip()]
    if env_urls:
        logger.info("Using AGENT_URLS from environment")
        return env_urls

    config_urls = _load_agent_urls_from_config()
    if config_urls:
        logger.info("AGENT_URLS not set; using URLs from config/agents.json")
        return config_urls

    logger.warning("No agent URLs configured (AGENT_URLS empty and config fallback unavailable)")
    return []


AGENT_URLS = _resolve_agent_urls()


def _load_scenario_catalog() -> list[dict[str, Any]]:
    """Load HelixCare scenario catalog for UI-friendly journey labels."""
    try:
        repo_root = Path(__file__).resolve().parents[3]
        catalog_path = repo_root / "tools" / "helixcare_all_scenarios.json"
        if not catalog_path.is_file():
            return []

        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog: list[dict[str, Any]] = []

        for item in raw:
            name = str(item.get("name", "")).strip()
            if not name:
                continue

            display_name = name.replace("_", " ").title()
            agents = [
                str(step.get("agent", "")).strip()
                for step in item.get("journey_steps", [])
                if isinstance(step, dict) and step.get("agent")
            ]

            task_id_prefixes = [
                name.lower(),
                name.lower().replace("_", "-"),
            ]

            catalog.append(
                {
                    "name": name,
                    "display_name": display_name,
                    "description": item.get("description", ""),
                    "agents": sorted(set(agents)),
                    "task_id_prefixes": task_id_prefixes,
                }
            )

        return catalog
    except Exception as exc:
        logger.warning(f"Failed to load scenario catalog: {exc}")
        return []


def _restore_trace_store_from_disk() -> int:
    """Restore persisted trace runs from disk into in-memory trace store."""
    try:
        if not TRACE_STORE_FILE.is_file():
            return 0

        raw = json.loads(TRACE_STORE_FILE.read_text(encoding="utf-8"))
        items = raw.get("traces", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return 0

        restored: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for item in items:
            if not isinstance(item, dict):
                continue
            trace_id = str(item.get("trace_id", "")).strip()
            if not trace_id:
                continue
            restored[trace_id] = item

        while len(restored) > TRACE_STORE_MAX:
            restored.popitem(last=False)

        trace_store.clear()
        trace_store.update(restored)
        return len(trace_store)
    except Exception as exc:
        logger.warning(f"Failed to restore trace store from {TRACE_STORE_FILE}: {exc}")
        return 0


def _persist_trace_store_to_disk() -> None:
    """Persist in-memory trace store to disk for restart resilience."""
    try:
        TRACE_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "traces": list(trace_store.values()),
        }

        temp_path = TRACE_STORE_FILE.with_suffix(TRACE_STORE_FILE.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(TRACE_STORE_FILE)
    except Exception as exc:
        logger.warning(f"Failed to persist trace store to {TRACE_STORE_FILE}: {exc}")


# ── Agent Discovery & Health Polling ──────────────────────────────────
async def _fetch_card_cached(url: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Return cached agent card, refreshing only after CARD_CACHE_TTL_S seconds."""
    now = asyncio.get_event_loop().time()
    cached_at, cached_card = _card_cache.get(url, (0.0, {}))
    if now - cached_at < CARD_CACHE_TTL_S:
        return cached_card or None
    try:
        resp = await client.get(
            f"{url}/.well-known/agent-card.json", timeout=AGENT_FETCH_TIMEOUT
        )
        if resp.status_code == 200:
            card = resp.json()
            _card_cache[url] = (now, card)
            return card
        _card_cache[url] = (now, {})
    except Exception as exc:
        logger.debug(f"Failed to fetch agent card from {url}: {exc}")
        _card_cache[url] = (now, {})
    return None


async def fetch_agent_card(url: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch agent card from discovery endpoint (bypasses cache — for direct callers)."""
    try:
        resp = await client.get(
            f"{url}/.well-known/agent-card.json", timeout=AGENT_FETCH_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.debug(f"Failed to fetch agent card from {url}: {exc}")
    return None


async def fetch_agent_health(url: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch agent health status."""
    try:
        resp = await client.get(f"{url}/health", timeout=AGENT_FETCH_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.debug(f"Health check failed for {url}: {exc}")
    return None


async def _poll_one_agent(
    url: str,
    client: httpx.AsyncClient,
    timestamp: str,
    sem: asyncio.Semaphore,
) -> None:
    """Poll a single agent under the concurrency semaphore, update agent_states."""
    async with sem:
        card = await _fetch_card_cached(url, client)
        health = await fetch_agent_health(url, client)

    async with lock:
        if card or health:
            agent_name = (health or {}).get("name") or (card or {}).get("name") or url
            status = "unknown"
            health_score = 0.5
            metrics = {}

            if health:
                status = health.get("status", "unknown")
                metrics = health.get("metrics", {})
                error_rate = 0.0
                total = metrics.get("tasks_completed", 0) + metrics.get("tasks_errored", 0)
                if total > 0:
                    error_rate = metrics.get("tasks_errored", 0) / total
                latency_factor = max(0, 1 - metrics.get("avg_latency_ms", 0) / 10000)
                health_score = latency_factor * 0.5 + (1 - error_rate) * 0.5

            agent_states[url] = {
                "name": agent_name,
                "url": url,
                "status": status,
                "health_score": round(health_score, 3),
                "metrics": metrics,
                "last_seen": timestamp,
            }
        else:
            if url in agent_states:
                agent_states[url]["status"] = "unhealthy"
                agent_states[url]["last_seen"] = timestamp


async def poll_agents():
    """Background task — polls all agents concurrently and broadcasts to WS clients."""
    global first_poll_cycle_completed
    sem = asyncio.Semaphore(POLL_CONCURRENCY)
    limits = httpx.Limits(
        max_keepalive_connections=POLL_CONCURRENCY,
        max_connections=POLL_CONCURRENCY + 4,
        keepalive_expiry=30.0,
    )
    async with httpx.AsyncClient(limits=limits) as client:
        while True:
            try:
                timestamp = datetime.now(timezone.utc).isoformat()
                # Poll all agents concurrently — no sequential blocking
                await asyncio.gather(
                    *[_poll_one_agent(url, client, timestamp, sem) for url in AGENT_URLS],
                    return_exceptions=True,
                )
                first_poll_cycle_completed = True
                # Broadcast slim snapshot to all connected WS clients (once per cycle)
                async with lock:
                    snapshot = _slim_agent_snapshot()
                await _broadcast_ws(
                    {
                        "type": "agents.snapshot",
                        "payload": snapshot,
                        "timestamp": timestamp,
                    }
                )
                await asyncio.sleep(UPDATE_INTERVAL_MS / 1000)
            except Exception as exc:
                logger.error(f"Error in poll_agents: {exc}")
                await asyncio.sleep(5.0)


@app.on_event("startup")
async def startup_event():
    """Start background polling on startup."""
    global poll_task_started, scenario_catalog
    scenario_catalog = _load_scenario_catalog()
    restored = _restore_trace_store_from_disk()
    asyncio.create_task(poll_agents())
    poll_task_started = True
    if restored:
        logger.info(f"Restored {restored} trace runs from {TRACE_STORE_FILE}")
    logger.info(f"Command Centre started. Monitoring {len(AGENT_URLS)} agents.")


# ── API Endpoints ─────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "name": "command-centre",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "monitored_agents": len(AGENT_URLS),
        "ready": poll_task_started and (first_poll_cycle_completed or not AGENT_URLS),
    }


@app.get("/readyz")
async def readyz():
    """Readiness endpoint used by strict launcher health checks."""
    ready = poll_task_started and (first_poll_cycle_completed or not AGENT_URLS)
    payload = {
        "status": "ready" if ready else "starting",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "poll_task_started": poll_task_started,
        "first_poll_cycle_completed": first_poll_cycle_completed,
        "monitored_agents": len(AGENT_URLS),
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.get("/api/agents")
async def get_agents():
    """Get current state of all monitored agents (slim payload — no card data)."""
    async with lock:
        return JSONResponse(content=_slim_agent_snapshot())


@app.get("/api/agents/{agent_url:path}")
async def get_agent_detail(agent_url: str):
    """Get full agent state including cached card data for a specific agent URL."""
    async with lock:
        state = agent_states.get(agent_url)
    if state is None:
        return JSONResponse(status_code=404, content={"error": "agent not found"})
    _, card = _card_cache.get(agent_url, (0.0, {}))
    return JSONResponse(content={**state, "card": card})


@app.get("/api/topology")
async def get_topology():
    """Get network topology graph data."""
    async with lock:
        nodes = []
        edges = []

        for url, state in agent_states.items():
            nodes.append(
                {
                    "id": state["name"],
                    "url": url,
                    "status": state["status"],
                    "health_score": state["health_score"],
                    "metrics": state["metrics"],
                }
            )

            # Build edges from dependencies (placeholder)
            for dep in state.get("dependencies", []):
                edges.append(
                    {
                        "source": state["name"],
                        "target": dep,
                    }
                )

        return JSONResponse(content={"nodes": nodes, "edges": edges})


@app.get("/api/scenario-catalog")
async def get_scenario_catalog():
    """Return scenario catalog metadata for dashboard journey labels."""
    return JSONResponse(content=scenario_catalog)


# ── Trace API ─────────────────────────────────────────────────────────
async def _broadcast_ws(message: dict[str, Any]) -> None:
    """Best-effort broadcast a JSON message to all connected WebSocket clients."""
    stale: list[WebSocket] = []
    for ws in ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        ws_clients.discard(ws)


@app.post("/api/traces", status_code=201)
async def ingest_trace(request: Request):
    """Accept a completed TraceRun JSON from the scenario runner."""
    body = await request.json()
    trace_id = body.get("trace_id", "")
    if not trace_id:
        return JSONResponse(status_code=400, content={"error": "trace_id required"})

    async with trace_lock:
        trace_store[trace_id] = body
        # Evict oldest when over capacity
        while len(trace_store) > TRACE_STORE_MAX:
            trace_store.popitem(last=False)
        _persist_trace_store_to_disk()

    # Broadcast to all WS clients
    await _broadcast_ws(
        {
            "type": "trace.run",
            "payload": {
                "trace_id": trace_id,
                "scenario_name": body.get("scenario_name", ""),
                "status": body.get("status", ""),
                "step_count": body.get("step_count", 0),
                "total_duration_ms": body.get("total_duration_ms", 0),
                "started_at": body.get("started_at", ""),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    return JSONResponse(
        status_code=201,
        content={"trace_id": trace_id, "stored": True},
    )


@app.get("/api/traces")
async def list_traces():
    """List stored trace run summaries (newest first)."""
    async with trace_lock:
        summaries = []
        for tid in reversed(trace_store):
            run = trace_store[tid]
            summaries.append(
                {
                    "trace_id": tid,
                    "scenario_name": run.get("scenario_name", ""),
                    "status": run.get("status", ""),
                    "started_at": run.get("started_at", ""),
                    "step_count": run.get("step_count", 0),
                    "total_duration_ms": run.get("total_duration_ms", 0),
                    "visit_id": run.get("visit_id", ""),
                    "patient_id": run.get("patient_id", ""),
                    "patient_profile": run.get("patient_profile", {}),
                }
            )
        return JSONResponse(content=summaries)


@app.delete("/api/traces")
async def reset_traces():
    """Clear all stored trace runs (in-memory + persisted file)."""
    async with trace_lock:
        cleared_count = len(trace_store)
        trace_store.clear()
        _persist_trace_store_to_disk()

    await _broadcast_ws(
        {
            "type": "trace.reset",
            "payload": {"cleared_count": cleared_count},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    return JSONResponse(content={"cleared": True, "cleared_count": cleared_count})


@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Return full trace run with all steps."""
    async with trace_lock:
        run = trace_store.get(trace_id)
    if run is None:
        return JSONResponse(status_code=404, content={"error": "trace not found"})
    return JSONResponse(content=run)


@app.get("/api/traces/{trace_id}/export")
async def export_trace(trace_id: str):
    """Download trace run as a JSON file attachment."""
    async with trace_lock:
        run = trace_store.get(trace_id)
    if run is None:
        return JSONResponse(status_code=404, content={"error": "trace not found"})
    content = json.dumps(run, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="trace-{trace_id}.json"'},
    )


# ── WebSocket Event Streaming ─────────────────────────────────────────
@app.websocket("/api/events")
async def websocket_events(websocket: WebSocket):
    """Stream real-time agent events to dashboard clients.

    Periodic agent snapshots are pushed by poll_agents() — one broadcast
    per poll cycle regardless of client count.  This handler just keeps
    the socket alive and forwards Redis events when Redis is available.
    """
    if len(ws_clients) >= WS_MAX_CLIENTS:
        await websocket.close(code=1013)  # 1013 = Try Again Later
        logger.warning(f"WS client rejected — limit {WS_MAX_CLIENTS} reached")
        return

    await websocket.accept()
    ws_clients.add(websocket)
    logger.info(f"WebSocket client connected ({len(ws_clients)}/{WS_MAX_CLIENTS})")

    redis_client = None
    pubsub = None
    try:
        # Send immediate snapshot on connect
        async with lock:
            snapshot = _slim_agent_snapshot()
        await websocket.send_json(
            {
                "type": "agents.snapshot",
                "payload": snapshot,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        if not REDIS_AVAILABLE:
            await websocket.send_json(
                {
                    "type": "system.warning",
                    "payload": {"message": "Redis not available; snapshots pushed every poll cycle"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            # No per-client loop — poll_agents broadcasts updates.
            # Just drain any incoming client messages until disconnect.
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
            return

        # ── Redis path: stream live task events ─────────────────────
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("nexus:events")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    event_data = json.loads(message["data"])
                    await websocket.send_json(
                        {
                            "type": "task.event",
                            "payload": event_data,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in Redis message: {message['data']}")

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
    finally:
        ws_clients.discard(websocket)
        logger.info(f"WebSocket client removed ({len(ws_clients)} remaining)")
        if pubsub is not None:
            try:
                await pubsub.unsubscribe("nexus:events")
            except Exception:
                pass
        if redis_client is not None:
            try:
                await redis_client.close()
            except Exception:
                pass


# ── Static Files ──────────────────────────────────────────────────────
# Mount static files last (fallback route)
# Use __file__-relative path so it works regardless of CWD
_static_dir = Path(__file__).resolve().parent / "static"
_index_html_path = _static_dir / "index.html"
_versioned_assets = ("styles.css", "colors.js", "dashboard.js")


def _compute_asset_version() -> str:
    """Compute a stable version token from static asset metadata."""
    hasher = hashlib.sha256()

    for asset_name in _versioned_assets:
        asset_path = _static_dir / asset_name
        hasher.update(asset_name.encode("utf-8"))

        if asset_path.is_file():
            stat = asset_path.stat()
            hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
            hasher.update(str(stat.st_size).encode("utf-8"))
        else:
            hasher.update(b"missing")

    return hasher.hexdigest()[:12]


def _render_index_html() -> str:
    """Render index.html with runtime asset version token."""
    raw = _index_html_path.read_text(encoding="utf-8")
    version = _compute_asset_version()
    return raw.replace("__ASSET_VERSION__", version)


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def serve_dashboard_index() -> HTMLResponse:
    """Serve dashboard index with dynamic cache-busting asset version token."""
    if not _index_html_path.is_file():
        return HTMLResponse(status_code=404, content="Dashboard index.html not found")

    return HTMLResponse(
        content=_render_index_html(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


if _static_dir.is_dir():
    app.mount("/", DevNoCacheStaticFiles(directory=str(_static_dir), html=True), name="static")
else:
    logger.warning(f"Static files directory not found at {_static_dir} — dashboard UI disabled")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8099)

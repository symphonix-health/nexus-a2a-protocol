"""Command Centre — Real-time monitoring dashboard for NEXUS-A2A agent networks.

Provides:
- Agent discovery and health polling
- Real-time event streaming via WebSocket
- Metrics aggregation with heatmap data
- Topology visualization support
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
UPDATE_INTERVAL_MS = int(os.getenv("UPDATE_INTERVAL_MS", "2000"))

# In-memory agent state
agent_states: dict[str, dict[str, Any]] = {}
scenario_catalog: list[dict[str, Any]] = []
lock = asyncio.Lock()
poll_task_started = False
first_poll_cycle_completed = False


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


# ── Agent Discovery & Health Polling ──────────────────────────────────
async def fetch_agent_card(url: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch agent card from discovery endpoint."""
    try:
        resp = await client.get(f"{url}/.well-known/agent-card.json", timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.debug(f"Failed to fetch agent card from {url}: {exc}")
    return None


async def fetch_agent_health(url: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch agent health status."""
    try:
        resp = await client.get(f"{url}/health", timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.debug(f"Health check failed for {url}: {exc}")
    return None


async def poll_agents():
    """Background task to continuously poll agent health."""
    global first_poll_cycle_completed
    async with httpx.AsyncClient() as client:
        while True:
            try:
                timestamp = datetime.now(timezone.utc).isoformat()

                for url in AGENT_URLS:
                    card = await fetch_agent_card(url, client)
                    health = await fetch_agent_health(url, client)

                    async with lock:
                        if card or health:
                            agent_name = (
                                (health or {}).get("name") or (card or {}).get("name") or url
                            )

                            # Infer dependencies from card
                            dependencies = []
                            if card and "methods" in card:
                                # Placeholder: parse from card or env vars
                                pass

                            # Calculate health score
                            status = "unknown"
                            health_score = 0.5
                            metrics = {}

                            if health:
                                status = health.get("status", "unknown")
                                metrics = health.get("metrics", {})

                                # Health score calculation
                                error_rate = 0.0
                                total = metrics.get("tasks_completed", 0) + metrics.get(
                                    "tasks_errored", 0
                                )
                                if total > 0:
                                    error_rate = metrics.get("tasks_errored", 0) / total

                                latency_factor = max(
                                    0, 1 - metrics.get("avg_latency_ms", 0) / 10000
                                )
                                success_rate = 1 - error_rate
                                health_score = latency_factor * 0.5 + success_rate * 0.5

                            agent_states[url] = {
                                "name": agent_name,
                                "url": url,
                                "status": status,
                                "health_score": round(health_score, 3),
                                "metrics": metrics,
                                "dependencies": dependencies,
                                "card": card or {},
                                "last_seen": timestamp,
                            }

                        # Mark unreachable agents
                        else:
                            if url in agent_states:
                                agent_states[url]["status"] = "unhealthy"
                                agent_states[url]["last_seen"] = timestamp

                first_poll_cycle_completed = True

                await asyncio.sleep(UPDATE_INTERVAL_MS / 1000)
            except Exception as exc:
                logger.error(f"Error in poll_agents: {exc}")
                await asyncio.sleep(5.0)


@app.on_event("startup")
async def startup_event():
    """Start background polling on startup."""
    global poll_task_started, scenario_catalog
    scenario_catalog = _load_scenario_catalog()
    asyncio.create_task(poll_agents())
    poll_task_started = True
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
    """Get current state of all monitored agents."""
    async with lock:
        return JSONResponse(content=list(agent_states.values()))


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


# ── WebSocket Event Streaming ─────────────────────────────────────────
@app.websocket("/api/events")
async def websocket_events(websocket: WebSocket):
    """Stream real-time events from Redis pub/sub."""
    await websocket.accept()
    logger.info("WebSocket client connected")

    try:
        if not REDIS_AVAILABLE:
            await websocket.send_json(
                {
                    "type": "system.warning",
                    "payload": {"message": "redis.asyncio not installed; event stream disabled"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            # Keep socket alive with periodic snapshots.
            while True:
                async with lock:
                    await websocket.send_json(
                        {
                            "type": "agents.snapshot",
                            "payload": list(agent_states.values()),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                await asyncio.sleep(5.0)

        # Connect to Redis
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("nexus:events")

        # Send initial agent state
        async with lock:
            await websocket.send_json(
                {
                    "type": "agents.snapshot",
                    "payload": list(agent_states.values()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        # Stream events
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

            # Periodically send agent updates
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
    finally:
        try:
            await pubsub.unsubscribe("nexus:events")
            await redis_client.close()
        except Exception:
            pass


# ── Static Files ──────────────────────────────────────────────────────
# Mount static files last (fallback route)
# Use __file__-relative path so it works regardless of CWD
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
else:
    logger.warning(f"Static files directory not found at {_static_dir} — dashboard UI disabled")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8099)

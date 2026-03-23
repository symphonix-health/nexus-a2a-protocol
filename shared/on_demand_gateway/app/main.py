"""On-demand gateway + process manager for demo agents.

This service starts agent processes lazily and proxies JSON-RPC requests:
    POST /rpc/{agent_alias}
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from shared.nexus_common.authorization import AuthorizationError, authorize_rpc_request
from shared.nexus_common.route_admission import (
    RouteAdmissionError,
    evaluate_route_admission,
)
from shared.nexus_common.gharra_models import parse_gharra_record
from shared.nexus_common.task_store import SqliteTaskEventStore, event_store_path_from_env

ROOT = Path(__file__).resolve().parents[3]
CONFIG_FILE = ROOT / "config" / "agents.json"
DEFAULT_GATEWAY_PORT = int(os.getenv("NEXUS_ON_DEMAND_GATEWAY_PORT", "8100"))
STARTUP_HEALTH_ATTEMPTS = int(os.getenv("NEXUS_ON_DEMAND_HEALTH_ATTEMPTS", "30"))
STARTUP_HEALTH_TIMEOUT_SECONDS = float(os.getenv("NEXUS_ON_DEMAND_HEALTH_TIMEOUT_SECONDS", "2.0"))
STARTUP_HEALTH_INTERVAL_SECONDS = float(
    os.getenv("NEXUS_ON_DEMAND_HEALTH_INTERVAL_SECONDS", "0.35")
)
RPC_TIMEOUT_SECONDS = float(os.getenv("NEXUS_ON_DEMAND_RPC_TIMEOUT_SECONDS", "45.0"))
IDLE_TTL_SECONDS = float(os.getenv("NEXUS_ON_DEMAND_IDLE_TTL_SECONDS", "120.0"))
IDLE_REAP_INTERVAL_SECONDS = max(5.0, IDLE_TTL_SECONDS / 4.0)
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")

# Dependency graph loaded from config/dependency_graph.json via seed database
def _load_dependency_graph() -> dict[str, list[str]]:
    """Load agent dependency graph from config file, falling back to seed DB."""
    try:
        dep_path = ROOT / "config" / "dependency_graph.json"
        if dep_path.is_file():
            raw = json.loads(dep_path.read_text(encoding="utf-8"))
            # Filter out non-list values (e.g. $schema, description)
            return {k: v for k, v in raw.items() if isinstance(v, list)}
    except Exception:
        pass
    try:
        from shared.nexus_common.seed_db import get_seed_db
        return get_seed_db().get_dependency_graph()
    except Exception:
        return {}


DEFAULT_DEPENDENCY_GRAPH: dict[str, list[str]] = _load_dependency_graph()


@dataclass(frozen=True)
class AgentSpec:
    """Runtime launch specification for one agent service."""

    spec_id: str
    category: str
    key: str
    alias: str
    path: str
    port: int
    description: str
    rpc_env: str | None
    env: str | None


def normalize_alias(alias: str) -> str:
    """Normalize aliases for process lookup and gateway routes."""
    value = alias.strip().lower().replace("-", "_")
    for suffix in ("_agent", "_scheduler", "_service"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    if value == "care_coordinator":
        return "coordinator"
    return value


def _load_config() -> dict[str, Any]:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def _alias_candidates(raw_key: str, normalized_alias: str) -> set[str]:
    candidates = {
        normalize_alias(raw_key),
        raw_key.strip().lower().replace("-", "_"),
        normalized_alias,
    }
    if normalized_alias == "coordinator":
        candidates.add("care_coordinator")
    if normalized_alias == "followup":
        candidates.add("followup_scheduler")
    return candidates


def build_alias_map(config: dict[str, Any]) -> dict[str, AgentSpec]:
    """Build alias -> AgentSpec map from config/agents.json."""
    alias_map: dict[str, AgentSpec] = {}
    agents_obj = config.get("agents", {})
    for category, category_agents in agents_obj.items():
        if not isinstance(category_agents, dict):
            continue
        for key, info in category_agents.items():
            if not isinstance(info, dict):
                continue
            normalized_alias = normalize_alias(key)
            spec = AgentSpec(
                spec_id=f"{category}.{key}",
                category=str(category),
                key=str(key),
                alias=normalized_alias,
                path=str(info.get("path", "")),
                port=int(info.get("port")),
                description=str(info.get("description", "")),
                rpc_env=info.get("rpc_env"),
                env=info.get("env"),
            )
            for candidate in _alias_candidates(key, normalized_alias):
                alias_map.setdefault(candidate, spec)
    return alias_map


def _load_dependency_graph() -> dict[str, list[str]]:
    env_value = os.getenv("NEXUS_ON_DEMAND_DEPENDENCIES_JSON", "").strip()
    if not env_value:
        return dict(DEFAULT_DEPENDENCY_GRAPH)

    try:
        parsed = json.loads(env_value)
    except json.JSONDecodeError:
        return dict(DEFAULT_DEPENDENCY_GRAPH)

    graph: dict[str, list[str]] = {}
    if isinstance(parsed, dict):
        for key, deps in parsed.items():
            normalized_key = normalize_alias(str(key))
            if isinstance(deps, list):
                graph[normalized_key] = [normalize_alias(str(dep)) for dep in deps]
            else:
                graph[normalized_key] = []
    return graph


def expand_dependency_order(alias: str, dependency_graph: dict[str, list[str]]) -> list[str]:
    """Expand dependencies in deterministic topological order."""
    root = normalize_alias(alias)
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        normalized_node = normalize_alias(node)
        if normalized_node in visited:
            return
        if normalized_node in visiting:
            raise ValueError(f"Dependency cycle detected at '{normalized_node}'")
        visiting.add(normalized_node)
        for dep in dependency_graph.get(normalized_node, []):
            visit(dep)
        visiting.remove(normalized_node)
        visited.add(normalized_node)
        ordered.append(normalized_node)

    visit(root)
    return ordered


class OnDemandProcessManager:
    """Lazily start and proxy to agent processes."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._alias_map = build_alias_map(config)
        self._dependency_graph = _load_dependency_graph()
        self._lock = asyncio.Lock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._last_used: dict[str, float] = {}
        self._externally_managed: set[str] = set()  # agents started outside gateway
        self._shutdown_event = asyncio.Event()
        self._reaper_task: asyncio.Task | None = None
        self._specs_by_id: dict[str, AgentSpec] = {}
        for spec in self._alias_map.values():
            self._specs_by_id[spec.spec_id] = spec

        self._base_env = self._build_base_env()

    def _build_base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env.setdefault("NEXUS_JWT_SECRET", "dev-secret-change-me")
        env.setdefault("DID_VERIFY", "false")
        env.setdefault("OPENAI_MODEL", "gpt-4o-mini")

        # Populate known inter-agent URLs from config for launched child processes.
        agent_urls: list[str] = []
        for spec in self._specs_by_id.values():
            base_url = f"http://localhost:{spec.port}"
            agent_urls.append(base_url)
            if spec.rpc_env:
                env[str(spec.rpc_env)] = f"{base_url}/rpc"
            if spec.env:
                env[str(spec.env)] = base_url

        if agent_urls:
            env["AGENT_URLS"] = ",".join(sorted(set(agent_urls)))
        return env

    def resolve_spec(self, alias: str) -> AgentSpec:
        normalized = normalize_alias(alias)
        spec = self._alias_map.get(normalized)
        if spec is None:
            raise KeyError(f"Unknown agent alias '{alias}'")
        return spec

    def _is_running(self, spec: AgentSpec) -> bool:
        if spec.spec_id in self._externally_managed:
            return True
        proc = self._processes.get(spec.spec_id)
        return proc is not None and proc.poll() is None

    def _touch(self, spec: AgentSpec) -> None:
        self._last_used[spec.spec_id] = time.monotonic()

    async def _wait_for_health(self, spec: AgentSpec) -> None:
        health_url = f"http://127.0.0.1:{spec.port}/.well-known/agent-card.json"
        timeout = STARTUP_HEALTH_TIMEOUT_SECONDS

        async with httpx.AsyncClient(timeout=timeout) as client:
            for _ in range(STARTUP_HEALTH_ATTEMPTS):
                proc = self._processes.get(spec.spec_id)
                if proc is None:
                    raise RuntimeError(f"{spec.alias} process missing during startup")
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"{spec.alias} exited during startup (code={proc.returncode})"
                    )

                try:
                    response = await client.get(health_url)
                    if response.status_code == 200:
                        return
                except Exception:
                    pass

                await asyncio.sleep(STARTUP_HEALTH_INTERVAL_SECONDS)

        raise RuntimeError(f"{spec.alias} did not become healthy on :{spec.port}")

    async def _is_externally_healthy(self, spec: AgentSpec) -> bool:
        """Check if an agent is already listening (started by launcher or externally)."""
        health_url = f"http://127.0.0.1:{spec.port}/.well-known/agent-card.json"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(health_url)
                return resp.status_code == 200
        except Exception:
            return False

    async def _start_spec(self, spec: AgentSpec) -> None:
        async with self._lock:
            if self._is_running(spec):
                self._touch(spec)
                return

            # Check if agent was started externally (e.g. by launcher)
            if await self._is_externally_healthy(spec):
                self._externally_managed.add(spec.spec_id)
                self._touch(spec)
                return

            cwd = ROOT / spec.path
            if not cwd.exists():
                raise RuntimeError(f"Agent path does not exist: {cwd}")

            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(spec.port),
                "--app-dir",
                ".",
            ]
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                env=self._base_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._processes[spec.spec_id] = proc
            self._touch(spec)

        try:
            await self._wait_for_health(spec)
        except Exception:
            await self.stop_spec(spec.alias)
            raise

    async def ensure_started(self, alias: str) -> AgentSpec:
        """Ensure target alias and its dependencies are running."""
        normalized = normalize_alias(alias)
        try:
            order = expand_dependency_order(normalized, self._dependency_graph)
        except ValueError:
            # Defensive fallback for misconfigured/cyclic dependency graphs.
            # Start only the requested alias rather than failing the RPC route.
            order = [normalized]
        for dep_alias in order:
            dep_spec = self.resolve_spec(dep_alias)
            await self._start_spec(dep_spec)
        spec = self.resolve_spec(normalized)
        self._touch(spec)
        return spec

    async def stop_spec(self, alias: str) -> None:
        spec = self.resolve_spec(alias)
        async with self._lock:
            proc = self._processes.pop(spec.spec_id, None)
            self._last_used.pop(spec.spec_id, None)
        if proc is None:
            return
        if proc.poll() is not None:
            return

        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    async def _reap_idle_processes(self) -> None:
        while True:
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=IDLE_REAP_INTERVAL_SECONDS,
                )
                break
            except asyncio.TimeoutError:
                pass
            if IDLE_TTL_SECONDS <= 0:
                continue

            now = time.monotonic()
            stale_aliases: list[str] = []
            async with self._lock:
                for spec_id, proc in list(self._processes.items()):
                    spec = self._specs_by_id.get(spec_id)
                    if spec is None:
                        continue
                    if proc.poll() is not None:
                        self._processes.pop(spec_id, None)
                        self._last_used.pop(spec_id, None)
                        continue
                    last = self._last_used.get(spec_id, now)
                    if (now - last) >= IDLE_TTL_SECONDS:
                        stale_aliases.append(spec.alias)

            for alias in stale_aliases:
                await self.stop_spec(alias)

    async def start_background_tasks(self) -> None:
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reap_idle_processes())

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._reaper_task is not None:
            await self._reaper_task
            self._reaper_task = None
        for spec in list(self._specs_by_id.values()):
            await self.stop_spec(spec.alias)

    def status(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for spec in sorted(
            self._specs_by_id.values(), key=lambda item: (item.category, item.alias)
        ):
            proc = self._processes.get(spec.spec_id)
            running = proc is not None and proc.poll() is None
            rows.append(
                {
                    "alias": spec.alias,
                    "category": spec.category,
                    "key": spec.key,
                    "port": spec.port,
                    "path": spec.path,
                    "description": spec.description,
                    "running": running,
                    "pid": proc.pid if running else None,
                    "managed_by_gateway": True,
                }
            )
        return rows


_config = _load_config()
_manager = OnDemandProcessManager(_config)

# --- Durable Event Sourcing (Mitigation 3.2) ---
# Initialise the gateway-level task event store for tasks/replay support.
_task_event_store: SqliteTaskEventStore | None = None
_store_path = event_store_path_from_env()
if _store_path:
    _retention_ms = int(os.getenv("NEXUS_TASK_EVENT_STORE_RETENTION_MS", "3600000"))
    _task_event_store = SqliteTaskEventStore(_store_path, retention_ms=_retention_ms)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _manager.start_background_tasks()
    try:
        yield
    finally:
        await _manager.shutdown()
        if _task_event_store is not None:
            _task_event_store.close()


app = FastAPI(
    title="NEXUS On-Demand Gateway",
    version="1.0.0",
    lifespan=lifespan,
)


def _proxy_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {"content-type": "application/json"}
    forward_keys = (
        "authorization",
        "x-forwarded-client-cert",
        "ssl-client-verify",
        "x-ssl-client-verify",
        "x-client-cert-sha256",
        "x-cert-thumbprint-sha256",
        "traceparent",
        "tracestate",
        "x-request-id",
    )
    for key in forward_keys:
        value = request.headers.get(key)
        if value:
            headers[key] = value
    return headers


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "on-demand-gateway"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    return {
        "status": "ready",
        "service": "on-demand-gateway",
        "managed_agents": len(_manager.status()),
        "default_port": DEFAULT_GATEWAY_PORT,
    }


@app.get("/api/agents")
async def list_agents() -> dict[str, Any]:
    return {"agents": _manager.status()}


@app.post("/api/agents/{agent_alias}/start")
async def start_agent(agent_alias: str) -> dict[str, Any]:
    try:
        spec = await _manager.ensure_started(agent_alias)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "started", "alias": spec.alias, "port": spec.port}


@app.post("/api/agents/{agent_alias}/stop")
async def stop_agent(agent_alias: str) -> dict[str, Any]:
    try:
        await _manager.stop_spec(agent_alias)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "stopped", "alias": normalize_alias(agent_alias)}


@app.post("/rpc/{agent_alias}")
async def proxy_rpc(agent_alias: str, request: Request) -> Response:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc

    try:
        spec = _manager.resolve_spec(agent_alias)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    method = str(payload.get("method") or "").strip()
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    if method:
        try:
            authorize_rpc_request(
                authorization_header=request.headers.get("authorization", ""),
                headers=request.headers,
                method=method,
                params=params,
                target_agent_id=spec.key,
                required_scope=REQUIRED_SCOPE,
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    # --- GHARRA route admission (optional) ---
    # BulletTrain passes the resolved GHARRA record via X-Gharra-Record header.
    # When present, Nexus validates trust before opening the route.
    gharra_header = request.headers.get("x-gharra-record", "").strip()
    if gharra_header:
        try:
            gharra_data = json.loads(gharra_header)
            gharra_record = parse_gharra_record(gharra_data)
            admission = evaluate_route_admission(
                gharra_record,
                method=method,
                session_id=request.headers.get("x-session-id"),
                route_source="on-demand-gateway",
            )
            if not admission.admitted:
                raise HTTPException(
                    status_code=403,
                    detail=f"Route admission denied: {'; '.join(admission.reasons)}",
                )
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid X-Gharra-Record JSON: {exc}"
            ) from exc
        except RouteAdmissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        spec = await _manager.ensure_started(agent_alias)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    proxy_url = f"http://127.0.0.1:{spec.port}/rpc"
    headers = _proxy_headers(request)

    try:
        async with httpx.AsyncClient(timeout=RPC_TIMEOUT_SECONDS) as client:
            resp = await client.post(proxy_url, json=payload, headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Proxy transport error: {exc}") from exc

    _manager._touch(spec)  # Touch on successful proxy attempt.

    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        except Exception:
            return Response(
                content=resp.content, status_code=resp.status_code, media_type=content_type
            )

    return Response(content=resp.content, status_code=resp.status_code, media_type=content_type)


# ---------------------------------------------------------------------------
# Durable Event Sourcing: tasks/replay RPC handler (Mitigation 3.2)
# ---------------------------------------------------------------------------


@app.post("/rpc/{agent_alias}/replay")
async def tasks_replay(agent_alias: str, request: Request) -> JSONResponse:
    """Replay task events from the durable event store.

    JSON-RPC method: tasks/replay
    Params:
      - task_id (str): required
      - since_seq (int): replay events after this sequence number (default 0)
      - max_events (int|null): limit number of replayed events (default null = all)

    Returns JSON-RPC result with replayed events list and stream state.
    """
    if _task_event_store is None:
        raise HTTPException(
            status_code=503,
            detail="Task event store not configured",
        )

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    task_id = str(params.get("task_id") or "").strip()
    if not task_id:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32602, "message": "task_id is required"},
            },
        )

    since_seq = int(params.get("since_seq", 0))
    max_events = params.get("max_events")
    if max_events is not None:
        max_events = int(max_events)

    # Check stream state
    state = _task_event_store.get_stream_state(task_id)
    if state is None:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32001, "message": f"No events found for task {task_id}"},
            },
        )

    stream_epoch, last_seq = state
    events = _task_event_store.replay_after(
        task_id, since_seq=since_seq, max_events=max_events,
    )

    return JSONResponse(
        status_code=200,
        content={
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "result": {
                "task_id": task_id,
                "stream_epoch": stream_epoch,
                "last_seq": last_seq,
                "since_seq": since_seq,
                "events": events,
                "event_count": len(events),
            },
        },
    )


@app.get("/api/event-store/replay")
async def event_store_replay(request: Request) -> JSONResponse:
    """Cross-registry event replay from the gateway event store (Mitigation 3.3).

    Query params:
      - task_id (str): optional filter by task_id
      - since_seq (int): replay events after this sequence (default 0)
      - max_events (int): max events to return (default 100)

    Returns a list of events with replay metadata.
    """
    if _task_event_store is None:
        return JSONResponse(
            status_code=200,
            content={
                "enabled": False,
                "events": [],
                "event_count": 0,
                "detail": "Task event store not configured",
            },
        )

    task_id = request.query_params.get("task_id", "").strip()
    since_seq = int(request.query_params.get("since_seq", "0"))
    max_events = int(request.query_params.get("max_events", "100"))

    if task_id:
        state = _task_event_store.get_stream_state(task_id)
        if state is None:
            return JSONResponse(
                status_code=200,
                content={
                    "enabled": True,
                    "task_id": task_id,
                    "events": [],
                    "event_count": 0,
                    "detail": f"No events found for task {task_id}",
                },
            )
        stream_epoch, last_seq = state
        events = _task_event_store.replay_after(task_id, since_seq=since_seq, max_events=max_events)
        return JSONResponse(
            status_code=200,
            content={
                "enabled": True,
                "task_id": task_id,
                "stream_epoch": stream_epoch,
                "last_seq": last_seq,
                "since_seq": since_seq,
                "events": events,
                "event_count": len(events),
            },
        )

    # No task_id: return store status with available streams
    return JSONResponse(
        status_code=200,
        content={
            "enabled": True,
            "events": [],
            "event_count": 0,
            "detail": "Provide task_id query parameter to replay specific task events",
            "store_path": str(_task_event_store._path),
        },
    )


@app.get("/api/event-store/status")
async def event_store_status() -> dict[str, Any]:
    """Return durable event store status for observability."""
    if _task_event_store is None:
        return {"enabled": False, "reason": "NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT=false"}
    return {
        "enabled": True,
        "store_path": str(_task_event_store._path),
        "retention_ms": _task_event_store._retention_ms,
    }

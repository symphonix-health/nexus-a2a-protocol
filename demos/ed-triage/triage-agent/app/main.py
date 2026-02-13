"""ED Triage Agent — entry point for clinical risk assessment workflow.

Orchestrates: TriageAgent → DiagnosisAgent → OpenHIE Mediator (FHIR).
Supports JSON-RPC 2.0, SSE streaming, and WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.health import HealthMonitor, apply_backpressure_to_agent_card
from shared.nexus_common.http_client import jsonrpc_call
from shared.nexus_common.idempotency import IdempotencyStore
from shared.nexus_common.ids import make_task_id, make_trace_id
from shared.nexus_common.jsonrpc import JsonRpcError, parse_request, response_error, response_result
from shared.nexus_common.sse import TaskEventBus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.triage-agent")

app = FastAPI(title="triage-agent")
bus = TaskEventBus(agent_name="triage-agent")
health_monitor = HealthMonitor("triage-agent")
idempotency_store = IdempotencyStore()
inflight_tasks = 0

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")


# ── Auth middleware ──────────────────────────────────────────────
def _require_auth(req: Request) -> str:
    auth = req.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if did_verify_enabled() and not verify_did_signature():
        raise HTTPException(status_code=401, detail="DID signature verification failed")
    return token


# ── Discovery ────────────────────────────────────────────────────
@app.get("/.well-known/agent-card.json")
async def agent_card():
    path = os.path.join(os.path.dirname(__file__), "agent_card.json")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return JSONResponse(content=apply_backpressure_to_agent_card(payload, health_monitor))


# ── Health ───────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check endpoint with metrics."""
    return JSONResponse(content=health_monitor.get_health())


# ── SSE streaming ────────────────────────────────────────────────
@app.get("/events/{task_id}")
async def events(task_id: str, request: Request):
    _require_auth(request)

    async def gen():
        async for chunk in bus.stream(task_id):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── WebSocket streaming ─────────────────────────────────────────
@app.websocket("/ws/{task_id}")
async def ws_stream(websocket: WebSocket, task_id: str):
    token = websocket.query_params.get("token", "")
    try:
        verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
    except AuthError:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        async for evt in bus.stream_ws(task_id):
            await websocket.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        bus.cleanup(task_id)


# ── RPC methods ──────────────────────────────────────────────────
METHODS: dict = {}


async def _send_subscribe(params: dict, token: str) -> dict:
    global inflight_tasks

    scenario_context = (
        params.get("scenario_context") if isinstance(params.get("scenario_context"), dict) else {}
    )
    correlation = params.get("correlation") if isinstance(params.get("correlation"), dict) else {}
    idempotency = params.get("idempotency") if isinstance(params.get("idempotency"), dict) else {}

    trace_id = correlation.get("trace_id") or make_trace_id()
    parent_task_id = correlation.get("parent_task_id")
    causation_id = correlation.get("causation_id")

    idempotency_key = idempotency.get("idempotency_key")
    dedup_window_ms = int(idempotency.get("dedup_window_ms", 60000)) if idempotency else 60000

    if idempotency_key:
        dedup = idempotency_store.check_or_register(idempotency_key, dedup_window_ms)
        if dedup.is_duplicate and dedup.cached_response:
            return {
                **dedup.cached_response,
                "dedup": {
                    "duplicate": True,
                    "idempotency_key": idempotency_key,
                    "dedup_window_ms": dedup.dedup_window_ms,
                },
            }

    task_id = make_task_id()

    if idempotency_key:
        first_response = {"task_id": task_id, "trace_id": trace_id}
        idempotency_store.save_response(idempotency_key, first_response)

    logger.info("[%s] task=%s ACCEPTED", trace_id, task_id)

    # Record metrics
    health_monitor.metrics.record_accepted()
    inflight_tasks += 1
    health_monitor.set_backpressure(queue_depth=inflight_tasks)
    start_time = asyncio.get_event_loop().time()

    event_correlation = {
        "trace_id": trace_id,
        **({"parent_task_id": parent_task_id} if parent_task_id else {}),
        **({"causation_id": causation_id} if causation_id else {}),
    }
    event_idempotency = (
        {"idempotency_key": idempotency_key, "dedup_window_ms": dedup_window_ms}
        if idempotency_key
        else None
    )

    await bus.publish(
        task_id,
        "nexus.task.accepted",
        json.dumps(
            {
                "task_id": task_id,
                "state": "accepted",
                "trace_id": trace_id,
                "progress": {"state": "accepted", "percent": 0.0},
            }
        ),
        scenario_context=scenario_context or None,
        correlation=event_correlation,
        idempotency=event_idempotency,
        progress={"state": "accepted", "percent": 0.0},
    )

    async def run():
        nonlocal scenario_context
        nonlocal event_correlation
        nonlocal event_idempotency
        global inflight_tasks
        try:
            await bus.publish(
                task_id,
                "nexus.task.working",
                json.dumps(
                    {
                        "task_id": task_id,
                        "state": "working",
                        "step": "calling_diagnosis",
                        "progress": {
                            "state": "working",
                            "percent": 35.0,
                            "eta_ms": 9000,
                        },
                    }
                ),
                scenario_context=scenario_context or None,
                correlation=event_correlation,
                idempotency=event_idempotency,
                progress={"state": "working", "percent": 35.0, "eta_ms": 9000},
            )
            diag_rpc = os.getenv("NEXUS_DIAGNOSIS_RPC", "http://diagnosis-agent:8022/rpc")
            diag_timeout_s = float(os.getenv("NEXUS_DIAGNOSIS_RPC_TIMEOUT_SECONDS", "600"))
            resp = await jsonrpc_call(
                diag_rpc,
                token,
                "diagnosis/assess",
                {
                    "task": params.get("task", {}),
                    "task_id": task_id,
                    "scenario_context": scenario_context,
                    "correlation": {
                        **event_correlation,
                        "parent_task_id": task_id,
                        "causation_id": f"{task_id}-triage",
                    },
                    "idempotency": event_idempotency or {},
                },
                f"{task_id}-diag",
                timeout=diag_timeout_s,
            )

            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            if "error" in resp:
                health_monitor.metrics.record_error(duration_ms)
                await bus.publish(
                    task_id,
                    "nexus.task.error",
                    json.dumps(
                        {
                            "task_id": task_id,
                            "error": resp["error"],
                            "progress": {
                                "state": "error",
                                "percent": 100.0,
                                "eta_ms": 0,
                            },
                        }
                    ),
                    duration_ms,
                    scenario_context=scenario_context or None,
                    correlation=event_correlation,
                    idempotency=event_idempotency,
                    progress={"state": "error", "percent": 100.0, "eta_ms": 0},
                )
                return

            health_monitor.metrics.record_completed(duration_ms)
            await bus.publish(
                task_id,
                "nexus.task.final",
                json.dumps(
                    {
                        **resp["result"],
                        "progress": {
                            "state": "final",
                            "percent": 100.0,
                            "eta_ms": 0,
                        },
                    }
                ),
                duration_ms,
                scenario_context=scenario_context or None,
                correlation=event_correlation,
                idempotency=event_idempotency,
                progress={"state": "final", "percent": 100.0, "eta_ms": 0},
            )
            logger.info("[%s] task=%s COMPLETED", trace_id, task_id)
        except Exception as exc:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.exception("[%s] task=%s FAILED", trace_id, task_id)
            health_monitor.metrics.record_error(duration_ms)
            await bus.publish(
                task_id,
                "nexus.task.error",
                json.dumps(
                    {
                        "task_id": task_id,
                        "error": str(exc),
                        "progress": {
                            "state": "error",
                            "percent": 100.0,
                            "eta_ms": 0,
                        },
                    }
                ),
                duration_ms,
                scenario_context=scenario_context or None,
                correlation=event_correlation,
                idempotency=event_idempotency,
                progress={"state": "error", "percent": 100.0, "eta_ms": 0},
            )
        finally:
            inflight_tasks = max(0, inflight_tasks - 1)
            health_monitor.set_backpressure(queue_depth=inflight_tasks)

    asyncio.create_task(run())
    response = {"task_id": task_id, "trace_id": trace_id}
    return response


METHODS["tasks/sendSubscribe"] = _send_subscribe


# ── JSON-RPC dispatcher ─────────────────────────────────────────
@app.post("/rpc")
async def rpc(request: Request):
    token = _require_auth(request)
    payload = await request.json()
    try:
        req = parse_request(payload)
        method, params, id_ = req["method"], req["params"], req["id"]
        if method not in METHODS:
            raise JsonRpcError(-32601, "Method not found", method)
        result = await METHODS[method](params, token)
        return JSONResponse(content=response_result(id_, result))
    except JsonRpcError as exc:
        return JSONResponse(
            content=response_error(payload.get("id"), exc),
            status_code=200,
        )
    except Exception as exc:
        err = JsonRpcError(-32000, "Server error", str(exc))
        return JSONResponse(
            content=response_error(payload.get("id"), err),
            status_code=200,
        )

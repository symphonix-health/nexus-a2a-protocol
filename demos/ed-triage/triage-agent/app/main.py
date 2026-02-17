from __future__ import annotations

import asyncio
import json
import logging
import os
from inspect import isawaitable

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.health import HealthMonitor, apply_backpressure_to_agent_card
from shared.nexus_common.http_client import jsonrpc_call
from shared.nexus_common.idempotency import IdempotencyStore, RedisIdempotencyStore
from shared.nexus_common.ids import make_task_id, make_trace_id
from shared.nexus_common.jsonrpc import JsonRpcError, parse_request, response_error, response_result
from shared.nexus_common.sse import TaskEventBus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.triage-agent")

app = FastAPI(title="triage-agent")
bus = TaskEventBus(agent_name="triage-agent")
health_monitor = HealthMonitor("triage-agent")
inflight_tasks = 0

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")


def _build_idempotency_store() -> IdempotencyStore | RedisIdempotencyStore:
    backend = os.getenv("NEXUS_IDEMPOTENCY_BACKEND", "memory").strip().lower()
    if backend == "redis":
        try:
            return RedisIdempotencyStore(redis_url=os.getenv("REDIS_URL"))
        except Exception as exc:
            logger.warning("Redis idempotency unavailable (%s); falling back to memory store", exc)
    return IdempotencyStore()


idempotency_store = _build_idempotency_store()


async def _idempotency_check_or_register(key: str, dedup_window_ms: int) -> object:
    result = idempotency_store.check_or_register(key, dedup_window_ms)
    if isawaitable(result):
        return await result
    return result


async def _idempotency_save_response(key: str, response: dict) -> None:
    result = idempotency_store.save_response(key, response)
    if isawaitable(result):
        await result


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


@app.get("/.well-known/agent-card.json")
async def agent_card():
    path = os.path.join(os.path.dirname(__file__), "agent_card.json")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return JSONResponse(content=apply_backpressure_to_agent_card(payload, health_monitor))


@app.get("/health")
async def health():
    return JSONResponse(content=health_monitor.get_health())


@app.get("/events/{task_id}")
async def events(task_id: str, request: Request):
    _require_auth(request)
    return StreamingResponse(bus.stream(task_id), media_type="text/event-stream")


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


def _triage_level_from_task(task: dict) -> str:
    complaint = str(task.get("chief_complaint") or (task.get("inputs") or {}).get("chief_complaint", "")).lower()
    vitals = task.get("vitals") if isinstance(task.get("vitals"), dict) else {}
    try:
        spo2 = float(vitals.get("spo2", 100))
    except Exception:
        spo2 = 100.0
    try:
        temp_c = float(vitals.get("temp_c", 36.8))
    except Exception:
        temp_c = 36.8

    if "chest" in complaint or "shortness of breath" in complaint or spo2 < 90:
        return "ESI-2"
    if "confusion" in complaint or temp_c >= 39.0:
        return "ESI-2"
    if "laceration" in complaint:
        return "ESI-4"
    return "ESI-3"


METHODS: dict = {}


async def _send_subscribe(params: dict, token: str) -> dict:
    global inflight_tasks

    correlation = params.get("correlation") if isinstance(params.get("correlation"), dict) else {}
    idempotency = params.get("idempotency") if isinstance(params.get("idempotency"), dict) else {}
    scenario_context = params.get("scenario_context") if isinstance(params.get("scenario_context"), dict) else {}

    idempotency_key = idempotency.get("idempotency_key")
    dedup_window_ms = int(idempotency.get("dedup_window_ms", 60000)) if idempotency else 60000

    if idempotency_key:
        dedup = await _idempotency_check_or_register(idempotency_key, dedup_window_ms)
        if getattr(dedup, "is_duplicate", False) and getattr(dedup, "cached_response", None):
            return {
                **dedup.cached_response,
                "dedup": {
                    "duplicate": True,
                    "idempotency_key": idempotency_key,
                    "dedup_window_ms": dedup.dedup_window_ms,
                },
            }

    task = params.get("task") if isinstance(params.get("task"), dict) else {}
    patient = task.get("patient") if isinstance(task.get("patient"), dict) else {}
    patient_id = str(patient.get("patient_id") or task.get("patient_ref") or "unknown")
    triage_level = _triage_level_from_task(task)

    task_id = make_task_id()
    trace_id = str(correlation.get("trace_id") or make_trace_id())
    logger.info("[%s] task=%s ACCEPTED", trace_id, task_id)

    response = {
        "task_id": task_id,
        "trace_id": trace_id,
        "patient_id": patient_id,
        "triage_level": triage_level,
        "rationale": "Triage task accepted and queued for diagnosis.",
    }

    if idempotency_key:
        await _idempotency_save_response(idempotency_key, response)

    health_monitor.metrics.record_accepted()
    inflight_tasks += 1
    health_monitor.set_backpressure(queue_depth=inflight_tasks)
    start_time = asyncio.get_event_loop().time()

    await bus.publish(
        task_id,
        "nexus.task.status",
        json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}),
        scenario_context=scenario_context or None,
        correlation=correlation or None,
        idempotency=idempotency or None,
    )

    async def run() -> None:
        global inflight_tasks
        try:
            await bus.publish(
                task_id,
                "nexus.task.status",
                json.dumps({"task_id": task_id, "state": "working", "step": "calling_diagnosis"}),
                scenario_context=scenario_context or None,
                correlation=correlation or None,
                idempotency=idempotency or None,
            )

            diag_rpc = os.getenv("NEXUS_DIAGNOSIS_RPC", "http://diagnosis-agent:8022/rpc")
            diag_timeout_s = float(os.getenv("NEXUS_DIAGNOSIS_RPC_TIMEOUT_SECONDS", "600"))
            resp = await jsonrpc_call(
                diag_rpc,
                token,
                "diagnosis/assess",
                {
                    "task": task,
                    "task_id": task_id,
                    "scenario_context": scenario_context,
                    "correlation": {
                        **correlation,
                        "trace_id": trace_id,
                        "parent_task_id": task_id,
                        "causation_id": f"{task_id}-triage",
                    },
                    "idempotency": idempotency,
                },
                f"{task_id}-diag",
                timeout=diag_timeout_s,
            )

            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            if isinstance(resp, dict) and "error" in resp:
                health_monitor.metrics.record_error(duration_ms)
                await bus.publish(
                    task_id,
                    "nexus.task.error",
                    json.dumps({"task_id": task_id, "error": resp.get("error")}),
                    duration_ms,
                    scenario_context=scenario_context or None,
                    correlation=correlation or None,
                    idempotency=idempotency or None,
                )
                return

            health_monitor.metrics.record_completed(duration_ms)
            result_payload = resp.get("result", {}) if isinstance(resp, dict) else {}
            final_payload = {
                "task_id": task_id,
                "patient_id": patient_id,
                "triage_level": triage_level,
                **(result_payload if isinstance(result_payload, dict) else {}),
            }
            await bus.publish(
                task_id,
                "nexus.task.final",
                json.dumps(final_payload),
                duration_ms,
                scenario_context=scenario_context or None,
                correlation=correlation or None,
                idempotency=idempotency or None,
            )
            logger.info("[%s] task=%s COMPLETED", trace_id, task_id)
        except Exception as exc:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.exception("[%s] task=%s FAILED", trace_id, task_id)
            health_monitor.metrics.record_error(duration_ms)
            await bus.publish(
                task_id,
                "nexus.task.error",
                json.dumps({"task_id": task_id, "error": str(exc)}),
                duration_ms,
                scenario_context=scenario_context or None,
                correlation=correlation or None,
                idempotency=idempotency or None,
            )
        finally:
            inflight_tasks = max(0, inflight_tasks - 1)
            health_monitor.set_backpressure(queue_depth=inflight_tasks)

    asyncio.create_task(run())
    return response


async def _tasks_get(params: dict, token: str) -> dict:
    task_id = params.get("task_id")
    if not task_id:
        raise JsonRpcError(-32602, "Invalid params", "task_id is required")
    return {"task_id": task_id, "state": "unknown"}


async def _tasks_cancel(params: dict, token: str) -> dict:
    task_id = params.get("task_id")
    if not task_id:
        raise JsonRpcError(-32602, "Invalid params", "task_id is required")
    return {"task_id": task_id, "cancelled": False, "reason": "cancel_not_supported"}


METHODS["tasks/sendSubscribe"] = _send_subscribe
METHODS["tasks/send"] = _send_subscribe
METHODS["tasks/get"] = _tasks_get
METHODS["tasks/cancel"] = _tasks_cancel


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
        return JSONResponse(content=response_result(id_, result, method=method, params=params))
    except JsonRpcError as exc:
        return JSONResponse(content=response_error(payload.get("id"), exc), status_code=200)
    except Exception as exc:
        err = JsonRpcError(-32000, "Server error", str(exc))
        return JSONResponse(content=response_error(payload.get("id"), err), status_code=200)


@app.on_event("shutdown")
async def _shutdown() -> None:
    close_method = getattr(idempotency_store, "close", None)
    if callable(close_method):
        result = close_method()
        if isawaitable(result):
            await result
    await bus.close()
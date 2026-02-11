"""Diagnosis Agent — performs clinical assessment using LLM + FHIR context."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.health import HealthMonitor
from shared.nexus_common.http_client import jsonrpc_call
from shared.nexus_common.ids import make_task_id, make_trace_id
from shared.nexus_common.jsonrpc import JsonRpcError, parse_request, response_error, response_result
from shared.nexus_common.openai_helper import llm_chat
from shared.nexus_common.sse import TaskEventBus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.diagnosis-agent")

app = FastAPI(title="diagnosis-agent")
bus = TaskEventBus(agent_name="diagnosis-agent")
health_monitor = HealthMonitor("diagnosis-agent")

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")


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
        return JSONResponse(content=json.load(f))


@app.get("/health")
async def health():
    """Health check endpoint with metrics."""
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


METHODS: dict = {}


async def _do_assess(params: dict, token: str) -> dict:
    """Core assessment logic without metrics tracking."""
    task = params.get("task", {})
    patient_ref = task.get("patient_ref", "Patient/unknown")
    openhie = os.getenv("NEXUS_OPENHIE_RPC", "http://openhie-mediator:8023/rpc")

    # Fetch FHIR context via OpenHIE mediator
    try:
        ctx = await jsonrpc_call(openhie, token, "fhir/get", {"patient_ref": patient_ref}, "fhir-1")
    except Exception:
        ctx = {"result": {"patient": {}, "allergies": {}}}

    chief = (task.get("inputs") or {}).get("chief_complaint", "")
    triage = "EMERGENCY" if "chest" in chief.lower() else "URGENT"

    system = "You are a cautious ED triage support assistant. Provide brief rationale."
    user = f"Complaint: {chief}. Context: {json.dumps(ctx.get('result', {}))[:1200]}"
    rationale = await asyncio.to_thread(llm_chat, system, user)

    return {
        "task_id": params.get("task_id"),
        "triage_priority": triage,
        "rationale": rationale,
        "patient_context": ctx.get("result", {}),
    }


async def _assess(params: dict, token: str) -> dict:
    """Assess with metrics tracking — for direct diagnosis/assess calls."""
    health_monitor.metrics.record_accepted()
    start_time = asyncio.get_event_loop().time()
    try:
        result = await _do_assess(params, token)
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        health_monitor.metrics.record_completed(duration_ms)
        return result
    except Exception:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        health_monitor.metrics.record_error(duration_ms)
        raise


METHODS["diagnosis/assess"] = _assess


async def _send_subscribe(params: dict, token: str) -> dict:
    """Handle tasks/sendSubscribe — matches the standard HelixCare agent pattern."""
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()
    await bus.publish(task_id, "nexus.task.status",
                      json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            await bus.publish(task_id, "nexus.task.status",
                              json.dumps({"task_id": task_id, "state": "working", "step": "diagnosing"}))
            result = await _do_assess({"task": params}, token)
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_completed(d)
            await bus.publish(task_id, "nexus.task.final",
                              json.dumps({"task_id": task_id, "result": result}), d)
        except Exception as exc:
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_error(d)
            await bus.publish(task_id, "nexus.task.error",
                              json.dumps({"task_id": task_id, "error": str(exc)}), d)

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}


METHODS["tasks/sendSubscribe"] = _send_subscribe
METHODS["tasks/send"] = _send_subscribe


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
        return JSONResponse(content=response_error(payload.get("id"), exc), status_code=200)
    except Exception as exc:
        err = JsonRpcError(-32000, "Server error", str(exc))
        return JSONResponse(content=response_error(payload.get("id"), err), status_code=200)

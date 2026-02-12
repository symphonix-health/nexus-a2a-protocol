"""Insurer Agent — orchestrates consent-gated record request with HITL gate."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import (FastAPI, HTTPException, Request, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.http_client import jsonrpc_call
from shared.nexus_common.ids import make_task_id, make_trace_id
from shared.nexus_common.jsonrpc import (JsonRpcError, parse_request,
                                         response_error, response_result)
from shared.nexus_common.sse import TaskEventBus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.insurer-agent")

app = FastAPI(title="insurer-agent")
bus = TaskEventBus()

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
    return JSONResponse(content={"status": "healthy", "name": "insurer-agent"})


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


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    logger.info("[%s] task=%s ACCEPTED", trace_id, task_id)
    await bus.publish(task_id, "nexus.task.status", json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            provider_rpc = os.getenv("PROVIDER_RPC", "http://provider-agent:8042/rpc")
            hitl_rpc = os.getenv("HITL_RPC", "http://hitl-ui:8044/rpc")
            hitl_required = os.getenv("HITL_REQUIRED", "true").lower() == "true"

            # Step 1: Request records from provider (which verifies consent)
            await bus.publish(task_id, "nexus.task.status", json.dumps({"task_id": task_id, "state": "working", "step": "requesting_records"}))
            resp = await jsonrpc_call(
                provider_rpc, token, "records/provide",
                {"task": params.get("task", {}), "task_id": task_id},
                f"{task_id}-prov",
            )
            provider_result = resp.get("result", {})
            await bus.publish(task_id, "nexus.task.status", json.dumps({"task_id": task_id, "state": "working", "step": "provider_responded"}))

            # Step 2: HITL gate (if required and consent was granted)
            if hitl_required and provider_result.get("authorized"):
                await bus.publish(task_id, "nexus.task.status", json.dumps({"task_id": task_id, "state": "input-required", "step": "awaiting_hitl_approval"}))
                hitl_resp = await jsonrpc_call(
                    hitl_rpc, token, "hitl/approve",
                    {"task_id": task_id, "decision": "APPROVE", "comment": "Auto-approved for PoC"},
                    f"{task_id}-hitl",
                )
                provider_result["hitl"] = hitl_resp.get("result", {})

            await bus.publish(task_id, "nexus.task.final", json.dumps(provider_result))
            logger.info("[%s] task=%s COMPLETED", trace_id, task_id)
        except Exception as exc:
            logger.exception("[%s] task=%s FAILED", trace_id, task_id)
            await bus.publish(task_id, "nexus.task.error", json.dumps({"task_id": task_id, "error": str(exc)}))

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}


METHODS["tasks/sendSubscribe"] = _send_subscribe


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

"""central-surveillance agent – orchestrator that fans out to hospital-reporter
and osint-agent (preferring MQTT, falling back to HTTP), then synthesises an
outbreak alert via LLM.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.http_client import jsonrpc_call
from shared.nexus_common.ids import make_task_id
from shared.nexus_common.jsonrpc import (INVALID_PARAMS, METHOD_NOT_FOUND,
                                         parse_request, response_error,
                                         response_result)
from shared.nexus_common.mqtt_client import (mqtt_available, mqtt_publish,
                                             mqtt_subscribe)
from shared.nexus_common.openai_helper import llm_available, llm_chat
from shared.nexus_common.sse import SseEvent, TaskEventBus

app = FastAPI(title="central-surveillance")
bus = TaskEventBus()

AGENT_CARD = json.loads(
    (pathlib.Path(__file__).resolve().parent.parent / "agent_card.json").read_text()
)

JWT_SECRET = os.environ.get("NEXUS_JWT_SECRET", "super-secret-test-key-change-me")
HOSPITAL_URL = os.environ.get("HOSPITAL_REPORTER_URL", "http://hospital-reporter:8051")
OSINT_URL = os.environ.get("OSINT_AGENT_URL", "http://osint-agent:8052")
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))

# ── auth ────────────────────────────────────────────────────────────
def _require_auth(request: Request) -> dict:
    hdr = request.headers.get("Authorization", "")
    if not hdr.startswith("Bearer "):
        raise AuthError("Missing Bearer token")
    return verify_jwt(hdr.split(" ", 1)[1], JWT_SECRET)

def _make_token() -> str:
    from shared.nexus_common.auth import mint_jwt
    return mint_jwt({"sub": "central-surveillance", "scope": "agent"}, JWT_SECRET, ttl=300)

# ── agent card ──────────────────────────────────────────────────────
@app.get("/.well-known/agent-card.json")
async def agent_card():
    return JSONResponse(AGENT_CARD)


@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy", "name": "central-surveillance"})

# ── SSE stream ──────────────────────────────────────────────────────
@app.get("/events/{task_id}")
async def sse(task_id: str, request: Request):
    _require_auth(request)
    return StreamingResponse(bus.stream(task_id), media_type="text/event-stream")

# ── WebSocket stream ────────────────────────────────────────────────
@app.websocket("/ws/{task_id}")
async def ws(websocket: WebSocket, task_id: str):
    token = websocket.query_params.get("token", "")
    verify_jwt(token, JWT_SECRET)
    await websocket.accept()
    try:
        async for event in bus.stream_ws(task_id):
            await websocket.send_text(event)
    except WebSocketDisconnect:
        pass

# ── MQTT helpers ────────────────────────────────────────────────────
async def _try_mqtt_request(topic_req: str, topic_resp: str, payload: dict, timeout: float = 10.0):
    """Publish a request via MQTT and await a response on topic_resp."""
    if not await mqtt_available(MQTT_BROKER, MQTT_PORT):
        return None
    response_holder: dict | None = None
    event = asyncio.Event()

    async def _on_msg(msg_payload: bytes):
        nonlocal response_holder
        try:
            response_holder = json.loads(msg_payload)
        except Exception:
            response_holder = {"raw": msg_payload.decode(errors="replace")}
        event.set()

    sub_task = asyncio.create_task(
        mqtt_subscribe(MQTT_BROKER, MQTT_PORT, topic_resp, _on_msg)
    )
    await asyncio.sleep(0.3)  # allow subscription to settle
    await mqtt_publish(MQTT_BROKER, MQTT_PORT, topic_req, json.dumps(payload).encode())
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    sub_task.cancel()
    return response_holder

# ── RPC methods ─────────────────────────────────────────────────────
async def _tasks_send_subscribe(params: dict) -> dict:
    task_data = params.get("task", params)
    pathogen = task_data.get("pathogen", "cholera")
    region = task_data.get("region", "Gauteng")
    task_id = make_task_id()
    token = _make_token()

    await bus.publish(task_id, SseEvent(event="status", data=json.dumps({"task_id": task_id, "status": "working", "step": "fan-out"})))

    # ── Fan-out: prefer MQTT, fall back to HTTP ────────────────────
    hospital_result = await _try_mqtt_request(
        "nexus/surveillance/report/req",
        "nexus/surveillance/report/resp",
        {"pathogen": pathogen, "region": region},
    )
    if hospital_result is None:
        hospital_result = await jsonrpc_call(
            f"{HOSPITAL_URL}/rpc", "surveillance/report",
            {"pathogen": pathogen, "region": region}, token,
        )

    osint_result = await _try_mqtt_request(
        "nexus/osint/headlines/req",
        "nexus/osint/headlines/resp",
        {"pathogen": pathogen},
    )
    if osint_result is None:
        osint_result = await jsonrpc_call(
            f"{OSINT_URL}/rpc", "osint/headlines",
            {"pathogen": pathogen}, token,
        )

    await bus.publish(task_id, SseEvent(event="status", data=json.dumps({"task_id": task_id, "status": "working", "step": "synthesis"})))

    # ── Synthesise alert via LLM ───────────────────────────────────
    prompt = (
        f"You are a public-health surveillance analyst. Given the following data, "
        f"produce a concise outbreak alert.\n\n"
        f"Hospital report: {json.dumps(hospital_result)}\n"
        f"OSINT headlines: {json.dumps(osint_result)}\n\n"
        f"Output a JSON object with keys: alert_level (green/yellow/orange/red), "
        f"summary (2-3 sentences), recommended_actions (list of strings)."
    )
    llm_answer = await llm_chat(prompt)

    # Try to parse LLM JSON; wrap raw string otherwise
    try:
        alert = json.loads(llm_answer)
    except Exception:
        alert = {
            "alert_level": "yellow",
            "summary": llm_answer,
            "recommended_actions": ["Review raw LLM output"],
        }

    result = {
        "task_id": task_id,
        "status": "completed",
        "pathogen": pathogen,
        "region": region,
        "hospital_data": hospital_result,
        "osint_data": osint_result,
        "alert": alert,
        "transport_used": "mqtt" if await mqtt_available(MQTT_BROKER, MQTT_PORT) else "http",
    }

    await bus.publish(task_id, SseEvent(event="status", data=json.dumps({"task_id": task_id, "status": "completed"})))
    await bus.publish(task_id, SseEvent(event="result", data=json.dumps(result)))
    return result


METHODS: dict[str, object] = {
    "tasks/sendSubscribe": _tasks_send_subscribe,
}

# ── JSON-RPC dispatcher ────────────────────────────────────────────
@app.post("/rpc")
async def rpc(request: Request):
    _require_auth(request)
    body = await request.body()
    parsed = parse_request(body)
    if "error" in parsed:
        return JSONResponse(parsed, status_code=400)

    method = parsed["method"]
    params = parsed.get("params", {})
    req_id = parsed.get("id")

    handler = METHODS.get(method)
    if not handler:
        return JSONResponse(response_error(req_id, METHOD_NOT_FOUND, f"Unknown method {method}"))

    try:
        result = await handler(params)
        return JSONResponse(response_result(req_id, result))
    except Exception as exc:
        return JSONResponse(response_error(req_id, INVALID_PARAMS, str(exc)))

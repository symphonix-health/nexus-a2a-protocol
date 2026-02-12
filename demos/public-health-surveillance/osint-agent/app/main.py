"""osint-agent – returns mock open-source intelligence headlines."""
from __future__ import annotations

import json
import os
import pathlib

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.ids import make_task_id
from shared.nexus_common.jsonrpc import (INVALID_PARAMS, METHOD_NOT_FOUND,
                                         parse_request, response_error,
                                         response_result)
from shared.nexus_common.sse import TaskEventBus

app = FastAPI(title="osint-agent")
bus = TaskEventBus()

AGENT_CARD = json.loads(
    (pathlib.Path(__file__).resolve().parent.parent / "agent_card.json").read_text()
)

JWT_SECRET = os.environ.get("NEXUS_JWT_SECRET", "super-secret-test-key-change-me")

# ── auth ────────────────────────────────────────────────────────────
def _require_auth(request: Request) -> dict:
    hdr = request.headers.get("Authorization", "")
    if not hdr.startswith("Bearer "):
        raise AuthError("Missing Bearer token")
    return verify_jwt(hdr.split(" ", 1)[1], JWT_SECRET)

# ── agent card ──────────────────────────────────────────────────────
@app.get("/.well-known/agent-card.json")
async def agent_card():
    return JSONResponse(AGENT_CARD)


@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy", "name": "osint-agent"})

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

# ── RPC methods ─────────────────────────────────────────────────────
_MOCK_HEADLINES = {
    "cholera": [
        "WHO reports cholera surge in Sub-Saharan Africa – 12 000 new cases this week",
        "Local authorities deploy oral cholera vaccines in flood-hit provinces",
        "NGO: Clean water access remains critical bottleneck",
    ],
    "measles": [
        "Measles outbreak in Northern Region – vaccination drive underway",
        "Health ministry confirms 800 measles cases among children under 5",
    ],
    "tuberculosis": [
        "TB remains leading infectious-disease killer in Southern Africa",
        "New rapid TB test approved by regulatory authority",
    ],
    "influenza": [
        "Seasonal flu admissions spike 30% above five-year average",
        "Updated influenza vaccine available at public clinics",
    ],
}

async def _osint_headlines(params: dict) -> dict:
    pathogen = params.get("pathogen", "cholera")
    headlines = _MOCK_HEADLINES.get(pathogen, [f"No OSINT data for {pathogen}"])
    return {
        "pathogen": pathogen,
        "source": "osint-agent-mock",
        "headlines": headlines,
    }

METHODS: dict[str, object] = {
    "osint/headlines": _osint_headlines,
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

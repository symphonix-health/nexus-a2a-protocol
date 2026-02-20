from __future__ import annotations

import base64
import json
import os
import struct
import wave
from io import BytesIO

from fastapi import (FastAPI, HTTPException, Request, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from shared.clinician_avatar.avatar_engine import AvatarEngine
from shared.clinician_avatar.avatar_protocol import (
    normalize_patient_message_params, normalize_start_session_params)
from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.jsonrpc import (JsonRpcError, parse_request,
                                         response_error, response_result)
from shared.nexus_common.sse import TaskEventBus

app = FastAPI(title="clinician-avatar-agent")
engine = AvatarEngine()
bus = TaskEventBus(agent_name="clinician-avatar-agent")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")


def _simple_viseme_timeline(text: str) -> list[dict[str, float | str]]:
    words = [w for w in text.split() if w.strip()]
    if not words:
        return [{"time_ms": 0.0, "viseme": "sil", "weight": 0.0}]

    timeline: list[dict[str, float | str]] = []
    t = 0.0
    for word in words:
        lower = word.lower()
        viseme = "AA"
        if any(ch in lower for ch in "fvm"):
            viseme = "FV"
        elif any(ch in lower for ch in "bp"):
            viseme = "PP"
        elif any(ch in lower for ch in "ou"):
            viseme = "OW"
        elif any(ch in lower for ch in "ei"):
            viseme = "EE"
        timeline.append({"time_ms": t, "viseme": viseme, "weight": 0.85})
        t += 160.0
    timeline.append({"time_ms": t + 120.0, "viseme": "sil", "weight": 0.0})
    return timeline


def _generate_tone_wav_b64(duration_seconds: float = 0.65, freq: float = 220.0) -> str:
    sample_rate = 16000
    n_samples = max(1, int(duration_seconds * sample_rate))
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            phase = (i / sample_rate) * freq * 6.283185307179586
            amp = int(8000 * (0.5 if (i // 60) % 2 == 0 else -0.5))
            wf.writeframes(struct.pack("<h", amp))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


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
async def agent_card() -> JSONResponse:
    path = os.path.join(os.path.dirname(__file__), "agent_card.json")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "healthy", "sessions": len(engine.sessions)})


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="avatar-static")


@app.get("/avatar")
async def avatar_page() -> FileResponse:
    html = os.path.join(STATIC_DIR, "avatar.html")
    if not os.path.isfile(html):
        raise HTTPException(status_code=404, detail="avatar UI not found")
    return FileResponse(html)


@app.post("/api/tts")
async def api_tts(request: Request) -> JSONResponse:
    _require_auth(request)
    payload = await request.json()
    text = str(payload.get("text") or "").strip()
    voice = str(payload.get("voice") or "alloy").strip()
    visemes = _simple_viseme_timeline(text)

    # Placeholder tone audio keeps API contract stable until full TTS wiring.
    audio_b64 = _generate_tone_wav_b64()
    return JSONResponse(
        content={
            "voice": voice,
            "mime_type": "audio/wav",
            "audio_b64": audio_b64,
            "visemes": visemes,
        }
    )


@app.get("/events/{task_id}")
async def events(task_id: str, request: Request) -> StreamingResponse:
    _require_auth(request)
    return StreamingResponse(bus.stream(task_id), media_type="text/event-stream")


@app.websocket("/ws/{task_id}")
async def ws_stream(websocket: WebSocket, task_id: str) -> None:
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


@app.post("/rpc")
async def rpc(request: Request) -> JSONResponse:
    _require_auth(request)
    payload = await request.json()
    try:
        req = parse_request(payload)
        method, params, id_ = req["method"], req["params"], req["id"]

        if method == "avatar/start_session":
            parsed = normalize_start_session_params(params)
            session = engine.start_session(parsed["patient_case"], parsed["persona"])
            result = {
                "session_id": session.session_id,
                "consultation_phase": session.consultation_phase,
                "framework": session.framework,
                "framework_progress": session.framework_progress,
                "greeting": session.conversation_history[-1]["content"],
            }
        elif method == "avatar/patient_message":
            parsed = normalize_patient_message_params(params)
            if not parsed["session_id"]:
                raise JsonRpcError(-32602, "Invalid params", "session_id is required")
            if not parsed["message"]:
                raise JsonRpcError(-32602, "Invalid params", "message is required")
            result = engine.handle_patient_message(parsed["session_id"], parsed["message"])
        elif method == "avatar/get_status":
            session_id = str(params.get("session_id") or "").strip()
            session = engine.get_session(session_id)
            if not session:
                raise JsonRpcError(-32602, "Invalid params", "unknown session_id")
            result = {
                "session_id": session.session_id,
                "consultation_phase": session.consultation_phase,
                "framework": session.framework,
                "framework_progress": session.framework_progress,
                "turns": len(session.conversation_history),
                "updated_at": session.updated_at,
            }
        elif method == "avatar/end_session":
            session_id = str(params.get("session_id") or "").strip()
            session = engine.sessions.pop(session_id, None)
            result = {
                "session_id": session_id,
                "ended": session is not None,
            }
        else:
            raise JsonRpcError(-32601, "Method not found", method)

        return JSONResponse(content=response_result(id_, result, method=method, params=params))
    except JsonRpcError as exc:
        return JSONResponse(content=response_error(payload.get("id"), exc), status_code=200)
    except Exception as exc:
        err = JsonRpcError(-32000, "Server error", str(exc))
        return JSONResponse(content=response_error(payload.get("id"), err), status_code=200)

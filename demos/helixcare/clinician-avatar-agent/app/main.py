from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from shared.clinician_avatar.avatar_engine import AvatarEngine
from shared.clinician_avatar.avatar_protocol import (
    normalize_patient_message_params,
    normalize_start_session_params,
)
from shared.clinician_avatar.video_clinician_provider import get_video_clinician_provider
from shared.nexus_common.auth import AuthError, verify_jwt
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.jsonrpc import JsonRpcError, parse_request, response_error, response_result
from shared.nexus_common.sse import TaskEventBus

app = FastAPI(title="clinician-avatar-agent")
engine = AvatarEngine()
video_provider = get_video_clinician_provider()
bus = TaskEventBus(agent_name="clinician-avatar-agent")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
live_ws_clients: set[WebSocket] = set()
live_ws_lock = asyncio.Lock()

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")


def _build_avatar_speech_payload(
    text: str,
    voice: str = "alloy",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_text = str(text or "").strip()
    rendered = video_provider.render(clean_text, voice=voice, context=context or {})
    speech = rendered.get("speech") if isinstance(rendered.get("speech"), dict) else {}
    speech.setdefault("voice", voice)
    speech.setdefault("mime_type", "audio/wav")
    speech.setdefault("audio_b64", "")
    speech.setdefault("text", clean_text)
    speech.setdefault("visemes", [])
    speech["provider"] = rendered.get(
        "provider",
        getattr(video_provider, "provider_id", "local_gpu"),
    )
    if isinstance(rendered.get("video"), dict):
        speech["video"] = rendered["video"]
    if "provider_status" in rendered:
        speech["provider_status"] = rendered["provider_status"]
    return speech


async def _broadcast_live_event(event: dict[str, Any]) -> None:
    async with live_ws_lock:
        clients = list(live_ws_clients)

    stale: list[WebSocket] = []
    for ws in clients:
        try:
            await ws.send_json(event)
        except Exception:
            stale.append(ws)

    if stale:
        async with live_ws_lock:
            for ws in stale:
                live_ws_clients.discard(ws)


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
    return JSONResponse(
        content={
            "status": "healthy",
            "sessions": len(engine.sessions),
            "video_provider": getattr(video_provider, "provider_id", "local_gpu"),
        }
    )


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
    return JSONResponse(
        content=_build_avatar_speech_payload(
            text,
            voice,
            context={"source": "api_tts"},
        )
    )


@app.get("/api/video-clinician/provider")
async def get_video_clinician_provider_info(request: Request) -> JSONResponse:
    _require_auth(request)
    configured = (
        str(os.getenv("VIDEO_CLINICIAN_PROVIDER", "local_gpu")).strip().lower()
        or "local_gpu"
    )
    return JSONResponse(
        content={
            "provider": getattr(video_provider, "provider_id", configured),
            "configured_provider": configured,
            "supported": ["local_gpu", "did", "sync"],
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


@app.websocket("/live/ws")
async def ws_live_avatar(websocket: WebSocket) -> None:
    await websocket.accept()
    async with live_ws_lock:
        live_ws_clients.add(websocket)
    try:
        await websocket.send_json(
            {
                "type": "avatar.live.connected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sessions": len(engine.sessions),
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with live_ws_lock:
            live_ws_clients.discard(websocket)


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
            await _broadcast_live_event(
                {
                    "type": "avatar.session_started",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "session_id": session.session_id,
                    "persona": parsed.get("persona", ""),
                    "patient_case": parsed.get("patient_case", {}),
                    "greeting": result["greeting"],
                    "framework": session.framework,
                    "framework_progress": session.framework_progress,
                    "speech": _build_avatar_speech_payload(
                        result["greeting"],
                        context={
                            "source": "avatar.start_session",
                            "session_id": session.session_id,
                            "patient_case": parsed.get("patient_case", {}),
                            "persona": parsed.get("persona", {}),
                        },
                    ),
                }
            )
        elif method == "avatar/patient_message":
            parsed = normalize_patient_message_params(params)
            if not parsed["session_id"]:
                raise JsonRpcError(-32602, "Invalid params", "session_id is required")
            if not parsed["message"]:
                raise JsonRpcError(-32602, "Invalid params", "message is required")
            result = engine.handle_patient_message(parsed["session_id"], parsed["message"])
            clinician_response = str(
                result.get("clinician_response")
                or result.get("response")
                or result.get("message")
                or ""
            ).strip()
            await _broadcast_live_event(
                {
                    "type": "avatar.patient_message",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "session_id": parsed["session_id"],
                    "patient_message": parsed["message"],
                    "clinician_response": clinician_response,
                    "framework_progress": result.get("framework_progress", {}),
                    "raw_result": result,
                    "speech": _build_avatar_speech_payload(
                        clinician_response,
                        context={
                            "source": "avatar.patient_message",
                            "session_id": parsed["session_id"],
                            "patient_message": parsed["message"],
                            "framework_progress": result.get("framework_progress", {}),
                        },
                    ),
                }
            )
        elif method == "avatar/get_status":
            session_id = str(params.get("session_id") or "").strip()
            found = engine.get_session(session_id)
            if not found:
                raise JsonRpcError(-32602, "Invalid params", "unknown session_id")
            result = {
                "session_id": found.session_id,
                "consultation_phase": found.consultation_phase,
                "framework": found.framework,
                "framework_progress": found.framework_progress,
                "turns": len(found.conversation_history),
                "updated_at": found.updated_at,
            }
        elif method == "avatar/end_session":
            session_id = str(params.get("session_id") or "").strip()
            ended = engine.sessions.pop(session_id, None) is not None
            result = {
                "session_id": session_id,
                "ended": ended,
            }
        else:
            raise JsonRpcError(-32601, "Method not found", method)

        return JSONResponse(content=response_result(id_, result, method=method, params=params))
    except JsonRpcError as exc:
        return JSONResponse(content=response_error(payload.get("id"), exc), status_code=200)
    except Exception as exc:  # noqa: BLE001
        err = JsonRpcError(-32000, "Server error", str(exc))
        return JSONResponse(content=response_error(payload.get("id"), err), status_code=200)

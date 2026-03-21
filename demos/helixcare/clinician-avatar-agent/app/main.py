from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import (FastAPI, File, Form, HTTPException, Request, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.responses import (FileResponse, JSONResponse, Response,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles

from shared.clinician_avatar.avatar_engine import AvatarEngine
from shared.clinician_avatar.avatar_protocol import (
    normalize_patient_message_params, normalize_start_session_params)
from shared.clinician_avatar.video_clinician_provider import (
    get_video_clinician_provider, has_openai_tts, simple_viseme_timeline,
    stream_tts_chunks)
from shared.nexus_common.auth import AuthError, mint_jwt, verify_jwt
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.identity import (get_agent_identity,
                                          get_persona_registry)
from shared.nexus_common.jsonrpc import (JsonRpcError, parse_request,
                                         response_error, response_result)
from shared.nexus_common.sse import TaskEventBus


@contextlib.asynccontextmanager
async def _lifespan(application: FastAPI):
    engine.start_reaper()
    yield


app = FastAPI(title="clinician-avatar-agent", lifespan=_lifespan)
engine = AvatarEngine()
video_provider = get_video_clinician_provider()
bus = TaskEventBus(agent_name="clinician-avatar-agent")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
# Avatar reference media lives in the repo-root avatar/ directory
AVATAR_MEDIA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "avatar")
)
live_ws_clients: set[WebSocket] = set()
live_ws_lock = asyncio.Lock()

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")


def _build_live_speech_payload(text: str) -> dict[str, Any]:
    """Lightweight speech payload for live-broadcast events.

    Does NOT make any external API calls — audio is omitted intentionally so that
    live-mode viewers use the same WebSocket TTS stream as interactive users.
    Only the viseme timeline (pre-computed, word-level) and text are included.
    """
    clean_text = str(text or "").strip()
    return {
        "text": clean_text,
        "voice": "nova",
        "mime_type": "audio/wav",
        "audio_b64": "",  # empty — live clients use /api/tts/stream WebSocket
        "visemes": simple_viseme_timeline(clean_text),
        "provider": getattr(video_provider, "provider_id", "local_gpu"),
    }


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


@app.get("/media/{filename:path}")
async def avatar_media(filename: str) -> FileResponse:
    """Serve reference avatar media (video/images) from the repo avatar/ directory."""
    # Prevent path traversal: only allow the basename
    safe = os.path.basename(filename)
    path = os.path.join(AVATAR_MEDIA_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Media not found: {safe}")
    return FileResponse(path)


DEV_SECRET = "dev-secret-change-me"


@app.get("/dev/token")
async def dev_token() -> JSONResponse:
    """Return a fresh short-lived JWT for browser-based development and demos.

    Only works when NEXUS_JWT_SECRET is the default placeholder value.
    Returns 403 if a custom secret is configured (i.e. production environment).
    """
    if JWT_SECRET != DEV_SECRET:
        raise HTTPException(status_code=403, detail="Dev token endpoint disabled in production")
    token = mint_jwt(subject="dev-browser", secret=JWT_SECRET, ttl_seconds=3600)
    return JSONResponse(content={"token": token, "expires_in": 3600})


@app.get("/.well-known/agent-card.json")
async def agent_card() -> JSONResponse:
    path = os.path.join(os.path.dirname(__file__), "agent_card.json")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))


@app.get("/health")
async def health() -> JSONResponse:
    try:
        identity = get_agent_identity("clinician_avatar_agent")
        persona = identity.primary_persona
        identity_info = {
            "persona_id": persona.persona_id,
            "persona_name": persona.name,
            "bulletrain_role": persona.bulletrain_role,
            "iam_groups": identity.iam_groups,
        }
    except Exception:  # noqa: BLE001
        identity_info = {}
    persona_display = identity_info.get("persona_name") or "Consultant Physician"
    return JSONResponse(
        content={
            "status": "healthy",
            "name": persona_display,
            "sessions": len(engine.sessions),
            "video_provider": getattr(video_provider, "provider_id", "local_gpu"),
            "has_tts": has_openai_tts(),
            "identity": identity_info,
        }
    )


@app.get("/api/identity")
async def get_identity(request: Request) -> JSONResponse:
    """Return this agent's persona and IAM configuration."""
    _require_auth(request)
    identity = get_agent_identity("clinician_avatar_agent")
    persona = identity.primary_persona
    return JSONResponse(
        content={
            "agent_id": identity.agent_id,
            "primary_persona": persona.to_avatar_dict(),
            "alternate_personas": {
                k: get_persona_registry().get(v).to_avatar_dict()
                for k, v in identity.alternate_persona_ids.items()
                if get_persona_registry().get(v)
            },
            "iam_groups": identity.iam_groups,
            "delegated_scopes": identity.delegated_scopes,
            "can_delegate_to": identity.can_delegate_to,
            "autonomous_actions": identity.autonomous_actions,
            "communication_permissions": {
                "send_sms": identity.can_send_sms,
                "send_email": identity.can_send_email,
                "receive_sms": identity.can_receive_sms,
                "receive_email": identity.can_receive_email,
            },
        }
    )


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


class _NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers.update(_NO_CACHE_HEADERS)
        return response


if os.path.isdir(STATIC_DIR):
    app.mount("/static", _NoCacheStaticFiles(directory=STATIC_DIR), name="avatar-static")


@app.get("/avatar")
async def avatar_page() -> FileResponse:
    html = os.path.join(STATIC_DIR, "avatar.html")
    if not os.path.isfile(html):
        raise HTTPException(status_code=404, detail="avatar UI not found")
    response = FileResponse(html)
    response.headers.update(_NO_CACHE_HEADERS)
    return response


@app.post("/api/tts")
async def api_tts(request: Request) -> JSONResponse:
    _require_auth(request)
    payload = await request.json()
    text = str(payload.get("text") or "").strip()
    voice = str(payload.get("voice") or "nova").strip()
    return JSONResponse(content=_build_live_speech_payload(text))


@app.post("/api/stt/upload")
async def api_stt_upload(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("en"),
) -> JSONResponse:
    """Transcribe uploaded patient audio clips via OpenAI Speech-to-Text."""
    _require_auth(request)

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured. Set it to enable uploaded-audio transcription.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded audio file is too large (max 20 MB).")

    model = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
    try:
        from openai import OpenAI

        client = OpenAI()
        audio_buf = io.BytesIO(content)
        audio_buf.name = file.filename or "patient_audio.wav"
        req_kwargs: dict[str, Any] = {
            "model": model,
            "file": audio_buf,
        }
        clean_language = str(language or "").strip()
        if clean_language:
            req_kwargs["language"] = clean_language
        transcript = client.audio.transcriptions.create(**req_kwargs)
        text = str(getattr(transcript, "text", "") or "").strip()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Failed to transcribe uploaded audio: {exc}"
        ) from exc

    if not text:
        raise HTTPException(
            status_code=502, detail="Transcription completed but returned empty text."
        )

    return JSONResponse(
        content={
            "transcript": text,
            "model": model,
            "filename": file.filename or "patient_audio.wav",
        }
    )


# ── OpenAI Realtime API — ephemeral key minting ───────────────────────────
_OPENAI_REALTIME_MODEL = os.getenv(
    "OPENAI_REALTIME_MODEL", "gpt-4o-mini-realtime-preview"
)


@app.post("/api/realtime/token")
async def api_realtime_token(request: Request) -> JSONResponse:
    """Mint an ephemeral client secret for the OpenAI Realtime API.

    The browser uses this short-lived key to establish a direct WebRTC
    connection with OpenAI — audio flows peer-to-peer afterwards.

    Request JSON (optional):  { "voice": "coral" }
    Response JSON: same shape as OpenAI ``/v1/realtime/client_secrets``
    """
    import httpx

    # ── Auth ────────────────────────────────────────────────────────────────
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
    except AuthError:
        raise HTTPException(status_code=401, detail="Unauthorized")

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY not configured — Realtime API unavailable",
        )

    body = {}
    with contextlib.suppress(Exception):
        body = await request.json()
    voice = body.get("voice", "coral")

    # ── Call OpenAI to mint ephemeral key ───────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.openai.com/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _OPENAI_REALTIME_MODEL,
                    "voice": voice,
                },
            )
            resp.raise_for_status()
            return JSONResponse(content=resp.json())
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response else str(exc)
        raise HTTPException(status_code=502, detail=f"OpenAI error: {detail}")
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach OpenAI Realtime API: {exc}",
        )


@app.websocket("/api/tts/stream")
async def api_tts_stream(websocket: WebSocket) -> None:
    """Streaming TTS over WebSocket.

    Protocol:
      Client → Server (JSON text):  {"type": "speak", "text": "...", "voice": "alloy"}
      Client → Server (JSON text):  {"type": "cancel"}
      Server → Client (JSON text):  {"type": "meta", "sample_rate": 24000, "channels": 1,
                                    "format": "pcm_s16le"}
      Server → Client (JSON text):  {"type": "visemes", "visemes": [...]}
      Server → Client (binary):     raw PCM chunks (24 kHz, 16-bit, mono, little-endian)
      Server → Client (JSON text):  {"type": "end"}
    """
    token = websocket.query_params.get("token", "")
    try:
        verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
    except AuthError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    speak_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    cancel_event = asyncio.Event()

    async def _dispatch() -> None:
        """Route all inbound WebSocket messages."""
        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if msg.get("type") == "cancel":
                    cancel_event.set()
                elif msg.get("type") == "speak":
                    await speak_queue.put(msg)
        except WebSocketDisconnect:
            await speak_queue.put(None)
        except Exception:
            await speak_queue.put(None)

    dispatch_task = asyncio.create_task(_dispatch())
    try:
        while True:
            msg = await speak_queue.get()
            if msg is None:
                break

            text = str(msg.get("text") or "").strip()
            voice = str(msg.get("voice") or "ash").strip() or "ash"
            instructions = str(msg.get("instructions") or "").strip() or None
            if not text:
                continue

            cancel_event.clear()

            _real_tts = has_openai_tts()
            if not _real_tts:
                # Hard-fail — no silent browser fallback; surface a visible error
                await websocket.send_json(
                    {
                        "type": "tts_error",
                        "message": "OPENAI_API_KEY is not configured on this server. Set it to enable speech.",
                    }
                )
                await websocket.send_json({"type": "end"})
                continue

            await websocket.send_json(
                {
                    "type": "meta",
                    "sample_rate": 24000,
                    "channels": 1,
                    "format": "pcm_s16le",
                }
            )
            await websocket.send_json({"type": "visemes", "visemes": simple_viseme_timeline(text)})

            pcm_sent = False
            try:
                async for chunk in stream_tts_chunks(text, voice, instructions=instructions):
                    if cancel_event.is_set():
                        break
                    await websocket.send_bytes(chunk)
                    pcm_sent = True
            except Exception:  # noqa: BLE001
                pass
            if not pcm_sent and not cancel_event.is_set():
                # API key was set but no audio came through — surface a visible error
                await websocket.send_json(
                    {
                        "type": "tts_error",
                        "message": "TTS synthesis failed — OpenAI returned no audio. Check your API key and quota.",
                    }
                )

            if not cancel_event.is_set():
                await websocket.send_json({"type": "end"})
    except WebSocketDisconnect:
        pass
    finally:
        dispatch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dispatch_task


@app.post("/api/patient/respond")
async def api_patient_respond(request: Request) -> JSONResponse:
    """Generate an AI-driven patient response to the clinician's last message.

    Accepts JSON:
      {
        "clinician_message": str,          # the clinician's last spoken line
        "patient_context": {               # persona loaded from patient_script_pack.json
          "name": str,
          "age": int | str,
          "gender": str,
          "chief_complaint": str,
          "medical_history": str,
          "medications": str,
          "allergies": str,
          "family_history": str,
          "social_history": str
        },
        "conversation_history": [          # last N {"role": "...", "content": "..."} turns
          {"role": "assistant", "content": "..."},
          {"role": "user",      "content": "..."}
        ]
      }

    Returns: {"patient_response": str}
    """
    _require_auth(request)

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured. Set it to enable AI patient responses.",
        )

    body = await request.json()
    clinician_message = str(body.get("clinician_message") or "").strip()
    patient_context = body.get("patient_context") or {}
    raw_history = body.get("conversation_history") or []

    if not clinician_message:
        raise HTTPException(status_code=400, detail="clinician_message is required")

    # Build patient persona description
    name = str(patient_context.get("name") or "the patient")
    age = str(patient_context.get("age") or "adult")
    gender = str(patient_context.get("gender") or "person")
    chief_complaint = str(patient_context.get("chief_complaint") or "")
    medical_history = str(patient_context.get("medical_history") or "not disclosed")
    medications = str(patient_context.get("medications") or "none known")
    allergies = str(patient_context.get("allergies") or "none known")
    family_history = str(patient_context.get("family_history") or "not disclosed")
    social_history = str(patient_context.get("social_history") or "not disclosed")

    system_prompt = f"""You are roleplaying as a real patient in a medical consultation.

Patient profile:
- Name: {name}
- Age: {age}, {gender}
- Chief complaint: {chief_complaint}
- Medical history: {medical_history}
- Current medications: {medications}
- Allergies: {allergies}
- Family history: {family_history}
- Social history: {social_history}

Behaviour rules:
1. Respond ONLY to what the clinician just asked. Do not volunteer information unprompted.
2. Reveal medical history, medications, and family history only when directly asked.
3. Keep responses to 1-3 sentences — patients do not speak in bullet points.
4. Show realistic emotion: anxiety about serious symptoms, relief at reassurance, confusion at medical jargon.
5. Use natural spoken English, not clinical terminology. You are not a doctor.
6. Never break character. Never describe what you are doing (e.g. do not say "As a patient...").
7. If asked something you would not realistically know, say so naturally.
"""

    # Cap history at 10 turns to control token spend
    capped_history = raw_history[-10:] if len(raw_history) > 10 else raw_history
    history_text = ""
    for turn in capped_history:
        role = str(turn.get("role") or "")
        content = str(turn.get("content") or "")
        if role == "assistant":
            history_text += f"Clinician: {content}\n"
        elif role == "user":
            history_text += f"Patient: {content}\n"

    user_prompt = f"{history_text}Clinician: {clinician_message}\nPatient:"

    try:
        from shared.nexus_common.openai_helper import llm_chat

        response_text = await asyncio.to_thread(
            llm_chat,
            system_prompt,
            user_prompt,
            temperature=0.85,
            top_p=0.95,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"AI patient response generation failed: {exc}",
        ) from exc

    patient_response = str(response_text or "").strip()
    # Strip any accidental "Patient:" prefix the LLM may produce
    if patient_response.lower().startswith("patient:"):
        patient_response = patient_response[len("patient:") :].strip()

    if not patient_response:
        raise HTTPException(status_code=502, detail="AI model returned an empty patient response.")

    return JSONResponse(content={"patient_response": patient_response})


@app.get("/api/video-clinician/provider")
async def get_video_clinician_provider_info(request: Request) -> JSONResponse:
    _require_auth(request)
    configured = (
        str(os.getenv("VIDEO_CLINICIAN_PROVIDER", "local_gpu")).strip().lower() or "local_gpu"
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

        if method == "avatar/list_personas":
            registry = get_persona_registry()
            country = str(params.get("country") or "").strip().lower()
            domain = str(params.get("domain") or "clinical").strip().lower()
            personas = registry.filter(country=country or None, domain=domain or None)
            result = [p.to_avatar_dict() for p in personas]
            return JSONResponse(content=response_result(id_, result, method=method, params=params))

        elif method == "avatar/start_session":
            parsed = normalize_start_session_params(params)

            # Resolve persona: explicit persona_id > country lookup > inline dict > default
            resolved_persona = parsed["persona"]
            registry = get_persona_registry()
            if parsed.get("persona_id"):
                p = registry.get(parsed["persona_id"])
                if p:
                    resolved_persona = p.to_avatar_dict()
            elif not resolved_persona and (parsed.get("country") or parsed.get("care_setting")):
                identity = get_agent_identity("clinician_avatar_agent")
                p = identity.persona_for_scenario(
                    country=parsed.get("country") or "uk",
                    care_setting=parsed.get("care_setting") or "",
                )
                resolved_persona = p.to_avatar_dict()
            elif not resolved_persona:
                # Default to the avatar agent's primary persona (Consultant Physician)
                identity = get_agent_identity("clinician_avatar_agent")
                resolved_persona = identity.primary_persona.to_avatar_dict()

            session = engine.start_session(
                parsed["patient_case"],
                resolved_persona,
                llm_config=parsed.get("llm_config"),
            )
            result = {
                "session_id": session.session_id,
                "consultation_phase": session.consultation_phase,
                "framework": session.framework,
                "framework_progress": session.framework_progress,
                "llm_config": session.llm_config,
                "greeting": session.conversation_history[-1]["content"],
                "persona": resolved_persona,
            }
            await _broadcast_live_event(
                {
                    "type": "avatar.session_started",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "session_id": session.session_id,
                    "persona": resolved_persona,
                    "patient_case": parsed.get("patient_case", {}),
                    "greeting": result["greeting"],
                    "framework": session.framework,
                    "framework_progress": session.framework_progress,
                    "speech": _build_live_speech_payload(result["greeting"]),
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
                    "speech": _build_live_speech_payload(clinician_response),
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

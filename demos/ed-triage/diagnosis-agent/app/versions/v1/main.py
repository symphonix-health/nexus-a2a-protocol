from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.a2a_http import (
    canonicalize_payload_method,
    negotiate_http_request,
    response_headers as a2a_response_headers,
)
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.health import HealthMonitor
from shared.nexus_common.http_client import jsonrpc_call
from shared.nexus_common.ids import make_task_id, make_trace_id
from shared.nexus_common.jsonrpc import JsonRpcError, parse_request, response_error, response_result
from shared.nexus_common.openai_helper import llm_chat
from shared.nexus_common.otel import start_span
from shared.nexus_common.service_auth import AuthError, extract_bearer_token, verify_service_auth
from shared.nexus_common.sse import TaskEventBus
from shared.nexus_common.trace_context import build_traceparent, extract_trace_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.diagnosis-agent")

@contextlib.asynccontextmanager
async def _lifespan(application: FastAPI):
    yield
    await bus.close()


app = FastAPI(title="diagnosis-agent", lifespan=_lifespan)
bus = TaskEventBus(agent_name="diagnosis-agent")
health_monitor = HealthMonitor("diagnosis-agent")

REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
_CONCURRENCY_LIMIT = int(os.getenv("NEXUS_DIAGNOSIS_MAX_CONCURRENCY", "10"))
_semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)


def _require_auth(req: Request) -> str:
    try:
        token = extract_bearer_token(req.headers.get("authorization", ""))
        verify_service_auth(
            token,
            headers=req.headers,
            required_scope=REQUIRED_SCOPE,
        )
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
    return JSONResponse(
        content=health_monitor.get_health(
            bus_stats=bus.get_stats()
        )
    )


@app.get("/events/{task_id}")
async def events(task_id: str, request: Request):
    _require_auth(request)
    return StreamingResponse(bus.stream(task_id), media_type="text/event-stream")


@app.websocket("/ws/{task_id}")
async def ws_stream(websocket: WebSocket, task_id: str):
    token = websocket.query_params.get("token", "")
    try:
        verify_service_auth(
            token,
            headers=websocket.headers,
            required_scope=REQUIRED_SCOPE,
        )
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


def _extract_patient_context(task: dict) -> tuple[str, str]:
    patient = task.get("patient") if isinstance(task.get("patient"), dict) else {}
    patient_id = str(patient.get("patient_id") or "").strip()
    patient_ref = str(task.get("patient_ref") or "").strip()
    if patient_ref:
        if not patient_id:
            patient_id = patient_ref.split("/")[-1]
        return patient_id or "unknown", patient_ref
    if patient_id:
        return patient_id, f"Patient/{patient_id}"
    return "unknown", "Patient/unknown"


def _derive_triage_level(task: dict) -> str:
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


async def _do_assess(params: dict, token: str) -> dict:
    task = params.get("task") if isinstance(params.get("task"), dict) else {}
    patient_id, patient_ref = _extract_patient_context(task)

    openhie = os.getenv("NEXUS_OPENHIE_RPC", "http://openhie-mediator:8023/rpc")
    try:
        ctx = await jsonrpc_call(
            openhie,
            token,
            "fhir/get",
            {"patient_ref": patient_ref},
            f"{params.get('task_id', 'diag')}-fhir",
        )
        patient_context = ctx.get("result", {}) if isinstance(ctx, dict) else {}
    except Exception as exc:
        logger.warning("FHIR context lookup failed: %s", exc)
        patient_context = {"patient": {}, "allergies": {}}

    triage_level = _derive_triage_level(task)
    chief = str(task.get("chief_complaint") or (task.get("inputs") or {}).get("chief_complaint", "")).strip()

    system = "You are a cautious ED triage support assistant. Return a one sentence rationale."
    user = f"Complaint: {chief}; triage={triage_level}; patient_id={patient_id}."
    rationale = await asyncio.to_thread(llm_chat, system, user)

    # Compact patient_context for event replay — full FHIR data
    # was only needed for the LLM call above.
    compact_context = {
        "patient_id": patient_id,
        "has_allergies": bool(
            patient_context.get("allergies")
        ),
    }

    return {
        "task_id": params.get("task_id"),
        "patient_id": patient_id,
        "patient_ref": patient_ref,
        "triage_level": triage_level,
        "triage_priority": "EMERGENCY" if triage_level == "ESI-2" else "URGENT",
        "rationale": rationale,
        "patient_context": compact_context,
    }


async def _assess(params: dict, token: str) -> dict:
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


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()

    await bus.publish(
        task_id,
        "nexus.task.status",
        json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}),
    )

    async def run() -> None:
        async with _semaphore:
            try:
                await bus.publish(
                    task_id,
                    "nexus.task.status",
                    json.dumps({"task_id": task_id, "state": "working", "step": "diagnosing"}),
                )
                result = await _do_assess({"task": params.get("task", {}), "task_id": task_id}, token)
                duration_ms = (asyncio.get_event_loop().time() - t0) * 1000
                health_monitor.metrics.record_completed(duration_ms)
                await bus.publish(task_id, "nexus.task.final", json.dumps(result), duration_ms)
                logger.info("[%s] task=%s COMPLETED", trace_id, task_id)
            except Exception as exc:
                duration_ms = (asyncio.get_event_loop().time() - t0) * 1000
                health_monitor.metrics.record_error(duration_ms)
                await bus.publish(
                    task_id,
                    "nexus.task.error",
                    json.dumps({"task_id": task_id, "error": str(exc)}),
                    duration_ms,
                )
                logger.exception("[%s] task=%s FAILED", trace_id, task_id)

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id, "resume_cursor": bus.build_resume_cursor(task_id)}


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


async def _tasks_resubscribe(params: dict, token: str) -> dict:
    cursor = params.get("cursor")
    max_catchup_events = params.get("max_catchup_events")
    try:
        task_id, replay = bus.replay_from_cursor(
            str(cursor),
            max_events=max_catchup_events,
        )
    except Exception as exc:
        raise JsonRpcError(
            -32002,
            "Task not found",
            {
                "reason": "invalid_or_stale_cursor",
                "field": "cursor",
                "detail": str(exc),
                "failure_domain": "validation",
            },
        ) from exc
    return {
        "task_id": task_id,
        "replayed_count": len(replay),
        "replayed_events": replay,
        "resume_cursor": bus.build_resume_cursor(task_id),
    }


METHODS["diagnosis/assess"] = _assess
METHODS["tasks/sendSubscribe"] = _send_subscribe
METHODS["tasks/send"] = _send_subscribe
METHODS["tasks/get"] = _tasks_get
METHODS["tasks/cancel"] = _tasks_cancel
METHODS["tasks/resubscribe"] = _tasks_resubscribe


@app.post("/rpc")
async def rpc(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        negotiation = negotiate_http_request(request, payload)
    except HTTPException as exc:
        err = JsonRpcError(
            -32600,
            "Invalid Request",
            exc.detail if isinstance(exc.detail, dict) else {"reason": "invalid_negotiation"},
        )
        return JSONResponse(
            content=response_error(payload.get("id"), err),
            status_code=exc.status_code,
            media_type="application/a2a+json",
        )
    payload = canonicalize_payload_method(payload, negotiation)
    traceparent_in, tracestate_in = extract_trace_context(request.headers)
    response_traceparent = traceparent_in
    try:
        try:
            token = _require_auth(request)
        except HTTPException as exc:
            if not response_traceparent:
                response_traceparent = build_traceparent(str(payload.get("id") or "auth"))
            return JSONResponse(
                content=response_error(
                    payload.get("id"),
                    JsonRpcError(
                        -32001,
                        "Unauthorized",
                        {
                            "reason": "auth_failed",
                            "detail": str(exc.detail),
                            "failure_domain": "auth",
                        },
                    ),
                ),
                status_code=exc.status_code,
                media_type=negotiation.response_media_type,
                headers=a2a_response_headers(
                    negotiation,
                    traceparent=response_traceparent,
                    tracestate=tracestate_in,
                ),
            )
        with start_span("nexus.rpc.handle", {"agent": "diagnosis-agent"}):
            req = parse_request(payload)
            method, params, id_ = req["method"], req["params"], req["id"]

            if traceparent_in or tracestate_in:
                corr = params.get("correlation") if isinstance(params.get("correlation"), dict) else {}
                corr = dict(corr)
                if traceparent_in and "traceparent" not in corr:
                    corr["traceparent"] = traceparent_in
                if tracestate_in and "tracestate" not in corr:
                    corr["tracestate"] = tracestate_in
                if corr:
                    params["correlation"] = corr

            if method not in METHODS:
                raise JsonRpcError(-32601, "Method not found", method)
            result = await METHODS[method](params, token)

            if negotiation.compatibility_mode and isinstance(result, dict):
                result = dict(result)
                compat = (
                    result.get("compatibility")
                    if isinstance(result.get("compatibility"), dict)
                    else {}
                )
                compat = dict(compat)
                compat["legacy_method"] = negotiation.original_method
                compat["canonical_method"] = negotiation.canonical_method
                compat["mode"] = negotiation.compatibility_mode
                result["compatibility"] = compat

            if not response_traceparent:
                response_traceparent = build_traceparent(str(result.get("trace_id") if isinstance(result, dict) else id_))

            return JSONResponse(
                content=response_result(id_, result, method=method, params=params),
                status_code=200,
                media_type=negotiation.response_media_type,
                headers=a2a_response_headers(
                    negotiation,
                    traceparent=response_traceparent,
                    tracestate=tracestate_in,
                ),
            )
    except JsonRpcError as exc:
        if not response_traceparent:
            response_traceparent = build_traceparent(str(payload.get("id")))
        return JSONResponse(
            content=response_error(payload.get("id"), exc),
            status_code=200,
            media_type=negotiation.response_media_type,
            headers=a2a_response_headers(
                negotiation,
                traceparent=response_traceparent,
                tracestate=tracestate_in,
            ),
        )
    except Exception as exc:
        err = JsonRpcError(-32000, "Server error", str(exc))
        if not response_traceparent:
            response_traceparent = build_traceparent(str(payload.get("id")))
        return JSONResponse(
            content=response_error(payload.get("id"), err),
            status_code=200,
            media_type=negotiation.response_media_type,
            headers=a2a_response_headers(
                negotiation,
                traceparent=response_traceparent,
                tracestate=tracestate_in,
            ),
        )



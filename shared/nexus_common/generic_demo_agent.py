"""Generic startup-safe demo agent runtime for corrupted demo entrypoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from inspect import isawaitable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from .a2a_http import (
    canonicalize_payload_method,
    negotiate_http_request,
    response_headers as a2a_response_headers,
)
from .authorization import AuthorizationError, authorize_rpc_request
from .did import did_verify_enabled, verify_did_signature
from .health import HealthMonitor, apply_backpressure_to_agent_card
from .ids import make_task_id, make_trace_id
from .idempotency import IdempotencyStore, RedisIdempotencyStore
from .jsonrpc import JsonRpcError, parse_request, response_error, response_result
from .llm_agent_handler import try_llm_result
from .otel import start_span
from .service_auth import AuthError, extract_bearer_token, verify_service_auth
from .sse import TaskEventBus
from .trace_context import build_traceparent, extract_trace_context

LOGGER = logging.getLogger("nexus.generic-demo-agent")


def _extract_patient_id(task: dict[str, Any]) -> str:
    patient = task.get("patient") if isinstance(task.get("patient"), dict) else {}
    patient_id = patient.get("patient_id")
    if patient_id:
        return str(patient_id)
    patient_ref = task.get("patient_ref") or task.get("subject")
    if isinstance(patient_ref, str) and patient_ref:
        return patient_ref.split("/")[-1]
    return "unknown"


def _build_common_result(
    method: str, params: dict[str, Any], task_id: str | None = None
) -> dict[str, Any]:
    task = params.get("task") if isinstance(params.get("task"), dict) else {}
    patient_id = _extract_patient_id(task)
    complaint = str(
        task.get("chief_complaint") or (task.get("inputs") or {}).get("chief_complaint", "")
    ).strip()
    result: dict[str, Any] = {
        "task_id": task_id or params.get("task_id"),
        "patient_id": patient_id,
        "method": method,
        "status": "ok",
        "triage_level": "ESI-3",
        "rationale": f"Processed by startup-safe generic handler for {method}.",
    }

    method_l = method.lower()
    if "chest" in complaint.lower() or "shortness of breath" in complaint.lower():
        result["triage_level"] = "ESI-2"

    if method_l == "fhir/get" or "fhir/" in method_l:
        result = {"patient": {}, "allergies": {}, "task_id": task_id or params.get("task_id")}
    elif "osint" in method_l:
        result.update(
            {
                "headlines": ["No critical OSINT signals detected in startup-safe mode."],
                "source": "generic-demo-agent",
            }
        )
    elif "consent" in method_l:
        result.update({"allowed": True, "reason": "Startup-safe default allow."})
    elif "ehr/save" == method_l:
        result = {"saved": True, "task_id": task_id or params.get("task_id")}
    elif "ehr/getlatestnote" == method_l:
        result = {
            "found": True,
            "created_at": "1970-01-01T00:00:00Z",
            "note_markdown": "# Startup-safe note\nNo data available.",
            "task_id": task_id or params.get("task_id"),
        }
    elif "diagnosis" in method_l:
        result.update({"triage_priority": "URGENT", "diagnosis": "undifferentiated"})
    elif "imaging" in method_l:
        result.update({"imaging_status": "pending_review", "finding": "none_critical"})
    elif "pharmacy" in method_l:
        result.update({"medication_plan": [], "interaction_alerts": []})
    elif "bed" in method_l or "admission" in method_l:
        result.update({"bed_assigned": "pending", "admission_status": "queued"})
    elif "discharge" in method_l:
        result.update({"discharge_ready": False, "discharge_summary": "pending"})
    elif "followup" in method_l:
        result.update({"followup_scheduled": False, "followup_window": "pending"})
    elif "summary" in method_l or "summaris" in method_l:
        result.update({"note_markdown": "# Summary\nStartup-safe placeholder."})
    elif "transcrib" in method_l:
        result.update({"transcript": "Startup-safe placeholder transcript."})

    return result


def build_generic_demo_app(*, default_name: str, app_dir: str) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    bus = TaskEventBus(agent_name=default_name)
    health_monitor = HealthMonitor(default_name)
    inflight_tasks = 0

    @asynccontextmanager
    async def _lifespan(application: FastAPI):  # noqa: ARG001
        yield
        close_method = getattr(idempotency_store, "close", None)
        if callable(close_method):
            result = close_method()
            if isawaitable(result):
                await result
        await bus.close()

    app = FastAPI(title=default_name, lifespan=_lifespan)

    required_scope = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    agent_id = os.getenv("NEXUS_AGENT_ID", default_name.strip().lower().replace("-", "_"))
    card_path = Path(app_dir) / "agent_card.json"

    def _build_idempotency_store() -> IdempotencyStore | RedisIdempotencyStore:
        backend = os.getenv("NEXUS_IDEMPOTENCY_BACKEND", "memory").strip().lower()
        if backend == "redis":
            try:
                return RedisIdempotencyStore(redis_url=os.getenv("REDIS_URL"))
            except Exception as exc:
                LOGGER.warning(
                    "Redis idempotency unavailable (%s); falling back to memory store",
                    exc,
                )
        return IdempotencyStore()

    idempotency_store = _build_idempotency_store()

    async def _idempotency_check_or_register(
        key: str,
        dedup_window_ms: int,
        *,
        scope: str | None,
        payload_hash: str | None,
    ) -> object:
        result = idempotency_store.check_or_register(
            key=key,
            dedup_window_ms=dedup_window_ms,
            scope=scope,
            payload_hash=payload_hash,
        )
        if isawaitable(result):
            return await result
        return result

    async def _idempotency_save_response(
        key: str,
        response: dict[str, Any],
        *,
        scope: str | None,
    ) -> None:
        result = idempotency_store.save_response(key=key, response=response, scope=scope)
        if isawaitable(result):
            await result

    def _build_result(
        method: str, params: dict[str, Any], task_id: str | None = None
    ) -> dict[str, Any]:
        """Build response payload with optional LLM enhancement.

        LLM enhancement is guarded in llm_agent_handler by env flag
        NEXUS_AGENT_LLM_ENABLED. If disabled/unavailable/error, this returns the
        deterministic startup-safe payload.
        """
        base = _build_common_result(method, params, task_id=task_id)
        llm_method_hint = f"{default_name}/{method}"
        llm_result = try_llm_result(llm_method_hint, params)
        if not isinstance(llm_result, dict):
            return base
        merged = dict(base)
        merged.update(llm_result)
        merged["rationale"] = f"Processed by LLM-enhanced generic handler for {default_name}."
        return merged

    def _load_card() -> dict[str, Any]:
        candidate_paths = [
            card_path,
            card_path.parent.parent / "agent_card.json",
        ]
        for candidate in candidate_paths:
            if not candidate.is_file():
                continue
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception as exc:
                LOGGER.warning("Failed to parse agent card at %s: %s", candidate, exc)
        return {
            "name": default_name,
            "protocol": "NEXUS-A2A",
            "protocolVersion": "1.0",
            "methods": [
                "tasks/send",
                "tasks/sendSubscribe",
                "tasks/get",
                "tasks/cancel",
                "tasks/resubscribe",
            ],
        }

    def _declared_methods() -> set[str]:
        card = _load_card()
        methods = card.get("methods", [])
        if not isinstance(methods, list):
            return {
                "tasks/send",
                "tasks/sendSubscribe",
                "tasks/get",
                "tasks/cancel",
                "tasks/resubscribe",
            }
        out = {m for m in methods if isinstance(m, str) and m}
        out.update(
            {
                "tasks/send",
                "tasks/sendSubscribe",
                "tasks/get",
                "tasks/cancel",
                "tasks/resubscribe",
            }
        )
        return out

    def _require_basic_auth(req: Request) -> str:
        try:
            token = extract_bearer_token(req.headers.get("authorization", ""))
            verify_service_auth(
                token,
                headers=req.headers,
                required_scope=required_scope,
            )
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if did_verify_enabled() and not verify_did_signature():
            raise HTTPException(status_code=401, detail="DID signature verification failed")
        return token

    def _authorize_rpc(req: Request, method: str, params: dict[str, Any]) -> str:
        try:
            authz = authorize_rpc_request(
                authorization_header=req.headers.get("authorization", ""),
                headers=req.headers,
                method=method,
                params=params,
                target_agent_id=agent_id,
                required_scope=required_scope,
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if did_verify_enabled() and not verify_did_signature():
            raise HTTPException(status_code=401, detail="DID signature verification failed")
        return authz.token

    @app.get("/.well-known/agent-card.json")
    async def agent_card() -> JSONResponse:
        payload = _load_card()
        return JSONResponse(content=apply_backpressure_to_agent_card(payload, health_monitor))

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            content=health_monitor.get_health(
                bus_stats=bus.get_stats()
            )
        )

    @app.get("/events/{task_id}")
    async def events(task_id: str, request: Request) -> StreamingResponse:
        _require_basic_auth(request)
        return StreamingResponse(bus.stream(task_id), media_type="text/event-stream")

    @app.websocket("/ws/{task_id}")
    async def ws_stream(websocket: WebSocket, task_id: str) -> None:
        token = websocket.query_params.get("token", "")
        try:
            verify_service_auth(
                token,
                headers=websocket.headers,
                required_scope=required_scope,
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

    async def _tasks_send_subscribe(params: dict[str, Any], token: str) -> dict[str, Any]:
        nonlocal inflight_tasks
        correlation = (
            params.get("correlation") if isinstance(params.get("correlation"), dict) else {}
        )
        idempotency = (
            params.get("idempotency") if isinstance(params.get("idempotency"), dict) else {}
        )
        idempotency_key = str(idempotency.get("idempotency_key") or "").strip()
        scope = str(idempotency.get("scope") or "").strip() or None
        payload_hash = str(idempotency.get("payload_hash") or "").strip() or None
        dedup_window_ms = int(idempotency.get("dedup_window_ms", 60000)) if idempotency else 60000
        if dedup_window_ms <= 0:
            raise JsonRpcError(-32602, "Invalid params", "idempotency.dedup_window_ms must be > 0")
        max_dedup_window_ms = int(os.getenv("NEXUS_IDEMPOTENCY_MAX_DEDUP_WINDOW_MS", "900000"))
        if max_dedup_window_ms > 0:
            dedup_window_ms = min(dedup_window_ms, max_dedup_window_ms)
        if idempotency_key:
            dedup = await _idempotency_check_or_register(
                idempotency_key,
                dedup_window_ms,
                scope=scope,
                payload_hash=payload_hash,
            )
            if getattr(dedup, "is_duplicate", False) and getattr(dedup, "cached_response", None):
                duplicate_response = dict(dedup.cached_response)
                duplicate_response["dedup"] = {
                    "duplicate": True,
                    "idempotency_key": idempotency_key,
                    "scope": scope,
                    "dedup_window_ms": int(getattr(dedup, "dedup_window_ms", dedup_window_ms)),
                    "payload_mismatch": bool(getattr(dedup, "payload_mismatch", False)),
                }
                return duplicate_response
        scenario_context = (
            params.get("scenario_context")
            if isinstance(params.get("scenario_context"), dict)
            else {}
        )

        task_id = make_task_id()
        trace_id = str(correlation.get("trace_id") or make_trace_id())

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
        resume_cursor = bus.build_resume_cursor(task_id)

        async def run() -> None:
            nonlocal inflight_tasks
            try:
                await bus.publish(
                    task_id,
                    "nexus.task.status",
                    json.dumps({"task_id": task_id, "state": "working", "step": "generic_handler"}),
                    scenario_context=scenario_context or None,
                    correlation=correlation or None,
                    idempotency=idempotency or None,
                )
                final_payload = _build_result("tasks/sendSubscribe", params, task_id=task_id)
                duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                health_monitor.metrics.record_completed(duration_ms)
                await bus.publish(
                    task_id,
                    "nexus.task.final",
                    json.dumps(final_payload),
                    duration_ms,
                    scenario_context=scenario_context or None,
                    correlation=correlation or None,
                    idempotency=idempotency or None,
                )
            except Exception as exc:
                duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
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
        response = {
            "task_id": task_id,
            "trace_id": trace_id,
            "resume_cursor": resume_cursor,
            **_build_result("tasks/sendSubscribe", params, task_id=task_id),
        }
        if idempotency_key:
            await _idempotency_save_response(idempotency_key, response, scope=scope)
        return response

    async def _tasks_get(params: dict[str, Any], token: str) -> dict[str, Any]:
        task_id = params.get("task_id")
        if not task_id:
            raise JsonRpcError(-32602, "Invalid params", "task_id is required")
        health_monitor.metrics.record_accepted()
        health_monitor.metrics.record_completed(1.0)
        return {"task_id": task_id, "state": "unknown"}

    async def _tasks_cancel(params: dict[str, Any], token: str) -> dict[str, Any]:
        task_id = params.get("task_id")
        if not task_id:
            raise JsonRpcError(-32602, "Invalid params", "task_id is required")
        health_monitor.metrics.record_accepted()
        health_monitor.metrics.record_completed(1.0)
        return {"task_id": task_id, "cancelled": False, "reason": "cancel_not_supported"}

    async def _tasks_resubscribe(params: dict[str, Any], token: str) -> dict[str, Any]:
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

    methods: dict[str, Any] = {
        "tasks/sendSubscribe": _tasks_send_subscribe,
        "tasks/send": _tasks_send_subscribe,
        "tasks/get": _tasks_get,
        "tasks/cancel": _tasks_cancel,
        "tasks/resubscribe": _tasks_resubscribe,
    }

    async def _invoke_declared_method(method: str, params: dict[str, Any]) -> dict[str, Any]:
        health_monitor.metrics.record_accepted()
        start = asyncio.get_event_loop().time()
        result = _build_result(method, params)
        duration_ms = (asyncio.get_event_loop().time() - start) * 1000
        health_monitor.metrics.record_completed(duration_ms)
        return result

    @app.post("/rpc")
    async def rpc(request: Request) -> JSONResponse:
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
            candidate_method = str(payload.get("method") or "").strip() or "tasks/send"
            candidate_params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            try:
                _token = _authorize_rpc(request, candidate_method, candidate_params)
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
            with start_span("nexus.rpc.handle", {"agent": default_name}):
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

                if method in methods:
                    result = await methods[method](params, _token)
                elif method in _declared_methods():
                    result = await _invoke_declared_method(method, params)
                else:
                    raise JsonRpcError(-32601, "Method not found", method)

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
                    trace_seed = str(result.get("trace_id") if isinstance(result, dict) else id_)
                    response_traceparent = build_traceparent(trace_seed)

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

    return app

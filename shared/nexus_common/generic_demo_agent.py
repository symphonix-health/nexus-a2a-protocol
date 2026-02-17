"""Generic startup-safe demo agent runtime for corrupted demo entrypoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from .auth import AuthError, verify_jwt
from .did import did_verify_enabled, verify_did_signature
from .health import HealthMonitor, apply_backpressure_to_agent_card
from .ids import make_task_id, make_trace_id
from .jsonrpc import JsonRpcError, parse_request, response_error, response_result
from .sse import TaskEventBus

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


def _build_common_result(method: str, params: dict[str, Any], task_id: str | None = None) -> dict[str, Any]:
    task = params.get("task") if isinstance(params.get("task"), dict) else {}
    patient_id = _extract_patient_id(task)
    complaint = str(
        task.get("chief_complaint")
        or (task.get("inputs") or {}).get("chief_complaint", "")
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
                "headlines": [
                    "No critical OSINT signals detected in startup-safe mode."
                ],
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
    app = FastAPI(title=default_name)
    bus = TaskEventBus(agent_name=default_name)
    health_monitor = HealthMonitor(default_name)
    inflight_tasks = 0

    jwt_secret = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
    required_scope = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    card_path = Path(app_dir) / "agent_card.json"

    def _load_card() -> dict[str, Any]:
        if card_path.is_file():
            try:
                return json.loads(card_path.read_text(encoding="utf-8"))
            except Exception as exc:
                LOGGER.warning("Failed to parse agent card at %s: %s", card_path, exc)
        return {
            "name": default_name,
            "protocol": "NEXUS-A2A",
            "protocolVersion": "1.0",
            "methods": ["tasks/send", "tasks/sendSubscribe", "tasks/get", "tasks/cancel"],
        }

    def _declared_methods() -> set[str]:
        card = _load_card()
        methods = card.get("methods", [])
        if not isinstance(methods, list):
            return {"tasks/send", "tasks/sendSubscribe", "tasks/get", "tasks/cancel"}
        out = {m for m in methods if isinstance(m, str) and m}
        out.update({"tasks/send", "tasks/sendSubscribe", "tasks/get", "tasks/cancel"})
        return out

    def _require_auth(req: Request) -> str:
        auth = req.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = auth.split(" ", 1)[1].strip()
        try:
            verify_jwt(token, jwt_secret, required_scope=required_scope)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if did_verify_enabled() and not verify_did_signature():
            raise HTTPException(status_code=401, detail="DID signature verification failed")
        return token

    @app.get("/.well-known/agent-card.json")
    async def agent_card() -> JSONResponse:
        payload = _load_card()
        return JSONResponse(content=apply_backpressure_to_agent_card(payload, health_monitor))

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(content=health_monitor.get_health())

    @app.get("/events/{task_id}")
    async def events(task_id: str, request: Request) -> StreamingResponse:
        _require_auth(request)
        return StreamingResponse(bus.stream(task_id), media_type="text/event-stream")

    @app.websocket("/ws/{task_id}")
    async def ws_stream(websocket: WebSocket, task_id: str) -> None:
        token = websocket.query_params.get("token", "")
        try:
            verify_jwt(token, jwt_secret, required_scope=required_scope)
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
        correlation = params.get("correlation") if isinstance(params.get("correlation"), dict) else {}
        idempotency = params.get("idempotency") if isinstance(params.get("idempotency"), dict) else {}
        scenario_context = (
            params.get("scenario_context") if isinstance(params.get("scenario_context"), dict) else {}
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
                final_payload = _build_common_result("tasks/sendSubscribe", params, task_id=task_id)
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
        return {
            "task_id": task_id,
            "trace_id": trace_id,
            **_build_common_result("tasks/sendSubscribe", params, task_id=task_id),
        }

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

    methods: dict[str, Any] = {
        "tasks/sendSubscribe": _tasks_send_subscribe,
        "tasks/send": _tasks_send_subscribe,
        "tasks/get": _tasks_get,
        "tasks/cancel": _tasks_cancel,
    }

    async def _invoke_declared_method(method: str, params: dict[str, Any]) -> dict[str, Any]:
        health_monitor.metrics.record_accepted()
        start = asyncio.get_event_loop().time()
        result = _build_common_result(method, params)
        duration_ms = (asyncio.get_event_loop().time() - start) * 1000
        health_monitor.metrics.record_completed(duration_ms)
        return result

    @app.post("/rpc")
    async def rpc(request: Request) -> JSONResponse:
        _token = _require_auth(request)
        payload = await request.json()
        try:
            req = parse_request(payload)
            method, params, id_ = req["method"], req["params"], req["id"]
            if method in methods:
                result = await methods[method](params, _token)
            elif method in _declared_methods():
                result = await _invoke_declared_method(method, params)
            else:
                raise JsonRpcError(-32601, "Method not found", method)
            return JSONResponse(content=response_result(id_, result, method=method, params=params))
        except JsonRpcError as exc:
            return JSONResponse(content=response_error(payload.get("id"), exc), status_code=200)
        except Exception as exc:
            err = JsonRpcError(-32000, "Server error", str(exc))
            return JSONResponse(content=response_error(payload.get("id"), err), status_code=200)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await bus.close()

    return app

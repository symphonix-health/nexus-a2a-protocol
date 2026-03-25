from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.a2a_http import (
    canonicalize_payload_method,
    negotiate_http_request,
    response_headers as a2a_response_headers,
)
from shared.nexus_common.audit import AuditLogEntry, env_audit_logger
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.health import HealthMonitor
from shared.nexus_common.jsonrpc import JsonRpcError, parse_request, response_error, response_result
from shared.nexus_common.otel import start_span
from shared.nexus_common.service_auth import AuthError, extract_bearer_token, verify_service_auth
from shared.nexus_common.sse import TaskEventBus
from shared.nexus_common.trace_context import build_traceparent, extract_trace_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.openhie-mediator")

@contextlib.asynccontextmanager
async def _lifespan(application: FastAPI):
    yield
    await bus.close()


app = FastAPI(title="openhie-mediator", lifespan=_lifespan)
bus = TaskEventBus(agent_name="openhie-mediator")
health_monitor = HealthMonitor("openhie-mediator")

REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
_AUDIT_LOGGER = env_audit_logger(default_path="logs/openhie_audit.jsonl")
_FHIR_VALIDATE_GATE = os.getenv("FHIR_VALIDATE_GATE", "warn").strip().lower()


def _require_auth(req: Request, required_roles: list[str] | None = None) -> str:
    try:
        token = extract_bearer_token(req.headers.get("authorization", ""))
        verify_service_auth(
            token,
            headers=req.headers,
            required_scope=REQUIRED_SCOPE,
            required_roles=required_roles,
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if did_verify_enabled() and not verify_did_signature():
        raise HTTPException(status_code=401, detail="DID signature verification failed")
    return token


def _audit(
    *,
    action: str,
    resource: str,
    outcome: str,
    trace_id: str | None = None,
    reason: str | None = None,
) -> None:
    try:
        _AUDIT_LOGGER.log(
            AuditLogEntry(
                actor="openhie-mediator",
                action=action,
                resource=resource,
                outcome=outcome,
                trace_id=trace_id,
                reason=reason,
            )
        )
    except Exception:
        return


def _normalize_gate_mode() -> str:
    gate = _FHIR_VALIDATE_GATE
    if gate in {"off", "false", "0", "disabled"}:
        return "off"
    if gate in {"enforce", "strict", "block"}:
        return "enforce"
    return "warn"


def _auth_error_response(
    *,
    payload: dict[str, Any],
    negotiation: Any,
    status_code: int,
    detail: str,
    traceparent: str | None,
    tracestate: str | None,
) -> JSONResponse:
    error = JsonRpcError(
        -32001,
        "Unauthorized",
        {
            "reason": "auth_failed",
            "detail": detail,
            "failure_domain": "auth",
        },
    )
    return JSONResponse(
        content=response_error(payload.get("id"), error),
        status_code=status_code,
        media_type=negotiation.response_media_type,
        headers=a2a_response_headers(
            negotiation,
            traceparent=traceparent,
            tracestate=tracestate,
        ),
    )


async def _fhir_validate_resource(
    client: httpx.AsyncClient,
    *,
    base: str,
    headers: dict[str, str],
    resource: dict[str, Any],
) -> tuple[bool, str]:
    resource_type = str(resource.get("resourceType") or "").strip()
    if not resource_type:
        return False, "missing_resource_type"
    try:
        resp = await client.post(
            f"{base}/{resource_type}/$validate",
            headers={**headers, "Content-Type": "application/fhir+json"},
            json=resource,
        )
        if resp.status_code >= 400:
            return False, f"http_{resp.status_code}"
        payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if isinstance(payload, dict):
            issues = payload.get("issue")
            if isinstance(issues, list):
                severities = {
                    str(issue.get("severity", "")).lower()
                    for issue in issues
                    if isinstance(issue, dict)
                }
                if severities.intersection({"error", "fatal"}):
                    return False, "operation_outcome_error"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


@app.get("/.well-known/agent-card.json")
async def agent_card() -> JSONResponse:
    path = os.path.join(os.path.dirname(__file__), "agent_card.json")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))


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


METHODS: dict[str, Any] = {}


async def _fhir_get(params: dict[str, Any], token: str) -> dict[str, Any]:
    health_monitor.metrics.record_accepted()
    start_time = asyncio.get_event_loop().time()
    correlation = params.get("correlation") if isinstance(params.get("correlation"), dict) else {}
    trace_id = str(correlation.get("trace_id") or "").strip() or None
    gate_mode = _normalize_gate_mode()

    try:
        base = os.getenv("FHIR_BASE_URL", "http://hapi-fhir:8080/fhir")
        patient_ref = str(params.get("patient_ref") or "Patient/unknown")
        patient_id = patient_ref.split("/")[-1]
        headers = {"Accept": "application/fhir+json"}

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                patient_resp = await client.get(f"{base}/Patient/{patient_id}", headers=headers)
                patient_resp.raise_for_status()
                allergy_resp = await client.get(
                    f"{base}/AllergyIntolerance?patient={patient_id}",
                    headers=headers,
                )
                allergy_resp.raise_for_status()

                patient_payload = patient_resp.json()
                allergy_payload = allergy_resp.json()

                validation_checked: list[dict[str, Any]] = []
                validation_failed: list[dict[str, Any]] = []
                if gate_mode != "off":
                    patient_ok, patient_reason = await _fhir_validate_resource(
                        client,
                        base=base,
                        headers=headers,
                        resource=patient_payload if isinstance(patient_payload, dict) else {},
                    )
                    patient_validation = {
                        "resource": f"Patient/{patient_id}",
                        "ok": bool(patient_ok),
                        "reason": patient_reason,
                    }
                    validation_checked.append(patient_validation)
                    if not patient_ok:
                        validation_failed.append(patient_validation)

                    if isinstance(allergy_payload, dict) and allergy_payload.get("resourceType") == "Bundle":
                        entries = allergy_payload.get("entry")
                        if isinstance(entries, list):
                            for idx, entry in enumerate(entries[:25]):
                                resource = entry.get("resource") if isinstance(entry, dict) else None
                                if not isinstance(resource, dict):
                                    continue
                                resource_type = str(resource.get("resourceType") or "").strip()
                                if not resource_type:
                                    continue
                                ok, reason = await _fhir_validate_resource(
                                    client,
                                    base=base,
                                    headers=headers,
                                    resource=resource,
                                )
                                validation = {
                                    "resource": f"{resource_type}#{idx}",
                                    "ok": bool(ok),
                                    "reason": reason,
                                }
                                validation_checked.append(validation)
                                if not ok:
                                    validation_failed.append(validation)

                if validation_failed and gate_mode == "enforce":
                    _audit(
                        action="validate",
                        resource=f"Patient/{patient_id}",
                        outcome="denied",
                        trace_id=trace_id,
                        reason="fhir_validation_failed",
                    )
                    raise JsonRpcError(
                        -32050,
                        "FHIR validation failed",
                        {
                            "reason": "fhir_validation_failed",
                            "failure_domain": "validation",
                            "failed_resources": validation_failed,
                        },
                    )

            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            health_monitor.metrics.record_completed(duration_ms)
            _audit(
                action="read",
                resource=f"Patient/{patient_id}",
                outcome="success",
                trace_id=trace_id,
            )
            result: dict[str, Any] = {
                "patient": patient_payload,
                "allergies": allergy_payload,
            }
            if gate_mode != "off":
                result["validation"] = {
                    "mode": gate_mode,
                    "checked": validation_checked,
                    "failed": validation_failed,
                }
            return result
        except JsonRpcError:
            raise
        except Exception as exc:
            logger.warning("FHIR request failed: %s -- returning fallback context", exc)
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            health_monitor.metrics.record_completed(duration_ms)
            _audit(
                action="read",
                resource=f"Patient/{patient_id}",
                outcome="error",
                trace_id=trace_id,
                reason=str(exc),
            )
            return {"patient": {}, "allergies": {}}
    except Exception:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        health_monitor.metrics.record_error(duration_ms)
        raise


METHODS["fhir/get"] = _fhir_get


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
        try:
            token = _require_auth(request)
        except HTTPException as exc:
            if not response_traceparent:
                response_traceparent = build_traceparent(str(payload.get("id") or "auth"))
            _audit(
                action="auth",
                resource="rpc",
                outcome="denied",
                reason=str(exc.detail),
            )
            return _auth_error_response(
                payload=payload,
                negotiation=negotiation,
                status_code=exc.status_code,
                detail=str(exc.detail),
                traceparent=response_traceparent,
                tracestate=tracestate_in,
            )

        with start_span("nexus.rpc.handle", {"agent": "openhie-mediator"}):
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
                compat = result.get("compatibility") if isinstance(result.get("compatibility"), dict) else {}
                compat = dict(compat)
                compat["legacy_method"] = negotiation.original_method
                compat["canonical_method"] = negotiation.canonical_method
                compat["mode"] = negotiation.compatibility_mode
                result["compatibility"] = compat

            if not response_traceparent:
                response_traceparent = build_traceparent(
                    str(result.get("trace_id") if isinstance(result, dict) else id_)
                )

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
            response_traceparent = build_traceparent(str(payload.get("id") or "error"))
        _audit(
            action="rpc",
            resource=str(payload.get("method") or "unknown"),
            outcome="error",
            reason=str(exc.data),
        )
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
            response_traceparent = build_traceparent(str(payload.get("id") or "exception"))
        _audit(
            action="rpc",
            resource=str(payload.get("method") or "unknown"),
            outcome="error",
            reason=str(exc),
        )
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



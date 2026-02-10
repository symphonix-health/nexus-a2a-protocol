"""Bed Manager Agent -- admission management with bed assignment (FR-6)."""
from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from shared.nexus_common.auth import AuthError, OidcError, verify_jwt, verify_jwt_rs256
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.health import HealthMonitor
from shared.nexus_common.http_client import jsonrpc_call
from shared.nexus_common.ids import make_task_id, make_trace_id
from shared.nexus_common.jsonrpc import (
    JsonRpcError, parse_request, response_error, response_result,
)
from shared.nexus_common.sse import TaskEventBus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("nexus.bed-manager-agent")

app = FastAPI(title="bed-manager-agent")
bus = TaskEventBus(agent_name="bed-manager-agent")
health_monitor = HealthMonitor("bed-manager-agent")

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
AUTH_MODE = os.getenv("AUTH_MODE", "hs256").lower()
OIDC_DISCOVERY_URL = os.getenv("OIDC_DISCOVERY_URL", "")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE")
OIDC_ISSUER = os.getenv("OIDC_ISSUER")
_ENV_REQUIRED_ROLES = [r.strip() for r in os.getenv("NEXUS_REQUIRED_ROLES", "").split(",") if r.strip()]


def _require_auth(req: Request, required_roles: list[str] | None = None) -> str:
    auth = req.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        if AUTH_MODE == "rs256":
            if not OIDC_DISCOVERY_URL:
                raise HTTPException(status_code=401, detail="OIDC discovery URL not configured")
            payload = verify_jwt_rs256(
                token,
                OIDC_DISCOVERY_URL,
                required_scope=REQUIRED_SCOPE,
                audience=OIDC_AUDIENCE,
                issuer=OIDC_ISSUER,
            )
        else:
            payload = verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
    except (AuthError, OidcError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    roles_claim = payload.get("roles") or payload.get("role") or payload.get("groups") or []
    if isinstance(roles_claim, str):
        user_roles = {r.strip() for r in roles_claim.split(",") if r.strip()}
    else:
        user_roles = {str(r).strip() for r in roles_claim if str(r).strip()}
    needed = required_roles if required_roles is not None else _ENV_REQUIRED_ROLES
    if needed and not set(needed).issubset(user_roles):
        raise HTTPException(status_code=403, detail="Insufficient roles")
    try:
        req.state.jwt_payload = payload
    except Exception:
        pass
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
    return JSONResponse(content=health_monitor.get_health())


@app.get("/events/{task_id}")
async def events(task_id: str, request: Request):
    _require_auth(request)
    async def gen():
        async for chunk in bus.stream(task_id):
            yield chunk
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.websocket("/ws/{task_id}")
async def ws_stream(websocket: WebSocket, task_id: str):
    token = websocket.query_params.get("token", "")
    try:
        if AUTH_MODE == "rs256":
            if not OIDC_DISCOVERY_URL:
                raise AuthError("OIDC discovery URL not configured")
            verify_jwt_rs256(
                token,
                OIDC_DISCOVERY_URL,
                required_scope=REQUIRED_SCOPE,
                audience=OIDC_AUDIENCE,
                issuer=OIDC_ISSUER,
            )
        else:
            verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
    except (AuthError, OidcError):
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


METHODS: dict = {}


import random

BED_INVENTORY = {
    "ICU": {"total": 20, "available": 5},
    "Ward": {"total": 60, "available": 22},
    "ED_Obs": {"total": 10, "available": 3},
    "Paediatric": {"total": 15, "available": 7},
    "Cardiac": {"total": 12, "available": 4},
}


async def _assign_bed(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        task = params.get("task", params)
        unit_pref = task.get("unit_pref", "Ward")
        pid = task.get("patient_id", task.get("patient", {}).get("patient_id", "P-0000"))
        decision = task.get("decision", "admit")
        info = BED_INVENTORY.get(unit_pref, BED_INVENTORY["Ward"])
        if info["available"] > 0:
            bid = f"{unit_pref}-{random.randint(100,999)}"
            status = "assigned"
        else:
            bid, status = None, "waitlisted"
            for alt, ai in BED_INVENTORY.items():
                if ai["available"] > 0:
                    bid = f"{alt}-{random.randint(100,999)}"
                    status = "assigned_alternative"
                    unit_pref = alt
                    break
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"patient_id": pid, "admission_status": status, "decision": decision,
                "bed_assignment_or_plan": bid or "waitlist", "unit": unit_pref, "bed_id": bid}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["admission/assign_bed"] = _assign_bed


async def _check_availability(params: dict, token: str) -> dict:
    health_monitor.metrics.record_accepted()
    t = asyncio.get_event_loop().time()
    try:
        avail = {}
        for unit, info in BED_INVENTORY.items():
            avail[unit] = {"total": info["total"], "available": info["available"],
                           "occupancy_pct": round((1 - info["available"]/info["total"]) * 100, 1)}
        d = (asyncio.get_event_loop().time() - t) * 1000
        health_monitor.metrics.record_completed(d)
        return {"bed_availability": avail}
    except Exception:
        health_monitor.metrics.record_error((asyncio.get_event_loop().time() - t) * 1000)
        raise

METHODS["admission/check_availability"] = _check_availability


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    health_monitor.metrics.record_accepted()
    t0 = asyncio.get_event_loop().time()
    await bus.publish(task_id, "nexus.task.status",
                      json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}))

    async def run():
        try:
            await bus.publish(task_id, "nexus.task.status",
                              json.dumps({"task_id": task_id, "state": "working", "step": "assigning_bed"}))
            task = params.get("task", {})
            meds = []
            med_plan = task.get("med_plan", [])
            if med_plan:
                pharm_url = os.getenv("NEXUS_PHARMACY_RPC", "http://localhost:8025/rpc")
                try:
                    r = await jsonrpc_call(pharm_url, token, "pharmacy/recommend",
                                           {"task": task}, f"{task_id}-pharm")
                    meds = r.get("result", {}).get("medications_checked", med_plan)
                except Exception:
                    meds = [{"drug": d, "status": "unchecked"} for d in med_plan]
            bed = await _assign_bed({"task": task}, token)
            result = {"task_id": task_id, "admission_status": bed["admission_status"],
                      "bed_assignment_or_plan": bed["bed_assignment_or_plan"],
                      "medications_checked": meds or med_plan, "unit": bed.get("unit")}
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_completed(d)
            await bus.publish(task_id, "nexus.task.final", json.dumps(result), d)
        except Exception as exc:
            d = (asyncio.get_event_loop().time() - t0) * 1000
            health_monitor.metrics.record_error(d)
            await bus.publish(task_id, "nexus.task.error",
                              json.dumps({"task_id": task_id, "error": str(exc)}), d)

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

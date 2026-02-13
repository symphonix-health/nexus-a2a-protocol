"""Home Visit Agent."""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from shared.nexus_common.auth import AuthError, OidcError, verify_jwt, verify_jwt_rs256
from shared.nexus_common.did import did_verify_enabled, verify_did_signature
from shared.nexus_common.health import HealthMonitor
from shared.nexus_common.ids import make_task_id, make_trace_id
from shared.nexus_common.jsonrpc import JsonRpcError, parse_request, response_error, response_result
from shared.nexus_common.sse import TaskEventBus

app = FastAPI(title="home-visit-agent")
bus = TaskEventBus(agent_name="home-visit-agent")
health_monitor = HealthMonitor("home-visit-agent")

JWT_SECRET = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
REQUIRED_SCOPE = os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
AUTH_MODE = os.getenv("AUTH_MODE", "hs256").lower()
OIDC_DISCOVERY_URL = os.getenv("OIDC_DISCOVERY_URL", "")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE")
OIDC_ISSUER = os.getenv("OIDC_ISSUER")
_ENV_REQUIRED_ROLES = [
    r.strip() for r in os.getenv("NEXUS_REQUIRED_ROLES", "").split(",") if r.strip()
]


def _require_auth(req: Request, required_roles: list[str] | None = None) -> str:
    auth = req.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = (
            verify_jwt_rs256(
                token,
                OIDC_DISCOVERY_URL,
                required_scope=REQUIRED_SCOPE,
                audience=OIDC_AUDIENCE,
                issuer=OIDC_ISSUER,
            )
            if AUTH_MODE == "rs256"
            else verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
        )
    except (AuthError, OidcError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    roles_claim = payload.get("roles") or payload.get("role") or payload.get("groups") or []
    user_roles = (
        {r.strip() for r in roles_claim.split(",")}
        if isinstance(roles_claim, str)
        else {str(r).strip() for r in roles_claim if str(r).strip()}
    )
    needed = required_roles if required_roles is not None else _ENV_REQUIRED_ROLES
    if needed and not set(needed).issubset(user_roles):
        raise HTTPException(status_code=403, detail="Insufficient roles")
    if did_verify_enabled() and not verify_did_signature():
        raise HTTPException(status_code=401, detail="DID signature verification failed")
    return token


@app.get("/.well-known/agent-card.json")
async def agent_card() -> JSONResponse:
    with open(os.path.join(os.path.dirname(__file__), "agent_card.json"), encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content=health_monitor.get_health())


@app.get("/events/{task_id}")
async def events(task_id: str, request: Request) -> StreamingResponse:
    _require_auth(request)

    async def gen():
        async for chunk in bus.stream(task_id):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.websocket("/ws/{task_id}")
async def ws_stream(websocket: WebSocket, task_id: str) -> None:
    token = websocket.query_params.get("token", "")
    try:
        verify_jwt_rs256(
            token,
            OIDC_DISCOVERY_URL,
            required_scope=REQUIRED_SCOPE,
            audience=OIDC_AUDIENCE,
            issuer=OIDC_ISSUER,
        ) if AUTH_MODE == "rs256" else verify_jwt(token, JWT_SECRET, required_scope=REQUIRED_SCOPE)
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


METHODS: dict[str, object] = {}


async def _dispatch(params: dict, token: str) -> dict:
    del token
    return {
        "home_safety_screen": bool(params.get("home_safety_screen", True)),
        "caregiver_present": bool(params.get("caregiver_present", False)),
        "dispatch_status": "completed",
    }


METHODS["home_visit/dispatch"] = _dispatch


async def _send_subscribe(params: dict, token: str) -> dict:
    task_id = make_task_id()
    trace_id = make_trace_id()
    await bus.publish(
        task_id,
        "nexus.task.status",
        json.dumps({"task_id": task_id, "state": "accepted", "trace_id": trace_id}),
    )

    async def run() -> None:
        try:
            await bus.publish(
                task_id,
                "nexus.task.status",
                json.dumps({"task_id": task_id, "state": "working", "step": "home_visit_workflow"}),
            )
            result = await _dispatch(params.get("task", params), token)
            await bus.publish(
                task_id, "nexus.task.final", json.dumps({"task_id": task_id, **result})
            )
        except Exception as exc:
            await bus.publish(
                task_id, "nexus.task.error", json.dumps({"task_id": task_id, "error": str(exc)})
            )

    asyncio.create_task(run())
    return {"task_id": task_id, "trace_id": trace_id}


METHODS["tasks/sendSubscribe"] = _send_subscribe


@app.post("/rpc")
async def rpc(request: Request) -> JSONResponse:
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

"""JSON-RPC helpers for Nexus A2A requests and responses."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .errors import ProtocolValidationError

A2A_METHODS = {
    "tasks/send",
    "tasks/sendSubscribe",
    "tasks/get",
    "tasks/cancel",
    "tasks/resubscribe",
}


def _next_request_id() -> str:
    return uuid4().hex


def make_request(
    method: str, params: dict[str, Any], request_id: str | None = None
) -> dict[str, Any]:
    """Build a JSON-RPC request with basic method validation."""

    if method not in A2A_METHODS:
        raise ProtocolValidationError(f"Unsupported method: {method}")
    if not isinstance(params, dict):
        raise ProtocolValidationError("params must be a dictionary")

    return {
        "jsonrpc": "2.0",
        "id": request_id or _next_request_id(),
        "method": method,
        "params": params,
    }


def make_result(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ProtocolValidationError("result must be a dictionary")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(
    request_id: str | None,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def validate_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a JSON-RPC envelope used by this SDK."""

    if not isinstance(payload, dict):
        raise ProtocolValidationError("payload must be a dictionary")
    if payload.get("jsonrpc") != "2.0":
        raise ProtocolValidationError("jsonrpc must be '2.0'")

    is_request = "method" in payload
    is_response = "result" in payload or "error" in payload

    if not (is_request or is_response):
        raise ProtocolValidationError("payload must contain either method or result/error")
    if is_request and is_response:
        raise ProtocolValidationError("payload cannot contain both request and response fields")
    if "id" not in payload:
        raise ProtocolValidationError("payload must contain id")

    if is_request:
        method = payload.get("method")
        if method not in A2A_METHODS:
            raise ProtocolValidationError(f"Unsupported method: {method}")
        params = payload.get("params")
        if not isinstance(params, dict):
            raise ProtocolValidationError("request params must be a dictionary")

    if "error" in payload:
        error = payload["error"]
        if not isinstance(error, dict):
            raise ProtocolValidationError("error must be a dictionary")
        if "code" not in error or "message" not in error:
            raise ProtocolValidationError("error must include code and message")

    return payload

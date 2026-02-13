"""JSON-RPC 2.0 request parsing and response building for NEXUS-A2A."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

JSONRPC_VERSION = "2.0"

# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_ERROR = -32000

# NEXUS-A2A custom error codes
NEXUS_AUTH_FAILED = -32001
NEXUS_TASK_NOT_FOUND = -32002
NEXUS_TASK_CANCELLED = -32003
NEXUS_RATE_LIMITED = -32004
FAILURE_DOMAINS = {"agent", "network", "validation"}


@dataclass
class JsonRpcError(Exception):
    """JSON-RPC error with code, message, and optional data."""

    code: int
    message: str
    data: Any | None = None
    retryable: bool | None = None
    retry_after_ms: int | None = None
    failure_domain: str | None = None

    def to_dict(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        data = make_error_data(
            self.data,
            retryable=self.retryable,
            retry_after_ms=self.retry_after_ms,
            failure_domain=self.failure_domain,
        )
        if data is not None:
            err["data"] = data
        return err


def make_error_data(
    data: Any | None,
    *,
    retryable: bool | None = None,
    retry_after_ms: int | None = None,
    failure_domain: str | None = None,
) -> Any | None:
    """Build standardized JSON-RPC error.data with NEXUS failure taxonomy."""
    if retry_after_ms is not None and retry_after_ms < 0:
        raise ValueError("retry_after_ms must be >= 0")
    if failure_domain is not None and failure_domain not in FAILURE_DOMAINS:
        raise ValueError(f"failure_domain must be one of {sorted(FAILURE_DOMAINS)}")

    if data is None and retryable is None and retry_after_ms is None and failure_domain is None:
        return None

    if isinstance(data, dict):
        payload: dict[str, Any] = dict(data)
    elif data is None:
        payload = {}
    else:
        payload = {"detail": data}

    if retryable is not None:
        payload["retryable"] = retryable
    if retry_after_ms is not None:
        payload["retry_after_ms"] = retry_after_ms
    if failure_domain is not None:
        payload["failure_domain"] = failure_domain

    return payload


def parse_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse and validate an incoming JSON-RPC 2.0 request."""
    if not isinstance(payload, dict):
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request", "Payload must be a JSON object")
    if payload.get("jsonrpc") != JSONRPC_VERSION:
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request", "jsonrpc must be '2.0'")
    if "method" not in payload or not isinstance(payload["method"], str):
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request", "method must be a string")
    if "id" not in payload:
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request", "id is required")
    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise JsonRpcError(INVALID_PARAMS, "Invalid params", "params must be an object")
    return {"id": payload["id"], "method": payload["method"], "params": params}


def response_result(id_: Any, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": id_, "result": result}


def response_error(id_: Any, err: JsonRpcError) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": id_, "error": err.to_dict()}

"""JSON-RPC 2.0 request parsing and response building for NEXUS-A2A."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

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


@dataclass
class JsonRpcError(Exception):
    """JSON-RPC error with code, message, and optional data."""

    code: int
    message: str
    data: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        err: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


def parse_request(payload: Dict[str, Any]) -> Dict[str, Any]:
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


def response_result(id_: Any, result: Any) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 success response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": id_, "result": result}


def response_error(id_: Any, err: JsonRpcError) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": id_, "error": err.to_dict()}

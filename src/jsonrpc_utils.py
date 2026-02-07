"""JSON-RPC helpers: build request envelopes and validate minimal structure."""

from typing import Any, Dict, Optional, Union


def build_request(method: str, params: Optional[object], id: Optional[Union[str, int]]) -> Dict[str, Any]:
    if not isinstance(method, str) or not method:
        raise ValueError("method must be a non-empty string")
    if id is not None and not isinstance(id, (str, int)):
        raise ValueError("id must be str|int|None")

    req: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        req["params"] = params
    if id is not None:
        req["id"] = id
    return req


def validate_envelope(obj: Dict[str, Any]) -> None:
    if not isinstance(obj, dict):
        raise ValueError("envelope must be a dict")
    if obj.get("jsonrpc") != "2.0":
        raise ValueError("jsonrpc must be '2.0'")
    method = obj.get("method")
    if not isinstance(method, str):
        raise ValueError("method must be a string")
    if "id" in obj and not isinstance(obj["id"], (str, int)) and obj["id"] is not None:
        raise ValueError("id must be str|int|None")

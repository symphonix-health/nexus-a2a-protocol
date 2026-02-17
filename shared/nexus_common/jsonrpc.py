"""JSON-RPC 2.0 request parsing and response building for NEXUS-A2A."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from .protocol import apply_mutation_response_metadata, evaluate_mutation_conflict
from .scale_profile import (
    SCALE_PROFILE_VERSION,
    build_canonical_shard_key,
    evaluate_feature_negotiation,
    should_enforce_scale_profile,
    validate_canonical_shard_key,
    validate_scale_profile_fields,
    validate_strict_idempotency_fields,
)
from .sse import parse_signed_resume_cursor

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

    method = payload["method"]
    _validate_scale_profile_contract(method, params)
    _validate_feature_negotiation(method, params)
    _validate_resubscribe_cursor_contract(method, params)
    return {"id": payload["id"], "method": payload["method"], "params": params}


def _validate_scale_profile_contract(method: str, params: dict[str, Any]) -> None:
    if not should_enforce_scale_profile(method, params):
        return
    scale_profile = params.get("scale_profile")
    if not isinstance(scale_profile, dict):
        raise JsonRpcError(
            INVALID_PARAMS,
            "Invalid params",
            {
                "reason": "missing_scale_profile",
                "field": "scale_profile",
                "failure_domain": "validation",
            },
        )
    ok, field = validate_scale_profile_fields(scale_profile)
    if not ok:
        raise JsonRpcError(
            INVALID_PARAMS,
            "Invalid params",
            {
                "reason": "missing_scale_profile_field",
                "field": field,
                "profile": SCALE_PROFILE_VERSION,
                "failure_domain": "validation",
            },
        )
    canonical_ok, canonical_reason, expected_shard_key = validate_canonical_shard_key(scale_profile)
    if not canonical_ok:
        error_data = {
            "reason": canonical_reason,
            "field": "shard_key",
            "profile": SCALE_PROFILE_VERSION,
            "failure_domain": "validation",
        }
        if canonical_reason == "non_canonical_shard_key":
            # Safe to compute expected key only from tuple routing identifiers.
            if expected_shard_key is None:
                expected_shard_key = build_canonical_shard_key(
                    tenant_key=scale_profile["tenant_key"],
                    user_key=scale_profile["user_key"],
                    task_key=scale_profile["task_key"],
                )
            error_data["expected_shard_key"] = expected_shard_key
        raise JsonRpcError(INVALID_PARAMS, "Invalid params", error_data)

    idempotency = params.get("idempotency")
    if not isinstance(idempotency, dict):
        raise JsonRpcError(
            INVALID_PARAMS,
            "Invalid params",
            {
                "reason": "missing_idempotency",
                "field": "idempotency",
                "failure_domain": "validation",
            },
        )
    ok_idem, idem_field = validate_strict_idempotency_fields(idempotency)
    if not ok_idem:
        raise JsonRpcError(
            INVALID_PARAMS,
            "Invalid params",
            {
                "reason": "missing_strict_idempotency_field",
                "field": idem_field,
                "profile": SCALE_PROFILE_VERSION,
                "failure_domain": "validation",
            },
        )


def _validate_feature_negotiation(method: str, params: dict[str, Any]) -> None:
    scale_profile = params.get("scale_profile")
    if not isinstance(scale_profile, dict):
        return

    negotiation = evaluate_feature_negotiation(scale_profile)
    if negotiation.get("accepted"):
        return

    error_type = negotiation.get("error_type")
    if error_type == "invalid_params":
        raise JsonRpcError(
            INVALID_PARAMS,
            "Invalid params",
            {
                "reason": negotiation.get("reason", "invalid_features_required"),
                "field": negotiation.get("field"),
                "method": method,
                "failure_domain": "validation",
            },
        )

    if error_type == "unsupported_feature":
        raise JsonRpcError(
            METHOD_NOT_FOUND,
            "Method not found",
            {
                "reason": "unsupported_feature",
                "method": method,
                "missing_required": negotiation.get("missing_required", []),
                "accepted_required": negotiation.get("accepted_required", []),
                "accepted_optional": negotiation.get("accepted_optional", []),
                "failure_domain": "validation",
            },
        )

    raise JsonRpcError(
        INTERNAL_ERROR,
        "Internal error",
        {
            "reason": "feature_negotiation_failed",
            "method": method,
            "failure_domain": "agent",
        },
    )


def _validate_resubscribe_cursor_contract(method: str, params: dict[str, Any]) -> None:
    if method != "tasks/resubscribe":
        return

    cursor = params.get("cursor")
    if not isinstance(cursor, str) or not cursor.strip():
        raise JsonRpcError(
            INVALID_PARAMS,
            "Invalid params",
            {
                "reason": "missing_cursor",
                "field": "cursor",
                "failure_domain": "validation",
            },
        )

    max_catchup_events = params.get("max_catchup_events")
    max_catchup_policy = int(os.getenv("NEXUS_RESUBSCRIBE_MAX_CATCHUP_EVENTS", "10000"))
    if max_catchup_events is not None:
        try:
            catchup = int(max_catchup_events)
        except Exception as exc:
            raise JsonRpcError(
                INVALID_PARAMS,
                "Invalid params",
                {
                    "reason": "invalid_max_catchup_events",
                    "field": "max_catchup_events",
                    "failure_domain": "validation",
                },
            ) from exc
        if catchup <= 0:
            raise JsonRpcError(
                INVALID_PARAMS,
                "Invalid params",
                {
                    "reason": "invalid_max_catchup_events",
                    "field": "max_catchup_events",
                    "failure_domain": "validation",
                },
            )
        if catchup > max_catchup_policy:
            retry_after_ms = int(os.getenv("NEXUS_RESUBSCRIBE_RETRY_AFTER_MS", "250"))
            raise JsonRpcError(
                NEXUS_RATE_LIMITED,
                "Rate limited",
                {
                    "reason": "catchup_exceeds_retention",
                    "failure_domain": "network",
                    "retryable": True,
                    "retry_after_ms": retry_after_ms,
                    "max_catchup_events": max_catchup_policy,
                    "requested_catchup_events": catchup,
                },
                retryable=True,
                retry_after_ms=retry_after_ms,
                failure_domain="network",
            )

    try:
        parse_signed_resume_cursor(cursor)
    except Exception as exc:  # noqa: BLE001 - normalized to protocol error taxonomy
        detail = str(exc)
        lowered = detail.lower()
        reason = "invalid_cursor"
        if "expired" in lowered:
            reason = "cursor_expired"
        elif "retention" in lowered:
            reason = "cursor_out_of_retention"
        elif "signature" in lowered:
            reason = "invalid_cursor_signature"
        elif "missing fields" in lowered:
            reason = "cursor_missing_fields"

        raise JsonRpcError(
            NEXUS_TASK_NOT_FOUND,
            "Task not found",
            {
                "reason": reason,
                "field": "cursor",
                "detail": detail,
                "failure_domain": "validation",
            },
            retryable=False,
            failure_domain="validation",
        ) from exc


def response_result(
    id_: Any,
    result: Any,
    *,
    method: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response."""
    payload_result = result
    if isinstance(result, dict):
        scale_profile = params.get("scale_profile") if isinstance(params, dict) else None
        try:
            conflict = evaluate_mutation_conflict(
                method=method,
                scale_profile=scale_profile if isinstance(scale_profile, dict) else None,
                result=result,
            )
        except ValueError as exc:
            raise JsonRpcError(
                INTERNAL_ERROR,
                "Internal error",
                {
                    "reason": "invalid_conflict_payload",
                    "method": method,
                    "detail": str(exc),
                    "failure_domain": "agent",
                },
                retryable=False,
                failure_domain="agent",
            ) from exc
        if conflict is not None:
            raise JsonRpcError(
                SERVER_ERROR,
                "Conflict",
                {
                    **conflict,
                    "failure_domain": "validation",
                },
                retryable=False,
                failure_domain="validation",
            )
        try:
            payload_result = apply_mutation_response_metadata(
                result,
                method=method,
                params=params,
            )
        except ValueError as exc:
            raise JsonRpcError(
                INTERNAL_ERROR,
                "Internal error",
                {
                    "reason": "invalid_mutation_response_metadata",
                    "method": method,
                    "detail": str(exc),
                    "failure_domain": "agent",
                },
                retryable=False,
                failure_domain="agent",
            ) from exc
    return {"jsonrpc": JSONRPC_VERSION, "id": id_, "result": payload_result}


def response_error(id_: Any, err: JsonRpcError) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": id_, "error": err.to_dict()}


def make_rate_limited_error(
    *,
    rate_limit_scope: str,
    bucket_id: str,
    limit_rps: float,
    observed_rps: float,
    retry_after_ms: int = 250,
) -> JsonRpcError:
    """Build a strict admission-control error according to scale profile."""
    return JsonRpcError(
        NEXUS_RATE_LIMITED,
        "Rate limited",
        {
            "retryable": True,
            "retry_after_ms": retry_after_ms,
            "failure_domain": "network",
            "rate_limit_scope": rate_limit_scope,
            "bucket_id": bucket_id,
            "limit_rps": float(limit_rps),
            "observed_rps": float(observed_rps),
        },
        retryable=True,
        retry_after_ms=retry_after_ms,
        failure_domain="network",
    )

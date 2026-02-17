"""JSON-RPC helpers for Nexus A2A requests and responses."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
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
FAILURE_DOMAINS = {"agent", "network", "validation"}
MUTATING_METHODS = {"tasks/send", "tasks/sendSubscribe", "tasks/cancel"}
SCALE_PROFILE_VERSION = "nexus-scale-v1.1"
SCALE_REQUIRED_FIELDS = ("profile", "tenant_key", "user_key", "task_key", "shard_key")
STRICT_IDEMPOTENCY_FIELDS = ("idempotency_key", "scope", "dedup_window_ms", "payload_hash")
SHARD_KEY_PREFIX = "sha256:"
ROUTING_KEY_SEPARATOR = "\x1f"
CURSOR_REQUIRED_FIELDS = {"stream_id", "stream_epoch", "seq", "exp_unix_ms", "sig"}
CURSOR_OPTIONAL_FIELDS = {"iat_unix_ms", "retention_until_unix_ms"}
SUPPORTED_FEATURE_FLAGS = {
    "routing.v1",
    "stream.resume.v1",
    "admission.v1",
    "idempotency.strict.v1",
    "consistency.versioning.v1",
    "consistency.vectorclock.v1",
}
SCALE_CONSISTENCY_LEVELS = {"eventual", "local_quorum", "global_quorum"}


def _normalize_non_empty_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _build_canonical_shard_key(*, tenant_key: str, user_key: str, task_key: str) -> str:
    routing_material = ROUTING_KEY_SEPARATOR.join((tenant_key, user_key, task_key)).encode("utf-8")
    digest = hashlib.sha256(routing_material).hexdigest()
    return f"{SHARD_KEY_PREFIX}{digest}"


def _validate_canonical_shard_key(profile: dict[str, Any]) -> tuple[bool, str | None, str | None]:
    tenant = _normalize_non_empty_text(profile.get("tenant_key"))
    user = _normalize_non_empty_text(profile.get("user_key"))
    task = _normalize_non_empty_text(profile.get("task_key"))
    shard_key = _normalize_non_empty_text(profile.get("shard_key"))

    if tenant is None or user is None or task is None or shard_key is None:
        return False, "missing_routing_field", None

    if not shard_key.startswith(SHARD_KEY_PREFIX):
        return False, "invalid_shard_key_format", None

    digest = shard_key[len(SHARD_KEY_PREFIX) :]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        return False, "invalid_shard_key_format", None

    expected = _build_canonical_shard_key(tenant_key=tenant, user_key=user, task_key=task)
    if shard_key != expected:
        return False, "non_canonical_shard_key", expected

    return True, None, expected


def _cursor_secret() -> str:
    return os.getenv(
        "NEXUS_STREAM_CURSOR_SECRET",
        os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me"),
    )


def _parse_resume_cursor(cursor: Any) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor.strip():
        raise ValueError("cursor must be non-empty string")
    token = cursor.strip()
    pad = "=" * ((4 - len(token) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode((token + pad).encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("cursor malformed") from exc

    if not isinstance(payload, dict):
        raise ValueError("cursor malformed")

    missing = CURSOR_REQUIRED_FIELDS - set(payload.keys())
    if missing:
        raise ValueError(f"cursor missing fields: {sorted(missing)}")

    stream_id = _normalize_non_empty_text(payload.get("stream_id"))
    stream_epoch = _normalize_non_empty_text(payload.get("stream_epoch"))
    if stream_id is None:
        raise ValueError("cursor stream_id must be non-empty")
    if stream_epoch is None:
        raise ValueError("cursor stream_epoch must be non-empty")

    try:
        seq = int(payload.get("seq"))
    except Exception as exc:
        raise ValueError("cursor invalid seq") from exc
    if seq < 0:
        raise ValueError("cursor invalid seq")

    try:
        exp_unix_ms = int(payload.get("exp_unix_ms"))
    except Exception as exc:
        raise ValueError("cursor invalid exp_unix_ms") from exc
    if exp_unix_ms <= 0:
        raise ValueError("cursor invalid exp_unix_ms")

    sig = _normalize_non_empty_text(payload.get("sig"))
    if sig is None:
        raise ValueError("invalid cursor signature")

    signable_payload = {
        "stream_id": stream_id,
        "stream_epoch": stream_epoch,
        "seq": seq,
        "exp_unix_ms": exp_unix_ms,
    }
    if "iat_unix_ms" in payload:
        try:
            iat_unix_ms = int(payload.get("iat_unix_ms"))
        except Exception as exc:
            raise ValueError("cursor invalid iat_unix_ms") from exc
        if iat_unix_ms <= 0 or iat_unix_ms > exp_unix_ms:
            raise ValueError("cursor invalid iat_unix_ms")
        signable_payload["iat_unix_ms"] = iat_unix_ms

    if "retention_until_unix_ms" in payload:
        try:
            retention_until_unix_ms = int(payload.get("retention_until_unix_ms"))
        except Exception as exc:
            raise ValueError("cursor invalid retention_until_unix_ms") from exc
        if retention_until_unix_ms <= 0 or retention_until_unix_ms > exp_unix_ms:
            raise ValueError("cursor invalid retention_until_unix_ms")
        if (
            "iat_unix_ms" in signable_payload
            and retention_until_unix_ms < signable_payload["iat_unix_ms"]
        ):
            raise ValueError("cursor invalid retention_until_unix_ms")
        signable_payload["retention_until_unix_ms"] = retention_until_unix_ms
    signable = json.dumps(signable_payload, separators=(",", ":"), sort_keys=True)
    expected_sig = hmac.new(
        _cursor_secret().encode("utf-8"),
        signable.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("invalid cursor signature")

    if exp_unix_ms < int(time.time() * 1000):
        raise ValueError("cursor expired")
    retention_until = signable_payload.get("retention_until_unix_ms", exp_unix_ms)
    if retention_until < int(time.time() * 1000):
        raise ValueError("cursor out of retention")

    parsed = dict(signable_payload)
    parsed["sig"] = sig
    return parsed


def _next_request_id() -> str:
    return uuid4().hex


def _resolve_supported_features() -> set[str]:
    env = os.getenv("NEXUS_SUPPORTED_FEATURES", "")
    features = {token.strip() for token in env.split(",") if token.strip()}
    if features:
        return features
    return set(SUPPORTED_FEATURE_FLAGS)


def _normalize_feature_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, str):
            continue
        token = entry.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _derive_default_resource_version(result: dict[str, Any]) -> str:
    for field in ("resource_version", "version", "task_id", "id"):
        value = result.get(field)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized if field == "resource_version" else f"rv:{normalized}"
    return "rv:unspecified"


def _extract_explicit_resource_version(result: dict[str, Any]) -> str | None:
    if "resource_version" not in result:
        return None
    value = result.get("resource_version")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _validate_mutation_conflict_policy(
    *,
    method: str | None,
    params: dict[str, Any] | None,
    result: dict[str, Any],
) -> None:
    if method not in MUTATING_METHODS:
        return
    if not isinstance(params, dict):
        return
    scale_profile = params.get("scale_profile")
    if not isinstance(scale_profile, dict):
        return

    expected = scale_profile.get("expected_version")
    if expected is None:
        return
    expected_version = str(expected).strip()
    if not expected_version:
        return

    current_version = _extract_explicit_resource_version(result)
    if current_version is None or current_version == expected_version:
        return

    conflict_policy = str(scale_profile.get("conflict_policy") or "last_write_wins").strip()
    if conflict_policy not in {"last_write_wins", "vector_clock", "reject_on_conflict"}:
        conflict_policy = "last_write_wins"

    if conflict_policy == "last_write_wins":
        return

    if conflict_policy == "vector_clock":
        raise ProtocolValidationError(
            "conflict: vector_clock requires merge or manual resolution; "
            f"expected_version={expected_version} current_version={current_version}"
        )

    raise ProtocolValidationError(
        "conflict: reject_on_conflict violation; "
        f"expected_version={expected_version} current_version={current_version}"
    )


def _validate_mutation_response_metadata(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result)

    resource_version = str(payload.get("resource_version", "")).strip()
    if not resource_version:
        raise ProtocolValidationError("resource_version must be a non-empty string")

    region_served = str(payload.get("region_served", "")).strip()
    if not region_served:
        raise ProtocolValidationError("region_served must be a non-empty string")

    consistency_applied = str(payload.get("consistency_applied", "")).strip()
    if consistency_applied not in SCALE_CONSISTENCY_LEVELS:
        raise ProtocolValidationError(
            "consistency_applied must be one of "
            f"{sorted(SCALE_CONSISTENCY_LEVELS)}"
        )

    scale_profile = str(payload.get("scale_profile", "")).strip()
    if scale_profile != SCALE_PROFILE_VERSION:
        raise ProtocolValidationError(f"scale_profile must be '{SCALE_PROFILE_VERSION}'")

    accepted_features_raw = payload.get("accepted_features", [])
    if not isinstance(accepted_features_raw, list):
        raise ProtocolValidationError("accepted_features must be a list")
    accepted_features: list[str] = []
    seen: set[str] = set()
    for idx, feature in enumerate(accepted_features_raw):
        if not isinstance(feature, str) or not feature.strip():
            raise ProtocolValidationError(
                f"accepted_features[{idx}] must be a non-empty string"
            )
        normalized = feature.strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        accepted_features.append(normalized)

    payload["resource_version"] = resource_version
    payload["region_served"] = region_served
    payload["consistency_applied"] = consistency_applied
    payload["scale_profile"] = scale_profile
    payload["accepted_features"] = accepted_features
    return payload


def _apply_mutation_response_metadata(
    result: dict[str, Any],
    *,
    method: str | None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if method not in MUTATING_METHODS:
        return dict(result)

    payload = dict(result)
    scale_profile = params.get("scale_profile") if isinstance(params, dict) else None
    if not isinstance(scale_profile, dict):
        scale_profile = {}

    supported_features = _resolve_supported_features()
    required = _normalize_feature_list(scale_profile.get("features_required"))
    optional = _normalize_feature_list(scale_profile.get("features_optional"))
    accepted_features = [f for f in [*required, *optional] if f in supported_features]

    payload.setdefault("resource_version", _derive_default_resource_version(payload))
    payload.setdefault("consistency_applied", str(scale_profile.get("write_consistency") or "eventual"))
    payload.setdefault("region_served", str(os.getenv("NEXUS_REGION", "local")))
    payload.setdefault("accepted_features", accepted_features)
    payload.setdefault("scale_profile", SCALE_PROFILE_VERSION)
    return _validate_mutation_response_metadata(payload)


def make_request(
    method: str, params: dict[str, Any], request_id: str | None = None
) -> dict[str, Any]:
    """Build a JSON-RPC request with basic method validation."""

    if method not in A2A_METHODS:
        raise ProtocolValidationError(f"Unsupported method: {method}")
    if not isinstance(params, dict):
        raise ProtocolValidationError("params must be a dictionary")

    normalized_params = dict(params)
    normalized_params.setdefault("scenario_context", {})
    normalized_params.setdefault("correlation", {})
    normalized_params.setdefault("idempotency", {})

    return {
        "jsonrpc": "2.0",
        "id": request_id or _next_request_id(),
        "method": method,
        "params": normalized_params,
    }


def make_result(
    request_id: str,
    result: dict[str, Any],
    *,
    method: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ProtocolValidationError("result must be a dictionary")
    _validate_mutation_conflict_policy(method=method, params=params, result=result)
    payload_result = _apply_mutation_response_metadata(result, method=method, params=params)
    return {"jsonrpc": "2.0", "id": request_id, "result": payload_result}


def make_error(
    request_id: str | None,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
    *,
    retryable: bool | None = None,
    retry_after_ms: int | None = None,
    failure_domain: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    payload = make_error_data(
        data,
        retryable=retryable,
        retry_after_ms=retry_after_ms,
        failure_domain=failure_domain,
    )
    if payload:
        error["data"] = payload
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def make_error_data(
    data: dict[str, Any] | None = None,
    *,
    retryable: bool | None = None,
    retry_after_ms: int | None = None,
    failure_domain: str | None = None,
) -> dict[str, Any]:
    payload = dict(data or {})
    if retry_after_ms is not None and retry_after_ms < 0:
        raise ProtocolValidationError("retry_after_ms must be >= 0")
    if failure_domain is not None and failure_domain not in FAILURE_DOMAINS:
        raise ProtocolValidationError(f"failure_domain must be one of {sorted(FAILURE_DOMAINS)}")
    if retryable is not None:
        payload["retryable"] = retryable
    if retry_after_ms is not None:
        payload["retry_after_ms"] = retry_after_ms
    if failure_domain is not None:
        payload["failure_domain"] = failure_domain
    return payload


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
        for field in ("scenario_context", "correlation", "idempotency"):
            value = params.get(field, {})
            if value is not None and not isinstance(value, dict):
                raise ProtocolValidationError(f"request {field} must be a dictionary")
        if method in MUTATING_METHODS:
            _validate_scale_profile_contract(params)
            _validate_strict_idempotency_contract(params)
        if method == "tasks/resubscribe":
            _validate_resubscribe_cursor_contract(params)

    if "error" in payload:
        error = payload["error"]
        if not isinstance(error, dict):
            raise ProtocolValidationError("error must be a dictionary")
        if "code" not in error or "message" not in error:
            raise ProtocolValidationError("error must include code and message")
        if "data" in error and not isinstance(error["data"], dict):
            raise ProtocolValidationError("error.data must be a dictionary when provided")

    return payload


def _validate_scale_profile_contract(params: dict[str, Any]) -> None:
    profile = params.get("scale_profile")
    if not isinstance(profile, dict):
        raise ProtocolValidationError("request scale_profile must be a dictionary")
    for field in SCALE_REQUIRED_FIELDS:
        value = profile.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ProtocolValidationError(f"request scale_profile missing required field: {field}")
    if profile.get("profile") != SCALE_PROFILE_VERSION:
        raise ProtocolValidationError("request scale_profile.profile must be 'nexus-scale-v1.1'")
    canonical_ok, canonical_reason, expected_shard_key = _validate_canonical_shard_key(profile)
    if not canonical_ok:
        if canonical_reason == "non_canonical_shard_key" and expected_shard_key:
            raise ProtocolValidationError(
                "request scale_profile.shard_key non_canonical_shard_key: "
                f"expected {expected_shard_key}"
            )
        raise ProtocolValidationError(
            "request scale_profile.shard_key invalid_shard_key_format: "
            "expected 'sha256:<64 lowercase hex>'"
        )


def _validate_strict_idempotency_contract(params: dict[str, Any]) -> None:
    idempotency = params.get("idempotency")
    if not isinstance(idempotency, dict):
        raise ProtocolValidationError("request idempotency must be a dictionary")
    for field in STRICT_IDEMPOTENCY_FIELDS:
        if field not in idempotency:
            raise ProtocolValidationError(f"request idempotency missing required field: {field}")
    dedup_window_ms = idempotency.get("dedup_window_ms")
    try:
        dedup_value = int(dedup_window_ms)
    except Exception as exc:
        raise ProtocolValidationError("request idempotency.dedup_window_ms must be an integer") from exc
    if dedup_value <= 0:
        raise ProtocolValidationError("request idempotency.dedup_window_ms must be > 0")


def _validate_resubscribe_cursor_contract(params: dict[str, Any]) -> None:
    cursor = params.get("cursor")
    try:
        _parse_resume_cursor(cursor)
    except Exception as exc:
        raise ProtocolValidationError(f"request cursor invalid: {exc}") from exc

    max_catchup_events = params.get("max_catchup_events")
    if max_catchup_events is not None:
        max_catchup_policy = int(os.getenv("NEXUS_RESUBSCRIBE_MAX_CATCHUP_EVENTS", "10000"))
        try:
            catchup = int(max_catchup_events)
        except Exception as exc:
            raise ProtocolValidationError(
                "request max_catchup_events must be a positive integer"
            ) from exc
        if catchup <= 0:
            raise ProtocolValidationError("request max_catchup_events must be > 0")
        if catchup > max_catchup_policy:
            raise ProtocolValidationError(
                "request max_catchup_events exceeds retention policy: "
                f"max={max_catchup_policy} requested={catchup}"
            )

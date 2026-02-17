"""Scale profile helpers for NEXUS A2A protocol v1.1."""

from __future__ import annotations

import hashlib
import os
from typing import Any

SCALE_PROFILE_VERSION = "nexus-scale-v1.1"
MUTATING_METHODS = {"tasks/send", "tasks/sendSubscribe", "tasks/cancel"}
SCALE_REQUIRED_FIELDS = ("profile", "tenant_key", "user_key", "task_key", "shard_key")
STRICT_IDEMPOTENCY_FIELDS = ("idempotency_key", "scope", "dedup_window_ms", "payload_hash")
SHARD_KEY_PREFIX = "sha256:"
ROUTING_KEY_SEPARATOR = "\x1f"

SUPPORTED_FEATURE_FLAGS = {
    "routing.v1",
    "stream.resume.v1",
    "admission.v1",
    "idempotency.strict.v1",
    "consistency.versioning.v1",
    "consistency.vectorclock.v1",
}


def scale_profile_strict_enabled() -> bool:
    return os.getenv("NEXUS_SCALE_PROFILE_STRICT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def should_enforce_scale_profile(method: str, params: dict[str, Any]) -> bool:
    if method not in MUTATING_METHODS:
        return False
    if scale_profile_strict_enabled():
        return True
    profile = params.get("scale_profile")
    if not isinstance(profile, dict):
        return False
    return str(profile.get("profile", "")).strip() == SCALE_PROFILE_VERSION


def _normalize_non_empty_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def build_canonical_shard_key(*, tenant_key: str, user_key: str, task_key: str) -> str:
    """Build deterministic shard key from tenant/user/task routing tuple."""
    tenant = _normalize_non_empty_text(tenant_key)
    user = _normalize_non_empty_text(user_key)
    task = _normalize_non_empty_text(task_key)
    if tenant is None or user is None or task is None:
        raise ValueError("tenant_key, user_key, and task_key must be non-empty strings")

    routing_material = ROUTING_KEY_SEPARATOR.join((tenant, user, task)).encode("utf-8")
    digest = hashlib.sha256(routing_material).hexdigest()
    return f"{SHARD_KEY_PREFIX}{digest}"


def validate_canonical_shard_key(
    scale_profile: dict[str, Any],
) -> tuple[bool, str | None, str | None]:
    """Validate shard key format and canonical routing derivation."""
    tenant = _normalize_non_empty_text(scale_profile.get("tenant_key"))
    user = _normalize_non_empty_text(scale_profile.get("user_key"))
    task = _normalize_non_empty_text(scale_profile.get("task_key"))
    shard_key = _normalize_non_empty_text(scale_profile.get("shard_key"))

    if tenant is None or user is None or task is None or shard_key is None:
        return False, "missing_routing_field", None

    if not shard_key.startswith(SHARD_KEY_PREFIX):
        return False, "invalid_shard_key_format", None

    digest = shard_key[len(SHARD_KEY_PREFIX) :]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        return False, "invalid_shard_key_format", None

    expected = build_canonical_shard_key(
        tenant_key=tenant,
        user_key=user,
        task_key=task,
    )
    if shard_key != expected:
        return False, "non_canonical_shard_key", expected
    return True, None, expected


def validate_scale_profile_fields(scale_profile: dict[str, Any]) -> tuple[bool, str | None]:
    for field in SCALE_REQUIRED_FIELDS:
        value = scale_profile.get(field)
        if not isinstance(value, str) or not value.strip():
            return False, field
    if scale_profile.get("profile") != SCALE_PROFILE_VERSION:
        return False, "profile"
    return True, None


def validate_strict_idempotency_fields(idempotency: dict[str, Any]) -> tuple[bool, str | None]:
    for field in STRICT_IDEMPOTENCY_FIELDS:
        if field not in idempotency:
            return False, field
    if not isinstance(idempotency.get("idempotency_key"), str) or not idempotency["idempotency_key"].strip():
        return False, "idempotency_key"
    if not isinstance(idempotency.get("scope"), str) or not idempotency["scope"].strip():
        return False, "scope"
    if not isinstance(idempotency.get("payload_hash"), str) or not idempotency["payload_hash"].strip():
        return False, "payload_hash"
    try:
        dedup_window_ms = int(idempotency.get("dedup_window_ms"))
    except Exception:
        return False, "dedup_window_ms"
    if dedup_window_ms <= 0:
        return False, "dedup_window_ms"
    return True, None


def negotiate_scale_features(
    required: list[str] | None,
    optional: list[str] | None = None,
    *,
    supported: set[str] | None = None,
) -> dict[str, Any]:
    supported_set = set(supported or SUPPORTED_FEATURE_FLAGS)
    required_set = {str(f).strip() for f in (required or []) if str(f).strip()}
    optional_set = {str(f).strip() for f in (optional or []) if str(f).strip()}

    missing_required = sorted(required_set - supported_set)
    accepted_required = sorted(required_set & supported_set)
    accepted_optional = sorted(optional_set & supported_set)
    unsupported_optional = sorted(optional_set - supported_set)

    return {
        "accepted": len(missing_required) == 0,
        "missing_required": missing_required,
        "accepted_required": accepted_required,
        "accepted_optional": accepted_optional,
        "unsupported_optional": unsupported_optional,
        "supported_features": sorted(supported_set),
        "profile": SCALE_PROFILE_VERSION,
    }


def _normalize_feature_list(
    features: list[Any],
    *,
    field_name: str,
) -> tuple[list[str] | None, str | None]:
    normalized: list[str] = []
    seen: set[str] = set()
    for idx, feature in enumerate(features):
        if not isinstance(feature, str):
            return None, f"{field_name}[{idx}]"
        token = feature.strip()
        if not token:
            return None, f"{field_name}[{idx}]"
        if token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized, None


def resolve_supported_features(
    *,
    supported: set[str] | None = None,
    supported_env: str | None = None,
) -> set[str]:
    if supported is not None:
        return {str(token).strip() for token in supported if str(token).strip()}

    env_value = supported_env
    if env_value is None:
        env_value = os.getenv("NEXUS_SUPPORTED_FEATURES", "")

    normalized_env = {token.strip() for token in str(env_value).split(",") if token.strip()}
    if normalized_env:
        return normalized_env
    return set(SUPPORTED_FEATURE_FLAGS)


def evaluate_feature_negotiation(
    scale_profile: dict[str, Any],
    *,
    supported: set[str] | None = None,
    supported_env: str | None = None,
) -> dict[str, Any]:
    """Evaluate required/optional feature negotiation for a scale profile.

    Returns a dictionary that always includes:
    - accepted: bool
    - error_type: None | "invalid_params" | "unsupported_feature"
    - reason: None | protocol reason string
    - field: optional field name for invalid params
    Plus the negotiated feature sets when parsing succeeds.
    """
    required_raw = scale_profile.get("features_required", [])
    optional_raw = scale_profile.get("features_optional", [])

    if required_raw is None:
        required_raw = []
    if optional_raw is None:
        optional_raw = []

    if not isinstance(required_raw, list):
        return {
            "accepted": False,
            "error_type": "invalid_params",
            "reason": "invalid_features_required",
            "field": "features_required",
        }
    if not isinstance(optional_raw, list):
        return {
            "accepted": False,
            "error_type": "invalid_params",
            "reason": "invalid_features_optional",
            "field": "features_optional",
        }

    required, required_invalid = _normalize_feature_list(
        required_raw,
        field_name="features_required",
    )
    if required_invalid:
        return {
            "accepted": False,
            "error_type": "invalid_params",
            "reason": "invalid_feature_entry",
            "field": required_invalid,
        }

    optional, optional_invalid = _normalize_feature_list(
        optional_raw,
        field_name="features_optional",
    )
    if optional_invalid:
        return {
            "accepted": False,
            "error_type": "invalid_params",
            "reason": "invalid_feature_entry",
            "field": optional_invalid,
        }

    supported_features = resolve_supported_features(
        supported=supported,
        supported_env=supported_env,
    )
    negotiation = negotiate_scale_features(
        required=required,
        optional=optional,
        supported=supported_features,
    )
    outcome = dict(negotiation)
    outcome["error_type"] = None
    outcome["reason"] = None
    outcome["field"] = None
    if not outcome["accepted"]:
        outcome["error_type"] = "unsupported_feature"
        outcome["reason"] = "unsupported_feature"
    return outcome


def build_scale_response_metadata(
    *,
    resource_version: str,
    consistency_applied: str,
    accepted_features: list[str] | None = None,
    region_served: str | None = None,
) -> dict[str, Any]:
    return {
        "resource_version": str(resource_version),
        "consistency_applied": str(consistency_applied),
        "region_served": str(region_served or os.getenv("NEXUS_REGION", "local")),
        "accepted_features": list(accepted_features or []),
        "scale_profile": SCALE_PROFILE_VERSION,
    }

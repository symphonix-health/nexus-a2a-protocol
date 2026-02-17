"""Protocol contract helpers for NEXUS-A2A task execution envelopes.

Defines shared contract payloads for:
- Scenario context on task envelopes
- Correlation context across RPC calls/events
- Idempotency semantics under retry/load
- Progress-state payload normalization
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .scale_profile import (
    build_canonical_shard_key,
    build_scale_response_metadata,
    evaluate_feature_negotiation,
)

PROGRESS_STATES = {"accepted", "working", "final", "error", "cancelled"}
FAILURE_DOMAINS = {"agent", "network", "validation"}
SCALE_PROFILE_NAME = "nexus-scale-v1.1"
SCALE_CONSISTENCY_LEVELS = {"eventual", "local_quorum", "global_quorum"}
SCALE_CONFLICT_POLICIES = {"last_write_wins", "vector_clock", "reject_on_conflict"}
VECTOR_CLOCK_RESOLUTION_VALUES = {
    "manual_or_merge_required",
    "winner_selected",
    "merge_applied",
}
MUTATING_METHODS = {"tasks/send", "tasks/sendSubscribe", "tasks/cancel"}


def _require_non_empty(value: str | None, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


@dataclass(slots=True)
class ScenarioContext:
    scenario_id: str
    visit_id: str
    journey_step: str
    phase: str
    deadline_ms: int

    def __post_init__(self) -> None:
        self.scenario_id = _require_non_empty(self.scenario_id, "scenario_id")
        self.visit_id = _require_non_empty(self.visit_id, "visit_id")
        self.journey_step = _require_non_empty(self.journey_step, "journey_step")
        self.phase = _require_non_empty(self.phase, "phase")
        if self.deadline_ms <= 0:
            raise ValueError("deadline_ms must be > 0")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CorrelationContext:
    trace_id: str
    parent_task_id: str | None = None
    causation_id: str | None = None

    def __post_init__(self) -> None:
        self.trace_id = _require_non_empty(self.trace_id, "trace_id")
        if self.parent_task_id is not None:
            self.parent_task_id = _require_non_empty(self.parent_task_id, "parent_task_id")
        if self.causation_id is not None:
            self.causation_id = _require_non_empty(self.causation_id, "causation_id")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class IdempotencyContext:
    idempotency_key: str
    dedup_window_ms: int = 60000

    def __post_init__(self) -> None:
        self.idempotency_key = _require_non_empty(self.idempotency_key, "idempotency_key")
        if self.dedup_window_ms <= 0:
            raise ValueError("dedup_window_ms must be > 0")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProgressState:
    state: str
    percent: float | None = None
    eta_ms: int | None = None

    def __post_init__(self) -> None:
        normalized = self.state.strip().lower()
        if normalized == "canceled":
            normalized = "cancelled"
        if normalized not in PROGRESS_STATES:
            raise ValueError(f"state must be one of {sorted(PROGRESS_STATES)}")
        self.state = normalized

        if self.percent is not None and not (0.0 <= self.percent <= 100.0):
            raise ValueError("percent must be between 0 and 100")
        if self.eta_ms is not None and self.eta_ms < 0:
            raise ValueError("eta_ms must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ScaleProfileContext:
    profile: str
    tenant_key: str
    user_key: str
    task_key: str
    shard_key: str
    region_hint: str | None = None
    write_consistency: str = "eventual"
    conflict_policy: str = "last_write_wins"
    expected_version: str | None = None
    features_required: list[str] | None = None
    features_optional: list[str] | None = None

    def __post_init__(self) -> None:
        self.profile = _require_non_empty(self.profile, "profile")
        self.tenant_key = _require_non_empty(self.tenant_key, "tenant_key")
        self.user_key = _require_non_empty(self.user_key, "user_key")
        self.task_key = _require_non_empty(self.task_key, "task_key")
        self.shard_key = _require_non_empty(self.shard_key, "shard_key")
        expected_shard_key = build_canonical_shard_key(
            tenant_key=self.tenant_key,
            user_key=self.user_key,
            task_key=self.task_key,
        )
        if self.shard_key != expected_shard_key:
            raise ValueError(
                "shard_key must match canonical routing hash derived from "
                f"tenant_key/user_key/task_key (expected {expected_shard_key})"
            )
        if self.region_hint is not None:
            self.region_hint = _require_non_empty(self.region_hint, "region_hint")
        if self.write_consistency not in SCALE_CONSISTENCY_LEVELS:
            raise ValueError(
                f"write_consistency must be one of {sorted(SCALE_CONSISTENCY_LEVELS)}"
            )
        if self.conflict_policy not in SCALE_CONFLICT_POLICIES:
            raise ValueError(f"conflict_policy must be one of {sorted(SCALE_CONFLICT_POLICIES)}")
        if self.expected_version is not None:
            self.expected_version = _require_non_empty(self.expected_version, "expected_version")
        if self.features_required is not None:
            self.features_required = [f for f in self.features_required if str(f).strip()]
        if self.features_optional is not None:
            self.features_optional = [f for f in self.features_optional if str(f).strip()]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


def build_task_envelope(
    task: dict[str, Any],
    scenario_context: ScenarioContext | None = None,
    correlation: CorrelationContext | None = None,
    idempotency: IdempotencyContext | None = None,
    progress: ProgressState | None = None,
    scale_profile: ScaleProfileContext | None = None,
) -> dict[str, Any]:
    """Build a task envelope containing standard protocol contract fields."""
    envelope: dict[str, Any] = {"task": dict(task)}
    if scenario_context is not None:
        envelope["scenario_context"] = scenario_context.to_dict()
    if correlation is not None:
        envelope["correlation"] = correlation.to_dict()
    if idempotency is not None:
        envelope["idempotency"] = idempotency.to_dict()
    if progress is not None:
        envelope["progress"] = progress.to_dict()
    if scale_profile is not None:
        envelope["scale_profile"] = scale_profile.to_dict()
    return envelope


def _derive_default_resource_version(result: dict[str, Any]) -> str:
    for field in ("resource_version", "version", "task_id", "id"):
        value = result.get(field)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return f"rv:{normalized}" if field != "resource_version" else normalized
    return "rv:unspecified"


def _extract_explicit_resource_version(result: dict[str, Any]) -> str | None:
    if "resource_version" not in result:
        return None
    value = result.get("resource_version")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def evaluate_mutation_conflict(
    *,
    method: str | None,
    scale_profile: dict[str, Any] | None,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    """Evaluate deterministic conflict-policy outcome for mutating responses.

    Returns conflict payload when request must be rejected under
    `reject_on_conflict` or `vector_clock`. Returns None when no conflict
    enforcement is required.
    """
    if method not in MUTATING_METHODS:
        return None
    if not isinstance(scale_profile, dict):
        return None

    expected_version = scale_profile.get("expected_version")
    if expected_version is None:
        return None
    expected = str(expected_version).strip()
    if not expected:
        return None

    current = _extract_explicit_resource_version(result)
    if current is None:
        # Cannot enforce deterministic conflict outcome if runtime did not
        # provide concrete resource version.
        return None

    if current == expected:
        return None

    policy = str(scale_profile.get("conflict_policy") or "last_write_wins").strip()
    if policy not in SCALE_CONFLICT_POLICIES:
        policy = "last_write_wins"

    if policy == "last_write_wins":
        return None

    payload: dict[str, Any] = {
        "reason": "conflict",
        "conflict_policy": policy,
        "expected_version": expected,
        "current_version": current,
    }

    if policy == "vector_clock":
        payload["competing_versions"] = [
            {"version": expected, "source": "expected"},
            {"version": current, "source": "current"},
        ]
        payload["causality"] = {
            "policy": "vector_clock",
            "resolution": "manual_or_merge_required",
            "winner": None,
        }
        return validate_vector_clock_conflict_payload(payload)

    return payload


def validate_vector_clock_conflict_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize deterministic vector-clock conflict payload schema."""
    normalized = dict(payload)
    reason = normalized.get("reason")
    if not isinstance(reason, str) or reason.strip() != "conflict":
        raise ValueError("vector clock conflict payload reason must be 'conflict'")
    conflict_policy = normalized.get("conflict_policy")
    if not isinstance(conflict_policy, str) or conflict_policy.strip() != "vector_clock":
        raise ValueError("vector clock conflict payload policy must be 'vector_clock'")

    expected_raw = normalized.get("expected_version")
    if not isinstance(expected_raw, str) or not expected_raw.strip():
        raise ValueError("vector clock conflict payload expected_version must be non-empty")
    expected_version = expected_raw.strip()

    current_raw = normalized.get("current_version")
    if not isinstance(current_raw, str) or not current_raw.strip():
        raise ValueError("vector clock conflict payload current_version must be non-empty")
    current_version = current_raw.strip()

    raw_versions = normalized.get("competing_versions")
    if not isinstance(raw_versions, list):
        raise ValueError("vector clock conflict payload competing_versions must be a list")
    competing_versions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for idx, entry in enumerate(raw_versions):
        if not isinstance(entry, dict):
            raise ValueError(f"competing_versions[{idx}] must be an object")
        version_raw = entry.get("version")
        source_raw = entry.get("source")
        if not isinstance(version_raw, str) or not version_raw.strip():
            raise ValueError(f"competing_versions[{idx}].version must be non-empty")
        if not isinstance(source_raw, str) or not source_raw.strip():
            raise ValueError(f"competing_versions[{idx}].source must be non-empty")
        version = version_raw.strip()
        source = source_raw.strip()
        key = (version, source)
        if key in seen:
            continue
        seen.add(key)
        competing_versions.append({"version": version, "source": source})
    if len(competing_versions) < 2:
        raise ValueError("vector clock conflict payload requires >=2 competing_versions")

    raw_causality = normalized.get("causality")
    if not isinstance(raw_causality, dict):
        raise ValueError("vector clock conflict payload causality must be an object")

    causality_policy_raw = raw_causality.get("policy")
    if not isinstance(causality_policy_raw, str) or causality_policy_raw.strip() != "vector_clock":
        raise ValueError("vector clock conflict payload causality.policy must be 'vector_clock'")

    causality_resolution_raw = raw_causality.get("resolution")
    if not isinstance(causality_resolution_raw, str):
        raise ValueError(
            "vector clock conflict payload causality.resolution must be one of "
            f"{sorted(VECTOR_CLOCK_RESOLUTION_VALUES)}"
        )
    causality_resolution = causality_resolution_raw.strip()
    if causality_resolution not in VECTOR_CLOCK_RESOLUTION_VALUES:
        raise ValueError(
            "vector clock conflict payload causality.resolution must be one of "
            f"{sorted(VECTOR_CLOCK_RESOLUTION_VALUES)}"
        )

    winner_raw = raw_causality.get("winner")
    winner: str | None = None
    if winner_raw is not None:
        if not isinstance(winner_raw, str) or not winner_raw.strip():
            raise ValueError("vector clock conflict payload causality.winner must be non-empty or null")
        winner = winner_raw.strip()
        allowed_winners = {entry["version"] for entry in competing_versions}
        if winner not in allowed_winners:
            raise ValueError(
                "vector clock conflict payload causality.winner must match competing_versions.version"
            )

    normalized["expected_version"] = expected_version
    normalized["current_version"] = current_version
    normalized["competing_versions"] = competing_versions
    normalized["causality"] = {
        "policy": "vector_clock",
        "resolution": causality_resolution,
        "winner": winner,
    }
    return normalized


def validate_mutation_response_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Validate required mutation response metadata contract and normalize fields."""
    payload = dict(result)

    resource_version = str(payload.get("resource_version", "")).strip()
    if not resource_version:
        raise ValueError("resource_version must be a non-empty string")

    region_served = str(payload.get("region_served", "")).strip()
    if not region_served:
        raise ValueError("region_served must be a non-empty string")

    consistency_applied = str(payload.get("consistency_applied", "")).strip()
    if consistency_applied not in SCALE_CONSISTENCY_LEVELS:
        raise ValueError(
            f"consistency_applied must be one of {sorted(SCALE_CONSISTENCY_LEVELS)}"
        )

    scale_profile = str(payload.get("scale_profile", "")).strip()
    if scale_profile != SCALE_PROFILE_NAME:
        raise ValueError(f"scale_profile must be '{SCALE_PROFILE_NAME}'")

    accepted_features_raw = payload.get("accepted_features", [])
    if not isinstance(accepted_features_raw, list):
        raise ValueError("accepted_features must be a list")
    accepted_features: list[str] = []
    seen: set[str] = set()
    for idx, feature in enumerate(accepted_features_raw):
        if not isinstance(feature, str) or not feature.strip():
            raise ValueError(f"accepted_features[{idx}] must be a non-empty string")
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


def apply_mutation_response_metadata(
    result: dict[str, Any],
    *,
    method: str | None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach required scale metadata for mutating method success responses.

    The metadata keys are:
    - resource_version
    - region_served
    - consistency_applied
    """
    if method not in MUTATING_METHODS:
        return dict(result)

    payload = dict(result)
    scale_profile = params.get("scale_profile") if isinstance(params, dict) else None

    accepted_features: list[str] = []
    if isinstance(scale_profile, dict):
        negotiation = evaluate_feature_negotiation(scale_profile)
        if negotiation.get("accepted"):
            accepted_features = [
                *negotiation.get("accepted_required", []),
                *negotiation.get("accepted_optional", []),
            ]

    consistency_applied = str(
        payload.get("consistency_applied")
        or (scale_profile or {}).get("write_consistency")
        or "eventual"
    )
    resource_version = str(payload.get("resource_version") or _derive_default_resource_version(payload))
    region_served = payload.get("region_served")
    metadata = build_scale_response_metadata(
        resource_version=resource_version,
        consistency_applied=consistency_applied,
        accepted_features=accepted_features,
        region_served=str(region_served) if region_served is not None else None,
    )

    for key, value in metadata.items():
        payload.setdefault(key, value)

    return validate_mutation_response_metadata(payload)

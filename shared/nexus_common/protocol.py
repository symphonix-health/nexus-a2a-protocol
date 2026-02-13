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

PROGRESS_STATES = {"accepted", "working", "final", "error", "cancelled"}
FAILURE_DOMAINS = {"agent", "network", "validation"}


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


def build_task_envelope(
    task: dict[str, Any],
    scenario_context: ScenarioContext | None = None,
    correlation: CorrelationContext | None = None,
    idempotency: IdempotencyContext | None = None,
    progress: ProgressState | None = None,
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
    return envelope

"""Trace event models for clinical scenario traceability.

Provides structured data models for capturing step-by-step request/response
traces across HelixCare patient journey scenarios, with built-in support for
correlation IDs, duration tracking, and redaction metadata.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

TRACE_STATUSES = {"accepted", "working", "final", "error"}


def _make_correlation_id() -> str:
    return f"corr-{uuid.uuid4()}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceStepEvent:
    """One step in a patient journey trace."""

    trace_id: str
    correlation_id: str
    scenario_name: str
    patient_id: str
    visit_id: str
    agent: str
    method: str
    step_index: int
    timestamp_start: str
    timestamp_end: str
    duration_ms: float
    status: str  # accepted | working | final | error
    request_redacted: dict[str, Any]
    response_redacted: dict[str, Any]
    redaction_meta: dict[str, Any]
    retry_count: int = 0
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in TRACE_STATUSES:
            raise ValueError(f"status must be one of {sorted(TRACE_STATUSES)}, got '{self.status}'")
        if not self.trace_id:
            raise ValueError("trace_id must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Strip None optional fields for cleaner JSON
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class TraceRun:
    """Complete trace of a single scenario run (all steps)."""

    trace_id: str
    scenario_name: str
    visit_id: str
    patient_id: str
    patient_profile: dict[str, Any]
    started_at: str
    completed_at: str | None = None
    status: str = "working"  # working | final | error
    steps: list[TraceStepEvent] = field(default_factory=list)
    total_duration_ms: float = 0.0
    delegation_chain: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("trace_id must be non-empty")

    def add_step(self, step: TraceStepEvent) -> None:
        self.steps.append(step)
        self.total_duration_ms = sum(s.duration_ms for s in self.steps)

    def finalize(self, status: str = "final") -> None:
        self.status = status
        self.completed_at = _utc_now_iso()
        self.total_duration_ms = sum(s.duration_ms for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "scenario_name": self.scenario_name,
            "visit_id": self.visit_id,
            "patient_id": self.patient_id,
            "patient_profile": self.patient_profile,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_ms": round(self.total_duration_ms, 2),
            "step_count": len(self.steps),
            "delegation_chain": self.delegation_chain,
        }

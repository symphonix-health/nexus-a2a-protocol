"""Intelligent clinical delegation engine.

Informed by Tomasev, Franklin & Osindero, *Intelligent AI Delegation*
(arXiv:2602.11865v1, Feb 2026).  Implements lightweight handoff validation,
context chaining, and delegation monitoring for HelixCare scenario execution.

Key concepts from the paper:
  - Task decomposition & assignment (§4.1-4.2)
  - Adaptive coordination  (§4.4)
  - Monitoring & verifiable completion (§4.5, §4.8)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Handoff policy (attached to individual scenario steps) ─────────


@dataclass
class HandoffPolicy:
    """Defines how one agent delegates to the next.

    Attributes:
        required_predecessors: Agent aliases that *must* have completed
            successfully before this step may execute.
        optional_predecessors: Agents whose output is useful but not
            blocking.
        required_context_keys: Dot-paths into ``clinical_context`` that
            must be non-empty for this step to proceed.
        fallback_action: ``skip`` | ``stub`` | ``fail``
            What to do when a required predecessor is missing.
        clinical_rationale: Free-text explanation of **why** this
            handoff makes clinical sense (structural transparency, §4.3).
    """

    required_predecessors: list[str] = field(default_factory=list)
    optional_predecessors: list[str] = field(default_factory=list)
    required_context_keys: list[str] = field(default_factory=list)
    fallback_action: str = "skip"  # skip | stub | fail
    clinical_rationale: str = ""


# ── Handoff validation ─────────────────────────────────────────────


@dataclass
class HandoffResult:
    """Outcome of a single handoff validation check."""

    allowed: bool
    skipped: bool = False
    reason: str = ""
    missing_predecessors: list[str] = field(default_factory=list)
    missing_context_keys: list[str] = field(default_factory=list)


def validate_handoff(
    policy: HandoffPolicy | dict[str, Any] | None,
    clinical_context: dict[str, Any],
    completed_agents: set[str],
    failed_agents: set[str],
) -> HandoffResult:
    """Check whether a step may execute given the current delegation state.

    Parameters
    ----------
    policy:
        The ``HandoffPolicy`` for the step, or a plain dict with the same
        keys, or ``None`` (in which case the step always proceeds).
    clinical_context:
        The accumulated clinical context dict.
    completed_agents:
        Set of agent aliases that finished with status ``final``.
    failed_agents:
        Set of agent aliases that finished with status ``error``.

    Returns
    -------
    HandoffResult
        ``allowed=True`` when the step may execute.
    """
    if policy is None:
        return HandoffResult(allowed=True)

    if isinstance(policy, dict):
        policy = HandoffPolicy(
            **{k: v for k, v in policy.items() if k in HandoffPolicy.__dataclass_fields__}
        )

    # Check required predecessors
    missing = [p for p in policy.required_predecessors if p not in completed_agents]
    failed_required = [p for p in missing if p in failed_agents]

    if missing:
        action = policy.fallback_action
        reason_parts = []
        if failed_required:
            reason_parts.append(f"Required predecessor(s) failed: {', '.join(failed_required)}")
        remaining_missing = [p for p in missing if p not in failed_agents]
        if remaining_missing:
            reason_parts.append(
                f"Required predecessor(s) not yet completed: {', '.join(remaining_missing)}"
            )
        reason = "; ".join(reason_parts)

        if action == "fail":
            return HandoffResult(
                allowed=False,
                reason=f"Handoff blocked — {reason}",
                missing_predecessors=missing,
            )
        if action == "skip":
            return HandoffResult(
                allowed=False,
                skipped=True,
                reason=f"Step skipped — {reason}",
                missing_predecessors=missing,
            )
        # action == "stub" → allow execution with stub data
        # (the step runs, but caller should note it's degraded)

    # Check required context keys
    missing_keys: list[str] = []
    for key_path in policy.required_context_keys:
        cursor: Any = clinical_context
        for segment in key_path.split("."):
            if isinstance(cursor, dict) and segment in cursor:
                cursor = cursor[segment]
            else:
                missing_keys.append(key_path)
                break

    if missing_keys:
        action = policy.fallback_action
        reason = f"Missing context keys: {', '.join(missing_keys)}"
        if action == "fail":
            return HandoffResult(
                allowed=False,
                reason=f"Handoff blocked — {reason}",
                missing_context_keys=missing_keys,
            )
        if action == "skip":
            return HandoffResult(
                allowed=False,
                skipped=True,
                reason=f"Step skipped — {reason}",
                missing_context_keys=missing_keys,
            )

    return HandoffResult(allowed=True)


# ── Delegation context builder ─────────────────────────────────────


def build_delegation_context(
    step: dict[str, Any],
    clinical_context: dict[str, Any],
    policy: HandoffPolicy | dict[str, Any] | None,
) -> dict[str, Any]:
    """Build enriched delegation context for a step.

    This adds a ``delegation`` key summarising which predecessor outputs
    are being forwarded and why, improving structural transparency (§4.3).
    """
    delegation_info: dict[str, Any] = {
        "delegating_to": step.get("agent", "unknown"),
        "method": step.get("method", ""),
    }

    if policy is not None:
        p = (
            policy
            if isinstance(policy, HandoffPolicy)
            else HandoffPolicy(
                **{k: v for k, v in policy.items() if k in HandoffPolicy.__dataclass_fields__}
            )
        )
        delegation_info["clinical_rationale"] = p.clinical_rationale
        delegation_info["required_predecessors"] = p.required_predecessors
        delegation_info["optional_predecessors"] = p.optional_predecessors

        # Attach predecessor outputs
        agent_outputs = clinical_context.get("agent_outputs", {})
        predecessor_data: dict[str, Any] = {}
        for pred in p.required_predecessors + p.optional_predecessors:
            if pred in agent_outputs:
                predecessor_data[pred] = agent_outputs[pred]
        if predecessor_data:
            delegation_info["predecessor_outputs"] = predecessor_data

    return delegation_info


# ── Delegation monitor ─────────────────────────────────────────────


@dataclass
class DelegationEvent:
    """One delegation transition in a scenario run."""

    from_agent: str
    to_agent: str
    step_index: int
    timestamp: str
    handoff_allowed: bool
    skipped: bool
    reason: str
    duration_ms: float = 0.0
    clinical_rationale: str = ""


class DelegationMonitor:
    """Tracks delegation events across a scenario run for traceability.

    Corresponds to the Monitoring requirement (§4.5) and Verifiable
    Task Completion (§4.8) from the paper.
    """

    def __init__(self) -> None:
        self.events: list[DelegationEvent] = []
        self._step_start: float | None = None

    def record_handoff(
        self,
        from_agent: str,
        to_agent: str,
        step_index: int,
        result: HandoffResult,
        clinical_rationale: str = "",
    ) -> DelegationEvent:
        ts = datetime.now(timezone.utc).isoformat()
        event = DelegationEvent(
            from_agent=from_agent,
            to_agent=to_agent,
            step_index=step_index,
            timestamp=ts,
            handoff_allowed=result.allowed,
            skipped=result.skipped,
            reason=result.reason,
            clinical_rationale=clinical_rationale,
        )
        self.events.append(event)
        return event

    def start_step_timer(self) -> None:
        self._step_start = time.perf_counter()

    def stop_step_timer(self) -> float:
        if self._step_start is None:
            return 0.0
        elapsed = (time.perf_counter() - self._step_start) * 1000
        self._step_start = None
        return elapsed

    def to_chain(self) -> list[dict[str, Any]]:
        """Serialise the full delegation chain for trace storage."""
        return [
            {
                "from": e.from_agent,
                "to": e.to_agent,
                "step": e.step_index,
                "ts": e.timestamp,
                "allowed": e.handoff_allowed,
                "skipped": e.skipped,
                "reason": e.reason,
                "duration_ms": round(e.duration_ms, 2),
                "rationale": e.clinical_rationale,
            }
            for e in self.events
        ]

    @property
    def skipped_count(self) -> int:
        return sum(1 for e in self.events if e.skipped)

    @property
    def failed_count(self) -> int:
        return sum(1 for e in self.events if not e.handoff_allowed and not e.skipped)

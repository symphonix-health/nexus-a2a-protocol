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
        fallback_mode: ``block_escalate`` | ``retry_then_escalate`` |
            ``reroute`` | ``degraded_allow`` | ``skip``.
            Defaults to safety-first block + escalate.
        fallback_action: Legacy alias retained for backward compatibility.
        criticality: ``clinical`` | ``administrative``.
        required_handover_fields: Required handoff payload fields.
        escalation_path: Ordered escalation targets.
        max_wait_seconds: Max wait window before escalation.
        safe_fallback_branch: Optional route name when rerouting.
        clinical_rationale: Free-text explanation of **why** this
            handoff makes clinical sense (structural transparency, §4.3).
    """

    required_predecessors: list[str] = field(default_factory=list)
    optional_predecessors: list[str] = field(default_factory=list)
    required_context_keys: list[str] = field(default_factory=list)
    fallback_mode: str = "block_escalate"
    fallback_action: str | None = None  # legacy alias: skip | stub | fail
    criticality: str = "clinical"
    required_handover_fields: list[str] = field(default_factory=list)
    escalation_path: list[str] = field(default_factory=lambda: ["care_coordinator", "hitl_ui"])
    max_wait_seconds: int = 0
    safe_fallback_branch: str | None = None
    guideline_refs: list[str] = field(default_factory=list)
    clinical_rationale: str = ""


# ── Handoff validation ─────────────────────────────────────────────


@dataclass
class HandoffResult:
    """Outcome of a single handoff validation check."""

    allowed: bool
    skipped: bool = False
    state: str = "allowed"
    reason_code: str = ""
    reason: str = ""
    missing_predecessors: list[str] = field(default_factory=list)
    missing_context_keys: list[str] = field(default_factory=list)
    missing_handover_fields: list[str] = field(default_factory=list)
    escalation_required: bool = False
    escalation_target: str | None = None
    deadline_at: str | None = None
    guideline_refs: list[str] = field(default_factory=list)
    safe_fallback_taken: bool = False
    retry_after_seconds: float | None = None


def _add_seconds_iso(seconds: int) -> str:
    now = datetime.now(timezone.utc).timestamp()
    return datetime.fromtimestamp(now + max(0, seconds), timezone.utc).isoformat()


def _normalize_fallback_mode(policy: HandoffPolicy) -> str:
    mode = (policy.fallback_mode or "").strip().lower()
    legacy = (policy.fallback_action or "").strip().lower()

    if not mode and legacy:
        if legacy == "fail":
            mode = "block_escalate"
        elif legacy == "stub":
            mode = "degraded_allow"
        elif legacy == "skip":
            mode = "skip"

    if not mode:
        mode = "block_escalate"

    aliases = {
        "block+escalate": "block_escalate",
        "block-escalate": "block_escalate",
        "retry": "retry_then_escalate",
        "stub": "degraded_allow",
        "fail": "block_escalate",
    }
    mode = aliases.get(mode, mode)
    return mode


def _policy_from_input(policy: HandoffPolicy | dict[str, Any] | None) -> HandoffPolicy | None:
    if policy is None:
        return None
    if isinstance(policy, HandoffPolicy):
        return policy
    if isinstance(policy, dict):
        return HandoffPolicy(
            **{k: v for k, v in policy.items() if k in HandoffPolicy.__dataclass_fields__}
        )
    return None


def _resolve_guidelines(policy: HandoffPolicy) -> list[str]:
    refs = list(policy.guideline_refs)
    if refs:
        return refs
    # Safety defaults: structured handover + medication transitions + escalation.
    return [
        "NICE-QS174-Statement4",
        "NICE-NG5",
        "NICE-QS213-Statement5",
        "WHO-Medication-Without-Harm",
    ]


def _resolve_escalation_target(policy: HandoffPolicy) -> str:
    if policy.escalation_path:
        return str(policy.escalation_path[0])
    return "care_coordinator"


def _build_missing_result(
    *,
    policy: HandoffPolicy,
    reason_code: str,
    reason: str,
    missing_predecessors: list[str] | None = None,
    missing_context_keys: list[str] | None = None,
    missing_handover_fields: list[str] | None = None,
) -> HandoffResult:
    mode = _normalize_fallback_mode(policy)

    # Skip mode is only valid for explicitly administrative non-critical steps.
    if mode == "skip" and policy.criticality not in {"administrative", "admin"}:
        mode = "block_escalate"

    if mode == "degraded_allow":
        return HandoffResult(
            allowed=True,
            state="degraded_allowed",
            reason_code=reason_code,
            reason=f"Degraded allow — {reason}",
            missing_predecessors=missing_predecessors or [],
            missing_context_keys=missing_context_keys or [],
            missing_handover_fields=missing_handover_fields or [],
            escalation_required=True,
            escalation_target=_resolve_escalation_target(policy),
            deadline_at=_add_seconds_iso(policy.max_wait_seconds or 0),
            guideline_refs=_resolve_guidelines(policy),
            safe_fallback_taken=bool(policy.safe_fallback_branch),
        )

    if mode == "retry_then_escalate":
        retry_after = float(policy.max_wait_seconds) if policy.max_wait_seconds > 0 else 15.0
        return HandoffResult(
            allowed=False,
            skipped=False,
            state="retry_pending",
            reason_code=reason_code,
            reason=f"Retry pending — {reason}",
            missing_predecessors=missing_predecessors or [],
            missing_context_keys=missing_context_keys or [],
            missing_handover_fields=missing_handover_fields or [],
            escalation_required=False,
            escalation_target=_resolve_escalation_target(policy),
            deadline_at=_add_seconds_iso(int(retry_after)),
            guideline_refs=_resolve_guidelines(policy),
            retry_after_seconds=retry_after,
        )

    if mode == "reroute" and policy.safe_fallback_branch:
        return HandoffResult(
            allowed=False,
            skipped=False,
            state="rerouted",
            reason_code=reason_code,
            reason=f"Rerouted — {reason}",
            missing_predecessors=missing_predecessors or [],
            missing_context_keys=missing_context_keys or [],
            missing_handover_fields=missing_handover_fields or [],
            escalation_required=True,
            escalation_target=_resolve_escalation_target(policy),
            deadline_at=_add_seconds_iso(policy.max_wait_seconds or 0),
            guideline_refs=_resolve_guidelines(policy),
            safe_fallback_taken=True,
        )

    if mode == "skip":
        return HandoffResult(
            allowed=False,
            skipped=True,
            state="skipped",
            reason_code=reason_code,
            reason=f"Step skipped — {reason}",
            missing_predecessors=missing_predecessors or [],
            missing_context_keys=missing_context_keys or [],
            missing_handover_fields=missing_handover_fields or [],
            escalation_required=False,
            guideline_refs=_resolve_guidelines(policy),
        )

    # Default safety-first behavior.
    return HandoffResult(
        allowed=False,
        skipped=False,
        state="blocked_escalated",
        reason_code=reason_code,
        reason=f"Handoff blocked — {reason}",
        missing_predecessors=missing_predecessors or [],
        missing_context_keys=missing_context_keys or [],
        missing_handover_fields=missing_handover_fields or [],
        escalation_required=True,
        escalation_target=_resolve_escalation_target(policy),
        deadline_at=_add_seconds_iso(policy.max_wait_seconds or 0),
        guideline_refs=_resolve_guidelines(policy),
    )


def _path_exists(payload: dict[str, Any], key_path: str) -> bool:
    cursor: Any = payload
    for segment in key_path.split("."):
        if isinstance(cursor, dict) and segment in cursor:
            cursor = cursor[segment]
            continue
        return False
    if cursor is None:
        return False
    if isinstance(cursor, str) and not cursor.strip():
        return False
    if isinstance(cursor, (list, dict)) and not cursor:
        return False
    return True


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
    policy_obj = _policy_from_input(policy)
    if policy_obj is None:
        return HandoffResult(allowed=True, state="allowed")

    # Check required predecessors
    missing = [p for p in policy_obj.required_predecessors if p not in completed_agents]
    failed_required = [p for p in missing if p in failed_agents]

    if missing:
        reason_parts = []
        if failed_required:
            reason_parts.append(f"Required predecessor(s) failed: {', '.join(failed_required)}")
        remaining_missing = [p for p in missing if p not in failed_agents]
        if remaining_missing:
            reason_parts.append(
                f"Required predecessor(s) not yet completed: {', '.join(remaining_missing)}"
            )
        reason = "; ".join(reason_parts)
        return _build_missing_result(
            policy=policy_obj,
            reason_code="missing_required_predecessor",
            reason=reason,
            missing_predecessors=missing,
        )

    # Check required context keys
    missing_keys: list[str] = []
    for key_path in policy_obj.required_context_keys:
        if not _path_exists(clinical_context, key_path):
            missing_keys.append(key_path)

    if missing_keys:
        reason = f"Missing context keys: {', '.join(missing_keys)}"
        return _build_missing_result(
            policy=policy_obj,
            reason_code="missing_required_context",
            reason=reason,
            missing_context_keys=missing_keys,
        )

    # Check required structured handover fields.
    missing_handover_fields: list[str] = []
    for field_path in policy_obj.required_handover_fields:
        # ``handover.`` paths are resolved from dedicated handover context first.
        if field_path.startswith("handover."):
            handover_ctx = clinical_context.get("handover", {})
            if not _path_exists(handover_ctx, field_path.split(".", 1)[1]):
                missing_handover_fields.append(field_path)
            continue
        if not _path_exists(clinical_context, field_path):
            missing_handover_fields.append(field_path)

    if missing_handover_fields:
        reason = f"Missing handover contract fields: {', '.join(missing_handover_fields)}"
        return _build_missing_result(
            policy=policy_obj,
            reason_code="missing_handover_contract",
            reason=reason,
            missing_handover_fields=missing_handover_fields,
        )

    return HandoffResult(
        allowed=True,
        state="allowed",
        reason_code="allowed",
        guideline_refs=_resolve_guidelines(policy_obj),
    )


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
        p = _policy_from_input(policy)
        if p is None:
            return delegation_info
        delegation_info["clinical_rationale"] = p.clinical_rationale
        delegation_info["required_predecessors"] = p.required_predecessors
        delegation_info["optional_predecessors"] = p.optional_predecessors
        delegation_info["criticality"] = p.criticality
        delegation_info["required_handover_fields"] = p.required_handover_fields
        delegation_info["escalation_path"] = p.escalation_path
        delegation_info["max_wait_seconds"] = p.max_wait_seconds
        delegation_info["fallback_mode"] = _normalize_fallback_mode(p)
        if p.safe_fallback_branch:
            delegation_info["safe_fallback_branch"] = p.safe_fallback_branch

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
    state: str
    reason_code: str
    reason: str
    duration_ms: float = 0.0
    clinical_rationale: str = ""
    escalation_required: bool = False
    escalation_target: str | None = None
    deadline_at: str | None = None
    guideline_refs: list[str] = field(default_factory=list)
    safe_fallback_taken: bool = False


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
            state=result.state,
            reason_code=result.reason_code,
            reason=result.reason,
            clinical_rationale=clinical_rationale,
            escalation_required=result.escalation_required,
            escalation_target=result.escalation_target,
            deadline_at=result.deadline_at,
            guideline_refs=result.guideline_refs,
            safe_fallback_taken=result.safe_fallback_taken,
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
                "state": e.state,
                "reason_code": e.reason_code,
                "reason": e.reason,
                "duration_ms": round(e.duration_ms, 2),
                "rationale": e.clinical_rationale,
                "escalation_required": e.escalation_required,
                "escalation_target": e.escalation_target,
                "deadline_at": e.deadline_at,
                "guideline_refs": e.guideline_refs,
                "safe_fallback_taken": e.safe_fallback_taken,
            }
            for e in self.events
        ]

    @property
    def skipped_count(self) -> int:
        return sum(1 for e in self.events if e.skipped)

    @property
    def failed_count(self) -> int:
        return sum(1 for e in self.events if not e.handoff_allowed and not e.skipped)

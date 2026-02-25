"""Assertions for clinical-negative transfer-of-care scenarios."""

from __future__ import annotations

from typing import Any


def assert_clinical_negative_trace(
    trace_run: dict[str, Any],
    *,
    expected_escalation: str | None = None,
    expected_safe_outcome: str | None = None,
) -> None:
    """Assert that a clinical-negative journey produced safe blocked/escalated behavior."""
    assert isinstance(trace_run, dict), f"trace_run must be dict, got {type(trace_run).__name__}"
    chain = trace_run.get("delegation_chain", [])
    assert isinstance(chain, list), "trace_run.delegation_chain must be a list"
    assert chain, "Clinical negative trace must include delegation_chain events"

    blocked = [e for e in chain if e.get("state") == "blocked_escalated"]
    assert blocked, f"Expected blocked_escalated event in chain, got states {[e.get('state') for e in chain]}"

    status = str(trace_run.get("handover_contract_status", ""))
    assert status in {"blocked", "degraded"}, (
        f"Expected handover_contract_status blocked/degraded, got '{status}'"
    )

    escalation_codes = {str(e.get("reason_code") or "") for e in chain}
    if expected_escalation:
        assert expected_escalation in escalation_codes or expected_escalation == trace_run.get(
            "escalation_trigger"
        ), (
            "Expected escalation trigger "
            f"'{expected_escalation}' in {sorted(escalation_codes)} / {trace_run.get('escalation_trigger')}"
        )

    if expected_safe_outcome:
        label = expected_safe_outcome.strip().lower()
        if "hitl" in label:
            assert any(str(e.get("escalation_target", "")).lower() == "hitl_ui" for e in chain), (
                "Expected HITL escalation target in delegation chain"
            )
        if "safety_net" in label or "safety-net" in label:
            assert bool(trace_run.get("safe_fallback_taken")), (
                "Expected safe_fallback_taken=true for safety-net outcomes"
            )


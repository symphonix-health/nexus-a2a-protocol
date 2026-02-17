"""Tests for shared.nexus_common.trace – TraceStepEvent and TraceRun models."""

from __future__ import annotations

import pytest
from shared.nexus_common.trace import TraceRun, TraceStepEvent, _utc_now_iso


def _sample_step(
    trace_id: str = "trace-001",
    step_index: int = 0,
    status: str = "final",
    **overrides,
) -> TraceStepEvent:
    defaults = dict(
        trace_id=trace_id,
        correlation_id="corr-abc",
        scenario_name="ed_intake",
        patient_id="P-100",
        visit_id="V-200",
        agent="triage",
        method="tasks/send",
        step_index=step_index,
        timestamp_start=_utc_now_iso(),
        timestamp_end=_utc_now_iso(),
        duration_ms=42.5,
        status=status,
        request_redacted={"age": 30},
        response_redacted={"result": "ok"},
        redaction_meta={"masked_fields": [], "policy_version": "v1"},
    )
    defaults.update(overrides)
    return TraceStepEvent(**defaults)


def _sample_run(trace_id: str = "trace-001", **overrides) -> TraceRun:
    defaults = dict(
        trace_id=trace_id,
        scenario_name="ed_intake",
        visit_id="V-200",
        patient_id="P-100",
        patient_profile={"age": 30, "gender": "male", "chief_complaint": "chest pain"},
        started_at=_utc_now_iso(),
    )
    defaults.update(overrides)
    return TraceRun(**defaults)


# ── TraceStepEvent ─────────────────────────────────────────────────────


class TestTraceStepEvent:
    def test_construction_valid(self) -> None:
        step = _sample_step()
        assert step.trace_id == "trace-001"
        assert step.step_index == 0
        assert step.duration_ms == 42.5

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValueError, match="status must be one of"):
            _sample_step(status="invalid")

    def test_empty_trace_id_raises(self) -> None:
        with pytest.raises(ValueError, match="trace_id must be non-empty"):
            _sample_step(trace_id="")

    def test_to_dict_contains_required_fields(self) -> None:
        d = _sample_step().to_dict()
        for key in ("trace_id", "correlation_id", "agent", "method", "status", "duration_ms"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_strips_none_fields(self) -> None:
        step = _sample_step(error_code=None, error_message=None)
        d = step.to_dict()
        assert "error_code" not in d
        assert "error_message" not in d

    def test_to_dict_keeps_error_when_present(self) -> None:
        step = _sample_step(status="error", error_code="TIMEOUT", error_message="Agent unreachable")
        d = step.to_dict()
        assert d["error_code"] == "TIMEOUT"
        assert d["error_message"] == "Agent unreachable"

    def test_retry_count_default_zero(self) -> None:
        step = _sample_step()
        assert step.retry_count == 0
        assert step.to_dict()["retry_count"] == 0


# ── TraceRun ───────────────────────────────────────────────────────────


class TestTraceRun:
    def test_construction_valid(self) -> None:
        run = _sample_run()
        assert run.trace_id == "trace-001"
        assert run.status == "working"
        assert run.steps == []

    def test_empty_trace_id_raises(self) -> None:
        with pytest.raises(ValueError, match="trace_id must be non-empty"):
            _sample_run(trace_id="")

    def test_add_step_updates_duration(self) -> None:
        run = _sample_run()
        run.add_step(_sample_step(duration_ms=100.0))
        run.add_step(_sample_step(step_index=1, duration_ms=50.0))
        assert len(run.steps) == 2
        assert run.total_duration_ms == 150.0

    def test_finalize_sets_status_and_completed(self) -> None:
        run = _sample_run()
        run.add_step(_sample_step(duration_ms=10.0))
        run.finalize(status="final")
        assert run.status == "final"
        assert run.completed_at is not None
        assert run.total_duration_ms == 10.0

    def test_finalize_defaults_to_final(self) -> None:
        run = _sample_run()
        run.finalize()
        assert run.status == "final"

    def test_to_dict_structure(self) -> None:
        run = _sample_run()
        run.add_step(_sample_step(duration_ms=25.0))
        run.finalize()
        d = run.to_dict()

        assert d["trace_id"] == "trace-001"
        assert d["scenario_name"] == "ed_intake"
        assert d["step_count"] == 1
        assert d["total_duration_ms"] == 25.0
        assert isinstance(d["steps"], list)
        assert len(d["steps"]) == 1
        assert d["steps"][0]["agent"] == "triage"

    def test_to_dict_patient_profile_preserved(self) -> None:
        profile = {"age": 55, "gender": "female", "symptoms": ["headache"]}
        run = _sample_run(patient_profile=profile)
        d = run.to_dict()
        assert d["patient_profile"] == profile

from __future__ import annotations

from shared.nexus_common.health import HealthMonitor, apply_backpressure_to_agent_card
from shared.nexus_common.idempotency import IdempotencyStore
from shared.nexus_common.protocol import (
    CorrelationContext,
    IdempotencyContext,
    ProgressState,
    ScenarioContext,
    build_task_envelope,
)
from shared.nexus_common.sse import TaskEventBus

from nexus_a2a_protocol import make_error, make_error_data, make_request


def test_task_envelope_contains_required_contracts() -> None:
    envelope = build_task_envelope(
        task={"id": "task-1"},
        scenario_context=ScenarioContext(
            scenario_id="chest_pain_cardiac",
            visit_id="VISIT-123",
            journey_step="triage",
            phase="accepted",
            deadline_ms=30000,
        ),
        correlation=CorrelationContext(trace_id="trace-1", parent_task_id="task-parent"),
        idempotency=IdempotencyContext(idempotency_key="idem-1", dedup_window_ms=60000),
        progress=ProgressState(state="working", percent=25.0, eta_ms=12000),
    )

    assert envelope["scenario_context"]["scenario_id"] == "chest_pain_cardiac"
    assert envelope["correlation"]["trace_id"] == "trace-1"
    assert envelope["idempotency"]["idempotency_key"] == "idem-1"
    assert envelope["progress"]["state"] == "working"


def test_idempotency_store_detects_duplicates() -> None:
    store = IdempotencyStore()
    first = store.check_or_register("idem-abc", dedup_window_ms=1000)
    second = store.check_or_register("idem-abc", dedup_window_ms=1000)

    assert first.is_duplicate is False
    assert second.is_duplicate is True


def test_health_includes_backpressure_contract() -> None:
    monitor = HealthMonitor("triage-agent")
    monitor.set_backpressure(
        queue_depth=12, max_concurrency=16, rate_limit_rps=40.0, retry_after_ms=500
    )

    payload = monitor.get_health()

    backpressure = payload["metrics"]["backpressure"]
    assert backpressure["queue_depth"] == 12
    assert backpressure["max_concurrency"] == 16
    assert backpressure["rate_limit_rps"] == 40.0
    assert backpressure["retry_after_ms"] == 500


def test_agent_card_backpressure_hints_are_applied() -> None:
    monitor = HealthMonitor("triage-agent")
    monitor.set_backpressure(
        queue_depth=7, max_concurrency=12, rate_limit_rps=20.0, retry_after_ms=300
    )

    card = {"name": "triage-agent", "version": "1.0"}
    merged = apply_backpressure_to_agent_card(card, monitor)

    assert merged["x-nexus-backpressure"]["queue_depth"] == 7
    assert merged["x-nexus-backpressure"]["max_concurrency"] == 12


def test_sse_event_payload_contains_correlation_and_progress() -> None:
    bus = TaskEventBus(agent_name="triage-agent")

    payload = bus.build_event_payload(
        task_id="task-1",
        event="nexus.task.working",
        data={"ok": True},
        duration_ms=45.0,
        scenario_context={"scenario_id": "chest_pain_cardiac"},
        correlation={"trace_id": "trace-1", "causation_id": "cause-1"},
        idempotency={"idempotency_key": "idem-1", "dedup_window_ms": 60000},
        progress={"state": "working", "percent": 50.0, "eta_ms": 2000},
    )

    assert payload["correlation"]["trace_id"] == "trace-1"
    assert payload["scenario_context"]["scenario_id"] == "chest_pain_cardiac"
    assert payload["idempotency"]["idempotency_key"] == "idem-1"
    assert payload["progress"]["state"] == "working"
    assert payload["progress"]["percent"] == 50.0


def test_jsonrpc_error_taxonomy_fields() -> None:
    payload = make_error(
        request_id="1",
        code=-32000,
        message="Transient upstream timeout",
        data={"upstream": "diagnosis-agent"},
        retryable=True,
        retry_after_ms=250,
        failure_domain="network",
    )

    error_data = payload["error"]["data"]
    assert error_data["retryable"] is True
    assert error_data["retry_after_ms"] == 250
    assert error_data["failure_domain"] == "network"


def test_jsonrpc_request_has_contract_containers() -> None:
    payload = make_request("tasks/send", {"task": {"id": "task-1"}}, request_id="req-1")

    params = payload["params"]
    assert isinstance(params["scenario_context"], dict)
    assert isinstance(params["correlation"], dict)
    assert isinstance(params["idempotency"], dict)


def test_make_error_data_rejects_invalid_failure_domain() -> None:
    try:
        make_error_data(failure_domain="database")
    except Exception as exc:
        assert "failure_domain" in str(exc)
    else:
        raise AssertionError("Expected invalid failure_domain to raise")

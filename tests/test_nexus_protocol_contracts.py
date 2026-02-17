from __future__ import annotations

import pytest

from shared.nexus_common.health import HealthMonitor, apply_backpressure_to_agent_card
from shared.nexus_common.idempotency import IdempotencyStore
from shared.nexus_common.jsonrpc import response_result
from shared.nexus_common.protocol import (
    CorrelationContext,
    IdempotencyContext,
    ProgressState,
    ScaleProfileContext,
    ScenarioContext,
    build_task_envelope,
    validate_vector_clock_conflict_payload,
)
from shared.nexus_common.scale_profile import build_canonical_shard_key
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
        scale_profile=ScaleProfileContext(
            profile="nexus-scale-v1.1",
            tenant_key="tenant-a",
            user_key="user-1",
            task_key="task-1",
            shard_key=build_canonical_shard_key(
                tenant_key="tenant-a",
                user_key="user-1",
                task_key="task-1",
            ),
        ),
    )

    assert envelope["scenario_context"]["scenario_id"] == "chest_pain_cardiac"
    assert envelope["correlation"]["trace_id"] == "trace-1"
    assert envelope["idempotency"]["idempotency_key"] == "idem-1"
    assert envelope["progress"]["state"] == "working"
    assert envelope["scale_profile"]["tenant_key"] == "tenant-a"


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


@pytest.mark.parametrize("method", ["tasks/send", "tasks/sendSubscribe", "tasks/cancel"])
def test_response_result_enriches_mutation_with_scale_metadata(method: str) -> None:
    profile = {
        "profile": "nexus-scale-v1.1",
        "tenant_key": "tenant-a",
        "user_key": "user-1",
        "task_key": "task-1",
        "shard_key": build_canonical_shard_key(
            tenant_key="tenant-a",
            user_key="user-1",
            task_key="task-1",
        ),
        "features_required": ["routing.v1", "stream.resume.v1"],
    }
    payload = response_result(
        "req-1",
        {"task_id": "task-1", "ok": True},
        method=method,
        params={"scale_profile": profile},
    )
    result = payload["result"]
    assert result["resource_version"] == "rv:task-1"
    assert result["consistency_applied"] == "eventual"
    assert result["region_served"] == "local"
    assert result["scale_profile"] == "nexus-scale-v1.1"
    assert "routing.v1" in result["accepted_features"]


def test_response_result_non_mutation_unmodified() -> None:
    payload = response_result(
        "req-2",
        {"task_id": "task-2", "ok": True},
        method="tasks/get",
        params={},
    )
    result = payload["result"]
    assert "resource_version" not in result
    assert "consistency_applied" not in result


def test_response_result_invalid_mutation_metadata_raises_internal_error() -> None:
    profile = {
        "profile": "nexus-scale-v1.1",
        "tenant_key": "tenant-a",
        "user_key": "user-1",
        "task_key": "task-1",
        "shard_key": build_canonical_shard_key(
            tenant_key="tenant-a",
            user_key="user-1",
            task_key="task-1",
        ),
    }
    with pytest.raises(Exception) as exc_info:
        response_result(
            "req-invalid-meta",
            {
                "task_id": "task-1",
                "resource_version": "  ",
                "region_served": "local",
                "consistency_applied": "eventual",
                "scale_profile": "nexus-scale-v1.1",
                "accepted_features": [],
            },
            method="tasks/send",
            params={"scale_profile": profile},
        )

    err = exc_info.value
    assert getattr(err, "code", None) == -32603
    assert getattr(err, "retryable", None) is False
    data = getattr(err, "data", {}) or {}
    assert data.get("reason") == "invalid_mutation_response_metadata"
    assert data.get("method") == "tasks/send"


def test_response_result_reject_on_conflict_raises_deterministic_error() -> None:
    profile = {
        "profile": "nexus-scale-v1.1",
        "tenant_key": "tenant-a",
        "user_key": "user-1",
        "task_key": "task-1",
        "shard_key": build_canonical_shard_key(
            tenant_key="tenant-a",
            user_key="user-1",
            task_key="task-1",
        ),
        "conflict_policy": "reject_on_conflict",
        "expected_version": "rv:expected",
    }

    try:
        response_result(
            "req-3",
            {
                "task_id": "task-1",
                "resource_version": "rv:current",
                "ok": True,
            },
            method="tasks/cancel",
            params={"scale_profile": profile},
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == -32000
        assert getattr(exc, "retryable", None) is False
        data = getattr(exc, "data", {})
        assert data.get("reason") == "conflict"
        assert data.get("conflict_policy") == "reject_on_conflict"
        assert data.get("expected_version") == "rv:expected"
        assert data.get("current_version") == "rv:current"
    else:
        raise AssertionError("Expected reject_on_conflict mismatch to raise conflict error")


def test_response_result_vector_clock_conflict_contains_causality() -> None:
    profile = {
        "profile": "nexus-scale-v1.1",
        "tenant_key": "tenant-a",
        "user_key": "user-1",
        "task_key": "task-1",
        "shard_key": build_canonical_shard_key(
            tenant_key="tenant-a",
            user_key="user-1",
            task_key="task-1",
        ),
        "conflict_policy": "vector_clock",
        "expected_version": "rv:expected",
    }

    try:
        response_result(
            "req-4",
            {
                "task_id": "task-1",
                "resource_version": "rv:current",
                "ok": True,
            },
            method="tasks/send",
            params={"scale_profile": profile},
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == -32000
        data = getattr(exc, "data", {})
        assert data.get("conflict_policy") == "vector_clock"
        assert data.get("reason") == "conflict"
        competing = data.get("competing_versions")
        assert isinstance(competing, list)
        assert len(competing) >= 2
        for item in competing:
            assert isinstance(item, dict)
            assert isinstance(item.get("version"), str) and item["version"].strip()
            assert isinstance(item.get("source"), str) and item["source"].strip()
        causality = data.get("causality", {})
        assert causality.get("policy") == "vector_clock"
        assert causality.get("resolution") == "manual_or_merge_required"
        assert causality.get("winner") is None
    else:
        raise AssertionError("Expected vector_clock mismatch to raise conflict error")


def test_validate_vector_clock_conflict_payload_rejects_invalid_winner() -> None:
    payload = {
        "reason": "conflict",
        "conflict_policy": "vector_clock",
        "expected_version": "rv:expected",
        "current_version": "rv:current",
        "competing_versions": [
            {"version": "rv:expected", "source": "expected"},
            {"version": "rv:current", "source": "current"},
        ],
        "causality": {
            "policy": "vector_clock",
            "resolution": "winner_selected",
            "winner": "rv:unknown",
        },
    }

    with pytest.raises(ValueError):
        validate_vector_clock_conflict_payload(payload)


def test_validate_vector_clock_conflict_payload_rejects_non_string_version_entry() -> None:
    payload = {
        "reason": "conflict",
        "conflict_policy": "vector_clock",
        "expected_version": "rv:expected",
        "current_version": "rv:current",
        "competing_versions": [
            {"version": "rv:expected", "source": "expected"},
            {"version": 7, "source": "current"},
        ],
        "causality": {
            "policy": "vector_clock",
            "resolution": "manual_or_merge_required",
            "winner": None,
        },
    }

    with pytest.raises(ValueError):
        validate_vector_clock_conflict_payload(payload)

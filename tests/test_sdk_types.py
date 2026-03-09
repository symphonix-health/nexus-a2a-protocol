from __future__ import annotations

import pytest

from nexus_a2a_protocol.sdk import (
    TaskEnvelope,
    TransportError,
    extract_task_id_from_response,
    make_task_event,
    map_nexus_event_to_progress,
)


def test_task_envelope_from_minimal_mapping() -> None:
    envelope = TaskEnvelope.from_input(
        {
            "method": "tasks/send",
            "params": {"task": {"type": "ConformanceTask"}},
            "request_id": "req-1",
        }
    )
    payload = envelope.to_jsonrpc()
    assert payload["method"] == "tasks/send"
    assert payload["id"] == "req-1"
    assert payload["params"]["task"]["type"] == "ConformanceTask"


def test_task_envelope_rejects_non_mapping_params() -> None:
    with pytest.raises(TransportError):
        TaskEnvelope.from_input({"method": "tasks/send", "params": "invalid"})


def test_extract_task_id_from_rpc_result() -> None:
    task_id = extract_task_id_from_response(
        {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {"task_id": "task-123"},
        }
    )
    assert task_id == "task-123"


def test_progress_mapping_stays_monotonic() -> None:
    events = [
        make_task_event(event_type="nexus.task.status", payload={"status": {"state": "accepted"}}),
        make_task_event(
            event_type="nexus.task.status",
            payload={"status": {"state": "working", "percent": 40}},
        ),
        make_task_event(event_type="nexus.task.final", payload={"ok": True}),
    ]

    current = 0
    for evt in events:
        mapped = map_nexus_event_to_progress(evt, current)
        assert mapped.progress >= current
        current = mapped.progress

    assert current == 100

from __future__ import annotations

import pytest

from nexus_a2a_protocol import (
    ProtocolValidationError,
    make_error,
    make_request,
    make_result,
    validate_envelope,
)
from shared.nexus_common.sse import build_signed_resume_cursor


def test_make_request_and_validate() -> None:
    payload = make_request("tasks/get", {"task_id": "abc"}, request_id="1")
    assert payload["jsonrpc"] == "2.0"
    assert validate_envelope(payload)["method"] == "tasks/get"


def test_make_request_rejects_unknown_method() -> None:
    with pytest.raises(ProtocolValidationError):
        make_request("tasks/unknown", {}, request_id="1")


def test_validate_envelope_rejects_invalid_payload() -> None:
    with pytest.raises(ProtocolValidationError):
        validate_envelope({"jsonrpc": "1.0", "id": "1"})


def test_make_error_shape() -> None:
    payload = make_error("1", -32600, "Invalid Request")
    assert payload["error"]["code"] == -32600
    assert payload["error"]["message"] == "Invalid Request"


@pytest.mark.parametrize("method", ["tasks/send", "tasks/sendSubscribe", "tasks/cancel"])
def test_make_result_enriches_mutation_metadata(method: str) -> None:
    payload = make_result(
        "1",
        {"task_id": "task-1", "ok": True},
        method=method,
        params={
            "scale_profile": {
                "write_consistency": "local_quorum",
                "features_required": ["routing.v1", "stream.resume.v1"],
            }
        },
    )
    result = payload["result"]
    assert result["resource_version"] == "rv:task-1"
    assert result["consistency_applied"] == "local_quorum"
    assert result["region_served"] == "local"
    assert result["scale_profile"] == "nexus-scale-v1.1"
    assert "routing.v1" in result["accepted_features"]


def test_make_result_rejects_invalid_mutation_metadata() -> None:
    with pytest.raises(ProtocolValidationError):
        make_result(
            "meta-invalid",
            {
                "task_id": "task-1",
                "resource_version": "rv:task-1",
                "region_served": "local",
                "consistency_applied": "eventual",
                "scale_profile": "nexus-scale-v1.0",
                "accepted_features": [],
            },
            method="tasks/send",
            params={"scale_profile": {"write_consistency": "eventual"}},
        )


def test_make_result_reject_on_conflict_mismatch() -> None:
    with pytest.raises(ProtocolValidationError):
        make_result(
            "2",
            {"task_id": "task-2", "resource_version": "rv:current"},
            method="tasks/cancel",
            params={
                "scale_profile": {
                    "conflict_policy": "reject_on_conflict",
                    "expected_version": "rv:expected",
                }
            },
        )


def test_make_result_vector_clock_conflict_mismatch() -> None:
    with pytest.raises(ProtocolValidationError):
        make_result(
            "2b",
            {"task_id": "task-2", "resource_version": "rv:current"},
            method="tasks/sendSubscribe",
            params={
                "scale_profile": {
                    "conflict_policy": "vector_clock",
                    "expected_version": "rv:expected",
                }
            },
        )


def test_validate_envelope_rejects_resubscribe_catchup_policy_violation() -> None:
    import os

    os.environ["NEXUS_RESUBSCRIBE_MAX_CATCHUP_EVENTS"] = "10"
    try:
        cursor = build_signed_resume_cursor(
            stream_id="task-1",
            stream_epoch="epoch-1",
            seq=1,
            exp_unix_ms=2999999999999,
        )
        with pytest.raises(ProtocolValidationError):
            validate_envelope(
                {
                    "jsonrpc": "2.0",
                    "id": "r-catchup",
                    "method": "tasks/resubscribe",
                    "params": {
                        "task_id": "task-1",
                        "cursor": cursor,
                        "max_catchup_events": 11,
                    },
                }
            )
    finally:
        os.environ.pop("NEXUS_RESUBSCRIBE_MAX_CATCHUP_EVENTS", None)

from __future__ import annotations

import json
import os
from pathlib import Path

from nexus_a2a_protocol import ProtocolValidationError, validate_envelope
from shared.nexus_common.idempotency import IdempotencyStore
from shared.nexus_common.jsonrpc import (
    NEXUS_RATE_LIMITED,
    make_rate_limited_error,
    parse_request,
    response_result,
)
from shared.nexus_common.scale_profile import build_canonical_shard_key, negotiate_scale_features
from shared.nexus_common.sse import (
    TaskEventBus,
    build_signed_resume_cursor,
    parse_signed_resume_cursor,
)


def _valid_scale_profile() -> dict:
    return {
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
        "features_optional": ["consistency.vectorclock.v1", "unknown.feature"],
    }


def _valid_idempotency() -> dict:
    return {
        "idempotency_key": "idem-1",
        "scope": "tenant-a:tasks/send",
        "dedup_window_ms": 60000,
        "payload_hash": "sha256:payload",
    }


def test_sdk_validate_envelope_requires_scale_profile_for_mutation() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tasks/send",
        "params": {
            "task": {"id": "task-1"},
            "idempotency": _valid_idempotency(),
        },
    }
    try:
        validate_envelope(payload)
    except Exception as exc:
        assert "scale_profile" in str(exc)
    else:
        raise AssertionError("Expected missing scale_profile to fail")


def test_parse_request_enforces_scale_profile_when_strict_enabled() -> None:
    os.environ["NEXUS_SCALE_PROFILE_STRICT"] = "true"
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tasks/sendSubscribe",
            "params": {"task": {"id": "task-1"}},
        }
        try:
            parse_request(payload)
        except Exception as exc:
            assert "scale_profile" in str(exc)
        else:
            raise AssertionError("Expected strict mode to reject missing scale_profile")
    finally:
        os.environ.pop("NEXUS_SCALE_PROFILE_STRICT", None)


def test_parse_request_rejects_missing_required_feature_support() -> None:
    os.environ["NEXUS_SCALE_PROFILE_STRICT"] = "true"
    os.environ["NEXUS_SUPPORTED_FEATURES"] = "routing.v1,stream.resume.v1"
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/send",
            "params": {
                "task": {"id": "task-2"},
                "scale_profile": {
                    **_valid_scale_profile(),
                    "features_required": ["routing.v1", "admission.v1"],
                },
                "idempotency": _valid_idempotency(),
            },
        }
        try:
            parse_request(payload)
        except Exception as exc:
            assert "unsupported_feature" in str(exc)
        else:
            raise AssertionError("Expected unsupported required feature to fail")
    finally:
        os.environ.pop("NEXUS_SCALE_PROFILE_STRICT", None)
        os.environ.pop("NEXUS_SUPPORTED_FEATURES", None)


def test_parse_request_rejects_invalid_features_required_type() -> None:
    os.environ["NEXUS_SCALE_PROFILE_STRICT"] = "true"
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "2c",
            "method": "tasks/send",
            "params": {
                "task": {"id": "task-2c"},
                "scale_profile": {
                    **_valid_scale_profile(),
                    "features_required": "routing.v1",
                },
                "idempotency": _valid_idempotency(),
            },
        }
        try:
            parse_request(payload)
        except Exception as exc:
            assert getattr(exc, "code", None) == -32602
            assert "invalid_features_required" in str(exc)
        else:
            raise AssertionError("Expected invalid features_required type to fail")
    finally:
        os.environ.pop("NEXUS_SCALE_PROFILE_STRICT", None)


def test_parse_request_rejects_invalid_feature_entry() -> None:
    os.environ["NEXUS_SCALE_PROFILE_STRICT"] = "true"
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "2d",
            "method": "tasks/send",
            "params": {
                "task": {"id": "task-2d"},
                "scale_profile": {
                    **_valid_scale_profile(),
                    "features_optional": ["consistency.vectorclock.v1", ""],
                },
                "idempotency": _valid_idempotency(),
            },
        }
        try:
            parse_request(payload)
        except Exception as exc:
            assert getattr(exc, "code", None) == -32602
            assert "invalid_feature_entry" in str(exc)
        else:
            raise AssertionError("Expected invalid feature entry to fail")
    finally:
        os.environ.pop("NEXUS_SCALE_PROFILE_STRICT", None)


def test_parse_request_rejects_non_canonical_shard_key() -> None:
    os.environ["NEXUS_SCALE_PROFILE_STRICT"] = "true"
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "2b",
            "method": "tasks/send",
            "params": {
                "task": {"id": "task-2b"},
                "scale_profile": {
                    **_valid_scale_profile(),
                    "shard_key": "sha256:" + ("0" * 64),
                },
                "idempotency": _valid_idempotency(),
            },
        }
        try:
            parse_request(payload)
        except Exception as exc:
            assert "non_canonical_shard_key" in str(exc)
        else:
            raise AssertionError("Expected non-canonical shard key to fail")
    finally:
        os.environ.pop("NEXUS_SCALE_PROFILE_STRICT", None)


def test_negotiate_scale_features_reports_missing_and_optional() -> None:
    result = negotiate_scale_features(
        required=["routing.v1", "admission.v1"],
        optional=["consistency.vectorclock.v1", "not-supported.v1"],
        supported={"routing.v1", "consistency.vectorclock.v1"},
    )
    assert result["accepted"] is False
    assert "admission.v1" in result["missing_required"]
    assert "consistency.vectorclock.v1" in result["accepted_optional"]


def test_idempotency_store_detects_payload_mismatch_for_same_key_scope() -> None:
    store = IdempotencyStore()
    first = store.check_or_register(
        "idem-1",
        dedup_window_ms=1000,
        scope="tenant:tasks/send",
        payload_hash="sha256:a",
    )
    second = store.check_or_register(
        "idem-1",
        dedup_window_ms=1000,
        scope="tenant:tasks/send",
        payload_hash="sha256:b",
    )
    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert second.payload_mismatch is True


def test_sse_cursor_roundtrip_and_monotonic_sequence() -> None:
    bus = TaskEventBus(agent_name="test-agent")

    # Drive internal seq state via payload generation path.
    payload1 = bus.build_event_payload("task-1", "nexus.task.accepted", {"ok": True}, 1.0)
    payload2 = bus.build_event_payload("task-1", "nexus.task.working", {"ok": True}, 1.0)

    assert payload2["stream"]["seq"] > payload1["stream"]["seq"]
    cursor = bus.build_resume_cursor("task-1")
    parsed = bus.parse_resume_cursor(cursor)
    assert parsed["stream_id"] == "task-1"
    assert parsed["seq"] >= payload2["stream"]["seq"]


def test_parse_request_rejects_invalid_resubscribe_cursor_signature() -> None:
    bus = TaskEventBus(agent_name="test-agent")
    valid = bus.build_resume_cursor("task-1")
    tampered = valid[:-1] + ("A" if valid[-1] != "A" else "B")
    payload = {
        "jsonrpc": "2.0",
        "id": "r1",
        "method": "tasks/resubscribe",
        "params": {
            "task_id": "task-1",
            "cursor": tampered,
            "max_catchup_events": 1000,
        },
    }
    try:
        parse_request(payload)
    except Exception as exc:
        assert getattr(exc, "code", None) == -32002
        assert getattr(exc, "retryable", None) is False
        assert "cursor" in str(exc).lower()
    else:
        raise AssertionError("Expected invalid cursor signature to fail")


def test_parse_request_rejects_expired_resubscribe_cursor() -> None:
    cursor = build_signed_resume_cursor(
        stream_id="task-1",
        stream_epoch="epoch-1",
        seq=10,
        exp_unix_ms=1,
    )
    payload = {
        "jsonrpc": "2.0",
        "id": "r2",
        "method": "tasks/resubscribe",
        "params": {
            "task_id": "task-1",
            "cursor": cursor,
            "max_catchup_events": 1000,
        },
    }
    try:
        parse_request(payload)
    except Exception as exc:
        assert getattr(exc, "code", None) == -32002
        assert getattr(exc, "retryable", None) is False
        assert "expired" in str(exc).lower()
    else:
        raise AssertionError("Expected expired cursor to fail")


def test_parse_request_rejects_resubscribe_cursor_out_of_retention() -> None:
    cursor = build_signed_resume_cursor(
        stream_id="task-1",
        stream_epoch="epoch-1",
        seq=10,
        exp_unix_ms=2999999999999,
        issued_at_unix_ms=1000,
        retention_until_unix_ms=1500,
    )
    payload = {
        "jsonrpc": "2.0",
        "id": "r2b",
        "method": "tasks/resubscribe",
        "params": {
            "task_id": "task-1",
            "cursor": cursor,
            "max_catchup_events": 1000,
        },
    }
    try:
        parse_request(payload)
    except Exception as exc:
        assert getattr(exc, "code", None) == -32002
        assert getattr(exc, "retryable", None) is False
        assert "retention" in str(exc).lower()
    else:
        raise AssertionError("Expected out-of-retention cursor to fail")


def test_parse_request_rejects_max_catchup_events_over_policy() -> None:
    os.environ["NEXUS_RESUBSCRIBE_MAX_CATCHUP_EVENTS"] = "100"
    try:
        cursor = build_signed_resume_cursor(
            stream_id="task-1",
            stream_epoch="epoch-1",
            seq=10,
            exp_unix_ms=2999999999999,
        )
        payload = {
            "jsonrpc": "2.0",
            "id": "r2c",
            "method": "tasks/resubscribe",
            "params": {
                "task_id": "task-1",
                "cursor": cursor,
                "max_catchup_events": 101,
            },
        }
        try:
            parse_request(payload)
        except Exception as exc:
            assert getattr(exc, "code", None) == -32004
            assert getattr(exc, "retryable", None) is True
            assert "catchup_exceeds_retention" in str(exc)
        else:
            raise AssertionError("Expected catchup policy violation to fail")
    finally:
        os.environ.pop("NEXUS_RESUBSCRIBE_MAX_CATCHUP_EVENTS", None)


def test_parse_signed_resume_cursor_accepts_optional_retention_fields() -> None:
    cursor = build_signed_resume_cursor(
        stream_id="task-1",
        stream_epoch="epoch-1",
        seq=10,
        exp_unix_ms=2999999999999,
        issued_at_unix_ms=2000,
        retention_until_unix_ms=3000,
        cursor_secret="secret-x",
    )
    parsed = parse_signed_resume_cursor(
        cursor,
        cursor_secret="secret-x",
        now_unix_ms=2500,
    )
    assert parsed["iat_unix_ms"] == 2000
    assert parsed["retention_until_unix_ms"] == 3000


def test_validate_envelope_rejects_invalid_resubscribe_cursor() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "r3",
        "method": "tasks/resubscribe",
        "params": {
            "task_id": "task-1",
            "cursor": "invalid-token",
            "max_catchup_events": 1000,
        },
    }
    try:
        validate_envelope(payload)
    except Exception as exc:
        assert "cursor" in str(exc).lower()
    else:
        raise AssertionError("Expected invalid cursor to fail in validate_envelope")


def test_make_rate_limited_error_contract() -> None:
    err = make_rate_limited_error(
        rate_limit_scope="tenant",
        bucket_id="tenant-a:tasks/send",
        limit_rps=100.0,
        observed_rps=150.0,
        retry_after_ms=300,
    )
    payload = err.to_dict()
    assert payload["code"] == NEXUS_RATE_LIMITED
    assert payload["data"]["retryable"] is True
    assert payload["data"]["retry_after_ms"] == 300
    assert payload["data"]["rate_limit_scope"] == "tenant"


def test_g0_schema_fuzz_required_fields_rejected() -> None:
    base = {
        "jsonrpc": "2.0",
        "id": "g0-fuzz-1",
        "method": "tasks/send",
        "params": {
            "task": {"id": "task-g0-fuzz-1"},
            "scale_profile": _valid_scale_profile(),
            "idempotency": _valid_idempotency(),
        },
    }
    scale_required = ("profile", "tenant_key", "user_key", "task_key", "shard_key")
    for field in scale_required:
        payload = json.loads(json.dumps(base))
        payload["params"]["scale_profile"].pop(field, None)
        try:
            validate_envelope(payload)
        except Exception as exc:
            assert isinstance(exc, ProtocolValidationError)
        else:
            raise AssertionError(f"Expected missing scale_profile.{field} to fail")

    idem_required = ("idempotency_key", "scope", "dedup_window_ms", "payload_hash")
    for field in idem_required:
        payload = json.loads(json.dumps(base))
        payload["params"]["idempotency"].pop(field, None)
        try:
            validate_envelope(payload)
        except Exception as exc:
            assert isinstance(exc, ProtocolValidationError)
        else:
            raise AssertionError(f"Expected missing idempotency.{field} to fail")

    for bad_shard in ("bad-shard", "sha256:abc", "sha256:" + ("Z" * 64)):
        payload = json.loads(json.dumps(base))
        payload["params"]["scale_profile"]["shard_key"] = bad_shard
        try:
            validate_envelope(payload)
        except Exception as exc:
            assert isinstance(exc, ProtocolValidationError)
        else:
            raise AssertionError(f"Expected invalid shard_key format to fail: {bad_shard}")


def test_g2_conflict_policy_outcomes_are_deterministic_by_policy() -> None:
    task_key = "task-g2-det-1"
    base_profile = {
        "profile": "nexus-scale-v1.1",
        "tenant_key": "tenant-g2-det",
        "user_key": "user-g2-det",
        "task_key": task_key,
        "shard_key": build_canonical_shard_key(
            tenant_key="tenant-g2-det",
            user_key="user-g2-det",
            task_key=task_key,
        ),
        "write_consistency": "global_quorum",
        "expected_version": "rv:expected",
    }
    result_payload = {
        "task_id": task_key,
        "resource_version": "rv:current",
        "region_served": "us-west-2",
    }

    try:
        response_result(
            "g2-reject",
            result_payload,
            method="tasks/cancel",
            params={"scale_profile": {**base_profile, "conflict_policy": "reject_on_conflict"}},
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == -32000
        data = getattr(exc, "data", {}) or {}
        assert data.get("conflict_policy") == "reject_on_conflict"
        assert data.get("reason") == "conflict"
    else:
        raise AssertionError("Expected reject_on_conflict mismatch to fail")

    try:
        response_result(
            "g2-vector",
            result_payload,
            method="tasks/cancel",
            params={"scale_profile": {**base_profile, "conflict_policy": "vector_clock"}},
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == -32000
        data = getattr(exc, "data", {}) or {}
        assert data.get("conflict_policy") == "vector_clock"
        assert data.get("reason") == "conflict"
        assert isinstance(data.get("competing_versions"), list)
        assert data.get("causality", {}).get("policy") == "vector_clock"
    else:
        raise AssertionError("Expected vector_clock mismatch to fail")

    payload = response_result(
        "g2-lww",
        result_payload,
        method="tasks/cancel",
        params={"scale_profile": {**base_profile, "conflict_policy": "last_write_wins"}},
    )
    result = payload["result"]
    assert result["resource_version"] == "rv:current"
    assert result["consistency_applied"] == "global_quorum"
    assert result["region_served"] == "us-west-2"


def test_g2_failover_resume_cursor_region_switch_seq_plus_one() -> None:
    cursor = build_signed_resume_cursor(
        stream_id="task-g2-failover",
        stream_epoch="epoch-g2-failover",
        seq=400,
        exp_unix_ms=5000,
        issued_at_unix_ms=1000,
        retention_until_unix_ms=4000,
        cursor_secret="g2-failover-secret",
    )
    parsed = parse_signed_resume_cursor(
        cursor,
        cursor_secret="g2-failover-secret",
        now_unix_ms=2000,
    )
    assert parsed["stream_id"] == "task-g2-failover"
    assert parsed["stream_epoch"] == "epoch-g2-failover"
    assert parsed["seq"] + 1 == 401


def test_g2_failover_resume_cursor_out_of_retention_rejected() -> None:
    cursor = build_signed_resume_cursor(
        stream_id="task-g2-failover-expired",
        stream_epoch="epoch-g2-failover-expired",
        seq=900,
        exp_unix_ms=5000,
        issued_at_unix_ms=1000,
        retention_until_unix_ms=1500,
        cursor_secret="g2-failover-secret",
    )
    try:
        parse_signed_resume_cursor(
            cursor,
            cursor_secret="g2-failover-secret",
            now_unix_ms=2000,
        )
    except Exception as exc:
        assert "retention" in str(exc).lower()
    else:
        raise AssertionError("Expected failover resume cursor outside retention to fail")


def test_scale_profile_matrix_has_expanded_g0_negative_coverage() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "nexus-a2a"
        / "artefacts"
        / "matrices"
        / "nexus_protocol_scale_profile_v1_1_matrix.json"
    )
    rows = json.loads(path.read_text(encoding="utf-8"))
    g0_negative = [
        row for row in rows if row.get("gate") == "g0" and row.get("scenario_type") == "negative"
    ]
    assert len(g0_negative) >= 5
    use_case_ids = {row.get("use_case_id") for row in g0_negative}
    assert {
        "UC-PROT-SCALE-G0-0001",
        "UC-PROT-SCALE-G0-0003",
        "UC-PROT-SCALE-G0-0004",
        "UC-PROT-SCALE-G0-0005",
        "UC-PROT-SCALE-G0-0006",
    }.issubset(use_case_ids)


def test_g0_required_field_reject_accept_pairs_complete() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "nexus-a2a"
        / "artefacts"
        / "matrices"
        / "nexus_protocol_scale_profile_v1_1_matrix.json"
    )
    rows = json.loads(path.read_text(encoding="utf-8"))
    required_fields = (
        "profile",
        "tenant_key",
        "user_key",
        "task_key",
        "shard_key",
        "idempotency_key",
        "scope",
        "dedup_window_ms",
        "payload_hash",
    )

    reject_fields: set[str] = set()
    accept_fields: set[str] = set()
    for row in rows:
        if row.get("gate") != "g0":
            continue

        payload = row.get("input_payload", {})
        if payload.get("method") not in {"tasks/send", "tasks/sendSubscribe", "tasks/cancel"}:
            continue

        expected_result = row.get("expected_result", {})
        if row.get("scenario_type") == "negative":
            field = expected_result.get("error_data_field")
            if isinstance(field, str) and field:
                reject_fields.add(field)

        if row.get("scenario_type") == "positive":
            params = payload.get("params", {})
            scale_profile = params.get("scale_profile", {})
            idempotency = params.get("idempotency", {})
            for field in ("profile", "tenant_key", "user_key", "task_key", "shard_key"):
                value = scale_profile.get(field)
                if isinstance(value, str) and value.strip():
                    accept_fields.add(field)
            for field in ("idempotency_key", "scope", "payload_hash"):
                value = idempotency.get(field)
                if isinstance(value, str) and value.strip():
                    accept_fields.add(field)
            dedup_window = idempotency.get("dedup_window_ms")
            if isinstance(dedup_window, int) and dedup_window > 0:
                accept_fields.add("dedup_window_ms")

    expected = set(required_fields)
    assert expected.issubset(reject_fields)
    assert expected.issubset(accept_fields)


def test_scale_profile_matrix_exists_and_has_all_gates() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "nexus-a2a"
        / "artefacts"
        / "matrices"
        / "nexus_protocol_scale_profile_v1_1_matrix.json"
    )
    rows = json.loads(path.read_text(encoding="utf-8"))
    gates = {row.get("gate") for row in rows}
    assert {"g0", "g1", "g2", "g3", "g4"}.issubset(gates)

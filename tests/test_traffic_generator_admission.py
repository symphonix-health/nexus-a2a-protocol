from __future__ import annotations

from tools.traffic_generator import validate_admission_rate_limit_payload


def test_validate_admission_rate_limit_payload_accepts_jsonrpc_contract() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "r1",
        "error": {
            "code": -32004,
            "message": "Rate limited",
            "data": {
                "retryable": True,
                "retry_after_ms": 250,
                "failure_domain": "network",
                "rate_limit_scope": "tenant",
                "bucket_id": "tenant-a:tasks/send",
                "limit_rps": 100.0,
                "observed_rps": 200.0,
            },
        },
    }
    ok, detail = validate_admission_rate_limit_payload(payload)
    assert ok is True
    assert detail == "validated"


def test_validate_admission_rate_limit_payload_rejects_missing_required_fields() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "r2",
        "error": {
            "code": -32004,
            "message": "Rate limited",
            "data": {
                "retryable": True,
                "retry_after_ms": 250,
                "failure_domain": "network",
                "rate_limit_scope": "tenant",
            },
        },
    }
    ok, detail = validate_admission_rate_limit_payload(payload)
    assert ok is False
    assert detail.startswith("missing_required_fields:")


def test_validate_admission_rate_limit_payload_rejects_non_network_failure_domain() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "r3",
        "error": {
            "code": -32004,
            "message": "Rate limited",
            "data": {
                "retryable": True,
                "retry_after_ms": 250,
                "failure_domain": "validation",
                "rate_limit_scope": "tenant",
                "bucket_id": "tenant-a:tasks/send",
                "limit_rps": 100.0,
                "observed_rps": 200.0,
            },
        },
    }
    ok, detail = validate_admission_rate_limit_payload(payload)
    assert ok is False
    assert detail == "failure_domain_must_be_network"

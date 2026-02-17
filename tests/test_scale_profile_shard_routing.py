from __future__ import annotations

import os

from nexus_a2a_protocol import validate_envelope
import nexus_a2a_protocol.jsonrpc as sdk_jsonrpc
from shared.nexus_common.jsonrpc import parse_request
from shared.nexus_common.scale_profile import build_canonical_shard_key


def _idempotency() -> dict:
    return {
        "idempotency_key": "idem-shard-1",
        "scope": "tenant-a:tasks/send",
        "dedup_window_ms": 60000,
        "payload_hash": "sha256:payload-shard-1",
    }


def _mutating_payload(*, scale_profile: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "shard-1",
        "method": "tasks/send",
        "params": {
            "task": {"id": "task-1"},
            "scale_profile": scale_profile,
            "idempotency": _idempotency(),
        },
    }


def _base_scale_profile(
    *,
    tenant_key: str = "tenant-a",
    user_key: str = "user-1",
    task_key: str = "task-1",
    shard_key: str | None = None,
) -> dict:
    canonical = build_canonical_shard_key(
        tenant_key=tenant_key.strip(),
        user_key=user_key.strip(),
        task_key=task_key.strip(),
    )
    return {
        "profile": "nexus-scale-v1.1",
        "tenant_key": tenant_key,
        "user_key": user_key,
        "task_key": task_key,
        "shard_key": shard_key or canonical,
    }


def test_parse_request_rejects_invalid_shard_key_prefix() -> None:
    payload = _mutating_payload(
        scale_profile=_base_scale_profile(shard_key="notsha256:1234"),
    )
    try:
        parse_request(payload)
    except Exception as exc:
        assert "invalid_shard_key_format" in str(exc)
    else:
        raise AssertionError("Expected invalid shard-key prefix to fail")


def test_parse_request_rejects_invalid_shard_key_hex_length() -> None:
    payload = _mutating_payload(
        scale_profile=_base_scale_profile(shard_key="sha256:" + ("a" * 63)),
    )
    try:
        parse_request(payload)
    except Exception as exc:
        assert "invalid_shard_key_format" in str(exc)
    else:
        raise AssertionError("Expected invalid shard-key digest length to fail")


def test_parse_request_rejects_uppercase_shard_key_digest() -> None:
    canonical = build_canonical_shard_key(
        tenant_key="tenant-a",
        user_key="user-1",
        task_key="task-1",
    )
    _, digest = canonical.split(":", 1)
    payload = _mutating_payload(
        scale_profile=_base_scale_profile(shard_key="sha256:" + digest.upper()),
    )
    try:
        parse_request(payload)
    except Exception as exc:
        assert "invalid_shard_key_format" in str(exc)
    else:
        raise AssertionError("Expected uppercase shard-key digest to fail")


def test_canonical_shard_key_accepts_whitespace_normalized_routing_tuple() -> None:
    profile = _base_scale_profile(
        tenant_key=" tenant-a ",
        user_key=" user-1 ",
        task_key=" task-1 ",
    )
    payload = _mutating_payload(scale_profile=profile)
    parse_request(payload)
    validate_envelope(payload)


def test_shared_and_sdk_shard_algorithms_match() -> None:
    expected = build_canonical_shard_key(
        tenant_key="tenant-x",
        user_key="user-y",
        task_key="task-z",
    )
    actual = sdk_jsonrpc._build_canonical_shard_key(  # noqa: SLF001 - parity regression check
        tenant_key="tenant-x",
        user_key="user-y",
        task_key="task-z",
    )
    assert actual == expected


def test_non_mutating_methods_do_not_require_scale_profile_under_strict_mode() -> None:
    os.environ["NEXUS_SCALE_PROFILE_STRICT"] = "true"
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "get-1",
            "method": "tasks/get",
            "params": {"task_id": "task-1"},
        }
        parsed = parse_request(payload)
        validated = validate_envelope(payload)
        assert parsed["method"] == "tasks/get"
        assert validated["method"] == "tasks/get"
    finally:
        os.environ.pop("NEXUS_SCALE_PROFILE_STRICT", None)

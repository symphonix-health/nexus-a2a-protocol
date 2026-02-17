from __future__ import annotations

from shared.nexus_common.idempotency import IdempotencyStore


def test_idempotency_window_expiry_with_deterministic_clock() -> None:
    now = [1000.0]
    store = IdempotencyStore(clock=lambda: now[0])

    first = store.check_or_register("idem-window", dedup_window_ms=1000, scope="tenant:a")
    assert first.is_duplicate is False
    assert first.first_seen_at == 1000.0

    now[0] = 1000.5
    second = store.check_or_register("idem-window", dedup_window_ms=1000, scope="tenant:a")
    assert second.is_duplicate is True
    assert second.first_seen_at == 1000.0

    now[0] = 1001.001
    third = store.check_or_register("idem-window", dedup_window_ms=1000, scope="tenant:a")
    assert third.is_duplicate is False
    assert third.first_seen_at == 1001.001


def test_idempotency_scope_isolation_is_deterministic() -> None:
    store = IdempotencyStore(clock=lambda: 5000.0)

    first = store.check_or_register("idem-scope", dedup_window_ms=1000, scope="tenant:a")
    second = store.check_or_register("idem-scope", dedup_window_ms=1000, scope="tenant:b")

    assert first.is_duplicate is False
    assert second.is_duplicate is False


def test_payload_mismatch_exposes_previous_hash_metadata() -> None:
    store = IdempotencyStore(clock=lambda: 7000.0)

    store.check_or_register(
        "idem-hash",
        dedup_window_ms=1000,
        scope="tenant:a:tasks/send",
        payload_hash="sha256:original",
    )
    second = store.check_or_register(
        "idem-hash",
        dedup_window_ms=1000,
        scope="tenant:a:tasks/send",
        payload_hash="sha256:new",
    )

    assert second.is_duplicate is True
    assert second.payload_mismatch is True
    assert second.incoming_payload_hash == "sha256:new"
    assert second.stored_payload_hash == "sha256:original"
    assert second.previous_payload_hash == "sha256:original"
    assert second.payload_hash == "sha256:original"

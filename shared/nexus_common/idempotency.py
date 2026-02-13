"""In-memory idempotency key store with TTL-based deduplication."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class IdempotencyResult:
    key: str
    is_duplicate: bool
    first_seen_at: float
    dedup_window_ms: int
    cached_response: dict[str, Any] | None = None


class IdempotencyStore:
    """Simple in-memory idempotency store suitable for single-process agents."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, int, dict[str, Any] | None]] = {}

    def check_or_register(
        self,
        key: str,
        dedup_window_ms: int,
        cached_response: dict[str, Any] | None = None,
    ) -> IdempotencyResult:
        if dedup_window_ms <= 0:
            raise ValueError("dedup_window_ms must be > 0")

        now = time.time()
        self._prune(now)

        existing = self._store.get(key)
        if existing is not None:
            first_seen_at, existing_window_ms, existing_response = existing
            return IdempotencyResult(
                key=key,
                is_duplicate=True,
                first_seen_at=first_seen_at,
                dedup_window_ms=existing_window_ms,
                cached_response=existing_response,
            )

        self._store[key] = (now, dedup_window_ms, cached_response)
        return IdempotencyResult(
            key=key,
            is_duplicate=False,
            first_seen_at=now,
            dedup_window_ms=dedup_window_ms,
            cached_response=cached_response,
        )

    def save_response(self, key: str, response: dict[str, Any]) -> None:
        if key not in self._store:
            return
        first_seen_at, dedup_window_ms, _ = self._store[key]
        self._store[key] = (first_seen_at, dedup_window_ms, dict(response))

    def _prune(self, now: float) -> None:
        expired_keys: list[str] = []
        for key, (first_seen_at, dedup_window_ms, _) in self._store.items():
            ttl_seconds = dedup_window_ms / 1000.0
            if now - first_seen_at > ttl_seconds:
                expired_keys.append(key)
        for key in expired_keys:
            self._store.pop(key, None)

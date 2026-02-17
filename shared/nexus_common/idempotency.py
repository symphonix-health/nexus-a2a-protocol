"""In-memory idempotency key store with TTL-based deduplication."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@dataclass(slots=True)
class IdempotencyResult:
    key: str
    is_duplicate: bool
    first_seen_at: float
    dedup_window_ms: int
    scope: str | None = None
    payload_hash: str | None = None
    incoming_payload_hash: str | None = None
    stored_payload_hash: str | None = None
    previous_payload_hash: str | None = None
    payload_mismatch: bool = False
    cached_response: dict[str, Any] | None = None


class IdempotencyStore:
    """Simple in-memory idempotency store suitable for single-process agents."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._store: dict[
            str,
            tuple[float, int, str | None, str | None, dict[str, Any] | None],
        ] = {}
        self._clock = clock or time.time

    def check_or_register(
        self,
        key: str,
        dedup_window_ms: int,
        scope: str | None = None,
        payload_hash: str | None = None,
        cached_response: dict[str, Any] | None = None,
        now_s: float | None = None,
    ) -> IdempotencyResult:
        if dedup_window_ms <= 0:
            raise ValueError("dedup_window_ms must be > 0")

        now = float(self._clock() if now_s is None else now_s)
        self._prune(now)

        full_key = f"{scope}:{key}" if scope else key
        existing = self._store.get(full_key)
        if existing is not None:
            first_seen_at, existing_window_ms, existing_scope, existing_hash, existing_response = existing
            payload_mismatch = False
            if payload_hash and existing_hash and payload_hash != existing_hash:
                payload_mismatch = True
            return IdempotencyResult(
                key=key,
                is_duplicate=True,
                first_seen_at=first_seen_at,
                dedup_window_ms=existing_window_ms,
                scope=existing_scope,
                payload_hash=existing_hash,
                incoming_payload_hash=payload_hash,
                stored_payload_hash=existing_hash,
                previous_payload_hash=existing_hash,
                payload_mismatch=payload_mismatch,
                cached_response=existing_response,
            )

        self._store[full_key] = (now, dedup_window_ms, scope, payload_hash, cached_response)
        return IdempotencyResult(
            key=key,
            is_duplicate=False,
            first_seen_at=now,
            dedup_window_ms=dedup_window_ms,
            scope=scope,
            payload_hash=payload_hash,
            incoming_payload_hash=payload_hash,
            stored_payload_hash=payload_hash,
            cached_response=cached_response,
        )

    def save_response(self, key: str, response: dict[str, Any], scope: str | None = None) -> None:
        full_key = f"{scope}:{key}" if scope else key
        if full_key not in self._store:
            return
        first_seen_at, dedup_window_ms, existing_scope, existing_hash, _ = self._store[full_key]
        self._store[full_key] = (
            first_seen_at,
            dedup_window_ms,
            existing_scope,
            existing_hash,
            dict(response),
        )

    def _prune(self, now: float) -> None:
        expired_keys: list[str] = []
        for key, (first_seen_at, dedup_window_ms, _, _, _) in self._store.items():
            ttl_seconds = dedup_window_ms / 1000.0
            if now - first_seen_at > ttl_seconds:
                expired_keys.append(key)
        for key in expired_keys:
            self._store.pop(key, None)


class RedisIdempotencyStore:
    """Redis-backed idempotency store for multi-process/multi-node agents."""

    def __init__(
        self,
        redis_url: str | None = None,
        namespace: str = "nexus:idempotency",
    ) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        if not self._redis_url:
            raise ValueError("Redis URL is required for RedisIdempotencyStore")
        self._namespace = namespace
        self._client: Any | None = None

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not REDIS_AVAILABLE:
            raise RuntimeError(
                "redis.asyncio is required for RedisIdempotencyStore. "
                "Install 'redis' package to enable this backend."
            )
        self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _key(self, idempotency_key: str) -> str:
        return f"{self._namespace}:{idempotency_key}"

    async def check_or_register(
        self,
        key: str,
        dedup_window_ms: int,
        scope: str | None = None,
        payload_hash: str | None = None,
        cached_response: dict[str, Any] | None = None,
        now_s: float | None = None,
    ) -> IdempotencyResult:
        if dedup_window_ms <= 0:
            raise ValueError("dedup_window_ms must be > 0")

        now = float(time.time() if now_s is None else now_s)
        full_key = f"{scope}:{key}" if scope else key
        store_key = self._key(full_key)
        client = await self._get_client()

        payload = json.dumps(
            {
                "first_seen_at": now,
                "dedup_window_ms": dedup_window_ms,
                "scope": scope,
                "payload_hash": payload_hash,
                "cached_response": cached_response,
            },
            separators=(",", ":"),
        )
        created = await client.set(store_key, payload, nx=True, px=dedup_window_ms)
        if created:
            return IdempotencyResult(
                key=key,
                is_duplicate=False,
                first_seen_at=now,
                dedup_window_ms=dedup_window_ms,
                scope=scope,
                payload_hash=payload_hash,
                incoming_payload_hash=payload_hash,
                stored_payload_hash=payload_hash,
                cached_response=cached_response,
            )

        raw = await client.get(store_key)
        if not raw:
            # Race on expiry: re-register and return non-duplicate.
            await client.set(store_key, payload, nx=True, px=dedup_window_ms)
            return IdempotencyResult(
                key=key,
                is_duplicate=False,
                first_seen_at=now,
                dedup_window_ms=dedup_window_ms,
                scope=scope,
                payload_hash=payload_hash,
                incoming_payload_hash=payload_hash,
                stored_payload_hash=payload_hash,
                cached_response=cached_response,
            )

        try:
            existing = json.loads(raw)
        except Exception:
            existing = {}

        first_seen_at = float(existing.get("first_seen_at", now))
        existing_window_ms = int(existing.get("dedup_window_ms", dedup_window_ms))
        existing_scope = existing.get("scope")
        existing_hash = existing.get("payload_hash")
        existing_response = existing.get("cached_response")
        if not isinstance(existing_response, dict):
            existing_response = None
        payload_mismatch = False
        if payload_hash and isinstance(existing_hash, str) and payload_hash != existing_hash:
            payload_mismatch = True

        return IdempotencyResult(
            key=key,
            is_duplicate=True,
            first_seen_at=first_seen_at,
            dedup_window_ms=existing_window_ms,
            scope=existing_scope if isinstance(existing_scope, str) else None,
            payload_hash=existing_hash if isinstance(existing_hash, str) else None,
            incoming_payload_hash=payload_hash,
            stored_payload_hash=existing_hash if isinstance(existing_hash, str) else None,
            previous_payload_hash=existing_hash if isinstance(existing_hash, str) else None,
            payload_mismatch=payload_mismatch,
            cached_response=existing_response,
        )

    async def save_response(
        self,
        key: str,
        response: dict[str, Any],
        scope: str | None = None,
    ) -> None:
        full_key = f"{scope}:{key}" if scope else key
        store_key = self._key(full_key)
        client = await self._get_client()
        raw = await client.get(store_key)
        if not raw:
            return
        try:
            data = json.loads(raw)
        except Exception:
            return

        data["cached_response"] = dict(response)
        ttl_ms = await client.pttl(store_key)
        if ttl_ms and ttl_ms > 0:
            await client.set(store_key, json.dumps(data, separators=(",", ":")), px=ttl_ms)
            return
        dedup_window_ms = int(data.get("dedup_window_ms", 60000))
        await client.set(
            store_key,
            json.dumps(data, separators=(",", ":")),
            px=dedup_window_ms,
        )

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.close()
        except Exception:
            pass

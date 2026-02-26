"""Server-Sent Events (SSE) support for NEXUS-A2A task streaming."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .protocol import ProgressState

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

CURSOR_REQUIRED_FIELDS = {"stream_id", "stream_epoch", "seq", "exp_unix_ms", "sig"}
CURSOR_OPTIONAL_FIELDS = {"iat_unix_ms", "retention_until_unix_ms"}


def _cursor_secret_from_env() -> str:
    return os.getenv(
        "NEXUS_STREAM_CURSOR_SECRET",
        os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me"),
    )


def _cursor_retention_ms_from_env() -> int:
    try:
        value = int(os.getenv("NEXUS_CURSOR_RETENTION_MS", "300000"))
    except Exception:
        value = 300000
    return max(1, value)


def _normalize_positive_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(value)
    except Exception as exc:
        raise ValueError(f"cursor invalid {field_name}") from exc
    if parsed <= 0:
        raise ValueError(f"cursor invalid {field_name}")
    return parsed


def _cursor_signable_payload_from_dict(payload: dict[str, Any]) -> dict[str, Any]:
    stream_id_str = str(payload.get("stream_id", "")).strip()
    stream_epoch_str = str(payload.get("stream_epoch", "")).strip()
    if not stream_id_str:
        raise ValueError("cursor stream_id must be non-empty")
    if not stream_epoch_str:
        raise ValueError("cursor stream_epoch must be non-empty")
    try:
        seq_int = int(payload.get("seq"))
    except Exception as exc:
        raise ValueError("cursor invalid seq") from exc
    if seq_int < 0:
        raise ValueError("cursor invalid seq")
    exp_int = _normalize_positive_int(payload.get("exp_unix_ms"), "exp_unix_ms")

    signable_payload: dict[str, Any] = {
        "stream_id": stream_id_str,
        "stream_epoch": stream_epoch_str,
        "seq": seq_int,
        "exp_unix_ms": exp_int,
    }

    if "iat_unix_ms" in payload:
        iat = _normalize_positive_int(payload.get("iat_unix_ms"), "iat_unix_ms")
        signable_payload["iat_unix_ms"] = iat
    if "retention_until_unix_ms" in payload:
        retention = _normalize_positive_int(
            payload.get("retention_until_unix_ms"),
            "retention_until_unix_ms",
        )
        signable_payload["retention_until_unix_ms"] = retention

    iat_value = signable_payload.get("iat_unix_ms")
    retention_value = signable_payload.get("retention_until_unix_ms")
    if iat_value is not None and iat_value > exp_int:
        raise ValueError("cursor invalid iat_unix_ms")
    if retention_value is not None and retention_value > exp_int:
        raise ValueError("cursor invalid retention_until_unix_ms")
    if iat_value is not None and retention_value is not None and retention_value < iat_value:
        raise ValueError("cursor invalid retention_until_unix_ms")

    return signable_payload


def build_signed_resume_cursor(
    *,
    stream_id: str,
    stream_epoch: str,
    seq: int,
    exp_unix_ms: int,
    issued_at_unix_ms: int | None = None,
    retention_until_unix_ms: int | None = None,
    cursor_secret: str | None = None,
) -> str:
    exp_value = _normalize_positive_int(exp_unix_ms, "exp_unix_ms")
    default_issued_at = min(exp_value, int(time.time() * 1000))
    issued_at = _normalize_positive_int(
        issued_at_unix_ms if issued_at_unix_ms is not None else default_issued_at,
        "iat_unix_ms",
    )
    retention_until = _normalize_positive_int(
        retention_until_unix_ms
        if retention_until_unix_ms is not None
        else min(exp_value, issued_at + _cursor_retention_ms_from_env()),
        "retention_until_unix_ms",
    )
    payload = {
        "stream_id": stream_id,
        "stream_epoch": stream_epoch,
        "seq": seq,
        "exp_unix_ms": exp_value,
        "iat_unix_ms": issued_at,
        "retention_until_unix_ms": retention_until,
    }
    signable_payload = _cursor_signable_payload_from_dict(payload)
    secret = cursor_secret or _cursor_secret_from_env()
    signable = json.dumps(signable_payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(
        secret.encode("utf-8"),
        signable.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload = dict(signable_payload)
    payload["sig"] = sig
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def parse_signed_resume_cursor(
    cursor: str,
    *,
    cursor_secret: str | None = None,
    now_unix_ms: int | None = None,
) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor.strip():
        raise ValueError("cursor must be non-empty string")
    token = cursor.strip()
    pad = "=" * ((4 - len(token) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode((token + pad).encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("cursor malformed") from exc

    if not isinstance(payload, dict):
        raise ValueError("cursor malformed")

    missing = CURSOR_REQUIRED_FIELDS - set(payload.keys())
    if missing:
        raise ValueError(f"cursor missing fields: {sorted(missing)}")

    signable_payload = _cursor_signable_payload_from_dict(payload)
    sig = str(payload.get("sig", "")).strip()
    if not sig:
        raise ValueError("invalid cursor signature")

    secret = cursor_secret or _cursor_secret_from_env()
    signable = json.dumps(signable_payload, separators=(",", ":"), sort_keys=True)
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        signable.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("invalid cursor signature")

    effective_now = int(time.time() * 1000) if now_unix_ms is None else int(now_unix_ms)
    if signable_payload["exp_unix_ms"] < effective_now:
        raise ValueError("cursor expired")
    retention_until = signable_payload.get("retention_until_unix_ms", signable_payload["exp_unix_ms"])
    if retention_until < effective_now:
        raise ValueError("cursor out of retention")

    parsed = dict(signable_payload)
    parsed["sig"] = sig
    return parsed


@dataclass
class SseEvent:
    """A single SSE event with type and data."""

    event: str
    data: Any
    seq: int | None = None
    stream_epoch: str | None = None
    ts_unix_ms: int | None = None


class TaskEventBus:
    """In-process async event bus for task lifecycle events.

    Supports multiple concurrent subscribers per task_id via SSE and WebSocket.
    Optionally publishes events to Redis for cross-agent monitoring.
    """

    def __init__(self, agent_name: str | None = None, redis_url: str | None = None) -> None:
        self._queues: dict[str, list[asyncio.Queue[SseEvent]]] = {}
        self._stream_seq: dict[str, int] = {}
        self._stream_epoch: dict[str, str] = {}
        self._history: dict[str, deque[SseEvent]] = {}
        self._history_last_ts: dict[str, int] = {}
        self._agent_name = agent_name or "unknown-agent"
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis_client: Any | None = None
        self._redis_enabled = False
        self._cursor_secret = _cursor_secret_from_env()
        self._history_max_events = max(1, int(os.getenv("NEXUS_STREAM_HISTORY_MAX_EVENTS", "1024")))
        self._history_retention_ms = _cursor_retention_ms_from_env()
        # Max JSONL file size before rotation (default 2 MB)
        self._persist_max_bytes = max(
            65536,
            int(os.getenv("NEXUS_TASK_EVENT_STORE_MAX_BYTES", str(2 * 1024 * 1024))),
        )
        self._persist_path = self._resolve_persist_path()
        self._load_persisted_history()

        # Initialize Redis if available
        if REDIS_AVAILABLE and self._redis_url:
            asyncio.create_task(self._init_redis())

    def _resolve_persist_path(self) -> Path | None:
        raw_path = (
            os.getenv("NEXUS_TASK_EVENT_STORE_PATH", "").strip()
            or os.getenv("NEXUS_STREAM_PERSIST_PATH", "").strip()
        )
        if not raw_path:
            default_enabled = os.getenv("NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT", "true").strip().lower()
            if default_enabled not in {"0", "false", "no", "off"}:
                raw_path = "temp/task_event_store/{agent}.jsonl"
        if not raw_path:
            return None
        agent = self._agent_name.replace("/", "-")
        resolved = Path(raw_path.format(agent=agent)).expanduser()
        if not resolved.is_absolute():
            resolved = Path.cwd() / resolved
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    def _load_persisted_history(self) -> None:
        if self._persist_path is None or not self._persist_path.exists():
            return
        # If the file is oversized, rotate it before loading so startup stays fast
        try:
            if self._persist_path.stat().st_size >= self._persist_max_bytes:
                self._rotate_persist_file()
        except Exception:
            pass
        try:
            with self._persist_path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                        task_id = str(item.get("task_id") or "").strip()
                        event = str(item.get("event") or "").strip()
                        if not task_id or not event:
                            continue
                        seq = int(item.get("seq"))
                        epoch = str(item.get("stream_epoch") or "").strip()
                        ts_unix_ms = int(item.get("ts_unix_ms"))
                        data = item.get("data")
                    except Exception:
                        continue
                    if not epoch:
                        continue
                    self._stream_epoch[task_id] = epoch
                    self._stream_seq[task_id] = max(self._stream_seq.get(task_id, 0), seq)
                    evt = SseEvent(
                        event=event,
                        data=data,
                        seq=seq,
                        stream_epoch=epoch,
                        ts_unix_ms=ts_unix_ms,
                    )
                    history = self._history.setdefault(task_id, deque(maxlen=self._history_max_events))
                    history.append(evt)
                    self._history_last_ts[task_id] = max(
                        int(self._history_last_ts.get(task_id, 0)),
                        ts_unix_ms,
                    )
        except Exception:
            # Persistence is optional; ignore load failures.
            return

    def _rotate_persist_file(self) -> None:
        """Rewrite the JSONL file keeping only events within the retention window."""
        if self._persist_path is None or not self._persist_path.exists():
            return
        now_ms = int(time.time() * 1000)
        min_ts = now_ms - self._history_retention_ms
        try:
            kept: list[str] = []
            with self._persist_path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        ts = int(json.loads(raw).get("ts_unix_ms", 0))
                    except Exception:
                        continue
                    if ts >= min_ts:
                        kept.append(raw)
            # Trim to at most history_max_events lines per rotation
            if len(kept) > self._history_max_events:
                kept = kept[-self._history_max_events :]
            tmp = self._persist_path.with_suffix(".jsonl.tmp")
            tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            tmp.replace(self._persist_path)
        except Exception:
            pass  # Rotation is best-effort

    def _persist_event(self, task_id: str, evt: SseEvent) -> None:
        if self._persist_path is None:
            return
        try:
            # Rotate before writing if file has grown too large
            try:
                if self._persist_path.stat().st_size >= self._persist_max_bytes:
                    self._rotate_persist_file()
            except FileNotFoundError:
                pass
            payload = {
                "task_id": task_id,
                "event": evt.event,
                "data": evt.data,
                "seq": evt.seq,
                "stream_epoch": evt.stream_epoch,
                "ts_unix_ms": evt.ts_unix_ms,
            }
            with self._persist_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, separators=(",", ":")))
                f.write("\n")
        except Exception:
            # Persistence is optional; ignore write failures.
            return

    def _persisted_stream_state(self, task_id: str) -> tuple[str, int] | None:
        if self._persist_path is None or not self._persist_path.exists():
            return None
        latest_epoch = ""
        latest_seq = -1
        try:
            with self._persist_path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except Exception:
                        continue
                    if str(item.get("task_id") or "").strip() != task_id:
                        continue
                    try:
                        seq = int(item.get("seq"))
                    except Exception:
                        continue
                    epoch = str(item.get("stream_epoch") or "").strip()
                    if not epoch:
                        continue
                    if seq > latest_seq:
                        latest_epoch = epoch
                        latest_seq = seq
        except Exception:
            return None
        if latest_seq < 0 or not latest_epoch:
            return None
        return latest_epoch, latest_seq

    def _replay_from_persisted_log(
        self,
        task_id: str,
        *,
        expected_epoch: str,
        since_seq: int,
        limit: int | None,
    ) -> list[dict[str, Any]] | None:
        if self._persist_path is None or not self._persist_path.exists():
            return None
        replay: list[dict[str, Any]] = []
        now_ms = int(time.time() * 1000)
        min_ts = now_ms - self._history_retention_ms
        try:
            with self._persist_path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except Exception:
                        continue
                    if str(item.get("task_id") or "").strip() != task_id:
                        continue
                    if str(item.get("stream_epoch") or "").strip() != expected_epoch:
                        continue
                    try:
                        seq = int(item.get("seq"))
                        ts_unix_ms = int(item.get("ts_unix_ms"))
                    except Exception:
                        continue
                    if seq <= since_seq:
                        continue
                    if ts_unix_ms < min_ts:
                        continue
                    replay.append(
                        {
                            "event": str(item.get("event") or ""),
                            "data": item.get("data"),
                            "stream": {
                                "stream_id": task_id,
                                "stream_epoch": expected_epoch,
                                "seq": seq,
                                "ts_unix_ms": ts_unix_ms,
                            },
                        }
                    )
                    if limit is not None and len(replay) >= limit:
                        break
        except Exception:
            return None
        return replay

    async def _init_redis(self) -> None:
        """Initialize Redis connection for pub/sub."""
        try:
            self._redis_client = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis_client.ping()
            self._redis_enabled = True
        except Exception:
            self._redis_enabled = False
            self._redis_client = None

    def subscribe(self, task_id: str) -> asyncio.Queue[SseEvent]:
        """Create a new subscription queue for a task."""
        if task_id not in self._queues:
            self._queues[task_id] = []
        q: asyncio.Queue[SseEvent] = asyncio.Queue()
        self._queues[task_id].append(q)
        return q

    def get_queue(self, task_id: str) -> asyncio.Queue[SseEvent]:
        """Get or create a default queue for backward compat (single subscriber)."""
        if task_id not in self._queues or not self._queues[task_id]:
            return self.subscribe(task_id)
        return self._queues[task_id][0]

    async def publish(
        self,
        task_id: str,
        event: str,
        data: Any,
        duration_ms: float = 0.0,
        scenario_context: dict[str, Any] | None = None,
        correlation: dict[str, Any] | None = None,
        idempotency: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
    ) -> None:
        """Publish an event to all subscribers for a task and optionally to Redis."""
        self._prune_history()
        if task_id not in self._queues:
            self._queues[task_id] = []
        seq = self._next_seq(task_id)
        epoch = self._stream_epoch[task_id]
        ts_unix_ms = int(time.time() * 1000)
        event_obj = SseEvent(
            event=event,
            data=data,
            seq=seq,
            stream_epoch=epoch,
            ts_unix_ms=ts_unix_ms,
        )
        history = self._history.setdefault(task_id, deque(maxlen=self._history_max_events))
        history.append(event_obj)
        self._history_last_ts[task_id] = ts_unix_ms
        self._persist_event(task_id, event_obj)
        for q in self._queues[task_id]:
            await q.put(event_obj)

        # Also publish to Redis for cross-agent monitoring
        await self._publish_to_redis(
            task_id,
            event,
            data,
            duration_ms,
            scenario_context=scenario_context,
            correlation=correlation,
            idempotency=idempotency,
            progress=progress,
            seq=seq,
            stream_epoch=epoch,
            ts_unix_ms=ts_unix_ms,
        )

    @staticmethod
    def normalize_progress_state(event: str, progress: dict[str, Any] | None) -> dict[str, Any]:
        """Build standardized progress-state contract payload."""
        if progress:
            payload = dict(progress)
            if payload.get("state") == "canceled":
                payload["state"] = "cancelled"
            return ProgressState(
                state=str(payload.get("state", "working")),
                percent=payload.get("percent"),
                eta_ms=payload.get("eta_ms"),
            ).to_dict()

        suffix = event.split(".")[-1].lower().strip()
        if suffix == "canceled":
            suffix = "cancelled"
        if suffix not in {"accepted", "working", "final", "error", "cancelled"}:
            suffix = "working"
        return ProgressState(state=suffix).to_dict()

    def build_event_payload(
        self,
        task_id: str,
        event: str,
        data: Any,
        duration_ms: float,
        scenario_context: dict[str, Any] | None = None,
        correlation: dict[str, Any] | None = None,
        idempotency: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        seq: int | None = None,
        stream_epoch: str | None = None,
        ts_unix_ms: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agent": self._agent_name,
            "task_id": task_id,
            "event": event,
            "data": data if isinstance(data, (dict, str)) else str(data),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "progress": self.normalize_progress_state(event, progress),
            "stream": {
                "stream_id": task_id,
                "stream_epoch": stream_epoch or self._stream_epoch.get(task_id) or self._new_stream_epoch(task_id),
                "seq": int(seq if seq is not None else self._next_seq(task_id)),
                "ts_unix_ms": int(ts_unix_ms if ts_unix_ms is not None else time.time() * 1000),
            },
        }
        if scenario_context:
            payload["scenario_context"] = dict(scenario_context)
        if correlation:
            payload["correlation"] = dict(correlation)
        if idempotency:
            payload["idempotency"] = dict(idempotency)
        return payload

    async def _publish_to_redis(
        self,
        task_id: str,
        event: str,
        data: Any,
        duration_ms: float,
        scenario_context: dict[str, Any] | None = None,
        correlation: dict[str, Any] | None = None,
        idempotency: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        seq: int | None = None,
        stream_epoch: str | None = None,
        ts_unix_ms: int | None = None,
    ) -> None:
        """Publish event to Redis pub/sub channel for command centre."""
        if not self._redis_enabled or not self._redis_client:
            return

        try:
            event_payload = self.build_event_payload(
                task_id,
                event,
                data,
                duration_ms,
                scenario_context=scenario_context,
                correlation=correlation,
                idempotency=idempotency,
                progress=progress,
                seq=seq,
                stream_epoch=stream_epoch,
                ts_unix_ms=ts_unix_ms,
            )
            await self._redis_client.publish("nexus:events", json.dumps(event_payload))
        except Exception:
            # Silently fail - Redis is optional
            pass

    async def stream(self, task_id: str) -> AsyncIterator[str]:
        """Yield SSE-formatted strings for a task until final or error."""
        q = self.subscribe(task_id)
        try:
            while True:
                evt = await q.get()
                data = evt.data if isinstance(evt.data, str) else json.dumps(evt.data)
                if evt.seq is not None:
                    yield f"id: {evt.seq}\nevent: {evt.event}\ndata: {data}\n\n"
                else:
                    yield f"event: {evt.event}\ndata: {data}\n\n"
                if evt.event in ("nexus.task.final", "nexus.task.error"):
                    break
        finally:
            self._unsubscribe(task_id, q)

    async def stream_ws(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield structured event dicts for WebSocket consumers."""
        q = self.subscribe(task_id)
        try:
            while True:
                evt = await q.get()
                data = evt.data if isinstance(evt.data, str) else json.dumps(evt.data)
                yield {
                    "event": evt.event,
                    "data": data,
                    "stream": {
                        "stream_id": task_id,
                        "stream_epoch": evt.stream_epoch,
                        "seq": evt.seq,
                        "ts_unix_ms": evt.ts_unix_ms,
                    },
                }
                if evt.event in ("nexus.task.final", "nexus.task.error"):
                    break
        finally:
            self._unsubscribe(task_id, q)

    def cleanup(self, task_id: str) -> None:
        """Remove live subscriber queues while preserving replay history."""
        self._queues.pop(task_id, None)

    async def close(self) -> None:
        """Close Redis connection if active."""
        if self._redis_client:
            try:
                await self._redis_client.close()
            except Exception:
                pass

    def _new_stream_epoch(self, task_id: str) -> str:
        epoch = uuid.uuid4().hex
        self._stream_epoch[task_id] = epoch
        self._stream_seq.setdefault(task_id, 0)
        return epoch

    def _next_seq(self, task_id: str) -> int:
        if task_id not in self._stream_seq:
            persisted = self._persisted_stream_state(task_id)
            if persisted is not None:
                epoch, seq = persisted
                self._stream_epoch[task_id] = epoch
                self._stream_seq[task_id] = max(self._stream_seq.get(task_id, 0), int(seq))
        self._stream_seq[task_id] = self._stream_seq.get(task_id, 0) + 1
        if task_id not in self._stream_epoch:
            self._new_stream_epoch(task_id)
        return self._stream_seq[task_id]

    def build_resume_cursor(
        self,
        task_id: str,
        *,
        expires_in_ms: int = 300000,
    ) -> str:
        stream_epoch = self._stream_epoch.get(task_id) or self._new_stream_epoch(task_id)
        seq = self._stream_seq.get(task_id, 0)
        return build_signed_resume_cursor(
            stream_id=task_id,
            stream_epoch=stream_epoch,
            seq=seq,
            exp_unix_ms=int(time.time() * 1000) + max(1, int(expires_in_ms)),
            cursor_secret=self._cursor_secret,
        )

    def parse_resume_cursor(self, cursor: str) -> dict[str, Any]:
        return parse_signed_resume_cursor(cursor, cursor_secret=self._cursor_secret)

    def replay_from_cursor(
        self,
        cursor: str,
        *,
        max_events: int | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Replay stream events after a validated signed resume cursor."""
        self._prune_history()
        parsed = self.parse_resume_cursor(cursor)
        task_id = parsed["stream_id"]
        expected_epoch = parsed["stream_epoch"]
        current_epoch = self._stream_epoch.get(task_id)
        if current_epoch is None:
            persisted = self._persisted_stream_state(task_id)
            if persisted is not None:
                current_epoch, seq = persisted
                self._stream_epoch[task_id] = current_epoch
                self._stream_seq[task_id] = max(self._stream_seq.get(task_id, 0), int(seq))
        if current_epoch is None:
            raise ValueError("task stream not found")
        if current_epoch != expected_epoch:
            raise ValueError("cursor stream_epoch mismatch")

        since_seq = int(parsed["seq"])
        limit = None
        if max_events is not None:
            try:
                limit = max(1, int(max_events))
            except Exception as exc:
                raise ValueError("max_events must be positive integer") from exc

        persisted_replay = self._replay_from_persisted_log(
            task_id,
            expected_epoch=expected_epoch,
            since_seq=since_seq,
            limit=limit,
        )
        if persisted_replay is not None:
            return task_id, persisted_replay

        history = self._history.get(task_id, deque())
        replay: list[dict[str, Any]] = []
        for evt in history:
            seq = int(evt.seq or 0)
            if seq <= since_seq:
                continue
            replay.append(self._event_to_payload(task_id, evt))
            if limit is not None and len(replay) >= limit:
                break
        return task_id, replay

    def _unsubscribe(self, task_id: str, queue: asyncio.Queue[SseEvent]) -> None:
        queues = self._queues.get(task_id)
        if not queues:
            return
        try:
            queues.remove(queue)
        except ValueError:
            return
        if not queues:
            self._queues.pop(task_id, None)

    def _event_to_payload(self, task_id: str, evt: SseEvent) -> dict[str, Any]:
        data: Any
        if isinstance(evt.data, str):
            stripped = evt.data.strip()
            if stripped and stripped[:1] in {"{", "["}:
                try:
                    data = json.loads(stripped)
                except Exception:
                    data = evt.data
            else:
                data = evt.data
        else:
            data = evt.data
        return {
            "event": evt.event,
            "data": data,
            "stream": {
                "stream_id": task_id,
                "stream_epoch": evt.stream_epoch,
                "seq": evt.seq,
                "ts_unix_ms": evt.ts_unix_ms,
            },
        }

    def _prune_history(self, now_unix_ms: int | None = None) -> None:
        now_ms = int(time.time() * 1000) if now_unix_ms is None else int(now_unix_ms)
        expired: list[str] = []
        for task_id, last_ts in self._history_last_ts.items():
            if now_ms - int(last_ts) <= self._history_retention_ms:
                continue
            if task_id in self._queues and self._queues.get(task_id):
                continue
            expired.append(task_id)
        for task_id in expired:
            self._history.pop(task_id, None)
            self._history_last_ts.pop(task_id, None)
            self._stream_seq.pop(task_id, None)
            self._stream_epoch.pop(task_id, None)

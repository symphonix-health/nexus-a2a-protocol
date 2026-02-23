"""Persistent task event store for resumable stream replay."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any


class SqliteTaskEventStore:
    """Lightweight SQLite-backed event store for `tasks/resubscribe` replay."""

    def __init__(self, path: str, *, retention_ms: int) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._retention_ms = max(1, int(retention_ms))
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_streams (
                    task_id TEXT PRIMARY KEY,
                    stream_epoch TEXT NOT NULL,
                    last_seq INTEGER NOT NULL,
                    updated_unix_ms INTEGER NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                    task_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    stream_epoch TEXT NOT NULL,
                    ts_unix_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (task_id, seq)
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_events_retention
                ON task_events (ts_unix_ms)
                """
            )

    def append_event(self, task_id: str, payload: dict[str, Any]) -> None:
        stream = payload.get("stream") if isinstance(payload.get("stream"), dict) else {}
        seq = int(stream.get("seq", 0))
        stream_epoch = str(stream.get("stream_epoch") or "").strip()
        ts_unix_ms = int(stream.get("ts_unix_ms", int(time.time() * 1000)))
        if not task_id or seq <= 0 or not stream_epoch:
            raise ValueError("invalid event payload for persistence")

        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO task_events(task_id, seq, stream_epoch, ts_unix_ms, payload_json)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        seq,
                        stream_epoch,
                        ts_unix_ms,
                        json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
                    ),
                )
                self._conn.execute(
                    """
                    INSERT INTO task_streams(task_id, stream_epoch, last_seq, updated_unix_ms)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        stream_epoch=excluded.stream_epoch,
                        last_seq=excluded.last_seq,
                        updated_unix_ms=excluded.updated_unix_ms
                    """,
                    (task_id, stream_epoch, seq, ts_unix_ms),
                )
            self.prune(now_unix_ms=ts_unix_ms)

    def get_stream_state(self, task_id: str) -> tuple[str, int] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT stream_epoch, last_seq FROM task_streams WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row[0]), int(row[1])

    def replay_after(
        self,
        task_id: str,
        *,
        since_seq: int,
        max_events: int | None,
    ) -> list[dict[str, Any]]:
        limit = None if max_events is None else max(1, int(max_events))
        query = (
            "SELECT payload_json FROM task_events WHERE task_id = ? AND seq > ? "
            "ORDER BY seq ASC"
        )
        params: tuple[Any, ...]
        if limit is None:
            params = (task_id, int(since_seq))
        else:
            query += " LIMIT ?"
            params = (task_id, int(since_seq), int(limit))
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        out: list[dict[str, Any]] = []
        for (payload_json,) in rows:
            try:
                payload = json.loads(str(payload_json))
            except Exception:
                continue
            if isinstance(payload, dict):
                out.append(payload)
        return out

    def prune(self, *, now_unix_ms: int | None = None) -> None:
        now_ms = int(time.time() * 1000) if now_unix_ms is None else int(now_unix_ms)
        floor = now_ms - self._retention_ms
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM task_events WHERE ts_unix_ms < ?", (floor,))
                self._conn.execute(
                    """
                    DELETE FROM task_streams
                    WHERE task_id NOT IN (SELECT DISTINCT task_id FROM task_events)
                    """
                )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def event_store_path_from_env() -> str | None:
    path = os.getenv("NEXUS_TASK_EVENT_STORE_PATH", "").strip()
    if path:
        return path
    default_enabled = os.getenv("NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT", "true").strip().lower()
    if default_enabled in {"0", "false", "no", "off"}:
        return None
    return str(Path("temp") / "task_event_store.sqlite3")

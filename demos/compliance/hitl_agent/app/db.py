"""SQLite persistence helpers for the HITL compliance interceptor."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

DB_PATH = "hitl_tasks.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                sender TEXT,
                content TEXT,
                risk_score INTEGER,
                status TEXT,
                timestamp TEXT,
                decision_comment TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def add_task(task_id: str, sender: str, content: str, risk_score: int) -> None:
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                sender,
                content,
                int(risk_score),
                "PENDING",
                datetime.now().isoformat(),
                "",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_pending_tasks() -> list[dict[str, Any]]:
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE status = 'PENDING'")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_decision(task_id: str, status: str, comment: str) -> None:
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET status = ?, decision_comment = ? WHERE id = ?",
            (status, comment, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_task(task_id: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

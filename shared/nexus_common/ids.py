"""Unique ID generators for NEXUS-A2A task lifecycle."""

from __future__ import annotations

import uuid


def make_task_id() -> str:
    return f"task-{uuid.uuid4()}"


def make_trace_id() -> str:
    return f"trace-{uuid.uuid4()}"


def make_conversation_id() -> str:
    return f"conv-{uuid.uuid4()}"

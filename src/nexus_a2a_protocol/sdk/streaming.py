"""SSE parsing and progress mapping for Nexus SDK transports."""

from __future__ import annotations

import json
from typing import Any

from .types import ProgressUpdate, TaskEvent, make_task_event



def parse_sse_chunk(chunk: str, *, task_id: str | None = None, agent_id: str = "unknown-agent") -> TaskEvent | None:
    """Parse a single SSE frame into a normalized TaskEvent."""
    event_name = ""
    data_lines: list[str] = []
    seq: int | None = None

    for raw_line in chunk.split("\n"):
        line = raw_line.rstrip("\r")
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        elif line.startswith("id:"):
            raw_id = line[len("id:") :].strip()
            try:
                seq = int(raw_id)
            except ValueError:
                pass

    if not event_name and not data_lines:
        return None

    raw_data = "\n".join(data_lines)
    try:
        parsed_data: Any = json.loads(raw_data)
    except (json.JSONDecodeError, ValueError):
        parsed_data = raw_data

    return make_task_event(
        event_type=event_name or "nexus.task.status",
        payload=parsed_data,
        task_id=task_id,
        seq=seq,
        agent_id=agent_id,
    )



def map_nexus_event_to_progress(evt: TaskEvent, current_progress: int = 0) -> ProgressUpdate:
    """Map task lifecycle events to monotonic progress values."""
    payload = evt.payload if isinstance(evt.payload, dict) else {}

    if evt.type == "nexus.task.final":
        return ProgressUpdate(progress=100, description="Task completed")

    if evt.type == "nexus.task.error":
        return ProgressUpdate(progress=max(current_progress, 99), description="Task error")

    status = payload.get("status", payload)
    if isinstance(status, dict):
        state = str(status.get("state") or "").strip().lower()
        percent = status.get("percent")
    else:
        state = str(status).strip().lower()
        percent = None

    if state == "accepted":
        return ProgressUpdate(progress=max(current_progress, 0), description="Task accepted")

    if state == "working":
        if percent is not None:
            try:
                pct = int(percent)
            except Exception:  # noqa: BLE001
                pct = current_progress + 1
            new = max(current_progress + 1, pct)
        else:
            new = max(current_progress + 1, 10)
        return ProgressUpdate(progress=min(new, 99), description="Task working")

    return ProgressUpdate(
        progress=min(current_progress + 1, 99),
        description=f"Event: {evt.type}",
    )

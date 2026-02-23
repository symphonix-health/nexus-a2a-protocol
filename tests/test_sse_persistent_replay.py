from __future__ import annotations

import os
from pathlib import Path

import pytest

from shared.nexus_common.sse import TaskEventBus


@pytest.mark.asyncio
async def test_resubscribe_replay_survives_bus_restart(tmp_path: Path) -> None:
    persist_path = tmp_path / "task_events.jsonl"
    previous_store_path = os.environ.get("NEXUS_TASK_EVENT_STORE_PATH")
    previous_default = os.environ.get("NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT")

    try:
        os.environ["NEXUS_TASK_EVENT_STORE_PATH"] = str(persist_path)
        os.environ["NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT"] = "true"

        task_id = "task-persist-1"
        bus_first = TaskEventBus(agent_name="persist-agent")
        await bus_first.publish(task_id, "nexus.task.status", {"state": "accepted"})
        resume_cursor = bus_first.build_resume_cursor(task_id, expires_in_ms=600000)
        await bus_first.publish(task_id, "nexus.task.status", {"state": "working"})
        await bus_first.publish(task_id, "nexus.task.final", {"state": "final"})
        await bus_first.close()

        bus_second = TaskEventBus(agent_name="persist-agent")
        replay_task_id, replay = bus_second.replay_from_cursor(
            resume_cursor,
            max_events=10,
        )
        await bus_second.close()

        assert replay_task_id == task_id
        assert len(replay) >= 2
        assert replay[0]["event"] == "nexus.task.status"
        assert replay[-1]["event"] == "nexus.task.final"
    finally:
        if previous_store_path is None:
            os.environ.pop("NEXUS_TASK_EVENT_STORE_PATH", None)
        else:
            os.environ["NEXUS_TASK_EVENT_STORE_PATH"] = previous_store_path

        if previous_default is None:
            os.environ.pop("NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT", None)
        else:
            os.environ["NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT"] = previous_default

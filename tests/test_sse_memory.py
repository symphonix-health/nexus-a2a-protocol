"""Memory regression tests for TaskEventBus.

Validates that the bus properly cleans up internal data structures
to prevent unbounded memory growth under sustained traffic.
"""

from __future__ import annotations

import os
import time

import pytest

# Override defaults before importing the module so tests run with
# small caps regardless of env.
os.environ.setdefault("NEXUS_STREAM_HISTORY_MAX_EVENTS", "16")
os.environ.setdefault("NEXUS_STREAM_HISTORY_MAX_TASKS", "20")
os.environ.setdefault("NEXUS_STREAM_PRUNE_INTERVAL_MS", "0")

from shared.nexus_common.sse import TaskEventBus  # noqa: E402


def _make_bus(**kwargs) -> TaskEventBus:
    """Create a bus with small caps for testing."""
    env_overrides = {
        "NEXUS_STREAM_HISTORY_MAX_EVENTS": "16",
        "NEXUS_STREAM_HISTORY_MAX_TASKS": "20",
        "NEXUS_STREAM_PRUNE_INTERVAL_MS": "0",  # prune every publish
        "NEXUS_STREAM_HISTORY_RETENTION_MS": "100",  # 100ms retention
        "NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT": "false",  # no disk I/O
    }
    for k, v in env_overrides.items():
        os.environ[k] = v
    try:
        return TaskEventBus(agent_name="test-agent", **kwargs)
    finally:
        for k in env_overrides:
            os.environ.pop(k, None)


# ── Orphaned queue tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_without_subscribe_no_queue_leak():
    """Publishing to 100 tasks without subscribing should not leak _queues entries."""
    bus = _make_bus()
    for i in range(100):
        await bus.publish(f"task-{i}", "nexus.task.status", {"state": "working"})
        await bus.publish(f"task-{i}", "nexus.task.final", {"state": "done"})

    # _queues should have no entries since no one subscribed
    assert len(bus._queues) == 0


@pytest.mark.asyncio
async def test_subscriber_creates_queue_entry():
    """Subscribing should create a _queues entry that is removed on unsubscribe."""
    bus = _make_bus()
    q = bus.subscribe("task-sub")
    assert "task-sub" in bus._queues
    assert len(bus._queues["task-sub"]) == 1

    # Unsubscribe via cleanup
    bus.cleanup("task-sub")
    assert "task-sub" not in bus._queues


# ── Prune / retention tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_prune_cleans_all_dicts():
    """After retention expires, all 5 internal dicts should be cleaned."""
    bus = _make_bus()
    await bus.publish("old-task", "nexus.task.final", {"done": True})

    # Verify task is tracked
    assert "old-task" in bus._history
    assert "old-task" in bus._history_last_ts
    assert "old-task" in bus._stream_seq
    assert "old-task" in bus._stream_epoch

    # Wait for retention to expire (100ms)
    time.sleep(0.15)

    # Trigger pruning via a new publish
    await bus.publish("new-task", "nexus.task.status", {"state": "working"})

    # Old task should be fully cleaned
    assert "old-task" not in bus._history
    assert "old-task" not in bus._history_last_ts
    assert "old-task" not in bus._stream_seq
    assert "old-task" not in bus._stream_epoch
    assert "old-task" not in bus._queues


# ── Task cap eviction tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_history_task_cap_evicts_oldest():
    """When task count exceeds max, oldest tasks should be evicted."""
    bus = _make_bus()
    max_tasks = bus._history_max_tasks  # 20

    # Create more than max_tasks
    for i in range(max_tasks + 15):
        await bus.publish(f"task-{i:04d}", "nexus.task.final", {"i": i})

    # Should be capped at max_tasks
    assert len(bus._history) <= max_tasks
    assert len(bus._history_last_ts) <= max_tasks

    # Newest tasks should survive
    assert f"task-{max_tasks + 14:04d}" in bus._history


@pytest.mark.asyncio
async def test_active_subscribers_survive_cap_eviction():
    """Tasks with active subscribers should not be evicted by cap enforcement."""
    bus = _make_bus()
    max_tasks = bus._history_max_tasks

    # Subscribe to an early task
    await bus.publish("protected-task", "nexus.task.status", {"state": "working"})
    _q = bus.subscribe("protected-task")

    # Fill past the cap
    for i in range(max_tasks + 10):
        await bus.publish(f"filler-{i:04d}", "nexus.task.final", {"i": i})

    # The protected task should survive because it has a subscriber
    assert "protected-task" in bus._history

    # Cleanup
    bus.cleanup("protected-task")


# ── Prune frequency gate ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_prune_frequency_gate():
    """With a prune interval, prune should not run on every publish."""
    os.environ["NEXUS_STREAM_PRUNE_INTERVAL_MS"] = "60000"  # 60s
    os.environ["NEXUS_STREAM_HISTORY_RETENTION_MS"] = "1"  # 1ms
    os.environ["NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT"] = "false"
    os.environ["NEXUS_STREAM_HISTORY_MAX_TASKS"] = "1000"
    try:
        bus = TaskEventBus(agent_name="test-gated")
        # Force last prune to now so the gate blocks future prunes
        bus._last_prune_ms = int(time.time() * 1000)

        for i in range(50):
            await bus.publish(f"gated-{i}", "nexus.task.final", {"i": i})

        # Even though retention is 1ms, the 60s gate prevents pruning
        # so all 50 tasks remain in history
        assert len(bus._history) == 50
    finally:
        os.environ.pop("NEXUS_STREAM_PRUNE_INTERVAL_MS", None)
        os.environ.pop("NEXUS_STREAM_HISTORY_RETENTION_MS", None)
        os.environ.pop("NEXUS_TASK_EVENT_STORE_ENABLE_DEFAULT", None)
        os.environ.pop("NEXUS_STREAM_HISTORY_MAX_TASKS", None)


# ── get_stats tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bus_get_stats():
    """get_stats should return all expected keys with correct types."""
    bus = _make_bus()
    await bus.publish("stats-task", "nexus.task.status", {"state": "working"})
    await bus.publish("stats-task", "nexus.task.final", {"state": "done"})

    stats = bus.get_stats()
    assert isinstance(stats, dict)
    assert stats["tasks_tracked"] >= 1
    assert stats["tasks_with_subscribers"] == 0
    assert stats["total_events_in_memory"] >= 2
    assert isinstance(stats["history_max_events_per_task"], int)
    assert isinstance(stats["history_max_tasks"], int)
    assert isinstance(stats["history_retention_ms"], int)


@pytest.mark.asyncio
async def test_bus_get_stats_with_subscriber():
    """get_stats should count active subscribers."""
    bus = _make_bus()
    await bus.publish("sub-task", "nexus.task.status", {"state": "working"})
    _q = bus.subscribe("sub-task")

    stats = bus.get_stats()
    assert stats["tasks_with_subscribers"] == 1

    bus.cleanup("sub-task")
    stats = bus.get_stats()
    assert stats["tasks_with_subscribers"] == 0

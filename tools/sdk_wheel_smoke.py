#!/usr/bin/env python3
"""Installed-wheel smoke checks for Nexus SDK transport surface."""

from __future__ import annotations

import asyncio


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def _run_async_smoke() -> None:
    from nexus_a2a_protocol import SimulationTransport, TaskEnvelope, map_nexus_event_to_progress

    transport = SimulationTransport()
    await transport.connect()
    submission = await transport.send_task(
        TaskEnvelope(method="tasks/sendSubscribe", params={"task": {"type": "SmokeTask"}})
    )
    _assert(bool(submission.task_id), "simulation submission missing task_id")

    progress = 0
    seen_terminal = False
    async for evt in transport.stream_events(submission.task_id):
        mapped = map_nexus_event_to_progress(evt, progress)
        _assert(mapped.progress >= progress, "progress must be monotonic")
        progress = mapped.progress
        if evt.is_terminal:
            seen_terminal = True
            break

    _assert(seen_terminal, "expected terminal event from simulation transport")
    await transport.stop()


def main() -> int:
    from nexus_a2a_protocol import (
        AgentTransport,
        HttpSseTransport,
        TransportFactory,
        WebSocketTransport,
    )

    _assert(issubclass(HttpSseTransport, AgentTransport), "HttpSseTransport must implement AgentTransport")
    _assert(issubclass(WebSocketTransport, AgentTransport), "WebSocketTransport must implement AgentTransport")

    transport = TransportFactory.from_env(mode="simulation")
    _assert(transport.__class__.__name__ == "SimulationTransport", "factory simulation mode mismatch")

    asyncio.run(_run_async_smoke())
    print("sdk wheel smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

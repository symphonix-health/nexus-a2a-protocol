from __future__ import annotations

import pytest

from nexus_a2a_protocol import (
    AgentCard,
    AgentNotRegisteredError,
    InMemoryAgent,
    InMemoryNexus,
    new_agent_message,
)


def test_in_memory_nexus_round_trip() -> None:
    nexus = InMemoryNexus()
    nexus.register(InMemoryAgent(AgentCard(agent_id="client"), handler=lambda msg: msg))
    nexus.register(
        InMemoryAgent(
            AgentCard(agent_id="echo"),
            handler=lambda msg: new_agent_message(f"echo:{msg.parts[0].text}"),
        )
    )

    task = nexus.send_text_task("client", "echo", "ping")

    assert task.status.state == "completed"
    assert task.artifacts[-1].parts[0].text == "echo:ping"


def test_in_memory_nexus_requires_registered_recipient() -> None:
    nexus = InMemoryNexus()
    nexus.register(InMemoryAgent(AgentCard(agent_id="client"), handler=lambda msg: msg))

    with pytest.raises(AgentNotRegisteredError):
        nexus.send_text_task("client", "missing", "ping")

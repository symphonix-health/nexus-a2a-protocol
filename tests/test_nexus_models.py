from __future__ import annotations

import pytest

from nexus_a2a_protocol import Message, ProtocolValidationError, Task, TextPart, new_agent_message


def test_message_round_trip() -> None:
    message = Message(role="user", parts=[TextPart(text="hello nexus")])
    decoded = Message.from_dict(message.to_dict())
    assert decoded.role == "user"
    assert decoded.parts[0].text == "hello nexus"


def test_message_rejects_invalid_role() -> None:
    with pytest.raises(ProtocolValidationError):
        Message(role="system", parts=[TextPart(text="not valid")])


def test_task_status_history_progresses() -> None:
    task = Task()
    task.set_status("working")
    task.set_status("completed", new_agent_message("done"))
    assert [status.state for status in task.history] == ["submitted", "working", "completed"]
    assert task.artifacts == []

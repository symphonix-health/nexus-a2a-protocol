"""Core data models for the Nexus A2A protocol draft."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .errors import ProtocolValidationError

VALID_ROLES = {"user", "agent"}
VALID_TASK_STATES = {
    "submitted",
    "working",
    "input-required",
    "completed",
    "failed",
    "canceled",
}


def _new_id() -> str:
    return uuid4().hex


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class TextPart:
    """Single text part in a protocol message."""

    text: str
    kind: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind != "text":
            raise ProtocolValidationError("TextPart.kind must be 'text'")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ProtocolValidationError("TextPart.text must be a non-empty string")
        if not isinstance(self.metadata, dict):
            raise ProtocolValidationError("TextPart.metadata must be a dictionary")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind, "text": self.text}
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TextPart:
        if not isinstance(payload, dict):
            raise ProtocolValidationError("TextPart payload must be a dictionary")
        return cls(
            text=str(payload.get("text", "")),
            kind=str(payload.get("kind", "text")),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class Message:
    """A2A-style message with role and content parts."""

    role: str
    parts: list[TextPart]
    message_id: str = field(default_factory=_new_id)
    kind: str = "message"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind != "message":
            raise ProtocolValidationError("Message.kind must be 'message'")
        if self.role not in VALID_ROLES:
            raise ProtocolValidationError(f"Message.role must be one of {sorted(VALID_ROLES)}")
        if not self.parts:
            raise ProtocolValidationError("Message.parts must contain at least one part")
        if any(not isinstance(part, TextPart) for part in self.parts):
            raise ProtocolValidationError("Message.parts may only contain TextPart values")
        if not isinstance(self.metadata, dict):
            raise ProtocolValidationError("Message.metadata must be a dictionary")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "messageId": self.message_id,
            "role": self.role,
            "parts": [part.to_dict() for part in self.parts],
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Message:
        if not isinstance(payload, dict):
            raise ProtocolValidationError("Message payload must be a dictionary")

        parts = payload.get("parts")
        if not isinstance(parts, list):
            raise ProtocolValidationError("Message.parts must be a list")

        return cls(
            role=str(payload.get("role", "")),
            parts=[TextPart.from_dict(part) for part in parts],
            message_id=str(payload.get("messageId", _new_id())),
            kind=str(payload.get("kind", "message")),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class TaskStatus:
    """Task lifecycle state for async task execution."""

    state: str
    timestamp: str = field(default_factory=_utc_now)
    message: Message | None = None

    def __post_init__(self) -> None:
        if self.state not in VALID_TASK_STATES:
            raise ProtocolValidationError(
                f"TaskStatus.state must be one of {sorted(VALID_TASK_STATES)}"
            )
        if self.message is not None and not isinstance(self.message, Message):
            raise ProtocolValidationError("TaskStatus.message must be a Message or None")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"state": self.state, "timestamp": self.timestamp}
        if self.message is not None:
            payload["message"] = self.message.to_dict()
        return payload


@dataclass(slots=True)
class Task:
    """A simple task container used by the PoC transport."""

    task_id: str = field(default_factory=_new_id)
    session_id: str = field(default_factory=_new_id)
    status: TaskStatus = field(default_factory=lambda: TaskStatus(state="submitted"))
    history: list[TaskStatus] = field(default_factory=list)
    artifacts: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.history:
            self.history.append(self.status)

    def set_status(self, state: str, message: Message | None = None) -> TaskStatus:
        next_status = TaskStatus(state=state, message=message)
        self.status = next_status
        self.history.append(next_status)
        return next_status

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "sessionId": self.session_id,
            "status": self.status.to_dict(),
            "history": [status.to_dict() for status in self.history],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


def new_user_message(text: str) -> Message:
    """Create a validated user message containing one text part."""

    return Message(role="user", parts=[TextPart(text=text)])


def new_agent_message(text: str) -> Message:
    """Create a validated agent message containing one text part."""

    return Message(role="agent", parts=[TextPart(text=text)])

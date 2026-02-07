"""In-memory proof-of-concept transport for local A2A task exchange."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .errors import AgentNotRegisteredError
from .models import Message, Task, new_user_message

MessageHandler = Callable[[Message], Message]


@dataclass(slots=True)
class AgentCard:
    """Minimal agent metadata used by the PoC registry."""

    agent_id: str
    endpoint: str = "local://in-memory"
    protocol_version: str = "1.0"
    capabilities: list[str] = field(default_factory=lambda: ["tasks/send", "tasks/get"])


@dataclass(slots=True)
class InMemoryAgent:
    """In-memory agent with a synchronous message handler."""

    card: AgentCard
    handler: MessageHandler

    def handle(self, message: Message) -> Message:
        return self.handler(message)


class InMemoryNexus:
    """Simple local registry for routing messages between agents."""

    def __init__(self) -> None:
        self._agents: dict[str, InMemoryAgent] = {}

    def register(self, agent: InMemoryAgent) -> None:
        self._agents[agent.card.agent_id] = agent

    def send_text_task(self, sender_id: str, recipient_id: str, text: str) -> Task:
        sender = self._agents.get(sender_id)
        recipient = self._agents.get(recipient_id)

        if sender is None:
            raise AgentNotRegisteredError(f"Sender is not registered: {sender_id}")
        if recipient is None:
            raise AgentNotRegisteredError(f"Recipient is not registered: {recipient_id}")

        _ = sender  # Sender existence is validated even though it is not used further in this PoC.

        inbound = new_user_message(text)
        task = Task()
        task.set_status("working", inbound)

        outbound = recipient.handle(inbound)
        task.artifacts.append(outbound)
        task.set_status("completed", outbound)
        return task

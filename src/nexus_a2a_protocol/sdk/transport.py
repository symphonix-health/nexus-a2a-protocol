"""Transport abstraction for simulation and Nexus runtime adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Mapping

from .types import TaskEnvelope, TaskEvent, TaskSubmission


class AgentTransport(ABC):
    """Stable transport contract consumed by tests and orchestration layers."""

    @abstractmethod
    async def connect(self) -> None:
        """Prepare underlying transport resources."""

    @abstractmethod
    async def send_task(self, task: TaskEnvelope | Mapping[str, Any]) -> TaskSubmission:
        """Send task request and return normalized submission details."""

    @abstractmethod
    async def stream_events(self, task_id: str) -> AsyncIterator[TaskEvent]:
        """Yield lifecycle events for a task until terminal event."""

    @abstractmethod
    async def stop(self) -> None:
        """Release transport resources."""

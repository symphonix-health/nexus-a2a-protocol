"""Nexus A2A Protocol SDK."""

from .errors import AgentNotRegisteredError, ProtocolValidationError
from .jsonrpc import (
    A2A_METHODS,
    FAILURE_DOMAINS,
    make_error,
    make_error_data,
    make_request,
    make_result,
    validate_envelope,
)
from .models import Message, Task, TaskStatus, TextPart, new_agent_message, new_user_message
from .poc import AgentCard, InMemoryAgent, InMemoryNexus
from .sdk import (
    AgentTransport,
    HttpSseTransport,
    SimulationTransport,
    TaskEnvelope,
    TaskEvent,
    TaskSubmission,
    TransportError,
    TransportFactory,
    WebSocketTransport,
    map_nexus_event_to_progress,
)

__all__ = [
    "A2A_METHODS",
    "FAILURE_DOMAINS",
    "AgentCard",
    "AgentNotRegisteredError",
    "InMemoryAgent",
    "InMemoryNexus",
    "Message",
    "ProtocolValidationError",
    "Task",
    "TaskEnvelope",
    "TaskEvent",
    "TaskSubmission",
    "TaskStatus",
    "TextPart",
    "TransportError",
    "TransportFactory",
    "AgentTransport",
    "SimulationTransport",
    "HttpSseTransport",
    "WebSocketTransport",
    "map_nexus_event_to_progress",
    "make_error",
    "make_error_data",
    "make_request",
    "make_result",
    "new_agent_message",
    "new_user_message",
    "validate_envelope",
]

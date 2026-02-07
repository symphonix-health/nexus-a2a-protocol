"""Custom exceptions for Nexus A2A protocol validation and PoC transport."""


class ProtocolValidationError(ValueError):
    """Raised when protocol payloads fail structural validation."""


class AgentNotRegisteredError(LookupError):
    """Raised when a sender or recipient agent is not registered."""

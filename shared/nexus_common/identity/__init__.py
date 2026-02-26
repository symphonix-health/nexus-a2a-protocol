"""NEXUS Identity module — persona registry and agent IAM configuration."""

from .agent_identity import AgentIdentity, AgentIdentityRegistry, get_agent_identity, get_agent_registry
from .persona_registry import PersonaRegistry, get_persona_registry

__all__ = [
    "AgentIdentity",
    "AgentIdentityRegistry",
    "PersonaRegistry",
    "get_agent_identity",
    "get_agent_registry",
    "get_persona_registry",
]

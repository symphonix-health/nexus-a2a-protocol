"""Agent identity — load an agent's persona + IAM config from agent_personas.json.

Usage::

    from shared.nexus_common.identity import get_agent_identity

    identity = get_agent_identity("clinician_avatar_agent")
    persona  = identity.primary_persona        # Persona dataclass
    groups   = identity.iam_groups             # ["nexus-clinical-high"]
    scopes   = identity.delegated_scopes       # list[str]
    can_send_sms = identity.can_send_sms       # bool

    # Select country-appropriate persona
    persona_for_uk = identity.persona_for_country("uk")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .persona_registry import Persona, get_persona_registry

_AGENT_PERSONAS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "agent_personas.json"
)


@dataclass
class CommunicationPermissions:
    send_sms: bool = False
    send_email: bool = False
    receive_sms: bool = False
    receive_email: bool = False
    sms_scope: str = ""
    email_scope: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CommunicationPermissions":
        return cls(
            send_sms=bool(d.get("send_sms", False)),
            send_email=bool(d.get("send_email", False)),
            receive_sms=bool(d.get("receive_sms", False)),
            receive_email=bool(d.get("receive_email", False)),
            sms_scope=str(d.get("sms_scope") or ""),
            email_scope=str(d.get("email_scope") or ""),
            note=str(d.get("note") or ""),
        )


@dataclass
class AgentIdentity:
    agent_id: str
    port: int
    primary_persona_id: str
    alternate_persona_ids: dict[str, str]
    iam_groups: list[str]
    delegated_scopes: list[str]
    can_delegate_to: list[str]
    can_receive_delegation_from: list[str]
    communication: CommunicationPermissions
    purpose_of_use: str
    autonomous_actions: list[str]
    avatar_style: dict[str, Any]
    scenario_roles: dict[str, list[str]]

    # -----------------------------------------------------------------------

    @property
    def primary_persona(self) -> Persona:
        registry = get_persona_registry()
        return registry.require(self.primary_persona_id)

    def persona_for_country(self, country: str) -> Persona:
        """Return country-appropriate persona, falling back to primary."""
        registry = get_persona_registry()
        key = country.lower()
        pid = self.alternate_persona_ids.get(key)
        if pid:
            p = registry.get(pid)
            if p:
                return p
        return self.primary_persona

    def persona_for_scenario(self, country: str = "uk", care_setting: str = "") -> Persona:
        """Pick the most contextually appropriate persona for avatar sessions."""
        # Special-case mappings first (e.g., uk_telehealth)
        registry = get_persona_registry()
        if care_setting:
            for k, pid in self.alternate_persona_ids.items():
                if care_setting.lower() in k.lower():
                    p = registry.get(pid)
                    if p:
                        return p
        return self.persona_for_country(country)

    @property
    def can_send_sms(self) -> bool:
        return self.communication.send_sms

    @property
    def can_send_email(self) -> bool:
        return self.communication.send_email

    @property
    def can_receive_sms(self) -> bool:
        return self.communication.receive_sms

    @property
    def can_receive_email(self) -> bool:
        return self.communication.receive_email

    def entra_app_role_assignments(self) -> list[dict[str, str]]:
        """Return app role assignment payloads for Microsoft Graph API provisioning."""
        primary = self.primary_persona
        return [
            {
                "principalDisplayName": f"NEXUS Agent — {self.agent_id}",
                "resourceDisplayName": "NEXUS A2A Platform",
                "appRoleId_hint": primary.bulletrain_role,
                "group_membership": self.iam_groups,
            }
        ]

    def graph_api_send_mail_payload(
        self,
        to_address: str,
        subject: str,
        body_html: str,
    ) -> dict[str, Any]:
        """
        Build a Microsoft Graph API /sendMail payload.
        The agent must have Mail.Send application permission granted in Entra.
        """
        if not self.can_send_email:
            raise PermissionError(
                f"Agent '{self.agent_id}' does not have send_email permission. "
                f"Scope: {self.communication.email_scope or 'none'}"
            )
        persona = self.primary_persona
        return {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": to_address}}],
                "from": {
                    "emailAddress": {
                        "name": f"NEXUS {persona.name}",
                        "address": f"nexus-{self.agent_id.replace('_', '-')}@placeholder.nexus",
                    }
                },
            },
            "saveToSentItems": True,
        }

    def graph_api_send_sms_payload(
        self,
        to_number: str,
        message: str,
    ) -> dict[str, Any]:
        """
        Placeholder payload for SMS via Azure Communication Services.
        Agent must have the ACS Send SMS role.
        See: https://learn.microsoft.com/azure/communication-services/quickstarts/sms/send
        """
        if not self.can_send_sms:
            raise PermissionError(
                f"Agent '{self.agent_id}' does not have send_sms permission. "
                f"Scope: {self.communication.sms_scope or 'none'}"
            )
        return {
            "from": f"+1-NEXUS-{self.agent_id[:6].upper()}",
            "to": [to_number],
            "message": message,
            "smsSendOptions": {"enableDeliveryReport": True},
        }

    @classmethod
    def from_dict(cls, agent_id: str, data: dict[str, Any]) -> "AgentIdentity":
        iam = data.get("iam") or {}
        comm_raw = iam.get("communication_permissions") or {}
        return cls(
            agent_id=agent_id,
            port=int(data.get("port") or 0),
            primary_persona_id=str(data.get("primary_persona_id") or "P001"),
            alternate_persona_ids=dict(data.get("alternate_personas") or {}),
            iam_groups=list(iam.get("groups") or []),
            delegated_scopes=list(iam.get("delegated_scopes") or []),
            can_delegate_to=list(iam.get("can_delegate_to") or []),
            can_receive_delegation_from=list(iam.get("can_receive_delegation_from") or []),
            communication=CommunicationPermissions.from_dict(comm_raw),
            purpose_of_use=str(iam.get("purpose_of_use") or "Treatment"),
            autonomous_actions=list(iam.get("autonomous_actions") or []),
            avatar_style=dict(data.get("avatar_style") or {}),
            scenario_roles=dict(data.get("scenario_roles") or {"primary": [], "secondary": []}),
        )


class AgentIdentityRegistry:
    """Registry of all agent identities loaded from config/agent_personas.json."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._agents: dict[str, AgentIdentity] = {
            agent_id: AgentIdentity.from_dict(agent_id, agent_data)
            for agent_id, agent_data in (data.get("agents") or {}).items()
        }
        self._iam_groups: dict[str, Any] = data.get("iam_groups") or {}

    def get(self, agent_id: str) -> AgentIdentity | None:
        return self._agents.get(agent_id)

    def require(self, agent_id: str) -> AgentIdentity:
        a = self.get(agent_id)
        if a is None:
            raise KeyError(f"Unknown agent_id '{agent_id}' in agent_personas.json")
        return a

    def agents_for_scenario(self, scenario_name: str, role: str = "primary") -> list[AgentIdentity]:
        """Return agents that have a primary or secondary role in a given scenario."""
        return [
            a for a in self._agents.values()
            if scenario_name in a.scenario_roles.get(role, [])
        ]

    def agents_in_group(self, group_name: str) -> list[AgentIdentity]:
        return [a for a in self._agents.values() if group_name in a.iam_groups]

    def all(self) -> list[AgentIdentity]:
        return list(self._agents.values())

    def iam_group_config(self, group_name: str) -> dict[str, Any]:
        return dict(self._iam_groups.get(group_name) or {})


@lru_cache(maxsize=1)
def _load_agent_registry() -> AgentIdentityRegistry:
    path = os.path.normpath(_AGENT_PERSONAS_PATH)
    with open(path, encoding="utf-8") as fh:
        return AgentIdentityRegistry(json.load(fh))


def get_agent_identity(agent_id: str) -> AgentIdentity:
    """Return the AgentIdentity for a named agent (raises KeyError if unknown)."""
    return _load_agent_registry().require(agent_id)


def get_agent_registry() -> AgentIdentityRegistry:
    """Return the full AgentIdentityRegistry singleton."""
    return _load_agent_registry()

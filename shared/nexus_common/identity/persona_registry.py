"""Persona registry — load and query the 68 clinical/operational personas.

Usage::

    from shared.nexus_common.identity import get_persona_registry

    registry = get_persona_registry()
    persona = registry.get("P004")          # Triage Nurse
    avatar_kwargs = persona.to_avatar_dict() # dict accepted by AvatarEngine
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

_PERSONAS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "personas.json"
)


@dataclass
class Persona:
    persona_id: str
    name: str
    country_context: str
    care_setting: str
    domain: str
    role_description: str
    integration_use_cases: list[str]
    primary_systems: list[str]
    fhir_resources: list[str]
    hl7v2_messages: list[str]
    data_access_level: str | None
    iam: dict[str, Any]
    compliance: dict[str, Any]

    # Derived helpers -------------------------------------------------------

    @property
    def bulletrain_role(self) -> str:
        return str(self.iam.get("bulletrain_role") or "patient_service")

    @property
    def rbac_level(self) -> str:
        return str(self.iam.get("rbac_level") or "Restricted")

    @property
    def data_sensitivity(self) -> str:
        return str(self.iam.get("data_sensitivity") or "Low")

    @property
    def scopes(self) -> list[str]:
        return list(self.iam.get("bulletrain_scopes") or [])

    @property
    def smart_fhir_scopes(self) -> list[str]:
        return list(self.iam.get("smart_fhir_scopes") or [])

    @property
    def communication_style(self) -> str:
        """Inferred style for avatar prompt from domain + role."""
        domain = self.domain.lower()
        if "clinical" in domain:
            return "calm, empathetic, and precise"
        if "pharmacy" in domain:
            return "thorough, safety-focused, and friendly"
        if "lab" in domain or "imaging" in domain:
            return "analytical and detail-oriented"
        if "governance" in domain or "iam" in domain:
            return "formal, compliance-oriented"
        if "admin" in domain or "records" in domain:
            return "efficient and process-driven"
        return "professional and helpful"

    def to_avatar_dict(self) -> dict[str, Any]:
        """Return a persona dict compatible with AvatarEngine.start_session()."""
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "role": self.domain.lower().replace(" ", "_"),
            "style": self.communication_style,
            "specialty": self.care_setting,
            "country_context": self.country_context,
            "role_description": self.role_description,
            "data_sensitivity": self.data_sensitivity,
            "rbac_level": self.rbac_level,
        }

    def to_jwt_claims_dict(self) -> dict[str, Any]:
        """Extra JWT claims that can be embedded when minting a persona-scoped token."""
        return {
            "persona_id": self.persona_id,
            "persona_name": self.name,
            "bulletrain_role": self.bulletrain_role,
            "rbac_level": self.rbac_level,
            "scopes": self.scopes,
            "purpose_of_use": self.iam.get("purpose_of_use", "Treatment"),
            "data_sensitivity": self.data_sensitivity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Persona":
        return cls(
            persona_id=data["persona_id"],
            name=data["name"],
            country_context=str(data.get("country_context") or ""),
            care_setting=str(data.get("care_setting") or ""),
            domain=str(data.get("domain") or ""),
            role_description=str(data.get("role_description") or ""),
            integration_use_cases=list(data.get("integration_use_cases") or []),
            primary_systems=list(data.get("primary_systems") or []),
            fhir_resources=list(data.get("fhir_resources") or []),
            hl7v2_messages=list(data.get("hl7v2_messages") or []),
            data_access_level=data.get("data_access_level"),
            iam=dict(data.get("iam") or {}),
            compliance=dict(data.get("compliance") or {}),
        )


class PersonaRegistry:
    """In-memory registry of all 68 personas keyed by persona_id."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._raw = data
        self._personas: dict[str, Persona] = {
            p["persona_id"]: Persona.from_dict(p) for p in data.get("personas", [])
        }
        self._rbac_roles: dict[str, Any] = data.get("bulletrain_rbac_roles", {})
        self._pou_codes: dict[str, str] = data.get("purpose_of_use_codes", {})
        self._sensitivity_tiers: dict[str, str] = data.get("data_sensitivity_tiers", {})

    # Lookup -----------------------------------------------------------------

    def get(self, persona_id: str) -> Persona | None:
        return self._personas.get(persona_id)

    def require(self, persona_id: str) -> Persona:
        p = self.get(persona_id)
        if p is None:
            raise KeyError(f"Unknown persona_id '{persona_id}'")
        return p

    def filter(
        self,
        *,
        country: str | None = None,
        domain: str | None = None,
        bulletrain_role: str | None = None,
        rbac_level: str | None = None,
    ) -> list[Persona]:
        results = list(self._personas.values())
        if country:
            c = country.lower()
            results = [p for p in results if c in p.country_context.lower()]
        if domain:
            d = domain.lower()
            results = [p for p in results if d in p.domain.lower()]
        if bulletrain_role:
            results = [p for p in results if p.bulletrain_role == bulletrain_role]
        if rbac_level:
            results = [p for p in results if p.rbac_level.lower() == rbac_level.lower()]
        return results

    def all(self) -> list[Persona]:
        return list(self._personas.values())

    def rbac_role(self, role_name: str) -> dict[str, Any]:
        return dict(self._rbac_roles.get(role_name) or {})

    def scopes_for_role(self, role_name: str) -> list[str]:
        return list((self._rbac_roles.get(role_name) or {}).get("default_scopes") or [])

    # Selection helpers ------------------------------------------------------

    def avatar_persona_for_scenario(
        self,
        scenario_domain: str = "clinical",
        country: str = "uk",
        care_setting: str | None = None,
    ) -> Persona:
        """Select the most appropriate avatar persona for a given scenario context."""
        # Priority: clinical high-rbac in matching country
        candidates = self.filter(domain=scenario_domain, country=country, rbac_level="High")
        if not candidates:
            candidates = self.filter(domain="clinical", country=country)
        if not candidates:
            candidates = self.filter(domain="clinical")
        # Prefer telehealth persona for remote consultations
        if care_setting and "telehealth" in care_setting.lower():
            telehealth = [p for p in candidates if "telehealth" in p.care_setting.lower()]
            if telehealth:
                return telehealth[0]
        return candidates[0] if candidates else self.require("P001")


@lru_cache(maxsize=1)
def _load_registry() -> PersonaRegistry:
    path = os.path.normpath(_PERSONAS_PATH)
    with open(path, encoding="utf-8") as fh:
        return PersonaRegistry(json.load(fh))


def get_persona_registry() -> PersonaRegistry:
    """Return the singleton PersonaRegistry (loaded once from config/personas.json)."""
    return _load_registry()

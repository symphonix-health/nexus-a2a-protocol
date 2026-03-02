"""Policy Information Point (PIP) adapters for patient-level constraints."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_POLICY_DATA_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "policy" / "patient_policy_data.json"
)


@dataclass(frozen=True)
class PatientPolicyContext:
    consent_granted: bool = True
    care_team: tuple[str, ...] = ()
    allowed_purposes_of_use: tuple[str, ...] = ()
    break_glass_allowed: bool = False
    requires_break_glass: bool = False
    redaction_profile: str | None = None


class InMemoryPolicyInformationProvider:
    """Deterministic PIP for local development and tests.

    Data shape is loaded from JSON and keyed by patient_id.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._defaults = data.get("defaults", {}) if isinstance(data, dict) else {}
        self._patients = data.get("patients", {}) if isinstance(data, dict) else {}

    @classmethod
    def from_file(cls, path: Path) -> "InMemoryPolicyInformationProvider":
        if not path.is_file():
            return cls({})
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            loaded = {}
        if not isinstance(loaded, dict):
            loaded = {}
        return cls(loaded)

    def for_patient(self, patient_id: str | None) -> PatientPolicyContext:
        merged: dict[str, Any] = dict(self._defaults)
        if patient_id:
            patient_cfg = self._patients.get(str(patient_id), {})
            if isinstance(patient_cfg, dict):
                merged.update(patient_cfg)

        return PatientPolicyContext(
            consent_granted=bool(merged.get("consent_granted", True)),
            care_team=tuple(str(v) for v in merged.get("care_team", []) if str(v).strip()),
            allowed_purposes_of_use=tuple(
                str(v) for v in merged.get("allowed_purposes_of_use", []) if str(v).strip()
            ),
            break_glass_allowed=bool(merged.get("break_glass_allowed", False)),
            requires_break_glass=bool(merged.get("requires_break_glass", False)),
            redaction_profile=str(merged.get("redaction_profile") or "").strip() or None,
        )


def _policy_data_path() -> Path:
    raw = os.getenv("NEXUS_POLICY_DATA_PATH", "").strip()
    return Path(raw) if raw else _DEFAULT_POLICY_DATA_PATH


@lru_cache(maxsize=1)
def get_policy_information_provider() -> InMemoryPolicyInformationProvider:
    return InMemoryPolicyInformationProvider.from_file(_policy_data_path())


def reload_policy_information_provider() -> InMemoryPolicyInformationProvider:
    get_policy_information_provider.cache_clear()
    return get_policy_information_provider()

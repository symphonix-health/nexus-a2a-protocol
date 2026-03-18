"""Audit logger for pathway personalisation decisions.

Every personalisation decision produces an auditable record containing
patient ID (pseudonymised), timestamp, decision rationale, modifications
made, and the requesting agent/role.  This supports GDPR, Caldicott,
and clinical governance requirements.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import PersonalisedPathway

logger = logging.getLogger(__name__)


class AuditEntry(BaseModel):
    """A single audit record for a pathway personalisation decision."""

    audit_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    patient_id_pseudonymised: str
    pathway_id: str
    pathway_title: str
    requesting_role: str = ""
    requesting_agent: str = ""
    purpose: str = "direct_care"
    modification_count: int = 0
    modifications_summary: list[str] = Field(default_factory=list)
    safety_warnings: list[str] = Field(default_factory=list)
    confidence: str = "high"
    clinician_override_recommended: bool = False
    context_factors_used: list[str] = Field(default_factory=list)


class AuditLogger:
    """Logs pathway personalisation decisions to an append-only audit trail."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir
        self._entries: list[AuditEntry] = []
        self._counter = 0

    def log_personalisation(
        self,
        result: PersonalisedPathway,
        *,
        requesting_role: str = "",
        requesting_agent: str = "",
        purpose: str = "direct_care",
    ) -> AuditEntry:
        """Create and store an audit entry for a personalisation decision."""
        self._counter += 1
        entry = AuditEntry(
            audit_id=f"AUDIT-CP-{self._counter:06d}",
            patient_id_pseudonymised=result.patient_id,
            pathway_id=result.pathway_id,
            pathway_title=result.pathway_title,
            requesting_role=requesting_role,
            requesting_agent=requesting_agent,
            purpose=purpose,
            modification_count=result.explainability.modification_count,
            modifications_summary=[m.description for m in result.explainability.modifications],
            safety_warnings=result.explainability.safety_warnings,
            confidence=result.explainability.confidence.value,
            clinician_override_recommended=result.explainability.clinician_override_recommended,
            context_factors_used=list({
                f for m in result.explainability.modifications for f in m.context_factors
            }),
        )

        self._entries.append(entry)
        self._persist(entry)

        logger.info(
            "Audit: %s — pathway=%s patient=%s modifications=%d safety_warnings=%d",
            entry.audit_id,
            entry.pathway_id,
            entry.patient_id_pseudonymised,
            entry.modification_count,
            len(entry.safety_warnings),
        )
        return entry

    def get_entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def get_entries_for_patient(self, patient_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.patient_id_pseudonymised == patient_id]

    def _persist(self, entry: AuditEntry) -> None:
        """Persist audit entry to file if log_dir is configured."""
        if self._log_dir is None:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self._log_dir / "pathway_audit.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

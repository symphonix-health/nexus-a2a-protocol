from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AvatarSession:
    session_id: str
    patient_case: dict[str, Any]
    persona: dict[str, Any]
    consultation_phase: str = "initiating"
    framework: str = "calgary_cambridge"
    framework_progress: dict[str, Any] = field(default_factory=dict)
    collected_findings: dict[str, Any] = field(default_factory=dict)
    investigations_ordered: list[dict[str, Any]] = field(default_factory=list)
    investigations_results: dict[str, Any] = field(default_factory=dict)
    clinical_actions: list[dict[str, Any]] = field(default_factory=list)
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    llm_config: dict[str, Any] = field(
        default_factory=dict,
    )
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

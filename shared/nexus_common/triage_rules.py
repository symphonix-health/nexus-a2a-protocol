"""Consolidated ESI triage rule evaluation.

Replaces the duplicated keyword/vital-based triage logic that was
previously hardcoded in three separate files:

- ``demos/ed-triage/triage-agent/app/main.py``
- ``demos/ed-triage/diagnosis-agent/app/main.py``
- ``shared/nexus_common/generic_demo_agent.py``

Rules are stored in the seed database and evaluated in priority order.
When the seed DB is unavailable (e.g. startup-safe mode), a hardcoded
fallback provides the same canonical rule set.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("nexus.triage-rules")

# ── Fallback rules (used when seed DB is unavailable) ───────────────────
_FALLBACK_RULES: list[tuple[str, str, str, str, str]] = [
    # (condition_type, field, operator, value, esi_level)
    ("keyword", "chief_complaint", "contains", "chest", "ESI-2"),
    ("keyword", "chief_complaint", "contains", "shortness of breath", "ESI-2"),
    ("vital_threshold", "spo2", "lt", "90", "ESI-2"),
    ("keyword", "chief_complaint", "contains", "confusion", "ESI-2"),
    ("vital_threshold", "temp_c", "gte", "39.0", "ESI-2"),
    ("keyword", "chief_complaint", "contains", "laceration", "ESI-4"),
    ("default", "_", "eq", "_", "ESI-3"),
]


def _apply_rules(
    rules: list[tuple[str, str, str, str, str]],
    complaint: str,
    vitals: dict[str, Any],
) -> str:
    complaint_lower = complaint.lower() if complaint else ""
    for condition_type, field, operator, value, esi_level in rules:
        if condition_type == "keyword":
            if operator == "contains" and value.lower() in complaint_lower:
                return esi_level
        elif condition_type == "vital_threshold":
            try:
                vital_val = float(vitals.get(field, float("nan")))
            except (TypeError, ValueError):
                continue
            threshold = float(value)
            if operator == "lt" and vital_val < threshold:
                return esi_level
            if operator == "gte" and vital_val >= threshold:
                return esi_level
        elif condition_type == "default":
            return esi_level
    return "ESI-3"


def evaluate_triage(
    complaint: str,
    vitals: dict[str, Any] | None = None,
) -> str:
    """Evaluate triage rules and return the ESI level (e.g. ``"ESI-2"``).

    Tries the seed database first; falls back to the hardcoded canonical
    rules if the database is unavailable.
    """
    vitals = vitals or {}
    try:
        from shared.nexus_common.seed_db import get_seed_db

        return get_seed_db().evaluate_triage_rules(complaint, vitals)
    except Exception:
        logger.debug("Seed DB unavailable; using fallback triage rules")
        return _apply_rules(_FALLBACK_RULES, complaint, vitals)


def evaluate_triage_from_task(task: dict[str, Any]) -> str:
    """Extract complaint and vitals from a task dict and evaluate triage.

    This is a convenience wrapper matching the signature previously used
    by triage and diagnosis agents.
    """
    complaint = str(
        task.get("chief_complaint")
        or (task.get("inputs") or {}).get("chief_complaint", "")
    ).strip()
    vitals = task.get("vitals") if isinstance(task.get("vitals"), dict) else {}
    return evaluate_triage(complaint, vitals)

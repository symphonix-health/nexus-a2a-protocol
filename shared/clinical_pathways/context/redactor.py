"""PHI redactor — de-identifies patient context for LLM consumption.

When patient context is passed to an AI agent prompt, personally
identifiable information must be stripped or pseudonymised to prevent
leakage.  This module provides that transformation.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .models import Demographics, PatientContext


class PHIRedactor:
    """Strips or pseudonymises PHI fields from a PatientContext."""

    # Fields to redact from demographics
    REDACTED_FIELDS: set[str] = {
        "given_name",
        "family_name",
        "national_id",
        "address",
        "telecom",
    }

    def redact(self, context: PatientContext, *, keep_age: bool = True) -> PatientContext:
        """Return a new PatientContext with PHI redacted.

        - Names, national ID, address, telecom → replaced with pseudonyms.
        - Date of birth → removed (age retained if keep_age=True).
        - Patient ID → hashed.
        - All other clinical data preserved as-is.
        """
        pid = context.demographics.patient_id
        pseudo_id = self._pseudonymise(pid)

        redacted_demographics = Demographics(
            patient_id=pseudo_id,
            given_name="[REDACTED]",
            family_name="[REDACTED]",
            date_of_birth=None,
            age=context.age if keep_age else None,
            gender=context.demographics.gender,
            national_id="[REDACTED]",
            address="[REDACTED]",
            telecom="[REDACTED]",
            language=context.demographics.language,
        )

        return context.model_copy(update={"demographics": redacted_demographics})

    @staticmethod
    def _pseudonymise(value: str) -> str:
        """One-way hash to create a pseudonymous identifier."""
        return hashlib.sha256(value.encode()).hexdigest()[:16]

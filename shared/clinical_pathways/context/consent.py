"""Consent checker — validates patient consent before context release.

Under UK GDPR and NHS policy, use of confidential patient information
requires a lawful basis.  This module enforces consent checks before
the Patient Context Service returns data.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import ConsentStatus, PatientContext

logger = logging.getLogger(__name__)


class ConsentDeniedError(Exception):
    """Raised when patient consent does not permit data access."""

    def __init__(self, patient_id: str, reason: str = ""):
        self.patient_id = patient_id
        self.reason = reason
        super().__init__(f"Consent denied for patient {patient_id}: {reason}")


class ConsentChecker:
    """Validates that the patient's consent permits context release.

    For direct care the implied-consent exception applies.
    For secondary use (analytics, research) explicit opt-in is required.
    """

    # Sensitive condition codes requiring additional consent checks
    SENSITIVE_CATEGORIES: set[str] = {
        "mental_health",
        "sexual_health",
        "substance_misuse",
        "hiv",
        "genetic_condition",
        "fertility",
    }

    def check(
        self,
        context: PatientContext,
        *,
        purpose: str = "direct_care",
        requesting_role: str = "",
    ) -> PatientContext:
        """Validate consent and return the (possibly filtered) context.

        Raises ConsentDeniedError if the patient has explicitly opted out.
        """
        pid = context.demographics.patient_id

        # Hard deny if consent is explicitly denied
        if context.consent_status == ConsentStatus.DENIED:
            raise ConsentDeniedError(pid, "Patient has opted out of data sharing")

        # Secondary use requires explicit consent
        if purpose != "direct_care" and context.consent_status != ConsentStatus.ACTIVE:
            raise ConsentDeniedError(
                pid,
                f"Secondary use purpose '{purpose}' requires explicit consent; "
                f"current status is '{context.consent_status.value}'",
            )

        # Filter sensitive conditions if purpose is not direct care
        if purpose != "direct_care":
            context = self._filter_sensitive(context)

        logger.info(
            "Consent check passed: patient=%s purpose=%s role=%s",
            pid,
            purpose,
            requesting_role,
        )
        return context

    def _filter_sensitive(self, context: PatientContext) -> PatientContext:
        """Remove Caldicott-sensitive data categories for non-direct-care use."""
        filtered_conditions = [
            c for c in context.conditions if c.code.lower() not in self.SENSITIVE_CATEGORIES
        ]
        return context.model_copy(update={"conditions": filtered_conditions})

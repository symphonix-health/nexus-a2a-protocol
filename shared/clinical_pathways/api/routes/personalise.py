"""Pathway personalisation endpoint — the main entry point.

POST /v1/pathways/personalise
  Takes a pathway_id + patient context JSON → returns a personalised
  encounter journey with full explainability.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...context.assembler import ContextAssembler
from ...context.consent import ConsentChecker, ConsentDeniedError
from ...context.redactor import PHIRedactor
from ...engine.personaliser import PathwayPersonaliser
from ...repository import PathwayRepository

router = APIRouter(prefix="/v1/pathways", tags=["personalisation"])

# Injected at app startup
_repo: PathwayRepository | None = None
_personaliser: PathwayPersonaliser | None = None
_assembler = ContextAssembler()
_consent = ConsentChecker()
_redactor = PHIRedactor()


def set_dependencies(repo: PathwayRepository, personaliser: PathwayPersonaliser) -> None:
    global _repo, _personaliser
    _repo = repo
    _personaliser = personaliser


class PersonaliseRequest(BaseModel):
    pathway_id: str
    patient_context: dict[str, Any]
    requesting_role: str = ""
    requesting_agent: str = ""
    purpose: str = "direct_care"
    redact_phi: bool = True


class PersonaliseResponse(BaseModel):
    pathway_id: str
    pathway_title: str
    patient_id: str
    personalised_at: str
    modification_count: int
    confidence: str
    safety_warnings: list[str] = Field(default_factory=list)
    clinician_override_recommended: bool
    encounter_journey_summary: str
    explainability: dict[str, Any]
    personalised_nodes: list[dict[str, Any]]


@router.post("/personalise", response_model=PersonaliseResponse)
async def personalise_pathway(request: PersonaliseRequest):
    if _repo is None or _personaliser is None:
        raise HTTPException(503, "Service not initialised")

    # 1. Look up pathway
    pathway = _repo.get(request.pathway_id)
    if pathway is None:
        raise HTTPException(404, f"Pathway '{request.pathway_id}' not found")

    # 2. Assemble patient context
    try:
        context = _assembler.assemble(request.patient_context)
    except Exception as exc:
        raise HTTPException(422, f"Invalid patient context: {exc}") from exc

    # 3. Check consent
    try:
        context = _consent.check(
            context,
            purpose=request.purpose,
            requesting_role=request.requesting_role,
        )
    except ConsentDeniedError as exc:
        raise HTTPException(403, str(exc)) from exc

    # 4. Personalise
    result = _personaliser.personalise(
        pathway,
        context,
        requesting_role=request.requesting_role,
        requesting_agent=request.requesting_agent,
    )

    # 5. Build response
    return PersonaliseResponse(
        pathway_id=result.pathway_id,
        pathway_title=result.pathway_title,
        patient_id=result.patient_id,
        personalised_at=result.personalised_at.isoformat(),
        modification_count=result.explainability.modification_count,
        confidence=result.explainability.confidence.value,
        safety_warnings=result.explainability.safety_warnings,
        clinician_override_recommended=result.explainability.clinician_override_recommended,
        encounter_journey_summary=result.encounter_journey_summary,
        explainability=result.explainability.model_dump(),
        personalised_nodes=[n.model_dump() for n in result.nodes],
    )

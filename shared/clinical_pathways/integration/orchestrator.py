"""Pathway Orchestrator — wires personalisation output to downstream agents.

Coordinates the full clinical workflow:
  1. Receives patient context + pathway ID
  2. Calls PathwayPersonaliser to produce PersonalisedPathway
  3. Routes output to appropriate BulletTrain agents via adapters
  4. Collects results and produces an integrated care plan

This orchestrator can be invoked by:
  - ChatAssistant (interactive clinical queries)
  - GHARRA agent discovery (pathway-personalisation capability)
  - Direct API call from BulletTrain workflow engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..context.models import PatientContext
from ..engine.models import ConfidenceLevel, ModificationType, PersonalisedPathway
from ..engine.personaliser import PathwayPersonaliser
from ..models import PathwayDefinition
from . import adapters

logger = logging.getLogger(__name__)


@dataclass
class AgentDispatch:
    """Record of a downstream agent invocation."""

    agent_name: str
    adapter_used: str
    input_payload: dict[str, Any]
    dispatched: bool = True
    reason: str = ""


@dataclass
class OrchestrationResult:
    """Full result of pathway-to-agent orchestration."""

    pathway: PersonalisedPathway
    dispatches: list[AgentDispatch] = field(default_factory=list)
    integrated_plan: dict[str, Any] = field(default_factory=dict)
    orchestrated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def agent_count(self) -> int:
        return len([d for d in self.dispatches if d.dispatched])

    @property
    def has_safety_blocks(self) -> bool:
        return any(not d.dispatched for d in self.dispatches)


class PathwayOrchestrator:
    """Routes PersonalisedPathway output to downstream BulletTrain agents.

    Does NOT make network calls — builds dispatch payloads that can be
    sent to agents via Nexus A2A, direct HTTP, or in-process invocation.
    """

    def __init__(
        self,
        personaliser: PathwayPersonaliser,
    ) -> None:
        self._personaliser = personaliser

    def orchestrate(
        self,
        pathway: PathwayDefinition,
        context: PatientContext,
        *,
        chief_complaint: str = "",
        diagnosis: str = "",
        specialty: str = "",
        requesting_role: str = "",
        requesting_agent: str = "",
    ) -> OrchestrationResult:
        """Run full personalisation + agent dispatch pipeline.

        1. Personalise pathway
        2. Build dispatches for each relevant downstream agent
        3. Return integrated result
        """
        # 1. Personalise
        personalised = self._personaliser.personalise(
            pathway,
            context,
            requesting_role=requesting_role,
            requesting_agent=requesting_agent,
        )

        dispatches: list[AgentDispatch] = []

        # 2. Diagnostic reasoning — always dispatched
        diag_ctx = adapters.to_diagnostic_context(
            personalised,
            patient_id=context.demographics.patient_id,
            chief_complaint=chief_complaint,
        )
        dispatches.append(AgentDispatch(
            agent_name="DiagnosticReasoningAgent",
            adapter_used="to_diagnostic_context",
            input_payload=diag_ctx,
        ))

        # 3. Treatment recommendation — if diagnosis provided
        if diagnosis:
            treat_ctx = adapters.to_treatment_context(
                personalised,
                diagnosis=diagnosis,
                specialty=specialty,
            )
            dispatches.append(AgentDispatch(
                agent_name="TreatmentRecommendationAgent",
                adapter_used="to_treatment_context",
                input_payload=treat_ctx,
            ))

        # 4. Referral agent — if pathway has referral activities
        referral_req = adapters.to_referral_request(
            personalised,
            patient_id=context.demographics.patient_id,
        )
        if referral_req["referrals"]:
            dispatches.append(AgentDispatch(
                agent_name="ReferralAgent",
                adapter_used="to_referral_request",
                input_payload=referral_req,
            ))

        # 5. Investigation planner — if pathway has investigation activities
        inv_plan = adapters.to_investigation_plan(personalised)
        if inv_plan["pathway_investigations"]:
            dispatches.append(AgentDispatch(
                agent_name="InvestigationPlannerAgent",
                adapter_used="to_investigation_plan",
                input_payload=inv_plan,
            ))

        # 6. Discharge planning — always included for care continuity
        discharge_plan = adapters.to_discharge_plan(personalised)
        dispatches.append(AgentDispatch(
            agent_name="DischargeAgent",
            adapter_used="to_discharge_plan",
            input_payload=discharge_plan,
        ))

        # 7. Continuity agent — if monitoring changes detected
        continuity_req = adapters.to_continuity_request(
            personalised,
            patient_id=context.demographics.patient_id,
        )
        if continuity_req["context"]["monitoring_changes"]:
            dispatches.append(AgentDispatch(
                agent_name="ContinuityAgent",
                adapter_used="to_continuity_request",
                input_payload=continuity_req,
            ))

        # 8. Chat context — always available
        chat_ctx = adapters.to_chat_context(personalised)
        dispatches.append(AgentDispatch(
            agent_name="ChatAssistant",
            adapter_used="to_chat_context",
            input_payload=chat_ctx,
        ))

        # 9. APEX risk — always fed back
        apex_input = adapters.to_apex_risk_input(
            personalised,
            patient_id=context.demographics.patient_id,
        )
        dispatches.append(AgentDispatch(
            agent_name="APEXRiskStratification",
            adapter_used="to_apex_risk_input",
            input_payload=apex_input,
        ))

        # 10. Build integrated plan summary
        integrated_plan = {
            "pathway_id": personalised.pathway_id,
            "pathway_title": personalised.pathway_title,
            "patient_id": personalised.patient_id,
            "personalised_at": personalised.personalised_at.isoformat(),
            "total_agents_dispatched": len([d for d in dispatches if d.dispatched]),
            "confidence": personalised.explainability.confidence.value,
            "clinician_override_recommended": personalised.explainability.clinician_override_recommended,
            "safety_warnings": personalised.explainability.safety_warnings,
            "encounter_journey_summary": personalised.encounter_journey_summary,
            "deviation_count": (
                personalised.deviation_register.total_deviations
                if personalised.deviation_register else 0
            ),
        }

        return OrchestrationResult(
            pathway=personalised,
            dispatches=dispatches,
            integrated_plan=integrated_plan,
        )

from __future__ import annotations

from typing import Any

STAGES = [
    "initiating",
    "gathering_information",
    "physical_examination",
    "explanation_and_planning",
    "closing",
]


def next_stage(current: str) -> str:
    if current not in STAGES:
        return STAGES[0]
    idx = STAGES.index(current)
    return STAGES[min(idx + 1, len(STAGES) - 1)]


def stage_prompt_context(stage: str) -> str:
    mapping = {
        "initiating": (
            "Greet patient, confirm identity, and establish the consultation agenda.\n"
            "KEY QUESTIONS: What is your name and date of birth? What brings you in today? "
            "Is there anything else you would like to discuss?\n"
            "DECISION CRITERIA TO ADVANCE: Move to gathering_information once the patient's "
            "identity is confirmed, the chief complaint is stated, and the agenda is agreed. "
            "If the patient raises multiple concerns, negotiate priority order before advancing."
        ),
        "gathering_information": (
            "Use open-to-closed questioning cone to explore the presenting complaint in depth. "
            "Systematically explore ICE: Ideas (what does the patient think is going on?), "
            "Concerns (what are they worried about?), Expectations (what are they hoping for?).\n"
            "KEY QUESTIONS: Can you tell me more about that? When did it start? "
            "What makes it better or worse? Have you had this before? "
            "What do you think might be causing it? Is there anything in particular you are worried about?\n"
            "DECISION CRITERIA TO ADVANCE: Move to physical_examination once the history is "
            "sufficiently detailed to form a working differential, ICE has been explored, "
            "and relevant red flags have been screened. Do not advance if critical history "
            "elements (onset, severity, associated symptoms) remain unclear."
        ),
        "physical_examination": (
            "Explain the focused examination you intend to perform and why. "
            "Describe expected findings relevant to the differential diagnosis.\n"
            "KEY QUESTIONS: I would like to examine your [region] - is that okay? "
            "Does it hurt when I press here? Can you take a deep breath for me?\n"
            "DECISION CRITERIA TO ADVANCE: Move to explanation_and_planning once examination "
            "findings are documented, they have been correlated with the history, and you have "
            "enough information to discuss the likely diagnosis and plan. If examination reveals "
            "unexpected findings, return to gathering_information for targeted follow-up questions."
        ),
        "explanation_and_planning": (
            "Explain the differential diagnosis and proposed management plan using shared "
            "decision-making. Check understanding at each step. Offer options where appropriate.\n"
            "KEY QUESTIONS: Based on what you have told me and the examination, I think the most "
            "likely explanation is... Does that make sense? Do you have any questions about this? "
            "There are a few options for how we can manage this - shall I go through them?\n"
            "DECISION CRITERIA TO ADVANCE: Move to closing once the diagnosis has been explained, "
            "the management plan is agreed, the patient's questions are answered, and consent "
            "for the plan has been confirmed. Do not advance if the patient appears confused "
            "or has outstanding concerns."
        ),
        "closing": (
            "Summarise the consultation, provide safety-net advice, and confirm the follow-up plan.\n"
            "KEY QUESTIONS: Let me summarise what we have discussed today - does that sound right? "
            "If [warning signs] occur, please [action]. Do you have any final questions? "
            "We will see you again in [timeframe] or sooner if needed.\n"
            "DECISION CRITERIA: This is the final stage. The consultation is complete when "
            "the summary is acknowledged, safety-net advice has been given with clear "
            "re-attendance criteria, and the patient confirms they understand the plan."
        ),
    }
    return mapping.get(stage, mapping["gathering_information"])


def progress_update(progress: dict[str, Any], patient_message: str) -> dict[str, Any]:
    out = dict(progress)
    asked = int(out.get("turns", 0)) + 1
    out["turns"] = asked
    if asked >= 2 and out.get("stage") == "initiating":
        out["stage"] = "gathering_information"
    return out

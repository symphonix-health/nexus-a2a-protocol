from __future__ import annotations

import uuid
from typing import Any

from shared.nexus_common.openai_helper import llm_chat

from .avatar_session import AvatarSession
from .frameworks.calgary_cambridge import next_stage as calgary_next_stage
from .frameworks.calgary_cambridge import progress_update as calgary_progress_update
from .frameworks.calgary_cambridge import stage_prompt_context
from .frameworks.framework_selector import select_framework
from .frameworks.socrates import initial_progress as socrates_initial
from .frameworks.socrates import update_progress as socrates_update
from .prompts.clinician_persona import build_persona_prompt


class AvatarEngine:
    def __init__(self) -> None:
        self.sessions: dict[str, AvatarSession] = {}

    def start_session(self, patient_case: dict[str, Any], persona: dict[str, Any]) -> AvatarSession:
        session_id = f"avatar-{uuid.uuid4()}"
        profile = patient_case.get("patient_profile") if isinstance(patient_case, dict) else {}
        complaint = str((profile or {}).get("chief_complaint") or "")
        urgency = str((profile or {}).get("urgency") or "")
        framework = select_framework(complaint, urgency)
        progress: dict[str, Any] = {"stage": "initiating", "turns": 0}
        if framework == "socrates":
            progress["socrates"] = socrates_initial()

        session = AvatarSession(
            session_id=session_id,
            patient_case=patient_case or {},
            persona=persona or {},
            consultation_phase="initiating",
            framework=framework,
            framework_progress=progress,
        )
        greeting = "Hello, I’m your clinician today. I’d like to understand what brought you in and how I can help."
        session.conversation_history.append({"role": "assistant", "content": greeting})
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> AvatarSession | None:
        return self.sessions.get(session_id)

    def handle_patient_message(self, session_id: str, message: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session is None:
            return {"error": "session_not_found", "session_id": session_id}

        session.conversation_history.append({"role": "user", "content": message})

        stage = str(session.framework_progress.get("stage") or "initiating")
        stage_context = stage_prompt_context(stage)

        if session.framework == "socrates":
            soc = session.framework_progress.get("socrates", socrates_initial())
            updated = socrates_update(soc, message)
            session.framework_progress["socrates"] = updated
            if not updated.get("remaining"):
                stage = "explanation_and_planning"

        system = build_persona_prompt(session.persona, session.framework, stage_context)
        user = (
            f"Patient context: {session.patient_case}. "
            f"Current stage: {stage}. "
            f"Patient says: {message}"
        )
        response_text = llm_chat(system, user)

        session.framework_progress = calgary_progress_update(session.framework_progress, message)
        new_stage = str(session.framework_progress.get("stage") or stage)
        if new_stage != stage:
            session.consultation_phase = new_stage

        if len(session.conversation_history) >= 6:
            session.consultation_phase = calgary_next_stage(session.consultation_phase)
            session.framework_progress["stage"] = session.consultation_phase

        session.conversation_history.append({"role": "assistant", "content": response_text})
        session.touch()

        return {
            "session_id": session.session_id,
            "clinician_response": response_text,
            "consultation_phase": session.consultation_phase,
            "framework": session.framework,
            "framework_progress": session.framework_progress,
            "actions_taken": session.clinical_actions,
        }

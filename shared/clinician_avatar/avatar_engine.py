from __future__ import annotations

import json
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
        greeting = (
            "Hello, I’m your clinician today. "
            "I’d like to understand what brought you in and how I can help."
        )
        session.conversation_history.append({"role": "assistant", "content": greeting})
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> AvatarSession | None:
        return self.sessions.get(session_id)

    @staticmethod
    def _looks_like_structured_payload(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        if stripped.startswith("{") or stripped.startswith("["):
            return True
        if stripped.startswith("```"):
            return True
        return "mock_response" in stripped.lower()

    @staticmethod
    def _best_next_question(patient_message: str, stage: str) -> str:
        msg = patient_message.lower()
        if "chest" in msg and "pain" in msg:
            return (
                "On a scale of 0 to 10, what is your chest pain right now, "
                "and does it spread to your arm, jaw, or back?"
            )
        if "headache" in msg or "migraine" in msg:
            return (
                "When did the headache begin, and have you noticed any vision changes, "
                "weakness, or trouble speaking?"
            )
        if "breath" in msg or "shortness" in msg:
            return (
                "Are you short of breath at rest, and are you having any chest tightness "
                "or wheezing right now?"
            )
        if "fever" in msg or "cough" in msg:
            return (
                "How long have these symptoms been present, and are you bringing up "
                "any phlegm or blood when coughing?"
            )
        if "dizzy" in msg or "faint" in msg:
            return (
                "Did the dizziness start suddenly, and did you have any loss of "
                "consciousness or palpitations?"
            )
        if "" == msg.strip():
            return "Could you tell me what symptom is bothering you the most right now?"

        if stage in {"gathering_information", "initiating"}:
            return "Could you share when this started and what has made it better or worse so far?"
        if stage == "physical_examination":
            return (
                "Are you noticing any new symptoms now, such as worsening pain, "
                "breathlessness, or confusion?"
            )
        if stage == "explanation_and_planning":
            return (
                "What concerns you most about the plan, so I can explain it clearly "
                "and address that first?"
            )
        return "Could you tell me more about how this is affecting your day-to-day activities?"

    @classmethod
    def _fallback_clinician_reply(cls, patient_message: str, stage: str) -> str:
        lead = (
            "Thank you for explaining that — I hear that this is difficult, and I’m here with you."
        )
        question = cls._best_next_question(patient_message, stage)
        return f"{lead}\n\n{question}"

    @classmethod
    def _normalize_clinician_response(
        cls,
        response_text: str,
        patient_message: str,
        stage: str,
    ) -> str:
        cleaned = (response_text or "").strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        if cls._looks_like_structured_payload(cleaned):
            # If the model returned JSON-y payload, convert to natural bedside language.
            try:
                payload = json.loads(cleaned)
                if isinstance(payload, dict):
                    maybe_text = str(
                        payload.get("clinician_response")
                        or payload.get("response")
                        or payload.get("message")
                        or ""
                    ).strip()
                    if maybe_text:
                        cleaned = maybe_text
                    else:
                        cleaned = cls._fallback_clinician_reply(patient_message, stage)
                else:
                    cleaned = cls._fallback_clinician_reply(patient_message, stage)
            except Exception:
                cleaned = cls._fallback_clinician_reply(patient_message, stage)

        if not cleaned:
            cleaned = cls._fallback_clinician_reply(patient_message, stage)

        # Ensure patient-facing structure: empathy + one focused next question.
        if "?" not in cleaned:
            cleaned = f"{cleaned}\n\n{cls._best_next_question(patient_message, stage)}"

        return cleaned.strip()

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
        response_text = self._normalize_clinician_response(response_text, message, stage)

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

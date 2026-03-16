from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Maximum turns kept per session (oldest pairs dropped to stay under cap)
MAX_CONVERSATION_TURNS = int(os.getenv("AVATAR_MAX_CONVERSATION_TURNS", "100"))
# Sessions idle longer than this many seconds are reaped automatically
SESSION_IDLE_TTL = float(os.getenv("AVATAR_SESSION_IDLE_TTL", "1800"))  # 30 min
# How often the background reaper checks for expired sessions
_REAPER_INTERVAL = float(os.getenv("AVATAR_REAPER_INTERVAL", "300"))  # 5 min

from shared.nexus_common.openai_helper import llm_chat


def _iso_to_ts(iso: str) -> float:
    """Parse an ISO-8601 string to a Unix timestamp; return 0.0 on failure."""
    try:
        from datetime import datetime, timezone

        return datetime.fromisoformat(iso).astimezone(timezone.utc).timestamp()
    except Exception:
        return 0.0


from .avatar_session import AvatarSession
from .frameworks.calgary_cambridge import next_stage as calgary_next_stage
from .frameworks.calgary_cambridge import progress_update as calgary_progress_update
from .frameworks.calgary_cambridge import stage_prompt_context
from .frameworks.framework_selector import select_framework
from .frameworks.socrates import initial_progress as socrates_initial
from .frameworks.socrates import update_progress as socrates_update
from .prompts.clinician_persona import build_persona_prompt


class AvatarEngine:
    _CONSENT_POLICY_CONFIRMATION_PHRASE = os.getenv(
        "AVATAR_CONSENT_POLICY_CONFIRMATION_PHRASE",
        "I confirm I understand the consent policy.",
    ).strip()
    _CONSENT_POLICY_CONFIRMATION_PROMPT_PREFIX = os.getenv(
        "AVATAR_CONSENT_POLICY_CONFIRMATION_PROMPT_PREFIX",
        "For compliance, please confirm by saying:",
    ).strip()

    _BASE_INTAKE_PROMPTS: list[tuple[str, str]] = [
        ("full_name", "Before we begin triage, can you confirm your full legal name?"),
        ("dob", "Thank you. What is your date of birth?"),
        ("phone", "What is the best phone number to reach you on today?"),
        (
            "location",
            "Please share your current location or nearest landmark in case urgent care is needed.",
        ),
        (
            "consent",
            "Do you consent to using your information for clinical care and urgent referral if needed?",
        ),
    ]

    @classmethod
    def _consent_policy_confirmation_phrase(cls) -> str:
        return cls._CONSENT_POLICY_CONFIRMATION_PHRASE

    @classmethod
    def _intake_prompts(cls) -> list[tuple[str, str]]:
        phrase = cls._consent_policy_confirmation_phrase()
        prefix = cls._CONSENT_POLICY_CONFIRMATION_PROMPT_PREFIX
        return [
            *cls._BASE_INTAKE_PROMPTS,
            ("consent_policy_confirm", f"{prefix} {phrase}"),
        ]

    @staticmethod
    def _normalize_policy_text(text: str) -> str:
        lowered = str(text or "").strip().lower()
        lowered = re.sub(r"[^a-z0-9\s]", "", lowered)
        return re.sub(r"\s+", " ", lowered).strip()

    @staticmethod
    def _normalize_phone(raw: str, country_hint: str = "") -> str:
        text = str(raw or "").strip()
        has_plus = text.startswith("+")
        digits = re.sub(r"\D", "", text)

        if not digits:
            return ""

        if text.startswith("00"):
            return f"+{digits[2:]}"

        if has_plus:
            return f"+{digits}"

        country = str(country_hint or "").strip().lower()
        if country in {"ke", "kenya"}:
            # Kenya local mobile forms: 07XXXXXXXX, 01XXXXXXXX, or 7XXXXXXXX.
            if digits.startswith("07") and len(digits) == 10:
                return f"+254{digits[1:]}"
            if digits.startswith("01") and len(digits) == 10:
                return f"+254{digits[1:]}"
            if digits.startswith("7") and len(digits) == 9:
                return f"+254{digits}"
            if digits.startswith("254") and len(digits) == 12:
                return f"+{digits}"

        if digits.startswith("254") and len(digits) == 12:
            return f"+{digits}"

        return digits

    @staticmethod
    def _is_valid_full_name(raw: str) -> bool:
        text = str(raw or "").strip()
        if len(text) < 3:
            return False
        parts = [p for p in re.split(r"\s+", text) if p]
        if len(parts) < 2:
            return False
        return all(bool(re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", p)) for p in parts)

    @staticmethod
    def _is_valid_dob(raw: str) -> bool:
        from datetime import datetime, timezone

        text = str(raw or "").strip()
        try:
            dt = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return False

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if dt > now:
            return False
        age_years = (now - dt).days / 365.25
        return 0.0 <= age_years <= 130.0

    @classmethod
    def _validate_intake_value(
        cls,
        key: str,
        raw_value: str,
        *,
        country_hint: str = "",
    ) -> tuple[bool, str, str]:
        text = str(raw_value or "").strip()
        if key == "full_name":
            if not cls._is_valid_full_name(text):
                return (
                    False,
                    "Please provide your full legal name as first and last name.",
                    "",
                )
            return True, "", text

        if key == "dob":
            if not cls._is_valid_dob(text):
                return (
                    False,
                    "Please provide date of birth in YYYY-MM-DD format.",
                    "",
                )
            return True, "", text

        if key == "phone":
            normalized = cls._normalize_phone(text, country_hint=country_hint)
            if len(normalized.lstrip("+")) < 10 or len(normalized.lstrip("+")) > 15:
                return (
                    False,
                    "Please provide a valid phone number with 10 to 15 digits.",
                    "",
                )
            if text.startswith("+"):
                normalized = f"+{normalized.lstrip('+')}"
            return True, "", normalized

        if key == "location":
            if len(text) < 4:
                return (
                    False,
                    "Please share your current location or nearest landmark.",
                    "",
                )
            return True, "", text

        if key == "consent":
            lowered = text.lower()
            yes_values = {"yes", "y", "i consent", "consent", "agree", "i agree"}
            no_values = {"no", "n", "decline", "i decline", "do not consent"}
            if lowered in yes_values:
                return True, "", "yes"
            if "yes" in lowered and ("consent" in lowered or "agree" in lowered):
                return True, "", "yes"
            if lowered in no_values:
                return False, "I need an explicit yes to proceed with clinical intake.", ""
            return (
                False,
                "Please answer consent with explicit yes or no.",
                "",
            )

        if key == "consent_policy_confirm":
            normalized_input = cls._normalize_policy_text(text)
            expected_phrase = cls._normalize_policy_text(
                cls._consent_policy_confirmation_phrase(),
            )
            if normalized_input == expected_phrase:
                return True, "", "confirmed"
            return (
                False,
                (f"Please confirm exactly: {cls._consent_policy_confirmation_phrase()}"),
                "",
            )

        return True, "", text

    def __init__(self) -> None:
        self.sessions: dict[str, AvatarSession] = {}
        self._reaper_task: asyncio.Task | None = None

    def start_reaper(self) -> None:
        """Schedule the background session reaper (call once from app startup)."""
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reap_loop())

    async def _reap_loop(self) -> None:
        """Periodically evict sessions that have been idle longer than SESSION_IDLE_TTL."""
        while True:
            await asyncio.sleep(_REAPER_INTERVAL)
            try:
                self._reap_idle_sessions()
            except Exception as exc:
                logger.warning(f"Avatar session reaper error: {exc}")

    def _reap_idle_sessions(self) -> int:
        now = time.time()
        expired = [
            sid
            for sid, s in self.sessions.items()
            # updated_at is an ISO string; fall back to created_at if needed
            if (now - _iso_to_ts(s.updated_at or s.created_at)) > SESSION_IDLE_TTL
        ]
        for sid in expired:
            self.sessions.pop(sid, None)
        if expired:
            logger.info(f"Reaped {len(expired)} idle avatar session(s)")
        return len(expired)

    @staticmethod
    def _sanitize_llm_config(llm_config: dict[str, Any] | None) -> dict[str, Any]:
        cfg = llm_config if isinstance(llm_config, dict) else {}
        out: dict[str, Any] = {}

        nondeterministic = bool(cfg.get("nondeterministic"))
        out["nondeterministic"] = nondeterministic

        temp_val = cfg.get("temperature")
        if temp_val is not None:
            try:
                out["temperature"] = max(0.0, min(1.5, float(temp_val)))
            except Exception:
                pass

        top_p_val = cfg.get("top_p")
        if top_p_val is not None:
            try:
                out["top_p"] = max(0.1, min(1.0, float(top_p_val)))
            except Exception:
                pass

        if out.get("nondeterministic") and "temperature" not in out:
            out["temperature"] = 0.7
        return out

    def start_session(
        self,
        patient_case: dict[str, Any],
        persona: dict[str, Any],
        llm_config: dict[str, Any] | None = None,
    ) -> AvatarSession:
        intake_prompts = self._intake_prompts()
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
            llm_config=self._sanitize_llm_config(llm_config),
        )
        registration_first = bool((patient_case or {}).get("registration_first_mode"))
        session.framework_progress["registration_first_mode"] = registration_first
        session.framework_progress["intake"] = {
            "required_fields": [k for k, _ in intake_prompts],
            "current_index": 0,
            "collected": {},
            "completed": not registration_first,
            "country_hint": str(
                (patient_case or {}).get("country") or (profile or {}).get("country") or ""
            ).strip(),
            "consent_policy_phrase": self._consent_policy_confirmation_phrase(),
        }

        if registration_first:
            greeting = (
                "Hello, I’m your clinician. "
                "I’ll complete a quick intake first so we can triage you safely. "
                f"{intake_prompts[0][1]}"
            )
        else:
            greeting = (
                "Hello, I’m your clinician today. "
                "I’d like to understand what brought you in and how I can help."
            )
        session.conversation_history.append({"role": "assistant", "content": greeting})
        self.sessions[session_id] = session
        return session

    def _handle_registration_first_turn(self, session: AvatarSession, message: str) -> str:
        intake_prompts = self._intake_prompts()
        intake = session.framework_progress.get("intake")
        if not isinstance(intake, dict):
            return "Thanks. Could you share your main symptom right now?"

        current_index = int(intake.get("current_index") or 0)
        collected = intake.get("collected")
        if not isinstance(collected, dict):
            collected = {}

        if current_index < len(intake_prompts):
            key, question = intake_prompts[current_index]
            valid, error_msg, normalized_value = self._validate_intake_value(
                key,
                message,
                country_hint=str(intake.get("country_hint") or ""),
            )
            if not valid:
                intake["last_error"] = {
                    "field": key,
                    "message": error_msg,
                }
                intake["collected"] = collected
                return f"{error_msg} {question}"
            collected[key] = normalized_value
            intake["last_error"] = None
            intake["collected"] = collected

        next_index = current_index + 1
        intake["current_index"] = next_index

        if next_index < len(intake_prompts):
            next_question = intake_prompts[next_index][1]
            return f"Thank you. {next_question}"

        intake["completed"] = True
        session.consultation_phase = "gathering_information"
        session.framework_progress["stage"] = "gathering_information"
        return (
            "Thank you — intake and consent are complete. "
            "Now let’s move to clinical triage. "
            "Please describe your main symptom and when it started."
        )

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

    @staticmethod
    def _trim_history(history: list[dict], max_turns: int) -> None:
        """Drop oldest user+assistant pairs in-place when history exceeds max_turns."""
        while len(history) > max_turns:
            # Always remove two entries (user + assistant) to preserve pairing
            del history[0]
            if history:
                del history[0]

    def handle_patient_message(self, session_id: str, message: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session is None:
            return {"error": "session_not_found", "session_id": session_id}

        session.conversation_history.append({"role": "user", "content": message})
        self._trim_history(session.conversation_history, MAX_CONVERSATION_TURNS)

        stage = str(session.framework_progress.get("stage") or "initiating")
        stage_context = stage_prompt_context(stage)

        intake = session.framework_progress.get("intake")
        intake_completed = bool(intake.get("completed")) if isinstance(intake, dict) else True
        registration_first = bool(session.framework_progress.get("registration_first_mode"))

        if registration_first and not intake_completed:
            response_text = self._handle_registration_first_turn(session, message)
            session.conversation_history.append({"role": "assistant", "content": response_text})
            session.touch()
            return {
                "session_id": session.session_id,
                "clinician_response": response_text,
                "consultation_phase": session.consultation_phase,
                "framework": session.framework,
                "framework_progress": session.framework_progress,
                "llm_config": session.llm_config,
                "actions_taken": session.clinical_actions,
            }

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
        llm_cfg = session.llm_config if isinstance(session.llm_config, dict) else {}
        response_text = llm_chat(
            system,
            user,
            temperature=llm_cfg.get("temperature"),
            top_p=llm_cfg.get("top_p"),
        )
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
            "llm_config": session.llm_config,
            "actions_taken": session.clinical_actions,
        }

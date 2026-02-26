"""Unit tests for the clinician-avatar runtime and scenario integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ── Avatar Engine ────────────────────────────────────────────────────────────


class TestAvatarEngine:
    """Tests for shared/clinician_avatar/avatar_engine.py."""

    def _make_engine(self):
        from shared.clinician_avatar.avatar_engine import AvatarEngine

        return AvatarEngine()

    def _case(self, complaint="Chest pain", age=54, gender="male", urgency="high"):
        return {"patient_profile": {"chief_complaint": complaint, "age": age, "gender": gender, "urgency": urgency}}

    def _persona(self, name="Dr. Alex", role="clinician", specialty="cardiology"):
        return {"name": name, "role": role, "specialty": specialty}

    def test_start_session_creates_session(self):
        engine = self._make_engine()
        result = engine.start_session(
            patient_case=self._case(),
            persona=self._persona(),
        )
        assert result.session_id.startswith("avatar-")
        assert result.framework in ("calgary_cambridge", "socrates", "abcde")
        assert len(result.conversation_history) >= 1  # greeting

    def test_start_session_selects_calgary_cambridge_by_default(self):
        engine = self._make_engine()
        result = engine.start_session(
            patient_case=self._case(complaint="Fatigue", urgency="medium"),
            persona=self._persona(),
        )
        assert result.framework == "calgary_cambridge"

    def test_start_session_selects_socrates_for_pain(self):
        engine = self._make_engine()
        result = engine.start_session(
            patient_case=self._case(complaint="Severe chest pain", urgency="high"),
            persona=self._persona(),
        )
        assert result.framework == "socrates"

    def test_start_session_selects_abcde_for_critical(self):
        engine = self._make_engine()
        result = engine.start_session(
            patient_case=self._case(complaint="Unresponsive patient", urgency="critical"),
            persona=self._persona(),
        )
        assert result.framework == "abcde"

    def test_handle_patient_message_returns_response(self):
        engine = self._make_engine()
        session = engine.start_session(
            patient_case=self._case(complaint="Headache", urgency="medium"),
            persona=self._persona(),
        )
        sid = session.session_id
        with patch(
            "shared.clinician_avatar.avatar_engine.llm_chat",
            return_value="I understand you have a throbbing headache. Can you describe where exactly it is?",
        ):
            result = engine.handle_patient_message(sid, "I have a throbbing headache on the left side.")
        assert "clinician_response" in result
        assert "consultation_phase" in result
        assert len(result["clinician_response"]) > 5

    def test_handle_patient_message_invalid_session(self):
        engine = self._make_engine()
        result = engine.handle_patient_message("nonexistent-session", "Hello")
        assert result.get("error") == "session_not_found"

    def test_get_session_returns_session_data(self):
        engine = self._make_engine()
        session = engine.start_session(
            patient_case=self._case(complaint="Cough", urgency="low"),
            persona=self._persona(),
        )
        sid = session.session_id
        data = engine.get_session(sid)
        assert data is not None
        assert data.session_id == sid

    def test_multiple_sessions_are_independent(self):
        engine = self._make_engine()
        s1 = engine.start_session(
            patient_case=self._case(complaint="Headache"),
            persona=self._persona(),
        )
        s2 = engine.start_session(
            patient_case=self._case(complaint="Knee pain"),
            persona=self._persona(),
        )
        assert s1.session_id != s2.session_id


# ── Framework Selector ───────────────────────────────────────────────────────


class TestFrameworkSelector:
    """Tests for shared/clinician_avatar/frameworks/framework_selector.py."""

    def test_default_is_calgary_cambridge(self):
        from shared.clinician_avatar.frameworks.framework_selector import \
            select_framework

        assert select_framework("fatigue", "medium") == "calgary_cambridge"

    def test_pain_selects_socrates(self):
        from shared.clinician_avatar.frameworks.framework_selector import \
            select_framework

        assert select_framework("severe chest pain", "high") == "socrates"

    def test_critical_selects_abcde(self):
        from shared.clinician_avatar.frameworks.framework_selector import \
            select_framework

        assert select_framework("collapse", "critical") == "abcde"

    def test_emergency_selects_abcde(self):
        from shared.clinician_avatar.frameworks.framework_selector import \
            select_framework

        assert select_framework("unresponsive", "emergency") == "abcde"


# ── Calgary-Cambridge Framework ──────────────────────────────────────────────


class TestCalgaryCambridge:
    """Tests for shared/clinician_avatar/frameworks/calgary_cambridge.py."""

    def test_stages_order(self):
        from shared.clinician_avatar.frameworks.calgary_cambridge import STAGES

        assert STAGES[0] == "initiating"
        assert STAGES[-1] == "closing"
        assert len(STAGES) >= 4

    def test_next_stage(self):
        from shared.clinician_avatar.frameworks.calgary_cambridge import \
            next_stage

        assert next_stage("initiating") == "gathering_information"

    def test_next_stage_at_end(self):
        from shared.clinician_avatar.frameworks.calgary_cambridge import \
            next_stage

        last_stage = "closing"
        assert next_stage(last_stage) == last_stage  # stays at end

    def test_stage_prompt_context(self):
        from shared.clinician_avatar.frameworks.calgary_cambridge import \
            stage_prompt_context

        ctx = stage_prompt_context("gathering_information")
        assert isinstance(ctx, str)
        assert len(ctx) > 10


# ── SOCRATES Framework ───────────────────────────────────────────────────────


class TestSocrates:
    """Tests for shared/clinician_avatar/frameworks/socrates.py."""

    def test_socrates_keys_complete(self):
        from shared.clinician_avatar.frameworks.socrates import SOCRATES_KEYS

        expected = {"site", "onset", "character", "radiation", "associations", "time_course", "exacerbating_relieving", "severity"}
        assert set(SOCRATES_KEYS) == expected

    def test_update_progress(self):
        from shared.clinician_avatar.frameworks.socrates import (
            initial_progress, update_progress)

        progress = initial_progress()
        updated = update_progress(progress, "I have pain in my left arm that started yesterday")
        assert isinstance(updated, dict)
        assert "completed" in updated
        assert "remaining" in updated


# ── ABCDE Framework ─────────────────────────────────────────────────────────


class TestAbcde:
    """Tests for shared/clinician_avatar/frameworks/abcde.py."""

    def test_abcde_steps(self):
        from shared.clinician_avatar.frameworks.abcde import ABCDE_STEPS

        assert ABCDE_STEPS == ["airway", "breathing", "circulation", "disability", "exposure"]


# ── Clinician Persona ────────────────────────────────────────────────────────


class TestClinicianPersona:
    """Tests for shared/clinician_avatar/prompts/clinician_persona.py."""

    def test_build_persona_prompt(self):
        from shared.clinician_avatar.frameworks.calgary_cambridge import \
            stage_prompt_context
        from shared.clinician_avatar.prompts.clinician_persona import \
            build_persona_prompt

        prompt = build_persona_prompt(
            persona={"name": "Dr. Alex", "role": "cardiologist", "specialty": "cardiology"},
            framework="calgary_cambridge",
            stage_context=stage_prompt_context("initiating"),
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 50
        assert "Alex" in prompt


# ── Avatar Protocol Helpers ──────────────────────────────────────────────────


class TestAvatarProtocol:
    """Tests for shared/clinician_avatar/avatar_protocol.py."""

    def test_imports(self):
        from shared.clinician_avatar import avatar_protocol  # noqa: F401


# ── Avatar Session Dataclass ─────────────────────────────────────────────────


class TestAvatarSession:
    """Tests for shared/clinician_avatar/avatar_session.py."""

    def test_session_creation(self):
        from shared.clinician_avatar.avatar_session import AvatarSession

        s = AvatarSession(
            session_id="test-123",
            patient_case={"chief_complaint": "Test"},
            persona={"name": "Dr. Test"},
            framework="calgary_cambridge",
        )
        assert s.session_id == "test-123"
        assert s.consultation_phase == "initiating"
        assert s.conversation_history == []


# ── Scenario Catalog Integrity ───────────────────────────────────────────────


class TestScenarioCatalog:
    """Verify all scenarios have medical_history and avatar scenario is wired."""

    def _load_scenarios(self):
        import os
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        os.chdir(os.path.join(os.path.dirname(__file__), "..", "tools"))
        from additional_scenarios import ADDITIONAL_SCENARIOS
        from helixcare_scenarios import SCENARIOS

        return SCENARIOS, ADDITIONAL_SCENARIOS

    def test_all_canonical_have_medical_history(self):
        canonical, _ = self._load_scenarios()
        for s in canonical:
            assert s.medical_history, f"{s.name} missing medical_history"

    def test_all_additional_have_medical_history(self):
        _, additional = self._load_scenarios()
        for s in additional:
            assert s.medical_history, f"{s.name} missing medical_history"

    def test_avatar_scenario_exists(self):
        _, additional = self._load_scenarios()
        avatar_scenarios = [s for s in additional if s.name == "clinician_avatar_consultation"]
        assert len(avatar_scenarios) == 1

    def test_avatar_scenario_has_avatar_steps(self):
        _, additional = self._load_scenarios()
        avatar_sc = [s for s in additional if s.name == "clinician_avatar_consultation"][0]
        avatar_steps = [step for step in avatar_sc.journey_steps if step["agent"] == "clinician_avatar"]
        assert len(avatar_steps) >= 2  # at least start_session + patient_message

    def test_total_scenario_count(self):
        canonical, additional = self._load_scenarios()
        assert len(canonical) == 10
        assert len(additional) >= 15

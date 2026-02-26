"""Unit tests for shared/nexus_common/identity/persona_registry.py.

All tests run without a running agent — they exercise the registry directly
against config/personas.json. Tests are deterministic and repeatable.
"""

from __future__ import annotations

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def registry():
    from shared.nexus_common.identity.persona_registry import get_persona_registry
    return get_persona_registry()


# ── Registry Load ─────────────────────────────────────────────────────────────

class TestPersonaRegistryLoad:
    """Verify the registry loads completely from config/personas.json."""

    def test_loads_68_personas(self, registry):
        assert len(registry.all()) == 68

    def test_all_personas_have_persona_id(self, registry):
        for p in registry.all():
            assert p.persona_id, f"Empty persona_id: {p}"

    def test_all_personas_have_name(self, registry):
        for p in registry.all():
            assert p.name, f"Empty name for {p.persona_id}"

    def test_no_duplicate_persona_ids(self, registry):
        ids = [p.persona_id for p in registry.all()]
        assert len(ids) == len(set(ids)), "Duplicate persona_ids found"

    def test_p001_is_consultant_physician(self, registry):
        p = registry.require("P001")
        assert "Consultant" in p.name or "Physician" in p.name

    def test_p068_is_last_persona(self, registry):
        p = registry.get("P068")
        assert p is not None
        assert p.persona_id == "P068"

    def test_rbac_roles_loaded(self, registry):
        roles = registry.rbac_role("clinician_service")
        assert roles, "clinician_service RBAC role not found"
        assert "default_scopes" in roles

    def test_scopes_for_role_returns_list(self, registry):
        scopes = registry.scopes_for_role("clinician_service")
        assert isinstance(scopes, list)
        assert len(scopes) > 0

    def test_scopes_for_unknown_role_returns_empty(self, registry):
        scopes = registry.scopes_for_role("nonexistent_role")
        assert scopes == []


# ── Persona Lookup ────────────────────────────────────────────────────────────

class TestPersonaLookup:
    """Test get / require / filter APIs."""

    def test_get_known_id_returns_persona(self, registry):
        p = registry.get("P004")
        assert p is not None
        assert p.name == "Triage Nurse"

    def test_get_unknown_id_returns_none(self, registry):
        p = registry.get("P999")
        assert p is None

    def test_require_known_id_returns_persona(self, registry):
        p = registry.require("P007")
        assert p.persona_id == "P007"

    def test_require_unknown_id_raises_key_error(self, registry):
        with pytest.raises(KeyError, match="P999"):
            registry.require("P999")

    def test_filter_by_country_uk(self, registry):
        results = registry.filter(country="uk")
        assert len(results) > 0
        for p in results:
            assert "uk" in p.country_context.lower()

    def test_filter_by_country_usa(self, registry):
        results = registry.filter(country="usa")
        assert len(results) > 0

    def test_filter_by_country_kenya(self, registry):
        results = registry.filter(country="kenya")
        assert len(results) > 0

    def test_filter_by_domain_clinical(self, registry):
        results = registry.filter(domain="clinical")
        assert len(results) > 15

    def test_filter_by_domain_pharmacy(self, registry):
        results = registry.filter(domain="pharmacy")
        assert len(results) >= 3  # UK, USA, Kenya pharmacists

    def test_filter_by_domain_imaging(self, registry):
        results = registry.filter(domain="imaging")
        assert len(results) >= 3  # UK, USA, Kenya

    def test_filter_by_bulletrain_role(self, registry):
        results = registry.filter(bulletrain_role="clinician_service")
        assert len(results) >= 40

    def test_filter_by_bulletrain_role_auditor(self, registry):
        results = registry.filter(bulletrain_role="auditor")
        assert len(results) >= 5

    def test_filter_by_rbac_level_high(self, registry):
        results = registry.filter(rbac_level="High")
        assert len(results) >= 20

    def test_filter_by_rbac_level_restricted(self, registry):
        results = registry.filter(rbac_level="Restricted")
        assert len(results) >= 5

    def test_filter_combined_country_and_domain(self, registry):
        results = registry.filter(country="uk", domain="clinical")
        assert len(results) > 0
        for p in results:
            assert "uk" in p.country_context.lower()
            assert "clinical" in p.domain.lower()

    def test_filter_no_match_returns_empty(self, registry):
        results = registry.filter(country="antarctica")
        assert results == []


# ── Persona Properties ────────────────────────────────────────────────────────

class TestPersonaProperties:
    """Test Persona dataclass computed properties."""

    def test_bulletrain_role_extracted_from_iam(self, registry):
        p = registry.require("P001")  # Consultant Physician
        assert p.bulletrain_role == "clinician_service"

    def test_rbac_level_extracted_from_iam(self, registry):
        p = registry.require("P001")
        assert p.rbac_level == "High"

    def test_data_sensitivity_extracted_from_iam(self, registry):
        p = registry.require("P001")
        assert p.data_sensitivity in ("High", "Medium", "Low")

    def test_scopes_are_list(self, registry):
        p = registry.require("P001")
        assert isinstance(p.scopes, list)
        assert len(p.scopes) > 0

    def test_smart_fhir_scopes_are_list(self, registry):
        p = registry.require("P001")
        assert isinstance(p.smart_fhir_scopes, list)

    def test_restricted_persona_has_lower_sensitivity(self, registry):
        p = registry.require("P011")  # Receptionist — Restricted
        assert p.rbac_level == "Restricted"
        assert p.data_sensitivity in ("Low", "Medium")

    def test_communication_style_clinical(self, registry):
        p = registry.require("P001")
        style = p.communication_style
        assert isinstance(style, str)
        assert len(style) > 5

    def test_communication_style_pharmacy(self, registry):
        p = registry.require("P007")  # Pharmacist
        style = p.communication_style
        assert "safety" in style.lower() or "thorough" in style.lower()

    def test_communication_style_auditor(self, registry):
        p = registry.require("P013")  # Caldicott Guardian
        style = p.communication_style
        assert isinstance(style, str)


# ── to_avatar_dict ────────────────────────────────────────────────────────────

class TestToAvatarDict:
    """Verify the avatar-compatible dict output."""

    def test_to_avatar_dict_has_required_keys(self, registry):
        d = registry.require("P001").to_avatar_dict()
        for key in ("persona_id", "name", "role", "style", "specialty", "country_context"):
            assert key in d, f"Missing key '{key}' in avatar dict"

    def test_to_avatar_dict_persona_id_matches(self, registry):
        p = registry.require("P004")
        d = p.to_avatar_dict()
        assert d["persona_id"] == "P004"
        assert d["name"] == "Triage Nurse"

    def test_to_avatar_dict_country_preserved(self, registry):
        p = registry.require("P014")  # USA Attending Physician
        d = p.to_avatar_dict()
        assert d["country_context"] == "USA"

    def test_to_avatar_dict_compatible_with_avatar_engine(self, registry):
        """to_avatar_dict output can be passed directly to AvatarEngine.start_session."""
        from shared.clinician_avatar.avatar_engine import AvatarEngine
        p = registry.require("P001")
        engine = AvatarEngine()
        session = engine.start_session(
            patient_case={"patient_profile": {"chief_complaint": "Test", "age": 50,
                                              "gender": "male", "urgency": "medium"}},
            persona=p.to_avatar_dict(),
        )
        assert session.session_id.startswith("avatar-")
        assert session.persona["persona_id"] == "P001"


# ── to_jwt_claims_dict ────────────────────────────────────────────────────────

class TestToJwtClaimsDict:
    """Verify JWT claims output for persona-scoped tokens."""

    def test_jwt_claims_has_required_fields(self, registry):
        claims = registry.require("P001").to_jwt_claims_dict()
        for key in ("persona_id", "persona_name", "bulletrain_role", "rbac_level",
                    "scopes", "purpose_of_use", "data_sensitivity"):
            assert key in claims, f"Missing '{key}' in JWT claims"

    def test_jwt_claims_scopes_is_list(self, registry):
        claims = registry.require("P007").to_jwt_claims_dict()
        assert isinstance(claims["scopes"], list)

    def test_jwt_claims_purpose_of_use_is_string(self, registry):
        claims = registry.require("P001").to_jwt_claims_dict()
        assert isinstance(claims["purpose_of_use"], str)
        assert len(claims["purpose_of_use"]) > 0


# ── Avatar Persona Selection ──────────────────────────────────────────────────

class TestAvatarPersonaSelection:
    """Test avatar_persona_for_scenario() helper."""

    def test_uk_clinical_returns_uk_persona(self, registry):
        p = registry.avatar_persona_for_scenario(scenario_domain="clinical", country="uk")
        assert "uk" in p.country_context.lower()
        assert p.rbac_level == "High"

    def test_usa_clinical_returns_usa_persona(self, registry):
        p = registry.avatar_persona_for_scenario(scenario_domain="clinical", country="usa")
        assert "usa" in p.country_context.lower()

    def test_telehealth_setting_prefers_telehealth_persona(self, registry):
        p = registry.avatar_persona_for_scenario(
            scenario_domain="clinical", country="uk", care_setting="telehealth"
        )
        assert "telehealth" in p.care_setting.lower() or "uk" in p.country_context.lower()

    def test_unknown_domain_falls_back_to_clinical(self, registry):
        p = registry.avatar_persona_for_scenario(
            scenario_domain="nonexistent_domain", country="uk"
        )
        assert p is not None

    def test_unknown_country_falls_back_gracefully(self, registry):
        p = registry.avatar_persona_for_scenario(
            scenario_domain="clinical", country="antarctica"
        )
        assert p is not None  # Falls back to any clinical persona


# ── Specific Known Personas ───────────────────────────────────────────────────

class TestKnownPersonas:
    """Spot-check specific well-known personas for correct field values."""

    @pytest.mark.parametrize("persona_id,expected_name,expected_country,expected_role", [
        ("P001", "Consultant Physician", "UK", "clinician_service"),
        ("P002", "GP (General Practitioner)", "UK", "clinician_service"),
        ("P004", "Triage Nurse", "UK", "clinician_service"),
        ("P005", "Radiologist", "UK", "clinician_service"),
        ("P007", "Pharmacist", "UK", "clinician_service"),
        ("P013", "Caldicott Guardian / Privacy Officer", "UK", "auditor"),
        ("P014", "Attending Physician", "USA", "clinician_service"),
        ("P026", "Medical Officer", "Kenya", "clinician_service"),
        ("P045", "Bed Manager", "UK", "patient_service"),
        ("P056", "Integration Engine Operator", "Generic", "connector"),
        ("P065", "Psychiatrist", "UK/USA/Kenya", "clinician_service"),
    ])
    def test_known_persona(self, registry, persona_id, expected_name, expected_country, expected_role):
        p = registry.require(persona_id)
        assert p.name == expected_name, f"{persona_id}: expected name '{expected_name}', got '{p.name}'"
        assert expected_country in p.country_context, (
            f"{persona_id}: expected country '{expected_country}', got '{p.country_context}'"
        )
        assert p.bulletrain_role == expected_role, (
            f"{persona_id}: expected role '{expected_role}', got '{p.bulletrain_role}'"
        )

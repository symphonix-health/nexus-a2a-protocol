"""Unit tests for shared/nexus_common/identity/agent_identity.py.

All tests are deterministic and run without a live agent.
They exercise the AgentIdentity and AgentIdentityRegistry against
config/agent_personas.json.
"""

from __future__ import annotations

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def agent_registry():
    from shared.nexus_common.identity.agent_identity import get_agent_registry
    return get_agent_registry()


@pytest.fixture(scope="module")
def avatar_identity():
    from shared.nexus_common.identity import get_agent_identity
    return get_agent_identity("clinician_avatar_agent")


@pytest.fixture(scope="module")
def discharge_identity():
    from shared.nexus_common.identity import get_agent_identity
    return get_agent_identity("discharge_agent")


@pytest.fixture(scope="module")
def consent_identity():
    from shared.nexus_common.identity import get_agent_identity
    return get_agent_identity("consent_analyser")


# ── Registry Load ─────────────────────────────────────────────────────────────

class TestAgentRegistryLoad:
    """Verify all expected agents are in the registry."""

    EXPECTED_AGENTS = [
        "triage_agent", "diagnosis_agent", "imaging_agent", "pharmacy_agent",
        "bed_manager_agent", "discharge_agent", "followup_scheduler", "care_coordinator",
        "clinician_avatar_agent", "consent_analyser", "hospital_reporter",
        "central_surveillance", "insurer_agent", "provider_agent",
        "primary_care_agent", "specialty_care_agent", "telehealth_agent",
        "home_visit_agent", "ccm_agent", "transcriber_agent", "summariser_agent",
        "ehr_writer_agent", "osint_agent", "openhie_mediator",
    ]

    def test_all_expected_agents_present(self, agent_registry):
        for agent_id in self.EXPECTED_AGENTS:
            a = agent_registry.get(agent_id)
            assert a is not None, f"Agent '{agent_id}' not found in registry"

    def test_unknown_agent_get_returns_none(self, agent_registry):
        assert agent_registry.get("nonexistent_agent") is None

    def test_unknown_agent_require_raises_key_error(self, agent_registry):
        with pytest.raises(KeyError, match="nonexistent_agent"):
            agent_registry.require("nonexistent_agent")

    def test_all_agents_have_port(self, agent_registry):
        for a in agent_registry.all():
            assert a.port > 0, f"{a.agent_id} has invalid port {a.port}"

    def test_all_agents_have_primary_persona_id(self, agent_registry):
        for a in agent_registry.all():
            assert a.primary_persona_id, f"{a.agent_id} missing primary_persona_id"


# ── Persona Resolution ────────────────────────────────────────────────────────

class TestPersonaResolution:
    """Test primary and country-based persona selection."""

    def test_avatar_primary_persona_is_consultant_physician(self, avatar_identity):
        p = avatar_identity.primary_persona
        assert "Consultant" in p.name or "Physician" in p.name

    def test_avatar_uk_persona_is_primary(self, avatar_identity):
        # UK has no override → returns primary
        p = avatar_identity.persona_for_country("uk")
        assert p.persona_id == avatar_identity.primary_persona_id

    def test_avatar_usa_persona_returns_attending_physician(self, avatar_identity):
        p = avatar_identity.persona_for_country("usa")
        assert "Attending" in p.name or "Physician" in p.name

    def test_avatar_kenya_persona_returns_medical_officer(self, avatar_identity):
        p = avatar_identity.persona_for_country("kenya")
        assert "Medical Officer" in p.name or "Medical" in p.name

    def test_avatar_unknown_country_falls_back_to_primary(self, avatar_identity):
        p = avatar_identity.persona_for_country("atlantis")
        assert p.persona_id == avatar_identity.primary_persona_id

    def test_avatar_telehealth_setting_prefers_telehealth_persona(self, avatar_identity):
        p = avatar_identity.persona_for_scenario(country="uk", care_setting="uk_telehealth")
        assert p is not None

    def test_triage_uk_persona_is_triage_nurse(self, agent_registry):
        triage = agent_registry.require("triage_agent")
        p = triage.primary_persona
        assert "Triage" in p.name or "Nurse" in p.name

    def test_triage_kenya_persona_is_nursing_officer(self, agent_registry):
        triage = agent_registry.require("triage_agent")
        p = triage.persona_for_country("kenya")
        assert p is not None

    def test_imaging_usa_persona_is_radiology_technologist(self, agent_registry):
        imaging = agent_registry.require("imaging_agent")
        p = imaging.persona_for_country("usa")
        assert "Radiol" in p.name or "Technolog" in p.name

    def test_consent_analyser_primary_persona_is_caldicott(self, consent_identity):
        p = consent_identity.primary_persona
        assert "Caldicott" in p.name or "Privacy" in p.name


# ── IAM Groups ────────────────────────────────────────────────────────────────

class TestIAMGroups:
    """Verify IAM group membership is correctly defined."""

    def test_avatar_in_clinical_high_group(self, avatar_identity):
        assert "nexus-clinical-high" in avatar_identity.iam_groups

    def test_consent_in_governance_group(self, consent_identity):
        assert "nexus-governance" in consent_identity.iam_groups

    def test_agents_in_group_clinical_high(self, agent_registry):
        members = agent_registry.agents_in_group("nexus-clinical-high")
        agent_ids = {a.agent_id for a in members}
        assert "clinician_avatar_agent" in agent_ids
        assert "diagnosis_agent" in agent_ids
        assert "triage_agent" in agent_ids
        assert "imaging_agent" in agent_ids

    def test_agents_in_group_governance(self, agent_registry):
        members = agent_registry.agents_in_group("nexus-governance")
        agent_ids = {a.agent_id for a in members}
        assert "consent_analyser" in agent_ids
        assert "hospital_reporter" in agent_ids

    def test_agents_in_group_connector(self, agent_registry):
        members = agent_registry.agents_in_group("nexus-connector")
        agent_ids = {a.agent_id for a in members}
        assert "insurer_agent" in agent_ids

    def test_iam_group_config_loaded(self, agent_registry):
        config = agent_registry.iam_group_config("nexus-clinical-high")
        assert "description" in config

    def test_unknown_group_config_returns_empty(self, agent_registry):
        config = agent_registry.iam_group_config("nonexistent_group")
        assert config == {}


# ── Communication Permissions ─────────────────────────────────────────────────

class TestCommunicationPermissions:
    """Verify email/SMS permissions are correctly defined."""

    def test_avatar_cannot_send_email(self, avatar_identity):
        assert avatar_identity.can_send_email is False

    def test_avatar_cannot_send_sms(self, avatar_identity):
        assert avatar_identity.can_send_sms is False

    def test_discharge_can_send_email(self, discharge_identity):
        assert discharge_identity.can_send_email is True

    def test_discharge_can_send_sms(self, discharge_identity):
        assert discharge_identity.can_send_sms is True

    def test_consent_cannot_send_email(self, consent_identity):
        assert consent_identity.can_send_email is False

    def test_consent_cannot_send_sms(self, consent_identity):
        assert consent_identity.can_send_sms is False

    def test_followup_can_send_and_receive_sms(self, agent_registry):
        followup = agent_registry.require("followup_scheduler")
        assert followup.can_send_sms is True
        assert followup.can_receive_sms is True

    def test_pharmacy_can_send_sms(self, agent_registry):
        pharmacy = agent_registry.require("pharmacy_agent")
        assert pharmacy.can_send_sms is True

    def test_diagnosis_can_send_email(self, agent_registry):
        diagnosis = agent_registry.require("diagnosis_agent")
        assert diagnosis.can_send_email is True
        assert diagnosis.can_send_sms is False

    def test_all_agents_have_defined_comm_permissions(self, agent_registry):
        for a in agent_registry.all():
            # These must be bool, not None
            assert isinstance(a.can_send_email, bool), f"{a.agent_id} send_email not bool"
            assert isinstance(a.can_send_sms, bool), f"{a.agent_id} send_sms not bool"
            assert isinstance(a.can_receive_email, bool), f"{a.agent_id} receive_email not bool"
            assert isinstance(a.can_receive_sms, bool), f"{a.agent_id} receive_sms not bool"


# ── Graph API / ACS Payload Builders ─────────────────────────────────────────

class TestPayloadBuilders:
    """Test Graph API email and ACS SMS payload generation."""

    def test_graph_mail_payload_structure(self, discharge_identity):
        payload = discharge_identity.graph_api_send_mail_payload(
            to_address="gp@test.nhs.uk",
            subject="Discharge Summary — Test Patient",
            body_html="<p>Please find attached the discharge summary.</p>",
        )
        assert "message" in payload
        msg = payload["message"]
        assert msg["subject"] == "Discharge Summary — Test Patient"
        assert msg["body"]["contentType"] == "HTML"
        assert any(
            r["emailAddress"]["address"] == "gp@test.nhs.uk"
            for r in msg["toRecipients"]
        )
        assert "from" in msg
        assert "saveToSentItems" in payload

    def test_graph_mail_from_contains_agent_name(self, discharge_identity):
        payload = discharge_identity.graph_api_send_mail_payload(
            "test@example.com", "Test", "<p>Test</p>"
        )
        from_name = payload["message"]["from"]["emailAddress"]["name"]
        assert "NEXUS" in from_name

    def test_graph_mail_raises_permission_error_for_no_email_agent(self, avatar_identity):
        with pytest.raises(PermissionError, match="send_email"):
            avatar_identity.graph_api_send_mail_payload(
                "test@example.com", "Subject", "<p>Body</p>"
            )

    def test_acs_sms_payload_structure(self, agent_registry):
        followup = agent_registry.require("followup_scheduler")
        payload = followup.graph_api_send_sms_payload(
            to_number="+447700900123",
            message="Your appointment is confirmed for tomorrow at 2pm.",
        )
        assert payload["to"] == ["+447700900123"]
        assert "appointment" in payload["message"].lower()
        assert payload["smsSendOptions"]["enableDeliveryReport"] is True

    def test_acs_sms_raises_permission_error_for_no_sms_agent(self, avatar_identity):
        with pytest.raises(PermissionError, match="send_sms"):
            avatar_identity.graph_api_send_sms_payload(
                "+447700900123", "Hello patient"
            )

    def test_acs_sms_raises_permission_error_for_diagnosis_agent(self, agent_registry):
        diagnosis = agent_registry.require("diagnosis_agent")
        with pytest.raises(PermissionError):
            diagnosis.graph_api_send_sms_payload("+447700900123", "Test")


# ── Delegation Graph ──────────────────────────────────────────────────────────

class TestDelegationGraph:
    """Verify the delegation graph is internally consistent."""

    def test_care_coordinator_can_delegate_to_triage(self, agent_registry):
        cc = agent_registry.require("care_coordinator")
        assert "triage_agent" in cc.can_delegate_to

    def test_avatar_can_delegate_to_care_coordinator(self, avatar_identity):
        assert "care_coordinator" in avatar_identity.can_delegate_to

    def test_osint_cannot_delegate_to_clinical_agents(self, agent_registry):
        osint = agent_registry.require("osint_agent")
        clinical_agents = {"triage_agent", "diagnosis_agent", "imaging_agent",
                           "pharmacy_agent", "discharge_agent"}
        overlap = clinical_agents.intersection(set(osint.can_delegate_to))
        assert not overlap, f"OSINT should not delegate to clinical agents: {overlap}"

    def test_consent_cannot_delegate_to_clinical_agents(self, consent_identity):
        assert consent_identity.can_delegate_to == []

    def test_no_self_delegation(self, agent_registry):
        for a in agent_registry.all():
            assert a.agent_id not in a.can_delegate_to, (
                f"{a.agent_id} delegates to itself — circular delegation not allowed"
            )

    def test_delegation_targets_exist_in_registry(self, agent_registry):
        for a in agent_registry.all():
            for target in a.can_delegate_to:
                assert agent_registry.get(target) is not None, (
                    f"{a.agent_id} delegates to unknown agent '{target}'"
                )

    def test_delegation_sources_exist_in_registry(self, agent_registry):
        for a in agent_registry.all():
            for source in a.can_receive_delegation_from:
                assert agent_registry.get(source) is not None, (
                    f"{a.agent_id} receives delegation from unknown agent '{source}'"
                )


# ── Scenario Roles ────────────────────────────────────────────────────────────

class TestScenarioRoles:
    """Test agents_for_scenario() queries."""

    def test_chest_pain_has_primary_agents(self, agent_registry):
        agents = agent_registry.agents_for_scenario("chest_pain_cardiac", "primary")
        agent_ids = {a.agent_id for a in agents}
        assert "triage_agent" in agent_ids
        assert "diagnosis_agent" in agent_ids
        assert "imaging_agent" in agent_ids

    def test_chest_pain_includes_avatar(self, agent_registry):
        agents = agent_registry.agents_for_scenario("chest_pain_cardiac", "primary")
        agent_ids = {a.agent_id for a in agents}
        assert "clinician_avatar_agent" in agent_ids

    def test_frailty_discharge_primary_agents(self, agent_registry):
        agents = agent_registry.agents_for_scenario("frailty_discharge", "primary")
        agent_ids = {a.agent_id for a in agents}
        assert "discharge_agent" in agent_ids or "care_coordinator" in agent_ids

    def test_secondary_agents_returned(self, agent_registry):
        agents = agent_registry.agents_for_scenario("chest_pain_cardiac", "secondary")
        assert isinstance(agents, list)

    def test_unknown_scenario_returns_empty(self, agent_registry):
        agents = agent_registry.agents_for_scenario("nonexistent_scenario", "primary")
        assert agents == []


# ── Entra Role Assignments ────────────────────────────────────────────────────

class TestEntraRoleAssignments:
    """Test Entra provisioning payload generation."""

    def test_role_assignments_is_list(self, avatar_identity):
        assignments = avatar_identity.entra_app_role_assignments()
        assert isinstance(assignments, list)
        assert len(assignments) >= 1

    def test_role_assignment_has_required_fields(self, avatar_identity):
        assignment = avatar_identity.entra_app_role_assignments()[0]
        assert "principalDisplayName" in assignment
        assert "appRoleId_hint" in assignment
        assert "group_membership" in assignment

    def test_role_assignment_hint_matches_persona_role(self, avatar_identity):
        assignment = avatar_identity.entra_app_role_assignments()[0]
        persona = avatar_identity.primary_persona
        assert assignment["appRoleId_hint"] == persona.bulletrain_role

    def test_group_membership_in_assignment(self, avatar_identity):
        assignment = avatar_identity.entra_app_role_assignments()[0]
        assert "nexus-clinical-high" in assignment["group_membership"]

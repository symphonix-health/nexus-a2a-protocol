"""Unit tests for shared/nexus_common/rbac.py.

Tests are fully deterministic, require no live agents, and run offline.
Coverage:
  • Scope matching (exact, wildcard, namespace prefix, negative cases)
  • check_scopes() — missing-scope list
  • extract_persona_scopes() — three claim layouts
  • enforce_rbac() — all enforcement axes
  • get_method_required_scopes() — known methods, prefix matching, fallback
  • assess_method_rbac() — holistic agent+method check
  • RBACError — structure and to_dict()
  • mint_persona_jwt() + persona claims round-trip
"""

from __future__ import annotations

import pytest

from shared.nexus_common.rbac import (
    RBACContext,
    RBACError,
    assess_method_rbac,
    check_scope,
    check_scopes,
    enforce_rbac,
    extract_persona_scopes,
    get_method_required_scopes,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _clinician_claims(
    persona_id: str = "P001",
    extra_scopes: list[str] | None = None,
    bulletrain_role: str = "clinician_service",
    purpose_of_use: str = "Treatment",
    data_sensitivity: str = "High",
) -> dict:
    scopes = [
        "patient.read", "patient.write",
        "encounter.read", "encounter.write",
        "observation.read", "observation.write",
        "medicationrequest.read", "medicationrequest.write",
        "diagnosticreport.read", "diagnosticreport.write",
        "consent.read",
    ]
    if extra_scopes:
        scopes.extend(extra_scopes)
    return {
        "sub": f"agent-{persona_id}",
        "scope": "nexus:invoke",
        "persona_id": persona_id,
        "persona_name": "Consultant Physician",
        "bulletrain_role": bulletrain_role,
        "rbac_level": "High",
        "scopes": scopes,
        "purpose_of_use": purpose_of_use,
        "data_sensitivity": data_sensitivity,
    }


def _auditor_claims(persona_id: str = "P013") -> dict:
    return {
        "sub": f"agent-{persona_id}",
        "scope": "nexus:invoke",
        "persona_id": persona_id,
        "persona_name": "Privacy Officer",
        "bulletrain_role": "auditor",
        "rbac_level": "High",
        "scopes": ["audit.read", "consent.read"],
        "purpose_of_use": "Healthcare Operations",
        "data_sensitivity": "High",
    }


def _patient_service_claims(persona_id: str = "P011") -> dict:
    return {
        "sub": f"agent-{persona_id}",
        "scope": "nexus:invoke",
        "persona_id": persona_id,
        "persona_name": "Receptionist",
        "bulletrain_role": "patient_service",
        "rbac_level": "Restricted",
        "scopes": ["patient.read", "appointment.read", "appointment.write"],
        "purpose_of_use": "Healthcare Operations",
        "data_sensitivity": "Medium",
    }


def _connector_claims(persona_id: str = "P056") -> dict:
    return {
        "sub": f"agent-{persona_id}",
        "scope": "nexus:invoke",
        "persona_id": persona_id,
        "persona_name": "Integration Engine Operator",
        "bulletrain_role": "connector",
        "rbac_level": "High",
        "scopes": ["system/*.read", "system/*.write"],
        "purpose_of_use": "System",
        "data_sensitivity": "High",
    }


def _bare_claims() -> dict:
    """Token with no persona claims — bare nexus:invoke."""
    return {
        "sub": "agent-system",
        "scope": "nexus:invoke",
        "exp": 9999999999,
    }


# ── TestScopeMatching ─────────────────────────────────────────────────────────


class TestCheckScope:
    """Wildcard-aware single-scope predicate."""

    def test_exact_match(self):
        assert check_scope(["patient.read"], "patient.read") is True

    def test_no_match(self):
        assert check_scope(["patient.read"], "patient.write") is False

    def test_universal_wildcard_star_dot_star(self):
        assert check_scope(["*.*"], "patient.write") is True
        assert check_scope(["*.*"], "encounter.read") is True
        assert check_scope(["*.*"], "system/admin.read") is True

    def test_universal_wildcard_bare_star(self):
        assert check_scope(["*"], "encounter.write") is True

    def test_resource_wildcard_patient_dot_star(self):
        assert check_scope(["patient.*"], "patient.read") is True
        assert check_scope(["patient.*"], "patient.write") is True
        assert check_scope(["patient.*"], "encounter.read") is False

    def test_action_wildcard_star_dot_read(self):
        assert check_scope(["*.read"], "patient.read") is True
        assert check_scope(["*.read"], "encounter.read") is True
        assert check_scope(["*.read"], "patient.write") is False

    def test_namespace_wildcard_system_slash_star(self):
        assert check_scope(["system/*"], "system/admin.read") is True
        assert check_scope(["system/*"], "system/anything.write") is True
        assert check_scope(["system/*"], "patient.read") is False

    def test_namespace_wildcard_with_action(self):
        # "system/*.read" via fnmatch should match "system/admin.read"
        assert check_scope(["system/*.read"], "system/admin.read") is True
        assert check_scope(["system/*.read"], "system/admin.write") is False

    def test_empty_granted_returns_false(self):
        assert check_scope([], "patient.read") is False

    def test_multiple_granted_one_matches(self):
        granted = ["encounter.read", "patient.read", "observation.write"]
        assert check_scope(granted, "patient.read") is True
        assert check_scope(granted, "patient.write") is False

    def test_case_sensitive_no_accidental_match(self):
        # Scope names are case-sensitive
        assert check_scope(["Patient.Read"], "patient.read") is False

    def test_partial_string_not_a_match(self):
        # "patient" without an action should not match "patient.read"
        assert check_scope(["patient"], "patient.read") is False

    def test_audit_read_scope(self):
        assert check_scope(["audit.read", "consent.read"], "audit.read") is True
        assert check_scope(["audit.read", "consent.read"], "encounter.write") is False


class TestCheckScopes:
    """Missing-scope list helper."""

    def test_all_satisfied_returns_empty(self):
        granted = ["patient.read", "encounter.write", "observation.read"]
        required = ["patient.read", "encounter.write"]
        missing = check_scopes(granted, required)
        assert missing == []

    def test_one_missing(self):
        granted = ["patient.read"]
        required = ["patient.read", "encounter.write"]
        missing = check_scopes(granted, required)
        assert "encounter.write" in missing
        assert "patient.read" not in missing

    def test_all_missing(self):
        missing = check_scopes([], ["patient.read", "medicationrequest.write"])
        assert set(missing) == {"patient.read", "medicationrequest.write"}

    def test_wildcard_grants_satisfy_specific(self):
        granted = ["*.*"]
        missing = check_scopes(granted, ["patient.read", "encounter.write", "system/admin.read"])
        assert missing == []


# ── TestExtractPersonaScopes ──────────────────────────────────────────────────


class TestExtractPersonaScopes:
    """Handles all three token claim layouts."""

    def test_list_valued_scopes_claim(self):
        claims = {"scopes": ["patient.read", "encounter.write"]}
        result = extract_persona_scopes(claims)
        assert result == ["patient.read", "encounter.write"]

    def test_space_separated_scope_string(self):
        claims = {"scope": "nexus:invoke patient.read encounter.read"}
        result = extract_persona_scopes(claims)
        # nexus:invoke is filtered out — it's the gateway scope, not a FHIR scope
        assert "patient.read" in result
        assert "encounter.read" in result
        assert "nexus:invoke" not in result

    def test_nexus_scopes_list_claim(self):
        claims = {"nexus_scopes": ["audit.read", "consent.read"]}
        result = extract_persona_scopes(claims)
        assert set(result) == {"audit.read", "consent.read"}

    def test_empty_claims_returns_empty(self):
        result = extract_persona_scopes({})
        assert result == []

    def test_bare_nexus_invoke_only_returns_empty(self):
        # nexus:invoke alone should not be treated as a FHIR scope
        result = extract_persona_scopes({"scope": "nexus:invoke"})
        assert result == []

    def test_prefers_scopes_list_over_scope_string(self):
        claims = {
            "scopes": ["patient.read"],
            "scope": "nexus:invoke encounter.read",
        }
        result = extract_persona_scopes(claims)
        assert result == ["patient.read"]  # list wins


# ── TestEnforceRBAC ───────────────────────────────────────────────────────────


class TestEnforceRBAC:
    """Core enforcement function — all axes."""

    # ── Scope checks ─────────────────────────────────────────────────────────

    def test_clinician_passes_clinical_scope_check(self):
        ctx = enforce_rbac(
            _clinician_claims(),
            required_scopes=["patient.read", "encounter.write"],
        )
        assert ctx.allowed is True
        assert ctx.missing_scopes == []

    def test_auditor_fails_clinical_write(self):
        with pytest.raises(RBACError) as exc_info:
            enforce_rbac(
                _auditor_claims(),
                required_scopes=["medicationrequest.write"],
            )
        err = exc_info.value
        assert "medicationrequest.write" in str(err)
        assert err.granted == ["audit.read", "consent.read"]

    def test_patient_service_fails_high_sensitivity_scope(self):
        with pytest.raises(RBACError) as exc_info:
            enforce_rbac(
                _patient_service_claims(),
                required_scopes=["observation.read", "encounter.write"],
            )
        err = exc_info.value
        missing = err.required
        assert "observation.read" in missing or "encounter.write" in missing

    def test_connector_wildcard_satisfies_system_scope(self):
        ctx = enforce_rbac(
            _connector_claims(),
            required_scopes=["system/*.read"],
        )
        assert ctx.allowed is True

    def test_connector_satisfies_specific_system_resource(self):
        # system/*.read should cover system/admin.read
        ctx = enforce_rbac(
            _connector_claims(),
            required_scopes=["system/admin.read"],
        )
        assert ctx.allowed is True

    def test_empty_required_scopes_always_passes(self):
        ctx = enforce_rbac(_bare_claims(), required_scopes=[])
        assert ctx.allowed is True

    def test_no_scopes_required_passes_bare_token(self):
        ctx = enforce_rbac(_bare_claims())
        assert ctx.allowed is True

    # ── Bulletrain role checks ────────────────────────────────────────────────

    def test_correct_bulletrain_role_passes(self):
        ctx = enforce_rbac(
            _clinician_claims(),
            permitted_bulletrain_roles=["clinician_service"],
        )
        assert ctx.allowed is True

    def test_wrong_bulletrain_role_denied(self):
        with pytest.raises(RBACError) as exc_info:
            enforce_rbac(
                _auditor_claims(),                          # role = auditor
                permitted_bulletrain_roles=["clinician_service"],
            )
        err = exc_info.value
        assert "auditor" in str(err)

    def test_multiple_permitted_roles_passes_one(self):
        ctx = enforce_rbac(
            _auditor_claims(),
            permitted_bulletrain_roles=["auditor", "admin"],
        )
        assert ctx.allowed is True

    def test_missing_role_claim_denied(self):
        claims = {"sub": "x", "scope": "nexus:invoke"}
        with pytest.raises(RBACError):
            enforce_rbac(claims, permitted_bulletrain_roles=["clinician_service"])

    # ── Purpose-of-use checks ─────────────────────────────────────────────────

    def test_correct_pou_passes(self):
        ctx = enforce_rbac(
            _clinician_claims(purpose_of_use="Treatment"),
            permitted_purposes_of_use=["Treatment"],
        )
        assert ctx.allowed is True

    def test_wrong_pou_denied(self):
        with pytest.raises(RBACError) as exc_info:
            enforce_rbac(
                _clinician_claims(purpose_of_use="Payment"),
                permitted_purposes_of_use=["Treatment", "Healthcare Operations"],
            )
        assert "Payment" in str(exc_info.value)

    def test_no_pou_claim_denied_when_required(self):
        claims = {"sub": "x", "scope": "nexus:invoke", "scopes": ["patient.read"]}
        with pytest.raises(RBACError):
            enforce_rbac(claims, permitted_purposes_of_use=["Treatment"])

    # ── Sensitivity tier checks ───────────────────────────────────────────────

    def test_high_sensitivity_token_passes_high_tier(self):
        ctx = enforce_rbac(
            _clinician_claims(data_sensitivity="High"),
            minimum_sensitivity_tier="High",
        )
        assert ctx.allowed is True

    def test_medium_sensitivity_fails_high_tier(self):
        with pytest.raises(RBACError) as exc_info:
            enforce_rbac(
                _patient_service_claims(),         # data_sensitivity = Medium
                minimum_sensitivity_tier="High",
            )
        assert "Medium" in str(exc_info.value) or "below" in str(exc_info.value)

    def test_medium_passes_low_tier(self):
        ctx = enforce_rbac(
            _patient_service_claims(),
            minimum_sensitivity_tier="Low",
        )
        assert ctx.allowed is True

    def test_high_passes_medium_high_tier(self):
        ctx = enforce_rbac(
            _clinician_claims(),
            minimum_sensitivity_tier="Medium-High",
        )
        assert ctx.allowed is True

    # ── Combined checks ───────────────────────────────────────────────────────

    def test_clinician_passes_all_axes(self):
        ctx = enforce_rbac(
            _clinician_claims(),
            required_scopes=["patient.read", "encounter.write"],
            permitted_bulletrain_roles=["clinician_service"],
            permitted_purposes_of_use=["Treatment"],
            minimum_sensitivity_tier="Medium",
        )
        assert ctx.allowed is True
        assert ctx.missing_scopes == []
        assert "role:clinician_service" in ctx.audit_tags
        assert "pou:Treatment" in ctx.audit_tags

    def test_audit_tags_accumulate_on_pass(self):
        ctx = enforce_rbac(
            _auditor_claims(),
            required_scopes=["audit.read"],
            permitted_bulletrain_roles=["auditor"],
            permitted_purposes_of_use=["Healthcare Operations"],
        )
        assert any("role:" in t for t in ctx.audit_tags)
        assert any("pou:" in t for t in ctx.audit_tags)
        assert any("scopes_ok:" in t for t in ctx.audit_tags)

    # ── Fallback to agent delegated_scopes ────────────────────────────────────

    def test_bare_token_falls_back_to_agent_registry(self):
        """A bare nexus:invoke token with no FHIR scopes should use the
        agent's registered delegated_scopes from config/agent_personas.json."""
        # triage_agent has patient.read + encounter.write in its delegated_scopes
        ctx = enforce_rbac(
            _bare_claims(),
            required_scopes=["patient.read"],
            agent_id="triage_agent",
        )
        assert ctx.allowed is True
        assert "scope_source:agent_registry" in ctx.audit_tags

    def test_bare_token_no_agent_id_fails_scope_check(self):
        """Bare token with no persona scopes and no agent_id — cannot fallback."""
        with pytest.raises(RBACError):
            enforce_rbac(
                _bare_claims(),
                required_scopes=["patient.read"],
                agent_id=None,
            )

    # ── RBACContext to_dict ───────────────────────────────────────────────────

    def test_context_to_dict_keys(self):
        ctx = enforce_rbac(_clinician_claims(), required_scopes=["patient.read"])
        d = ctx.to_dict()
        assert d["allowed"] is True
        assert "persona_id" in d
        assert "bulletrain_role" in d
        assert "granted_scopes" in d
        assert "required_scopes" in d
        assert "missing_scopes" in d
        assert "audit_tags" in d

    # ── RBACError to_dict ─────────────────────────────────────────────────────

    def test_rbac_error_to_dict(self):
        try:
            enforce_rbac(_auditor_claims(), required_scopes=["medicationrequest.write"])
        except RBACError as exc:
            d = exc.to_dict()
            assert d["error"] == "rbac_denied"
            assert isinstance(d["required"], list)
            assert isinstance(d["granted"], list)


# ── TestGetMethodRequiredScopes ───────────────────────────────────────────────


class TestGetMethodRequiredScopes:
    """Verify per-method scope requirements."""

    def test_tasks_send_needs_only_nexus_invoke(self):
        scopes = get_method_required_scopes("tasks/sendSubscribe")
        assert scopes == ["nexus:invoke"]

    def test_triage_assess_needs_patient_encounter(self):
        scopes = get_method_required_scopes("triage/assess")
        assert "patient.read" in scopes
        assert "encounter.write" in scopes

    def test_pharmacy_dispense_needs_medication_write(self):
        scopes = get_method_required_scopes("pharmacy/dispense")
        assert "medicationrequest.write" in scopes

    def test_audit_query_needs_audit_read(self):
        scopes = get_method_required_scopes("audit/query")
        assert "audit.read" in scopes

    def test_fhir_get_needs_patient_read(self):
        scopes = get_method_required_scopes("fhir/get")
        assert "patient.read" in scopes

    def test_osint_scan_needs_system_wildcard(self):
        scopes = get_method_required_scopes("osint/scan")
        assert "system/*.read" in scopes

    def test_unknown_method_returns_nexus_invoke(self):
        scopes = get_method_required_scopes("completely/unknown/method")
        assert scopes == ["nexus:invoke"]

    def test_prefix_match_triage_submethod(self):
        # "triage/something_else" should pick up triage prefix rules
        scopes = get_method_required_scopes("triage/prioritise")
        assert "patient.read" in scopes

    def test_ehr_save_needs_encounter_write(self):
        scopes = get_method_required_scopes("ehr/save")
        assert "encounter.write" in scopes

    def test_consent_check_needs_consent_read(self):
        scopes = get_method_required_scopes("consent/check")
        assert "consent.read" in scopes

    def test_avatar_start_session_needs_clinical_scopes(self):
        scopes = get_method_required_scopes("avatar/start_session")
        assert "patient.read" in scopes
        assert "encounter.write" in scopes

    def test_hl7_receive_needs_system_read(self):
        scopes = get_method_required_scopes("hl7/receive")
        assert "system/*.read" in scopes

    def test_tasks_get_needs_nexus_invoke(self):
        assert get_method_required_scopes("tasks/get") == ["nexus:invoke"]

    def test_tasks_cancel_needs_nexus_invoke(self):
        assert get_method_required_scopes("tasks/cancel") == ["nexus:invoke"]


# ── TestAssessMethodRBAC ──────────────────────────────────────────────────────


class TestAssessMethodRBAC:
    """Holistic agent+method RBAC assessment."""

    def test_clinician_passes_triage_assess(self):
        ctx = assess_method_rbac("triage_agent", "triage/assess", _clinician_claims("P004"))
        assert ctx.allowed is True
        assert ctx.method == "triage/assess"

    def test_clinician_passes_pharmacy_dispense(self):
        ctx = assess_method_rbac("pharmacy_agent", "pharmacy/dispense", _clinician_claims("P007"))
        assert ctx.allowed is True

    def test_auditor_passes_audit_query(self):
        ctx = assess_method_rbac("consent_analyser", "audit/query", _auditor_claims("P013"))
        assert ctx.allowed is True

    def test_auditor_denied_for_pharmacy_dispense(self):
        with pytest.raises(RBACError) as exc_info:
            assess_method_rbac("pharmacy_agent", "pharmacy/dispense", _auditor_claims("P013"))
        assert "medicationrequest.write" in str(exc_info.value)

    def test_patient_service_denied_for_diagnosis(self):
        with pytest.raises(RBACError):
            assess_method_rbac(
                "diagnosis_agent", "diagnosis/analyse", _patient_service_claims("P011")
            )

    def test_connector_passes_osint(self):
        ctx = assess_method_rbac("osint_agent", "osint/scan", _connector_claims("P056"))
        assert ctx.allowed is True

    def test_clinician_passes_ehr_save(self):
        ctx = assess_method_rbac("ehr_writer_agent", "ehr/save", _clinician_claims("P050"))
        assert ctx.allowed is True

    def test_bare_token_passes_tasks_get_via_fallback(self):
        """tasks/get only needs nexus:invoke — bare token should always pass."""
        ctx = assess_method_rbac("discharge_agent", "tasks/get", _bare_claims())
        assert ctx.allowed is True

    def test_bare_token_passes_triage_via_agent_registry(self):
        """Bare token + agent_id — uses agent's registered delegated_scopes."""
        ctx = assess_method_rbac("triage_agent", "triage/assess", _bare_claims())
        assert ctx.allowed is True

    def test_connector_passes_hl7_receive(self):
        ctx = assess_method_rbac("openhie_mediator", "hl7/receive", _connector_claims("P056"))
        assert ctx.allowed is True

    def test_auditor_denied_ehr_write(self):
        with pytest.raises(RBACError):
            assess_method_rbac("ehr_writer_agent", "ehr/write", _auditor_claims("P013"))

    def test_context_has_method_set(self):
        ctx = assess_method_rbac("triage_agent", "triage/assess", _clinician_claims())
        assert ctx.method == "triage/assess"


# ── TestMintPersonaJWT ────────────────────────────────────────────────────────


class TestMintPersonaJWT:
    """Persona-scoped JWT round-trip tests."""

    SECRET = "test-secret-for-rbac-tests"

    def test_plain_jwt_still_verifiable(self):
        from shared.nexus_common.auth import mint_jwt, verify_jwt

        token = mint_jwt("test-subject", self.SECRET)
        claims = verify_jwt(token, self.SECRET, required_scope="nexus:invoke")
        assert claims["sub"] == "test-subject"

    def test_persona_jwt_includes_persona_claims(self):
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        token = mint_persona_jwt(
            "triage_agent",
            self.SECRET,
            persona_id="P004",
            agent_id="triage_agent",
        )
        claims = verify_jwt(token, self.SECRET, required_scope="nexus:invoke")
        assert claims.get("persona_id") == "P004"
        assert claims.get("bulletrain_role") == "clinician_service"
        assert "scopes" in claims
        assert isinstance(claims["scopes"], list)
        assert "patient.read" in claims["scopes"]
        assert claims.get("agent_id") == "triage_agent"

    def test_persona_jwt_without_persona_id_is_still_valid(self):
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        token = mint_persona_jwt("bare-agent", self.SECRET)
        claims = verify_jwt(token, self.SECRET, required_scope="nexus:invoke")
        assert claims["sub"] == "bare-agent"
        # No persona claims embedded
        assert "persona_id" not in claims

    def test_persona_jwt_unknown_persona_id_still_valid(self):
        """Unknown persona_id should not crash minting — graceful degradation."""
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        token = mint_persona_jwt("agent-x", self.SECRET, persona_id="P999_DOES_NOT_EXIST")
        # Token is still valid — just without persona claims
        claims = verify_jwt(token, self.SECRET, required_scope="nexus:invoke")
        assert claims["sub"] == "agent-x"

    def test_persona_jwt_rbac_enforcement_round_trip(self):
        """Full round-trip: mint → verify → enforce_rbac."""
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        token = mint_persona_jwt(
            "pharmacist",
            self.SECRET,
            persona_id="P007",     # Pharmacist — has medicationdispense.write
        )
        claims = verify_jwt(token, self.SECRET)
        ctx = enforce_rbac(
            claims,
            required_scopes=["patient.read", "medicationdispense.write"],
        )
        assert ctx.allowed is True
        assert ctx.persona_id == "P007"

    def test_auditor_persona_jwt_denied_for_clinical_write(self):
        """Auditor round-trip should fail when clinical write scope required."""
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        token = mint_persona_jwt(
            "consent-analyser",
            self.SECRET,
            persona_id="P013",    # Caldicott Guardian — audit.read + consent.read only
        )
        claims = verify_jwt(token, self.SECRET)
        with pytest.raises(RBACError):
            enforce_rbac(claims, required_scopes=["medicationrequest.write"])

    def test_ttl_respected(self):
        """Expired persona JWT must be rejected."""
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt, AuthError

        token = mint_persona_jwt(
            "expired-agent",
            self.SECRET,
            ttl_seconds=-1,     # already expired
        )
        with pytest.raises(AuthError, match="expired"):
            verify_jwt(token, self.SECRET)

    @pytest.mark.parametrize("persona_id,expected_role", [
        ("P001", "clinician_service"),   # Consultant Physician
        ("P004", "clinician_service"),   # Triage Nurse
        ("P007", "clinician_service"),   # Pharmacist
        ("P013", "auditor"),             # Caldicott Guardian
        ("P056", "connector"),           # Integration Engine Operator
        ("P045", "patient_service"),     # Bed Manager (operations)
    ])
    def test_known_persona_roles_in_jwt(self, persona_id: str, expected_role: str):
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        token = mint_persona_jwt("test", self.SECRET, persona_id=persona_id)
        claims = verify_jwt(token, self.SECRET)
        assert claims.get("bulletrain_role") == expected_role, (
            f"P{persona_id}: expected {expected_role}, got {claims.get('bulletrain_role')}"
        )


# ── TestRBACErrorStructure ────────────────────────────────────────────────────


class TestRBACErrorStructure:
    """RBACError exception carries useful debugging context."""

    def test_error_message_is_string(self):
        err = RBACError("test message")
        assert str(err) == "test message"

    def test_error_stores_required_and_granted(self):
        err = RBACError(
            "missing scopes",
            required=["patient.read"],
            granted=["audit.read"],
            persona_id="P013",
            agent_id="consent_analyser",
            bulletrain_role="auditor",
        )
        assert err.required == ["patient.read"]
        assert err.granted == ["audit.read"]
        assert err.persona_id == "P013"
        assert err.agent_id == "consent_analyser"
        assert err.bulletrain_role == "auditor"

    def test_to_dict_well_formed(self):
        err = RBACError(
            "missing scopes",
            required=["encounter.write"],
            granted=["audit.read"],
        )
        d = err.to_dict()
        assert d["error"] == "rbac_denied"
        assert d["required"] == ["encounter.write"]
        assert d["granted"] == ["audit.read"]
        assert "message" in d

    def test_to_dict_defaults_for_missing_fields(self):
        err = RBACError("simple error")
        d = err.to_dict()
        assert d["required"] == []
        assert d["granted"] == []
        assert d["persona_id"] is None

    def test_is_exception_subclass(self):
        err = RBACError("test")
        assert isinstance(err, Exception)

    def test_can_be_caught_as_exception(self):
        with pytest.raises(Exception):
            raise RBACError("test")


# ── TestAgentRegistryIntegration ─────────────────────────────────────────────


class TestAgentRegistryIntegration:
    """Test that all 25 registered agents can mint + validate persona tokens."""

    SECRET = "integration-test-secret"

    @pytest.fixture(scope="class")
    def agent_registry(self):
        from shared.nexus_common.identity import get_agent_registry
        return get_agent_registry()

    def test_all_agents_have_valid_primary_persona(self, agent_registry):
        from shared.nexus_common.identity.persona_registry import get_persona_registry
        persona_reg = get_persona_registry()
        for agent in agent_registry.all():
            persona = persona_reg.get(agent.primary_persona_id)
            assert persona is not None, (
                f"Agent {agent.agent_id} primary_persona_id {agent.primary_persona_id} not found"
            )

    def test_all_agents_have_delegated_scopes(self, agent_registry):
        for agent in agent_registry.all():
            assert len(agent.delegated_scopes) > 0, (
                f"Agent {agent.agent_id} has no delegated_scopes"
            )

    def test_all_agents_have_iam_groups(self, agent_registry):
        for agent in agent_registry.all():
            assert len(agent.iam_groups) > 0, (
                f"Agent {agent.agent_id} has no IAM groups"
            )

    def test_each_agent_jwt_contains_persona_scopes(self, agent_registry):
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        for agent in agent_registry.all():
            token = mint_persona_jwt(
                agent.agent_id,
                self.SECRET,
                persona_id=agent.primary_persona_id,
                agent_id=agent.agent_id,
            )
            claims = verify_jwt(token, self.SECRET)
            assert claims.get("persona_id") == agent.primary_persona_id
            assert claims.get("agent_id") == agent.agent_id
            scopes = claims.get("scopes", [])
            assert len(scopes) > 0, (
                f"Agent {agent.agent_id} persona JWT has no FHIR scopes"
            )

    def test_clinical_agents_can_access_patient_read(self, agent_registry):
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        clinical_agents = [
            a for a in agent_registry.all()
            if any("clinical" in g for g in a.iam_groups)
        ]
        assert len(clinical_agents) >= 10, "Expected at least 10 clinical agents"

        for agent in clinical_agents:
            token = mint_persona_jwt(
                agent.agent_id, self.SECRET, persona_id=agent.primary_persona_id
            )
            claims = verify_jwt(token, self.SECRET)
            ctx = enforce_rbac(claims, required_scopes=["patient.read"])
            assert ctx.allowed is True, (
                f"Clinical agent {agent.agent_id} denied patient.read"
            )

    def test_governance_agents_cannot_write_medication(self, agent_registry):
        from shared.nexus_common.auth import mint_persona_jwt, verify_jwt

        governance_agents = agent_registry.agents_in_group("nexus-governance")
        assert len(governance_agents) > 0

        for agent in governance_agents:
            token = mint_persona_jwt(
                agent.agent_id, self.SECRET, persona_id=agent.primary_persona_id
            )
            claims = verify_jwt(token, self.SECRET)
            with pytest.raises(RBACError):
                enforce_rbac(claims, required_scopes=["medicationrequest.write"])

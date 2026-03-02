from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.nexus_common.auth import mint_jwt, mint_persona_jwt
from shared.nexus_common.authorization import AuthorizationError, authorize_rpc_request
from shared.nexus_common.policy.pdp import reload_policy_decision_point


def _write_policy_data(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _set_common_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    secret: str,
    policy_mode: str,
    policy_path: Path,
    persona_strict: bool = False,
) -> None:
    monkeypatch.setenv("NEXUS_JWT_SECRET", secret)
    monkeypatch.setenv("NEXUS_AUTH_MODE", "hs256")
    monkeypatch.setenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    monkeypatch.setenv("NEXUS_POLICY_MODE", policy_mode)
    monkeypatch.setenv("NEXUS_POLICY_DATA_PATH", str(policy_path))
    monkeypatch.setenv("NEXUS_PERSONA_STRICT", "true" if persona_strict else "false")
    monkeypatch.setenv("NEXUS_MTLS_REQUIRED", "false")
    monkeypatch.setenv("NEXUS_MTLS_AGENT_MAPPING_REQUIRED", "false")
    monkeypatch.setenv("NEXUS_MTLS_AGENT_MATCH_REQUIRED", "false")
    monkeypatch.setenv("NEXUS_CERT_BOUND_TOKENS_REQUIRED", "false")
    reload_policy_decision_point()


def _authorize(
    *,
    token: str,
    method: str,
    params: dict,
    target_agent_id: str,
) -> object:
    return authorize_rpc_request(
        authorization_header=f"Bearer {token}",
        headers={},
        method=method,
        params=params,
        target_agent_id=target_agent_id,
        required_scope="nexus:invoke",
    )


def test_non_encounter_control_plane_method_allows_without_patient_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "non-enc-secret"
    token = mint_jwt("triage_agent", secret, scope="nexus:invoke")
    policy_path = tmp_path / "policy.json"
    _write_policy_data(
        policy_path,
        {
            "defaults": {
                "consent_granted": False,
                "care_team": [],
                "allowed_purposes_of_use": ["Treatment"],
                "requires_break_glass": True,
                "break_glass_allowed": False,
            }
        },
    )
    _set_common_env(monkeypatch, secret=secret, policy_mode="enforce", policy_path=policy_path)

    result = _authorize(
        token=token,
        method="tasks/get",
        params={},
        target_agent_id="triage_agent",
    )
    assert result.policy.allowed is True
    assert result.policy.reasons == []


def test_non_encounter_shadow_mode_records_policy_deny_but_allows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "non-enc-secret"
    token = mint_jwt("consent_analyser", secret, scope="nexus:invoke")
    policy_path = tmp_path / "policy.json"
    _write_policy_data(
        policy_path,
        {
            "defaults": {
                "consent_granted": False,
                "care_team": ["consent_analyser"],
                "allowed_purposes_of_use": ["Healthcare Operations"],
            }
        },
    )
    _set_common_env(monkeypatch, secret=secret, policy_mode="shadow", policy_path=policy_path)

    result = _authorize(
        token=token,
        method="audit/query",
        params={"patient_id": "patient-shadow-01"},
        target_agent_id="consent_analyser",
    )
    assert result.policy.allowed is True
    assert result.policy.shadow_denied is True
    assert "consent_denied" in result.policy.reasons


def test_non_encounter_rbac_denies_insufficient_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "non-enc-secret"
    token = mint_jwt("triage_agent", secret, scope="nexus:invoke")
    policy_path = tmp_path / "policy.json"
    _write_policy_data(policy_path, {"defaults": {"consent_granted": True}})
    _set_common_env(monkeypatch, secret=secret, policy_mode="off", policy_path=policy_path)

    with pytest.raises(AuthorizationError, match="Missing required scopes"):
        _authorize(
            token=token,
            method="audit/query",
            params={},
            target_agent_id="triage_agent",
        )


def test_non_encounter_persona_strict_mode_denies_unknown_agent_principal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "non-enc-secret"
    token = mint_jwt("unknown_service_agent", secret, scope="nexus:invoke")
    policy_path = tmp_path / "policy.json"
    _write_policy_data(policy_path, {"defaults": {"consent_granted": True}})
    _set_common_env(
        monkeypatch,
        secret=secret,
        policy_mode="off",
        policy_path=policy_path,
        persona_strict=True,
    )

    with pytest.raises(AuthorizationError, match="Unknown agent principal"):
        _authorize(
            token=token,
            method="tasks/get",
            params={},
            target_agent_id="triage_agent",
        )


def test_non_encounter_break_glass_with_reason_allows_and_emits_obligation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "non-enc-secret"
    token = mint_jwt("consent_analyser", secret, scope="nexus:invoke")
    policy_path = tmp_path / "policy.json"
    _write_policy_data(
        policy_path,
        {
            "defaults": {
                "consent_granted": False,
                "care_team": [],
                "allowed_purposes_of_use": ["Healthcare Operations"],
                "requires_break_glass": True,
                "break_glass_allowed": True,
            }
        },
    )
    _set_common_env(monkeypatch, secret=secret, policy_mode="enforce", policy_path=policy_path)

    result = _authorize(
        token=token,
        method="audit/query",
        params={
            "patient_id": "patient-bg-01",
            "break_glass": True,
            "break_glass_reason": "Urgent compliance investigation",
        },
        target_agent_id="consent_analyser",
    )
    assert result.policy.allowed is True
    obligation_codes = {item.code for item in result.policy.obligations}
    assert "break_glass_audit" in obligation_codes


def test_non_encounter_purpose_of_use_mismatch_is_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "non-enc-secret"
    token = mint_persona_jwt(
        "consent_analyser",
        secret,
        persona_id="P053",
        agent_id="consent_analyser",
        scope="nexus:invoke",
    )
    policy_path = tmp_path / "policy.json"
    _write_policy_data(
        policy_path,
        {
            "defaults": {
                "consent_granted": True,
                "care_team": ["consent_analyser"],
                "allowed_purposes_of_use": ["Treatment"],
            }
        },
    )
    _set_common_env(monkeypatch, secret=secret, policy_mode="enforce", policy_path=policy_path)

    with pytest.raises(AuthorizationError, match="purpose_of_use_not_allowed"):
        _authorize(
            token=token,
            method="audit/query",
            params={"patient_id": "patient-pou-01"},
            target_agent_id="consent_analyser",
        )

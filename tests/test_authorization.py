from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.nexus_common.auth import mint_jwt
from shared.nexus_common.authorization import AuthorizationError, authorize_rpc_request
from shared.nexus_common.policy.pdp import reload_policy_decision_point


def _write_policy_data(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_authorize_rpc_request_enforce_mode_denies_patient_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "auth-secret"
    token = mint_jwt("triage_agent", secret, scope="nexus:invoke")
    policy_path = tmp_path / "patient_policy_data.json"
    _write_policy_data(
        policy_path,
        {
            "defaults": {
                "consent_granted": False,
                "care_team": [],
                "allowed_purposes_of_use": ["Treatment"],
            }
        },
    )

    monkeypatch.setenv("NEXUS_JWT_SECRET", secret)
    monkeypatch.setenv("NEXUS_AUTH_MODE", "hs256")
    monkeypatch.setenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    monkeypatch.setenv("NEXUS_POLICY_MODE", "enforce")
    monkeypatch.setenv("NEXUS_POLICY_DATA_PATH", str(policy_path))
    reload_policy_decision_point()

    with pytest.raises(AuthorizationError, match="Policy denied"):
        authorize_rpc_request(
            authorization_header=f"Bearer {token}",
            headers={},
            method="tasks/get",
            params={"patient_id": "p-deny"},
            target_agent_id="triage_agent",
            required_scope="nexus:invoke",
        )


def test_authorize_rpc_request_shadow_mode_returns_allow_with_shadow_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "auth-secret"
    token = mint_jwt("triage_agent", secret, scope="nexus:invoke")
    policy_path = tmp_path / "patient_policy_data.json"
    _write_policy_data(
        policy_path,
        {
            "defaults": {
                "consent_granted": False,
                "care_team": [],
                "allowed_purposes_of_use": ["Treatment"],
            }
        },
    )

    monkeypatch.setenv("NEXUS_JWT_SECRET", secret)
    monkeypatch.setenv("NEXUS_AUTH_MODE", "hs256")
    monkeypatch.setenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    monkeypatch.setenv("NEXUS_POLICY_MODE", "shadow")
    monkeypatch.setenv("NEXUS_POLICY_DATA_PATH", str(policy_path))
    reload_policy_decision_point()

    result = authorize_rpc_request(
        authorization_header=f"Bearer {token}",
        headers={},
        method="tasks/get",
        params={"patient_id": "p-shadow"},
        target_agent_id="triage_agent",
        required_scope="nexus:invoke",
    )
    assert result.policy.allowed is True
    assert result.policy.shadow_denied is True

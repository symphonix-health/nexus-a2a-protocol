from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.nexus_common.auth import AuthError, mint_jwt, mint_persona_jwt
from shared.nexus_common.service_auth import verify_service_request


def _write_cert_registry(path: Path, mapping: dict[str, str]) -> None:
    payload = {"version": "1.0", "thumbprints": mapping}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_verify_service_request_maps_agent_principal_from_thumbprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "svc-secret"
    token = mint_persona_jwt(
        "triage_agent",
        secret,
        agent_id="triage_agent",
        scope="nexus:invoke",
    )
    registry_path = tmp_path / "agent_cert_registry.json"
    _write_cert_registry(registry_path, {"AA:BB:CC": "triage_agent"})

    monkeypatch.setenv("NEXUS_JWT_SECRET", secret)
    monkeypatch.setenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    monkeypatch.setenv("NEXUS_AUTH_MODE", "hs256")
    monkeypatch.setenv("NEXUS_MTLS_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_MTLS_AGENT_MAPPING_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_AGENT_CERT_REGISTRY_PATH", str(registry_path))

    ctx = verify_service_request(
        f"Bearer {token}",
        headers={"x-client-cert-sha256": "aa-bb-cc"},
        required_scope="nexus:invoke",
    )
    assert ctx.agent_principal == "triage_agent"
    assert ctx.claims.get("agent_principal") == "triage_agent"
    assert ctx.mtls_present is True


def test_verify_service_request_rejects_unmapped_mtls_thumbprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "svc-secret"
    token = mint_jwt("triage_agent", secret, scope="nexus:invoke")
    registry_path = tmp_path / "agent_cert_registry.json"
    _write_cert_registry(registry_path, {"deadbeef": "triage_agent"})

    monkeypatch.setenv("NEXUS_JWT_SECRET", secret)
    monkeypatch.setenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    monkeypatch.setenv("NEXUS_AUTH_MODE", "hs256")
    monkeypatch.setenv("NEXUS_MTLS_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_MTLS_AGENT_MAPPING_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_AGENT_CERT_REGISTRY_PATH", str(registry_path))

    with pytest.raises(AuthError, match="not mapped"):
        verify_service_request(
            f"Bearer {token}",
            headers={"x-client-cert-sha256": "aabbcc"},
            required_scope="nexus:invoke",
        )


def test_verify_service_request_rejects_token_actor_mismatch_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "svc-secret"
    token = mint_jwt("diagnosis_agent", secret, scope="nexus:invoke")
    registry_path = tmp_path / "agent_cert_registry.json"
    _write_cert_registry(registry_path, {"aabbcc": "triage_agent"})

    monkeypatch.setenv("NEXUS_JWT_SECRET", secret)
    monkeypatch.setenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    monkeypatch.setenv("NEXUS_AUTH_MODE", "hs256")
    monkeypatch.setenv("NEXUS_MTLS_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_MTLS_AGENT_MAPPING_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_MTLS_AGENT_MATCH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_AGENT_CERT_REGISTRY_PATH", str(registry_path))

    with pytest.raises(AuthError, match="does not match"):
        verify_service_request(
            f"Bearer {token}",
            headers={"x-client-cert-sha256": "aabbcc"},
            required_scope="nexus:invoke",
        )


def test_verify_service_request_parses_xfcc_hash_for_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "svc-secret"
    token = mint_jwt("triage_agent", secret, scope="nexus:invoke")
    registry_path = tmp_path / "agent_cert_registry.json"
    _write_cert_registry(registry_path, {"aabbccdd": "triage_agent"})

    monkeypatch.setenv("NEXUS_JWT_SECRET", secret)
    monkeypatch.setenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    monkeypatch.setenv("NEXUS_AUTH_MODE", "hs256")
    monkeypatch.setenv("NEXUS_MTLS_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_MTLS_AGENT_MAPPING_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_AGENT_CERT_REGISTRY_PATH", str(registry_path))

    ctx = verify_service_request(
        f"Bearer {token}",
        headers={
            "x-forwarded-client-cert": "By=spiffe://gateway;Hash=aa:bb:cc:dd;Subject=\"CN=triage\""
        },
        required_scope="nexus:invoke",
    )
    assert ctx.agent_principal == "triage_agent"

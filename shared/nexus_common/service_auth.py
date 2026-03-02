"""Service-to-service auth profile helpers (HS256, OIDC/JWKS, optional mTLS)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from .auth import AuthError, OidcError, verify_jwt, verify_jwt_rs256
from .identity import get_agent_cert_registry, normalize_thumbprint
from .identity.agent_cert_registry import extract_thumbprint_from_xfcc


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _canonical_actor(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_")


@dataclass(frozen=True)
class ServiceAuthContext:
    token: str
    claims: dict[str, Any]
    mtls_present: bool
    cert_thumbprint: str | None
    agent_principal: str | None


def extract_bearer_token(authorization_header: str) -> str:
    auth = str(authorization_header or "")
    if not auth.lower().startswith("bearer "):
        raise AuthError("Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    if not token:
        raise AuthError("Missing bearer token")
    return token


def _verify_token(
    token: str,
    *,
    required_scope: str,
) -> dict[str, Any]:
    auth_mode = os.getenv("NEXUS_AUTH_MODE", "auto").strip().lower()
    if auth_mode == "auto":
        auth_mode = "rs256" if os.getenv("OIDC_DISCOVERY_URL", "").strip() else "hs256"

    if auth_mode in {"rs256", "oidc", "jwks"}:
        discovery_url = os.getenv("OIDC_DISCOVERY_URL", "").strip()
        if not discovery_url:
            raise AuthError("OIDC discovery URL not configured")
        try:
            return verify_jwt_rs256(
                token,
                discovery_url,
                required_scope=required_scope,
                audience=os.getenv("OIDC_AUDIENCE"),
                issuer=os.getenv("OIDC_ISSUER"),
            )
        except (AuthError, OidcError):
            raise
        except Exception as exc:  # noqa: BLE001 - normalize to auth taxonomy
            raise AuthError(str(exc)) from exc

    jwt_secret = os.getenv("NEXUS_JWT_SECRET", "dev-secret-change-me")
    return verify_jwt(token, jwt_secret, required_scope=required_scope)


def _enforce_roles(payload: dict[str, Any], required_roles: list[str] | None = None) -> None:
    env_roles = [r.strip() for r in os.getenv("NEXUS_REQUIRED_ROLES", "").split(",") if r.strip()]
    needed = required_roles if required_roles is not None else env_roles
    if not needed:
        return
    roles_claim = payload.get("roles") or payload.get("role") or payload.get("groups") or []
    if isinstance(roles_claim, str):
        got = {r.strip() for r in roles_claim.split(",") if r.strip()}
    elif isinstance(roles_claim, list):
        got = {str(r).strip() for r in roles_claim if str(r).strip()}
    else:
        got = set()
    if not set(needed).issubset(got):
        raise AuthError("Insufficient roles")


def _extract_client_cert_thumbprint(headers: Mapping[str, str]) -> str | None:
    direct = str(
        headers.get("x-client-cert-sha256") or headers.get("x-cert-thumbprint-sha256") or ""
    ).strip()
    if direct:
        return normalize_thumbprint(direct)
    xfcc = str(headers.get("x-forwarded-client-cert", "")).strip()
    if xfcc:
        parsed = extract_thumbprint_from_xfcc(xfcc)
        if parsed:
            return parsed
    return None


def _has_mtls_identity(headers: Mapping[str, str]) -> bool:
    if _extract_client_cert_thumbprint(headers):
        return True
    xfcc = str(headers.get("x-forwarded-client-cert", "")).strip()
    if xfcc:
        return True
    ssl_verify = str(headers.get("ssl-client-verify", "")).strip().lower()
    if ssl_verify == "success":
        return True
    x_ssl_verify = str(headers.get("x-ssl-client-verify", "")).strip().lower()
    if x_ssl_verify == "success":
        return True
    return False


def _enforce_mtls(headers: Mapping[str, str]) -> None:
    if not _env_bool("NEXUS_MTLS_REQUIRED", False):
        return
    if not _has_mtls_identity(headers):
        raise AuthError("mTLS client certificate required")


def _thumbprints_match(expected_thumbprint: str, presented_thumbprint: str) -> bool:
    if presented_thumbprint == expected_thumbprint:
        return True
    return normalize_thumbprint(presented_thumbprint) == normalize_thumbprint(expected_thumbprint)


def _enforce_cert_bound_token(payload: dict[str, Any], headers: Mapping[str, str]) -> None:
    if not _env_bool("NEXUS_CERT_BOUND_TOKENS_REQUIRED", False):
        return
    cnf = payload.get("cnf")
    expected_thumbprint = None
    if isinstance(cnf, dict):
        expected_thumbprint = str(cnf.get("x5t#S256") or "").strip()
    presented_thumbprint = _extract_client_cert_thumbprint(headers) or ""
    if not expected_thumbprint:
        raise AuthError("Token cnf.x5t#S256 claim required for cert-bound validation")
    if not presented_thumbprint:
        raise AuthError("Client certificate thumbprint header required for cert-bound validation")
    if not _thumbprints_match(expected_thumbprint, presented_thumbprint):
        raise AuthError("Certificate-bound token mismatch")


def _resolve_agent_principal(headers: Mapping[str, str]) -> tuple[str | None, str | None]:
    thumbprint = _extract_client_cert_thumbprint(headers)
    if not thumbprint:
        return None, None
    registry = get_agent_cert_registry()
    return thumbprint, registry.resolve_agent_principal(thumbprint)


def _enforce_agent_mapping(payload: dict[str, Any], headers: Mapping[str, str]) -> tuple[str | None, str | None]:
    thumbprint, mapped_agent = _resolve_agent_principal(headers)
    mapping_required = _env_bool("NEXUS_MTLS_AGENT_MAPPING_REQUIRED", False)
    if mapping_required and not mapped_agent:
        raise AuthError("mTLS certificate is not mapped to an agent principal")

    token_actor = (
        str(payload.get("agent_principal") or payload.get("agent_id") or payload.get("sub") or "").strip()
        or None
    )
    match_required = _env_bool("NEXUS_MTLS_AGENT_MATCH_REQUIRED", False)
    if match_required and mapped_agent and token_actor:
        if _canonical_actor(mapped_agent) != _canonical_actor(token_actor):
            raise AuthError("mTLS agent principal does not match token subject")

    if mapped_agent and not payload.get("agent_principal"):
        payload["agent_principal"] = mapped_agent

    return thumbprint, mapped_agent


def verify_service_auth(
    token: str,
    *,
    headers: Mapping[str, str] | None = None,
    required_scope: str | None = None,
    required_roles: list[str] | None = None,
) -> dict[str, Any]:
    req_scope = required_scope or os.getenv("NEXUS_REQUIRED_SCOPE", "nexus:invoke")
    claims = _verify_token(token, required_scope=req_scope)
    request_headers: Mapping[str, str] = headers or {}
    _enforce_mtls(request_headers)
    _enforce_cert_bound_token(claims, request_headers)
    _enforce_roles(claims, required_roles=required_roles)
    _enforce_agent_mapping(claims, request_headers)
    return claims


def verify_service_request(
    authorization_header: str,
    *,
    headers: Mapping[str, str] | None = None,
    required_scope: str | None = None,
    required_roles: list[str] | None = None,
) -> ServiceAuthContext:
    """Authenticate request headers and return identity context."""
    request_headers: Mapping[str, str] = headers or {}
    token = extract_bearer_token(authorization_header)
    claims = verify_service_auth(
        token,
        headers=request_headers,
        required_scope=required_scope,
        required_roles=required_roles,
    )
    cert_thumbprint, mapped_agent = _resolve_agent_principal(request_headers)
    agent_principal = str(
        claims.get("agent_principal") or claims.get("agent_id") or mapped_agent or ""
    ).strip() or None
    return ServiceAuthContext(
        token=token,
        claims=claims,
        mtls_present=_has_mtls_identity(request_headers),
        cert_thumbprint=cert_thumbprint,
        agent_principal=agent_principal,
    )

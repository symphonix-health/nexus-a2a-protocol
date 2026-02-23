"""Service-to-service auth profile helpers (HS256, OIDC/JWKS, optional mTLS)."""

from __future__ import annotations

import os
from typing import Any, Mapping

from .auth import AuthError, OidcError, verify_jwt, verify_jwt_rs256


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


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


def _has_mtls_identity(headers: Mapping[str, str]) -> bool:
    xfcc = str(headers.get("x-forwarded-client-cert", "")).strip()
    if xfcc:
        return True
    ssl_verify = str(headers.get("ssl-client-verify", "")).strip().lower()
    if ssl_verify == "success":
        return True
    x_ssl_verify = str(headers.get("x-ssl-client-verify", "")).strip().lower()
    if x_ssl_verify == "success":
        return True
    cert_thumbprint = str(headers.get("x-client-cert-sha256", "")).strip()
    if cert_thumbprint:
        return True
    return False


def _enforce_mtls(headers: Mapping[str, str]) -> None:
    if not _env_bool("NEXUS_MTLS_REQUIRED", False):
        return
    if not _has_mtls_identity(headers):
        raise AuthError("mTLS client certificate required")


def _enforce_cert_bound_token(payload: dict[str, Any], headers: Mapping[str, str]) -> None:
    if not _env_bool("NEXUS_CERT_BOUND_TOKENS_REQUIRED", False):
        return
    cnf = payload.get("cnf")
    expected_thumbprint = None
    if isinstance(cnf, dict):
        expected_thumbprint = str(cnf.get("x5t#S256") or "").strip()
    presented_thumbprint = str(
        headers.get("x-client-cert-sha256") or headers.get("x-cert-thumbprint-sha256") or ""
    ).strip()
    if not expected_thumbprint:
        raise AuthError("Token cnf.x5t#S256 claim required for cert-bound validation")
    if not presented_thumbprint:
        raise AuthError("Client certificate thumbprint header required for cert-bound validation")
    if presented_thumbprint != expected_thumbprint:
        raise AuthError("Certificate-bound token mismatch")


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
    return claims

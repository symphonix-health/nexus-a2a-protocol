"""Shared IAM authorization orchestration for gateway and runtime PEPs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from .audit import AuditLogEntry, env_audit_logger
from .identity import PersonaResolutionError, resolve_persona_context
from .policy import PolicyDecision, PolicyRequest, apply_policy_mode, get_policy_decision_point
from .rbac import RBACError, RBACContext, assess_method_rbac
from .service_auth import AuthError, ServiceAuthContext, verify_service_request


class AuthorizationError(Exception):
    """Raised for authorization failures with an attached HTTP status code."""

    def __init__(self, message: str, *, status_code: int = 403) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class AuthorizationResult:
    auth: ServiceAuthContext
    claims: dict[str, Any]
    persona: Any
    rbac: RBACContext | None
    policy: PolicyDecision
    method: str
    params: dict[str, Any]

    @property
    def token(self) -> str:
        return self.auth.token


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _extract_patient_id(params: Mapping[str, Any]) -> str | None:
    if not isinstance(params, Mapping):
        return None

    direct = str(params.get("patient_id") or "").strip()
    if direct:
        return direct

    patient_obj = params.get("patient")
    if isinstance(patient_obj, Mapping):
        pid = str(patient_obj.get("patient_id") or patient_obj.get("id") or "").strip()
        if pid:
            return pid

    task = params.get("task")
    if isinstance(task, Mapping):
        nested = task.get("patient")
        if isinstance(nested, Mapping):
            pid = str(nested.get("patient_id") or nested.get("id") or "").strip()
            if pid:
                return pid
        ref = str(task.get("patient_ref") or task.get("subject") or "").strip()
        if ref:
            return ref.split("/")[-1]

    ref = str(params.get("patient_ref") or params.get("subject") or "").strip()
    if ref:
        return ref.split("/")[-1]
    return None


def _extract_encounter_id(params: Mapping[str, Any]) -> str | None:
    if not isinstance(params, Mapping):
        return None
    for key in ("encounter_id", "visit_id", "episode_id"):
        value = str(params.get(key) or "").strip()
        if value:
            return value
    task = params.get("task")
    if isinstance(task, Mapping):
        for key in ("encounter_id", "visit_id", "episode_id"):
            value = str(task.get(key) or "").strip()
            if value:
                return value
    return None


def _extract_break_glass(params: Mapping[str, Any], claims: Mapping[str, Any]) -> tuple[bool, str | None]:
    break_glass = bool(claims.get("break_glass") or claims.get("emergency_override"))
    reason = str(claims.get("break_glass_reason") or "").strip() or None
    if isinstance(params, Mapping):
        break_glass = break_glass or bool(
            params.get("break_glass")
            or params.get("emergency_override")
            or params.get("override")
        )
        if not reason:
            reason = str(
                params.get("break_glass_reason")
                or params.get("override_reason")
                or params.get("justification")
                or ""
            ).strip() or None
        task = params.get("task")
        if isinstance(task, Mapping):
            break_glass = break_glass or bool(
                task.get("break_glass")
                or task.get("emergency_override")
                or task.get("override")
            )
            if not reason:
                reason = str(
                    task.get("break_glass_reason")
                    or task.get("override_reason")
                    or task.get("justification")
                    or ""
                ).strip() or None
    return break_glass, reason


def _method_resource_action(method: str) -> tuple[str, str]:
    clean = str(method or "").strip()
    if "/" not in clean:
        return clean or "unknown", "invoke"
    resource, _, action = clean.partition("/")
    return resource or "unknown", action or "invoke"


def _policy_request(
    *,
    method: str,
    params: dict[str, Any],
    claims: dict[str, Any],
) -> PolicyRequest:
    resource, action = _method_resource_action(method)
    break_glass, break_glass_reason = _extract_break_glass(params, claims)
    human_actor = (
        str(claims.get("human_actor") or claims.get("on_behalf_of") or "").strip()
        or None
    )
    return PolicyRequest(
        method=method,
        action=action,
        resource=resource,
        patient_id=_extract_patient_id(params),
        encounter_id=_extract_encounter_id(params),
        agent_actor=str(claims.get("agent_principal") or claims.get("agent_id") or claims.get("sub") or "").strip()
        or None,
        human_actor=human_actor,
        effective_persona=str(claims.get("effective_persona") or claims.get("persona_id") or "").strip() or None,
        purpose_of_use=str(claims.get("purpose_of_use") or "").strip() or None,
        break_glass=break_glass,
        break_glass_reason=break_glass_reason,
        claims=dict(claims),
    )


def _log_decision(
    *,
    result: AuthorizationResult | None,
    error: Exception | None,
    trace_id: str | None,
) -> None:
    if not _env_bool("NEXUS_AUDIT_DECISIONS", False):
        return
    logger = env_audit_logger()

    if result is not None:
        policy = result.policy
        reason = ",".join(policy.reasons) if policy.reasons else None
        obligations = ",".join(item.code for item in policy.obligations) if policy.obligations else None
        logger.log(
            AuditLogEntry(
                actor=str(result.claims.get("sub") or result.claims.get("agent_principal") or ""),
                action=result.method,
                resource=result.policy.policy_version,
                outcome="success" if policy.allowed else "denied",
                trace_id=trace_id,
                patient_id=_extract_patient_id(result.params),
                reason=reason,
                agent_actor=str(result.claims.get("agent_principal") or result.claims.get("agent_id") or "") or None,
                human_actor=str(result.claims.get("human_actor") or result.claims.get("on_behalf_of") or "") or None,
                effective_persona=str(
                    result.claims.get("effective_persona") or result.claims.get("persona_id") or ""
                )
                or None,
                decision="allow" if policy.allowed else "deny",
                deny_reasons=policy.reasons or None,
                obligations=obligations.split(",") if obligations else None,
                method=result.method,
            )
        )
        return

    if error is not None:
        logger.log(
            AuditLogEntry(
                actor="unknown",
                action="rpc",
                resource="authorization",
                outcome="denied",
                trace_id=trace_id,
                reason=str(error),
                decision="deny",
            )
        )


def authorize_rpc_request(
    *,
    authorization_header: str,
    headers: Mapping[str, str],
    method: str,
    params: dict[str, Any] | None,
    target_agent_id: str,
    required_scope: str,
    required_roles: list[str] | None = None,
) -> AuthorizationResult:
    """Authenticate + persona-map + RBAC + patient policy decision."""
    trace_id = None
    result: AuthorizationResult | None = None
    try:
        auth = verify_service_request(
            authorization_header,
            headers=headers,
            required_scope=required_scope,
            required_roles=required_roles,
        )
        claims = dict(auth.claims)
        trace_id = str(claims.get("trace_id") or "").strip() or None

        strict_persona = _env_bool("NEXUS_PERSONA_STRICT", False)
        try:
            persona = resolve_persona_context(
                claims,
                agent_principal=auth.agent_principal,
                strict=strict_persona,
            )
        except PersonaResolutionError as exc:
            raise AuthorizationError(str(exc), status_code=403) from exc
        claims.update(persona.to_claims_patch())

        rbac_ctx = assess_method_rbac(target_agent_id, method, claims)

        request_params = params if isinstance(params, dict) else {}
        policy_req = _policy_request(method=method, params=request_params, claims=claims)
        policy_decision = apply_policy_mode(get_policy_decision_point().evaluate(policy_req))

        if not policy_decision.allowed:
            raise AuthorizationError(
                "Policy denied: " + ", ".join(policy_decision.reasons),
                status_code=403,
            )

        result = AuthorizationResult(
            auth=auth,
            claims=claims,
            persona=persona,
            rbac=rbac_ctx,
            policy=policy_decision,
            method=method,
            params=request_params,
        )
        _log_decision(result=result, error=None, trace_id=trace_id)
        return result
    except AuthError as exc:
        _log_decision(result=None, error=exc, trace_id=trace_id)
        raise AuthorizationError(str(exc), status_code=401) from exc
    except RBACError as exc:
        _log_decision(result=None, error=exc, trace_id=trace_id)
        raise AuthorizationError(str(exc), status_code=403) from exc
    except AuthorizationError as exc:
        _log_decision(result=None, error=exc, trace_id=trace_id)
        raise

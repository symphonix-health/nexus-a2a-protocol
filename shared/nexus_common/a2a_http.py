"""HTTP negotiation helpers for NEXUS A2A runtimes.

Supports:
- `application/a2a+json` media type (with legacy `application/json` fallback)
- `A2A-Version` negotiation
- `A2A-Extensions` negotiation
- compatibility shim for legacy `tasks/sendSubscribe` callers
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from fastapi import HTTPException, Request

A2A_MEDIA_TYPE = "application/a2a+json"
A2A_VERSION_HEADER = "A2A-Version"
A2A_EXTENSIONS_HEADER = "A2A-Extensions"
A2A_DEFAULT_VERSION = "1.0"

_LEGACY_MEDIA_TYPES = {
    "application/json",
    "application/json-rpc",
    "application/jsonrpc",
}

_DEFAULT_SUPPORTED_EXTENSIONS = (
    "compat.tasks_sendSubscribe.v1",
    "stream.resume.v1",
    "tracecontext.w3c.v1",
)


@dataclass(frozen=True)
class A2ANegotiation:
    version: str
    requested_extensions: tuple[str, ...]
    accepted_extensions: tuple[str, ...]
    request_media_type: str
    response_media_type: str
    original_method: str
    canonical_method: str
    compatibility_mode: str | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _split_tokens(raw: str) -> list[str]:
    tokens: list[str] = []
    for part in raw.split(","):
        token = part.strip()
        if token:
            tokens.append(token)
    return tokens


def _parse_media_type(content_type: str) -> str:
    token = str(content_type or "").split(";", 1)[0].strip().lower()
    if not token:
        return "application/json"
    return token


def resolve_supported_extensions() -> set[str]:
    env_value = os.getenv("NEXUS_A2A_SUPPORTED_EXTENSIONS", "").strip()
    if env_value:
        return {token for token in _split_tokens(env_value)}
    return set(_DEFAULT_SUPPORTED_EXTENSIONS)


def response_headers(
    negotiation: A2ANegotiation,
    *,
    traceparent: str | None = None,
    tracestate: str | None = None,
) -> dict[str, str]:
    headers = {
        A2A_VERSION_HEADER: negotiation.version,
        A2A_EXTENSIONS_HEADER: ",".join(negotiation.accepted_extensions),
    }
    if traceparent:
        headers["traceparent"] = traceparent
    if tracestate:
        headers["tracestate"] = tracestate
    return headers


def canonicalize_payload_method(payload: dict[str, Any], negotiation: A2ANegotiation) -> dict[str, Any]:
    if negotiation.canonical_method == negotiation.original_method:
        return payload
    out = dict(payload)
    out["method"] = negotiation.canonical_method
    params = out.get("params")
    if isinstance(params, dict):
        out["params"] = dict(params)
    else:
        out["params"] = {}
    out["params"]["legacy_method"] = negotiation.original_method
    return out


def _requested_extensions_from_headers(request: Request) -> tuple[str, ...]:
    requested: list[str] = []
    raw = request.headers.get(A2A_EXTENSIONS_HEADER, "")
    requested.extend(_split_tokens(raw))
    # Some gateway/proxy stacks preserve pseudo-header names literally.
    raw_pseudo = request.headers.get(":A2A-Extensions", "")
    requested.extend(_split_tokens(raw_pseudo))
    dedup: list[str] = []
    seen: set[str] = set()
    for token in requested:
        if token in seen:
            continue
        seen.add(token)
        dedup.append(token)
    return tuple(dedup)


def negotiate_http_request(request: Request, payload: dict[str, Any]) -> A2ANegotiation:
    request_media_type = _parse_media_type(request.headers.get("content-type", ""))
    strict_media = _env_bool("NEXUS_A2A_STRICT_MEDIA_TYPE", False)
    allowed_media = {A2A_MEDIA_TYPE, *_LEGACY_MEDIA_TYPES}
    if request_media_type not in allowed_media:
        raise HTTPException(
            status_code=415,
            detail={
                "reason": "unsupported_media_type",
                "expected": sorted(allowed_media),
                "actual": request_media_type,
            },
        )
    if strict_media and request_media_type != A2A_MEDIA_TYPE:
        raise HTTPException(
            status_code=415,
            detail={
                "reason": "legacy_media_type_disallowed",
                "expected": A2A_MEDIA_TYPE,
                "actual": request_media_type,
            },
        )

    expected_version = os.getenv("NEXUS_A2A_VERSION", A2A_DEFAULT_VERSION).strip() or A2A_DEFAULT_VERSION
    requested_version = str(request.headers.get(A2A_VERSION_HEADER, "")).strip()
    strict_version = _env_bool("NEXUS_A2A_STRICT_VERSION", False)
    if requested_version and strict_version and requested_version != expected_version:
        raise HTTPException(
            status_code=426,
            detail={
                "reason": "unsupported_a2a_version",
                "expected": expected_version,
                "actual": requested_version,
            },
        )

    requested_extensions = _requested_extensions_from_headers(request)
    supported_extensions = resolve_supported_extensions()
    accepted_extensions = tuple(sorted(ext for ext in requested_extensions if ext in supported_extensions))

    method = str(payload.get("method") or "").strip()
    canonical_method = method
    compatibility_mode: str | None = None
    if method == "tasks/sendSubscribe":
        canonical_method = "tasks/send"
        compatibility_mode = "compat.tasks_sendSubscribe.v1"
        if compatibility_mode in supported_extensions and compatibility_mode not in accepted_extensions:
            accepted_extensions = tuple(sorted([*accepted_extensions, compatibility_mode]))

    return A2ANegotiation(
        version=expected_version if not requested_version else requested_version,
        requested_extensions=requested_extensions,
        accepted_extensions=accepted_extensions,
        request_media_type=request_media_type,
        response_media_type=A2A_MEDIA_TYPE,
        original_method=method,
        canonical_method=canonical_method,
        compatibility_mode=compatibility_mode,
    )


def build_outbound_headers(
    *,
    token: str,
    version: str | None = None,
    extensions: list[str] | tuple[str, ...] | None = None,
    traceparent: str | None = None,
    tracestate: str | None = None,
) -> dict[str, str]:
    selected_version = (version or os.getenv("NEXUS_A2A_VERSION", A2A_DEFAULT_VERSION)).strip()
    if not selected_version:
        selected_version = A2A_DEFAULT_VERSION

    if extensions is None:
        ext_list = sorted(resolve_supported_extensions())
    else:
        ext_list = sorted({str(x).strip() for x in extensions if str(x).strip()})

    headers = {
        "Content-Type": A2A_MEDIA_TYPE,
        "Accept": A2A_MEDIA_TYPE,
        "Authorization": f"Bearer {token}",
        A2A_VERSION_HEADER: selected_version,
        A2A_EXTENSIONS_HEADER: ",".join(ext_list),
    }
    if traceparent:
        headers["traceparent"] = traceparent
    if tracestate:
        headers["tracestate"] = tracestate
    return headers

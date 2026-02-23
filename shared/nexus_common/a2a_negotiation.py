"""A2A header/media negotiation helpers for JSON-RPC endpoints."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from .jsonrpc import INVALID_REQUEST, JsonRpcError

DEFAULT_SUPPORTED_VERSIONS = {"1.0", "1.1"}


def _supported_versions() -> set[str]:
    raw = os.getenv("NEXUS_A2A_SUPPORTED_VERSIONS", "").strip()
    if not raw:
        return set(DEFAULT_SUPPORTED_VERSIONS)
    parsed = {token.strip() for token in raw.split(",") if token.strip()}
    return parsed or set(DEFAULT_SUPPORTED_VERSIONS)


def _supported_extensions() -> set[str]:
    raw = os.getenv("NEXUS_A2A_SUPPORTED_EXTENSIONS", "").strip()
    if not raw:
        return set()
    return {token.strip() for token in raw.split(",") if token.strip()}


def _parse_extensions(header_value: str | None) -> tuple[list[str], list[str]]:
    required: list[str] = []
    optional: list[str] = []
    if not header_value:
        return required, optional
    for raw_token in header_value.split(","):
        token = raw_token.strip()
        if not token:
            continue
        if token.startswith("!"):
            normalized = token[1:].strip()
            if normalized:
                required.append(normalized)
            continue
        optional.append(token)
    return required, optional


def negotiate_a2a_headers(headers: Mapping[str, str]) -> dict[str, Any]:
    """Validate A2A request headers and return negotiated metadata.

    Rules:
    - Content-Type must be application/json or application/a2a+json.
    - A2A-Version is optional, but when present must be supported.
    - A2A-Extensions supports comma-separated tokens; required tokens are prefixed with '!'.
    """
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
    media_ok = (
        "application/a2a+json" in content_type
        or "application/json" in content_type
        or content_type == ""
    )
    if not media_ok:
        raise JsonRpcError(
            INVALID_REQUEST,
            "Invalid Request",
            {
                "reason": "unsupported_media_type",
                "field": "Content-Type",
                "accepted": ["application/a2a+json", "application/json"],
                "failure_domain": "validation",
            },
        )

    version = str(headers.get("A2A-Version") or headers.get("a2a-version") or "").strip()
    supported_versions = _supported_versions()
    if version and version not in supported_versions:
        raise JsonRpcError(
            INVALID_REQUEST,
            "Invalid Request",
            {
                "reason": "unsupported_a2a_version",
                "field": "A2A-Version",
                "supported_versions": sorted(supported_versions),
                "failure_domain": "validation",
            },
        )

    required_ext, optional_ext = _parse_extensions(
        str(headers.get("A2A-Extensions") or headers.get("a2a-extensions") or "")
    )
    supported_ext = _supported_extensions()
    missing_required = sorted([token for token in required_ext if token not in supported_ext])
    if missing_required:
        raise JsonRpcError(
            INVALID_REQUEST,
            "Invalid Request",
            {
                "reason": "unsupported_required_extension",
                "field": "A2A-Extensions",
                "missing_required_extensions": missing_required,
                "supported_extensions": sorted(supported_ext),
                "failure_domain": "validation",
            },
        )

    return {
        "media_type": "application/a2a+json" if "application/a2a+json" in content_type else "application/json",
        "a2a_version": version or "1.0",
        "extensions_required": required_ext,
        "extensions_optional": optional_ext,
        "extensions_accepted": sorted([token for token in [*required_ext, *optional_ext] if token in supported_ext]),
    }

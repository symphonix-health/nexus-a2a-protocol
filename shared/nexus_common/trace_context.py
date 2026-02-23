"""W3C trace-context helpers for inter-agent request propagation."""

from __future__ import annotations

import hashlib
import os
import secrets
from typing import Mapping


def _normalize_hex(value: str, size: int) -> str:
    token = "".join(ch for ch in value.lower() if ch in "0123456789abcdef")
    if len(token) == size:
        return token
    if len(token) > size:
        return token[-size:]
    return token.rjust(size, "0")


def _derive_trace_hex(trace_id: str | None) -> str:
    raw = str(trace_id or "").strip()
    if raw:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return _normalize_hex(digest, 32)
    return secrets.token_hex(16)


def _derive_span_hex(trace_id: str | None) -> str:
    raw = str(trace_id or "").strip()
    if raw:
        digest = hashlib.sha256((raw + "::span").encode("utf-8")).hexdigest()
        return _normalize_hex(digest, 16)
    return secrets.token_hex(8)


def build_traceparent(trace_id: str | None, *, sampled: bool = True) -> str:
    trace_hex = _derive_trace_hex(trace_id)
    span_hex = _derive_span_hex(trace_id)
    flags = "01" if sampled else "00"
    return f"00-{trace_hex}-{span_hex}-{flags}"


def extract_trace_context(headers: Mapping[str, str]) -> tuple[str | None, str | None]:
    traceparent = str(headers.get("traceparent", "")).strip() or None
    tracestate = str(headers.get("tracestate", "")).strip() or None
    return traceparent, tracestate


def inject_trace_context(
    headers: dict[str, str],
    *,
    trace_id: str | None,
    tracestate: str | None = None,
) -> tuple[str, str | None]:
    sampled = os.getenv("NEXUS_TRACE_SAMPLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    traceparent = build_traceparent(trace_id, sampled=sampled)
    headers["traceparent"] = traceparent
    if tracestate:
        headers["tracestate"] = tracestate
    return traceparent, tracestate

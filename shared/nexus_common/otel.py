"""Optional OpenTelemetry helpers.

Instrumentation is enabled only when:
- `NEXUS_OTEL_ENABLED=true`
- `opentelemetry` packages are installed
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Any, Iterator


def _otel_enabled() -> bool:
    return os.getenv("NEXUS_OTEL_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    if not _otel_enabled():
        yield None
        return
    try:
        from opentelemetry import trace as otel_trace  # type: ignore
    except Exception:
        yield None
        return

    tracer = otel_trace.get_tracer("nexus-a2a")
    with tracer.start_as_current_span(name) as span:
        if span is not None and isinstance(attributes, dict):
            for key, value in attributes.items():
                try:
                    span.set_attribute(str(key), value)
                except Exception:
                    continue
        yield span


def emit_route_telemetry(
    *,
    route_source: str,
    route_target: str,
    agent_name: str,
    zone: str,
    trust_anchor: str,
    policy_result: str,
    session_id: str | None = None,
    admitted: bool = True,
    deny_reasons: list[str] | None = None,
) -> None:
    """Emit a route admission telemetry span with standard GHARRA attributes.

    This is a fire-and-forget helper — if OTel is disabled or unavailable,
    it silently returns.
    """
    attrs: dict[str, Any] = {
        "route.source": route_source,
        "route.target": route_target,
        "route.agent_name": agent_name,
        "route.zone": zone,
        "route.trust_anchor": trust_anchor,
        "route.policy_result": policy_result,
        "route.admitted": admitted,
    }
    if session_id:
        attrs["route.session_id"] = session_id
    if deny_reasons:
        attrs["route.deny_reasons"] = ",".join(deny_reasons)

    with start_span("gharra.route_telemetry", attributes=attrs):
        pass

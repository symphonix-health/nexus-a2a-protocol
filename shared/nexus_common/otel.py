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

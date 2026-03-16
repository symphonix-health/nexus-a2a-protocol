"""GHARRA-aware transport wrapper for SDK transport implementations.

Wraps any AgentTransport to run route admission before send_task().
The GHARRA record can be provided at construction or injected per-task
via a ``gharra_record`` key in the task envelope params.

This keeps the base transport classes (HttpSseTransport, WebSocketTransport)
free from GHARRA coupling while making admission available at the SDK level.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

from .transport import AgentTransport
from .types import TaskEnvelope, TaskEvent, TaskSubmission, TransportError

logger = logging.getLogger(__name__)


class GharraAdmissionTransport(AgentTransport):
    """Transport decorator that enforces GHARRA route admission pre-flight.

    Usage::

        inner = HttpSseTransport(base_url=..., token=...)
        transport = GharraAdmissionTransport(
            inner,
            gharra_record={...},          # default record
            route_source="bullettrain",
        )
        await transport.connect()
        submission = await transport.send_task(envelope)
    """

    def __init__(
        self,
        inner: AgentTransport,
        *,
        gharra_record: dict[str, Any] | None = None,
        route_source: str = "sdk-transport",
        local_mtls_available: bool = False,
        local_cert_thumbprint: str | None = None,
    ) -> None:
        self._inner = inner
        self._default_record = gharra_record
        self._route_source = route_source
        self._local_mtls_available = local_mtls_available
        self._local_cert_thumbprint = local_cert_thumbprint

    async def connect(self) -> None:
        await self._inner.connect()

    async def send_task(
        self, task: TaskEnvelope | Mapping[str, Any]
    ) -> TaskSubmission:
        # Resolve GHARRA record: per-task override > constructor default
        gharra_data = self._default_record
        if isinstance(task, Mapping):
            params = task.get("params")
            if isinstance(params, dict) and "gharra_record" in params:
                gharra_data = params.get("gharra_record")

        if gharra_data and isinstance(gharra_data, dict):
            self._run_admission(gharra_data, task)

        return await self._inner.send_task(task)

    async def stream_events(self, task_id: str) -> AsyncIterator[TaskEvent]:
        async for event in self._inner.stream_events(task_id):
            yield event

    async def stop(self) -> None:
        await self._inner.stop()

    def _run_admission(
        self,
        gharra_data: dict[str, Any],
        task: TaskEnvelope | Mapping[str, Any],
    ) -> None:
        """Run synchronous route admission check.

        Import is deferred to avoid hard dependency on shared.nexus_common
        in SDK-only deployments.
        """
        try:
            from shared.nexus_common.route_admission import (
                evaluate_route_admission_from_dict,
            )
        except ImportError:
            logger.debug(
                "shared.nexus_common.route_admission not available; "
                "skipping GHARRA admission in SDK transport"
            )
            return

        method = None
        if isinstance(task, TaskEnvelope):
            method = task.method
        elif isinstance(task, Mapping):
            method = str(task.get("method") or "").strip() or None

        result = evaluate_route_admission_from_dict(
            gharra_data,
            local_mtls_available=self._local_mtls_available,
            local_cert_thumbprint=self._local_cert_thumbprint,
            method=method,
            route_source=self._route_source,
        )

        if not result.admitted:
            raise TransportError(
                f"GHARRA route admission denied: "
                f"{'; '.join(result.reasons)}",
                code=-32003,
                details=result.to_dict(),
            )

        if result.warnings:
            logger.warning(
                "GHARRA admission warnings for %s: %s",
                result.agent_name,
                "; ".join(result.warnings),
            )

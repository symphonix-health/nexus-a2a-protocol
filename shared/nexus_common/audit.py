"""Structured audit logging helpers for HelixCare/NEXUS-A2A.

This module provides a minimal JSONL audit logger suitable for development
and POC deployments. In production, wire this to an append-only store
or external audit service.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class AuditLogEntry:
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    actor: str = ""
    action: str = ""  # e.g., read | write | consent_check | approve | deny
    resource: str = ""  # e.g., "Patient/123", "DocumentReference/abc"
    outcome: str = ""  # success | denied | error
    trace_id: Optional[str] = None
    patient_id: Optional[str] = None
    reason: Optional[str] = None
    ip_address: Optional[str] = None
    agent_actor: Optional[str] = None
    human_actor: Optional[str] = None
    effective_persona: Optional[str] = None
    decision: Optional[str] = None
    deny_reasons: Optional[list[str]] = None
    obligations: Optional[list[str]] = None
    method: Optional[str] = None


class AuditLogger:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, entry: AuditLogEntry) -> None:
        line = json.dumps(asdict(entry), separators=(",", ":"))
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def env_audit_logger(default_path: str = "logs/audit.jsonl") -> AuditLogger:
    """Construct an AuditLogger from environment (AUDIT_LOG_PATH)."""
    path = os.environ.get("AUDIT_LOG_PATH", default_path)
    return AuditLogger(path)

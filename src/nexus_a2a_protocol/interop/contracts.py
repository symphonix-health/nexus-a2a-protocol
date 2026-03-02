"""Contracts for hybrid profile envelopes and typed artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ActorContext:
    sub: str
    actor_type: str
    scopes: list[str] = field(default_factory=list)
    tenant: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = payload.pop("actor_type")
        return {k: v for k, v in payload.items() if v is not None}


@dataclass(slots=True)
class AcceptableProfile:
    profile_id: str
    version_range: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "profileId": self.profile_id,
            "versionRange": self.version_range,
        }


@dataclass(slots=True)
class ArtifactPart:
    part_id: str
    kind: str
    content_type: str
    payload_mode: str = "inline"
    inline_payload: Any | None = None
    reference: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "partId": self.part_id,
            "kind": self.kind,
            "contentType": self.content_type,
            "payloadMode": self.payload_mode,
        }
        if self.inline_payload is not None:
            payload["inlinePayload"] = self.inline_payload
        if self.reference is not None:
            payload["reference"] = self.reference
        if self.constraints is not None:
            payload["constraints"] = self.constraints
        return payload


@dataclass(slots=True)
class NexusEnvelope:
    envelope_version: str
    task_id: str
    correlation_id: str
    actor: ActorContext
    requested_profile: str
    parts: list[ArtifactPart]
    acceptable_profiles: list[AcceptableProfile] = field(default_factory=list)
    idempotency_key: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    replay: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "envelopeVersion": self.envelope_version,
            "taskId": self.task_id,
            "correlationId": self.correlation_id,
            "timestamp": self.timestamp,
            "actor": self.actor.to_dict(),
            "requestedProfile": self.requested_profile,
            "parts": [part.to_dict() for part in self.parts],
        }
        if self.acceptable_profiles:
            payload["acceptableProfiles"] = [
                profile.to_dict() for profile in self.acceptable_profiles
            ]
        if self.idempotency_key:
            payload["idempotencyKey"] = self.idempotency_key
        if self.replay is not None:
            payload["replay"] = self.replay
        if self.meta is not None:
            payload["meta"] = self.meta
        return payload


@dataclass(slots=True)
class NexusProblem:
    code: str
    message: str
    retryable: bool
    correlation_id: str
    details: dict[str, Any] | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "correlationId": self.correlation_id,
            "timestamp": self.timestamp,
        }
        if self.details is not None:
            payload["details"] = self.details
        return payload

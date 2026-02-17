"""NEXUS-A2A shared common library for agent-to-agent communication."""

from .audit import AuditLogEntry, AuditLogger, env_audit_logger  # noqa: F401
from .auth import mint_jwt, verify_jwt, verify_jwt_rs256  # noqa: F401
from .health import HealthMonitor, apply_backpressure_to_agent_card  # noqa: F401
from .http_client import jsonrpc_call  # noqa: F401
from .idempotency import IdempotencyResult, IdempotencyStore, RedisIdempotencyStore  # noqa: F401
from .jsonrpc import JsonRpcError, parse_request, response_error, response_result  # noqa: F401
from .protocol import (  # noqa: F401
    CorrelationContext,
    IdempotencyContext,
    ProgressState,
    ScaleProfileContext,
    ScenarioContext,
    apply_mutation_response_metadata,
    build_task_envelope,
    validate_vector_clock_conflict_payload,
)
from .redaction import redact_payload  # noqa: F401
from .scale_profile import (  # noqa: F401
    SCALE_PROFILE_VERSION,
    build_canonical_shard_key,
    build_scale_response_metadata,
    evaluate_feature_negotiation,
    negotiate_scale_features,
    resolve_supported_features,
    validate_canonical_shard_key,
)
from .sse import TaskEventBus, build_signed_resume_cursor, parse_signed_resume_cursor  # noqa: F401
from .trace import TraceRun, TraceStepEvent  # noqa: F401

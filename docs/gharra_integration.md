# GHARRA Integration — Nexus Route Admission

## Overview

Nexus integrates with GHARRA (Global Healthcare Agent Registry & Routing Authority) as a **consumer of trust and routing metadata** — not as a registry or orchestration engine.

```
BulletTrain (orchestration)
  → GHARRA (resolve agent by name/capability)
  → Nexus (validate trust, open transport)
  → Remote agent
```

Nexus validates GHARRA records before opening routes. It does not perform discovery.

## Data Flow

1. **BulletTrain** resolves an agent via GHARRA (`GET /v1/agents/{name}`)
2. **BulletTrain** passes the GHARRA record to Nexus via `X-Gharra-Record` header (gateway) or `gharra_record` param (SDK)
3. **Nexus** runs route admission checks (13 validations)
4. If admitted, Nexus proxies the JSON-RPC request to the target agent
5. Route telemetry is emitted via OpenTelemetry; audit log written if enabled

## Route Admission Checks (13 total)

| # | Check | Severity | Module |
|---|-------|----------|--------|
| 1 | Record status is `active` | deny | `gharra_trust.validate_record_status` |
| 2 | Agent name is valid (.health namespace) | deny | `gharra_trust.validate_agent_name` |
| 3 | Zone delegation chain consistent | deny | `gharra_trust.validate_zone_delegation` |
| 4 | Trust anchor in allowed set | deny | `gharra_trust.validate_trust_anchors` |
| 5 | JWKS URI well-formed | warn/deny | `gharra_trust.validate_jwks_uri` |
| 6 | Thumbprint policy consistent | warn/deny | `gharra_trust.validate_thumbprint_policy` |
| 7 | Certificate-bound token rules satisfiable | deny | `gharra_trust.validate_cert_binding` |
| 8 | Policy tags not denied / required present | deny | `gharra_trust.validate_policy_tags` |
| 9 | Jurisdiction / data-residency allowed | deny | `gharra_trust.validate_jurisdiction` |
| 10 | Federated records pass trust check | deny | `gharra_trust.validate_federation` |
| 11 | Protocol is `nexus-a2a` | deny | `route_admission._validate_protocol_compatibility` |
| 12 | Protocol version compatible (1.0/1.1) | deny | `route_admission._validate_protocol_compatibility` |
| 13 | Feature flags supported | warn/deny | `route_admission._validate_feature_compatibility` |
| 14 | Transport endpoint non-empty | deny | `route_admission.evaluate_route_admission` |

Checks 5, 6, 13 produce **warnings** in relaxed mode (default) and **hard denials** in strict mode.

## GHARRA Record Format

```json
{
  "agent_name": "patient-registry.nhs.uk.health",
  "zone": "nhs.uk.health",
  "trust_anchor": "uk.health",
  "transport": {
    "endpoint": "https://router.nhs.uk/a2a/patient-registry",
    "protocol": "nexus-a2a",
    "protocol_versions": ["1.0", "1.1"],
    "feature_flags": ["routing.v1", "stream.resume.v1"]
  },
  "authentication": {
    "mtls_required": true,
    "jwks_uri": "https://auth.nhs.uk/.well-known/jwks.json",
    "cert_bound_tokens_required": true,
    "thumbprint_policy": "cnf.x5t#S256"
  },
  "capabilities": ["FHIR.Patient.read", "identity.match"],
  "policy_tags": ["phi", "uk-only"],
  "jurisdiction": "UK",
  "status": "active",
  "federated": false
}
```

## Gateway Integration

The On-Demand Gateway (`POST /rpc/{agent_alias}`) accepts `X-Gharra-Record` header:

```
POST /rpc/patient_registry HTTP/1.1
Authorization: Bearer <jwt>
X-Gharra-Record: {"agent_name":"patient-registry.nhs.uk.health",...}
Content-Type: application/json

{"jsonrpc":"2.0","method":"tasks/send","params":{...},"id":1}
```

If admission is denied, a `403` response with denial reasons is returned.

## SDK Transport Integration

The `GharraAdmissionTransport` wraps any `AgentTransport` (e.g. `HttpSseTransport`) to run admission before `send_task()`:

```python
from nexus_a2a_protocol.sdk.http_sse_transport import HttpSseTransport
from nexus_a2a_protocol.sdk.gharra_transport import GharraAdmissionTransport

inner = HttpSseTransport(base_url="http://localhost:8100/rpc/triage", token=token)
transport = GharraAdmissionTransport(
    inner,
    gharra_record=gharra_data,
    route_source="bullettrain-signalbox",
)
await transport.connect()
submission = await transport.send_task(envelope)
```

Per-task records can also be injected via `params.gharra_record`.

## Record Caching

Admitted GHARRA records are cached in-memory with a configurable TTL (default: 60s). The `evaluate_route_admission_from_dict` function checks the cache before re-validating, reducing overhead for repeated calls to the same agent.

```python
from shared.nexus_common.gharra_models import get_record_cache

cache = get_record_cache()
cache.clear()  # Clear when trust anchors change
```

## Certificate-Bound Token Validation

When a GHARRA record specifies `authentication.cert_bound_tokens_required: true`:

1. The JWT `cnf.x5t#S256` claim must be present
2. A client certificate thumbprint must be available
3. The thumbprint must match the JWT claim

Extended with `verify_gharra_cert_binding()` in `service_auth.py` for per-route control.

When `thumbprint_policy: "cnf.x5t#S256"` is set, `cert_bound_tokens_required` must also be true (consistency check).

## Jurisdiction / Data-Residency

When `NEXUS_GHARRA_ALLOWED_JURISDICTIONS` is set:
- Agents must declare a matching `jurisdiction`
- PHI-tagged agents without jurisdiction are denied
- Non-PHI agents without jurisdiction produce no error

## Federation

Federated agents (from peer GHARRA registries, `federated: true`) require trust anchor validation even when the general trust model is open.

## Scale-Profile Extension

Route admission can inject GHARRA metadata into the JSON-RPC scale profile:

```python
from shared.nexus_common.route_admission import build_gharra_scale_extension

ext = build_gharra_scale_extension(record)
# Returns: {"gharra": {"agent_name": ..., "zone": ..., ...}}
```

## Audit Logging

When `NEXUS_AUDIT_DECISIONS=true`, route admission writes to the audit log:

```json
{"actor":"on-demand-gateway","action":"route_admission","resource":"patient-registry.nhs.uk.health","outcome":"success"}
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXUS_GHARRA_STRICT_NAMESPACE` | `false` | Enforce `.health` namespace format |
| `NEXUS_GHARRA_TRUSTED_ANCHORS` | *(none — open trust)* | Comma-separated allowed trust anchors |
| `NEXUS_GHARRA_DENIED_TAGS` | *(none)* | Comma-separated denied policy tags |
| `NEXUS_GHARRA_REQUIRED_TAGS` | *(none)* | Comma-separated required policy tags |
| `NEXUS_GHARRA_ALLOWED_JURISDICTIONS` | *(none — open)* | Comma-separated allowed jurisdictions |
| `NEXUS_GHARRA_ENFORCE_MTLS` | `false` | Deny routes requiring mTLS when unavailable |
| `NEXUS_GHARRA_STRICT_FEATURES` | `false` | Deny routes with unsupported feature flags |
| `NEXUS_GHARRA_STRICT_JWKS` | `false` | Deny routes with malformed JWKS URIs |
| `NEXUS_GHARRA_STRICT_THUMBPRINT` | `false` | Deny routes with inconsistent thumbprint policy |
| `NEXUS_AUDIT_DECISIONS` | `false` | Enable audit logging for admission decisions |

## Route Telemetry

When OTel is enabled (`NEXUS_OTEL_ENABLED=true`), route admission emits spans with:

| Attribute | Description |
|-----------|-------------|
| `route.source` | Origin (e.g. `on-demand-gateway`, `sdk-transport`) |
| `route.target` | Transport endpoint |
| `route.agent_name` | GHARRA agent name |
| `route.zone` | GHARRA zone |
| `route.trust_anchor` | Trust anchor used |
| `route.policy_result` | `admit`, `deny`, or `warn` |
| `route.jurisdiction` | Declared jurisdiction |
| `route.federated` | Whether agent is from a federated registry |
| `route.session_id` | Session ID (if available) |
| `route.admitted` | Boolean |
| `route.check_duration_ms` | Validation time in milliseconds |
| `route.deny_reasons` | Comma-separated reasons (if denied) |
| `route.warnings` | Comma-separated warnings (if any) |

## Module Layout

```
shared/nexus_common/
├── gharra_models.py      # GharraRecord, RouteDescriptor, RouteAdmissionResult,
│                         # GharraRecordCache, parse_gharra_record
├── gharra_trust.py       # 10 trust validators (name, zone, anchors, jwks, thumbprint,
│                         # certs, tags, jurisdiction, status, federation)
├── route_admission.py    # Route admission gate, audit logging, scale-profile extension,
│                         # caching, evaluate/enforce/from_dict
├── service_auth.py       # Extended: verify_gharra_cert_binding()
└── otel.py               # Extended: emit_route_telemetry()

src/nexus_a2a_protocol/sdk/
└── gharra_transport.py   # GharraAdmissionTransport — SDK transport decorator

tests/
├── test_gharra_trust.py             # 62 trust validation tests
└── test_gharra_route_admission.py   # 35 route admission + model + cache tests

HelixCare/
└── helixcare_gharra_route_admission_matrix.json  # 13 harness scenarios
```

## Harness Test Matrix

`HelixCare/helixcare_gharra_route_admission_matrix.json` contains 13 scenarios:
- 3 positive (valid record, federation, feature warnings)
- 8 negative (revoked, zone mismatch, protocol, endpoint, tags, trust, jurisdiction, version)
- 2 edge (name alias, minimal record)

## What Nexus Does NOT Do

- **Discovery**: Nexus does not query GHARRA. BulletTrain resolves agents.
- **Registry**: Nexus does not store agent records. GHARRA owns the registry.
- **Orchestration**: Nexus does not decide which agent to call. BulletTrain/SignalBox orchestrates.
- **Zone delegation**: Nexus validates delegation chains but does not manage them.

## Alignment with Existing Patterns

| Existing Pattern | GHARRA Extension |
|-----------------|------------------|
| `service_auth.py` cert-bound tokens | `verify_gharra_cert_binding()` for per-route enforcement |
| `scale_profile.py` feature flags | Route admission validates against `SUPPORTED_FEATURE_FLAGS` |
| `authorization.py` orchestration | Route admission runs at transport level (gateway/SDK), not IAM level |
| `audit.py` logging | `_audit_route_decision()` uses existing `AuditLogEntry` pattern |
| `otel.py` span helpers | `emit_route_telemetry()` for route-level observability |
| `idempotency.py` TTL cache | `GharraRecordCache` uses same TTL pattern |
| On-demand gateway proxy | `X-Gharra-Record` header triggers admission before proxy |
| SDK `AgentTransport` ABC | `GharraAdmissionTransport` decorator preserves interface |

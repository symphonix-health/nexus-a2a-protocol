# NEXUS A2A Hyperscale Implementation Backlog

Status date: 2026-02-15
Target: 2B registered users, 2M concurrent sessions
Scope: concrete implementation backlog for this repository

## Milestones

### M0 - Foundation Hardening

`Goal`: remove single-process assumptions in critical hot paths and establish gateable load assets.

Platform tickets:
- `HS-M0-PLAT-001` Replace per-request HTTP client creation with pooled clients in shared RPC transport.
- `HS-M0-PLAT-002` Introduce Redis-capable idempotency backend and controlled fallback to in-memory mode.
- `HS-M0-PLAT-003` Make triage agent idempotency backend selectable by env (`memory|redis`).

Data tickets:
- `HS-M0-DATA-001` Keep in-memory idempotency store for dev and tests as explicit fallback path.
- `HS-M0-DATA-002` Define Redis key schema for idempotency records with TTL and cached response support.

Messaging tickets:
- `HS-M0-MSG-001` Preserve current JSON-RPC contract while reducing transport churn under load.

Test gate tickets:
- `HS-M0-TEST-001` Expand command-centre load matrix from ~1k to >=7k scenarios with explicit gate tags.
- `HS-M0-TEST-002` Add automated matrix integrity tests for scenario volume and high-concurrency coverage.

### M1 - Regional Scale Unit

`Goal`: make a single region scale unit with explicit ingress and rate controls.

Service tickets:
- `HS-M1-SVC-001` `shared/command-centre`: split health polling and event fanout workers, add bounded worker pools.
- `HS-M1-SVC-002` `demos/ed-triage/triage-agent`: enforce semaphore-based in-flight limits from env.
- `HS-M1-SVC-003` `demos/ed-triage/diagnosis-agent`: add async queue and timeout budget enforcement.
- `HS-M1-SVC-004` `demos/helixcare/care-coordinator`: migrate from fire-and-forget tasks to durable workflow handles.

Datastore tickets:
- `HS-M1-DS-001` Deploy Redis Cluster profile and move all hot idempotency/session keys to cluster-safe keying.
- `HS-M1-DS-002` Add managed Postgres/Cockroach metadata store for tenancy, policies, and routing config.

Messaging tickets:
- `HS-M1-MSG-001` Introduce Kafka topic set for task lifecycle (`accepted|working|final|error`) and DLQ.

Test gate tickets:
- `HS-M1-GATE-001` Gate G1: 100k concurrency synthetic matrix + 48h soak profile definitions.
- `HS-M1-GATE-002` Gate G1: chaos scenarios for broker restart, Redis shard failover, and API worker churn.

### M2 - Multi-Region Active-Active (3 Regions)

`Goal`: deliver first true active-active deployment blueprint and repo support assets.

Service tickets:
- `HS-M2-SVC-001` Add region-aware routing metadata to agent cards and request correlation context.
- `HS-M2-SVC-002` Add stateless session affinity keys for SSE/WebSocket connection plane workers.

Datastore tickets:
- `HS-M2-DS-001` Introduce wide-column profile (Scylla/Cassandra) for user/session/task metadata.
- `HS-M2-DS-002` Implement dual-write adapters and backfill scripts for metadata migration.

Messaging tickets:
- `HS-M2-MSG-001` Configure per-region Kafka clusters with replicated topic policies.
- `HS-M2-MSG-002` Add replay tools to reconstruct task-state timelines.

Test gate tickets:
- `HS-M2-GATE-001` Gate G2: 500k concurrency, 75k RPS, one-region failover profile.
- `HS-M2-GATE-002` Gate G2: data consistency checks on dual-write and replay.

### M3 - 8 Region Cell Architecture

`Goal`: scale to production cell model with bounded blast radius and autoscaling.

Service tickets:
- `HS-M3-SVC-001` Add cell identifiers to runtime config and telemetry dimensions.
- `HS-M3-SVC-002` Build per-cell admission control and overload shedding contracts.

Datastore tickets:
- `HS-M3-DS-001` Implement shard-map management for 2B users and online rebalancing hooks.
- `HS-M3-DS-002` Add hot/warm/cold retention policies for event and audit stores.

Messaging tickets:
- `HS-M3-MSG-001` Partition expansion automation and consumer lag SLO enforcement.

Test gate tickets:
- `HS-M3-GATE-001` Gate G3: 1.5M concurrency, 220k RPS, AZ outage and broker outage scenarios.

### M4 - 2M Concurrency Production Gate

`Goal`: final readiness gate for 2M concurrent users.

Service tickets:
- `HS-M4-SVC-001` Finalize SLO-based autoscaling profiles and admission policies.

Datastore tickets:
- `HS-M4-DS-001` Validate RPO/RTO with full replay and restore exercises.

Messaging tickets:
- `HS-M4-MSG-001` Validate sustained high-throughput event ingestion and replay correctness.

Test gate tickets:
- `HS-M4-GATE-001` Gate G4: 2M concurrency, 300k RPS, 7-day soak, zero unrecoverable message loss.
- `HS-M4-GATE-002` Gate G4: weekly chaos game-day scenario bundle.

## Service Backlog by Component

- `shared/nexus_common/http_client.py`
  - `HS-M0-PLAT-001` pooled client transport
  - `HS-M1-SVC-010` request-level budgets and adaptive retries
- `shared/nexus_common/idempotency.py`
  - `HS-M0-PLAT-002` Redis idempotency backend
  - `HS-M1-DS-005` namespace and tenancy key strategy
- `demos/ed-triage/triage-agent/app/main.py`
  - `HS-M0-PLAT-003` env-selectable idempotency backend
  - `HS-M1-SVC-002` bounded in-flight queue
- `shared/command-centre/app/main.py`
  - `HS-M1-SVC-001` bounded polling and event fanout
  - `HS-M2-SVC-010` region-aware topology

## Datastore Backlog

- `Redis`
  - `HS-M0-DATA-002` idempotency key schema + TTL
  - `HS-M1-DS-001` cluster rollout and failover testing
- `Kafka/Pulsar`
  - `HS-M1-MSG-001` lifecycle topics + DLQ
  - `HS-M2-MSG-002` replay tooling
- `Scylla/Cassandra`
  - `HS-M2-DS-001` large-scale metadata store
  - `HS-M3-DS-001` shard-map and rebalancing
- `Cockroach/Postgres`
  - `HS-M1-DS-002` control-plane metadata
- `Object Storage`
  - `HS-M3-DS-002` immutable archives + retention

## Test Gate Backlog

Gate inventory:
- `G0` foundation load assets and matrix integrity
- `G1` 100k concurrency regional scale unit
- `G2` 500k concurrency multi-region failover
- `G3` 1.5M concurrency 8-region cell tests
- `G4` 2M concurrency production gate

Gate ticket mapping:
- `G0`: `HS-M0-TEST-001`, `HS-M0-TEST-002`
- `G1`: `HS-M1-GATE-001`, `HS-M1-GATE-002`
- `G2`: `HS-M2-GATE-001`, `HS-M2-GATE-002`
- `G3`: `HS-M3-GATE-001`
- `G4`: `HS-M4-GATE-001`, `HS-M4-GATE-002`

## Current Commenced Work (this change set)

Completed:
- `HS-M0-PLAT-001`
- `HS-M0-PLAT-002`
- `HS-M0-PLAT-003`
- `HS-M0-TEST-001`
- `HS-M0-TEST-002`

Next suggested start:
- `HS-M1-SVC-002`
- `HS-M1-MSG-001`
- `HS-M1-GATE-001`

"""Central seed database for production-grade agent configuration.

Supports three backends selected by ``NEXUS_SEED_DB_BACKEND``:

- **sqlite** (default) — zero-config local dev, WAL-mode SQLite
- **postgresql** — production, requires ``NEXUS_SEED_DB_URL``
  (e.g. ``postgresql://user:pass@host:5432/nexus``)

Optional layers:

- **Redis** — read-through cache for hot-path lookups (``REDIS_URL``)
- **Kafka** — publishes ``nexus.seed.*`` events on seed writes (``KAFKA_BOOTSTRAP_SERVERS``)

Usage::

    from shared.nexus_common.seed_db import get_seed_db

    db = get_seed_db()
    url = db.get_agent_url("pharmacy")          # http://localhost:8025
    profiles = db.get_job_profiles()             # {"triage": "Triage Nurse", ...}
    graph = db.get_dependency_graph()            # {"triage": ["diagnosis", ...], ...}
    esi = db.evaluate_triage_rules("chest pain", {"spo2": 88})  # "ESI-2"
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("nexus.seed-db")

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ── Optional imports (gracefully degrade when not installed) ────────────
try:
    import psycopg2
    import psycopg2.extras

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

try:
    import redis as _redis_mod

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    from confluent_kafka import Producer as _KafkaProducer

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False


# ── Alias normalisation (mirrors tools/helixcare_scenarios.py logic) ────
_ALIAS_OVERRIDES: dict[str, str] = {
    "care_coordinator": "coordinator",
    "followup_scheduler": "followup",
}

_KEEP_SUFFIX_IDS: set[str] = {
    "insurer_agent",
    "provider_agent",
}


def _agent_id_to_alias(agent_id: str) -> str:
    """Convert an agents.json key (e.g. ``triage_agent``) to the short alias
    used by the scenario runner and gateway (e.g. ``triage``)."""
    if agent_id in _ALIAS_OVERRIDES:
        return _ALIAS_OVERRIDES[agent_id]
    if agent_id in _KEEP_SUFFIX_IDS:
        return agent_id
    for suffix in ("_agent",):
        if agent_id.endswith(suffix):
            return agent_id[: -len(suffix)]
    return agent_id


# ═══════════════════════════════════════════════════════════════════════
#  Kafka event publisher (optional)
# ═══════════════════════════════════════════════════════════════════════

class _KafkaEventPublisher:
    """Publishes seed-change events to Kafka topics."""

    def __init__(self) -> None:
        self._producer: Any | None = None
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        if KAFKA_AVAILABLE and bootstrap:
            try:
                self._producer = _KafkaProducer({
                    "bootstrap.servers": bootstrap,
                    "client.id": "nexus-seed-db",
                    "acks": "all",
                    "retries": 3,
                    "linger.ms": 10,
                })
                logger.info("Kafka event publisher connected to %s", bootstrap)
            except Exception as exc:
                logger.warning("Kafka unavailable (%s); seed events will not be published", exc)

    def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        if self._producer is None:
            return
        try:
            self._producer.produce(
                topic,
                key=key.encode(),
                value=json.dumps(payload, separators=(",", ":")).encode(),
                timestamp=int(time.time() * 1000),
            )
            self._producer.poll(0)
        except Exception as exc:
            logger.warning("Kafka publish failed for %s/%s: %s", topic, key, exc)

    def flush(self, timeout: float = 5.0) -> None:
        if self._producer is not None:
            self._producer.flush(timeout)


_kafka = _KafkaEventPublisher()


# ═══════════════════════════════════════════════════════════════════════
#  Redis cache layer (optional)
# ═══════════════════════════════════════════════════════════════════════

class _RedisCache:
    """Read-through cache for hot-path seed DB lookups."""

    _PREFIX = "nexus:seed:"
    _TTL = int(os.getenv("NEXUS_SEED_CACHE_TTL", "300"))  # 5 min default

    def __init__(self) -> None:
        self._client: Any | None = None
        redis_url = os.getenv("REDIS_URL", "").strip()
        if REDIS_AVAILABLE and redis_url:
            try:
                self._client = _redis_mod.Redis.from_url(
                    redis_url, decode_responses=True, socket_timeout=2.0
                )
                self._client.ping()
                logger.info("Redis seed cache connected to %s", redis_url)
            except Exception as exc:
                logger.warning("Redis unavailable (%s); seed cache disabled", exc)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def get(self, key: str) -> str | None:
        if self._client is None:
            return None
        try:
            return self._client.get(f"{self._PREFIX}{key}")
        except Exception:
            return None

    def set(self, key: str, value: str) -> None:
        if self._client is None:
            return
        try:
            self._client.setex(f"{self._PREFIX}{key}", self._TTL, value)
        except Exception:
            pass

    def invalidate(self, pattern: str = "*") -> None:
        if self._client is None:
            return
        try:
            keys = self._client.keys(f"{self._PREFIX}{pattern}")
            if keys:
                self._client.delete(*keys)
        except Exception:
            pass


_cache = _RedisCache()


# ═══════════════════════════════════════════════════════════════════════
#  Abstract backend
# ═══════════════════════════════════════════════════════════════════════

class _SeedBackend(ABC):
    """Common interface for seed database backends."""

    @abstractmethod
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Execute a query and return rows."""

    @abstractmethod
    def execute_many(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        """Execute a parameterised statement for multiple rows."""

    @abstractmethod
    def execute_script(self, sql: str) -> None:
        """Execute a multi-statement DDL script."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""


# ═══════════════════════════════════════════════════════════════════════
#  SQLite backend (local dev)
# ═══════════════════════════════════════════════════════════════════════

class _SqliteBackend(_SeedBackend):
    def __init__(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(p), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def execute_many(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        with self._lock:
            with self._conn:
                self._conn.executemany(sql, rows)

    def execute_script(self, sql: str) -> None:
        with self._lock:
            with self._conn:
                self._conn.executescript(sql)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ═══════════════════════════════════════════════════════════════════════
#  PostgreSQL backend (production)
# ═══════════════════════════════════════════════════════════════════════

class _PostgresBackend(_SeedBackend):
    def __init__(self, dsn: str) -> None:
        if not POSTGRES_AVAILABLE:
            raise RuntimeError(
                "psycopg2 is required for PostgreSQL backend: pip install psycopg2-binary"
            )
        self._lock = threading.Lock()
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        sql = self._adapt_sql(sql)
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description:
                    return cur.fetchall()
                return []

    def execute_many(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        sql = self._adapt_sql(sql)
        with self._lock:
            with self._conn.cursor() as cur:
                psycopg2.extras.execute_batch(cur, sql, rows)
            self._conn.commit()

    def execute_script(self, sql: str) -> None:
        sql = self._adapt_pg_ddl(sql)
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(sql)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _adapt_sql(sql: str) -> str:
        """Convert SQLite ``?`` placeholders to PostgreSQL ``%s``."""
        return sql.replace("?", "%s")

    @staticmethod
    def _adapt_pg_ddl(sql: str) -> str:
        """Adapt SQLite DDL to PostgreSQL-compatible DDL."""
        adapted = sql
        # AUTOINCREMENT → GENERATED ALWAYS AS IDENTITY
        adapted = adapted.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT",
            "INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY",
        )
        # INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE (handled per-statement)
        return adapted


# ═══════════════════════════════════════════════════════════════════════
#  NexusSeedDB — unified API over any backend
# ═══════════════════════════════════════════════════════════════════════

# PostgreSQL uses ON CONFLICT ... DO UPDATE instead of INSERT OR REPLACE.
# These upsert templates are selected based on the active backend.

_SQLITE_UPSERT_AGENTS = (
    "INSERT OR REPLACE INTO agents "
    "(agent_id, alias, agent_group, port, path, description, rpc_env, env) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_PG_UPSERT_AGENTS = (
    "INSERT INTO agents "
    "(agent_id, alias, agent_group, port, path, description, rpc_env, env) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (agent_id) DO UPDATE SET "
    "alias=EXCLUDED.alias, agent_group=EXCLUDED.agent_group, port=EXCLUDED.port, "
    "path=EXCLUDED.path, description=EXCLUDED.description, "
    "rpc_env=EXCLUDED.rpc_env, env=EXCLUDED.env"
)
_SQLITE_UPSERT_PERSONAS = (
    "INSERT OR REPLACE INTO personas "
    "(persona_id, full_name, country, job_profile, specialty, data_json) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)
_PG_UPSERT_PERSONAS = (
    "INSERT INTO personas "
    "(persona_id, full_name, country, job_profile, specialty, data_json) "
    "VALUES (%s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (persona_id) DO UPDATE SET "
    "full_name=EXCLUDED.full_name, country=EXCLUDED.country, "
    "job_profile=EXCLUDED.job_profile, specialty=EXCLUDED.specialty, "
    "data_json=EXCLUDED.data_json"
)
_SQLITE_UPSERT_AGENT_PERSONAS = (
    "INSERT OR REPLACE INTO agent_personas "
    "(agent_id, port, primary_persona_id, persona_name, "
    " iam_groups_json, delegated_scopes_json, data_json) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_PG_UPSERT_AGENT_PERSONAS = (
    "INSERT INTO agent_personas "
    "(agent_id, port, primary_persona_id, persona_name, "
    " iam_groups_json, delegated_scopes_json, data_json) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (agent_id) DO UPDATE SET "
    "port=EXCLUDED.port, primary_persona_id=EXCLUDED.primary_persona_id, "
    "persona_name=EXCLUDED.persona_name, iam_groups_json=EXCLUDED.iam_groups_json, "
    "delegated_scopes_json=EXCLUDED.delegated_scopes_json, data_json=EXCLUDED.data_json"
)
_SQLITE_UPSERT_SCENARIOS = (
    "INSERT OR REPLACE INTO scenarios "
    "(name, description, patient_profile_json, journey_steps_json, medical_history_json) "
    "VALUES (?, ?, ?, ?, ?)"
)
_PG_UPSERT_SCENARIOS = (
    "INSERT INTO scenarios "
    "(name, description, patient_profile_json, journey_steps_json, medical_history_json) "
    "VALUES (%s, %s, %s, %s, %s) "
    "ON CONFLICT (name) DO UPDATE SET "
    "description=EXCLUDED.description, patient_profile_json=EXCLUDED.patient_profile_json, "
    "journey_steps_json=EXCLUDED.journey_steps_json, "
    "medical_history_json=EXCLUDED.medical_history_json"
)
_SQLITE_UPSERT_DEP_GRAPH = (
    "INSERT OR REPLACE INTO dependency_graph (source_agent, target_agent) VALUES (?, ?)"
)
_PG_UPSERT_DEP_GRAPH = (
    "INSERT INTO dependency_graph (source_agent, target_agent) VALUES (%s, %s) "
    "ON CONFLICT (source_agent, target_agent) DO NOTHING"
)


class NexusSeedDB:
    """Unified seed database — SQLite (dev) or PostgreSQL (production),
    with optional Redis cache and Kafka event publishing."""

    def __init__(self, path: str | None = None) -> None:
        backend_type = os.getenv("NEXUS_SEED_DB_BACKEND", "sqlite").strip().lower()
        self._is_pg = backend_type == "postgresql"

        if self._is_pg:
            dsn = os.getenv("NEXUS_SEED_DB_URL", "")
            if not dsn:
                raise RuntimeError(
                    "NEXUS_SEED_DB_URL is required when NEXUS_SEED_DB_BACKEND=postgresql"
                )
            self._backend: _SeedBackend = _PostgresBackend(dsn)
            logger.info("Seed DB using PostgreSQL backend")
        else:
            resolved = path or os.getenv(
                "NEXUS_SEED_DB_PATH",
                str(_REPO_ROOT / "temp" / "nexus_seed.sqlite3"),
            )
            self._backend = _SqliteBackend(resolved)
            logger.info("Seed DB using SQLite backend at %s", resolved)

        self._init_schema()

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        self._backend.execute_script(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_id    TEXT PRIMARY KEY,
                alias       TEXT NOT NULL,
                agent_group TEXT NOT NULL,
                port        INTEGER NOT NULL,
                path        TEXT NOT NULL,
                description TEXT,
                rpc_env     TEXT,
                env         TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_personas (
                agent_id              TEXT PRIMARY KEY,
                port                  INTEGER NOT NULL,
                primary_persona_id    TEXT NOT NULL,
                persona_name          TEXT NOT NULL,
                iam_groups_json       TEXT NOT NULL DEFAULT '[]',
                delegated_scopes_json TEXT NOT NULL DEFAULT '[]',
                data_json             TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS personas (
                persona_id  TEXT PRIMARY KEY,
                full_name   TEXT NOT NULL,
                country     TEXT NOT NULL,
                job_profile TEXT NOT NULL,
                specialty   TEXT,
                data_json   TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS scenarios (
                name                 TEXT PRIMARY KEY,
                description          TEXT,
                patient_profile_json TEXT NOT NULL DEFAULT '{}',
                journey_steps_json   TEXT NOT NULL DEFAULT '[]',
                medical_history_json TEXT
            );

            CREATE TABLE IF NOT EXISTS triage_rules (
                rule_id        INTEGER PRIMARY KEY
                    """
            + ("AUTOINCREMENT" if not self._is_pg else "GENERATED ALWAYS AS IDENTITY")
            + """,
                priority       INTEGER NOT NULL,
                condition_type TEXT NOT NULL,
                field          TEXT NOT NULL,
                operator       TEXT NOT NULL,
                value          TEXT NOT NULL,
                esi_level      TEXT NOT NULL,
                rationale      TEXT
            );

            CREATE TABLE IF NOT EXISTS dependency_graph (
                source_agent TEXT NOT NULL,
                target_agent TEXT NOT NULL,
                PRIMARY KEY (source_agent, target_agent)
            );
            """
        )
        # Unique index on alias — CREATE INDEX IF NOT EXISTS works on both backends
        try:
            self._backend.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_alias ON agents (alias)"
            )
        except Exception:
            pass  # index already exists

    # ── Helpers ─────────────────────────────────────────────────────────

    def _upsert(self, sqlite_sql: str, pg_sql: str, rows: list[tuple[Any, ...]]) -> None:
        sql = pg_sql if self._is_pg else sqlite_sql
        self._backend.execute_many(sql, rows)

    # ── Seed methods ────────────────────────────────────────────────────

    def seed_agents(self, config_path: str | None = None) -> int:
        """Seed the ``agents`` table from ``config/agents.json``. Returns row count."""
        path = Path(config_path) if config_path else _REPO_ROOT / "config" / "agents.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows: list[tuple[str, ...]] = []

        for section_key in ("backend", "gateway"):
            section = raw.get(section_key, {})
            if isinstance(section, dict):
                for agent_id, info in section.items():
                    if not isinstance(info, dict):
                        continue
                    port = info.get("port")
                    if not isinstance(port, int):
                        continue
                    alias = _agent_id_to_alias(agent_id)
                    rows.append((
                        agent_id, alias, section_key, port,
                        info.get("path", ""), info.get("description", ""),
                        info.get("rpc_env", ""), info.get("env", ""),
                    ))

        agents_by_group = raw.get("agents", {})
        if isinstance(agents_by_group, dict):
            for group_name, group in agents_by_group.items():
                if not isinstance(group, dict):
                    continue
                for agent_id, info in group.items():
                    if not isinstance(info, dict):
                        continue
                    port = info.get("port")
                    if not isinstance(port, int):
                        continue
                    alias = _agent_id_to_alias(agent_id)
                    rows.append((
                        agent_id, alias, group_name, port,
                        info.get("path", ""), info.get("description", ""),
                        info.get("rpc_env", ""), info.get("env", ""),
                    ))

        self._upsert(_SQLITE_UPSERT_AGENTS, _PG_UPSERT_AGENTS, rows)
        _cache.invalidate("agent_urls*")
        _kafka.publish("nexus.seed.agents", "agents", {"count": len(rows)})
        return len(rows)

    def seed_personas(self, config_path: str | None = None) -> int:
        """Seed the ``personas`` table from ``config/personas.json``."""
        path = Path(config_path) if config_path else _REPO_ROOT / "config" / "personas.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        personas_data = raw.get("personas", [])
        # Support both list (actual format) and dict (legacy)
        if isinstance(personas_data, dict):
            items = list(personas_data.items())
        elif isinstance(personas_data, list):
            items = [(p.get("persona_id", ""), p) for p in personas_data if isinstance(p, dict)]
        else:
            return 0
        rows: list[tuple[str, ...]] = []
        for pid, pdata in items:
            if not isinstance(pdata, dict) or not pid:
                continue
            # personas.json uses "name" and "country_context"
            full_name = pdata.get("full_name") or pdata.get("name", "")
            country = pdata.get("country") or pdata.get("country_context", "")
            job_profile = pdata.get("job_profile") or pdata.get("role_description", "")
            specialty = pdata.get("specialty") or pdata.get("domain", "")
            rows.append((
                pid, full_name, country, job_profile, specialty,
                json.dumps(pdata, separators=(",", ":"), ensure_ascii=False),
            ))
        self._upsert(_SQLITE_UPSERT_PERSONAS, _PG_UPSERT_PERSONAS, rows)
        _kafka.publish("nexus.seed.personas", "personas", {"count": len(rows)})
        return len(rows)

    def seed_agent_personas(self, config_path: str | None = None) -> int:
        """Seed the ``agent_personas`` table from ``config/agent_personas.json``."""
        path = (
            Path(config_path) if config_path else _REPO_ROOT / "config" / "agent_personas.json"
        )
        raw = json.loads(path.read_text(encoding="utf-8"))
        agents = raw.get("agents", {})
        if not isinstance(agents, dict):
            return 0
        rows: list[tuple[Any, ...]] = []
        for agent_id, adata in agents.items():
            if not isinstance(adata, dict):
                continue
            iam = adata.get("iam", {}) if isinstance(adata.get("iam"), dict) else {}
            rows.append((
                agent_id, adata.get("port", 0),
                adata.get("primary_persona_id", ""),
                adata.get("persona_name", ""),
                json.dumps(iam.get("groups", []), separators=(",", ":")),
                json.dumps(iam.get("delegated_scopes", []), separators=(",", ":")),
                json.dumps(adata, separators=(",", ":"), ensure_ascii=False),
            ))
        self._upsert(
            _SQLITE_UPSERT_AGENT_PERSONAS, _PG_UPSERT_AGENT_PERSONAS, rows
        )
        _cache.invalidate("job_profiles*")
        _kafka.publish("nexus.seed.agent_personas", "agent_personas", {"count": len(rows)})
        return len(rows)

    def seed_scenarios(self, catalog_path: str | None = None) -> int:
        """Seed the ``scenarios`` table from ``tools/helixcare_all_scenarios.json``."""
        path = (
            Path(catalog_path)
            if catalog_path
            else _REPO_ROOT / "tools" / "helixcare_all_scenarios.json"
        )
        if not path.is_file():
            return 0
        catalog = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(catalog, list):
            return 0
        rows: list[tuple[str, ...]] = []
        for entry in catalog:
            if not isinstance(entry, dict):
                continue
            rows.append((
                entry.get("name", ""),
                entry.get("description", ""),
                json.dumps(
                    entry.get("patient_profile", {}), separators=(",", ":"), ensure_ascii=False
                ),
                json.dumps(
                    entry.get("journey_steps", []), separators=(",", ":"), ensure_ascii=False
                ),
                json.dumps(entry.get("medical_history"), separators=(",", ":"), ensure_ascii=False)
                if entry.get("medical_history")
                else None,
            ))
        self._upsert(_SQLITE_UPSERT_SCENARIOS, _PG_UPSERT_SCENARIOS, rows)
        _kafka.publish("nexus.seed.scenarios", "scenarios", {"count": len(rows)})
        return len(rows)

    def seed_triage_rules(self) -> int:
        """Seed the canonical ESI triage rules (consolidated from 3 agent implementations)."""
        rules = [
            (1, "keyword", "chief_complaint", "contains", "chest", "ESI-2",
             "Chest-related complaints require urgent evaluation"),
            (2, "keyword", "chief_complaint", "contains", "shortness of breath", "ESI-2",
             "Respiratory distress requires urgent evaluation"),
            (3, "vital_threshold", "spo2", "lt", "90", "ESI-2",
             "Hypoxia (SpO2 < 90%) requires urgent intervention"),
            (4, "keyword", "chief_complaint", "contains", "confusion", "ESI-2",
             "Altered mental status requires urgent evaluation"),
            (5, "vital_threshold", "temp_c", "gte", "39.0", "ESI-2",
             "High fever (>= 39.0C) requires urgent evaluation"),
            (6, "keyword", "chief_complaint", "contains", "laceration", "ESI-4",
             "Simple laceration is low-acuity"),
            (99, "default", "_", "eq", "_", "ESI-3",
             "Default triage level for unmatched presentations"),
        ]
        self._backend.execute("DELETE FROM triage_rules", ())
        insert_sql = (
            "INSERT INTO triage_rules "
            "(priority, condition_type, field, operator, value, esi_level, rationale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        if self._is_pg:
            insert_sql = insert_sql.replace("?", "%s")
        self._backend.execute_many(insert_sql, rules)
        _cache.invalidate("triage_rules*")
        _kafka.publish("nexus.seed.triage_rules", "triage_rules", {"count": len(rules)})
        return len(rules)

    def seed_dependency_graph(
        self, graph: dict[str, list[str]] | None = None, config_path: str | None = None
    ) -> int:
        """Seed the ``dependency_graph`` table."""
        if graph is None:
            path = (
                Path(config_path)
                if config_path
                else _REPO_ROOT / "config" / "dependency_graph.json"
            )
            if not path.is_file():
                return 0
            graph = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(graph, dict):
            return 0
        rows: list[tuple[str, str]] = []
        for source, targets in graph.items():
            if isinstance(targets, list):
                for target in targets:
                    if isinstance(target, str):
                        rows.append((source, target))
        self._backend.execute("DELETE FROM dependency_graph", ())
        self._upsert(_SQLITE_UPSERT_DEP_GRAPH, _PG_UPSERT_DEP_GRAPH, rows)
        _cache.invalidate("dep_graph*")
        _kafka.publish("nexus.seed.dependency_graph", "dependency_graph", {"count": len(rows)})
        return len(rows)

    def seed_all(self) -> dict[str, int]:
        """Seed all tables from default config paths. Idempotent."""
        counts: dict[str, int] = {}
        counts["agents"] = self.seed_agents()
        counts["personas"] = self.seed_personas()
        counts["agent_personas"] = self.seed_agent_personas()
        counts["scenarios"] = self.seed_scenarios()
        counts["triage_rules"] = self.seed_triage_rules()
        counts["dependency_graph"] = self.seed_dependency_graph()
        logger.info("Seed DB populated: %s", counts)
        _kafka.flush()
        return counts

    # ── Read API (with Redis cache) ─────────────────────────────────────

    def get_agent_url(self, alias: str) -> str | None:
        """Return ``http://localhost:{port}`` for the given alias, or ``None``."""
        cache_key = f"agent_url:{alias}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached if cached != "__NONE__" else None

        rows = self._backend.execute(
            "SELECT port FROM agents WHERE alias = ?"
            if not self._is_pg
            else "SELECT port FROM agents WHERE alias = %s",
            (alias,),
        )
        if not rows:
            _cache.set(cache_key, "__NONE__")
            return None
        url = f"http://localhost:{rows[0][0]}"
        _cache.set(cache_key, url)
        return url

    def get_all_agent_urls(self) -> dict[str, str]:
        """Return alias → URL map (replaces the old ``BASE_URLS`` dict)."""
        cache_key = "agent_urls:all"
        cached = _cache.get(cache_key)
        if cached is not None:
            return json.loads(cached)

        rows = self._backend.execute(
            "SELECT alias, port FROM agents "
            "WHERE agent_group NOT IN ('backend', 'gateway') "
            "ORDER BY port"
        )
        result = {alias: f"http://localhost:{port}" for alias, port in rows}
        _cache.set(cache_key, json.dumps(result, separators=(",", ":")))
        return result

    def get_job_profiles(self) -> dict[str, str]:
        """Return normalised alias → persona display name map."""
        cache_key = "job_profiles:all"
        cached = _cache.get(cache_key)
        if cached is not None:
            return json.loads(cached)

        rows = self._backend.execute(
            "SELECT a.alias, ap.persona_name "
            "FROM agent_personas ap "
            "JOIN agents a ON a.agent_id = ap.agent_id "
            "ORDER BY a.port"
        )
        result = {alias: name for alias, name in rows}
        _cache.set(cache_key, json.dumps(result, separators=(",", ":")))
        return result

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """Return the agent dependency graph as a dict."""
        cache_key = "dep_graph:all"
        cached = _cache.get(cache_key)
        if cached is not None:
            return json.loads(cached)

        rows = self._backend.execute(
            "SELECT source_agent, target_agent FROM dependency_graph ORDER BY source_agent"
        )
        graph: dict[str, list[str]] = {}
        for source, target in rows:
            graph.setdefault(source, []).append(target)
        _cache.set(cache_key, json.dumps(graph, separators=(",", ":")))
        return graph

    def evaluate_triage_rules(
        self, complaint: str, vitals: dict[str, Any] | None = None
    ) -> str:
        """Evaluate triage rules in priority order and return the ESI level."""
        rows = self._backend.execute(
            "SELECT condition_type, field, operator, value, esi_level "
            "FROM triage_rules ORDER BY priority"
        )
        vitals = vitals or {}
        complaint_lower = complaint.lower() if complaint else ""
        for condition_type, field, operator, value, esi_level in rows:
            if condition_type == "keyword":
                if operator == "contains" and value.lower() in complaint_lower:
                    return esi_level
            elif condition_type == "vital_threshold":
                try:
                    vital_val = float(vitals.get(field, float("nan")))
                except (TypeError, ValueError):
                    continue
                threshold = float(value)
                if operator == "lt" and vital_val < threshold:
                    return esi_level
                if operator == "gte" and vital_val >= threshold:
                    return esi_level
            elif condition_type == "default":
                return esi_level
        return "ESI-3"

    def get_scenario(self, name: str) -> dict[str, Any] | None:
        """Return a full scenario record by name."""
        rows = self._backend.execute(
            "SELECT name, description, patient_profile_json, journey_steps_json, "
            "medical_history_json FROM scenarios WHERE name = ?"
            if not self._is_pg
            else "SELECT name, description, patient_profile_json, journey_steps_json, "
            "medical_history_json FROM scenarios WHERE name = %s",
            (name,),
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "name": row[0],
            "description": row[1],
            "patient_profile": json.loads(row[2]),
            "journey_steps": json.loads(row[3]),
            "medical_history": json.loads(row[4]) if row[4] else None,
        }

    def get_scenario_catalog(self) -> list[dict[str, Any]]:
        """Return lightweight scenario catalog for dashboard display."""
        rows = self._backend.execute(
            "SELECT name, description, patient_profile_json, journey_steps_json "
            "FROM scenarios ORDER BY name"
        )
        catalog: list[dict[str, Any]] = []
        for name, desc, profile_json, steps_json in rows:
            steps = json.loads(steps_json)
            catalog.append({
                "name": name,
                "description": desc,
                "patient_profile": json.loads(profile_json),
                "step_count": len(steps) if isinstance(steps, list) else 0,
            })
        return catalog

    def close(self) -> None:
        self._backend.close()
        _kafka.flush()


@lru_cache(maxsize=1)
def get_seed_db() -> NexusSeedDB:
    """Singleton access to the seed database. Seeds on first call."""
    db = NexusSeedDB()
    db.seed_all()
    return db

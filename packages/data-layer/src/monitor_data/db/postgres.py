"""
PostgreSQL client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (asyncpg, tenacity)
CALLED BY: postgres_tools.py, monitor_ui backend

Async PostgreSQL client built on asyncpg — stores structured relational data:

  system_config         Key/value app-wide configuration
  ─────────────────────────────────────────────────────────
  llm_providers         LLM provider credentials + model config
  llm_node_assignments  Which agent node uses which LLM (+ overrides)
  ─────────────────────────────────────────────────────────
  worlds                World/universe registry
  world_db_bindings     Per-world DB namespace pointers
                        (neo4j db, mongo collection prefix, qdrant coll, etc.)
  ─────────────────────────────────────────────────────────
  connection_settings   Named, saved DB connection profiles
  active_mode           Current system operation mode (singleton)
  user_preferences      Per-key JSON preferences

Schema is created automatically on first connect (idempotent DDL).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import asyncpg
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitor_data.config import settings

# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

_DB_RETRY: dict[str, Any] = dict(
    stop=stop_after_attempt(settings.db_retry_attempts),
    wait=wait_exponential(
        multiplier=1,
        min=settings.db_retry_min_wait,
        max=settings.db_retry_max_wait,
    ),
    retry=retry_if_exception_type(
        (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError)
    ),
    reraise=True,
)

# ---------------------------------------------------------------------------
# DDL — all tables created once on first connect (fully idempotent)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- ──────────────────────────────────────────────────────────────────────────
-- 1. Generic app-wide key/value store
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_config (
    key         TEXT PRIMARY KEY,
    value       TEXT        NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ──────────────────────────────────────────────────────────────────────────
-- 2. LLM providers
--    One row per named provider profile.  Multiple profiles can share the
--    same provider type (e.g. two different OpenAI keys for different envs).
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS llm_providers (
    id              TEXT PRIMARY KEY,
    name            TEXT        NOT NULL,           -- human label
    provider        TEXT        NOT NULL,           -- anthropic | openai | ollama | groq …
    model           TEXT        NOT NULL,           -- e.g. claude-sonnet-4-20250514
    api_key         TEXT        NOT NULL DEFAULT '',
    base_url        TEXT,                           -- for local / self-hosted
    -- model sampling parameters (stored as jsonb so new params need no migration)
    model_params    JSONB       NOT NULL DEFAULT '{}',
    -- e.g. {"temperature": 0.7, "max_tokens": 4096, "top_p": 0.95}
    status          TEXT        NOT NULL DEFAULT 'unconfigured',
    latency_ms      INTEGER,
    is_default      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ──────────────────────────────────────────────────────────────────────────
-- 3. LLM node assignments
--    Maps each named agent node to a specific llm_provider.
--    Nodes that have no row fall back to the is_default provider.
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS llm_node_assignments (
    node_name       TEXT PRIMARY KEY,   -- narrator | canonkeeper | resolver |
                                        -- context_assembly | indexer | orchestrator
    provider_id     TEXT        NOT NULL REFERENCES llm_providers(id)
                                    ON DELETE RESTRICT,
    -- per-node parameter overrides that take precedence over provider defaults
    param_overrides JSONB       NOT NULL DEFAULT '{}',
    notes           TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Durable audit ledger for every LLM task attempt.
CREATE TABLE IF NOT EXISTS llm_task_attempts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID,
    source_id       UUID,
    stage           TEXT        NOT NULL,
    batch_id        TEXT,
    provider_id     TEXT,
    model           TEXT,
    role            TEXT,
    attempt_no      INTEGER     NOT NULL CHECK (attempt_no >= 1),
    max_attempts    INTEGER     NOT NULL DEFAULT 1 CHECK (max_attempts >= 1),
    status          TEXT        NOT NULL,
    retryable       BOOLEAN     NOT NULL DEFAULT FALSE,
    error_class     TEXT,
    error_message   TEXT,
    backoff_ms      INTEGER,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ NOT NULL,
    request_id      TEXT,
    prompt_hash     TEXT,
    input_size      INTEGER,
    output_size     INTEGER,
    metadata        JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_llm_task_attempts_job_started
    ON llm_task_attempts (job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_task_attempts_source_started
    ON llm_task_attempts (source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_task_attempts_stage_started
    ON llm_task_attempts (stage, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_task_attempts_provider_started
    ON llm_task_attempts (provider_id, started_at DESC);

-- ──────────────────────────────────────────────────────────────────────────
-- 4. World routing registry
--    Postgres only holds the slug + DB namespace pointers.
--    The actual world definition (name, genre, entities, lore) lives in Neo4j
--    as (:Omniverse)-[:CONTAINS]->(:Multiverse)-[:CONTAINS]->(:Universe).
--    One row here per Universe node in Neo4j that this instance manages.
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS worlds (
    id              TEXT PRIMARY KEY,   -- must match the Neo4j Universe.id UUID
    label           TEXT NOT NULL,      -- denormalised display name (read from Neo4j, cached here)
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ──────────────────────────────────────────────────────────────────────────
-- 5. Per-world database bindings
--    Where to find this world's data in each backend store.
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS world_db_bindings (
    world_id            TEXT PRIMARY KEY REFERENCES worlds(id) ON DELETE CASCADE,
    -- Neo4j
    neo4j_database      TEXT NOT NULL DEFAULT 'neo4j',
                        -- Neo4j 5 supports multiple named databases per instance
    -- MongoDB
    mongodb_database    TEXT NOT NULL DEFAULT 'monitor',
    mongodb_collection_prefix TEXT NOT NULL DEFAULT '',
                        -- e.g. "lotr_" → lotr_scenes, lotr_memories …
    -- Qdrant
    qdrant_collection   TEXT NOT NULL DEFAULT 'monitor_memories',
    -- MinIO / S3
    minio_bucket        TEXT NOT NULL DEFAULT 'monitor',
    minio_prefix        TEXT NOT NULL DEFAULT '',
                        -- e.g. "forgotten-realms/" inside the bucket
    -- OpenSearch (optional)
    opensearch_index_prefix TEXT NOT NULL DEFAULT '',
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ──────────────────────────────────────────────────────────────────────────
-- 6. Active world (which world is the current session working in)
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS active_world (
    singleton   BOOLEAN PRIMARY KEY DEFAULT TRUE,
    world_id    TEXT REFERENCES worlds(id) ON DELETE SET NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT  active_world_singleton CHECK (singleton)
);

INSERT INTO active_world (singleton) VALUES (TRUE)
ON CONFLICT (singleton) DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────
-- 7. Named/saved connection profiles
--    Lets users save alternative DB endpoints by name (e.g. "prod", "staging").
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS connection_settings (
    id          TEXT PRIMARY KEY,           -- slug, e.g. "prod-neo4j"
    label       TEXT        NOT NULL,
    backend     TEXT        NOT NULL,       -- neo4j | mongodb | qdrant | minio | postgres
    host        TEXT        NOT NULL,
    port        INTEGER     NOT NULL,
    database    TEXT        NOT NULL DEFAULT '',
    username    TEXT        NOT NULL DEFAULT '',
    password    TEXT        NOT NULL DEFAULT '',
    extra       JSONB       NOT NULL DEFAULT '{}',
                -- captures backend-specific options (bolt scheme, ssl, etc.)
    is_active   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ──────────────────────────────────────────────────────────────────────────
-- 8. System operation mode (singleton row)
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS active_mode (
    singleton   BOOLEAN PRIMARY KEY DEFAULT TRUE,
    mode_id     TEXT        NOT NULL DEFAULT 'world_architect',
    context     JSONB       NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT  active_mode_singleton CHECK (singleton)
);

INSERT INTO active_mode (singleton, mode_id)
VALUES (TRUE, 'world_architect')
ON CONFLICT (singleton) DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────
-- 9. User preferences (generic JSON bag)
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_preferences (
    key         TEXT PRIMARY KEY,
    value       JSONB       NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ──────────────────────────────────────────────────────────────────────────
-- Migrations (idempotent — safe to run on existing databases)
-- ──────────────────────────────────────────────────────────────────────────

-- Add role column to llm_providers (values: light | standard | heavy).
-- See ModelRole enum in monitor_data.schemas.llm_config.
ALTER TABLE llm_providers
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'standard';

-- Add model_params + llm_node_assignments if an older schema was applied first.
ALTER TABLE llm_providers
    ADD COLUMN IF NOT EXISTS model_params JSONB NOT NULL DEFAULT '{}';

ALTER TABLE llm_providers
    ADD COLUMN IF NOT EXISTS latency_ms INTEGER;

CREATE TABLE IF NOT EXISTS llm_node_assignments (
    node_name       TEXT PRIMARY KEY,
    provider_id     TEXT        NOT NULL REFERENCES llm_providers(id)
                                    ON DELETE RESTRICT,
    param_overrides JSONB       NOT NULL DEFAULT '{}',
    notes           TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ──────────────────────────────────────────────────────────────────────────
-- RPG Ontology tables (formal typed game-mechanical data)
--
-- These tables replace the old ``properties: Dict[str, Any]`` blob pattern.
-- Each game system registers its attribute specs here.  Character sheets
-- and equipment items are stored as validated JSONB blobs (validated by the
-- Pydantic model for that system) with indexed key columns for queries.
-- ──────────────────────────────────────────────────────────────────────────

-- 10. Game system registry — one row per registered RPG system
--     ``spec`` stores the full GameSystemSpec as JSONB (meta.py format).
--     The old ``attributes``, ``resources``, ``schema_class`` columns are
--     kept for backward compatibility but should be considered deprecated;
--     use ``spec`` instead.
CREATE TABLE IF NOT EXISTS game_system_schemas (
    system_id           TEXT PRIMARY KEY,       -- e.g. "death_in_space", "dnd5e"
    system_name         TEXT NOT NULL,          -- e.g. "Death in Space"
    version             TEXT NOT NULL DEFAULT '1.0',
    description         TEXT NOT NULL DEFAULT '',
    publisher           TEXT,
    core_mechanic       TEXT NOT NULL DEFAULT '',
    attributes          JSONB NOT NULL DEFAULT '[]',  -- legacy List[AttributeSpec]
    resources           JSONB NOT NULL DEFAULT '[]',  -- legacy List[ResourceSpec]
    schema_class        TEXT NOT NULL DEFAULT '',     -- legacy Python import path
    -- Full GameSystemSpec blob (meta.py) — authoritative source
    spec                JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migration: add spec column if this table already existed without it
ALTER TABLE game_system_schemas
    ADD COLUMN IF NOT EXISTS spec JSONB;

-- 11. Character sheet index — typed character data linked to Neo4j entities
--     One row per character per world.  sheet_data is validated JSON
--     conforming to the system's BaseCharacterSheet subclass.
CREATE TABLE IF NOT EXISTS character_sheet_index (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    world_id            TEXT REFERENCES worlds(id) ON DELETE CASCADE,
    entity_id           TEXT NOT NULL,          -- Neo4j EntityInstance UUID
    system_id           TEXT NOT NULL REFERENCES game_system_schemas(system_id)
                                ON DELETE RESTRICT,
    character_name      TEXT NOT NULL,          -- denormalised for fast queries
    is_player_character BOOLEAN NOT NULL DEFAULT TRUE,
    sheet_data          JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,
    UNIQUE (entity_id, world_id)
);

CREATE INDEX IF NOT EXISTS idx_character_sheet_world
    ON character_sheet_index (world_id);
CREATE INDEX IF NOT EXISTS idx_character_sheet_system
    ON character_sheet_index (system_id);

-- 12. Equipment catalog — typed items indexed by system and type
CREATE TABLE IF NOT EXISTS equipment_catalog (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    world_id            TEXT REFERENCES worlds(id) ON DELETE CASCADE,
    system_id           TEXT NOT NULL REFERENCES game_system_schemas(system_id)
                                ON DELETE RESTRICT,
    item_name           TEXT NOT NULL,
    item_type           TEXT NOT NULL,          -- ItemType enum value
    item_data           JSONB NOT NULL DEFAULT '{}',
    source_ref          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (system_id, item_name, world_id)
);

CREATE INDEX IF NOT EXISTS idx_equipment_world_system
    ON equipment_catalog (world_id, system_id);
CREATE INDEX IF NOT EXISTS idx_equipment_type
    ON equipment_catalog (item_type);

-- 13. Character–equipment join table
CREATE TABLE IF NOT EXISTS character_equipment (
    character_sheet_id  UUID NOT NULL
                            REFERENCES character_sheet_index(id) ON DELETE CASCADE,
    item_id             UUID NOT NULL
                            REFERENCES equipment_catalog(id) ON DELETE CASCADE,
    quantity            INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 1),
    is_equipped         BOOLEAN NOT NULL DEFAULT FALSE,
    slot                TEXT,                   -- optional: "main_hand", "chest", etc.
    notes               TEXT,
    PRIMARY KEY (character_sheet_id, item_id)
);
"""


class PostgresClient:
    """
    Async PostgreSQL client for MONITOR app configuration and settings.

    Uses a connection pool internally.  All public methods are coroutines.
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        self._dsn: str = dsn or settings.postgres_dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Optional[asyncpg.Pool] = None
        self._pool_loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the connection pool and apply schema DDL (idempotent)."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if (
            self._pool is not None
            and running is not None
            and self._pool_loop is not None
            and self._pool_loop is not running
        ):
            self._pool = None
            self._pool_loop = None

        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._min_size,
                max_size=self._max_size,
            )
            self._pool_loop = running
            await self._apply_schema()

    async def close(self) -> None:
        """Close all pooled connections gracefully."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._pool_loop = None

    async def _apply_schema(self) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(_SCHEMA_SQL)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @retry(**_DB_RETRY)
    async def verify_connectivity(self) -> bool:
        """Return True if the database is reachable."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True

    # ------------------------------------------------------------------
    # system_config
    # ------------------------------------------------------------------

    async def config_get(self, key: str) -> Optional[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM system_config WHERE key = $1", key)
            return row["value"] if row else None

    async def config_set(self, key: str, value: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO system_config (key, value, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = now()
                """,
                key,
                value,
            )

    async def config_all(self) -> dict[str, str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM system_config ORDER BY key")
            return {r["key"]: r["value"] for r in rows}

    # ------------------------------------------------------------------
    # llm_providers
    # ------------------------------------------------------------------

    async def providers_list(self) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM llm_providers ORDER BY is_default DESC, created_at"
            )
            return [self._row_to_dict(r) for r in rows]

    async def provider_get(self, provider_id: str) -> Optional[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM llm_providers WHERE id = $1", provider_id)
            return self._row_to_dict(row) if row else None

    async def provider_upsert(self, provider: dict[str, Any]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO llm_providers
                    (id, name, provider, model, api_key, base_url,
                     model_params, role, status, latency_ms, is_default, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,now())
                ON CONFLICT (id) DO UPDATE SET
                    name         = EXCLUDED.name,
                    provider     = EXCLUDED.provider,
                    model        = EXCLUDED.model,
                    api_key      = EXCLUDED.api_key,
                    base_url     = EXCLUDED.base_url,
                    model_params = EXCLUDED.model_params,
                    role         = EXCLUDED.role,
                    status       = EXCLUDED.status,
                    latency_ms   = EXCLUDED.latency_ms,
                    is_default   = EXCLUDED.is_default,
                    updated_at   = now()
                """,
                provider["id"],
                provider["name"],
                provider["provider"],
                provider["model"],
                provider.get("api_key", ""),
                provider.get("base_url"),
                json.dumps(provider.get("model_params", {})),
                provider.get("role", "standard"),
                provider.get("status", "unconfigured"),
                provider.get("latency_ms"),
                bool(provider.get("is_default", False)),
            )

    async def provider_delete(self, provider_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM llm_providers WHERE id = $1", provider_id)

    async def provider_set_default(self, provider_id: str) -> None:
        """Make one provider the default and clear the flag on all others."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE llm_providers SET is_default = FALSE, updated_at = now()"
                )
                await conn.execute(
                    "UPDATE llm_providers SET is_default = TRUE, updated_at = now() WHERE id = $1",
                    provider_id,
                )

    async def provider_get_default(self) -> Optional[dict[str, Any]]:
        """Return the provider marked ``is_default = TRUE``, or None."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM llm_providers WHERE is_default = TRUE LIMIT 1")
            return self._row_to_dict(row) if row else None

    async def provider_get_by_role(self, role: str) -> Optional[dict[str, Any]]:
        """
        Return the first provider whose ``role`` column matches *role*.

        Preference order: is_default providers first, then by creation date.
        Returns None if no provider has been tagged with this role.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM llm_providers
                WHERE  role = $1
                ORDER BY is_default DESC, created_at
                LIMIT  1
                """,
                role,
            )
            return self._row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # llm_node_assignments
    # ------------------------------------------------------------------

    async def node_assignments_list(self) -> list[dict[str, Any]]:
        """Return all node→provider assignments with provider details joined."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.node_name, a.provider_id, a.param_overrides, a.notes,
                       p.name AS provider_name, p.model, p.provider
                FROM   llm_node_assignments a
                JOIN   llm_providers p ON p.id = a.provider_id
                ORDER BY a.node_name
                """
            )
            return [self._row_to_dict(r) for r in rows]

    async def node_assignment_get(self, node_name: str) -> Optional[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT a.node_name, a.provider_id, a.param_overrides, a.notes,
                       p.name AS provider_name, p.model, p.provider,
                       p.model_params, p.api_key, p.base_url
                FROM   llm_node_assignments a
                JOIN   llm_providers p ON p.id = a.provider_id
                WHERE  a.node_name = $1
                """,
                node_name,
            )
            return self._row_to_dict(row) if row else None

    async def node_assignment_set(
        self,
        node_name: str,
        provider_id: str,
        param_overrides: Optional[dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO llm_node_assignments
                    (node_name, provider_id, param_overrides, notes, updated_at)
                VALUES ($1, $2, $3::jsonb, $4, now())
                ON CONFLICT (node_name) DO UPDATE SET
                    provider_id     = EXCLUDED.provider_id,
                    param_overrides = EXCLUDED.param_overrides,
                    notes           = EXCLUDED.notes,
                    updated_at      = now()
                """,
                node_name,
                provider_id,
                json.dumps(param_overrides or {}),
                notes,
            )

    async def node_assignment_delete(self, node_name: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM llm_node_assignments WHERE node_name = $1", node_name)

    async def effective_llm_for_node(self, node_name: str) -> dict[str, Any]:
        """
        Return the effective LLM config for a node.

        Merges: provider.model_params  ←  node.param_overrides
        Falls back to the is_default provider if no assignment exists.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT p.id, p.name, p.provider, p.model, p.api_key, p.base_url,
                       p.model_params, p.role,
                       COALESCE(a.param_overrides, '{}')::jsonb AS param_overrides,
                       a.prompt_version
                FROM   llm_providers p
                LEFT JOIN llm_node_assignments a
                       ON a.provider_id = p.id AND a.node_name = $1
                WHERE  a.node_name = $1
                   OR  p.is_default
                ORDER BY (a.node_name IS NOT NULL) DESC   -- prefer explicit assignment
                LIMIT  1
                """,
                node_name,
            )
            if not row:
                raise ValueError(
                    f"No LLM provider configured (no assignment for '{node_name}' and no default)"
                )
            d = self._row_to_dict(row)
            # Merge: provider defaults + node overrides
            params = {**(d.get("model_params") or {}), **(d.get("param_overrides") or {})}
            d["effective_params"] = params
            return d

    # ------------------------------------------------------------------
    # llm_task_attempts
    # ------------------------------------------------------------------

    async def llm_task_attempt_record(self, attempt: dict[str, Any]) -> dict[str, Any]:
        """Persist one attempt-level LLM audit row for later incident review or replay."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO llm_task_attempts (
                    job_id, source_id, stage, batch_id, provider_id, model, role,
                    attempt_no, max_attempts, status, retryable, error_class,
                    error_message, backoff_ms, started_at, ended_at, request_id,
                    prompt_hash, input_size, output_size, metadata
                ) VALUES (
                    $1::uuid, $2::uuid, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17,
                    $18, $19, $20, $21::jsonb
                )
                RETURNING *
                """,
                attempt.get("job_id"),
                attempt.get("source_id"),
                attempt.get("stage", "unspecified"),
                attempt.get("batch_id"),
                attempt.get("provider_id"),
                attempt.get("model"),
                attempt.get("role"),
                int(attempt.get("attempt_no", 1)),
                int(attempt.get("max_attempts", 1)),
                attempt.get("status", "failed"),
                bool(attempt.get("retryable", False)),
                attempt.get("error_class"),
                attempt.get("error_message"),
                attempt.get("backoff_ms"),
                attempt.get("started_at"),
                attempt.get("ended_at"),
                attempt.get("request_id"),
                attempt.get("prompt_hash"),
                attempt.get("input_size"),
                attempt.get("output_size"),
                json.dumps(attempt.get("metadata", {})),
            )
            return self._row_to_dict(row)

    async def llm_task_attempts_list(
        self,
        *,
        job_id: Optional[str] = None,
        source_id: Optional[str] = None,
        stage: Optional[str] = None,
        batch_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent durable LLM attempts filtered by job, source, stage, or provider."""
        pool = await self._get_pool()
        conditions: list[str] = []
        params: list[Any] = []

        if job_id:
            params.append(job_id)
            conditions.append(f"job_id = ${len(params)}::uuid")
        if source_id:
            params.append(source_id)
            conditions.append(f"source_id = ${len(params)}::uuid")
        if stage:
            params.append(stage)
            conditions.append(f"stage = ${len(params)}")
        if batch_id:
            params.append(batch_id)
            conditions.append(f"batch_id = ${len(params)}")
        if provider_id:
            params.append(provider_id)
            conditions.append(f"provider_id = ${len(params)}")

        safe_limit = max(1, min(int(limit), 500))
        params.append(safe_limit)

        sql = "SELECT * FROM llm_task_attempts"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += f" ORDER BY started_at DESC, attempt_no DESC LIMIT ${len(params)}"

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # worlds
    # ------------------------------------------------------------------

    async def worlds_list(self, active_only: bool = False) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        sql = "SELECT * FROM worlds"
        if active_only:
            sql += " WHERE active = TRUE"
        sql += " ORDER BY name"
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
            return [self._row_to_dict(r) for r in rows]

    async def world_get(self, world_id: str) -> Optional[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM worlds WHERE id = $1", world_id)
            return self._row_to_dict(row) if row else None

    async def world_upsert(self, world: dict[str, Any]) -> None:
        """
        Register or refresh a world pointer.
        ``id`` must match the corresponding Neo4j Universe.id.
        ``label`` is a cached display name read from Neo4j — update it whenever
        the Neo4j node changes.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO worlds (id, label, active, updated_at)
                VALUES ($1,$2,$3,now())
                ON CONFLICT (id) DO UPDATE SET
                    label      = EXCLUDED.label,
                    active     = EXCLUDED.active,
                    updated_at = now()
                """,
                world["id"],
                world["label"],
                bool(world.get("active", True)),
            )

    async def world_delete(self, world_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM worlds WHERE id = $1", world_id)

    # ------------------------------------------------------------------
    # world_db_bindings
    # ------------------------------------------------------------------

    async def world_bindings_get(self, world_id: str) -> Optional[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM world_db_bindings WHERE world_id = $1", world_id
            )
            return self._row_to_dict(row) if row else None

    async def world_bindings_upsert(self, bindings: dict[str, Any]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO world_db_bindings (
                    world_id,
                    neo4j_database,
                    mongodb_database,
                    mongodb_collection_prefix,
                    qdrant_collection,
                    minio_bucket,
                    minio_prefix,
                    opensearch_index_prefix,
                    updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,now())
                ON CONFLICT (world_id) DO UPDATE SET
                    neo4j_database            = EXCLUDED.neo4j_database,
                    mongodb_database          = EXCLUDED.mongodb_database,
                    mongodb_collection_prefix = EXCLUDED.mongodb_collection_prefix,
                    qdrant_collection         = EXCLUDED.qdrant_collection,
                    minio_bucket              = EXCLUDED.minio_bucket,
                    minio_prefix              = EXCLUDED.minio_prefix,
                    opensearch_index_prefix   = EXCLUDED.opensearch_index_prefix,
                    updated_at                = now()
                """,
                bindings["world_id"],
                bindings.get("neo4j_database", "neo4j"),
                bindings.get("mongodb_database", "monitor"),
                bindings.get("mongodb_collection_prefix", ""),
                bindings.get("qdrant_collection", "monitor_memories"),
                bindings.get("minio_bucket", "monitor"),
                bindings.get("minio_prefix", ""),
                bindings.get("opensearch_index_prefix", ""),
            )

    async def world_full_get(self, world_id: str) -> Optional[dict[str, Any]]:
        """Return a world row joined with its DB bindings."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT w.*, b.neo4j_database, b.mongodb_database,
                       b.mongodb_collection_prefix, b.qdrant_collection,
                       b.minio_bucket, b.minio_prefix, b.opensearch_index_prefix
                FROM   worlds w
                LEFT   JOIN world_db_bindings b ON b.world_id = w.id
                WHERE  w.id = $1
                """,
                world_id,
            )
            return self._row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # active_world
    # ------------------------------------------------------------------

    async def active_world_get(self) -> Optional[dict[str, Any]]:
        """Return the currently active world with its DB bindings, or None."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT w.*, b.neo4j_database, b.mongodb_database,
                       b.mongodb_collection_prefix, b.qdrant_collection,
                       b.minio_bucket, b.minio_prefix, b.opensearch_index_prefix
                FROM   active_world aw
                JOIN   worlds w ON w.id = aw.world_id
                LEFT   JOIN world_db_bindings b ON b.world_id = w.id
                WHERE  aw.singleton = TRUE
                """
            )
            return self._row_to_dict(row) if row else None

    async def active_world_set(self, world_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE active_world
                SET world_id = $1, updated_at = now()
                WHERE singleton = TRUE
                """,
                world_id,
            )

    # ------------------------------------------------------------------
    # connection_settings
    # ------------------------------------------------------------------

    async def connections_list(self, backend: Optional[str] = None) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if backend:
                rows = await conn.fetch(
                    "SELECT * FROM connection_settings WHERE backend = $1 ORDER BY label",
                    backend,
                )
            else:
                rows = await conn.fetch("SELECT * FROM connection_settings ORDER BY backend, label")
            return [self._row_to_dict(r) for r in rows]

    async def connection_upsert(self, conn_def: dict[str, Any]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO connection_settings
                    (id, label, backend, host, port, database,
                     username, password, extra, is_active, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,now())
                ON CONFLICT (id) DO UPDATE SET
                    label      = EXCLUDED.label,
                    backend    = EXCLUDED.backend,
                    host       = EXCLUDED.host,
                    port       = EXCLUDED.port,
                    database   = EXCLUDED.database,
                    username   = EXCLUDED.username,
                    password   = EXCLUDED.password,
                    extra      = EXCLUDED.extra,
                    is_active  = EXCLUDED.is_active,
                    updated_at = now()
                """,
                conn_def["id"],
                conn_def["label"],
                conn_def["backend"],
                conn_def["host"],
                int(conn_def["port"]),
                conn_def.get("database", ""),
                conn_def.get("username", ""),
                conn_def.get("password", ""),
                json.dumps(conn_def.get("extra", {})),
                bool(conn_def.get("is_active", False)),
            )

    async def connection_activate(self, conn_id: str, backend: str) -> None:
        """Set one connection as active for a backend, deactivating all others of the same backend."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE connection_settings SET is_active = FALSE, updated_at = now() WHERE backend = $1",
                    backend,
                )
                await conn.execute(
                    "UPDATE connection_settings SET is_active = TRUE, updated_at = now() WHERE id = $1",
                    conn_id,
                )

    async def connection_delete(self, conn_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM connection_settings WHERE id = $1", conn_id)

    # ------------------------------------------------------------------
    # active_mode
    # ------------------------------------------------------------------

    async def mode_get(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT mode_id, context FROM active_mode")
            return {"mode_id": row["mode_id"], "context": dict(row["context"])}

    async def mode_set(self, mode_id: str, context: Optional[dict[str, Any]] = None) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE active_mode
                SET mode_id = $1, context = $2::jsonb, updated_at = now()
                WHERE singleton = TRUE
                """,
                mode_id,
                json.dumps(context or {}),
            )

    # ------------------------------------------------------------------
    # user_preferences
    # ------------------------------------------------------------------

    async def pref_get(self, key: str) -> Optional[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM user_preferences WHERE key = $1", key)
            return dict(row["value"]) if row else None

    async def pref_set(self, key: str, value: dict[str, Any]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_preferences (key, value, updated_at)
                VALUES ($1, $2::jsonb, now())
                ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = now()
                """,
                key,
                json.dumps(value),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_pool(self) -> asyncpg.Pool:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if (
            self._pool is not None
            and running is not None
            and self._pool_loop is not None
            and self._pool_loop is not running
        ):
            self._pool = None
            self._pool_loop = None

        if self._pool is None:
            await self.connect()
        if self._pool is None:
            raise RuntimeError("PostgreSQL pool not initialized")
        return self._pool

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        """Convert an asyncpg Record to a plain dict, expanding JSONB fields."""
        import json as _json

        d = dict(row)
        for k, v in d.items():
            # asyncpg returns JSONB as str unless a type codec is registered.
            # Deserialise JSON strings for known JSONB columns defensively.
            if isinstance(v, str) and v and v[0] in ("{", "[", '"'):
                try:
                    parsed = _json.loads(v)
                    if isinstance(parsed, (dict, list)):
                        d[k] = parsed
                except (ValueError, TypeError):
                    pass
            # Timestamps → ISO strings for easy JSON serialisation downstream.
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        return d


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_postgres_client: Optional[PostgresClient] = None


def get_postgres_client() -> PostgresClient:
    """Return (or create) the module-level PostgreSQL client singleton."""
    global _postgres_client
    if _postgres_client is None:
        _postgres_client = PostgresClient()
    return _postgres_client

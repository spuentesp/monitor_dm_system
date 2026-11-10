"""Multi-tenancy additions to PostgresClient.

Covers the Phase 6 surface:
- provider API-key encryption at rest (Fernet, env-keyed, plaintext fallback)
- per-user daily usage recording and quota-limit overrides
- the per-user Conversatory marker on the ``worlds`` ownership registry

All tests use the mocked-asyncpg-pool pattern from ``test_postgres.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

import monitor_data.db.postgres as pg
from monitor_data.db.postgres import (
    PostgresClient,
    decrypt_provider_api_key,
    encrypt_provider_api_key,
    provider_key_encryption_enabled,
)


@pytest.fixture(autouse=True)
def reset_singleton_and_env(monkeypatch: pytest.MonkeyPatch):
    pg._postgres_client = None
    pg._fernet_cache = None
    pg._fernet_cache_key = None
    pg._plaintext_warning_emitted = False
    monkeypatch.delenv(pg.PROVIDER_KEY_ENV, raising=False)
    yield
    pg._fernet_cache = None
    pg._fernet_cache_key = None
    pg._plaintext_warning_emitted = False


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=ctx)
    pool.close = AsyncMock()
    return pool, conn


@pytest.fixture
def client(mock_pool):
    pool, conn = mock_pool
    c = PostgresClient(dsn="postgresql://test:test@localhost/test")
    c._pool = pool
    return c, conn


@pytest.fixture
def fernet_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv(pg.PROVIDER_KEY_ENV, key)
    pg._fernet_cache = None
    pg._fernet_cache_key = None
    return key


# ---------------------------------------------------------------------------
# Provider API-key encryption
# ---------------------------------------------------------------------------


class TestProviderKeyEncryption:
    def test_round_trip(self, fernet_key: str) -> None:
        secret = "sk-live-do-not-log-me"
        stored = encrypt_provider_api_key(secret)
        assert stored != secret
        assert secret not in stored
        assert decrypt_provider_api_key(stored) == secret

    def test_encrypt_is_idempotent(self, fernet_key: str) -> None:
        once = encrypt_provider_api_key("sk-a")
        assert encrypt_provider_api_key(once) == once

    def test_plaintext_mode_passthrough(self) -> None:
        assert provider_key_encryption_enabled() is False
        assert encrypt_provider_api_key("sk-plain") == "sk-plain"
        assert decrypt_provider_api_key("sk-plain") == "sk-plain"

    def test_legacy_plaintext_rows_stay_readable_with_key_set(self, fernet_key: str) -> None:
        assert decrypt_provider_api_key("sk-legacy-plaintext") == "sk-legacy-plaintext"

    def test_empty_value_passthrough(self, fernet_key: str) -> None:
        assert encrypt_provider_api_key("") == ""
        assert decrypt_provider_api_key("") == ""

    def test_warning_flag_not_raised_when_key_set(self, fernet_key: str) -> None:
        encrypt_provider_api_key("sk-x")
        assert pg._plaintext_warning_emitted is False

    def test_plaintext_mode_warns_once(self) -> None:
        encrypt_provider_api_key("sk-x")
        encrypt_provider_api_key("sk-y")
        assert pg._plaintext_warning_emitted is True


class TestProviderRowCrypto:
    @pytest.mark.asyncio
    async def test_provider_upsert_stores_ciphertext(self, client, fernet_key: str) -> None:
        c, conn = client
        secret = "sk-live-abc123"
        await c.provider_upsert(
            {
                "id": "p1",
                "name": "P",
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": secret,
            }
        )
        sql, *params = conn.execute.call_args.args
        assert "INSERT INTO llm_providers" in sql
        assert secret not in params
        assert decrypt_provider_api_key(params[4]) == secret

    @pytest.mark.asyncio
    async def test_provider_get_returns_plaintext(self, client, fernet_key: str) -> None:
        c, conn = client
        conn.fetchrow = AsyncMock(
            return_value={
                "id": "p1",
                "name": "P",
                "api_key": encrypt_provider_api_key("sk-live-xyz"),
            }
        )
        row = await c.provider_get("p1")
        assert row is not None
        assert row["api_key"] == "sk-live-xyz"

    @pytest.mark.asyncio
    async def test_provider_round_trip_keeps_key_stable(self, client, fernet_key: str) -> None:
        """status-only updates re-encrypt the same plaintext to a stable value."""
        c, conn = client
        conn.fetchrow = AsyncMock(return_value={"id": "p1", "api_key": encrypt_provider_api_key("sk-round")})
        row = await c.provider_get("p1")
        await c.provider_upsert({**row, "name": "P", "provider": "openai", "model": "m"})
        _, *params = conn.execute.call_args.args
        assert decrypt_provider_api_key(params[4]) == "sk-round"


# ---------------------------------------------------------------------------
# Usage + quota
# ---------------------------------------------------------------------------


class TestUsage:
    @pytest.mark.asyncio
    async def test_usage_record_binds_counts(self, client) -> None:
        c, conn = client
        uid = uuid4()
        await c.usage_record(uid, tokens=42, calls=1)
        sql, *params = conn.fetchrow.call_args.args
        assert "INSERT INTO user_usage_daily" in sql
        assert "ON CONFLICT (user_id, usage_day)" in sql
        assert params[0] == uid
        assert params[1] == 42
        assert params[2] == 1

    @pytest.mark.asyncio
    async def test_usage_get_reads_current_day(self, client) -> None:
        c, conn = client
        uid = uuid4()
        conn.fetchrow = AsyncMock(return_value={"tokens": 7, "calls": 3})
        row = await c.usage_get(uid)
        sql, *params = conn.fetchrow.call_args.args
        assert "FROM   user_usage_daily" in sql
        assert params[0] == uid
        assert row == {"tokens": 7, "calls": 3}

    @pytest.mark.asyncio
    async def test_usage_limit_set_upserts_override(self, client) -> None:
        c, conn = client
        uid = uuid4()
        await c.usage_limit_set(uid, daily_token_cap=1000, daily_call_cap=10, exempt=False)
        sql, *params = conn.fetchrow.call_args.args
        assert "INSERT INTO user_usage_limits" in sql
        assert params[0] == uid
        assert params[1] == 1000
        assert params[2] == 10

    @pytest.mark.asyncio
    async def test_usage_limit_get_returns_row_or_none(self, client) -> None:
        c, conn = client
        uid = uuid4()
        assert await c.usage_limit_get(uid) is None
        conn.fetchrow = AsyncMock(
            return_value={"user_id": uid, "daily_token_cap": None, "daily_call_cap": 5, "exempt": False}
        )
        row = await c.usage_limit_get(uid)
        assert row is not None and row["daily_call_cap"] == 5

    @pytest.mark.asyncio
    async def test_usage_admin_summary_joins_users(self, client) -> None:
        c, conn = client
        conn.fetch = AsyncMock(return_value=[{"user_id": uuid4(), "calls": 2}])
        rows = await c.usage_admin_summary(limit=5)
        sql, *params = conn.fetch.call_args.args
        assert "FROM   users" in sql and "user_usage_daily" in sql
        assert params == [5]
        assert rows == [{"user_id": rows[0]["user_id"], "calls": 2}]


# ---------------------------------------------------------------------------
# Conversatory registry marker
# ---------------------------------------------------------------------------


class TestConversatoryRegistry:
    @pytest.mark.asyncio
    async def test_world_upsert_binds_kind(self, client) -> None:
        c, conn = client
        await c.world_upsert(
            {"id": "w1", "owner_id": uuid4(), "multiverse_id": "m1", "label": "Conversatory", "kind": "conversatory"}
        )
        sql, *params = conn.execute.call_args.args
        assert "kind" in sql
        assert params[5] == "conversatory"

    @pytest.mark.asyncio
    async def test_world_upsert_without_kind_preserves_marker(self, client) -> None:
        c, conn = client
        await c.world_upsert({"id": "w1", "label": "X"})
        _, *params = conn.execute.call_args.args
        assert params[5] is None
        sql = conn.execute.call_args.args[0]
        assert "COALESCE($6, worlds.kind)" in sql

    @pytest.mark.asyncio
    async def test_world_get_conversatory_filters_by_owner_and_kind(self, client) -> None:
        c, conn = client
        uid = uuid4()
        conn.fetchrow = AsyncMock(return_value={"id": "w1", "owner_id": uid, "kind": "conversatory"})
        row = await c.world_get_conversatory(uid)
        sql, *params = conn.fetchrow.call_args.args
        assert "kind = 'conversatory'" in sql
        assert params == [uid]
        assert row is not None and row["id"] == "w1"


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------


class TestSchema:
    def test_migrations_create_usage_tables_and_kind_column(self) -> None:
        ddl = "\n".join(sql for _, sql in pg._MIGRATIONS)
        assert "CREATE TABLE IF NOT EXISTS user_usage_daily" in ddl
        assert "CREATE TABLE IF NOT EXISTS user_usage_limits" in ddl
        assert "ALTER TABLE worlds ADD COLUMN IF NOT EXISTS kind" in ddl

    @pytest.mark.asyncio
    async def test_connect_applies_migrations(self, mock_pool) -> None:
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)  # no applied checksums
        with patch("monitor_data.db.postgres.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
            c = PostgresClient(dsn="postgresql://test")
            await c.connect()
        executed = "\n".join(call.args[0] for call in conn.execute.call_args_list)
        assert "user_usage_daily" in executed

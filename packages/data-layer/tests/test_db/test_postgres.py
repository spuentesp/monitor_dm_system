"""
Unit tests for PostgreSQL client.

Covers all PostgresClient public methods with mocked asyncpg pool.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_data.db.postgres import PostgresClient, get_postgres_client

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton before each test."""
    import monitor_data.db.postgres as _pg

    _pg._postgres_client = None


@pytest.fixture
def mock_pool():
    """Return a mocked asyncpg pool with async context-manager connections."""
    pool = AsyncMock()
    conn = AsyncMock()
    # Mock transaction as async context manager
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    # Make pool.acquire() return an async context manager
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=ctx)
    pool.close = AsyncMock()
    return pool, conn


@pytest.fixture
def client(mock_pool):
    """Return a PostgresClient with pre-mocked pool."""
    pool, conn = mock_pool
    c = PostgresClient(dsn="postgresql://test:test@localhost/test")
    c._pool = pool
    return c, conn


# =============================================================================
# CONNECTION LIFECYCLE
# =============================================================================


@pytest.mark.asyncio
async def test_connect_creates_pool_and_applies_schema(mock_pool):
    pool, conn = mock_pool
    with patch("monitor_data.db.postgres.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
        c = PostgresClient(dsn="postgresql://test")
        await c.connect()
    assert c._pool is pool
    pool.acquire.assert_called()
    conn.execute.assert_called()
    # schema applied (first call is schema DDL)
    assert "CREATE TABLE" in conn.execute.call_args_list[0][0][0]


@pytest.mark.asyncio
async def test_connect_skips_if_pool_exists(mock_pool):
    pool, conn = mock_pool
    c = PostgresClient(dsn="postgresql://test")
    c._pool = pool
    with patch("monitor_data.db.postgres.asyncpg.create_pool", new=AsyncMock()) as mock_create:
        await c.connect()
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_close_pool(client):
    c, _ = client
    await c.close()
    assert c._pool is None


@pytest.mark.asyncio
async def test_get_pool_auto_connects(mock_pool):
    pool, conn = mock_pool
    with patch("monitor_data.db.postgres.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
        c = PostgresClient(dsn="postgresql://test")
        c._pool = None
        result = await c._get_pool()
    assert result is pool


# =============================================================================
# HEALTH CHECK
# =============================================================================


@pytest.mark.asyncio
async def test_verify_connectivity_success(client):
    c, conn = client
    conn.fetchval = AsyncMock(return_value=1)
    assert await c.verify_connectivity() is True
    conn.fetchval.assert_called_once_with("SELECT 1")


# =============================================================================
# SYSTEM CONFIG
# =============================================================================


@pytest.mark.asyncio
async def test_config_get_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"value": "bar"})
    assert await c.config_get("foo") == "bar"


@pytest.mark.asyncio
async def test_config_get_not_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value=None)
    assert await c.config_get("foo") is None


@pytest.mark.asyncio
async def test_config_set(client):
    c, conn = client
    await c.config_set("foo", "bar")
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO system_config" in sql
    assert "ON CONFLICT" in sql


@pytest.mark.asyncio
async def test_config_all(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[{"key": "a", "value": "1"}, {"key": "b", "value": "2"}])
    result = await c.config_all()
    assert result == {"a": "1", "b": "2"}


# =============================================================================
# LLM PROVIDERS
# =============================================================================


@pytest.mark.asyncio
async def test_providers_list(client):
    c, conn = client
    conn.fetch = AsyncMock(
        return_value=[
            {"id": "p1", "name": "OpenAI", "is_default": True},
        ]
    )
    result = await c.providers_list()
    assert len(result) == 1
    assert result[0]["id"] == "p1"


@pytest.mark.asyncio
async def test_provider_get_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"id": "p1", "name": "OpenAI"})
    result = await c.provider_get("p1")
    assert result["id"] == "p1"


@pytest.mark.asyncio
async def test_provider_get_not_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value=None)
    assert await c.provider_get("p1") is None


@pytest.mark.asyncio
async def test_provider_upsert(client):
    c, conn = client
    await c.provider_upsert(
        {
            "id": "p1",
            "name": "OpenAI",
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "sk-test",
        }
    )
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO llm_providers" in sql


@pytest.mark.asyncio
async def test_provider_delete(client):
    c, conn = client
    await c.provider_delete("p1")
    conn.execute.assert_called_once()
    assert "DELETE FROM llm_providers" in conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_provider_set_default(client):
    c, conn = client
    await c.provider_set_default("p1")
    assert conn.execute.call_count == 2
    calls = [conn.execute.call_args_list[i][0][0] for i in range(2)]
    assert any("is_default = FALSE" in c for c in calls)
    assert any("is_default = TRUE" in c for c in calls)


@pytest.mark.asyncio
async def test_provider_get_default_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"id": "p1", "is_default": True})
    result = await c.provider_get_default()
    assert result is not None


@pytest.mark.asyncio
async def test_provider_get_default_not_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value=None)
    assert await c.provider_get_default() is None


@pytest.mark.asyncio
async def test_provider_get_by_role(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"id": "p1", "role": "narrator"})
    result = await c.provider_get_by_role("narrator")
    assert result["id"] == "p1"


# =============================================================================
# LLM NODE ASSIGNMENTS
# =============================================================================


@pytest.mark.asyncio
async def test_node_assignments_list(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[{"node_name": "narrator", "provider_id": "p1"}])
    result = await c.node_assignments_list()
    assert len(result) == 1


@pytest.mark.asyncio
async def test_node_assignment_get_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"node_name": "narrator", "provider_id": "p1"})
    result = await c.node_assignment_get("narrator")
    assert result["node_name"] == "narrator"


@pytest.mark.asyncio
async def test_node_assignment_set(client):
    c, conn = client
    await c.node_assignment_set("narrator", "p1", param_overrides={"temperature": 0.7})
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO llm_node_assignments" in sql


@pytest.mark.asyncio
async def test_node_assignment_delete(client):
    c, conn = client
    await c.node_assignment_delete("narrator")
    assert "DELETE FROM llm_node_assignments" in conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_effective_llm_for_node_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(
        return_value={
            "id": "p1",
            "name": "OpenAI",
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "",
            "base_url": None,
            "model_params": '{"temperature": 0.5}',
            "role": "standard",
            "param_overrides": '{"temperature": 0.9}',
        }
    )
    result = await c.effective_llm_for_node("narrator")
    assert result["effective_params"]["temperature"] == 0.9


@pytest.mark.asyncio
async def test_effective_llm_for_node_missing_raises(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="No LLM provider configured"):
        await c.effective_llm_for_node("narrator")


# =============================================================================
# LLM TASK ATTEMPTS
# =============================================================================


@pytest.mark.asyncio
async def test_llm_task_attempt_record(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"id": "attempt-1", "status": "success"})
    result = await c.llm_task_attempt_record(
        {
            "job_id": "job-1",
            "stage": "generation",
            "attempt_no": 1,
            "status": "success",
            "max_attempts": 3,
            "retryable": False,
        }
    )
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_llm_task_attempts_list_no_filters(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[{"id": "a1"}, {"id": "a2"}])
    result = await c.llm_task_attempts_list()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_llm_task_attempts_list_with_filters(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[])
    await c.llm_task_attempts_list(job_id="job-1", stage="gen", limit=50)
    sql = conn.fetch.call_args[0][0]
    assert "job_id = $1::uuid" in sql
    assert "stage = $2" in sql
    assert "LIMIT $3" in sql


# =============================================================================
# WORLDS
# =============================================================================


@pytest.mark.asyncio
async def test_worlds_list(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[{"id": "w1", "name": "Test World"}])
    result = await c.worlds_list()
    assert len(result) == 1


@pytest.mark.asyncio
async def test_worlds_list_active_only(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[])
    await c.worlds_list(active_only=True)
    sql = conn.fetch.call_args[0][0]
    assert "WHERE active = TRUE" in sql


@pytest.mark.asyncio
async def test_world_get_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"id": "w1", "label": "World 1"})
    result = await c.world_get("w1")
    assert result["id"] == "w1"


@pytest.mark.asyncio
async def test_world_get_not_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value=None)
    assert await c.world_get("w1") is None


@pytest.mark.asyncio
async def test_world_upsert(client):
    c, conn = client
    await c.world_upsert({"id": "w1", "label": "World 1", "active": True})
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO worlds" in sql


@pytest.mark.asyncio
async def test_world_delete(client):
    c, conn = client
    await c.world_delete("w1")
    assert "DELETE FROM worlds" in conn.execute.call_args[0][0]


# =============================================================================
# WORLD DB BINDINGS
# =============================================================================


@pytest.mark.asyncio
async def test_world_bindings_get_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"world_id": "w1", "neo4j_database": "neo4j"})
    result = await c.world_bindings_get("w1")
    assert result["neo4j_database"] == "neo4j"


@pytest.mark.asyncio
async def test_world_bindings_upsert(client):
    c, conn = client
    await c.world_bindings_upsert({"world_id": "w1"})
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO world_db_bindings" in sql


@pytest.mark.asyncio
async def test_world_full_get_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"id": "w1", "label": "W", "neo4j_database": "n"})
    result = await c.world_full_get("w1")
    assert result["neo4j_database"] == "n"


# =============================================================================
# ACTIVE WORLD
# =============================================================================


@pytest.mark.asyncio
async def test_active_world_get_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"id": "w1", "label": "Active"})
    result = await c.active_world_get()
    assert result["id"] == "w1"


@pytest.mark.asyncio
async def test_active_world_get_not_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value=None)
    assert await c.active_world_get() is None


@pytest.mark.asyncio
async def test_active_world_set(client):
    c, conn = client
    await c.active_world_set("w1")
    assert "UPDATE active_world" in conn.execute.call_args[0][0]


# =============================================================================
# CONNECTION SETTINGS
# =============================================================================


@pytest.mark.asyncio
async def test_connections_list_all(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[{"id": "c1"}])
    result = await c.connections_list()
    assert len(result) == 1


@pytest.mark.asyncio
async def test_connections_list_by_backend(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[])
    await c.connections_list(backend="postgres")
    assert "WHERE backend = $1" in conn.fetch.call_args[0][0]


@pytest.mark.asyncio
async def test_connection_upsert(client):
    c, conn = client
    await c.connection_upsert(
        {
            "id": "c1",
            "label": "Prod",
            "backend": "postgres",
            "host": "db.example.com",
            "port": 5432,
        }
    )
    assert "INSERT INTO connection_settings" in conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_connection_activate(client):
    c, conn = client
    await c.connection_activate("c1", "postgres")
    assert conn.execute.call_count == 2
    calls = [conn.execute.call_args_list[i][0][0] for i in range(2)]
    assert any("is_active = FALSE" in c for c in calls)
    assert any("is_active = TRUE" in c for c in calls)


@pytest.mark.asyncio
async def test_connection_delete(client):
    c, conn = client
    await c.connection_delete("c1")
    assert "DELETE FROM connection_settings" in conn.execute.call_args[0][0]


# =============================================================================
# ACTIVE MODE
# =============================================================================


@pytest.mark.asyncio
async def test_mode_get(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"mode_id": "play", "context": {"session": "s1"}})
    result = await c.mode_get()
    assert result["mode_id"] == "play"


@pytest.mark.asyncio
async def test_mode_set(client):
    c, conn = client
    await c.mode_set("play", context={"session": "s1"})
    assert "UPDATE active_mode" in conn.execute.call_args[0][0]


# =============================================================================
# USER PREFERENCES
# =============================================================================


@pytest.mark.asyncio
async def test_pref_get_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value={"value": {"theme": "dark"}})
    result = await c.pref_get("ui")
    assert result["theme"] == "dark"


@pytest.mark.asyncio
async def test_pref_get_not_found(client):
    c, conn = client
    conn.fetchrow = AsyncMock(return_value=None)
    assert await c.pref_get("ui") is None


@pytest.mark.asyncio
async def test_pref_set(client):
    c, conn = client
    await c.pref_set("ui", {"theme": "light"})
    assert "INSERT INTO user_preferences" in conn.execute.call_args[0][0]


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


@pytest.mark.asyncio
async def test_row_to_dict_parses_jsonb():
    from types import SimpleNamespace

    row = SimpleNamespace()

    # asyncpg Record.__getitem__ behaves like a dict
    # We mock by using a simple dict-like object
    class FakeRow:
        def __init__(self, data):
            self._data = data

        def __getitem__(self, k):
            return self._data[k]

        def __iter__(self):
            return iter(self._data.keys())

        def keys(self):
            return self._data.keys()

    row = FakeRow({"id": "1", "model_params": '{"t": 0.7}', "created_at": None})
    result = PostgresClient._row_to_dict(row)
    assert result["model_params"] == {"t": 0.7}


def test_get_postgres_client_singleton():
    c1 = get_postgres_client()
    c2 = get_postgres_client()
    assert c1 is c2

"""The idempotent pre-auth ownership backfill.

Rows created before the ownership registry existed carry no owner, so only
the local account can reach them. The backfill claims them permanently —
and running it twice changes nothing the second time.

Uses the mocked-asyncpg-pool pattern from ``test_postgres.py``.

Run:
    uv run pytest packages/data-layer/tests/test_db/test_ownership_backfill.py -q
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from monitor_data.db.postgres import PostgresClient


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
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


class TestOwnershipBackfill:
    async def test_the_unowned_rows_are_claimed(self, client) -> None:
        c, conn = client
        conn.execute = AsyncMock(side_effect=["UPDATE 3", "UPDATE 1"])

        claimed = await c.ownership_backfill(uuid4())

        assert claimed == {"worlds": 3, "multiverses": 1}

    async def test_only_rows_without_an_owner_are_touched(self, client) -> None:
        c, conn = client
        conn.execute = AsyncMock(side_effect=["UPDATE 0", "UPDATE 0"])

        claimed = await c.ownership_backfill(uuid4())

        # A second run has nothing left to claim: the WHERE clause only
        # matches rows that still have no owner.
        assert claimed == {"worlds": 0, "multiverses": 0}
        for call in conn.execute.await_args_list:
            assert "owner_id IS NULL" in call.args[0]

    async def test_a_row_with_another_owner_is_left_alone(self, client) -> None:
        c, conn = client
        conn.execute = AsyncMock(side_effect=["UPDATE 0", "UPDATE 0"])

        await c.ownership_backfill(uuid4())

        for call in conn.execute.await_args_list:
            assert "SET owner_id" in call.args[0]
            # No "owner_id IS NOT NULL" clause that would steal rows.
            assert "IS NOT NULL" not in call.args[0]

"""Setup paths that only run against a fresh environment."""

from __future__ import annotations

import asyncio
import importlib.util
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_data.db.neo4j import Neo4jClient

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "seed_ollama_embedding_provider.py"


def test_neo4j_health_probe_works_before_the_first_query():
    client = Neo4jClient.__new__(Neo4jClient)
    client._driver = None
    client._uri, client._user, client.password = "bolt://x", "neo4j", "pw"
    driver = MagicMock()
    driver.verify_connectivity = AsyncMock()

    with patch("monitor_data.db.neo4j.AsyncGraphDatabase.driver", return_value=driver) as make:
        assert asyncio.run(client.verify_connectivity()) is True

    make.assert_called_once_with("bolt://x", auth=("neo4j", "pw"))


def test_neo4j_health_probe_still_reports_an_unreachable_server():
    client = Neo4jClient.__new__(Neo4jClient)
    client._driver = None
    client._uri, client._user, client.password = "bolt://x", "neo4j", "pw"
    driver = MagicMock()
    driver.verify_connectivity = AsyncMock(side_effect=OSError("refused"))

    with patch("monitor_data.db.neo4j.AsyncGraphDatabase.driver", return_value=driver):
        assert asyncio.run(client.verify_connectivity()) is False


class _Conn:
    def __init__(self, existing: list[dict[str, Any]]) -> None:
        self.existing = existing
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, _sql: str) -> list[dict[str, Any]]:
        return self.existing

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append((" ".join(sql.split()), args))
        return "OK"

    async def close(self) -> None:
        pass


def _run_seed(conn: _Conn) -> None:
    spec = importlib.util.spec_from_file_location("seed_ollama_embedding_provider", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    checker = MagicMock()
    checker.return_value.verify = AsyncMock(
        return_value=types.SimpleNamespace(healthy=True, detail="ok", vector_dim=768)
    )
    with (
        patch("asyncpg.connect", new=AsyncMock(return_value=conn)),
        patch("monitor_data.retrieval.embedding_health.EmbeddingHealthChecker", checker),
    ):
        asyncio.run(module._seed("nomic-embed-text:latest", "http://localhost:11434"))


def test_seed_on_a_fresh_database_inserts_a_usable_default_row():
    conn = _Conn(existing=[])
    _run_seed(conn)

    sql, args = next((s, a) for s, a in conn.executed if s.startswith("INSERT INTO llm_providers"))
    columns = sql.split("(", 1)[1].split(")", 1)[0].replace(" ", "").split(",")
    assert columns[0] == "id"
    assert "ollama-embedding" in args or "'ollama-embedding'" in sql
    # The pair sync needs an embedding default; a fresh row must be it.
    assert "true, 'embedding'" in sql.lower()


@pytest.mark.parametrize("has_default", [False, True])
def test_seed_on_existing_rows_leaves_exactly_one_default(has_default: bool):
    conn = _Conn(existing=[{"id": "a", "model": "m", "provider": "p", "is_default": has_default}])
    _run_seed(conn)

    made_default = [a for s, a in conn.executed if "SET is_default=TRUE" in s]
    assert made_default == ([] if has_default else [("a",)])

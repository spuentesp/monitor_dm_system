"""The Neo4j status probe must work on a stack without the APOC plugin."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from monitor_ui.routers import databases
import pytest


pytestmark = pytest.mark.usefixtures("local_auth_mode")


def _driver(record: dict[str, Any]) -> tuple[MagicMock, list[str]]:
    queries: list[str] = []
    result = MagicMock()
    result.single = AsyncMock(return_value=record)

    async def run(query: str, *_args: Any, **_kwargs: Any) -> Any:
        queries.append(query)
        return result

    session = MagicMock()
    session.run = run
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session.return_value = session
    driver.close = AsyncMock()
    return driver, queries


def test_probe_reports_counts_without_apoc():
    driver, queries = _driver({"nodeCount": 5, "relCount": 4, "labelCount": 18})
    with patch("neo4j.AsyncGraphDatabase.driver", return_value=driver):
        status = asyncio.run(databases._probe_neo4j())

    assert status.status == "online"
    assert status.stats == {"nodes": 5, "relationships": 4, "labels": 18}
    assert all("apoc" not in q.lower() for q in queries)

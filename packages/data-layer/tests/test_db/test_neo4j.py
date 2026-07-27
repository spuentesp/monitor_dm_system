"""
Unit tests for Neo4j client.

Tests cover:
- Neo4jClient initialization
- Password requirement enforcement
- Connection management
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_data.db.neo4j import Neo4jClient


def test_neo4j_client_requires_password():
    """Test that Neo4jClient raises error when password is not provided."""
    # Clear password env var if it exists
    original_password = os.environ.get("NEO4J_PASSWORD")
    if "NEO4J_PASSWORD" in os.environ:
        del os.environ["NEO4J_PASSWORD"]

    try:
        with pytest.raises(ValueError, match="Neo4j password is required"):
            Neo4jClient()
    finally:
        # Restore original password
        if original_password:
            os.environ["NEO4J_PASSWORD"] = original_password


def test_neo4j_client_accepts_explicit_password():
    """Test that Neo4jClient works with explicit password parameter."""
    # Clear password env var
    original_password = os.environ.get("NEO4J_PASSWORD")
    if "NEO4J_PASSWORD" in os.environ:
        del os.environ["NEO4J_PASSWORD"]

    try:
        client = Neo4jClient(password="explicit_password")
        assert client.password == "explicit_password"
    finally:
        # Restore original password
        if original_password:
            os.environ["NEO4J_PASSWORD"] = original_password


def test_neo4j_client_uses_env_password():
    """Test that Neo4jClient uses password from environment variable."""
    os.environ["NEO4J_PASSWORD"] = "env_password"

    client = Neo4jClient()
    assert client.password == "env_password"


def test_neo4j_client_explicit_overrides_env():
    """Test that explicit password parameter overrides environment variable."""
    os.environ["NEO4J_PASSWORD"] = "env_password"

    client = Neo4jClient(password="explicit_password")
    assert client.password == "explicit_password"


def test_neo4j_client_execute_read_auto_connects():
    """execute_read should connect without deadlocking the background loop."""
    os.environ["NEO4J_PASSWORD"] = "test_password"

    mock_session = AsyncMock()
    mock_session.execute_write = AsyncMock()
    mock_session.execute_read = AsyncMock(return_value=[{"value": 1}])

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session

    mock_driver = AsyncMock()
    mock_driver.session = MagicMock(return_value=mock_ctx)

    with patch("monitor_data.db.neo4j.AsyncGraphDatabase.driver", return_value=mock_driver):
        client = Neo4jClient()
        assert client.execute_read("RETURN 1") == [{"value": 1}]

    # Schema bootstrap now runs one write per statement (resilient bootstrap)
    from monitor_data.db.neo4j import _SCHEMA_BOOTSTRAP_QUERIES

    assert mock_session.execute_write.call_count == len(_SCHEMA_BOOTSTRAP_QUERIES)
    mock_session.execute_read.assert_called_once()


def test_neo4j_client_execute_write_auto_connects():
    """execute_write should connect without deadlocking the background loop."""
    os.environ["NEO4J_PASSWORD"] = "test_password"

    from monitor_data.db.neo4j import _SCHEMA_BOOTSTRAP_QUERIES

    n_bootstrap = len(_SCHEMA_BOOTSTRAP_QUERIES)
    mock_session = AsyncMock()
    mock_session.execute_write = AsyncMock(side_effect=[None] * n_bootstrap + [[{"value": 1}]])

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session

    mock_driver = AsyncMock()
    mock_driver.session = MagicMock(return_value=mock_ctx)

    with patch("monitor_data.db.neo4j.AsyncGraphDatabase.driver", return_value=mock_driver):
        client = Neo4jClient()
        assert client.execute_write("CREATE (n:Test) RETURN n") == [{"value": 1}]

    assert mock_session.execute_write.call_count == n_bootstrap + 1


@pytest.mark.asyncio
async def test_neo4j_client_connect_initializes_schema_once():
    """Connect should bootstrap Neo4j indexes/constraints only once per client."""
    os.environ["NEO4J_PASSWORD"] = "test_password"

    mock_session = AsyncMock()
    mock_session.execute_write = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session

    mock_driver = AsyncMock()
    mock_driver.session = MagicMock(return_value=mock_ctx)

    with patch("monitor_data.db.neo4j.AsyncGraphDatabase.driver", return_value=mock_driver):
        client = Neo4jClient()
        await client.connect()
        await client.connect()

    # One write per bootstrap statement, executed only on the FIRST connect
    from monitor_data.db.neo4j import _SCHEMA_BOOTSTRAP_QUERIES

    assert mock_session.execute_write.call_count == len(_SCHEMA_BOOTSTRAP_QUERIES)


@patch("monitor_data.db.neo4j.get_neo4j_client")
def test_save_entity_as_template(mock_get_neo4j_client, mock_neo4j_client):
    from monitor_data.tools.neo4j_tools.entities import neo4j_save_template

    mock_get_neo4j_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_write.return_value = [{"id": "template-123"}]
    result = neo4j_save_template(entity_id="entity-123", template_name="Goblin Grunt")
    assert result == "template-123"

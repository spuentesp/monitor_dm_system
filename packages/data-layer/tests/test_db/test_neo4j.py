"""
Unit tests for Neo4j client.

Tests cover:
- Neo4jClient initialization
- Password requirement enforcement
- Connection management
"""

import os
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


def test_neo4j_client_execute_read_without_connection():
    """Test that execute_read raises RuntimeError when not connected."""
    os.environ["NEO4J_PASSWORD"] = "test_password"

    client = Neo4jClient()
    # Don't call connect()

    with pytest.raises(
        RuntimeError, match="Neo4j client not connected. Call connect\\(\\) first."
    ):
        client.execute_read("RETURN 1")


def test_neo4j_client_execute_write_without_connection():
    """Test that execute_write raises RuntimeError when not connected."""
    os.environ["NEO4J_PASSWORD"] = "test_password"

    client = Neo4jClient()
    # Don't call connect()

    with pytest.raises(
        RuntimeError, match="Neo4j client not connected. Call connect\\(\\) first."
    ):
        client.execute_write("CREATE (n:Test) RETURN n")

"""
Pytest configuration and fixtures for MONITOR Data Layer tests.

This module provides:
- Mock database clients (unit tests)
- Testcontainers fixtures (integration tests — real Neo4j + MongoDB)
- Test data factories
- Common fixtures

TEST-1: testcontainers fixtures for Neo4j and MongoDB.
        Use the ``neo4j_container`` and ``mongodb_container`` fixtures in
        integration tests.  They are session-scoped so containers start once
        per test session and are reused across all tests.
"""

import os
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from testcontainers.mongodb import MongoDbContainer
from testcontainers.neo4j import Neo4jContainer

from monitor_data.db.neo4j import Neo4jClient
from monitor_data.schemas.base import Authority, CanonLevel

# =============================================================================
# TEST CONFIGURATION
# =============================================================================


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip integration/e2e tests unless explicitly enabled."""
    if "integration" in item.keywords and not os.getenv("RUN_INTEGRATION"):
        pytest.skip("set RUN_INTEGRATION=1 to run integration tests")
    if "e2e" in item.keywords and not os.getenv("RUN_E2E"):
        pytest.skip("set RUN_E2E=1 to run e2e tests")


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    os.environ.setdefault("NEO4J_USER", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "test_password")
    os.environ.setdefault("MINIO_SECRET_KEY", "test_secret")


# =============================================================================
# TESTCONTAINERS — Real DB integration fixtures (TEST-1)
# =============================================================================


@pytest.fixture(scope="session")
def neo4j_container():
    """
    Start a real Neo4j container for integration tests.

    Yields a running Neo4jContainer.  The bolt URI and credentials are
    exported as environment variables so Neo4jClient picks them up via Settings.

    Scope: session — container starts once and is shared across all tests.
    """
    with Neo4jContainer("neo4j:5") as container:
        bolt_url = container.get_connection_url()
        os.environ["NEO4J_URI"] = bolt_url
        os.environ["NEO4J_USER"] = "neo4j"
        os.environ["NEO4J_PASSWORD"] = container.NEO4J_ADMIN_PASSWORD

        # Clear the settings cache so the new URI is picked up
        from monitor_data.config import get_settings

        get_settings.cache_clear()

        yield container


@pytest.fixture(scope="session")
def mongodb_container():
    """
    Start a real MongoDB container for integration tests.

    Yields a running MongoDbContainer.  The MongoDB URI is exported as an
    environment variable so MongoDBClient picks it up via Settings.

    Scope: session — container starts once and is shared across all tests.
    """
    with MongoDbContainer("mongo:7") as container:
        mongodb_uri = container.get_connection_url()
        os.environ["MONGODB_URI"] = mongodb_uri

        from monitor_data.config import get_settings

        get_settings.cache_clear()

        yield container


@pytest.fixture
async def neo4j_client(neo4j_container) -> AsyncGenerator[Neo4jClient, None]:
    """
    Provide a connected async Neo4j client, cleaned up after each test.

    Requires: ``neo4j_container`` session fixture (starts the DB).
    """
    from monitor_data.db.neo4j import get_neo4j_client, reset_neo4j_client

    client = await get_neo4j_client()
    yield client
    await reset_neo4j_client()


@pytest.fixture
async def mongodb_client(mongodb_container):
    """
    Provide a connected async Motor MongoDB client, cleaned up after each test.

    Requires: ``mongodb_container`` session fixture (starts the DB).
    """
    from monitor_data.db.mongodb import get_mongodb_client, reset_mongodb_client

    client = await get_mongodb_client()
    yield client
    await reset_mongodb_client()


# =============================================================================
# MOCK CLIENTS — For unit tests (no real DB needed)
# =============================================================================


@pytest.fixture
def mock_neo4j_client() -> Generator[Mock, None, None]:
    """
    Provide a mock Neo4j client for unit testing.

    Returns an AsyncMock so async methods can be awaited in tests.
    """
    mock_client = AsyncMock(spec=Neo4jClient)
    mock_client.execute_read = Mock(return_value=[])
    mock_client.execute_write = Mock(return_value=[])
    mock_client.verify_connectivity = AsyncMock(return_value=True)
    mock_client.connect = AsyncMock()
    mock_client.close = AsyncMock()

    yield mock_client


@pytest.fixture
def mock_mongodb_client():
    """Provide a mock Motor MongoDB client for unit testing."""
    from monitor_data.db.mongodb import MongoDBClient

    mock_client = AsyncMock(spec=MongoDBClient)
    mock_client.get_collection = Mock(return_value=AsyncMock())
    mock_client.connect = AsyncMock()
    mock_client.close = AsyncMock()
    yield mock_client


# =============================================================================
# TEST DATA FACTORIES
# =============================================================================


@pytest.fixture
def omniverse_data() -> dict[str, Any]:
    """Provide sample omniverse data."""
    return {
        "id": str(uuid4()),
        "name": "Test Omniverse",
        "description": "Test omniverse for unit tests",
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def multiverse_data(omniverse_data: dict[str, Any]) -> dict[str, Any]:
    """Provide sample multiverse data."""
    return {
        "id": str(uuid4()),
        "omniverse_id": omniverse_data["id"],
        "name": "Test Multiverse",
        "system_name": "Test System",
        "description": "Test multiverse for unit tests",
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def universe_data(multiverse_data: dict[str, Any]) -> dict[str, Any]:
    """Provide sample universe data."""
    return {
        "id": str(uuid4()),
        "multiverse_id": multiverse_data["id"],
        "name": "Test Universe",
        "description": "A test universe for unit tests",
        "genre": "fantasy",
        "tone": "heroic",
        "tech_level": "medieval",
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def universe_node(universe_data: dict[str, Any]) -> dict[str, Any]:
    """
    Provide a universe node as returned by Neo4j.

    This simulates the structure returned by execute_read/execute_write.
    """
    return {"u": universe_data}


@pytest.fixture
def story_data(universe_data: dict[str, Any]) -> dict[str, Any]:
    """Provide sample story data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "title": "Test Story",
    }


# =============================================================================
# UTILITY FIXTURES
# =============================================================================


@pytest.fixture
def valid_uuid() -> str:
    """Provide a valid UUID string."""
    return str(uuid4())


@pytest.fixture
def invalid_uuid() -> str:
    """Provide an invalid UUID string."""
    return "not-a-valid-uuid"

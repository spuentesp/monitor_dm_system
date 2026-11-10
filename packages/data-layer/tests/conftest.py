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

The client fixtures (``neo4j_client``, ``mongodb_client``) build their client
with the container's own URI and credentials and install it as the module-level
singleton.  ``monitor_data.config.settings`` is a module-level singleton built
at import time, so exporting environment variables afterwards never reached
the clients: a "testcontainer" test could silently talk to the compose
database instead.  The clients are now wired explicitly and the connection is
verified against the container before the test body runs.
"""

import os
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from testcontainers.mongodb import MongoDbContainer
from testcontainers.neo4j import Neo4jContainer

from monitor_data.config import settings
from monitor_data.db.mongodb import MongoDBClient
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

# Credentials for the throw-away containers.  They are deliberately unlike
# anything in .env: a client that authenticates with them can only have
# reached the container, never the compose database.
NEO4J_TEST_USER = "neo4j"
NEO4J_TEST_PASSWORD = "integration-neo4j-password"
MONGO_TEST_USER = "monitor"
MONGO_TEST_PASSWORD = "integration-mongo-password"
MONGO_TEST_DATABASE = "monitor_integration"


@pytest.fixture(scope="session")
def neo4j_container():
    """
    Start a real Neo4j container for integration tests.

    Yields a running Neo4jContainer.  The image matches the compose service so
    a CI runner reuses the layers it already pulled.

    Scope: session — container starts once and is shared across all tests.
    """
    with Neo4jContainer(
        "neo4j:5.15-community",
        username=NEO4J_TEST_USER,
        password=NEO4J_TEST_PASSWORD,
    ) as container:
        yield container


@pytest.fixture(scope="session")
def mongodb_container():
    """
    Start a real MongoDB container for integration tests.

    Yields a running MongoDbContainer.  The image matches the compose service
    so a CI runner reuses the layers it already pulled.

    Scope: session — container starts once and is shared across all tests.
    """
    with MongoDbContainer(
        "mongo:7.0",
        username=MONGO_TEST_USER,
        password=MONGO_TEST_PASSWORD,
    ) as container:
        yield container


@pytest.fixture
def neo4j_client(neo4j_container, monkeypatch) -> Generator[Neo4jClient, None, None]:
    """
    Provide a Neo4j client bound to the test container.

    The client is built with the container's own URI and credentials and is
    installed as the module-level singleton, so the sync MCP tools
    (``neo4j_create_entity`` and friends) reach the same container as the
    test body instead of whatever ``NEO4J_URI`` happens to point at.

    Requires: ``neo4j_container`` session fixture (starts the DB).
    """
    from monitor_data.db import neo4j as neo4j_module
    from monitor_data.db._utils import run_sync

    uri = neo4j_container.get_connection_url()
    client = Neo4jClient(
        uri=uri,
        user=neo4j_container.username,
        password=neo4j_container.password,
    )
    monkeypatch.setattr(neo4j_module, "_neo4j_client_instance", client)
    # Point the settings singleton at the container as well, so a client
    # created later in the test (after a reset) reaches it too.
    monkeypatch.setattr(settings, "neo4j_uri", uri)
    monkeypatch.setattr(settings, "neo4j_user", neo4j_container.username)
    monkeypatch.setattr(settings, "neo4j_password", neo4j_container.password)

    # Prove the client under test talks to the container: a marker written
    # through the container's own driver must come back through the client.
    marker_id = uuid4().hex
    with neo4j_container.get_driver() as driver:
        driver.execute_query(
            "CREATE (:IntegrationTestMarker {id: $id})",
            {"id": marker_id},
        )
    rows = client.execute_read(
        "MATCH (m:IntegrationTestMarker {id: $id}) RETURN m.id AS id",
        {"id": marker_id},
    )
    assert rows and rows[0]["id"] == marker_id, "the Neo4j client under test is not connected to the test container"
    client.execute_write(
        "MATCH (m:IntegrationTestMarker {id: $id}) DELETE m",
        {"id": marker_id},
    )

    yield client

    run_sync(client.close())


@pytest.fixture
def mongodb_client(mongodb_container, monkeypatch) -> Generator[MongoDBClient, None, None]:
    """
    Provide a MongoDB client bound to the test container.

    Like ``neo4j_client``, the client is installed as the module-level
    singleton so the sync MCP tools reach the container too.

    Requires: ``mongodb_container`` session fixture (starts the DB).
    """
    from monitor_data.db import mongodb as mongodb_module
    from monitor_data.db._utils import run_sync

    uri = mongodb_container.get_connection_url()
    client = MongoDBClient(
        uri=uri,
        database=MONGO_TEST_DATABASE,
    )
    monkeypatch.setattr(mongodb_module, "_mongodb_client_instance", client)
    # Point the settings singleton at the container as well, so a client
    # created later in the test (after a reset) reaches it too.
    monkeypatch.setattr(settings, "mongodb_uri", uri)
    monkeypatch.setattr(settings, "mongodb_database", MONGO_TEST_DATABASE)

    # Prove the client under test talks to the container.
    marker_id = uuid4().hex
    with mongodb_container.get_connection_client() as container_client:
        container_client[MONGO_TEST_DATABASE]["integration_test_marker"].insert_one({"id": marker_id})
    found = client.get_collection("integration_test_marker").find_one({"id": marker_id})
    assert found is not None, "the MongoDB client under test is not connected to the test container"
    client.get_collection("integration_test_marker").delete_one({"id": marker_id})

    yield client

    run_sync(client.close())


@pytest.fixture
async def qdrant_client() -> AsyncGenerator[Any, None]:
    """
    Provide the async Qdrant client with the entity and knowledge collections created.

    There is no Qdrant testcontainer: this talks to the Qdrant at the
    configured address (the compose service in the integration job) and skips
    when none answers.  The collections are created the way the application
    creates them, payload indexes included.
    """
    from monitor_data.db.qdrant import QdrantClient

    url = settings.resolved_qdrant_url
    wrapper = QdrantClient(url=url)
    await wrapper.connect()
    try:
        await wrapper.get_client().get_collections()
    except Exception as exc:  # noqa: BLE001  # reason: any connection failure means no Qdrant to test against
        await wrapper.close()
        pytest.skip(f"no Qdrant reachable at {url}: {exc}")

    for collection_name in ("entities", "knowledge"):
        await wrapper.ensure_collection(collection_name)

    yield wrapper.get_client()

    await wrapper.close()


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

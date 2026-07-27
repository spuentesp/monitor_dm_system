"""
Tests for health check endpoint.

Tests health status reporting for all database components.
"""

from unittest.mock import AsyncMock, Mock, patch

from monitor_data.health import (
    HealthStatus,
    check_mongodb_connectivity,
    check_neo4j_connectivity,
    check_qdrant_connectivity,
    get_health_status,
    is_healthy,
)

# =============================================================================
# NEO4J CONNECTIVITY TESTS
# =============================================================================


@patch("monitor_data.health.get_neo4j_client")
async def test_check_neo4j_connectivity_healthy(mock_get_client):
    """Test Neo4j health check when connection is healthy."""
    mock_client = AsyncMock()
    mock_client.verify_connectivity.return_value = True
    mock_get_client.return_value = mock_client

    result = await check_neo4j_connectivity()

    assert result["status"] == HealthStatus.HEALTHY
    assert "Neo4j connection established" in result["message"]


@patch("monitor_data.health.get_neo4j_client")
async def test_check_neo4j_connectivity_unhealthy(mock_get_client):
    """Test Neo4j health check when connection fails."""
    mock_client = AsyncMock()
    mock_client.verify_connectivity.return_value = False
    mock_get_client.return_value = mock_client

    result = await check_neo4j_connectivity()

    assert result["status"] == HealthStatus.UNHEALTHY
    assert "Neo4j connection failed" in result["message"]


@patch("monitor_data.health.get_neo4j_client")
async def test_check_neo4j_connectivity_error(mock_get_client):
    """Test Neo4j health check when exception occurs."""
    mock_get_client.side_effect = Exception("Connection error")

    result = await check_neo4j_connectivity()

    assert result["status"] == HealthStatus.UNHEALTHY
    assert "Neo4j error" in result["message"]


# =============================================================================
# MONGODB CONNECTIVITY TESTS
# =============================================================================


@patch("monitor_data.health.get_mongodb_client")
async def test_check_mongodb_connectivity_healthy(mock_get_client):
    """Test MongoDB health check when connection is healthy."""
    mock_client = AsyncMock()
    mock_client.verify_connectivity.return_value = True
    mock_get_client.return_value = mock_client

    result = await check_mongodb_connectivity()

    assert result["status"] == HealthStatus.HEALTHY
    assert "MongoDB connection established" in result["message"]


@patch("monitor_data.health.get_mongodb_client")
async def test_check_mongodb_connectivity_unhealthy(mock_get_client):
    """Test MongoDB health check when connection fails."""
    mock_client = AsyncMock()
    mock_client.verify_connectivity.return_value = False
    mock_get_client.return_value = mock_client

    result = await check_mongodb_connectivity()

    assert result["status"] == HealthStatus.UNHEALTHY
    assert "MongoDB connection failed" in result["message"]


@patch("monitor_data.health.get_mongodb_client")
async def test_check_mongodb_connectivity_error(mock_get_client):
    """Test MongoDB health check when exception occurs."""
    mock_get_client.side_effect = Exception("Connection error")

    result = await check_mongodb_connectivity()

    assert result["status"] == HealthStatus.UNHEALTHY
    assert "MongoDB error" in result["message"]


# =============================================================================
# QDRANT CONNECTIVITY TESTS
# =============================================================================


@patch("monitor_data.health.get_qdrant_client")
def test_check_qdrant_connectivity_healthy(mock_get_client):
    """Test Qdrant health check when connection is healthy."""
    mock_client = Mock()
    mock_client.verify_connectivity.return_value = True
    mock_get_client.return_value = mock_client

    result = check_qdrant_connectivity()

    assert result["status"] == HealthStatus.HEALTHY
    assert "Qdrant connection established" in result["message"]


@patch("monitor_data.health.get_qdrant_client")
def test_check_qdrant_connectivity_unhealthy(mock_get_client):
    """Test Qdrant health check when connection fails."""
    mock_client = Mock()
    mock_client.verify_connectivity.return_value = False
    mock_get_client.return_value = mock_client

    result = check_qdrant_connectivity()

    assert result["status"] == HealthStatus.UNHEALTHY
    assert "Qdrant connection failed" in result["message"]


@patch("monitor_data.health.get_qdrant_client")
def test_check_qdrant_connectivity_error(mock_get_client):
    """Test Qdrant health check when exception occurs."""
    mock_get_client.side_effect = Exception("Connection error")

    result = check_qdrant_connectivity()

    assert result["status"] == HealthStatus.UNHEALTHY
    assert "Qdrant error" in result["message"]


# =============================================================================
# OVERALL HEALTH STATUS TESTS
# =============================================================================


@patch("monitor_data.health.check_llm_providers")
@patch("monitor_data.health.check_minio_connectivity", new_callable=AsyncMock)
@patch("monitor_data.health.check_postgres_connectivity", new_callable=AsyncMock)
@patch("monitor_data.health.check_qdrant_connectivity")
@patch("monitor_data.health.check_mongodb_connectivity")
@patch("monitor_data.health.check_neo4j_connectivity")
async def test_get_health_status_all_healthy(
    mock_neo4j, mock_mongodb, mock_qdrant, mock_postgres, mock_minio, mock_llm
):
    """Test overall health status when all components are healthy."""
    mock_neo4j.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_mongodb.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_qdrant.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_postgres.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_minio.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_llm.return_value = {"status": HealthStatus.HEALTHY, "providers": {}}

    status = await get_health_status()

    assert status["overall_status"] == HealthStatus.HEALTHY
    assert status["components"]["neo4j"]["status"] == HealthStatus.HEALTHY
    assert status["components"]["mongodb"]["status"] == HealthStatus.HEALTHY
    assert status["components"]["qdrant"]["status"] == HealthStatus.HEALTHY
    assert status["components"]["postgres"]["status"] == HealthStatus.HEALTHY
    assert status["components"]["minio"]["status"] == HealthStatus.HEALTHY
    assert status["components"]["llm"]["status"] == HealthStatus.HEALTHY
    assert "version" in status
    assert "timestamp" in status


@patch("monitor_data.health.check_llm_providers")
@patch("monitor_data.health.check_minio_connectivity", new_callable=AsyncMock)
@patch("monitor_data.health.check_postgres_connectivity", new_callable=AsyncMock)
@patch("monitor_data.health.check_qdrant_connectivity")
@patch("monitor_data.health.check_mongodb_connectivity")
@patch("monitor_data.health.check_neo4j_connectivity")
async def test_get_health_status_one_unhealthy(
    mock_neo4j, mock_mongodb, mock_qdrant, mock_postgres, mock_minio, mock_llm
):
    """Test overall health status when one component is unhealthy."""
    mock_neo4j.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_mongodb.return_value = {"status": HealthStatus.UNHEALTHY, "message": "Failed"}
    mock_qdrant.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_postgres.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_minio.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_llm.return_value = {"status": HealthStatus.HEALTHY, "providers": {}}

    status = await get_health_status()

    # With one unhealthy component, overall should be degraded
    assert status["overall_status"] == HealthStatus.DEGRADED
    assert status["components"]["mongodb"]["status"] == HealthStatus.UNHEALTHY


@patch("monitor_data.health.check_llm_providers")
@patch("monitor_data.health.check_minio_connectivity", new_callable=AsyncMock)
@patch("monitor_data.health.check_postgres_connectivity", new_callable=AsyncMock)
@patch("monitor_data.health.check_qdrant_connectivity")
@patch("monitor_data.health.check_mongodb_connectivity")
@patch("monitor_data.health.check_neo4j_connectivity")
async def test_get_health_status_all_unhealthy(
    mock_neo4j, mock_mongodb, mock_qdrant, mock_postgres, mock_minio, mock_llm
):
    """Test overall health status when all components are unhealthy."""
    mock_neo4j.return_value = {"status": HealthStatus.UNHEALTHY, "message": "Failed"}
    mock_mongodb.return_value = {"status": HealthStatus.UNHEALTHY, "message": "Failed"}
    mock_qdrant.return_value = {"status": HealthStatus.UNHEALTHY, "message": "Failed"}
    mock_postgres.return_value = {"status": HealthStatus.UNHEALTHY, "message": "Failed"}
    mock_minio.return_value = {"status": HealthStatus.UNHEALTHY, "message": "Failed"}
    mock_llm.return_value = {"status": HealthStatus.UNHEALTHY, "providers": {}}

    status = await get_health_status()

    # With all unhealthy, overall should be unhealthy (not degraded)
    assert status["overall_status"] == HealthStatus.UNHEALTHY


# =============================================================================
# IS HEALTHY TESTS
# =============================================================================


async def test_is_healthy_true():
    """Test is_healthy returns True when all components are healthy."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "monitor_data.health.get_health_status",
        new=AsyncMock(
            return_value={
                "overall_status": HealthStatus.HEALTHY,
                "components": {},
                "version": "0.1.0",
                "timestamp": "2025-01-01T00:00:00Z",
            }
        ),
    ):
        assert await is_healthy() is True


async def test_is_healthy_false():
    """Test is_healthy returns False when system is degraded or unhealthy."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "monitor_data.health.get_health_status",
        new=AsyncMock(
            return_value={
                "overall_status": HealthStatus.DEGRADED,
                "components": {},
                "version": "0.1.0",
                "timestamp": "2025-01-01T00:00:00Z",
            }
        ),
    ):
        assert await is_healthy() is False


async def test_is_healthy_exception():
    """Test is_healthy returns False when exception occurs."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "monitor_data.health.get_health_status",
        new=AsyncMock(side_effect=Exception("Health check failed")),
    ):
        assert await is_healthy() is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


@patch("monitor_data.health.check_llm_providers")
@patch("monitor_data.health.check_minio_connectivity", new_callable=AsyncMock)
@patch("monitor_data.health.check_postgres_connectivity", new_callable=AsyncMock)
@patch("monitor_data.health.check_qdrant_connectivity")
@patch("monitor_data.health.check_mongodb_connectivity")
@patch("monitor_data.health.check_neo4j_connectivity")
async def test_health_status_structure(mock_neo4j, mock_mongodb, mock_qdrant, mock_postgres, mock_minio, mock_llm):
    """Test health status response has correct structure."""
    mock_neo4j.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_mongodb.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_qdrant.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_postgres.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_minio.return_value = {"status": HealthStatus.HEALTHY, "message": "OK"}
    mock_llm.return_value = {"status": HealthStatus.HEALTHY, "providers": {}}

    status = await get_health_status()

    # Verify structure
    assert "overall_status" in status
    assert "components" in status
    assert "version" in status
    assert "timestamp" in status

    # Verify components
    assert "neo4j" in status["components"]
    assert "mongodb" in status["components"]
    assert "qdrant" in status["components"]
    assert "postgres" in status["components"]
    assert "minio" in status["components"]

    # Verify timestamp format (ISO 8601)
    assert status["timestamp"].endswith("Z")

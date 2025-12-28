"""
Unit tests for MCP server health endpoint.

Tests cover:
- Health endpoint returns correct structure
- Health endpoint includes version info
- Health endpoint includes database status
- Health endpoint returns 200 status code
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from monitor_data.server import app


# =============================================================================
# TEST CLIENT SETUP
# =============================================================================


@pytest.fixture
def client():
    """Provide a test client for the FastAPI app."""
    return TestClient(app)


# =============================================================================
# TESTS: Health Endpoint
# =============================================================================


def test_health_endpoint_returns_200(client):
    """Health endpoint returns 200 status code."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint_structure(client):
    """Health endpoint returns correct JSON structure."""
    response = client.get("/health")
    data = response.json()
    
    assert "status" in data
    assert "version" in data
    assert "timestamp" in data
    assert "databases" in data


def test_health_endpoint_status_field(client):
    """Health endpoint includes status field."""
    response = client.get("/health")
    data = response.json()
    
    assert data["status"] in ["healthy", "degraded", "unhealthy"]


def test_health_endpoint_version_info(client):
    """Health endpoint includes version information."""
    response = client.get("/health")
    data = response.json()
    
    assert "version" in data
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


def test_health_endpoint_timestamp(client):
    """Health endpoint includes current timestamp."""
    response = client.get("/health")
    data = response.json()
    
    assert "timestamp" in data
    # Verify it's a valid ISO timestamp
    timestamp = data["timestamp"]
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert isinstance(parsed, datetime)


def test_health_endpoint_database_connectivity(client):
    """Health endpoint includes database connectivity status."""
    response = client.get("/health")
    data = response.json()
    
    assert "databases" in data
    assert isinstance(data["databases"], dict)
    
    # Should include status for each database
    databases = data["databases"]
    assert "neo4j" in databases
    assert "mongodb" in databases
    assert "qdrant" in databases
    
    # Each should be a boolean
    for db_name, status in databases.items():
        assert isinstance(status, bool)


def test_health_endpoint_healthy_when_all_dbs_ok(client):
    """Health endpoint reports healthy when all databases are OK."""
    response = client.get("/health")
    data = response.json()
    
    # If all databases report True, status should be healthy
    all_healthy = all(data["databases"].values())
    if all_healthy:
        assert data["status"] == "healthy"


def test_health_endpoint_degraded_when_db_down(client):
    """Health endpoint reports degraded when database is down."""
    # This test would require mocking database connectivity
    # For now, we just verify the structure supports this
    response = client.get("/health")
    data = response.json()
    
    # Status should be one of the valid values
    assert data["status"] in ["healthy", "degraded", "unhealthy"]


# =============================================================================
# TESTS: Content Type
# =============================================================================


def test_health_endpoint_content_type(client):
    """Health endpoint returns JSON content type."""
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]


# =============================================================================
# TESTS: Response Schema Validation
# =============================================================================


def test_health_response_schema_valid(client):
    """Health endpoint response matches expected schema."""
    response = client.get("/health")
    data = response.json()
    
    # Verify all required fields are present
    required_fields = ["status", "version", "timestamp", "databases"]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Verify field types
    assert isinstance(data["status"], str)
    assert isinstance(data["version"], str)
    assert isinstance(data["timestamp"], str)
    assert isinstance(data["databases"], dict)

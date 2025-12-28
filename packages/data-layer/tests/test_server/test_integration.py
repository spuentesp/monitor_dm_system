"""
Integration tests for MCP server tool calls.

Tests the full flow: request → auth → validation → execution → response.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from uuid import uuid4

from monitor_data.server import app


# =============================================================================
# TEST CLIENT SETUP
# =============================================================================


@pytest.fixture
def client():
    """Provide a test client for the FastAPI app."""
    return TestClient(app)


# =============================================================================
# TESTS: Tool Introspection
# =============================================================================


def test_list_tools_endpoint(client):
    """Tools endpoint lists all registered tools."""
    response = client.get("/tools")
    assert response.status_code == 200
    
    tools = response.json()
    assert isinstance(tools, list)
    assert len(tools) > 0
    
    # Check structure of first tool
    tool = tools[0]
    assert "name" in tool
    assert "description" in tool
    assert "authority" in tool
    assert "parameters" in tool


def test_list_tools_includes_neo4j_tools(client):
    """Tools endpoint includes Neo4j tools."""
    response = client.get("/tools")
    tools = response.json()
    
    tool_names = [t["name"] for t in tools]
    assert "neo4j_create_universe" in tool_names
    assert "neo4j_get_universe" in tool_names


def test_tool_schema_includes_authority(client):
    """Tool schemas include authority information."""
    response = client.get("/tools")
    tools = response.json()
    
    # Find a restricted tool
    create_universe = next(
        (t for t in tools if t["name"] == "neo4j_create_universe"), None
    )
    assert create_universe is not None
    assert "CanonKeeper" in create_universe["authority"]


# =============================================================================
# TESTS: Successful Tool Calls
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_authorized_tool_call_succeeds(mock_client_getter, client):
    """Authorized agent can call restricted tool."""
    # Mock Neo4j client
    mock_client = Mock()
    mock_client.execute_read.return_value = [{"o": {"id": str(uuid4())}}]
    mock_client.execute_write.return_value = None
    mock_client_getter.return_value = mock_client
    
    omniverse_id = str(uuid4())
    request_data = {
        "tool_name": "neo4j_create_multiverse",
        "agent_id": "test-canonkeeper",
        "agent_type": "CanonKeeper",
        "arguments": {
            "omniverse_id": omniverse_id,
            "name": "Test Multiverse",
            "system_name": "Test System",
            "description": "Test description",
        },
    }
    
    response = client.post("/tools/call", json=request_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert "result" in data


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_read_only_tool_call_any_agent(mock_client_getter, client):
    """Any agent can call read-only tools."""
    # Mock Neo4j client
    mock_client = Mock()
    mock_client.execute_read.return_value = []
    mock_client_getter.return_value = mock_client
    
    request_data = {
        "tool_name": "neo4j_list_universes",
        "agent_id": "test-narrator",
        "agent_type": "Narrator",
        "arguments": {},
    }
    
    response = client.post("/tools/call", json=request_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True


# =============================================================================
# TESTS: Authorization Failures
# =============================================================================


def test_unauthorized_tool_call_fails(client):
    """Unauthorized agent cannot call restricted tool."""
    request_data = {
        "tool_name": "neo4j_create_universe",
        "agent_id": "test-narrator",
        "agent_type": "Narrator",  # Not authorized
        "arguments": {
            "multiverse_id": str(uuid4()),
            "name": "Test",
            "description": "Test",
            "genre": "fantasy",
            "tone": "heroic",
            "tech_level": "medieval",
            "confidence": 1.0,
            "authority": "system",
        },
    }
    
    response = client.post("/tools/call", json=request_data)
    assert response.status_code == 200  # Success at HTTP level
    
    data = response.json()
    assert data["success"] is False
    assert "error" in data
    assert data["error"]["code"] == 403
    assert data["error"]["type"] == "UNAUTHORIZED"


# =============================================================================
# TESTS: Validation Failures
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_invalid_arguments_fail_validation(mock_client_getter, client):
    """Invalid arguments fail validation."""
    mock_client = Mock()
    mock_client_getter.return_value = mock_client
    
    request_data = {
        "tool_name": "neo4j_create_multiverse",
        "agent_id": "test-canonkeeper",
        "agent_type": "CanonKeeper",
        "arguments": {
            # Missing required fields
            "name": "Test Multiverse",
        },
    }
    
    response = client.post("/tools/call", json=request_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is False
    assert "error" in data
    assert data["error"]["code"] == 400
    assert data["error"]["type"] == "VALIDATION_ERROR"


# =============================================================================
# TESTS: Tool Not Found
# =============================================================================


def test_nonexistent_tool_returns_404(client):
    """Calling non-existent tool returns 404."""
    request_data = {
        "tool_name": "nonexistent_tool",
        "agent_id": "test-agent",
        "agent_type": "CanonKeeper",
        "arguments": {},
    }
    
    response = client.post("/tools/call", json=request_data)
    assert response.status_code == 404


# =============================================================================
# TESTS: Logging
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_tool_call_is_logged(mock_client_getter, client, caplog):
    """Tool calls are logged with metadata."""
    mock_client = Mock()
    mock_client.execute_read.return_value = []
    mock_client_getter.return_value = mock_client
    
    request_data = {
        "tool_name": "neo4j_list_universes",
        "agent_id": "test-agent",
        "agent_type": "Narrator",
        "arguments": {},
    }
    
    with caplog.at_level("INFO"):
        response = client.post("/tools/call", json=request_data)
    
    # Check that tool call was logged
    assert any("Tool call" in record.message for record in caplog.records)
    assert any("neo4j_list_universes" in record.message for record in caplog.records)


def test_authorization_failure_is_logged(client, caplog):
    """Authorization failures are logged."""
    request_data = {
        "tool_name": "neo4j_create_universe",
        "agent_id": "test-narrator",
        "agent_type": "Narrator",
        "arguments": {},
    }
    
    with caplog.at_level("WARNING"):
        response = client.post("/tools/call", json=request_data)
    
    # Check that authorization failure was logged
    assert any(
        "Authorization failed" in record.message for record in caplog.records
    )


# =============================================================================
# TESTS: Error Response Format
# =============================================================================


def test_error_response_format_consistent(client):
    """Error responses follow consistent format."""
    request_data = {
        "tool_name": "neo4j_create_universe",
        "agent_id": "test-narrator",
        "agent_type": "Narrator",
        "arguments": {},
    }
    
    response = client.post("/tools/call", json=request_data)
    data = response.json()
    
    assert "success" in data
    assert data["success"] is False
    assert "error" in data
    
    error = data["error"]
    assert "code" in error
    assert "type" in error
    assert "message" in error


# =============================================================================
# TESTS: Request Middleware
# =============================================================================


def test_request_logging_middleware(client, caplog):
    """All requests are logged by middleware."""
    with caplog.at_level("INFO"):
        response = client.get("/health")
    
    # Check that request was logged
    assert any("Request:" in record.message for record in caplog.records)
    assert any("/health" in record.message for record in caplog.records)


def test_response_logging_middleware(client, caplog):
    """All responses are logged by middleware."""
    with caplog.at_level("INFO"):
        response = client.get("/health")
    
    # Check that response was logged
    assert any("Response:" in record.message for record in caplog.records)
    assert any("200" in record.message for record in caplog.records)

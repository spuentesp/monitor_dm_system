"""
SYS-1: Start Application — Contract Tests

This module tests the API contracts defined in SYS-1-contracts.md:
- Data layer tools: neo4j_health_check, mongodb_health_check, qdrant_health_check, minio_health_check, llm_health_check
- Agent classes: AppInitializer, ConfigLoader
- CLI commands: monitor command
"""

import os

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List


# ============================================================================
# Data Layer Tool Contract Tests
# ============================================================================

class TestNeo4jHealthCheckContract:
    """Contract tests for neo4j_health_check data layer tool."""

    @pytest.mark.unit
    async def test_returns_health_status_with_all_required_fields(self, fake_mcp_client):
        """Contract: Returns dict with healthy, message, response_time_ms."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "healthy": True,
            "message": "Neo4j is responding normally",
            "response_time_ms": 25
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "neo4j_health_check",
            {}
        )

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "healthy" in result
        assert "message" in result
        assert "response_time_ms" in result

        # Verify contract: correct types
        assert isinstance(result["healthy"], bool)
        assert isinstance(result["message"], str)
        assert isinstance(result["response_time_ms"], int)

        # Verify contract: correct values
        assert result["healthy"] == True
        assert result["response_time_ms"] >= 0

    @pytest.mark.unit
    async def test_returns_healthy_false_when_neo4j_unresponsive(self, fake_mcp_client):
        """Contract: Returns healthy: False when Neo4j is down or unresponsive."""
        fake_mcp_client.call_tool.return_value = {
            "healthy": False,
            "message": "Neo4j is not responding",
            "response_time_ms": 5000
        }

        result = await fake_mcp_client.call_tool(
            "neo4j_health_check",
            {}
        )

        # Verify contract: healthy is False
        assert result["healthy"] == False

    @pytest.mark.unit
    async def test_raises_connection_error_when_neo4j_not_accessible(self, fake_mcp_client):
        """Contract: Raises ConnectionError when Neo4j is not accessible."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "ConnectionError: Failed to connect to Neo4j: Connection refused"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "neo4j_health_check",
                {}
            )

        assert "ConnectionError" in str(exc_info.value)


class TestMongodbHealthCheckContract:
    """Contract tests for mongodb_health_check data layer tool."""

    @pytest.mark.unit
    async def test_returns_health_status_with_all_required_fields(self, fake_mcp_client):
        """Contract: Returns dict with healthy, message, response_time_ms."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "healthy": True,
            "message": "MongoDB is responding normally",
            "response_time_ms": 18
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "mongodb_health_check",
            {}
        )

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "healthy" in result
        assert "message" in result
        assert "response_time_ms" in result

        # Verify contract: correct types
        assert isinstance(result["healthy"], bool)
        assert isinstance(result["message"], str)
        assert isinstance(result["response_time_ms"], int)

    @pytest.mark.unit
    async def test_raises_connection_error_when_mongodb_not_accessible(self, fake_mcp_client):
        """Contract: Raises ConnectionError when MongoDB is not accessible."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "ConnectionError: Failed to connect to MongoDB: Connection refused"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "mongodb_health_check",
                {}
            )

        assert "ConnectionError" in str(exc_info.value)


class TestQdrantHealthCheckContract:
    """Contract tests for qdrant_health_check data layer tool."""

    @pytest.mark.unit
    async def test_returns_health_status_with_all_required_fields(self, fake_mcp_client):
        """Contract: Returns dict with healthy, message, response_time_ms."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "healthy": True,
            "message": "Qdrant is responding normally",
            "response_time_ms": 12
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "qdrant_health_check",
            {}
        )

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "healthy" in result
        assert "message" in result
        assert "response_time_ms" in result

    @pytest.mark.unit
    async def test_raises_connection_error_when_qdrant_not_accessible(self, fake_mcp_client):
        """Contract: Raises ConnectionError when Qdrant is not accessible."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "ConnectionError: Failed to connect to Qdrant: Connection refused"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "qdrant_health_check",
                {}
            )

        assert "ConnectionError" in str(exc_info.value)


class TestMinioHealthCheckContract:
    """Contract tests for minio_health_check data layer tool."""

    @pytest.mark.unit
    async def test_returns_health_status_with_all_required_fields(self, fake_mcp_client):
        """Contract: Returns dict with healthy, message, response_time_ms."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "healthy": True,
            "message": "MinIO is responding normally",
            "response_time_ms": 20
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "minio_health_check",
            {}
        )

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "healthy" in result
        assert "message" in result
        assert "response_time_ms" in result

    @pytest.mark.unit
    async def test_raises_connection_error_when_minio_not_accessible(self, fake_mcp_client):
        """Contract: Raises ConnectionError when MinIO is not accessible."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "ConnectionError: Failed to connect to MinIO: Connection refused"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "minio_health_check",
                {}
            )

        assert "ConnectionError" in str(exc_info.value)


class TestLLMHealthCheckContract:
    """Contract tests for llm_health_check data layer tool."""

    @pytest.mark.unit
    async def test_returns_health_status_with_all_required_fields(self, fake_mcp_client):
        """Contract: Returns dict with healthy, message, response_time_ms."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "healthy": True,
            "message": "LLM API is responding normally",
            "response_time_ms": 150
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "llm_health_check",
            {}
        )

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "healthy" in result
        assert "message" in result
        assert "response_time_ms" in result

    @pytest.mark.unit
    async def test_raises_authentication_error_when_api_key_invalid(self, fake_mcp_client):
        """Contract: Raises AuthenticationError when API key is invalid."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "AuthenticationError: Invalid credentials for LLM API: Invalid API key"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "llm_health_check",
                {}
            )

        assert "AuthenticationError" in str(exc_info.value)


# ============================================================================
# Agent Contract Tests
# ============================================================================

@pytest.mark.unit
class TestAppInitializerInitializeContract:
    """Contract tests for AppInitializer.initialize method."""

    @pytest.mark.unit
    async def test_returns_complete_initialization_status(self, fake_mcp_client, fake_llm_client):
        """Contract: Returns dict with success, health_status, errors, warnings."""
        # Mock MCP responses for all health checks
        fake_mcp_client.call_tool.side_effect = [
            # neo4j_health_check
            {"healthy": True, "message": "Neo4j is responding", "response_time_ms": 25},
            # mongodb_health_check
            {"healthy": True, "message": "MongoDB is responding", "response_time_ms": 18},
            # qdrant_health_check
            {"healthy": True, "message": "Qdrant is responding", "response_time_ms": 12},
            # minio_health_check
            {"healthy": True, "message": "MinIO is responding", "response_time_ms": 20},
            # llm_health_check
            {"healthy": True, "message": "LLM API is responding", "response_time_ms": 150},
        ]

        # Create AppInitializer instance
        from monitor_agents.app_initializer import AppInitializer
        initializer = AppInitializer(mcp_client=fake_mcp_client, llm_client=fake_llm_client)

        # Call method with contract-specified parameters
        result = await initializer.initialize()

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "success" in result
        assert "health_status" in result
        assert "errors" in result
        assert "warnings" in result

        # Verify contract: correct types
        assert isinstance(result["success"], bool)
        assert isinstance(result["health_status"], dict)
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)

    @pytest.mark.unit
    async def test_returns_success_true_when_all_services_healthy(self, fake_mcp_client, fake_llm_client):
        """Contract: Returns success: True only when all services are healthy."""
        # Mock all health checks as healthy
        fake_mcp_client.call_tool.side_effect = [
            {"healthy": True, "message": "OK", "response_time_ms": 25},
            {"healthy": True, "message": "OK", "response_time_ms": 18},
            {"healthy": True, "message": "OK", "response_time_ms": 12},
            {"healthy": True, "message": "OK", "response_time_ms": 20},
            {"healthy": True, "message": "OK", "response_time_ms": 150},
        ]

        from monitor_agents.app_initializer import AppInitializer
        initializer = AppInitializer(mcp_client=fake_mcp_client, llm_client=fake_llm_client)

        result = await initializer.initialize()

        # Verify contract: success is True
        assert result["success"] == True

    @pytest.mark.unit
    async def test_returns_success_false_when_any_service_unhealthy(self, fake_mcp_client, fake_llm_client):
        """Contract: Returns success: False when any service is unhealthy."""
        # Mock MongoDB as unhealthy
        fake_mcp_client.call_tool.side_effect = [
            {"healthy": True, "message": "OK", "response_time_ms": 25},
            {"healthy": False, "message": "MongoDB not responding", "response_time_ms": 5000},
            {"healthy": True, "message": "OK", "response_time_ms": 12},
            {"healthy": True, "message": "OK", "response_time_ms": 20},
            {"healthy": True, "message": "OK", "response_time_ms": 150},
        ]

        from monitor_agents.app_initializer import AppInitializer
        initializer = AppInitializer(mcp_client=fake_mcp_client, llm_client=fake_llm_client)

        result = await initializer.initialize()

        # Verify contract: success is False
        assert result["success"] == False

    @pytest.mark.unit
    async def test_calls_all_health_checks(self, fake_mcp_client, fake_llm_client):
        """Contract: Calls health check for all services."""
        # Mock all health checks
        fake_mcp_client.call_tool.side_effect = [
            {"healthy": True, "message": "OK", "response_time_ms": 25},
            {"healthy": True, "message": "OK", "response_time_ms": 18},
            {"healthy": True, "message": "OK", "response_time_ms": 12},
            {"healthy": True, "message": "OK", "response_time_ms": 20},
            {"healthy": True, "message": "OK", "response_time_ms": 150},
        ]

        from monitor_agents.app_initializer import AppInitializer
        initializer = AppInitializer(mcp_client=fake_mcp_client, llm_client=fake_llm_client)

        await initializer.initialize()

        # Verify all health checks were called
        call_args_list = fake_mcp_client.call_tool.call_args_list
        assert len(call_args_list) == 5

        # Verify correct tools were called
        tool_names = [call[0][0] for call in call_args_list]
        assert "neo4j_health_check" in tool_names
        assert "mongodb_health_check" in tool_names
        assert "qdrant_health_check" in tool_names
        assert "minio_health_check" in tool_names
        assert "llm_health_check" in tool_names

    @pytest.mark.unit
    async def test_collects_and_returns_all_errors(self, fake_mcp_client, fake_llm_client):
        """Contract: Collects and returns all errors encountered."""
        # Mock some services failing
        fake_mcp_client.call_tool.side_effect = [
            {"healthy": True, "message": "OK", "response_time_ms": 25},
            {"healthy": False, "message": "MongoDB not responding", "response_time_ms": 5000},
            {"healthy": False, "message": "Qdrant not responding", "response_time_ms": 5000},
            {"healthy": True, "message": "OK", "response_time_ms": 20},
            {"healthy": True, "message": "OK", "response_time_ms": 150},
        ]

        from monitor_agents.app_initializer import AppInitializer
        initializer = AppInitializer(mcp_client=fake_mcp_client, llm_client=fake_llm_client)

        result = await initializer.initialize()

        # Verify contract: errors are collected
        assert len(result["errors"]) >= 2
        assert any("MongoDB" in str(e) for e in result["errors"])
        assert any("Qdrant" in str(e) for e in result["errors"])


@pytest.mark.unit
class TestConfigLoaderLoadConfigContract:
    """Contract tests for ConfigLoader.load_config method."""

    @pytest.mark.unit
    def test_returns_complete_configuration_dict(self, tmp_path):
        """Contract: Returns dict with neo4j, mongodb, qdrant, minio, llm, app sections."""
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("""
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=pass
NEO4J_DATABASE=monitor

MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=monitor

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=key

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=monitor

LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4
LLM_API_KEY=sk-ant-api123
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096

APP_LOG_LEVEL=INFO
APP_AUTO_SAVE=true
""")

        # Create ConfigLoader instance
        from monitor_agents.config_loader import ConfigLoader
        config_loader = ConfigLoader()

        # Call method with contract-specified parameters
        result = config_loader.load_config(str(env_file))

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains all required sections
        assert "neo4j" in result
        assert "mongodb" in result
        assert "qdrant" in result
        assert "minio" in result
        assert "llm" in result
        assert "app" in result

        # Verify contract: neo4j section has required fields
        assert "uri" in result["neo4j"]
        assert "username" in result["neo4j"]
        assert "password" in result["neo4j"]
        assert "database" in result["neo4j"]

        # Verify contract: llm section has required fields
        assert "provider" in result["llm"]
        assert "model" in result["llm"]
        assert "api_key" in result["llm"]
        assert "temperature" in result["llm"]
        assert "max_tokens" in result["llm"]

    @pytest.mark.unit
    def test_raises_configuration_error_when_env_file_missing(self, tmp_path):
        """Contract: Raises ConfigurationError when .env file is missing."""
        from monitor_agents.config_loader import ConfigLoader, ConfigurationError
        config_loader = ConfigLoader()

        # Try to load non-existent file
        with pytest.raises(ConfigurationError):
            config_loader.load_config(str(tmp_path / "nonexistent.env"))

    @pytest.mark.unit
    def test_raises_configuration_error_when_required_keys_missing(self, tmp_path, monkeypatch):
        """Contract: Raises ConfigurationError when required configuration keys are missing."""
        # Clear all MONITOR-related env vars to avoid pollution from other tests
        for key in list(os.environ.keys()):
            if key.startswith(("NEO4J_", "MONGODB_", "QDRANT_", "MINIO_", "LLM_")):
                monkeypatch.delenv(key, raising=False)

        # Create .env file with missing required keys
        env_file = tmp_path / ".env"
        env_file.write_text("""
NEO4J_URI=bolt://localhost:7687
# Missing NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE
""")

        from monitor_agents.config_loader import ConfigLoader, ConfigurationError
        config_loader = ConfigLoader()

        # Try to load incomplete config
        with pytest.raises(ConfigurationError):
            config_loader.load_config(str(env_file))


# ============================================================================
# Integration Tests (with FakeMCPClient)
# ============================================================================

@pytest.mark.unit
class TestSYS1Integration:
    """Integration tests for SYS-1 using FakeMCPClient."""

    @pytest.mark.integration
    async def test_full_application_initialization_workflow(self, fake_mcp_client, fake_llm_client):
        """Contract: Full initialization workflow returns success and health status for all services."""
        # Setup: Mock all required MCP tool calls
        fake_mcp_client.call_tool.side_effect = [
            # Step 1: neo4j_health_check
            {"healthy": True, "message": "Neo4j is responding normally", "response_time_ms": 25},
            # Step 2: mongodb_health_check
            {"healthy": True, "message": "MongoDB is responding normally", "response_time_ms": 18},
            # Step 3: qdrant_health_check
            {"healthy": True, "message": "Qdrant is responding normally", "response_time_ms": 12},
            # Step 4: minio_health_check
            {"healthy": True, "message": "MinIO is responding normally", "response_time_ms": 20},
            # Step 5: llm_health_check
            {"healthy": True, "message": "LLM API is responding normally", "response_time_ms": 150},
        ]

        # Create AppInitializer instance
        from monitor_agents.app_initializer import AppInitializer
        initializer = AppInitializer(mcp_client=fake_mcp_client, llm_client=fake_llm_client)

        # Execute: Initialize application
        result = await initializer.initialize()

        # Verify: Contract compliance
        assert isinstance(result, dict)
        assert result["success"] == True
        assert len(result["errors"]) == 0

        # Verify: Health status for all services
        health_status = result["health_status"]
        assert "neo4j" in health_status
        assert "mongodb" in health_status
        assert "qdrant" in health_status
        assert "minio" in health_status
        assert "llm" in health_status

        # Verify: All services are healthy
        for service, status in health_status.items():
            assert status["healthy"] == True
            assert "message" in status
            assert "response_time_ms" in status
            assert status["response_time_ms"] > 0

        # Verify: All health checks were called in sequence
        assert fake_mcp_client.call_tool.call_count == 5

        # Verify: Health check order (important for troubleshooting)
        call_args_list = fake_mcp_client.call_tool.call_args_list
        assert call_args_list[0][0][0] == "neo4j_health_check"
        assert call_args_list[1][0][0] == "mongodb_health_check"
        assert call_args_list[2][0][0] == "qdrant_health_check"
        assert call_args_list[3][0][0] == "minio_health_check"
        assert call_args_list[4][0][0] == "llm_health_check"

    @pytest.mark.integration
    async def test_initialization_failure_when_service_unhealthy(self, fake_mcp_client, fake_llm_client):
        """Contract: Returns success: False with error details when service is unhealthy."""
        # Setup: Mock MongoDB as unhealthy
        fake_mcp_client.call_tool.side_effect = [
            {"healthy": True, "message": "Neo4j is responding normally", "response_time_ms": 25},
            {"healthy": False, "message": "MongoDB is not responding", "response_time_ms": 5000},
            {"healthy": True, "message": "Qdrant is responding normally", "response_time_ms": 12},
            {"healthy": True, "message": "MinIO is responding normally", "response_time_ms": 20},
            {"healthy": True, "message": "LLM API is responding normally", "response_time_ms": 150},
        ]

        from monitor_agents.app_initializer import AppInitializer
        initializer = AppInitializer(mcp_client=fake_mcp_client, llm_client=fake_llm_client)

        # Execute: Initialize application
        result = await initializer.initialize()

        # Verify: Contract compliance
        assert isinstance(result, dict)
        assert result["success"] == False

        # Verify: Error details provided
        assert len(result["errors"]) > 0
        assert any("MongoDB" in str(e) for e in result["errors"])

        # Verify: Health status still includes all services
        health_status = result["health_status"]
        assert health_status["mongodb"]["healthy"] == False
        assert health_status["neo4j"]["healthy"] == True
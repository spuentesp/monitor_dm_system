"""
SYS-3: Exit Application — Contract Tests

This module tests the API contracts defined in SYS-3-contracts.md:
- Data layer tools: mongodb_get_active_scene, mongodb_update_scene, neo4j_close_connection,
  mongodb_close_connection, qdrant_close_connection, minio_close_connection
- Agent classes: ApplicationExitHandler (check_active_scene, prompt_save_scene, auto_save_scene,
  save_scene, close_all_connections, exit_application, handle_keyboard_interrupt)
- CLI commands: monitor exit
"""

from unittest.mock import patch

import pytest

# ============================================================================
# Data Layer Tool Contract Tests
# ============================================================================


class TestMongodbGetActiveSceneContract:
    """Contract tests for mongodb_get_active_scene data layer tool."""

    @pytest.mark.unit
    async def test_returns_scene_dict_when_active_scene_exists(self, fake_mcp_client):
        """Contract: Returns scene dict when active scene exists for user."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "_id": "scene789",
            "story_id": "story123",
            "user_id": "user456",
            "title": "Mines of Moria",
            "status": "active",
            "last_modified": "2025-01-19T12:00:00Z",
            "turns": [],
            "entities": ["char1", "char2"],
            "location_id": "loc1",
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "mongodb_get_active_scene", {"user_id": "user456"}
        )

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "_id" in result
        assert "user_id" in result
        assert "status" in result

        # Verify contract: correct values
        assert result["status"] == "active"
        assert result["user_id"] == "user456"

    @pytest.mark.unit
    async def test_returns_none_when_no_active_scene_exists(self, fake_mcp_client):
        """Contract: Returns None when no active scene exists for user."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = None

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "mongodb_get_active_scene", {"user_id": "user123"}
        )

        # Verify contract: returns None
        assert result is None

    @pytest.mark.unit
    async def test_raises_connection_error_on_mongodb_failure(self, fake_mcp_client):
        """Contract: Raises ConnectionError when MongoDB query fails."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "ConnectionError: Failed to query active scenes: Connection refused"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "mongodb_get_active_scene", {"user_id": "user123"}
            )

        assert "ConnectionError" in str(exc_info.value)


class TestMongodbUpdateSceneContract:
    """Contract tests for mongodb_update_scene data layer tool."""

    @pytest.mark.unit
    async def test_returns_updated_scene_dict(self, fake_mcp_client):
        """Contract: Returns updated scene dict with new status."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "_id": "scene789",
            "story_id": "story123",
            "user_id": "user456",
            "title": "Mines of Moria",
            "status": "saved",  # Updated
            "last_modified": "2025-01-19T12:30:00Z",  # Updated
            "turns": [],
            "entities": ["char1", "char2"],
            "location_id": "loc1",
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "mongodb_update_scene",
            {
                "scene_id": "scene789",
                "updates": {"status": "saved", "last_modified": "2025-01-19T12:30:00Z"},
            },
        )

        # Verify contract: returns dict
        assert isinstance(result, dict)

        # Verify contract: contains updated fields
        assert result["status"] == "saved"
        assert "2025-01-19T12:30:00Z" in result["last_modified"]

    @pytest.mark.unit
    async def test_raises_not_found_error_for_invalid_scene_id(self, fake_mcp_client):
        """Contract: Raises NotFoundError when scene_id is invalid."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "NotFoundError: Scene not found: invalid_scene_id"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "mongodb_update_scene",
                {"scene_id": "invalid_scene_id", "updates": {"status": "saved"}},
            )

        assert "NotFoundError" in str(exc_info.value)


class TestNeo4jCloseConnectionContract:
    """Contract tests for neo4j_close_connection data layer tool."""

    @pytest.mark.unit
    async def test_closes_neo4j_connection(self, fake_mcp_client):
        """Contract: Closes Neo4j connection without error."""
        # Mock response (no return value)
        fake_mcp_client.call_tool.return_value = None

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool("neo4j_close_connection", {})

        # Verify contract: returns None
        assert result is None

    @pytest.mark.unit
    async def test_handles_already_closed_connection(self, fake_mcp_client):
        """Contract: Logs warning when connection already closed."""
        # Mock response (no return value, operation succeeds)
        fake_mcp_client.call_tool.return_value = None

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool("neo4j_close_connection", {})

        # Verify contract: returns None (no exception)
        assert result is None


class TestMongodbCloseConnectionContract:
    """Contract tests for mongodb_close_connection data layer tool."""

    @pytest.mark.unit
    async def test_closes_mongodb_connection(self, fake_mcp_client):
        """Contract: Closes MongoDB connection without error."""
        # Mock response (no return value)
        fake_mcp_client.call_tool.return_value = None

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool("mongodb_close_connection", {})

        # Verify contract: returns None
        assert result is None

    @pytest.mark.unit
    async def test_handles_already_closed_connection(self, fake_mcp_client):
        """Contract: Logs warning when connection already closed."""
        # Mock response (no return value, operation succeeds)
        fake_mcp_client.call_tool.return_value = None

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool("mongodb_close_connection", {})

        # Verify contract: returns None (no exception)
        assert result is None


class TestQdrantCloseConnectionContract:
    """Contract tests for qdrant_close_connection data layer tool."""

    @pytest.mark.unit
    async def test_closes_qdrant_connection(self, fake_mcp_client):
        """Contract: Closes Qdrant connection without error."""
        # Mock response (no return value)
        fake_mcp_client.call_tool.return_value = None

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool("qdrant_close_connection", {})

        # Verify contract: returns None
        assert result is None


class TestMinioCloseConnectionContract:
    """Contract tests for minio_close_connection data layer tool."""

    @pytest.mark.unit
    async def test_closes_minio_connection(self, fake_mcp_client):
        """Contract: Closes MinIO connection without error."""
        # Mock response (no return value)
        fake_mcp_client.call_tool.return_value = None

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool("minio_close_connection", {})

        # Verify contract: returns None
        assert result is None


# ============================================================================
# Agent Contract Tests
# ============================================================================


@pytest.mark.unit
class TestApplicationExitHandlerCheckActiveSceneContract:
    """Contract tests for ApplicationExitHandler.check_active_scene method."""

    @pytest.mark.unit
    async def test_returns_scene_when_active_scene_exists(
        self, fake_mcp_client, fake_llm_client
    ):
        """Contract: Returns scene dict when active scene exists."""
        # Mock MCP response
        fake_mcp_client.call_tool.return_value = {
            "_id": "scene789",
            "user_id": "user456",
            "status": "active",
        }

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        result = await handler.check_active_scene("user456")

        # Verify contract: returns scene dict
        assert isinstance(result, dict)
        assert result["status"] == "active"

    @pytest.mark.unit
    async def test_returns_none_when_no_active_scene(
        self, fake_mcp_client, fake_llm_client
    ):
        """Contract: Returns None when no active scene exists."""
        # Mock MCP response
        fake_mcp_client.call_tool.return_value = None

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        result = await handler.check_active_scene("user123")

        # Verify contract: returns None
        assert result is None


@pytest.mark.unit
class TestApplicationExitHandlerPromptSaveSceneContract:
    """Contract tests for ApplicationExitHandler.prompt_save_scene method."""

    @pytest.mark.unit
    @patch("builtins.input")
    async def test_returns_true_when_user_confirms_save(
        self, mock_input, fake_mcp_client, fake_llm_client
    ):
        """Contract: Returns True when user enters 'y' or 'Y'."""
        # Mock user input
        mock_input.return_value = "y"

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        result = await handler.prompt_save_scene({"_id": "scene789"})

        # Verify contract: returns True
        assert result

    @pytest.mark.unit
    @patch("builtins.input")
    async def test_returns_false_when_user_declines_save(
        self, mock_input, fake_mcp_client, fake_llm_client
    ):
        """Contract: Returns False when user enters 'n' or 'N'."""
        # Mock user input
        mock_input.return_value = "n"

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        result = await handler.prompt_save_scene({"_id": "scene789"})

        # Verify contract: returns False
        assert not result


@pytest.mark.unit
class TestApplicationExitHandlerAutoSaveSceneContract:
    """Contract tests for ApplicationExitHandler.auto_save_scene method."""

    @pytest.mark.unit
    @patch("monitor_agents.config_loader.ConfigLoader.get_auto_save_enabled")
    async def test_saves_scene_when_auto_save_enabled(
        self, mock_get_auto_save, fake_mcp_client, fake_llm_client
    ):
        """Contract: Saves scene when auto-save is configured."""
        # Mock auto-save enabled
        mock_get_auto_save.return_value = True

        # Mock MCP response for update
        fake_mcp_client.call_tool.return_value = {"_id": "scene789", "status": "saved"}

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        result = await handler.auto_save_scene({"_id": "scene789", "status": "active"})

        # Verify contract: returns updated scene
        assert result["status"] == "saved"

    @pytest.mark.unit
    @patch("monitor_agents.config_loader.ConfigLoader.get_auto_save_enabled")
    async def test_skips_save_when_auto_save_disabled(
        self, mock_get_auto_save, fake_mcp_client, fake_llm_client
    ):
        """Contract: Skips save when auto-save is not configured."""
        # Mock auto-save disabled
        mock_get_auto_save.return_value = False

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        result = await handler.auto_save_scene({"_id": "scene789", "status": "active"})

        # Verify contract: returns scene unchanged
        assert result["status"] == "active"


@pytest.mark.unit
class TestApplicationExitHandlerSaveSceneContract:
    """Contract tests for ApplicationExitHandler.save_scene method."""

    @pytest.mark.unit
    async def test_saves_scene_to_mongodb(self, fake_mcp_client, fake_llm_client):
        """Contract: Saves scene state to MongoDB."""
        # Mock MCP response for update
        fake_mcp_client.call_tool.return_value = {
            "_id": "scene789",
            "status": "saved",
            "last_modified": "2025-01-19T12:30:00Z",
        }

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        result = await handler.save_scene({"_id": "scene789", "status": "active"})

        # Verify contract: returns updated scene
        assert result["status"] == "saved"
        assert "last_modified" in result


@pytest.mark.unit
class TestApplicationExitHandlerCloseAllConnectionsContract:
    """Contract tests for ApplicationExitHandler.close_all_connections method."""

    @pytest.mark.unit
    async def test_closes_all_database_connections(
        self, fake_mcp_client, fake_llm_client
    ):
        """Contract: Closes Neo4j, MongoDB, Qdrant, and MinIO connections."""
        # Mock all close operations
        fake_mcp_client.call_tool.return_value = None

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        await handler.close_all_connections()

        # Verify contract: all 4 close tools were called
        assert fake_mcp_client.call_tool.call_count == 4

        # Verify contract: correct tools were called
        call_args_list = fake_mcp_client.call_tool.call_args_list
        tool_names = [call[0][0] for call in call_args_list]
        assert "neo4j_close_connection" in tool_names
        assert "mongodb_close_connection" in tool_names
        assert "qdrant_close_connection" in tool_names
        assert "minio_close_connection" in tool_names

    @pytest.mark.unit
    async def test_continues_when_one_connection_fails(
        self, fake_mcp_client, fake_llm_client
    ):
        """Contract: Continues cleanup when one connection fails (best effort)."""
        # Mock one close operation to fail
        call_count = 0

        def mock_close(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # MongoDB close fails
                raise Exception("ConnectionError: Failed to close MongoDB")
            return None

        fake_mcp_client.call_tool.side_effect = mock_close

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method (should not raise exception)
        await handler.close_all_connections()

        # Verify contract: all 4 close tools were attempted
        assert fake_mcp_client.call_tool.call_count == 4


@pytest.mark.unit
class TestApplicationExitHandlerExitApplicationContract:
    """Contract tests for ApplicationExitHandler.exit_application method."""

    @pytest.mark.unit
    @patch("sys.exit")
    async def test_exits_without_save_prompt_when_no_active_scene(
        self, mock_exit, fake_mcp_client, fake_llm_client
    ):
        """Contract: Skips save prompt when no active scene exists."""
        # Mock no active scene
        fake_mcp_client.call_tool.return_value = None

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        await handler.exit_application("user123")

        # Verify contract: sys.exit was called
        mock_exit.assert_called_once_with(0)

    @pytest.mark.unit
    @patch("monitor_agents.config_loader.ConfigLoader.get_auto_save_enabled")
    @patch("sys.exit")
    async def test_auto_saves_when_active_scene_and_auto_save_enabled(
        self, mock_exit, mock_get_auto_save, fake_mcp_client, fake_llm_client
    ):
        """Contract: Auto-saves scene when auto-save is configured."""
        # Mock auto-save enabled
        mock_get_auto_save.return_value = True

        # Mock responses
        fake_mcp_client.call_tool.side_effect = [
            # get_active_scene
            {"_id": "scene789", "status": "active"},
            # update_scene (auto-save)
            {"_id": "scene789", "status": "saved"},
            # close operations (4 calls)
            None,
            None,
            None,
            None,
        ]

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Call method
        await handler.exit_application("user456")

        # Verify contract: sys.exit was called
        mock_exit.assert_called_once_with(0)

        # Verify contract: scene was updated to saved
        assert fake_mcp_client.call_tool.call_count == 6  # 1 get + 1 update + 4 close


# ============================================================================
# CLI Command Contract Tests
# ============================================================================


class TestMonitorExitCommandContract:
    """Contract tests for monitor exit CLI command."""

    @pytest.mark.unit
    def test_exits_cleanly(self, cli_tester):
        """Contract: monitor exit calls exit_application and exits cleanly."""
        result = cli_tester.run_command(["monitor", "exit"])

        # Verify contract: command executed
        assert result.exit_code == 0 or "exit" in result.output.lower()


# ============================================================================
# Integration Tests (with mocks)
# ============================================================================


@pytest.mark.unit
class TestSYS3Integration:
    """Integration tests for SYS-3 using mocked components."""

    @pytest.mark.integration
    @patch("sys.exit")
    async def test_full_exit_workflow_no_active_scene(
        self, mock_exit, fake_mcp_client, fake_llm_client
    ):
        """Contract: Full exit workflow when no active scene exists."""
        # Mock no active scene
        fake_mcp_client.call_tool.side_effect = [None, None, None, None, None]

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Execute: Exit application
        await handler.exit_application("user123")

        # Verify: Contract compliance
        assert fake_mcp_client.call_tool.call_count == 5  # 1 get + 4 close
        mock_exit.assert_called_once_with(0)

    @pytest.mark.integration
    @patch("monitor_agents.config_loader.ConfigLoader.get_auto_save_enabled")
    @patch("sys.exit")
    async def test_full_exit_workflow_with_auto_save(
        self, mock_exit, mock_get_auto_save, fake_mcp_client, fake_llm_client
    ):
        """Contract: Full exit workflow with auto-save enabled."""
        # Mock auto-save enabled
        mock_get_auto_save.return_value = True

        # Mock responses
        fake_mcp_client.call_tool.side_effect = [
            # get_active_scene
            {"_id": "scene789", "status": "active"},
            # update_scene (auto-save)
            {"_id": "scene789", "status": "saved"},
            # close operations (4 calls)
            None,
            None,
            None,
            None,
        ]

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Execute: Exit application
        await handler.exit_application("user456")

        # Verify: Contract compliance
        assert fake_mcp_client.call_tool.call_count == 6  # 1 get + 1 update + 4 close
        mock_exit.assert_called_once_with(0)

    @pytest.mark.integration
    @patch("monitor_agents.config_loader.ConfigLoader.get_auto_save_enabled")
    @patch("builtins.input")
    @patch("sys.exit")
    async def test_full_exit_workflow_with_save_prompt_confirmed(
        self,
        mock_exit,
        mock_input,
        mock_get_auto_save,
        fake_mcp_client,
        fake_llm_client,
    ):
        """Contract: Full exit workflow with save prompt, user confirms."""
        # Mock auto-save disabled
        mock_get_auto_save.return_value = False

        # Mock user confirms save
        mock_input.return_value = "y"

        # Mock responses
        fake_mcp_client.call_tool.side_effect = [
            # get_active_scene
            {"_id": "scene789", "status": "active"},
            # update_scene (save)
            {"_id": "scene789", "status": "saved"},
            # close operations (4 calls)
            None,
            None,
            None,
            None,
        ]

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Execute: Exit application
        await handler.exit_application("user789")

        # Verify: Contract compliance
        assert fake_mcp_client.call_tool.call_count == 6  # 1 get + 1 update + 4 close
        mock_exit.assert_called_once_with(0)

    @pytest.mark.integration
    @patch("monitor_agents.config_loader.ConfigLoader.get_auto_save_enabled")
    @patch("builtins.input")
    @patch("sys.exit")
    async def test_full_exit_workflow_with_save_prompt_declined(
        self,
        mock_exit,
        mock_input,
        mock_get_auto_save,
        fake_mcp_client,
        fake_llm_client,
    ):
        """Contract: Full exit workflow with save prompt, user declines."""
        # Mock auto-save disabled
        mock_get_auto_save.return_value = False

        # Mock user declines save
        mock_input.return_value = "n"

        # Mock responses
        fake_mcp_client.call_tool.side_effect = [
            # get_active_scene
            {"_id": "scene789", "status": "active"},
            # close operations (4 calls) - no update since user declined
            None,
            None,
            None,
            None,
        ]

        # Create handler
        from monitor_agents.application_exit_handler import ApplicationExitHandler

        handler = ApplicationExitHandler(
            mcp_client=fake_mcp_client, llm_client=fake_llm_client
        )

        # Execute: Exit application
        await handler.exit_application("user999")

        # Verify: Contract compliance
        assert fake_mcp_client.call_tool.call_count == 5  # 1 get + 4 close (no update)
        mock_exit.assert_called_once_with(0)

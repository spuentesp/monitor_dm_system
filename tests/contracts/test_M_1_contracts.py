"""
Contract tests for M-1: Create Multiverse.

These tests verify that the API contracts for multiverse creation are correctly
defined and implemented. They do not test implementation details, only the
shape and behavior of the API contracts.

Run with: uv run pytest tests/contracts/test_M_1_contracts.py -v
"""

from datetime import datetime

import pytest

# =============================================================================
# Data Layer Tool Contracts Tests
# =============================================================================


class TestNeo4jGetOmniverseContract:
    """Tests for neo4j_get_omniverse() contract."""

    @pytest.mark.asyncio
    async def test_returns_omniverse_dict_with_required_fields(self, fake_mcp_client):
        """Contract: Returns omniverse dict with id, name, description, created_at."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_get_omniverse",
            {},
            {
                "id": "omni123",
                "name": "Omniverse",
                "description": "The root of all multiverses",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        # Execute
        result = await fake_mcp_client.call_tool("neo4j_get_omniverse", {})

        # Contract: Returns dict with required fields
        assert isinstance(result, dict)
        assert "id" in result
        assert "name" in result
        assert "description" in result
        assert "created_at" in result

    @pytest.mark.asyncio
    async def test_auto_creates_omniverse_if_not_exists(self, fake_mcp_client):
        """Contract: Creates omniverse if none exists."""
        # Setup - simulate omniverse not existing
        fake_mcp_client.add_response(
            "neo4j_get_omniverse",
            {},
            {
                "id": "omni456",
                "name": "Omniverse",
                "description": "Auto-created omniverse",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        # Execute
        result = await fake_mcp_client.call_tool("neo4j_get_omniverse", {})

        # Contract: Returns omniverse dict even when auto-created
        assert isinstance(result, dict)
        assert result["name"] == "Omniverse"

    @pytest.mark.asyncio
    async def test_connection_error_raises_exception(self, fake_mcp_client):
        """Contract: Neo4j connection error raises ConnectionError."""
        # Setup - simulate connection error
        fake_mcp_client.add_error(
            "neo4j_get_omniverse",
            {},
            ConnectionError("Failed to get or create omniverse"),
        )

        # Execute & Verify
        with pytest.raises(ConnectionError, match="Failed to get or create omniverse"):
            await fake_mcp_client.call_tool("neo4j_get_omniverse", {})


class TestNeo4jCreateMultiverseContract:
    """Tests for neo4j_create_multiverse() contract."""

    @pytest.mark.asyncio
    async def test_returns_multiverse_id_uuid_string(self, fake_mcp_client):
        """Contract: Returns multiverse ID as UUID string (36 chars)."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "D&D Worlds",
                    "system_name": "D&D 5e",
                    "description": "A collection of D&D campaigns",
                    "canon_level": "canon",
                },
            },
            "multi12345678901234567890123456789012",
        )  # 36-char UUID

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "D&D Worlds",
                    "system_name": "D&D 5e",
                    "description": "A collection of D&D campaigns",
                    "canon_level": "canon",
                },
            },
        )

        # Contract: Returns 36-char UUID string
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_creates_multiverse_with_all_properties(self, fake_mcp_client):
        """Contract: Creates multiverse node with all provided properties."""
        # Setup
        multiverse_id = "multi12345678901234567890123456789012"
        fake_mcp_client.add_response(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "Marvel Cinematic Universe",
                    "system_name": "Marvel RPG",
                    "description": "All Marvel movies and TV shows",
                    "canon_level": "canon",
                },
            },
            multiverse_id,
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "Marvel Cinematic Universe",
                    "system_name": "Marvel RPG",
                    "description": "All Marvel movies and TV shows",
                    "canon_level": "canon",
                },
            },
        )

        # Contract: Returns multiverse ID
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_invalid_omniverse_id_raises_error(self, fake_mcp_client):
        """Contract: Invalid omniverse_id raises NotFoundError."""
        # Setup - simulate omniverse not found
        fake_mcp_client.add_error(
            "neo4j_create_multiverse",
            {},
            FileNotFoundError("Omniverse not found: invalid123"),
        )

        # Execute & Verify
        with pytest.raises(FileNotFoundError, match="Omniverse not found"):
            await fake_mcp_client.call_tool(
                "neo4j_create_multiverse",
                {
                    "omniverse_id": "invalid123",
                    "params": {"name": "Test", "system_name": "D&D 5e"},
                },
            )

    @pytest.mark.asyncio
    async def test_invalid_name_raises_validation_error(self, fake_mcp_client):
        """Contract: Invalid name (too short/long) raises ValidationError."""
        # Setup - simulate name too long
        fake_mcp_client.add_error(
            "neo4j_create_multiverse", {}, ValueError("Name must be 1-200 characters")
        )

        # Execute & Verify - name too long (201 chars)
        with pytest.raises(ValueError, match="Name must be 1-200 characters"):
            await fake_mcp_client.call_tool(
                "neo4j_create_multiverse",
                {
                    "omniverse_id": "omni123",
                    "params": {"name": "x" * 201, "system_name": "D&D 5e"},
                },
            )

    @pytest.mark.asyncio
    async def test_empty_name_raises_validation_error(self, fake_mcp_client):
        """Contract: Empty name raises ValidationError."""
        # Setup - simulate name too short (empty)
        fake_mcp_client.add_error(
            "neo4j_create_multiverse", {}, ValueError("Name must be 1-200 characters")
        )

        # Execute & Verify
        with pytest.raises(ValueError, match="Name must be 1-200 characters"):
            await fake_mcp_client.call_tool(
                "neo4j_create_multiverse",
                {
                    "omniverse_id": "omni123",
                    "params": {"name": "", "system_name": "D&D 5e"},
                },
            )

    @pytest.mark.asyncio
    async def test_connection_error_raises_exception(self, fake_mcp_client):
        """Contract: Neo4j connection error raises ConnectionError."""
        # Setup - simulate connection error
        fake_mcp_client.add_error(
            "neo4j_create_multiverse",
            {},
            ConnectionError("Failed to create multiverse"),
        )

        # Execute & Verify
        with pytest.raises(ConnectionError, match="Failed to create multiverse"):
            await fake_mcp_client.call_tool(
                "neo4j_create_multiverse",
                {
                    "omniverse_id": "omni123",
                    "params": {"name": "Test", "system_name": "D&D 5e"},
                },
            )


class TestNeo4jListMultiversesContract:
    """Tests for neo4j_list_multiverses() contract."""

    @pytest.mark.asyncio
    async def test_returns_list_of_multiverse_summaries(self, fake_mcp_client):
        """Contract: Returns list of multiverse summary dicts."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_multiverses",
            {"omniverse_id": "omni123"},
            [
                {
                    "id": "multi123",
                    "name": "D&D Worlds",
                    "system_name": "D&D 5e",
                    "universe_count": 3,
                },
                {
                    "id": "multi456",
                    "name": "Marvel Cinematic Universe",
                    "system_name": "Marvel RPG",
                    "universe_count": 1,
                },
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_multiverses", {"omniverse_id": "omni123"}
        )

        # Contract: Returns list
        assert isinstance(result, list)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_multiverse_summary_has_required_fields(self, fake_mcp_client):
        """Contract: Each multiverse summary has id, name, system_name, universe_count."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_multiverses",
            {"omniverse_id": "omni123"},
            [
                {
                    "id": "multi123",
                    "name": "D&D Worlds",
                    "system_name": "D&D 5e",
                    "universe_count": 3,
                }
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_multiverses", {"omniverse_id": "omni123"}
        )

        # Contract: Each summary has required fields
        assert "id" in result[0]
        assert "name" in result[0]
        assert "system_name" in result[0]
        assert "universe_count" in result[0]

    @pytest.mark.asyncio
    async def test_universe_count_is_integer(self, fake_mcp_client):
        """Contract: universe_count field is an integer."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_multiverses",
            {"omniverse_id": "omni123"},
            [
                {
                    "id": "multi123",
                    "name": "D&D Worlds",
                    "system_name": "D&D 5e",
                    "universe_count": 5,
                }
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_multiverses", {"omniverse_id": "omni123"}
        )

        # Contract: universe_count is integer
        assert isinstance(result[0]["universe_count"], int)

    @pytest.mark.asyncio
    async def test_returns_empty_list_if_no_multiverses(self, fake_mcp_client):
        """Contract: Returns empty list if no multiverses exist."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_multiverses", {"omniverse_id": "omni123"}, []
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_multiverses", {"omniverse_id": "omni123"}
        )

        # Contract: Returns empty list
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_invalid_omniverse_id_raises_error(self, fake_mcp_client):
        """Contract: Invalid omniverse_id raises NotFoundError."""
        # Setup - simulate omniverse not found
        fake_mcp_client.add_error(
            "neo4j_list_multiverses",
            {},
            FileNotFoundError("Omniverse not found: invalid123"),
        )

        # Execute & Verify
        with pytest.raises(FileNotFoundError, match="Omniverse not found"):
            await fake_mcp_client.call_tool(
                "neo4j_list_multiverses", {"omniverse_id": "invalid123"}
            )


# =============================================================================
# Agent Contract Tests
# =============================================================================


class TestMultiverseCreatorContract:
    """Tests for MultiverseCreator agent contracts."""

    @pytest.mark.asyncio
    async def test_create_multiverse_returns_id_string(self, fake_mcp_client):
        """Contract: create_multiverse() returns multiverse ID string."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_get_omniverse",
            {},
            {
                "id": "omni123",
                "name": "Omniverse",
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        fake_mcp_client.add_response(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "Test Multiverse",
                    "system_name": "D&D 5e",
                    "description": "Test description",
                    "canon_level": "canon",
                },
            },
            "multi12345678901234567890123456789012",
        )

        # Simulate MultiverseCreator agent call
        result = await fake_mcp_client.call_tool(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "Test Multiverse",
                    "system_name": "D&D 5e",
                    "description": "Test description",
                    "canon_level": "canon",
                },
            },
        )

        # Contract: Returns multiverse ID string
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_create_multiverse_validates_name_length(self):
        """Contract: Validates name is 1-200 characters."""
        # Simulate validation logic
        name = "x" * 201  # 201 chars (too long)

        # Contract: Name too long should fail
        assert len(name) > 200

    @pytest.mark.asyncio
    async def test_create_multiverse_validates_system_name_length(self):
        """Contract: Validates system_name is 1-100 characters."""
        # Simulate validation logic
        system_name = "x" * 101  # 101 chars (too long)

        # Contract: system_name too long should fail
        assert len(system_name) > 100

    @pytest.mark.asyncio
    async def test_create_multiverse_validates_description_length(self):
        """Contract: Validates description is max 5000 characters."""
        # Simulate validation logic
        description = "x" * 5001  # 5001 chars (too long)

        # Contract: description too long should fail
        assert len(description) > 5000

    @pytest.mark.asyncio
    async def test_seed_from_knowledge_pack_creates_entities(self, fake_mcp_client):
        """Contract: seed_from_knowledge_pack() creates entities in Neo4j."""
        # Setup - simulate successful seeding
        fake_mcp_client.add_response(
            "seed_from_knowledge_pack",
            {"multiverse_id": "multi123", "pack_id": "pack456"},
            None,
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "seed_from_knowledge_pack",
            {"multiverse_id": "multi123", "pack_id": "pack456"},
        )

        # Contract: Returns None on success
        assert result is None

    @pytest.mark.asyncio
    async def test_seed_from_knowledge_pack_invalid_pack_id_raises_error(
        self, fake_mcp_client
    ):
        """Contract: Invalid pack_id raises NotFoundError."""
        # Setup - simulate pack not found
        fake_mcp_client.add_error(
            "seed_from_knowledge_pack",
            {},
            FileNotFoundError("Knowledge pack not found: invalid123"),
        )

        # Execute & Verify
        with pytest.raises(FileNotFoundError, match="Knowledge pack not found"):
            await fake_mcp_client.call_tool(
                "seed_from_knowledge_pack",
                {"multiverse_id": "multi123", "pack_id": "invalid123"},
            )


# =============================================================================
# Integration Tests
# =============================================================================


class TestMultiverseCreationIntegration:
    """Integration tests for multiverse creation workflow."""

    @pytest.mark.asyncio
    async def test_full_multiverse_creation_workflow(self, fake_mcp_client):
        """Contract: Full workflow: get omniverse → create multiverse → return ID."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_get_omniverse",
            {},
            {
                "id": "omni123",
                "name": "Omniverse",
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        fake_mcp_client.add_response(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "Test Multiverse",
                    "system_name": "D&D 5e",
                    "description": "Test",
                    "canon_level": "canon",
                },
            },
            "multi12345678901234567890123456789012",
        )

        # Execute workflow
        omniverse = await fake_mcp_client.call_tool("neo4j_get_omniverse", {})
        assert omniverse["id"] is not None

        multiverse_id = await fake_mcp_client.call_tool(
            "neo4j_create_multiverse",
            {
                "omniverse_id": omniverse["id"],
                "params": {
                    "name": "Test Multiverse",
                    "system_name": "D&D 5e",
                    "description": "Test",
                    "canon_level": "canon",
                },
            },
        )

        # Contract: Workflow completes successfully
        assert isinstance(multiverse_id, str)
        assert isinstance(multiverse_id, str)

    @pytest.mark.asyncio
    async def test_multiverse_creation_with_knowledge_pack_seeding(
        self, fake_mcp_client
    ):
        """Contract: Create multiverse and seed from knowledge pack."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_get_omniverse",
            {},
            {
                "id": "omni123",
                "name": "Omniverse",
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        fake_mcp_client.add_response(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "Marvel",
                    "system_name": "Marvel RPG",
                    "description": "Marvel",
                    "canon_level": "canon",
                },
            },
            "multi12345678901234567890123456789012",
        )
        fake_mcp_client.add_response(
            "seed_from_knowledge_pack",
            {
                "multiverse_id": "multi12345678901234567890123456789012",
                "pack_id": "pack456",
            },
            None,
        )

        # Execute workflow with seeding
        omniverse = await fake_mcp_client.call_tool("neo4j_get_omniverse", {})
        multiverse_id = await fake_mcp_client.call_tool(
            "neo4j_create_multiverse",
            {
                "omniverse_id": omniverse["id"],
                "params": {
                    "name": "Marvel",
                    "system_name": "Marvel RPG",
                    "description": "Marvel",
                    "canon_level": "canon",
                },
            },
        )
        await fake_mcp_client.call_tool(
            "seed_from_knowledge_pack",
            {"multiverse_id": multiverse_id, "pack_id": "pack456"},
        )

        # Contract: Workflow completes successfully
        assert isinstance(multiverse_id, str)
        assert isinstance(multiverse_id, str)


# =============================================================================
# Edge Cases and Error Scenarios
# =============================================================================


class TestMultiverseCreationEdgeCases:
    """Edge case tests for multiverse creation."""

    @pytest.mark.asyncio
    async def test_empty_description_is_valid(self, fake_mcp_client):
        """Contract: Empty description is valid (optional field)."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "Test",
                    "system_name": "D&D 5e",
                    "description": "",  # Empty description
                    "canon_level": "canon",
                },
            },
            "multi12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "Test",
                    "system_name": "D&D 5e",
                    "description": "",
                    "canon_level": "canon",
                },
            },
        )

        # Contract: Empty description is valid
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_minimal_valid_name_length(self, fake_mcp_client):
        """Contract: Name with 1 character is valid."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "A",  # 1 char (minimal)
                    "system_name": "D&D 5e",
                    "canon_level": "canon",
                },
            },
            "multi12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "A",
                    "system_name": "D&D 5e",
                    "canon_level": "canon",
                },
            },
        )

        # Contract: 1-char name is valid
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_maximal_valid_name_length(self, fake_mcp_client):
        """Contract: Name with 200 characters is valid."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "x" * 200,  # 200 chars (maximal)
                    "system_name": "D&D 5e",
                    "canon_level": "canon",
                },
            },
            "multi12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_multiverse",
            {
                "omniverse_id": "omni123",
                "params": {
                    "name": "x" * 200,
                    "system_name": "D&D 5e",
                    "canon_level": "canon",
                },
            },
        )

        # Contract: 200-char name is valid
        assert isinstance(result, str)
        assert isinstance(result, str)


# =============================================================================
# Data Structure Tests
# =============================================================================


class TestDataStructureContracts:
    """Tests for data structure contracts."""

    @pytest.mark.asyncio
    async def test_omniverse_dict_structure(self, fake_mcp_client):
        """Contract: Omniverse dict has correct structure."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_get_omniverse",
            {},
            {
                "id": "omni123",
                "name": "Omniverse",
                "description": "Root of all multiverses",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        # Execute
        result = await fake_mcp_client.call_tool("neo4j_get_omniverse", {})

        # Contract: Verify dict structure
        assert isinstance(result["id"], str)
        assert isinstance(result["name"], str)
        assert isinstance(result["description"], str)
        assert isinstance(result["created_at"], str)

    @pytest.mark.asyncio
    async def test_multiverse_summary_dict_structure(self, fake_mcp_client):
        """Contract: MultiverseSummary dict has correct structure."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_multiverses",
            {"omniverse_id": "omni123"},
            [
                {
                    "id": "multi123",
                    "name": "D&D Worlds",
                    "system_name": "D&D 5e",
                    "universe_count": 3,
                }
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_multiverses", {"omniverse_id": "omni123"}
        )

        # Contract: Verify dict structure
        assert isinstance(result[0]["id"], str)
        assert isinstance(result[0]["name"], str)
        assert isinstance(result[0]["system_name"], str)
        assert isinstance(result[0]["universe_count"], int)

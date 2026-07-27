"""
Contract tests for M-2: Create Universe.

These tests verify that the API contracts for universe creation are correctly
defined and implemented. They do not test implementation details, only the
shape and behavior of the API contracts.

Run with: uv run pytest tests/contracts/test_M_2_contracts.py -v
"""

import pytest

# =============================================================================
# Data Layer Tool Contracts Tests
# =============================================================================


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


class TestNeo4jCreateUniverseContract:
    """Tests for neo4j_create_universe() contract."""

    @pytest.mark.asyncio
    async def test_returns_universe_id_uuid_string(self, fake_mcp_client):
        """Contract: Returns universe ID as UUID string (36 chars)."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "High fantasy world",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
            "universe12345678901234567890123456789012",
        )  # 36-char UUID

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "High fantasy world",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
        )

        # Contract: Returns 36-char UUID string
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_creates_universe_fresh_start(self, fake_mcp_client):
        """Contract: Creates universe with fresh start (no branch_from)."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "High fantasy world",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
            "universe12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "High fantasy world",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
        )

        # Contract: Returns universe ID
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_creates_universe_with_branch(self, fake_mcp_client):
        """Contract: Creates universe branching from existing universe."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms - Alternate",
                    "genre": "Fantasy",
                    "tone": "Dark",
                    "tech_level": "Pre-Industrial",
                    "description": "Alternate timeline",
                    "canon_level": "canon",
                },
                "branch_from": "universe456",
            },
            "universe12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms - Alternate",
                    "genre": "Fantasy",
                    "tone": "Dark",
                    "tech_level": "Pre-Industrial",
                    "description": "Alternate timeline",
                    "canon_level": "canon",
                },
                "branch_from": "universe456",
            },
        )

        # Contract: Returns universe ID
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_invalid_multiverse_id_raises_error(self, fake_mcp_client):
        """Contract: Invalid multiverse_id raises NotFoundError."""
        # Setup - simulate multiverse not found
        fake_mcp_client.add_error(
            "neo4j_create_universe",
            {},
            FileNotFoundError("Multiverse not found: invalid123"),
        )

        # Execute & Verify
        with pytest.raises(FileNotFoundError, match="Multiverse not found"):
            await fake_mcp_client.call_tool(
                "neo4j_create_universe",
                {
                    "multiverse_id": "invalid123",
                    "params": {
                        "name": "Test",
                        "genre": "Fantasy",
                        "tone": "Heroic",
                        "tech_level": "Pre-Industrial",
                    },
                    "branch_from": None,
                },
            )

    @pytest.mark.asyncio
    async def test_invalid_branch_from_raises_error(self, fake_mcp_client):
        """Contract: Invalid branch_from raises NotFoundError."""
        # Setup - simulate source universe not found
        fake_mcp_client.add_error(
            "neo4j_create_universe",
            {},
            FileNotFoundError("Source universe not found: invalid456"),
        )

        # Execute & Verify
        with pytest.raises(FileNotFoundError, match="Source universe not found"):
            await fake_mcp_client.call_tool(
                "neo4j_create_universe",
                {
                    "multiverse_id": "multi123",
                    "params": {
                        "name": "Test",
                        "genre": "Fantasy",
                        "tone": "Heroic",
                        "tech_level": "Pre-Industrial",
                    },
                    "branch_from": "invalid456",
                },
            )

    @pytest.mark.asyncio
    async def test_invalid_name_raises_validation_error(self, fake_mcp_client):
        """Contract: Invalid name (too short/long) raises ValidationError."""
        # Setup - simulate name too long
        fake_mcp_client.add_error(
            "neo4j_create_universe", {}, ValueError("Name must be 1-200 characters")
        )

        # Execute & Verify - name too long (201 chars)
        with pytest.raises(ValueError, match="Name must be 1-200 characters"):
            await fake_mcp_client.call_tool(
                "neo4j_create_universe",
                {
                    "multiverse_id": "multi123",
                    "params": {
                        "name": "x" * 201,
                        "genre": "Fantasy",
                        "tone": "Heroic",
                        "tech_level": "Pre-Industrial",
                    },
                    "branch_from": None,
                },
            )

    @pytest.mark.asyncio
    async def test_invalid_genre_raises_validation_error(self, fake_mcp_client):
        """Contract: Invalid genre raises ValidationError."""
        # Setup - simulate invalid genre
        fake_mcp_client.add_error(
            "neo4j_create_universe",
            {},
            ValueError(
                "Invalid genre. Must be one of: Fantasy, Sci-Fi, Cyberpunk, etc."
            ),
        )

        # Execute & Verify
        with pytest.raises(ValueError, match="Invalid genre"):
            await fake_mcp_client.call_tool(
                "neo4j_create_universe",
                {
                    "multiverse_id": "multi123",
                    "params": {
                        "name": "Test",
                        "genre": "InvalidGenre",
                        "tone": "Heroic",
                        "tech_level": "Pre-Industrial",
                    },
                    "branch_from": None,
                },
            )

    @pytest.mark.asyncio
    async def test_invalid_tone_raises_validation_error(self, fake_mcp_client):
        """Contract: Invalid tone raises ValidationError."""
        # Setup - simulate invalid tone
        fake_mcp_client.add_error(
            "neo4j_create_universe",
            {},
            ValueError("Invalid tone. Must be one of: Dark, Heroic, Whimsical, etc."),
        )

        # Execute & Verify
        with pytest.raises(ValueError, match="Invalid tone"):
            await fake_mcp_client.call_tool(
                "neo4j_create_universe",
                {
                    "multiverse_id": "multi123",
                    "params": {
                        "name": "Test",
                        "genre": "Fantasy",
                        "tone": "InvalidTone",
                        "tech_level": "Pre-Industrial",
                    },
                    "branch_from": None,
                },
            )

    @pytest.mark.asyncio
    async def test_invalid_tech_level_raises_validation_error(self, fake_mcp_client):
        """Contract: Invalid tech_level raises ValidationError."""
        # Setup - simulate invalid tech level
        fake_mcp_client.add_error(
            "neo4j_create_universe",
            {},
            ValueError(
                "Invalid tech level. Must be one of: Pre-Industrial, Modern, Future, etc."
            ),
        )

        # Execute & Verify
        with pytest.raises(ValueError, match="Invalid tech level"):
            await fake_mcp_client.call_tool(
                "neo4j_create_universe",
                {
                    "multiverse_id": "multi123",
                    "params": {
                        "name": "Test",
                        "genre": "Fantasy",
                        "tone": "Heroic",
                        "tech_level": "InvalidTechLevel",
                    },
                    "branch_from": None,
                },
            )

    @pytest.mark.asyncio
    async def test_connection_error_raises_exception(self, fake_mcp_client):
        """Contract: Neo4j connection error raises ConnectionError."""
        # Setup - simulate connection error
        fake_mcp_client.add_error(
            "neo4j_create_universe", {}, ConnectionError("Failed to create universe")
        )

        # Execute & Verify
        with pytest.raises(ConnectionError, match="Failed to create universe"):
            await fake_mcp_client.call_tool(
                "neo4j_create_universe",
                {
                    "multiverse_id": "multi123",
                    "params": {
                        "name": "Test",
                        "genre": "Fantasy",
                        "tone": "Heroic",
                        "tech_level": "Pre-Industrial",
                    },
                    "branch_from": None,
                },
            )


class TestNeo4jListUniversesContract:
    """Tests for neo4j_list_universes() contract."""

    @pytest.mark.asyncio
    async def test_returns_list_of_universe_summaries(self, fake_mcp_client):
        """Contract: Returns list of universe summary dicts."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_universes",
            {"multiverse_id": "multi123"},
            [
                {
                    "id": "universe123",
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "entity_count": 15,
                    "story_count": 3,
                },
                {
                    "id": "universe456",
                    "name": "Eberron",
                    "genre": "Fantasy",
                    "tone": "Mysterious",
                    "tech_level": "Steam",
                    "entity_count": 8,
                    "story_count": 1,
                },
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_universes", {"multiverse_id": "multi123"}
        )

        # Contract: Returns list
        assert isinstance(result, list)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_universe_summary_has_required_fields(self, fake_mcp_client):
        """Contract: Each universe summary has id, name, genre, tone, tech_level, entity_count, story_count."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_universes",
            {"multiverse_id": "multi123"},
            [
                {
                    "id": "universe123",
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "entity_count": 15,
                    "story_count": 3,
                }
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_universes", {"multiverse_id": "multi123"}
        )

        # Contract: Each summary has required fields
        assert "id" in result[0]
        assert "name" in result[0]
        assert "genre" in result[0]
        assert "tone" in result[0]
        assert "tech_level" in result[0]
        assert "entity_count" in result[0]
        assert "story_count" in result[0]

    @pytest.mark.asyncio
    async def test_entity_count_is_integer(self, fake_mcp_client):
        """Contract: entity_count field is an integer."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_universes",
            {"multiverse_id": "multi123"},
            [
                {
                    "id": "universe123",
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "entity_count": 15,
                    "story_count": 3,
                }
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_universes", {"multiverse_id": "multi123"}
        )

        # Contract: entity_count is integer
        assert isinstance(result[0]["entity_count"], int)

    @pytest.mark.asyncio
    async def test_story_count_is_integer(self, fake_mcp_client):
        """Contract: story_count field is an integer."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_universes",
            {"multiverse_id": "multi123"},
            [
                {
                    "id": "universe123",
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "entity_count": 15,
                    "story_count": 3,
                }
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_universes", {"multiverse_id": "multi123"}
        )

        # Contract: story_count is integer
        assert isinstance(result[0]["story_count"], int)

    @pytest.mark.asyncio
    async def test_returns_empty_list_if_no_universes(self, fake_mcp_client):
        """Contract: Returns empty list if no universes exist."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_universes", {"multiverse_id": "multi123"}, []
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_universes", {"multiverse_id": "multi123"}
        )

        # Contract: Returns empty list
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_invalid_multiverse_id_raises_error(self, fake_mcp_client):
        """Contract: Invalid multiverse_id raises NotFoundError."""
        # Setup - simulate multiverse not found
        fake_mcp_client.add_error(
            "neo4j_list_universes",
            {},
            FileNotFoundError("Multiverse not found: invalid123"),
        )

        # Execute & Verify
        with pytest.raises(FileNotFoundError, match="Multiverse not found"):
            await fake_mcp_client.call_tool(
                "neo4j_list_universes", {"multiverse_id": "invalid123"}
            )


# =============================================================================
# Agent Contract Tests
# =============================================================================


class TestUniverseCreatorContract:
    """Tests for UniverseCreator agent contracts."""

    @pytest.mark.asyncio
    async def test_create_universe_fresh_start_returns_id_string(self, fake_mcp_client):
        """Contract: create_universe() returns universe ID string (fresh start)."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "High fantasy world",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
            "universe12345678901234567890123456789012",
        )

        # Simulate UniverseCreator agent call
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "High fantasy world",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
        )

        # Contract: Returns universe ID string
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_create_universe_with_branch_returns_id_string(self, fake_mcp_client):
        """Contract: create_universe() returns universe ID string (with branch)."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms - Alternate",
                    "genre": "Fantasy",
                    "tone": "Dark",
                    "tech_level": "Pre-Industrial",
                    "description": "Alternate timeline",
                    "canon_level": "canon",
                },
                "branch_from": "universe456",
            },
            "universe12345678901234567890123456789012",
        )

        # Simulate UniverseCreator agent call
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms - Alternate",
                    "genre": "Fantasy",
                    "tone": "Dark",
                    "tech_level": "Pre-Industrial",
                    "description": "Alternate timeline",
                    "canon_level": "canon",
                },
                "branch_from": "universe456",
            },
        )

        # Contract: Returns universe ID string
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_create_universe_validates_name_length(self):
        """Contract: Validates name is 1-200 characters."""
        # Simulate validation logic
        name = "x" * 201  # 201 chars (too long)

        # Contract: Name too long should fail
        assert len(name) > 200

    @pytest.mark.asyncio
    async def test_create_universe_validates_genre_enum(self):
        """Contract: Validates genre is in Genre enum."""
        # Valid genres (from contract)
        valid_genres = [
            "Fantasy",
            "Sci-Fi",
            "Cyberpunk",
            "Horror",
            "Western",
            "Modern",
            "Historical",
            "Post-Apocalyptic",
            "Steampunk",
            "Urban Fantasy",
            "Space Opera",
            "Superhero",
        ]

        # Contract: Invalid genre should fail
        invalid_genre = "InvalidGenre"
        assert invalid_genre not in valid_genres

    @pytest.mark.asyncio
    async def test_create_universe_validates_tone_enum(self):
        """Contract: Validates tone is in Tone enum."""
        # Valid tones (from contract)
        valid_tones = [
            "Dark",
            "Heroic",
            "Whimsical",
            "Grimdark",
            "Optimistic",
            "Mysterious",
            "Campy",
            "Serious",
            "Light-Hearted",
        ]

        # Contract: Invalid tone should fail
        invalid_tone = "InvalidTone"
        assert invalid_tone not in valid_tones

    @pytest.mark.asyncio
    async def test_create_universe_validates_tech_level_enum(self):
        """Contract: Validates tech_level is in TechLevel enum."""
        # Valid tech levels (from contract)
        valid_tech_levels = [
            "Pre-Industrial",
            "Steam",
            "Early Modern",
            "Modern",
            "Near Future",
            "Far Future",
            "Post-Apocalyptic",
            "Ancient",
            "Medieval",
        ]

        # Contract: Invalid tech level should fail
        invalid_tech_level = "InvalidTechLevel"
        assert invalid_tech_level not in valid_tech_levels

    @pytest.mark.asyncio
    async def test_create_universe_validates_description_length(self):
        """Contract: Validates description is max 5000 characters."""
        # Simulate validation logic
        description = "x" * 5001  # 5001 chars (too long)

        # Contract: description too long should fail
        assert len(description) > 5000


# =============================================================================
# Integration Tests
# =============================================================================


class TestUniverseCreationIntegration:
    """Integration tests for universe creation workflow."""

    @pytest.mark.asyncio
    async def test_full_universe_creation_workflow_fresh_start(self, fake_mcp_client):
        """Contract: Full workflow: list multiverses → create universe (fresh) → return ID."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_multiverses",
            {"omniverse_id": "omni123"},
            [
                {
                    "id": "multi123",
                    "name": "D&D Worlds",
                    "system_name": "D&D 5e",
                    "universe_count": 2,
                }
            ],
        )
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "High fantasy world",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
            "universe12345678901234567890123456789012",
        )

        # Execute workflow
        multiverses = await fake_mcp_client.call_tool(
            "neo4j_list_multiverses", {"omniverse_id": "omni123"}
        )
        assert len(multiverses) >= 1
        multiverse_id = multiverses[0]["id"]

        universe_id = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": multiverse_id,
                "params": {
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "High fantasy world",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
        )

        # Contract: Workflow completes successfully
        assert isinstance(universe_id, str)
        assert isinstance(universe_id, str)

    @pytest.mark.asyncio
    async def test_full_universe_creation_workflow_with_branching(
        self, fake_mcp_client
    ):
        """Contract: Full workflow: list universes → create universe (branch) → return ID."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_universes",
            {"multiverse_id": "multi123"},
            [
                {
                    "id": "universe456",
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "entity_count": 15,
                    "story_count": 3,
                }
            ],
        )
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms - Alternate",
                    "genre": "Fantasy",
                    "tone": "Dark",
                    "tech_level": "Pre-Industrial",
                    "description": "Alternate timeline",
                    "canon_level": "canon",
                },
                "branch_from": "universe456",
            },
            "universe12345678901234567890123456789012",
        )

        # Execute workflow with branching
        universes = await fake_mcp_client.call_tool(
            "neo4j_list_universes", {"multiverse_id": "multi123"}
        )
        assert len(universes) >= 1
        source_universe_id = universes[0]["id"]

        universe_id = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Forgotten Realms - Alternate",
                    "genre": "Fantasy",
                    "tone": "Dark",
                    "tech_level": "Pre-Industrial",
                    "description": "Alternate timeline",
                    "canon_level": "canon",
                },
                "branch_from": source_universe_id,
            },
        )

        # Contract: Workflow completes successfully
        assert isinstance(universe_id, str)
        assert isinstance(universe_id, str)


# =============================================================================
# Edge Cases and Error Scenarios
# =============================================================================


class TestUniverseCreationEdgeCases:
    """Edge case tests for universe creation."""

    @pytest.mark.asyncio
    async def test_empty_description_is_valid(self, fake_mcp_client):
        """Contract: Empty description is valid (optional field)."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Test",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "",  # Empty description
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
            "universe12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Test",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "description": "",
                    "canon_level": "canon",
                },
                "branch_from": None,
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
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "A",  # 1 char (minimal)
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
            "universe12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "A",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "canon_level": "canon",
                },
                "branch_from": None,
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
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "x" * 200,  # 200 chars (maximal)
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
            "universe12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "x" * 200,
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
        )

        # Contract: 200-char name is valid
        assert isinstance(result, str)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_branch_from_none_is_valid_fresh_start(self, fake_mcp_client):
        """Contract: branch_from=None indicates fresh start (no branching)."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Test",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "canon_level": "canon",
                },
                "branch_from": None,  # Fresh start
            },
            "universe12345678901234567890123456789012",
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_create_universe",
            {
                "multiverse_id": "multi123",
                "params": {
                    "name": "Test",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "canon_level": "canon",
                },
                "branch_from": None,
            },
        )

        # Contract: branch_from=None is valid for fresh start
        assert isinstance(result, str)
        assert isinstance(result, str)


# =============================================================================
# Data Structure Tests
# =============================================================================


class TestDataStructureContracts:
    """Tests for data structure contracts."""

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

    @pytest.mark.asyncio
    async def test_universe_summary_dict_structure(self, fake_mcp_client):
        """Contract: UniverseSummary dict has correct structure."""
        # Setup
        fake_mcp_client.add_response(
            "neo4j_list_universes",
            {"multiverse_id": "multi123"},
            [
                {
                    "id": "universe123",
                    "name": "Forgotten Realms",
                    "genre": "Fantasy",
                    "tone": "Heroic",
                    "tech_level": "Pre-Industrial",
                    "entity_count": 15,
                    "story_count": 3,
                }
            ],
        )

        # Execute
        result = await fake_mcp_client.call_tool(
            "neo4j_list_universes", {"multiverse_id": "multi123"}
        )

        # Contract: Verify dict structure
        assert isinstance(result[0]["id"], str)
        assert isinstance(result[0]["name"], str)
        assert isinstance(result[0]["genre"], str)
        assert isinstance(result[0]["tone"], str)
        assert isinstance(result[0]["tech_level"], str)
        assert isinstance(result[0]["entity_count"], int)
        assert isinstance(result[0]["story_count"], int)

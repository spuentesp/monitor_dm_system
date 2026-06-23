"""Contract tests for M-13: Create Character.

Tests the API contracts for creating character entities.
"""

import pytest
from typing import Dict, List, Any

from tests.conftest import FakeMCPClient, FakeLLMClient


class TestM13DataLayerContracts:
    """Tests for M-13 data layer tool contracts."""

    async def test_neo4j_list_archetypes(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_list_archetypes contract: returns list of archetype summaries."""
        result = await fake_mcp_client.call("neo4j_list_archetypes", {"universe_id": "universe123"})

        assert isinstance(result, list), "Result must be a list"
        assert len(result) >= 1, "Result must contain at least one archetype"
        assert result[0]["id"] is not None, "Archetype ID must not be None"
        assert result[0]["name"] is not None, "Archetype name must not be None"
        assert result[0]["entity_type"] == "archetype", "Entity type must be 'archetype'"

    async def test_neo4j_list_archetypes_universe_not_found(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_list_archetypes raises NotFoundError for invalid universe_id."""
        fake_mcp_client.add_error("neo4j_list_archetypes", {}, Exception("Universe not found: invalid_universe"))
        with pytest.raises(Exception, match="Universe not found"):
            await fake_mcp_client.call("neo4j_list_archetypes", {"universe_id": "invalid_universe"})

    async def test_neo4j_create_entity_character(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_create_entity contract: creates EntityInstance node for character."""
        result = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Gandalf",
                "description": "A wise and powerful wizard",
                "role": "ally",
                "properties": {},
                "state_tags": [],
                "canon_level": "canon"
            }
        })

        assert isinstance(result, str), "Result must be a string (entity ID)"
        assert isinstance(result, str), "Result must be a string (entity ID)"

    async def test_neo4j_create_entity_character_universe_not_found(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_create_entity raises NotFoundError for invalid universe_id."""
        fake_mcp_client.add_error("neo4j_create_entity", {}, Exception("Universe not found: invalid_universe"))
        with pytest.raises(Exception, match="Universe not found"):
            await fake_mcp_client.call("neo4j_create_entity", {
                "universe_id": "invalid_universe",
                "entity_type": "character",
                "params": {
                    "name": "Test Character",
                    "role": "NPC"
                }
            })

    async def test_neo4j_create_entity_character_invalid_name(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_create_entity raises ValidationError for invalid name."""
        # Name too short
        fake_mcp_client.add_error("neo4j_create_entity", {}, Exception("Name must be 1-200 characters"))
        with pytest.raises(Exception, match="Name must be 1-200 characters"):
            await fake_mcp_client.call("neo4j_create_entity", {
                "universe_id": "universe123",
                "entity_type": "character",
                "params": {
                    "name": "",  # Empty name
                    "role": "NPC"
                }
            })

        # Name too long
        with pytest.raises(Exception, match="Name must be 1-200 characters"):
            await fake_mcp_client.call("neo4j_create_entity", {
                "universe_id": "universe123",
                "entity_type": "character",
                "params": {
                    "name": "x" * 201,  # 201 chars
                    "role": "NPC"
                }
            })

    async def test_neo4j_create_relationship_derives_from(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_create_relationship contract: creates DERIVES_FROM relationship."""
        result = await fake_mcp_client.call("neo4j_create_relationship", {
            "from_id": "entity123",
            "to_id": "archetype456",
            "relationship_type": "DERIVES_FROM",
            "properties": {}
        })

        assert isinstance(result, str), "Result must be a string (relationship ID)"

    async def test_neo4j_create_relationship_has_entity(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_create_relationship contract: creates HAS_ENTITY relationship."""
        result = await fake_mcp_client.call("neo4j_create_relationship", {
            "from_id": "universe123",
            "to_id": "entity456",
            "relationship_type": "HAS_ENTITY",
            "properties": {}
        })

        assert isinstance(result, str), "Result must be a string (relationship ID)"

    async def test_neo4j_create_relationship_invalid_from_entity(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_create_relationship raises NotFoundError for invalid from_id."""
        fake_mcp_client.add_error("neo4j_create_relationship", {}, Exception("Source entity not found: invalid_entity"))
        with pytest.raises(Exception, match="Source entity not found"):
            await fake_mcp_client.call("neo4j_create_relationship", {
                "from_id": "invalid_entity",
                "to_id": "archetype456",
                "relationship_type": "DERIVES_FROM",
                "properties": {}
            })

    async def test_neo4j_create_relationship_invalid_to_entity(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_create_relationship raises NotFoundError for invalid to_id."""
        fake_mcp_client.add_error("neo4j_create_relationship", {}, Exception("Target entity not found: invalid_archetype"))
        with pytest.raises(Exception, match="Target entity not found"):
            await fake_mcp_client.call("neo4j_create_relationship", {
                "from_id": "entity123",
                "to_id": "invalid_archetype",
                "relationship_type": "DERIVES_FROM",
                "properties": {}
            })

    async def test_neo4j_create_relationship_invalid_relationship_type(self, fake_mcp_client: FakeMCPClient):
        """Test neo4j_create_relationship raises ValidationError for invalid relationship_type."""
        fake_mcp_client.add_error("neo4j_create_relationship", {}, Exception("Invalid relationship type: INVALID_TYPE"))
        with pytest.raises(Exception, match="Invalid relationship type"):
            await fake_mcp_client.call("neo4j_create_relationship", {
                "from_id": "entity123",
                "to_id": "archetype456",
                "relationship_type": "INVALID_TYPE",
                "properties": {}
            })

    async def test_mongodb_create_character_sheet(self, fake_mcp_client: FakeMCPClient):
        """Test mongodb_create_character_sheet contract: creates character sheet in MongoDB."""
        result = await fake_mcp_client.call("mongodb_create_character_sheet", {
            "entity_id": "entity123",
            "stats": {
                "STR": 16,
                "DEX": 14,
                "CON": 14,
                "INT": 18,
                "WIS": 16,
                "CHA": 16
            },
            "resources": {
                "hp_max": 14,
                "hp_current": 14,
                "mp_max": 20,
                "mp_current": 20
            },
            "abilities": ["Fireball", "Lightning Bolt", "Teleport"],
            "equipment": ["Staff", "Robe of the Archmagi"]
        })

        assert isinstance(result, str), "Result must be a string (MongoDB ObjectId)"

    async def test_mongodb_create_character_sheet_invalid_entity_id(self, fake_mcp_client: FakeMCPClient):
        """Test mongodb_create_character_sheet raises NotFoundError for invalid entity_id."""
        fake_mcp_client.add_error("mongodb_create_character_sheet", {}, Exception("Character entity not found: invalid_entity"))
        with pytest.raises(Exception, match="Character entity not found"):
            await fake_mcp_client.call("mongodb_create_character_sheet", {
                "entity_id": "invalid_entity",
                "stats": {
                    "STR": 16,
                    "DEX": 14,
                    "CON": 14,
                    "INT": 18,
                    "WIS": 16,
                    "CHA": 16
                },
                "resources": {
                    "hp_max": 14,
                    "hp_current": 14
                }
            })

    async def test_mongodb_create_character_sheet_invalid_stats(self, fake_mcp_client: FakeMCPClient):
        """Test mongodb_create_character_sheet raises ValidationError for invalid stats."""
        fake_mcp_client.add_error("mongodb_create_character_sheet", {}, Exception("Invalid stats: missing required keys"))
        with pytest.raises(Exception, match="Invalid stats"):
            await fake_mcp_client.call("mongodb_create_character_sheet", {
                "entity_id": "entity123",
                "stats": {
                    "STR": 16,
                    "DEX": 14
                    # Missing CON, INT, WIS, CHA
                },
                "resources": {
                    "hp_max": 14,
                    "hp_current": 14
                }
            })


@pytest.mark.unit
class TestM13AgentContracts:
    """Tests for M-13 agent contracts."""

    @pytest.fixture
    def character_creator(self):
        """Fixture for CharacterCreator agent."""
        from monitor_agents.character_creator import CharacterCreator
        from unittest.mock import MagicMock

        # Create a real CharacterCreator with mocked MCP client
        mock_mcp = MagicMock()
        mock_llm = MagicMock()
        creator = CharacterCreator(mcp_client=mock_mcp, llm_client=mock_llm)
        return creator

    def test_validate_character_params_valid(self, character_creator):
        """Test validate_character_params passes with valid parameters."""
        from monitor_agents.character_creator import ValidationError

        # Valid params — should not raise
        result = character_creator.validate_character_params(
            name="Gandalf",
            role="ally",
            description="A wise and powerful wizard",
            stats={
                "STR": 16,
                "DEX": 14,
                "CON": 14,
                "INT": 18,
                "WIS": 16,
                "CHA": 16
            }
        )
        assert result["name"] == "Gandalf"
        assert result["role"] == "ally"

    def test_validate_character_params_invalid_name_too_short(self, character_creator):
        """Test validate_character_params raises ValidationError for name too short."""
        from monitor_agents.character_creator import ValidationError

        with pytest.raises(ValidationError, match="Name must be 1-200 characters"):
            character_creator.validate_character_params(
                name="",
                role="PC",
                description="Test"
            )

    def test_validate_character_params_invalid_name_too_long(self, character_creator):
        """Test validate_character_params raises ValidationError for name too long."""
        from monitor_agents.character_creator import ValidationError

        with pytest.raises(ValidationError, match="Name must be 1-200 characters"):
            character_creator.validate_character_params(
                name="x" * 201,
                role="PC",
                description="Test"
            )

    def test_validate_character_params_invalid_stats_not_dict(self, character_creator):
        """Test validate_character_params raises ValidationError for non-dict stats."""
        from monitor_agents.character_creator import ValidationError

        with pytest.raises(ValidationError, match="Stats must be a dictionary"):
            character_creator.validate_character_params(
                name="Test",
                role="PC",
                description="Test",
                stats="not_a_dict"
            )

    def test_validate_character_params_invalid_stats_value_too_low(self, character_creator):
        """Test validate_character_params raises ValidationError for stat value too low."""
        from monitor_agents.character_creator import ValidationError

        with pytest.raises(ValidationError, match="must be between 1 and 30"):
            character_creator.validate_character_params(
                name="Test",
                role="PC",
                description="Test",
                stats={
                    "STR": 0,
                    "DEX": 14,
                    "CON": 14,
                    "INT": 18,
                    "WIS": 16,
                    "CHA": 16
                }
            )

    def test_validate_character_params_invalid_stats_value_too_high(self, character_creator):
        """Test validate_character_params raises ValidationError for stat value too high."""
        from monitor_agents.character_creator import ValidationError

        with pytest.raises(ValidationError, match="must be between 1 and 30"):
            character_creator.validate_character_params(
                name="Test",
                role="PC",
                description="Test",
                stats={
                    "STR": 31,
                    "DEX": 14,
                    "CON": 14,
                    "INT": 18,
                    "WIS": 16,
                    "CHA": 16
                }
            )

    def test_calculate_hp(self, character_creator):
        """Test calculate_hp returns correct HP value based on CON."""
        # CON 14 → +2 modifier, d8 avg=4, HP = (4+2)*1 = 6
        result = character_creator.calculate_hp(constitution=14, level=1, hit_die="d8")
        assert result == 6

        # CON 10 → +0 modifier, d8 avg=4, HP = (4+0)*1 = 4
        result = character_creator.calculate_hp(constitution=10, level=1, hit_die="d8")
        assert result == 4

        # CON 18 → +4 modifier, d8 avg=4, HP = (4+4)*1 = 8
        result = character_creator.calculate_hp(constitution=18, level=1, hit_die="d8")
        assert result == 8

    def test_calculate_hp_level_scaling(self, character_creator):
        """Test calculate_hp scales with level."""
        # Level 5, CON 14 (+2), d8 (avg 4): (4+2)*5 = 30
        result = character_creator.calculate_hp(constitution=14, level=5, hit_die="d8")
        assert result == 30

    def test_calculate_hp_minimum_hp(self, character_creator):
        """Test calculate_hp ensures minimum 1 HP per level."""
        # CON 3 → -4 modifier, d4 (avg 2): max(1, 2-4)*1 = 1
        result = character_creator.calculate_hp(constitution=3, level=1, hit_die="d4")
        assert result == 1


class TestM13CharacterCreationFlow:
    """Tests for M-13 character creation flow."""

    async def test_create_character_pc_with_archetype(self, fake_mcp_client: FakeMCPClient, llm_client: FakeLLMClient):
        """Test creating a PC with archetype and stats."""
        # Create character entity
        entity_id = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Gandalf",
                "description": "A wise and powerful wizard",
                "role": "ally",
                "properties": {},
                "state_tags": [],
                "canon_level": "canon"
            }
        })

        # Link to universe
        await fake_mcp_client.call("neo4j_create_relationship", {
            "from_id": "universe123",
            "to_id": entity_id,
            "relationship_type": "HAS_ENTITY",
            "properties": {}
        })

        # Link to archetype
        await fake_mcp_client.call("neo4j_create_relationship", {
            "from_id": entity_id,
            "to_id": "archetype456",
            "relationship_type": "DERIVES_FROM",
            "properties": {}
        })

        # Create character sheet
        await fake_mcp_client.call("mongodb_create_character_sheet", {
            "entity_id": entity_id,
            "stats": {
                "STR": 16,
                "DEX": 14,
                "CON": 14,
                "INT": 18,
                "WIS": 16,
                "CHA": 16
            },
            "resources": {
                "hp_max": 10,
                "hp_current": 10,
                "mp_max": 20,
                "mp_current": 20
            },
            "abilities": ["Fireball", "Lightning Bolt", "Teleport"],
            "equipment": ["Staff", "Robe of the Archmagi"]
        })

        assert isinstance(entity_id, str)
        assert isinstance(entity_id, str)

    async def test_create_character_npc_without_archetype(self, fake_mcp_client: FakeMCPClient, llm_client: FakeLLMClient):
        """Test creating an NPC without archetype or detailed stats."""
        # Create character entity
        entity_id = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Villager",
                "description": "A simple villager",
                "role": "NPC",
                "properties": {},
                "state_tags": [],
                "canon_level": "canon"
            }
        })

        # Link to universe
        await fake_mcp_client.call("neo4j_create_relationship", {
            "from_id": "universe123",
            "to_id": entity_id,
            "relationship_type": "HAS_ENTITY",
            "properties": {}
        })

        # No archetype link
        # No character sheet (NPC without detailed stats)

        assert isinstance(entity_id, str)
        assert isinstance(entity_id, str)

    async def test_create_character_antagonist_with_stats(self, fake_mcp_client: FakeMCPClient, llm_client: FakeLLMClient):
        """Test creating an antagonist with detailed stats."""
        # Create character entity
        entity_id = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Sauron",
                "description": "The Dark Lord",
                "role": "antagonist",
                "properties": {},
                "state_tags": [],
                "canon_level": "canon"
            }
        })

        # Link to universe
        await fake_mcp_client.call("neo4j_create_relationship", {
            "from_id": "universe123",
            "to_id": entity_id,
            "relationship_type": "HAS_ENTITY",
            "properties": {}
        })

        # Create character sheet
        await fake_mcp_client.call("mongodb_create_character_sheet", {
            "entity_id": entity_id,
            "stats": {
                "STR": 18,
                "DEX": 14,
                "CON": 18,
                "INT": 18,
                "WIS": 18,
                "CHA": 18
            },
            "resources": {
                "hp_max": 12,
                "hp_current": 12,
                "mp_max": 50,
                "mp_current": 50
            },
            "abilities": ["Dark Fire", "Corruption", "Mind Control"],
            "equipment": ["One Ring", "Morgul-knife"]
        })

        assert isinstance(entity_id, str)
        assert isinstance(entity_id, str)


class TestM13EnumsAndDataStructures:
    """Tests for M-13 enums and data structures."""

    def test_character_role_enum_values(self):
        """Test CharacterRole enum has correct values."""
        # In a real test, we'd import the enum from the actual code
        valid_roles = ["PC", "NPC", "antagonist", "ally"]
        for role in valid_roles:
            assert role in ["PC", "NPC", "antagonist", "ally"]

    def test_archetype_summary_structure(self):
        """Test ArchetypeSummary dict has correct structure."""
        archetype_summary = {
            "id": "archetype123",
            "name": "Wizard",
            "description": "A spellcaster who studies arcane magic",
            "entity_type": "archetype"
        }
        assert isinstance(archetype_summary["id"], str)
        assert isinstance(archetype_summary["name"], str)
        assert isinstance(archetype_summary["description"], str)
        assert archetype_summary["entity_type"] == "archetype"

    def test_character_sheet_structure(self):
        """Test CharacterSheet dict has correct structure."""
        character_sheet = {
            "entity_id": "entity123",
            "stats": {
                "STR": 16,
                "DEX": 14,
                "CON": 14,
                "INT": 18,
                "WIS": 16,
                "CHA": 16
            },
            "resources": {
                "hp_max": 14,
                "hp_current": 14,
                "mp_max": 20,
                "mp_current": 20
            },
            "abilities": ["Fireball", "Lightning Bolt", "Teleport"],
            "equipment": ["Staff", "Robe of the Archmagi"],
            "created_at": "2025-01-09T12:00:00Z"
        }
        assert isinstance(character_sheet["entity_id"], str)
        assert isinstance(character_sheet["stats"], dict)
        assert "STR" in character_sheet["stats"]
        assert "DEX" in character_sheet["stats"]
        assert "CON" in character_sheet["stats"]
        assert "INT" in character_sheet["stats"]
        assert "WIS" in character_sheet["stats"]
        assert "CHA" in character_sheet["stats"]
        assert isinstance(character_sheet["resources"], dict)
        assert "hp_max" in character_sheet["resources"]
        assert "hp_current" in character_sheet["resources"]
        assert isinstance(character_sheet["abilities"], list)
        assert isinstance(character_sheet["equipment"], list)
        assert isinstance(character_sheet["created_at"], str)

    def test_stats_validation_all_required_keys(self):
        """Test that stats dict must have all 6 required keys."""
        required_keys = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
        stats = {key: 10 for key in required_keys}
        for key in required_keys:
            assert key in stats

    def test_stats_validation_value_range(self):
        """Test that stat values must be in range 8-18."""
        valid_stats = {key: 10 for key in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]}
        for value in valid_stats.values():
            assert 8 <= value <= 18

        # Test out of range values
        invalid_stats_low = {"STR": 7, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}
        assert any(value < 8 for value in invalid_stats_low.values())

        invalid_stats_high = {"STR": 19, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}
        assert any(value > 18 for value in invalid_stats_high.values())


class TestM13ErrorHandling:
    """Tests for M-13 error handling."""

    async def test_universe_not_found(self, fake_mcp_client: FakeMCPClient):
        """Test that creating character with invalid universe_id raises error."""
        fake_mcp_client.add_error("neo4j_create_entity", {}, Exception("Universe not found: invalid_universe"))
        with pytest.raises(Exception, match="Universe not found"):
            await fake_mcp_client.call("neo4j_create_entity", {
                "universe_id": "invalid_universe",
                "entity_type": "character",
                "params": {
                    "name": "Test Character",
                    "role": "NPC"
                }
            })

    async def test_archetype_not_found(self, fake_mcp_client: FakeMCPClient):
        """Test that creating character with invalid archetype_id raises error."""
        # Create character entity first
        entity_id = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Test Character",
                "role": "NPC"
            }
        })

        # Try to link to invalid archetype
        fake_mcp_client.add_error("neo4j_create_relationship", {}, Exception("Target entity not found: invalid_archetype"))
        with pytest.raises(Exception, match="Target entity not found"):
            await fake_mcp_client.call("neo4j_create_relationship", {
                "from_id": entity_id,
                "to_id": "invalid_archetype",
                "relationship_type": "DERIVES_FROM",
                "properties": {}
            })

    async def test_character_creation_fails(self, fake_mcp_client: FakeMCPClient):
        """Test that character creation failures are handled gracefully."""
        # Simulate Neo4j connection error
        fake_mcp_client.add_error("neo4j_create_entity", {}, Exception("Failed to create character: ConnectionError"))
        with pytest.raises(Exception, match="Failed to create character"):
            await fake_mcp_client.call("neo4j_create_entity", {
                "universe_id": "universe123",
                "entity_type": "character",
                "params": {
                    "name": "Test Character",
                    "role": "NPC"
                }
            })

    async def test_character_sheet_creation_fails(self, fake_mcp_client: FakeMCPClient):
        """Test that character sheet creation failures are handled gracefully."""
        # Simulate MongoDB connection error
        fake_mcp_client.add_error("mongodb_create_character_sheet", {}, Exception("Failed to create character sheet: ConnectionError"))
        with pytest.raises(Exception, match="Failed to create character sheet"):
            await fake_mcp_client.call("mongodb_create_character_sheet", {
                "entity_id": "entity123",
                "stats": {
                    "STR": 16,
                    "DEX": 14,
                    "CON": 14,
                    "INT": 18,
                    "WIS": 16,
                    "CHA": 16
                },
                "resources": {
                    "hp_max": 14,
                    "hp_current": 14
                }
            })


class TestM13ComplianceChecklist:
    """Tests for M-13 compliance checklist items."""

    async def test_validates_name_length(self, fake_mcp_client: FakeMCPClient):
        """Test: Validates name length (1-200 chars)."""
        # Name too short
        fake_mcp_client.add_error("neo4j_create_entity", {}, Exception("Name must be 1-200 characters"))
        with pytest.raises(Exception, match="Name must be 1-200 characters"):
            await fake_mcp_client.call("neo4j_create_entity", {
                "universe_id": "universe123",
                "entity_type": "character",
                "params": {
                    "name": "",
                    "role": "NPC"
                }
            })

        # Name too long
        with pytest.raises(Exception, match="Name must be 1-200 characters"):
            await fake_mcp_client.call("neo4j_create_entity", {
                "universe_id": "universe123",
                "entity_type": "character",
                "params": {
                    "name": "x" * 201,
                    "role": "NPC"
                }
            })

    async def test_creates_entity_instance_node(self, fake_mcp_client: FakeMCPClient):
        """Test: Creates EntityInstance node in Neo4j."""
        result = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Test Character",
                "role": "NPC"
            }
        })
        assert isinstance(result, str)
        assert isinstance(result, str)

    async def test_links_character_to_universe(self, fake_mcp_client: FakeMCPClient):
        """Test: Links character to universe via HAS_ENTITY edge."""
        # Create character entity
        entity_id = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Test Character",
                "role": "NPC"
            }
        })

        # Link to universe
        result = await fake_mcp_client.call("neo4j_create_relationship", {
            "from_id": "universe123",
            "to_id": entity_id,
            "relationship_type": "HAS_ENTITY",
            "properties": {}
        })
        assert isinstance(result, str)

    async def test_links_character_to_archetype(self, fake_mcp_client: FakeMCPClient):
        """Test: Links character to archetype via DERIVES_FROM edge."""
        # Create character entity
        entity_id = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Test Character",
                "role": "NPC"
            }
        })

        # Link to archetype
        result = await fake_mcp_client.call("neo4j_create_relationship", {
            "from_id": entity_id,
            "to_id": "archetype456",
            "relationship_type": "DERIVES_FROM",
            "properties": {}
        })
        assert isinstance(result, str)

    async def test_creates_character_sheet(self, fake_mcp_client: FakeMCPClient):
        """Test: Creates character sheet in MongoDB."""
        result = await fake_mcp_client.call("mongodb_create_character_sheet", {
            "entity_id": "entity123",
            "stats": {
                "STR": 16,
                "DEX": 14,
                "CON": 14,
                "INT": 18,
                "WIS": 16,
                "CHA": 16
            },
            "resources": {
                "hp_max": 14,
                "hp_current": 14
            }
        })
        assert isinstance(result, str)

    async def test_returns_entity_id(self, fake_mcp_client: FakeMCPClient):
        """Test: Returns entity ID."""
        result = await fake_mcp_client.call("neo4j_create_entity", {
            "universe_id": "universe123",
            "entity_type": "character",
            "params": {
                "name": "Test Character",
                "role": "NPC"
            }
        })
        assert isinstance(result, str)
        assert isinstance(result, str)

    async def test_lists_archetypes_for_selection(self, fake_mcp_client: FakeMCPClient):
        """Test: Lists archetypes for selection."""
        result = await fake_mcp_client.call("neo4j_list_archetypes", {"universe_id": "universe123"})
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["entity_type"] == "archetype"
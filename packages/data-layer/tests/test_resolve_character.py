"""
Tests for mongodb_resolve_character — unified character resolution.

Covers:
- MongoDB standalone character found
- Neo4j entity found (fallback)
- Neither found → ValueError
- MongoDB error falls back to Neo4j
- Neo4j entity with string properties (JSON)

Run:
    cd /path/to/monitor_dm_system && pytest packages/data-layer/tests/test_resolve_character.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.tools.mongodb_tools.characters import (
    mongodb_resolve_character,
)


def _make_standalone(char_id: str, name: str = "Test Char") -> dict:
    return {
        "id": char_id,
        "name": name,
        "personality": "brave",
        "description": "A brave hero",
        "is_ooc_persona": False,
    }


def _make_entity(entity_id: str, name: str = "Entity Char") -> dict:
    return {
        "entity_id": entity_id,
        "name": name,
        "description": "An NPC",
        "state_tags": ["npc"],
        "properties": {
            "personality": "cunning",
            "role": "npc",
            "attributes": {"str": 10},
            "skills": {"stealth": 5},
            "resources": {"hp": 20},
        },
    }


class TestResolveCharacterStandalone:
    """When a standalone character exists in MongoDB, it should be returned."""

    @patch("monitor_data.tools.mongodb_tools.characters.mongodb_get_character")
    def test_returns_standalone_character(self, mock_get):
        char_id = str(uuid4())
        mock_get.return_value = _make_standalone(char_id, "Aria")

        result = mongodb_resolve_character(char_id)

        assert result["source"] == "standalone"
        assert result["name"] == "Aria"
        assert result["role"] == "pc"
        assert "standalone" in result["state_tags"]

    @patch("monitor_data.tools.mongodb_tools.characters.mongodb_get_character")
    def test_standalone_has_empty_game_data(self, mock_get):
        char_id = str(uuid4())
        mock_get.return_value = _make_standalone(char_id)

        result = mongodb_resolve_character(char_id)

        assert result["attributes"] == {}
        assert result["skills"] == {}
        assert result["resources"] == {}


class TestResolveCharacterEntity:
    """When no standalone character exists, fall back to Neo4j entity."""

    @patch("monitor_data.tools.mongodb_tools.characters.get_neo4j_client")
    @patch("monitor_data.tools.mongodb_tools.characters.mongodb_get_character")
    def test_returns_neo4j_entity(self, mock_get, mock_neo):
        entity_id = str(uuid4())
        mock_get.return_value = None
        mock_client = MagicMock()
        mock_client.execute_read.return_value = [{"e": _make_entity(entity_id, "Goblin")}]
        mock_neo.return_value = mock_client

        result = mongodb_resolve_character(entity_id)

        assert result["source"] == "entity"
        assert result["name"] == "Goblin"
        assert result["role"] == "npc"
        assert result["attributes"] == {"str": 10}

    @patch("monitor_data.tools.mongodb_tools.characters.get_neo4j_client")
    @patch("monitor_data.tools.mongodb_tools.characters.mongodb_get_character")
    def test_entity_with_json_string_properties(self, mock_get, mock_neo):
        entity_id = str(uuid4())
        mock_get.return_value = None
        entity = _make_entity(entity_id)
        entity["properties"] = '{"personality": "cunning", "role": "npc"}'
        mock_client = MagicMock()
        mock_client.execute_read.return_value = [{"e": entity}]
        mock_neo.return_value = mock_client

        result = mongodb_resolve_character(entity_id)

        assert result["source"] == "entity"
        assert result["personality"] == "cunning"


class TestResolveCharacterNotFound:
    """When neither MongoDB nor Neo4j has the character, raise ValueError."""

    @patch("monitor_data.tools.mongodb_tools.characters.get_neo4j_client")
    @patch("monitor_data.tools.mongodb_tools.characters.mongodb_get_character")
    def test_raises_value_error(self, mock_get, mock_neo):
        mock_get.return_value = None
        mock_client = MagicMock()
        mock_client.execute_read.return_value = []
        mock_neo.return_value = mock_client

        with pytest.raises(ValueError, match="not found"):
            mongodb_resolve_character("nonexistent-id")


class TestResolveCharacterFallback:
    """When MongoDB fails, fall back to Neo4j."""

    @patch("monitor_data.tools.mongodb_tools.characters.get_neo4j_client")
    @patch("monitor_data.tools.mongodb_tools.characters.mongodb_get_character")
    def test_mongodb_error_falls_back_to_neo4j(self, mock_get, mock_neo):
        entity_id = str(uuid4())
        mock_get.side_effect = Exception("MongoDB connection error")
        mock_client = MagicMock()
        mock_client.execute_read.return_value = [{"e": _make_entity(entity_id, "Orc")}]
        mock_neo.return_value = mock_client

        result = mongodb_resolve_character(entity_id)

        assert result["source"] == "entity"
        assert result["name"] == "Orc"

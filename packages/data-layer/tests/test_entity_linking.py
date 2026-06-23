"""
Tests for neo4j_link_to_archetype and neo4j_create_character_relationship.

Covers:
- Linking an entity to an archetype (DERIVES_FROM)
- Idempotent linking (already exists)
- Missing entity/archetype raises ValueError
- Creating character relationships
- Invalid relationship type raises ValueError
- Missing characters raises ValueError

Run:
    cd /path/to/monitor_dm_system && pytest packages/data-layer/tests/test_entity_linking.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.tools.neo4j_tools.entities import (
    neo4j_create_character_relationship,
    neo4j_link_to_archetype,
)


def _mock_client(*query_results):
    """Create a mock Neo4j client that returns sequential results."""
    client = MagicMock()
    client.execute_query.side_effect = list(query_results)
    client.execute_write.return_value = None
    return client


class TestLinkToArchetype:
    """Tests for neo4j_link_to_archetype."""

    @patch("monitor_data.tools.neo4j_tools.entities.get_neo4j_client")
    def test_link_creates_derives_from(self, mock_get):
        entity_id = uuid4()
        archetype_id = uuid4()
        mock_client = _mock_client(
            [{"eid": str(entity_id), "aid": str(archetype_id)}],  # verify
            [],  # check existing (empty)
        )
        mock_get.return_value = mock_client

        result = neo4j_link_to_archetype(entity_id, archetype_id)

        assert result["relationship"] == "DERIVES_FROM"
        assert result["status"] == "created"
        assert result["entity_id"] == str(entity_id)
        assert result["archetype_id"] == str(archetype_id)

    @patch("monitor_data.tools.neo4j_tools.entities.get_neo4j_client")
    def test_link_already_exists(self, mock_get):
        entity_id = uuid4()
        archetype_id = uuid4()
        mock_client = _mock_client(
            [{"eid": str(entity_id), "aid": str(archetype_id)}],  # verify
            [{"r": "DERIVES_FROM"}],  # check existing (found)
        )
        mock_get.return_value = mock_client

        result = neo4j_link_to_archetype(entity_id, archetype_id)

        assert result["status"] == "already_exists"
        # Should NOT call execute_write
        mock_client.execute_write.assert_not_called()

    @patch("monitor_data.tools.neo4j_tools.entities.get_neo4j_client")
    def test_link_missing_entity_raises(self, mock_get):
        entity_id = uuid4()
        archetype_id = uuid4()
        mock_client = _mock_client([])  # verify returns empty
        mock_get.return_value = mock_client

        with pytest.raises(ValueError, match="not found"):
            neo4j_link_to_archetype(entity_id, archetype_id)


class TestCreateCharacterRelationship:
    """Tests for neo4j_create_character_relationship."""

    @patch("monitor_data.tools.neo4j_tools.entities.get_neo4j_client")
    def test_create_ally_relationship(self, mock_get):
        from_id = uuid4()
        to_id = uuid4()
        mock_client = _mock_client(
            [{"aid": str(from_id), "bid": str(to_id)}],  # verify
        )
        mock_get.return_value = mock_client

        result = neo4j_create_character_relationship(from_id, to_id, "ALLY_OF")

        assert result["relationship_type"] == "ALLY_OF"
        assert result["status"] == "created"
        assert result["from_id"] == str(from_id)
        assert result["to_id"] == str(to_id)

    @patch("monitor_data.tools.neo4j_tools.entities.get_neo4j_client")
    def test_create_relationship_with_properties(self, mock_get):
        from_id = uuid4()
        to_id = uuid4()
        mock_client = _mock_client(
            [{"aid": str(from_id), "bid": str(to_id)}],
        )
        mock_get.return_value = mock_client

        result = neo4j_create_character_relationship(
            from_id, to_id, "MENTOR_OF", properties={"since": "2024-01-01"}
        )

        assert result["properties"] == {"since": "2024-01-01"}

    @patch("monitor_data.tools.neo4j_tools.entities.get_neo4j_client")
    def test_invalid_rel_type_raises(self, mock_get):
        from_id = uuid4()
        to_id = uuid4()
        mock_client = _mock_client(
            [{"aid": str(from_id), "bid": str(to_id)}],
        )
        mock_get.return_value = mock_client

        with pytest.raises(ValueError, match="Invalid relationship type"):
            neo4j_create_character_relationship(from_id, to_id, "HACKED_REL_TYPE")

    @patch("monitor_data.tools.neo4j_tools.entities.get_neo4j_client")
    def test_missing_character_raises(self, mock_get):
        from_id = uuid4()
        to_id = uuid4()
        mock_client = _mock_client([])  # verify returns empty
        mock_get.return_value = mock_client

        with pytest.raises(ValueError, match="not found"):
            neo4j_create_character_relationship(from_id, to_id, "ALLY_OF")

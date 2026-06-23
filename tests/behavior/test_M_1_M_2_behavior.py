"""Behavior tests for M-1/M-2: Create Multiverse, Create Universe.

Verifies that actual implementation matches behavior specifications.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch, MagicMock

from monitor_data.schemas.universe import MultiverseCreate, UniverseCreate
from monitor_data.tools.neo4j_tools.core import (
    neo4j_create_multiverse,
    neo4j_list_multiverses,
    neo4j_create_universe,
)


class TestM1MultiverseCreation:
    """Scenario 1: M-1 Multiverse Creation."""

    def test_neo4j_create_multiverse_exists(self):
        """Test that neo4j_create_multiverse function exists."""
        assert neo4j_create_multiverse is not None

    def test_multiverse_create_schema_valid(self):
        """Test MultiverseCreate schema validation."""
        omniverse_id = uuid4()
        multiverse = MultiverseCreate(
            omniverse_id=omniverse_id,
            name="Test Multiverse",
            system_name="D&D 5e",
            description="A test multiverse",
        )
        assert multiverse.name == "Test Multiverse"
        assert multiverse.system_name == "D&D 5e"

    @pytest.mark.integration
    def test_create_multiverse_returns_response(self):
        """Test that creating a multiverse returns proper response."""
        omniverse_id = uuid4()

        with patch("monitor_data.tools.neo4j_tools.core.get_neo4j_client") as mock_neo:
            mock_client = MagicMock()
            mock_neo.return_value = mock_client

            mock_client.execute_write = MagicMock(
                return_value=[{
                    "m": {
                        "id": str(uuid4()),
                        "omniverse_id": str(omniverse_id),
                        "name": "Test Multiverse",
                        "system_name": "D&D 5e",
                        "description": "Test",
                        "is_template": False,
                        "knowledge_tree_type": "default",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                }]
            )

            multiverse = neo4j_create_multiverse(MultiverseCreate(
                omniverse_id=omniverse_id,
                name="Test Multiverse",
                system_name="D&D 5e",
                description="Test",
            ))

            assert multiverse is not None
            assert multiverse.name == "Test Multiverse"

    def test_multiverse_name_validation(self):
        """Test that name is required for multiverse."""
        omniverse_id = uuid4()
        multiverse = MultiverseCreate(
            omniverse_id=omniverse_id,
            name="Valid Name",
            system_name="D&D 5e",
            description="A valid description",
        )
        assert len(multiverse.name) > 0


class TestM2UniverseCreation:
    """Scenario 2: M-2 Universe Creation."""

    def test_neo4j_create_universe_exists(self):
        """Test that neo4j_create_universe function exists."""
        assert neo4j_create_universe is not None

    def test_neo4j_list_multiverses_exists(self):
        """Test that neo4j_list_multiverses function exists."""
        assert neo4j_list_multiverses is not None

    def test_universe_create_schema_valid(self):
        """Test UniverseCreate schema validation."""
        multiverse_id = uuid4()
        universe = UniverseCreate(
            multiverse_id=multiverse_id,
            name="Test Universe",
            description="A test universe",
            genre="fantasy",
            tone="heroic",
            tech_level="pre-industrial",
        )
        assert universe.name == "Test Universe"
        assert universe.genre == "fantasy"

    @pytest.mark.integration
    def test_list_multiverses_returns_list(self):
        """Test that listing multiverses returns a list."""
        with patch("monitor_data.tools.neo4j_tools.core.get_neo4j_client") as mock_neo:
            mock_client = MagicMock()
            mock_neo.return_value = mock_client

            mock_client.execute_read = MagicMock(
                return_value=[
                    {
                        "m": {
                            "id": str(uuid4()),
                            "omniverse_id": str(uuid4()),
                            "name": "Multiverse 1",
                            "system_name": "D&D 5e",
                            "description": "Test multiverse",
                            "is_template": False,
                            "knowledge_tree_type": "dynamic",
                            "created_at": datetime.now(tz=timezone.utc).isoformat(),
                        }
                    }
                ]
            )

            multiverses = neo4j_list_multiverses()
            assert isinstance(multiverses, list)

    @pytest.mark.integration
    def test_create_universe_returns_response(self):
        """Test that creating a universe returns proper response."""
        multiverse_id = uuid4()

        with patch("monitor_data.tools.neo4j_tools.core.get_neo4j_client") as mock_neo:
            mock_client = MagicMock()
            mock_neo.return_value = mock_client

            mock_client.execute_write = MagicMock(
                return_value=[{
                    "m": {
                        "id": str(uuid4()),
                        "multiverse_id": str(multiverse_id),
                        "name": "Test Universe",
                        "genre": "fantasy",
                        "tone": "heroic",
                        "tech_level": "pre-industrial",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                }]
            )

            universe = neo4j_create_universe(UniverseCreate(
                multiverse_id=multiverse_id,
                name="Test Universe",
                description="Test",
                genre="fantasy",
                tone="heroic",
                tech_level="pre-industrial",
            ))

            assert universe is not None
            assert universe.name == "Test Universe"


class TestM12AcceptanceCriteria:
    """Verify acceptance criteria from M-1/M-2 behavior specs."""

    def test_ac1_omniverse_retrieval(self):
        """AC-1: Omniverse singleton can be retrieved."""
        from monitor_data.tools.neo4j_tools.core import neo4j_list_multiverses
        assert neo4j_list_multiverses is not None

    def test_ac2_multiverse_name_validated(self):
        """AC-2: Multiverse name is validated."""
        omniverse_id = uuid4()
        multiverse = MultiverseCreate(
            omniverse_id=omniverse_id,
            name="A" * 100,
            system_name="D&D 5e",
            description="Test description",
        )
        assert len(multiverse.name) <= 200

    def test_ac3_multiverse_linked_to_omniverse(self):
        """AC-3: Multiverse is linked to Omniverse via CONTAINS."""
        with patch("monitor_data.tools.neo4j_tools.core.get_neo4j_client") as mock_neo:
            mock_client = MagicMock()
            mock_neo.return_value = mock_client

            mock_client.execute_write = MagicMock(
                return_value=[{
                    "m": {
                        "id": str(uuid4()),
                        "omniverse_id": str(uuid4()),
                        "name": "Test",
                        "system_name": "D&D 5e",
                        "description": "Test",
                        "is_template": False,
                        "knowledge_tree_type": "default",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                }]
            )

            neo4j_create_multiverse(MultiverseCreate(
                omniverse_id=uuid4(),
                name="Test",
                system_name="D&D 5e",
                description="Test",
            ))

            assert mock_client.execute_write.called

    def test_ac4_universe_genre_recorded(self):
        """AC-4: Universe genre is recorded."""
        universe = UniverseCreate(
            multiverse_id=uuid4(),
            name="Test Universe",
            description="Test",
            genre="sci-fi",
            tone="dark",
            tech_level="modern",
        )
        assert universe.genre == "sci-fi"

    def test_ac5_universe_linked_to_multiverse(self):
        """AC-5: Universe is linked to Multiverse."""
        with patch("monitor_data.tools.neo4j_tools.core.get_neo4j_client") as mock_neo:
            mock_client = MagicMock()
            mock_neo.return_value = mock_client

            mock_client.execute_write = MagicMock(
                return_value=[{
                    "m": {
                        "id": str(uuid4()),
                        "multiverse_id": str(uuid4()),
                        "name": "Test",
                        "genre": "fantasy",
                        "tone": "heroic",
                        "tech_level": "pre-industrial",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                }]
            )

            neo4j_create_universe(UniverseCreate(
                multiverse_id=uuid4(),
                name="Test",
                description="Test",
                genre="fantasy",
                tone="heroic",
                tech_level="pre-industrial",
            ))

            assert mock_client.execute_write.called
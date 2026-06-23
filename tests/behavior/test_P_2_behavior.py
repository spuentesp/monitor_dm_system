"""Behavior tests for P-2: Start Scene.

Verifies that actual implementation matches behavior specifications.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch, MagicMock

from monitor_data.schemas.base import SceneStatus, Speaker, TemporalMode
from monitor_data.schemas.scenes import SceneCreate, SceneUpdate, TurnCreate
from monitor_data.tools.mongodb_tools.scenes import mongodb_create_scene, mongodb_append_turn


def _mock_execute_read_result(query: str, params: dict):
    """Helper to create mock result for entity lookups."""
    return [{"id": params.get("entity_id") or params.get("story_id") or params.get("location_id")}]


class TestP2SceneCreationHappyPath:
    """Scenario 1: Basic Scene Creation (Happy Path)."""

    def test_scene_creation_with_all_fields(self):
        """Test scene creation with all required and optional fields."""
        story_id = uuid4()
        universe_id = uuid4()
        scene_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                # Story/universe check, batch entity check, location check
                def neo4j_read_side_effect(query, p):
                    if "node_ids" in p:
                        return [{"id": i} for i in p["node_ids"]]
                    if "location_id" in p:
                        return [{"id": str(p["location_id"])}]
                    return [{"story_id": str(story_id), "universe_id": str(universe_id)}]

                neo4j_client.execute_read = neo4j_read_side_effect

                # Mock MongoDB insert
                mongo_client.get_collection.return_value.insert_one = MagicMock(
                    return_value=MagicMock(inserted_id=str(scene_id))
                )

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Tavern Encounter",
                    purpose="Social interaction",
                    location_ref=uuid4(),
                    participating_entities=[uuid4(), uuid4()]
                )
                result = mongodb_create_scene(params)

                assert result is not None
                assert result.title == "Tavern Encounter"
                assert result.purpose == "Social interaction"

    def test_scene_node_properties_match_spec(self):
        """Test that Scene document has correct properties per spec."""
        story_id = uuid4()
        universe_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                neo4j_client.execute_read = lambda q, p: [{"story_id": str(story_id), "universe_id": str(universe_id)}]
                mongo_client.get_collection.return_value.insert_one = MagicMock(
                    return_value=MagicMock(inserted_id=str(uuid4()))
                )

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Test Scene"
                )
                result = mongodb_create_scene(params)

                assert result.story_id == story_id
                assert result.universe_id == universe_id


class TestP2SceneCreationFailsWithoutStory:
    """Scenario 2: Scene Creation Fails Without Story."""

    def test_scene_creation_fails_without_story(self):
        """Test ValueError when story doesn't exist."""
        story_id = uuid4()
        universe_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                # Story not found
                neo4j_client.execute_read = lambda q, p: []

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Orphaned Scene"
                )
                with pytest.raises(ValueError, match="Story"):
                    mongodb_create_scene(params)


class TestP2SceneCreationFailsWithoutUniverse:
    """Scenario 3: Scene Creation Fails Without Universe."""

    def test_scene_creation_fails_without_universe(self):
        """Test ValueError when universe doesn't exist."""
        story_id = uuid4()
        universe_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                # Story exists but universe check fails
                def neo4j_read_side_effect(query, params):
                    if "universe_id" in params:
                        return []  # Universe not found
                    return [{"story_id": str(story_id), "universe_id": str(universe_id)}]

                neo4j_client.execute_read = neo4j_read_side_effect

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Orphaned Scene"
                )
                with pytest.raises(ValueError, match="Universe"):
                    mongodb_create_scene(params)


class TestP2ParticipatingEntitiesValidation:
    """Scenario 4: Participating Entities Are Validated."""

    def test_valid_participating_entities_accepted(self):
        """Test that valid entity IDs are accepted."""
        story_id = uuid4()
        universe_id = uuid4()
        entity_id_1 = uuid4()
        entity_id_2 = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                call_count = [0]
                def neo4j_read_side_effect(query, params):
                    call_count[0] += 1
                    if "node_ids" in params:
                        return [{"id": i} for i in params["node_ids"]]
                    return [{"story_id": str(story_id), "universe_id": str(universe_id)}]

                neo4j_client.execute_read = neo4j_read_side_effect
                mongo_client.get_collection.return_value.insert_one = MagicMock(
                    return_value=MagicMock(inserted_id=str(uuid4()))
                )

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Battle Scene",
                    participating_entities=[entity_id_1, entity_id_2]
                )
                result = mongodb_create_scene(params)
                assert result is not None

    def test_invalid_participating_entity_rejected(self):
        """Test that invalid entity ID raises ValueError."""
        story_id = uuid4()
        universe_id = uuid4()
        invalid_entity_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                def neo4j_read_side_effect(query, params):
                    if "node_ids" in params:
                        return []  # Entity not found
                    return [{"story_id": str(story_id), "universe_id": str(universe_id)}]

                neo4j_client.execute_read = neo4j_read_side_effect

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Invalid Entity Scene",
                    participating_entities=[invalid_entity_id]
                )
                with pytest.raises(ValueError, match="Entity"):
                    mongodb_create_scene(params)


class TestP2LocationRefValidation:
    """Scenario 5: Location Ref Is Validated."""

    def test_valid_location_ref_accepted(self):
        """Test that valid location ref is accepted."""
        story_id = uuid4()
        universe_id = uuid4()
        location_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                call_count = [0]
                def neo4j_read_side_effect(query, params):
                    if "location_id" in params:
                        return [{"id": str(location_id)}]
                    return [{"story_id": str(story_id), "universe_id": str(universe_id)}]

                neo4j_client.execute_read = neo4j_read_side_effect
                mongo_client.get_collection.return_value.insert_one = MagicMock(
                    return_value=MagicMock(inserted_id=str(uuid4()))
                )

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Tavern Scene",
                    location_ref=location_id
                )
                result = mongodb_create_scene(params)
                assert result is not None

    def test_invalid_location_ref_rejected(self):
        """Test that invalid location ref raises ValueError."""
        story_id = uuid4()
        universe_id = uuid4()
        invalid_location_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                def neo4j_read_side_effect(query, params):
                    if "location_id" in params:
                        return []  # Location not found
                    return [{"story_id": str(story_id), "universe_id": str(universe_id)}]

                neo4j_client.execute_read = neo4j_read_side_effect

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Invalid Location Scene",
                    location_ref=invalid_location_id
                )
                with pytest.raises(ValueError, match="Location"):
                    mongodb_create_scene(params)


class TestP2SceneTitleValidation:
    """Scenario 6: Scene Title Is Required."""

    def test_empty_title_rejected(self):
        """Test that empty title raises ValidationError."""
        with pytest.raises(Exception, match="title"):
            params = SceneCreate(
                story_id=uuid4(),
                universe_id=uuid4(),
                title=""
            )
            mongodb_create_scene(params)


class TestP2SceneStatusDefault:
    """Scenario 7: Scene Status Defaults to ACTIVE."""

    def test_status_defaults_to_active(self):
        """Test that status defaults to ACTIVE when not specified."""
        story_id = uuid4()
        universe_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                neo4j_client.execute_read = lambda q, p: [{"story_id": str(story_id), "universe_id": str(universe_id)}]
                mongo_client.get_collection.return_value.insert_one = MagicMock(
                    return_value=MagicMock(inserted_id=str(uuid4()))
                )

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Default Status Scene"
                )
                result = mongodb_create_scene(params)
                assert result.status == SceneStatus.ACTIVE


class TestP2TemporalContext:
    """Scenario 8: Temporal Context Is Stored."""

    def test_temporal_mode_and_description_stored(self):
        """Test that temporal context fields are stored."""
        story_id = uuid4()
        universe_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                neo4j_client.execute_read = lambda q, p: [{"story_id": str(story_id), "universe_id": str(universe_id)}]
                mongo_client.get_collection.return_value.insert_one = MagicMock(
                    return_value=MagicMock(inserted_id=str(uuid4()))
                )

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Flashback Scene",
                    temporal_mode=TemporalMode.FLASHBACK,
                    time_description="10 years ago"
                )
                result = mongodb_create_scene(params)

                assert result.temporal_mode == TemporalMode.FLASHBACK
                assert result.time_description == "10 years ago"


class TestP2ParticipatingEntitiesStored:
    """Scenario 9: Participating Entities Are Stored."""

    def test_participating_entities_stored(self):
        """Test that participating entities are stored in the scene."""
        story_id = uuid4()
        universe_id = uuid4()
        entity_ids = [uuid4(), uuid4(), uuid4()]

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                def neo4j_read_side_effect(query, params):
                    if "node_ids" in params:
                        return [{"id": i} for i in params["node_ids"]]
                    return [{"story_id": str(story_id), "universe_id": str(universe_id)}]

                neo4j_client.execute_read = neo4j_read_side_effect
                mongo_client.get_collection.return_value.insert_one = MagicMock(
                    return_value=MagicMock(inserted_id=str(uuid4()))
                )

                params = SceneCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    title="Party Scene",
                    participating_entities=entity_ids
                )
                result = mongodb_create_scene(params)

                assert len(result.participating_entities) == 3


class TestP2OpeningTurn:
    """Scenario 10: Opening Turn Is Appended."""

    @pytest.mark.integration
    def test_append_opening_narration_turn(self):
        """Test that opening narration turn can be appended to scene."""
        scene_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            mongo_client = MagicMock()
            mock_mongo.return_value = mongo_client

            mongo_client.get_collection.return_value.update_one = MagicMock()

            turn = mongodb_append_turn(scene_id, TurnCreate(
                speaker=Speaker.GM,
                text="The tavern is crowded tonight..."
            ))

            assert turn is not None
            assert turn.speaker == Speaker.GM
            mongo_client.get_collection.return_value.update_one.assert_called_once()


class TestP2AcceptanceCriteria:
    """Verify all acceptance criteria from P-2-behavior.md."""

    def test_ac1_story_must_exist(self):
        """AC-1: Story must exist before scene creation."""
        with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
            neo4j_client = MagicMock()
            mock_neo.return_value = neo4j_client
            neo4j_client.execute_read = lambda q, p: []

            with pytest.raises(ValueError, match="Story"):
                mongodb_create_scene(SceneCreate(
                    story_id=uuid4(),
                    universe_id=uuid4(),
                    title="Test"
                ))

    def test_ac5_title_required(self):
        """AC-5: Title is required."""
        with pytest.raises(Exception, match="title"):
            mongodb_create_scene(SceneCreate(
                story_id=uuid4(),
                universe_id=uuid4(),
                title=""
            ))

    def test_ac6_status_defaults_to_active(self):
        """AC-6: Status defaults to ACTIVE."""
        with patch("monitor_data.tools.mongodb_tools.scenes.get_mongodb_client") as mock_mongo:
            with patch("monitor_data.tools.mongodb_tools.scenes.get_neo4j_client") as mock_neo:
                mongo_client = MagicMock()
                neo4j_client = MagicMock()
                mock_mongo.return_value = mongo_client
                mock_neo.return_value = neo4j_client

                neo4j_client.execute_read = lambda q, p: [{"story_id": str(uuid4()), "universe_id": str(uuid4())}]
                mongo_client.get_collection.return_value.insert_one = MagicMock(
                    return_value=MagicMock(inserted_id=str(uuid4()))
                )

                result = mongodb_create_scene(SceneCreate(
                    story_id=uuid4(),
                    universe_id=uuid4(),
                    title="Test"
                ))
                assert result.status == SceneStatus.ACTIVE
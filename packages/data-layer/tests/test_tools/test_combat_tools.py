"""
Tests for Combat MongoDB tools (DL-25).

Tests all combat CRUD operations, participant management,
combat log, and outcome tracking.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.base import CombatSide, CombatStatus
from monitor_data.schemas.combat import (
    AddCombatLogEntry,
    AddCombatParticipant,
    CombatCreate,
    CombatEnd,
    CombatEnvironment,
    CombatFilter,
    CombatInitiativeEntry,
    CombatNextRound,
    CombatParticipant,
    CombatResponse,
    CombatSetInitiative,
    CombatStart,
    CombatUpdate,
    CombatUpdateCombatant,
    Condition,
    RemoveCombatParticipant,
    SetCombatOutcome,
    UpdateCombatParticipant,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_add_combat_log_entry,
    mongodb_add_combat_participant,
    mongodb_combat_end,
    mongodb_combat_get,
    mongodb_combat_next_round,
    mongodb_combat_set_initiative,
    mongodb_combat_start,
    mongodb_combat_update_combatant,
    mongodb_create_combat,
    mongodb_delete_combat,
    mongodb_get_combat,
    mongodb_list_combats,
    mongodb_remove_combat_participant,
    mongodb_set_combat_outcome,
    mongodb_update_combat,
    mongodb_update_combat_participant,
)

# =============================================================================
# TEST: mongodb_create_combat
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_create_combat_success(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating a combat encounter."""
    scene_id = uuid4()
    story_id = uuid4()
    encounter_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: mock_combats if name == "combat_encounters" else mock_scenes

    # Mock scene exists
    mock_scenes.find_one.return_value = {"scene_id": str(scene_id)}

    # Mock Neo4j
    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = [{"story_id": str(story_id)}]

    # Test data
    participants = [
        CombatParticipant(
            entity_id=uuid4(),
            name="Fighter",
            side=CombatSide.PC,
            initiative_value=15.5,
            is_active=True,
            conditions=[],
            resources={"hp": 50},
            position=None,
        )
    ]

    params = CombatCreate(
        scene_id=scene_id,
        story_id=story_id,
        participants=participants,
        environment=CombatEnvironment(terrain="forest", lighting="dim"),
    )

    with patch("monitor_data.tools.mongodb_tools.combat.uuid4", return_value=encounter_id):
        result = mongodb_create_combat(params)

    assert result.id == encounter_id
    assert result.scene_id == scene_id
    assert result.story_id == story_id
    assert result.status == CombatStatus.INITIALIZING
    assert result.round == 0
    assert len(result.participants) == 1
    assert result.participants[0].name == "Fighter"
    assert result.environment.terrain == "forest"
    mock_combats.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.combat.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_create_combat_scene_not_found(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating combat with invalid scene_id."""
    scene_id = uuid4()
    story_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: mock_combats if name == "combat_encounters" else mock_scenes

    # Scene does not exist
    mock_scenes.find_one.return_value = None

    params = CombatCreate(
        scene_id=scene_id,
        story_id=story_id,
    )

    with pytest.raises(ValueError, match=f"Scene {scene_id} not found"):
        mongodb_create_combat(params)


@patch("monitor_data.tools.mongodb_tools.combat.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_create_combat_story_not_found(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating combat with invalid story_id."""
    scene_id = uuid4()
    story_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: mock_combats if name == "combat_encounters" else mock_scenes

    # Scene exists but story does not
    mock_scenes.find_one.return_value = {"scene_id": str(scene_id)}
    mock_get_neo4j.return_value = MagicMock(execute_read=MagicMock(return_value=[]))

    params = CombatCreate(
        scene_id=scene_id,
        story_id=story_id,
    )

    with pytest.raises(ValueError, match=f"Story {story_id} not found"):
        mongodb_create_combat(params)


# =============================================================================
# TEST: mongodb_get_combat
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_get_combat_success(mock_get_mongodb: Mock):
    """Test retrieving a combat encounter."""
    encounter_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    combat_doc = {
        "encounter_id": str(encounter_id),
        "scene_id": str(scene_id),
        "story_id": str(story_id),
        "status": "active",
        "round": 3,
        "turn_order": [str(entity_id)],
        "current_turn_index": 0,
        "participants": [
            {
                "entity_id": str(entity_id),
                "name": "Wizard",
                "side": "pc",
                "initiative_value": 18.0,
                "is_active": True,
                "conditions": [],
                "resources": {"hp": 30, "spell_slots": {"1": 2}},
                "position": {"x": 5, "y": 10},
            }
        ],
        "environment": {
            "terrain": "dungeon",
            "lighting": "dark",
            "hazards": [],
            "cover_positions": [],
            "metadata": {},
        },
        "combat_log": [],
        "outcome": None,
        "created_at": datetime.now(UTC),
        "updated_at": None,
    }

    mock_combats.find_one.return_value = combat_doc

    result = mongodb_get_combat(encounter_id)

    assert result is not None
    assert result.id == encounter_id
    assert result.status == CombatStatus.ACTIVE
    assert result.round == 3
    assert len(result.participants) == 1
    assert result.participants[0].name == "Wizard"
    assert result.environment.terrain == "dungeon"
    mock_combats.find_one.assert_called_once_with({"encounter_id": str(encounter_id)})


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_get_combat_not_found(mock_get_mongodb: Mock):
    """Test retrieving non-existent combat."""
    encounter_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    mock_combats.find_one.return_value = None

    result = mongodb_get_combat(encounter_id)

    assert result is None


# =============================================================================
# TEST: mongodb_list_combats
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_list_combats_by_scene(mock_get_mongodb: Mock):
    """Test listing combats filtered by scene_id."""
    scene_id = uuid4()
    encounter1_id = uuid4()
    encounter2_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_cursor = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    combat_docs = [
        {
            "encounter_id": str(encounter1_id),
            "scene_id": str(scene_id),
            "story_id": str(uuid4()),
            "status": "active",
            "round": 1,
            "turn_order": [],
            "current_turn_index": 0,
            "participants": [],
            "environment": {
                "terrain": "normal",
                "lighting": "normal",
                "hazards": [],
                "cover_positions": [],
                "metadata": {},
            },
            "combat_log": [],
            "outcome": None,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        },
        {
            "encounter_id": str(encounter2_id),
            "scene_id": str(scene_id),
            "story_id": str(uuid4()),
            "status": "resolved",
            "round": 5,
            "turn_order": [],
            "current_turn_index": 0,
            "participants": [],
            "environment": {
                "terrain": "normal",
                "lighting": "normal",
                "hazards": [],
                "cover_positions": [],
                "metadata": {},
            },
            "combat_log": [],
            "outcome": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        },
    ]

    mock_combats.count_documents.return_value = 2
    mock_combats.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = combat_docs

    params = CombatFilter(scene_id=scene_id, limit=50, offset=0)
    result = mongodb_list_combats(params)

    assert result.total == 2
    assert len(result.combats) == 2
    assert result.combats[0].id == encounter1_id
    assert result.combats[1].id == encounter2_id
    mock_combats.count_documents.assert_called_once_with({"scene_id": str(scene_id)})


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_list_combats_by_status(mock_get_mongodb: Mock):
    """Test listing combats filtered by status."""
    encounter_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_cursor = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    combat_docs = [
        {
            "encounter_id": str(encounter_id),
            "scene_id": str(uuid4()),
            "story_id": str(uuid4()),
            "status": "active",
            "round": 2,
            "turn_order": [],
            "current_turn_index": 0,
            "participants": [],
            "environment": {
                "terrain": "normal",
                "lighting": "normal",
                "hazards": [],
                "cover_positions": [],
                "metadata": {},
            },
            "combat_log": [],
            "outcome": None,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        },
    ]

    mock_combats.count_documents.return_value = 1
    mock_combats.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = combat_docs

    params = CombatFilter(status="active", limit=50, offset=0)
    result = mongodb_list_combats(params)

    assert result.total == 1
    assert len(result.combats) == 1
    assert result.combats[0].status == CombatStatus.ACTIVE
    mock_combats.count_documents.assert_called_once_with({"status": "active"})


# =============================================================================
# TEST: mongodb_update_combat
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_combat_round(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test updating combat round."""
    encounter_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists
    mock_combats.find_one.return_value = {"encounter_id": str(encounter_id)}

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_combat.round = 5
    mock_get_combat.return_value = updated_combat

    params = CombatUpdate(round=5)
    result = mongodb_update_combat(encounter_id, params)

    assert result.round == 5
    mock_combats.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_combat_status(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test updating combat status."""
    encounter_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists
    mock_combats.find_one.return_value = {"encounter_id": str(encounter_id)}

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_combat.status = CombatStatus.PAUSED
    mock_get_combat.return_value = updated_combat

    params = CombatUpdate(status=CombatStatus.PAUSED)
    result = mongodb_update_combat(encounter_id, params)

    assert result.status == CombatStatus.PAUSED
    mock_combats.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_combat_not_found(mock_get_mongodb: Mock):
    """Test updating non-existent combat."""
    encounter_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Combat does not exist
    mock_combats.find_one.return_value = None

    params = CombatUpdate(round=3)

    with pytest.raises(ValueError, match=f"Combat encounter {encounter_id} not found"):
        mongodb_update_combat(encounter_id, params)


# =============================================================================
# TEST: mongodb_delete_combat
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_delete_combat_success(mock_get_mongodb: Mock):
    """Test deleting a combat encounter."""
    encounter_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_result = Mock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    mock_result.deleted_count = 1
    mock_combats.delete_one.return_value = mock_result

    result = mongodb_delete_combat(encounter_id)

    assert result is True
    mock_combats.delete_one.assert_called_once_with({"encounter_id": str(encounter_id)})


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_delete_combat_not_found(mock_get_mongodb: Mock):
    """Test deleting non-existent combat."""
    encounter_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_result = Mock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    mock_result.deleted_count = 0
    mock_combats.delete_one.return_value = mock_result

    result = mongodb_delete_combat(encounter_id)

    assert result is False


# =============================================================================
# TEST: mongodb_add_combat_participant
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_add_combat_participant_success(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test adding a participant to combat."""
    encounter_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists with no participants
    mock_combats.find_one.return_value = {
        "encounter_id": str(encounter_id),
        "participants": [],
    }

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_combat.participants = [
        CombatParticipant(
            entity_id=entity_id,
            name="Rogue",
            side=CombatSide.PC,
            initiative_value=20.0,
            is_active=True,
            conditions=[],
            resources={"hp": 40},
            position=None,
        )
    ]
    mock_get_combat.return_value = updated_combat

    params = AddCombatParticipant(
        encounter_id=encounter_id,
        entity_id=entity_id,
        name="Rogue",
        side=CombatSide.PC,
        initiative_value=20.0,
    )

    result = mongodb_add_combat_participant(params)

    assert len(result.participants) == 1
    assert result.participants[0].name == "Rogue"
    mock_combats.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_add_combat_participant_already_exists(mock_get_mongodb: Mock):
    """Test adding duplicate participant."""
    encounter_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists with participant already in it
    mock_combats.find_one.return_value = {
        "encounter_id": str(encounter_id),
        "participants": [{"entity_id": str(entity_id), "name": "Rogue"}],
    }

    params = AddCombatParticipant(
        encounter_id=encounter_id,
        entity_id=entity_id,
        name="Rogue",
        side=CombatSide.PC,
    )

    with pytest.raises(ValueError, match=f"Entity {entity_id} is already in combat"):
        mongodb_add_combat_participant(params)


# =============================================================================
# TEST: mongodb_update_combat_participant
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_participant_initiative(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test updating participant initiative."""
    encounter_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat with participant
    mock_combats.find_one.return_value = {
        "encounter_id": str(encounter_id),
        "participants": [{"entity_id": str(entity_id), "name": "Cleric", "initiative_value": 12.0}],
    }

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_participant = Mock()
    updated_participant.initiative_value = 18.5
    updated_combat.participants = [updated_participant]
    mock_get_combat.return_value = updated_combat

    params = UpdateCombatParticipant(
        encounter_id=encounter_id,
        entity_id=entity_id,
        initiative_value=18.5,
    )

    result = mongodb_update_combat_participant(params)

    assert result.participants[0].initiative_value == 18.5
    mock_combats.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_participant_conditions(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test updating participant conditions."""
    encounter_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat with participant
    mock_combats.find_one.return_value = {
        "encounter_id": str(encounter_id),
        "participants": [{"entity_id": str(entity_id), "name": "Paladin", "conditions": []}],
    }

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_participant = Mock()
    updated_participant.conditions = [
        Condition(
            name="Blessed",
            source="Cleric",
            duration_type="rounds",
            duration_remaining=3,
        )
    ]
    updated_combat.participants = [updated_participant]
    mock_get_combat.return_value = updated_combat

    conditions = [
        Condition(
            name="Blessed",
            source="Cleric",
            duration_type="rounds",
            duration_remaining=3,
        )
    ]
    params = UpdateCombatParticipant(
        encounter_id=encounter_id,
        entity_id=entity_id,
        conditions=conditions,
    )

    result = mongodb_update_combat_participant(params)

    assert len(result.participants[0].conditions) == 1
    assert result.participants[0].conditions[0].name == "Blessed"
    mock_combats.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_participant_resources(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test updating participant resources."""
    encounter_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat with participant
    mock_combats.find_one.return_value = {
        "encounter_id": str(encounter_id),
        "participants": [{"entity_id": str(entity_id), "name": "Barbarian", "resources": {"hp": 100}}],
    }

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_participant = Mock()
    updated_participant.resources = {"hp": 75, "rage": 2}
    updated_combat.participants = [updated_participant]
    mock_get_combat.return_value = updated_combat

    params = UpdateCombatParticipant(
        encounter_id=encounter_id,
        entity_id=entity_id,
        resources={"hp": 75, "rage": 2},
    )

    result = mongodb_update_combat_participant(params)

    assert result.participants[0].resources == {"hp": 75, "rage": 2}
    mock_combats.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_participant_not_found(mock_get_mongodb: Mock):
    """Test updating non-existent participant."""
    encounter_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Combat exists but participant does not
    mock_combats.find_one.return_value = {
        "encounter_id": str(encounter_id),
        "participants": [],
    }

    params = UpdateCombatParticipant(
        encounter_id=encounter_id,
        entity_id=entity_id,
        initiative_value=15.0,
    )

    with pytest.raises(ValueError, match=f"Participant {entity_id} not found"):
        mongodb_update_combat_participant(params)


# =============================================================================
# TEST: mongodb_remove_combat_participant
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_remove_participant_success(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test removing a participant from combat."""
    encounter_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat with participant
    mock_combats.find_one.return_value = {
        "encounter_id": str(encounter_id),
        "participants": [{"entity_id": str(entity_id), "name": "Goblin"}],
    }

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_combat.participants = []
    mock_get_combat.return_value = updated_combat

    params = RemoveCombatParticipant(
        encounter_id=encounter_id,
        entity_id=entity_id,
    )

    result = mongodb_remove_combat_participant(params)

    assert len(result.participants) == 0
    mock_combats.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_remove_participant_not_found(mock_get_mongodb: Mock):
    """Test removing non-existent participant."""
    encounter_id = uuid4()
    entity_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Combat exists but participant does not
    mock_combats.find_one.return_value = {
        "encounter_id": str(encounter_id),
        "participants": [],
    }

    params = RemoveCombatParticipant(
        encounter_id=encounter_id,
        entity_id=entity_id,
    )

    with pytest.raises(ValueError, match=f"Participant {entity_id} not found"):
        mongodb_remove_combat_participant(params)


# =============================================================================
# TEST: mongodb_add_combat_log_entry
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_add_log_entry_success(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test adding a combat log entry."""
    encounter_id = uuid4()
    actor_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists
    mock_combats.find_one.return_value = {"encounter_id": str(encounter_id)}

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    log_entry = Mock()
    log_entry.round = 2
    log_entry.turn = 3
    log_entry.action = "Attack with longsword"
    log_entry.summary = "Fighter attacks goblin - HIT for 8 damage"
    updated_combat.combat_log = [log_entry]
    mock_get_combat.return_value = updated_combat

    params = AddCombatLogEntry(
        encounter_id=encounter_id,
        round=2,
        turn=3,
        actor_id=actor_id,
        action="Attack with longsword",
        summary="Fighter attacks goblin - HIT for 8 damage",
    )

    result = mongodb_add_combat_log_entry(params)

    assert len(result.combat_log) == 1
    assert result.combat_log[0].action == "Attack with longsword"
    mock_combats.update_one.assert_called_once()


# =============================================================================
# TEST: mongodb_set_combat_outcome
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_set_outcome_success(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test setting combat outcome."""
    encounter_id = uuid4()
    survivor_id = uuid4()
    casualty_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists
    mock_combats.find_one.return_value = {"encounter_id": str(encounter_id)}

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    outcome = Mock()
    outcome.result = "victory"
    outcome.winning_side = CombatSide.PC
    outcome.survivors = [survivor_id]
    outcome.casualties = [casualty_id]
    outcome.xp_awarded = 450
    updated_combat.outcome = outcome
    updated_combat.status = CombatStatus.RESOLVED
    mock_get_combat.return_value = updated_combat

    params = SetCombatOutcome(
        encounter_id=encounter_id,
        result="victory",
        winning_side=CombatSide.PC,
        survivors=[survivor_id],
        casualties=[casualty_id],
        xp_awarded=450,
    )

    result = mongodb_set_combat_outcome(params)

    assert result.outcome is not None
    assert result.outcome.result == "victory"
    assert result.outcome.xp_awarded == 450
    assert result.status == CombatStatus.RESOLVED
    mock_combats.update_one.assert_called_once()


# =============================================================================
# TEST: mongodb_list_combats - by story_id
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_list_combats_by_story(mock_get_mongodb: Mock):
    """Test listing combats filtered by story_id."""
    encounter_id = uuid4()
    story_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_cursor = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    combat_docs = [
        {
            "encounter_id": str(encounter_id),
            "scene_id": str(uuid4()),
            "story_id": str(story_id),
            "status": "active",
            "round": 2,
            "turn_order": [],
            "current_turn_index": 0,
            "participants": [],
            "environment": {
                "terrain": "normal",
                "lighting": "normal",
                "hazards": [],
                "cover_positions": [],
                "metadata": {},
            },
            "combat_log": [],
            "outcome": None,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        },
    ]

    mock_combats.count_documents.return_value = 1
    mock_combats.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = combat_docs

    params = CombatFilter(story_id=story_id, limit=50, offset=0)
    result = mongodb_list_combats(params)

    assert result.total == 1
    assert len(result.combats) == 1
    assert str(result.combats[0].story_id) == str(story_id)
    mock_combats.count_documents.assert_called_once_with({"story_id": str(story_id)})


# =============================================================================
# TEST: mongodb_update_combat - turn_order
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_combat_turn_order(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test updating combat turn order."""
    encounter_id = uuid4()
    turn_order_ids = [uuid4(), uuid4(), uuid4()]

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists
    mock_combats.find_one.return_value = {"encounter_id": str(encounter_id)}

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_combat.turn_order = turn_order_ids
    mock_get_combat.return_value = updated_combat

    params = CombatUpdate(turn_order=turn_order_ids)
    result = mongodb_update_combat(encounter_id, params)

    assert len(result.turn_order) == 3
    assert result.turn_order == turn_order_ids
    mock_combats.update_one.assert_called_once()


# =============================================================================
# TEST: mongodb_update_combat - current_turn_index
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_update_combat_current_turn_index(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test updating combat current turn index."""
    encounter_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists
    mock_combats.find_one.return_value = {"encounter_id": str(encounter_id)}

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    updated_combat.current_turn_index = 2
    mock_get_combat.return_value = updated_combat

    params = CombatUpdate(current_turn_index=2)
    result = mongodb_update_combat(encounter_id, params)

    assert result.current_turn_index == 2
    mock_combats.update_one.assert_called_once()


# =============================================================================
# TEST: mongodb_add_combat_log_entry - with resolution_id
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_add_log_entry_with_resolution(mock_get_mongodb: Mock, mock_get_combat: Mock):
    """Test adding a combat log entry with resolution link."""
    encounter_id = uuid4()
    actor_id = uuid4()
    resolution_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_combats

    # Mock combat exists
    mock_combats.find_one.return_value = {"encounter_id": str(encounter_id)}

    # Mock updated result
    updated_combat = Mock(spec=CombatResponse)
    log_entry = Mock()
    log_entry.round = 2
    log_entry.turn = 3
    log_entry.actor_id = actor_id
    log_entry.action = "Cast fireball"
    log_entry.resolution_id = resolution_id
    log_entry.summary = "Wizard casts fireball - 3 goblins killed"
    updated_combat.combat_log = [log_entry]
    mock_get_combat.return_value = updated_combat

    params = AddCombatLogEntry(
        encounter_id=encounter_id,
        round=2,
        turn=3,
        actor_id=actor_id,
        action="Cast fireball",
        resolution_id=resolution_id,
        summary="Wizard casts fireball - 3 goblins killed",
    )

    result = mongodb_add_combat_log_entry(params)

    assert len(result.combat_log) == 1
    assert result.combat_log[0].action == "Cast fireball"
    assert result.combat_log[0].resolution_id == resolution_id
    mock_combats.update_one.assert_called_once()


# =============================================================================
# TEST: mongodb_create_combat - with environmental hazards
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.combat.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.combat.get_mongodb_client")
def test_create_combat_with_hazards(mock_get_mongodb: Mock, mock_get_neo4j: Mock):
    """Test creating a combat encounter with environmental hazards."""
    scene_id = uuid4()
    story_id = uuid4()

    mock_mongodb = MagicMock()
    mock_combats = MagicMock()
    mock_scenes = MagicMock()
    mock_neo4j_client = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: mock_combats if name == "combat_encounters" else mock_scenes
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock scene exists
    mock_scenes.find_one.return_value = {"scene_id": str(scene_id)}

    # Mock story exists
    mock_neo4j_client.execute_read.return_value = [{"story_id": str(story_id)}]

    # Mock the combat created (insert_one doesn't need to return specific value)
    # but _convert_combat_doc_to_response will call find_one
    inserted_id = uuid4()
    with patch("monitor_data.tools.mongodb_tools.combat.uuid4", return_value=inserted_id):
        mock_combats.find_one.return_value = {
            "encounter_id": str(inserted_id),
            "scene_id": str(scene_id),
            "story_id": str(story_id),
            "status": "initializing",
            "round": 0,
            "turn_order": [],
            "current_turn_index": 0,
            "participants": [],
            "environment": {
                "terrain": "dungeon_corridor",
                "lighting": "dim",
                "hazards": [
                    {"type": "spike_pit", "damage": "1d6", "location": "center"},
                    {"type": "collapsing_floor", "damage": "2d6", "location": "north"},
                ],
                "cover_positions": [
                    {"type": "pillar", "location": "east", "bonus": "+2 AC"},
                ],
                "metadata": {"danger_level": "high"},
            },
            "combat_log": [],
            "outcome": None,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }

        environment = CombatEnvironment(
            terrain="dungeon_corridor",
            lighting="dim",
            hazards=[
                {"type": "spike_pit", "damage": "1d6", "location": "center"},
                {"type": "collapsing_floor", "damage": "2d6", "location": "north"},
            ],
            cover_positions=[
                {"type": "pillar", "location": "east", "bonus": "+2 AC"},
            ],
            metadata={"danger_level": "high"},
        )

        params = CombatCreate(scene_id=scene_id, story_id=story_id, environment=environment)
        result = mongodb_create_combat(params)

    assert result.scene_id == scene_id
    assert result.story_id == story_id
    assert len(result.environment.hazards) == 2
    assert result.environment.hazards[0]["type"] == "spike_pit"
    assert result.environment.metadata["danger_level"] == "high"
    mock_combats.insert_one.assert_called_once()


# =============================================================================
# TEST: session combat tracker (CF-9)
# =============================================================================
# These tools are ephemeral table state keyed by (universe_id, session_id).
# The fake collection below is stateful so start → get → update → initiative
# → next-round → end round-trips exercise the real persistence paths.


class _FakeSessionColl:
    """Minimal in-memory stand-in for the ``session_combats`` collection."""

    def __init__(self) -> None:
        self.docs: list[dict] = []

    def _match(self, d: dict, q: dict) -> bool:
        return all(d.get(k) == v for k, v in q.items())

    def find_one(self, q: dict, *a, **k) -> dict | None:
        return next((d for d in self.docs if self._match(d, q)), None)

    def replace_one(self, q: dict, doc: dict, upsert: bool = False) -> None:
        for i, d in enumerate(self.docs):
            if self._match(d, q):
                self.docs[i] = dict(doc)
                return
        if upsert:
            self.docs.append(dict(doc))


@pytest.fixture
def session_coll() -> _FakeSessionColl:
    return _FakeSessionColl()


@pytest.fixture
def patch_session_mongo(session_coll: _FakeSessionColl):
    """Patch get_mongodb_client so session-combat tools hit the fake collection."""
    mock_client = MagicMock()
    mock_client.get_collection.return_value = session_coll
    with patch(
        "monitor_data.tools.mongodb_tools.combat.get_mongodb_client",
        return_value=mock_client,
    ):
        yield session_coll


def _start_params(**over):
    base = {
        "universe_id": uuid4(),
        "session_id": "sess-1",
        "combatants": [
            {"name": "Mira", "side": CombatSide.PC, "hp": 24, "max_hp": 24},
            {"name": "Goblin", "side": CombatSide.ENEMY, "hp": 7, "max_hp": 7},
            {"name": "Goblin Boss", "side": CombatSide.ENEMY, "hp": 14, "max_hp": 14},
        ],
    }
    base.update(over)
    return CombatStart(**base)


def test_session_combat_start_creates_initial_state(patch_session_mongo):
    state = mongodb_combat_start(_start_params())
    assert state.status == CombatStatus.INITIATIVE
    assert state.round == 1
    assert state.turn_order == []
    assert state.ended_at is None
    assert {c.name for c in state.combatants} == {"Mira", "Goblin", "Goblin Boss"}
    # Combatants get their own instance ids (distinct from canon entity ids).
    assert len({c.id for c in state.combatants}) == 3


def test_session_combat_start_rejects_hp_over_max(patch_session_mongo):
    with pytest.raises(ValueError, match="cannot exceed max_hp"):
        mongodb_combat_start(
            _start_params(combatants=[{"name": "Broken", "hp": 11, "max_hp": 10}])
        )


def test_session_combat_start_replaces_prior_state_for_same_key(patch_session_mongo):
    uid = uuid4()
    first = mongodb_combat_start(_start_params(universe_id=uid))
    second = mongodb_combat_start(
        _start_params(universe_id=uid, combatants=[{"name": "Solo", "hp": 5, "max_hp": 5}])
    )
    assert len(patch_session_mongo.docs) == 1  # same (universe, session) key
    assert [c.name for c in second.combatants] == ["Solo"]
    assert second.started_at >= first.started_at


def test_session_combat_get_returns_none_when_absent(patch_session_mongo):
    assert mongodb_combat_get(uuid4(), "nope") is None


def test_session_combat_get_round_trips_state(patch_session_mongo):
    started = mongodb_combat_start(_start_params())
    fetched = mongodb_combat_get(started.universe_id, started.session_id)
    assert fetched is not None
    assert fetched.universe_id == started.universe_id
    assert fetched.session_id == "sess-1"
    assert [c.name for c in fetched.combatants] == [c.name for c in started.combatants]


def test_session_combat_is_isolated_per_universe(patch_session_mongo):
    uid_a, uid_b = uuid4(), uuid4()
    mongodb_combat_start(_start_params(universe_id=uid_a))
    assert mongodb_combat_get(uid_b, "sess-1") is None


def test_update_combatant_damage_absorbs_temp_hp_first(patch_session_mongo):
    started = mongodb_combat_start(
        _start_params(combatants=[{"name": "Mira", "side": CombatSide.PC, "hp": 20, "max_hp": 20, "temp_hp": 5}])
    )
    mira = started.combatants[0]
    # 8 damage: 5 absorbed by temp HP, 3 hit HP.
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=mira.id,
            hp_delta=-8,
        )
    )
    updated = state.combatants[0]
    assert updated.temp_hp == 0
    assert updated.hp == 17


def test_update_combatant_damage_floors_at_zero(patch_session_mongo):
    started = mongodb_combat_start(
        _start_params(combatants=[{"name": "Goblin", "hp": 7, "max_hp": 7}])
    )
    goblin = started.combatants[0]
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=goblin.id,
            hp_delta=-99,
        )
    )
    assert state.combatants[0].hp == 0


def test_update_combatant_heal_clamps_to_max(patch_session_mongo):
    started = mongodb_combat_start(
        _start_params(combatants=[{"name": "Mira", "side": CombatSide.PC, "hp": 10, "max_hp": 20}])
    )
    mira = started.combatants[0]
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=mira.id,
            hp_delta=50,
        )
    )
    assert state.combatants[0].hp == 20


def test_update_combatant_absolute_hp_overrides_delta(patch_session_mongo):
    started = mongodb_combat_start(
        _start_params(combatants=[{"name": "Mira", "side": CombatSide.PC, "hp": 10, "max_hp": 20}])
    )
    mira = started.combatants[0]
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=mira.id,
            hp=3,
            hp_delta=-9,
        )
    )
    assert state.combatants[0].hp == 3


def test_update_combatant_conditions_add_and_remove(patch_session_mongo):
    started = mongodb_combat_start(
        _start_params(combatants=[{"name": "Mira", "side": CombatSide.PC, "hp": 20, "max_hp": 20}])
    )
    mira = started.combatants[0]
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=mira.id,
            conditions_add=["poisoned", "prone"],
        )
    )
    assert state.combatants[0].conditions == ["poisoned", "prone"]
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=mira.id,
            conditions_add=["poisoned"],  # duplicate is a no-op
            conditions_remove=["prone"],
        )
    )
    assert state.combatants[0].conditions == ["poisoned"]


def test_update_combatant_dead_flag_forces_hp_zero(patch_session_mongo):
    started = mongodb_combat_start(
        _start_params(combatants=[{"name": "Goblin", "hp": 7, "max_hp": 7}])
    )
    goblin = started.combatants[0]
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=goblin.id,
            dead=True,
            unconscious=True,
        )
    )
    updated = state.combatants[0]
    assert updated.dead is True
    assert updated.unconscious is True
    assert updated.hp == 0


def test_update_combatant_concentration_set_and_clear(patch_session_mongo):
    started = mongodb_combat_start(
        _start_params(combatants=[{"name": "Mira", "side": CombatSide.PC, "hp": 20, "max_hp": 20}])
    )
    mira = started.combatants[0]
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=mira.id,
            concentration="bless: 3 allies",
        )
    )
    assert state.combatants[0].concentration == "bless: 3 allies"
    state = mongodb_combat_update_combatant(
        CombatUpdateCombatant(
            universe_id=started.universe_id,
            session_id=started.session_id,
            combatant_id=mira.id,
            concentration="",  # '' clears
        )
    )
    assert state.combatants[0].concentration is None


def test_update_combatant_missing_encounter_raises(patch_session_mongo):
    with pytest.raises(ValueError, match="No combat encounter"):
        mongodb_combat_update_combatant(
            CombatUpdateCombatant(
                universe_id=uuid4(),
                session_id="ghost",
                combatant_id=uuid4(),
                hp_delta=-1,
            )
        )


def test_update_combatant_unknown_combatant_raises(patch_session_mongo):
    started = mongodb_combat_start(_start_params())
    with pytest.raises(ValueError, match="not found in encounter"):
        mongodb_combat_update_combatant(
            CombatUpdateCombatant(
                universe_id=started.universe_id,
                session_id=started.session_id,
                combatant_id=uuid4(),
                hp_delta=-1,
            )
        )


def test_set_initiative_orders_by_score_then_tiebreak(patch_session_mongo):
    started = mongodb_combat_start(_start_params())
    by_name = {c.name: c for c in started.combatants}
    state = mongodb_combat_set_initiative(
        CombatSetInitiative(
            universe_id=started.universe_id,
            session_id=started.session_id,
            entries=[
                CombatInitiativeEntry(combatant_id=by_name["Goblin"].id, initiative=12, tiebreak=3),
                CombatInitiativeEntry(combatant_id=by_name["Mira"].id, initiative=18, tiebreak=1),
                CombatInitiativeEntry(combatant_id=by_name["Goblin Boss"].id, initiative=12, tiebreak=5),
            ],
        )
    )
    order = [c.name for c in state.combatants]
    # Mira wins outright; the 12-tie breaks on tiebreak (Boss 5 > Goblin 3).
    assert order == ["Mira", "Goblin Boss", "Goblin"]
    assert state.turn_order == [c.id for c in state.combatants]
    assert state.status == CombatStatus.ACTIVE
    assert state.combatants[0].initiative == 18


def test_set_initiative_unrolled_sink_and_name_tiebreak(patch_session_mongo):
    started = mongodb_combat_start(
        _start_params(
            combatants=[
                {"name": "zeta", "hp": 5, "max_hp": 5},
                {"name": "alpha", "hp": 5, "max_hp": 5},
                {"name": "mid", "hp": 5, "max_hp": 5},
            ]
        )
    )
    by_name = {c.name: c for c in started.combatants}
    state = mongodb_combat_set_initiative(
        CombatSetInitiative(
            universe_id=started.universe_id,
            session_id=started.session_id,
            entries=[
                # Exact tie on initiative and tiebreak → alphabetical: alpha < zeta.
                CombatInitiativeEntry(combatant_id=by_name["zeta"].id, initiative=10),
                CombatInitiativeEntry(combatant_id=by_name["alpha"].id, initiative=10),
                # "mid" never rolls → sinks below both.
            ],
        )
    )
    assert [c.name for c in state.combatants] == ["alpha", "zeta", "mid"]
    assert state.combatants[2].initiative is None


def test_set_initiative_unknown_combatant_raises(patch_session_mongo):
    started = mongodb_combat_start(_start_params())
    with pytest.raises(ValueError, match="Unknown combatant"):
        mongodb_combat_set_initiative(
            CombatSetInitiative(
                universe_id=started.universe_id,
                session_id=started.session_id,
                entries=[CombatInitiativeEntry(combatant_id=uuid4(), initiative=10)],
            )
        )


def test_next_round_increments_and_refuses_after_end(patch_session_mongo):
    started = mongodb_combat_start(_start_params())
    state = mongodb_combat_next_round(
        CombatNextRound(universe_id=started.universe_id, session_id=started.session_id)
    )
    assert state.round == 2
    state = mongodb_combat_next_round(
        CombatNextRound(universe_id=started.universe_id, session_id=started.session_id)
    )
    assert state.round == 3
    mongodb_combat_end(CombatEnd(universe_id=started.universe_id, session_id=started.session_id))
    with pytest.raises(ValueError, match="already ended"):
        mongodb_combat_next_round(
            CombatNextRound(universe_id=started.universe_id, session_id=started.session_id)
        )


def test_combat_end_resolves_and_stamps_ended_at(patch_session_mongo):
    started = mongodb_combat_start(_start_params())
    state = mongodb_combat_end(
        CombatEnd(universe_id=started.universe_id, session_id=started.session_id)
    )
    assert state.status == CombatStatus.RESOLVED
    assert state.ended_at is not None
    # Round-trip: the resolved status survives persistence.
    fetched = mongodb_combat_get(started.universe_id, started.session_id)
    assert fetched is not None
    assert fetched.status == CombatStatus.RESOLVED


def test_combat_end_missing_encounter_raises(patch_session_mongo):
    with pytest.raises(ValueError, match="No combat encounter"):
        mongodb_combat_end(CombatEnd(universe_id=uuid4(), session_id="ghost"))

"""
Tests for Combat MongoDB tools (DL-25).

Tests all combat CRUD operations, participant management,
combat log, and outcome tracking.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.combat import (
    CombatCreate,
    CombatUpdate,
    CombatResponse,
    CombatFilter,
    CombatParticipant,
    AddCombatParticipant,
    UpdateCombatParticipant,
    RemoveCombatParticipant,
    CombatEnvironment,
    AddCombatLogEntry,
    SetCombatOutcome,
    Condition,
)
from monitor_data.schemas.base import CombatStatus, CombatSide
from monitor_data.tools.mongodb_tools import (
    mongodb_create_combat,
    mongodb_get_combat,
    mongodb_list_combats,
    mongodb_update_combat,
    mongodb_delete_combat,
    mongodb_add_combat_participant,
    mongodb_update_combat_participant,
    mongodb_remove_combat_participant,
    mongodb_add_combat_log_entry,
    mongodb_set_combat_outcome,
)


# =============================================================================
# TEST: mongodb_create_combat
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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
    mock_mongodb.get_collection.side_effect = lambda name: (
        mock_combats if name == "combat_encounters" else mock_scenes
    )

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

    with patch("monitor_data.tools.mongodb_tools.uuid4", return_value=encounter_id):
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


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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
    mock_mongodb.get_collection.side_effect = lambda name: (
        mock_combats if name == "combat_encounters" else mock_scenes
    )

    # Scene does not exist
    mock_scenes.find_one.return_value = None

    params = CombatCreate(
        scene_id=scene_id,
        story_id=story_id,
    )

    with pytest.raises(ValueError, match=f"Scene {scene_id} not found"):
        mongodb_create_combat(params)


# =============================================================================
# TEST: mongodb_get_combat
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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
        "created_at": datetime.now(timezone.utc),
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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
            "created_at": datetime.now(timezone.utc),
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
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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
            "created_at": datetime.now(timezone.utc),
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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
        "participants": [
            {"entity_id": str(entity_id), "name": "Cleric", "initiative_value": 12.0}
        ],
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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
        "participants": [
            {"entity_id": str(entity_id), "name": "Paladin", "conditions": []}
        ],
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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
        "participants": [
            {"entity_id": str(entity_id), "name": "Barbarian", "resources": {"hp": 100}}
        ],
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.mongodb_get_combat")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
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

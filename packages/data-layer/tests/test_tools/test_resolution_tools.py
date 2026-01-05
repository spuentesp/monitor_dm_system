"""
Tests for Resolution MongoDB tools (DL-24).

Tests all resolution CRUD operations including dice rolls,
contested resolutions, card draws, and effects tracking.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.resolutions import (
    ResolutionCreate,
    ResolutionUpdate,
    ResolutionFilter,
    ActionType,
    ResolutionType,
    SuccessLevel,
    EffectType,
    Modifier,
    RollResult,
    ContestedRoll,
    CardDraw,
    Mechanics,
    Effect,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_resolution,
    mongodb_get_resolution,
    mongodb_list_resolutions,
    mongodb_update_resolution,
    mongodb_delete_resolution,
)


# =============================================================================
# TEST: mongodb_create_resolution
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_resolution_success(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating a resolution record."""
    turn_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()
    actor_id = uuid4()
    resolution_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: (
        mock_resolutions if name == "resolutions" else mock_scenes
    )

    # Mock scene with turn
    mock_scenes.find_one.return_value = {
        "scene_id": str(scene_id),
        "turns": [{"turn_id": str(turn_id)}],
    }

    # Mock Neo4j
    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = [{"story_id": str(story_id)}]

    # Test data - simple dice roll
    mechanics = Mechanics(
        formula="1d20+5 vs DC 15",
        modifiers=[
            Modifier(source="Strength", value=3, reason="Strength modifier"),
            Modifier(source="Proficiency", value=2, reason="Proficiency bonus"),
        ],
        target=15,
        roll=RollResult(
            raw_rolls=[18],
            kept_rolls=[18],
            total=23,
            natural=18,
            critical=False,
            fumble=False,
        ),
    )

    effects = [
        Effect(
            effect_type=EffectType.DAMAGE,
            target_id=uuid4(),
            magnitude=10,
            damage_type="slashing",
            description="Sword damage",
        )
    ]

    params = ResolutionCreate(
        turn_id=turn_id,
        scene_id=scene_id,
        story_id=story_id,
        actor_id=actor_id,
        action="Fighter attacks with longsword",
        action_type=ActionType.COMBAT,
        resolution_type=ResolutionType.DICE,
        mechanics=mechanics,
        success_level=SuccessLevel.SUCCESS,
        margin=8,
        effects=effects,
        description="The longsword strikes true, dealing 10 damage",
    )

    with patch("monitor_data.tools.mongodb_tools.uuid4", return_value=resolution_id):
        result = mongodb_create_resolution(params)

    assert result.id == resolution_id
    assert result.turn_id == turn_id
    assert result.scene_id == scene_id
    assert result.story_id == story_id
    assert result.actor_id == actor_id
    assert result.action == "Fighter attacks with longsword"
    assert result.action_type == ActionType.COMBAT
    assert result.resolution_type == ResolutionType.DICE
    assert result.success_level == SuccessLevel.SUCCESS
    assert result.margin == 8
    assert len(result.effects) == 1
    assert result.mechanics.roll.total == 23
    mock_resolutions.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_resolution_scene_not_found(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating resolution with invalid scene_id."""
    turn_id = uuid4()
    scene_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: (
        mock_resolutions if name == "resolutions" else mock_scenes
    )

    # Scene does not exist
    mock_scenes.find_one.return_value = None

    params = ResolutionCreate(
        turn_id=turn_id,
        scene_id=scene_id,
        story_id=uuid4(),
        actor_id=uuid4(),
        action="Test action",
        action_type=ActionType.SKILL,
        resolution_type=ResolutionType.DICE,
        mechanics=Mechanics(formula="1d20", target=10),
        success_level=SuccessLevel.SUCCESS,
    )

    with pytest.raises(ValueError, match=f"Scene {scene_id} not found"):
        mongodb_create_resolution(params)


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_resolution_turn_not_found(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating resolution with invalid turn_id."""
    turn_id = uuid4()
    scene_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: (
        mock_resolutions if name == "resolutions" else mock_scenes
    )

    # Scene exists but turn doesn't
    mock_scenes.find_one.return_value = {
        "scene_id": str(scene_id),
        "turns": [{"turn_id": str(uuid4())}],  # Different turn_id
    }

    params = ResolutionCreate(
        turn_id=turn_id,
        scene_id=scene_id,
        story_id=uuid4(),
        actor_id=uuid4(),
        action="Test action",
        action_type=ActionType.SKILL,
        resolution_type=ResolutionType.DICE,
        mechanics=Mechanics(formula="1d20", target=10),
        success_level=SuccessLevel.SUCCESS,
    )

    with pytest.raises(
        ValueError, match=f"Turn {turn_id} not found in scene {scene_id}"
    ):
        mongodb_create_resolution(params)


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_resolution_story_not_found(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating resolution with invalid story_id."""
    turn_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: (
        mock_resolutions if name == "resolutions" else mock_scenes
    )

    # Scene and turn exist
    mock_scenes.find_one.return_value = {
        "scene_id": str(scene_id),
        "turns": [{"turn_id": str(turn_id)}],
    }

    # Story doesn't exist in Neo4j
    mock_get_neo4j.return_value = MagicMock(execute_read=MagicMock(return_value=[]))

    params = ResolutionCreate(
        turn_id=turn_id,
        scene_id=scene_id,
        story_id=story_id,
        actor_id=uuid4(),
        action="Test action",
        action_type=ActionType.SKILL,
        resolution_type=ResolutionType.DICE,
        mechanics=Mechanics(formula="1d20", target=10),
        success_level=SuccessLevel.SUCCESS,
    )

    with pytest.raises(ValueError, match=f"Story {story_id} not found"):
        mongodb_create_resolution(params)


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_resolution_contested(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating a contested resolution."""
    turn_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()
    actor_id = uuid4()
    opponent_id = uuid4()
    resolution_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: (
        mock_resolutions if name == "resolutions" else mock_scenes
    )

    mock_scenes.find_one.return_value = {
        "scene_id": str(scene_id),
        "turns": [{"turn_id": str(turn_id)}],
    }

    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = [{"story_id": str(story_id)}]

    # Contested roll data
    mechanics = Mechanics(
        formula="1d20+3 vs 1d20+2",
        modifiers=[Modifier(source="Athletics", value=3, reason="Athletics skill")],
        roll=RollResult(raw_rolls=[15], kept_rolls=[15], total=18, natural=15),
        contested=ContestedRoll(
            opponent_id=opponent_id,
            opponent_roll=RollResult(
                raw_rolls=[12], kept_rolls=[12], total=14, natural=12
            ),
            opponent_modifiers=[
                Modifier(source="Athletics", value=2, reason="Athletics skill")
            ],
            margin_of_victory=4,
        ),
    )

    params = ResolutionCreate(
        turn_id=turn_id,
        scene_id=scene_id,
        story_id=story_id,
        actor_id=actor_id,
        action="Grapple attempt",
        action_type=ActionType.COMBAT,
        resolution_type=ResolutionType.CONTESTED,
        mechanics=mechanics,
        success_level=SuccessLevel.SUCCESS,
        margin=4,
        effects=[
            Effect(
                effect_type=EffectType.CONDITION,
                target_id=opponent_id,
                magnitude=0,
                condition="grappled",
                description="Target is grappled",
            )
        ],
    )

    with patch("monitor_data.tools.mongodb_tools.uuid4", return_value=resolution_id):
        result = mongodb_create_resolution(params)

    assert result.resolution_type == ResolutionType.CONTESTED
    assert result.mechanics.contested is not None
    assert result.mechanics.contested.opponent_id == opponent_id
    assert result.mechanics.contested.margin_of_victory == 4


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_resolution_card_draw(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating a card-based resolution."""
    turn_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()
    resolution_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()
    mock_scenes = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.side_effect = lambda name: (
        mock_resolutions if name == "resolutions" else mock_scenes
    )

    mock_scenes.find_one.return_value = {
        "scene_id": str(scene_id),
        "turns": [{"turn_id": str(turn_id)}],
    }

    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = [{"story_id": str(story_id)}]

    # Card draw data
    mechanics = Mechanics(
        formula="Draw 2 cards, highest wins",
        card_draw=CardDraw(
            cards_drawn=["Hearts-King", "Spades-Queen"],
            total_value=23,  # King=13 + Queen=10
            special="High card: King of Hearts",
        ),
    )

    params = ResolutionCreate(
        turn_id=turn_id,
        scene_id=scene_id,
        story_id=story_id,
        actor_id=uuid4(),
        action="Initiative draw",
        action_type=ActionType.OTHER,
        resolution_type=ResolutionType.CARD,
        mechanics=mechanics,
        success_level=SuccessLevel.SUCCESS,
    )

    with patch("monitor_data.tools.mongodb_tools.uuid4", return_value=resolution_id):
        result = mongodb_create_resolution(params)

    assert result.resolution_type == ResolutionType.CARD
    assert result.mechanics.card_draw is not None
    assert len(result.mechanics.card_draw.cards_drawn) == 2
    assert result.mechanics.card_draw.total_value == 23


# =============================================================================
# TEST: mongodb_get_resolution
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_resolution_success(mock_get_mongodb: Mock):
    """Test getting a resolution by ID."""
    resolution_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    # Mock resolution document
    resolution_doc = {
        "resolution_id": str(resolution_id),
        "turn_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "actor_id": str(uuid4()),
        "action": "Attack",
        "action_type": "combat",
        "resolution_type": "dice",
        "mechanics": {
            "formula": "1d20+5",
            "modifiers": [],
            "target": 15,
            "roll": {
                "raw_rolls": [12],
                "kept_rolls": [12],
                "total": 17,
                "natural": 12,
                "critical": False,
                "fumble": False,
            },
        },
        "success_level": "success",
        "margin": 2,
        "effects": [],
        "description": None,
        "gm_notes": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": None,
    }

    mock_resolutions.find_one.return_value = resolution_doc

    result = mongodb_get_resolution(resolution_id)

    assert result is not None
    assert result.id == resolution_id
    assert result.action == "Attack"
    assert result.success_level == SuccessLevel.SUCCESS
    mock_resolutions.find_one.assert_called_once_with(
        {"resolution_id": str(resolution_id)}
    )


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_resolution_not_found(mock_get_mongodb: Mock):
    """Test getting non-existent resolution."""
    resolution_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions
    mock_resolutions.find_one.return_value = None

    result = mongodb_get_resolution(resolution_id)

    assert result is None


# =============================================================================
# TEST: mongodb_list_resolutions
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_resolutions_all(mock_get_mongodb: Mock):
    """Test listing all resolutions."""
    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    # Mock count and find
    mock_resolutions.count_documents.return_value = 2
    mock_cursor = MagicMock()
    mock_resolutions.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "resolution_id": str(uuid4()),
            "turn_id": str(uuid4()),
            "scene_id": str(uuid4()),
            "story_id": str(uuid4()),
            "actor_id": str(uuid4()),
            "action": "Action 1",
            "action_type": "combat",
            "resolution_type": "dice",
            "mechanics": {"formula": "1d20", "modifiers": []},
            "success_level": "success",
            "margin": None,
            "effects": [],
            "created_at": datetime.now(timezone.utc),
        },
        {
            "resolution_id": str(uuid4()),
            "turn_id": str(uuid4()),
            "scene_id": str(uuid4()),
            "story_id": str(uuid4()),
            "actor_id": str(uuid4()),
            "action": "Action 2",
            "action_type": "skill",
            "resolution_type": "dice",
            "mechanics": {"formula": "1d20", "modifiers": []},
            "success_level": "failure",
            "margin": None,
            "effects": [],
            "created_at": datetime.now(timezone.utc),
        },
    ]

    params = ResolutionFilter()
    result = mongodb_list_resolutions(params)

    assert len(result.resolutions) == 2
    assert result.total == 2
    mock_resolutions.count_documents.assert_called_once_with({})


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_resolutions_by_scene(mock_get_mongodb: Mock):
    """Test listing resolutions filtered by scene_id."""
    scene_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    mock_resolutions.count_documents.return_value = 1
    mock_cursor = MagicMock()
    mock_resolutions.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "resolution_id": str(uuid4()),
            "turn_id": str(uuid4()),
            "scene_id": str(scene_id),
            "story_id": str(uuid4()),
            "actor_id": str(uuid4()),
            "action": "Scene action",
            "action_type": "combat",
            "resolution_type": "dice",
            "mechanics": {"formula": "1d20", "modifiers": []},
            "success_level": "success",
            "margin": None,
            "effects": [],
            "created_at": datetime.now(timezone.utc),
        }
    ]

    params = ResolutionFilter(scene_id=scene_id)
    result = mongodb_list_resolutions(params)

    assert len(result.resolutions) == 1
    assert result.resolutions[0].scene_id == scene_id
    mock_resolutions.count_documents.assert_called_once_with(
        {"scene_id": str(scene_id)}
    )


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_resolutions_by_turn(mock_get_mongodb: Mock):
    """Test listing resolutions filtered by turn_id."""
    turn_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    mock_resolutions.count_documents.return_value = 1
    mock_cursor = MagicMock()
    mock_resolutions.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = []

    params = ResolutionFilter(turn_id=turn_id)
    mongodb_list_resolutions(params)

    mock_resolutions.count_documents.assert_called_once_with({"turn_id": str(turn_id)})


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_resolutions_by_actor(mock_get_mongodb: Mock):
    """Test listing resolutions filtered by actor_id."""
    actor_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    mock_resolutions.count_documents.return_value = 0
    mock_cursor = MagicMock()
    mock_resolutions.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = []

    params = ResolutionFilter(actor_id=actor_id)
    mongodb_list_resolutions(params)

    mock_resolutions.count_documents.assert_called_once_with(
        {"actor_id": str(actor_id)}
    )


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_resolutions_by_action_type(mock_get_mongodb: Mock):
    """Test listing resolutions filtered by action_type."""
    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    mock_resolutions.count_documents.return_value = 0
    mock_cursor = MagicMock()
    mock_resolutions.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = []

    params = ResolutionFilter(action_type=ActionType.COMBAT)
    mongodb_list_resolutions(params)

    mock_resolutions.count_documents.assert_called_once_with({"action_type": "combat"})


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_resolutions_by_success_level(mock_get_mongodb: Mock):
    """Test listing resolutions filtered by success_level."""
    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    mock_resolutions.count_documents.return_value = 0
    mock_cursor = MagicMock()
    mock_resolutions.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = []

    params = ResolutionFilter(success_level=SuccessLevel.CRITICAL_SUCCESS)
    mongodb_list_resolutions(params)

    mock_resolutions.count_documents.assert_called_once_with(
        {"success_level": "critical_success"}
    )


# =============================================================================
# TEST: mongodb_update_resolution
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_resolution_success(mock_get_mongodb: Mock):
    """Test updating a resolution."""
    resolution_id = uuid4()
    target_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    # Mock update result
    mock_result = MagicMock()
    mock_result.matched_count = 1
    mock_resolutions.update_one.return_value = mock_result

    # Mock get after update
    updated_doc = {
        "resolution_id": str(resolution_id),
        "turn_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "actor_id": str(uuid4()),
        "action": "Attack",
        "action_type": "combat",
        "resolution_type": "dice",
        "mechanics": {"formula": "1d20", "modifiers": []},
        "success_level": "success",
        "margin": None,
        "effects": [
            {
                "effect_type": "damage",
                "target_id": str(target_id),
                "magnitude": 15,
                "description": "Updated damage",
            }
        ],
        "description": "Updated description",
        "gm_notes": "Secret notes",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    mock_resolutions.find_one.return_value = updated_doc

    # Update with new effects
    new_effects = [
        Effect(
            effect_type=EffectType.DAMAGE,
            target_id=target_id,
            magnitude=15,
            description="Updated damage",
        )
    ]

    params = ResolutionUpdate(
        effects=new_effects,
        description="Updated description",
        gm_notes="Secret notes",
    )

    result = mongodb_update_resolution(resolution_id, params)

    assert result.id == resolution_id
    assert len(result.effects) == 1
    assert result.effects[0].magnitude == 15
    assert result.description == "Updated description"
    assert result.gm_notes == "Secret notes"
    mock_resolutions.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_resolution_not_found(mock_get_mongodb: Mock):
    """Test updating non-existent resolution."""
    resolution_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    mock_result = MagicMock()
    mock_result.matched_count = 0
    mock_resolutions.update_one.return_value = mock_result

    params = ResolutionUpdate(description="New description")

    with pytest.raises(ValueError, match=f"Resolution {resolution_id} not found"):
        mongodb_update_resolution(resolution_id, params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_resolution_no_changes(mock_get_mongodb: Mock):
    """Test updating resolution with no changes."""
    resolution_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    # Mock current state
    current_doc = {
        "resolution_id": str(resolution_id),
        "turn_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "actor_id": str(uuid4()),
        "action": "Attack",
        "action_type": "combat",
        "resolution_type": "dice",
        "mechanics": {"formula": "1d20", "modifiers": []},
        "success_level": "success",
        "margin": None,
        "effects": [],
        "description": None,
        "gm_notes": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": None,
    }
    mock_resolutions.find_one.return_value = current_doc

    params = ResolutionUpdate()  # No updates
    result = mongodb_update_resolution(resolution_id, params)

    assert result.id == resolution_id
    # Should not call update_one when no changes
    mock_resolutions.update_one.assert_not_called()


# =============================================================================
# TEST: mongodb_delete_resolution
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_resolution_success(mock_get_mongodb: Mock):
    """Test deleting a resolution."""
    resolution_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    mock_result = MagicMock()
    mock_result.deleted_count = 1
    mock_resolutions.delete_one.return_value = mock_result

    result = mongodb_delete_resolution(resolution_id)

    assert result is True
    mock_resolutions.delete_one.assert_called_once_with(
        {"resolution_id": str(resolution_id)}
    )


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_resolution_not_found(mock_get_mongodb: Mock):
    """Test deleting non-existent resolution."""
    resolution_id = uuid4()

    mock_mongodb = MagicMock()
    mock_resolutions = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_resolutions

    mock_result = MagicMock()
    mock_result.deleted_count = 0
    mock_resolutions.delete_one.return_value = mock_result

    result = mongodb_delete_resolution(resolution_id)

    assert result is False

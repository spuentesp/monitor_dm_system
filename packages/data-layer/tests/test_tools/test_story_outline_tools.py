"""
Unit tests for MongoDB story outline operations (DL-6).

Tests cover:
- mongodb_create_story_outline
- mongodb_get_story_outline
- mongodb_update_story_outline
"""

from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID, uuid4
from datetime import datetime

import pytest

from monitor_data.schemas.story_outlines import (
    StoryOutlineCreate,
    StoryOutlineUpdate,
    StoryBeat,
    MysteryStructure,
    MysteryClue,
)
from monitor_data.schemas.base import (
    StoryStructureType,
    ArcTemplate,
    BeatStatus,
    ClueVisibility,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_story_outline,
    mongodb_get_story_outline,
    mongodb_update_story_outline,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def story_beat_data() -> Dict[str, Any]:
    """Provide sample story beat data."""
    beat_id = uuid4()
    return {
        "beat_id": str(beat_id),
        "title": "Opening Scene",
        "description": "Introduce the heroes in the tavern",
        "order": 0,
        "status": BeatStatus.PENDING.value,
        "optional": False,
        "related_threads": [],
        "required_for_threads": [],
        "created_at": datetime.utcnow(),
        "started_at": None,
        "completed_at": None,
        "completed_in_scene_id": None,
    }


@pytest.fixture
def mystery_clue_data() -> Dict[str, Any]:
    """Provide sample mystery clue data."""
    return {
        "clue_id": str(uuid4()),
        "content": "A bloody dagger was found at the scene",
        "discovery_methods": ["search", "investigation"],
        "is_discovered": False,
        "discovered_in_scene_id": None,
        "discovered_at": None,
        "points_to": "butler",
        "visibility": ClueVisibility.HIDDEN.value,
    }


@pytest.fixture
def story_outline_data(
    story_data: Dict[str, Any], story_beat_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Provide sample story outline data."""
    return {
        "story_id": story_data["id"],
        "theme": "Mystery in the manor",
        "premise": "A murder has occurred and players must solve it",
        "constraints": ["No time travel", "No resurrections"],
        "beats": [story_beat_data],
        "structure_type": StoryStructureType.LINEAR.value,
        "template": ArcTemplate.MYSTERY.value,
        "branching_points": [],
        "mystery_structure": None,
        "pacing_metrics": {
            "current_act": 1,
            "tension_level": 0.0,
            "scenes_since_major_event": 0,
            "scenes_in_current_act": 0,
            "estimated_completion": 0.0,
            "last_updated": datetime.utcnow(),
        },
        "open_threads": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


# =============================================================================
# TESTS: mongodb_create_story_outline
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_story_outline_success(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test successful story outline creation."""
    # Setup Neo4j mock
    mock_get_neo4j.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": story_data["id"]}]

    # Setup MongoDB mock
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_collection.find_one.return_value = None  # No existing outline
    mock_collection.insert_one.return_value = Mock()

    # Create test beat
    beat = StoryBeat(
        title="Opening Scene",
        description="Introduce the heroes",
        order=0,
    )

    params = StoryOutlineCreate(
        story_id=UUID(story_data["id"]),
        theme="Adventure and mystery",
        premise="Heroes embark on a quest",
        beats=[beat],
        structure_type=StoryStructureType.LINEAR,
        template=ArcTemplate.THREE_ACT,
    )

    result = mongodb_create_story_outline(params)

    assert result.story_id == UUID(story_data["id"])
    assert result.theme == "Adventure and mystery"
    assert result.premise == "Heroes embark on a quest"
    assert len(result.beats) == 1
    assert result.beats[0].title == "Opening Scene"
    assert result.structure_type == StoryStructureType.LINEAR
    assert result.template == ArcTemplate.THREE_ACT

    # Verify Neo4j was called to verify story exists
    mock_neo4j_client.execute_read.assert_called_once()

    # Verify MongoDB insert was called
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_story_outline_story_not_found(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_neo4j_client: Mock,
):
    """Test story outline creation fails when story doesn't exist."""
    # Setup Neo4j mock - story not found
    mock_get_neo4j.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = StoryOutlineCreate(
        story_id=uuid4(),
        theme="Test theme",
        premise="Test premise",
    )

    with pytest.raises(ValueError, match="not found"):
        mongodb_create_story_outline(params)


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_story_outline_already_exists(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
    story_outline_data: Dict[str, Any],
):
    """Test story outline creation fails when outline already exists."""
    # Setup Neo4j mock
    mock_get_neo4j.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": story_data["id"]}]

    # Setup MongoDB mock - outline exists
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_collection.find_one.return_value = story_outline_data  # Existing outline

    params = StoryOutlineCreate(
        story_id=UUID(story_data["id"]),
    )

    with pytest.raises(ValueError, match="already exists"):
        mongodb_create_story_outline(params)


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_story_outline_with_mystery(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test creating story outline with mystery structure."""
    # Setup mocks
    mock_get_neo4j.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": story_data["id"]}]

    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_collection.find_one.return_value = None
    mock_collection.insert_one.return_value = Mock()

    # Create mystery structure
    mystery = MysteryStructure(
        truth="The butler did it with a candlestick",
        question="Who killed Lord Blackwood?",
        core_clues=[
            MysteryClue(
                content="A bloody dagger",
                discovery_methods=["search"],
            )
        ],
    )

    params = StoryOutlineCreate(
        story_id=UUID(story_data["id"]),
        theme="Mystery",
        premise="Murder mystery",
        mystery_structure=mystery,
    )

    result = mongodb_create_story_outline(params)

    assert result.mystery_structure is not None
    assert result.mystery_structure.truth == "The butler did it with a candlestick"
    assert result.mystery_structure.question == "Who killed Lord Blackwood?"
    assert len(result.mystery_structure.core_clues) == 1


# =============================================================================
# TESTS: mongodb_get_story_outline
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_story_outline_success(
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    story_outline_data: Dict[str, Any],
):
    """Test successful story outline retrieval."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_collection.find_one.return_value = story_outline_data

    result = mongodb_get_story_outline(UUID(story_data["id"]))

    assert result is not None
    assert result.story_id == UUID(story_data["id"])
    assert result.theme == "Mystery in the manor"
    assert len(result.beats) == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_story_outline_not_found(mock_get_mongo: Mock):
    """Test story outline retrieval when outline doesn't exist."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_collection.find_one.return_value = None

    result = mongodb_get_story_outline(uuid4())

    assert result is None


# =============================================================================
# TESTS: mongodb_update_story_outline
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_story_outline_theme_and_premise(
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    story_outline_data: Dict[str, Any],
):
    """Test updating story outline theme and premise."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection

    # First call returns existing doc, second call returns updated doc
    updated_data = story_outline_data.copy()
    updated_data["theme"] = "Updated theme"
    updated_data["premise"] = "Updated premise"
    mock_collection.find_one.side_effect = [story_outline_data, updated_data]
    mock_collection.update_one.return_value = Mock()

    params = StoryOutlineUpdate(
        theme="Updated theme",
        premise="Updated premise",
    )

    result = mongodb_update_story_outline(UUID(story_data["id"]), params)

    assert result.theme == "Updated theme"
    assert result.premise == "Updated premise"

    # Verify update was called
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_story_outline_add_beats(
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    story_outline_data: Dict[str, Any],
):
    """Test adding beats to story outline."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection

    # Create updated data with new beat
    new_beat = StoryBeat(
        title="Second Beat",
        description="New story beat",
        order=1,
    )
    updated_data = story_outline_data.copy()
    updated_data["beats"].append(new_beat.model_dump(mode="json"))

    mock_collection.find_one.side_effect = [story_outline_data, updated_data]
    mock_collection.update_one.return_value = Mock()

    params = StoryOutlineUpdate(
        add_beats=[new_beat],
    )

    result = mongodb_update_story_outline(UUID(story_data["id"]), params)

    assert len(result.beats) == 2
    assert result.beats[1].title == "Second Beat"


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_story_outline_remove_beats(
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    story_outline_data: Dict[str, Any],
):
    """Test removing beats from story outline."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection

    # Setup data with multiple beats
    beat1_id = uuid4()
    beat2_id = uuid4()
    multi_beat_data = story_outline_data.copy()
    multi_beat_data["beats"] = [
        {
            "beat_id": str(beat1_id),
            "title": "Beat 1",
            "description": "First beat",
            "order": 0,
            "status": BeatStatus.PENDING.value,
            "optional": False,
            "related_threads": [],
            "required_for_threads": [],
            "created_at": datetime.utcnow(),
        },
        {
            "beat_id": str(beat2_id),
            "title": "Beat 2",
            "description": "Second beat",
            "order": 1,
            "status": BeatStatus.PENDING.value,
            "optional": False,
            "related_threads": [],
            "required_for_threads": [],
            "created_at": datetime.utcnow(),
        },
    ]

    updated_data = multi_beat_data.copy()
    updated_data["beats"] = [multi_beat_data["beats"][0]]  # Only first beat remains

    mock_collection.find_one.side_effect = [multi_beat_data, updated_data]
    mock_collection.update_one.return_value = Mock()

    params = StoryOutlineUpdate(
        remove_beat_ids=[beat2_id],
    )

    result = mongodb_update_story_outline(UUID(story_data["id"]), params)

    assert len(result.beats) == 1
    assert result.beats[0].beat_id == beat1_id


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_story_outline_reorder_beats(
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    story_outline_data: Dict[str, Any],
):
    """Test reordering beats in story outline."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection

    beat1_id = uuid4()
    beat2_id = uuid4()
    multi_beat_data = story_outline_data.copy()
    multi_beat_data["beats"] = [
        {
            "beat_id": str(beat1_id),
            "title": "Beat 1",
            "description": "First beat",
            "order": 0,
            "status": BeatStatus.PENDING.value,
            "optional": False,
            "related_threads": [],
            "required_for_threads": [],
            "created_at": datetime.utcnow(),
        },
        {
            "beat_id": str(beat2_id),
            "title": "Beat 2",
            "description": "Second beat",
            "order": 1,
            "status": BeatStatus.PENDING.value,
            "optional": False,
            "related_threads": [],
            "required_for_threads": [],
            "created_at": datetime.utcnow(),
        },
    ]

    # Reordered: beat2 comes before beat1
    updated_data = multi_beat_data.copy()
    updated_data["beats"] = [multi_beat_data["beats"][1], multi_beat_data["beats"][0]]
    updated_data["beats"][0]["order"] = 0
    updated_data["beats"][1]["order"] = 1

    mock_collection.find_one.side_effect = [multi_beat_data, updated_data]
    mock_collection.update_one.return_value = Mock()

    params = StoryOutlineUpdate(
        reorder_beats=[beat2_id, beat1_id],
    )

    result = mongodb_update_story_outline(UUID(story_data["id"]), params)

    assert result.beats[0].beat_id == beat2_id
    assert result.beats[0].order == 0
    assert result.beats[1].beat_id == beat1_id
    assert result.beats[1].order == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_story_outline_update_beats(
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    story_outline_data: Dict[str, Any],
):
    """Test updating existing beats in story outline."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection

    beat_id = UUID(story_outline_data["beats"][0]["beat_id"])

    updated_data = story_outline_data.copy()
    updated_data["beats"][0]["status"] = BeatStatus.COMPLETED.value
    updated_data["beats"][0]["completed_at"] = datetime.utcnow()

    mock_collection.find_one.side_effect = [story_outline_data, updated_data]
    mock_collection.update_one.return_value = Mock()

    # Update the beat status
    updated_beat = StoryBeat(
        beat_id=beat_id,
        title="Opening Scene",
        description="Introduce the heroes in the tavern",
        order=0,
        status=BeatStatus.COMPLETED,
        completed_at=datetime.utcnow(),
    )

    params = StoryOutlineUpdate(
        update_beats=[updated_beat],
    )

    result = mongodb_update_story_outline(UUID(story_data["id"]), params)

    assert result.beats[0].status == BeatStatus.COMPLETED
    assert result.beats[0].completed_at is not None


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_story_outline_not_found(mock_get_mongo: Mock):
    """Test updating non-existent story outline."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_collection.find_one.return_value = None

    params = StoryOutlineUpdate(theme="New theme")

    with pytest.raises(ValueError, match="not found"):
        mongodb_update_story_outline(uuid4(), params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_story_outline_mark_clue_discovered(
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    story_outline_data: Dict[str, Any],
    mystery_clue_data: Dict[str, Any],
):
    """Test marking a clue as discovered in mystery structure."""
    mock_mongo_client = MagicMock()
    mock_collection = MagicMock()
    mock_get_mongo.return_value = mock_mongo_client
    mock_mongo_client.get_collection.return_value = mock_collection

    # Add mystery structure to outline
    outline_with_mystery = story_outline_data.copy()
    outline_with_mystery["mystery_structure"] = {
        "truth": "The butler did it",
        "question": "Who killed Lord Blackwood?",
        "core_clues": [mystery_clue_data],
        "bonus_clues": [],
        "red_herrings": [],
        "suspects": [],
        "current_player_theories": [],
    }

    # Updated with discovered clue
    updated_data = outline_with_mystery.copy()
    updated_data["mystery_structure"]["core_clues"][0]["is_discovered"] = True
    updated_data["mystery_structure"]["core_clues"][0][
        "visibility"
    ] = ClueVisibility.DISCOVERED.value

    mock_collection.find_one.side_effect = [outline_with_mystery, updated_data]
    mock_collection.update_one.return_value = Mock()

    clue_id = UUID(mystery_clue_data["clue_id"])
    params = StoryOutlineUpdate(
        mark_clue_discovered=clue_id,
    )

    result = mongodb_update_story_outline(UUID(story_data["id"]), params)

    assert result.mystery_structure is not None
    assert result.mystery_structure.core_clues[0].is_discovered is True
    assert (
        result.mystery_structure.core_clues[0].visibility == ClueVisibility.DISCOVERED
    )

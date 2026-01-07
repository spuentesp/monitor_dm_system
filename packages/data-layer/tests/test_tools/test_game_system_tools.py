"""
Tests for Game Systems MongoDB tools (DL-20).

Tests all game system and rule override CRUD operations including
built-in system seeding, custom system management, and rule overrides.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch, mock_open
from uuid import uuid4

import pytest

from monitor_data.schemas.game_systems import (
    GameSystemCreate,
    GameSystemUpdate,
    RuleOverrideCreate,
    RuleOverrideUpdate,
    CoreMechanicType,
    SuccessType,
    RuleOverrideScope,
    CoreMechanic,
    AttributeDefinition,
    SkillDefinition,
    ResourceDefinition,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_game_system,
    mongodb_get_game_system,
    mongodb_list_game_systems,
    mongodb_update_game_system,
    mongodb_delete_game_system,
    mongodb_create_rule_override,
    mongodb_get_rule_override,
    mongodb_list_rule_overrides,
    mongodb_update_rule_override,
    mongodb_delete_rule_override,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_core_mechanic():
    """Sample core mechanic for testing."""
    return CoreMechanic(
        type=CoreMechanicType.D20,
        formula="1d20 + modifier vs DC",
        success_type=SuccessType.MEET_OR_BEAT,
        success_threshold="Meet or beat DC",
        critical_success="Natural 20",
        critical_failure="Natural 1",
    )


@pytest.fixture
def sample_attributes():
    """Sample attributes for testing."""
    return [
        AttributeDefinition(
            name="Strength",
            abbreviation="STR",
            min_value=1,
            max_value=20,
            default_value=10,
            modifier_formula="(VALUE - 10) / 2",
        ),
        AttributeDefinition(
            name="Dexterity",
            abbreviation="DEX",
            min_value=1,
            max_value=20,
            default_value=10,
            modifier_formula="(VALUE - 10) / 2",
        ),
    ]


@pytest.fixture
def sample_skills():
    """Sample skills for testing."""
    return [
        SkillDefinition(
            name="Athletics",
            abbreviation="Ath",
            linked_attribute="Strength",
            description="Physical prowess",
        ),
        SkillDefinition(
            name="Stealth",
            abbreviation="Ste",
            linked_attribute="Dexterity",
            description="Moving silently",
        ),
    ]


@pytest.fixture
def sample_resources():
    """Sample resources for testing."""
    return [
        ResourceDefinition(
            name="Hit Points",
            abbreviation="HP",
            calculation="class_hit_die + CON",
            min_value=0,
            recovers_on="long rest",
        ),
    ]


# =============================================================================
# TEST: mongodb_create_game_system
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_game_system_success(
    mock_get_mongodb: Mock,
    sample_core_mechanic,
    sample_attributes,
    sample_skills,
    sample_resources,
):
    """Test creating a custom game system."""
    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Create system
    create_params = GameSystemCreate(
        name="My Custom System",
        description="A homebrew RPG system",
        version="1.0",
        core_mechanic=sample_core_mechanic,
        attributes=sample_attributes,
        skills=sample_skills,
        resources=sample_resources,
        custom_dice={},
        is_builtin=False,
    )

    result = mongodb_create_game_system(create_params)

    # Verify insert was called
    assert mock_systems.insert_one.called
    inserted_doc = mock_systems.insert_one.call_args[0][0]

    # Verify document structure
    assert inserted_doc["name"] == "My Custom System"
    assert inserted_doc["description"] == "A homebrew RPG system"
    assert inserted_doc["version"] == "1.0"
    assert inserted_doc["is_builtin"] is False
    assert "system_id" in inserted_doc
    assert "created_at" in inserted_doc

    # Verify response
    assert result.name == "My Custom System"
    assert result.is_builtin is False
    assert len(result.attributes) == 2
    assert len(result.skills) == 2
    assert len(result.resources) == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_game_system_builtin_rejected(
    mock_get_mongodb: Mock,
    sample_core_mechanic,
):
    """Test that manually creating builtin systems is rejected."""
    create_params = GameSystemCreate(
        name="Fake Builtin",
        description="Should not work",
        core_mechanic=sample_core_mechanic,
        attributes=[],
        is_builtin=True,  # This should cause rejection
    )

    with pytest.raises(ValueError, match="Cannot manually create builtin systems"):
        mongodb_create_game_system(create_params)


# =============================================================================
# TEST: mongodb_get_game_system
# =============================================================================


@patch("monitor_data.tools.mongodb_tools._ensure_builtin_systems_seeded")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_game_system_found(
    mock_get_mongodb: Mock,
    mock_ensure_seeded: Mock,
):
    """Test retrieving a game system."""
    system_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Mock system document
    mock_systems.find_one.return_value = {
        "system_id": str(system_id),
        "name": "Test System",
        "description": "A test system",
        "version": "1.0",
        "core_mechanic": {
            "type": "d20",
            "formula": "1d20",
            "success_type": "meet_or_beat",
        },
        "attributes": [],
        "skills": [],
        "resources": [],
        "custom_dice": {},
        "is_builtin": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": None,
    }

    result = mongodb_get_game_system(system_id)

    # Verify seeding was checked
    assert mock_ensure_seeded.called

    # Verify result
    assert result is not None
    assert result.name == "Test System"
    assert result.id == system_id


@patch("monitor_data.tools.mongodb_tools._ensure_builtin_systems_seeded")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_game_system_not_found(
    mock_get_mongodb: Mock,
    mock_ensure_seeded: Mock,
):
    """Test retrieving a non-existent game system."""
    system_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems
    mock_systems.find_one.return_value = None

    result = mongodb_get_game_system(system_id)

    assert result is None


# =============================================================================
# TEST: mongodb_list_game_systems
# =============================================================================


@patch("monitor_data.tools.mongodb_tools._ensure_builtin_systems_seeded")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_game_systems_includes_builtin(
    mock_get_mongodb: Mock,
    mock_ensure_seeded: Mock,
):
    """Test listing game systems includes builtin systems."""
    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Mock cursor with 2 systems
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(
        [
            {
                "system_id": str(uuid4()),
                "name": "D&D 5e",
                "description": "Fifth Edition",
                "version": "5e",
                "core_mechanic": {
                    "type": "d20",
                    "formula": "1d20",
                    "success_type": "meet_or_beat",
                },
                "attributes": [],
                "skills": [],
                "resources": [],
                "custom_dice": {},
                "is_builtin": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": None,
            },
            {
                "system_id": str(uuid4()),
                "name": "Custom System",
                "description": "Homebrew",
                "version": "1.0",
                "core_mechanic": {
                    "type": "dice_pool",
                    "formula": "3d6",
                    "success_type": "count_successes",
                },
                "attributes": [],
                "skills": [],
                "resources": [],
                "custom_dice": {},
                "is_builtin": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": None,
            },
        ]
    )

    mock_systems.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_systems.count_documents.return_value = 2

    result = mongodb_list_game_systems(include_builtin=True, limit=50, offset=0)

    # Verify seeding was checked
    assert mock_ensure_seeded.called

    # Verify results
    assert len(result.systems) == 2
    assert result.total == 2
    assert result.systems[0].name == "D&D 5e"
    assert result.systems[0].is_builtin is True
    assert result.systems[1].name == "Custom System"
    assert result.systems[1].is_builtin is False


@patch("monitor_data.tools.mongodb_tools._ensure_builtin_systems_seeded")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_game_systems_exclude_builtin(
    mock_get_mongodb: Mock,
    mock_ensure_seeded: Mock,
):
    """Test listing game systems excluding builtin."""
    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Mock cursor with only custom system
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(
        [
            {
                "system_id": str(uuid4()),
                "name": "Custom System",
                "description": "Homebrew",
                "version": "1.0",
                "core_mechanic": {
                    "type": "dice_pool",
                    "formula": "3d6",
                    "success_type": "count_successes",
                },
                "attributes": [],
                "skills": [],
                "resources": [],
                "custom_dice": {},
                "is_builtin": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": None,
            },
        ]
    )

    mock_systems.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_systems.count_documents.return_value = 1

    result = mongodb_list_game_systems(include_builtin=False, limit=50, offset=0)

    # Verify query excluded builtin
    called_query = mock_systems.find.call_args[0][0]
    assert "is_builtin" in called_query
    assert called_query["is_builtin"] is False

    # Verify results
    assert len(result.systems) == 1
    assert result.systems[0].is_builtin is False


# =============================================================================
# TEST: mongodb_update_game_system
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.mongodb_get_game_system")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_game_system_success(
    mock_get_mongodb: Mock,
    mock_get_system: Mock,
    sample_core_mechanic,
):
    """Test updating a custom game system."""
    system_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Mock existing system (not builtin)
    mock_systems.find_one.return_value = {
        "system_id": str(system_id),
        "is_builtin": False,
    }

    # Mock the get after update
    mock_result = MagicMock()
    mock_result.id = system_id
    mock_result.name = "Updated System"
    mock_result.is_builtin = False
    mock_get_system.return_value = mock_result

    # Update
    update_params = GameSystemUpdate(
        name="Updated System",
        description="Updated description",
    )

    result = mongodb_update_game_system(system_id, update_params)

    # Verify update was called
    assert mock_systems.update_one.called
    update_call = mock_systems.update_one.call_args[0]
    assert update_call[0] == {"system_id": str(system_id)}
    assert "name" in update_call[1]["$set"]
    assert update_call[1]["$set"]["name"] == "Updated System"

    # Verify result
    assert result.name == "Updated System"


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_builtin_system_rejected(mock_get_mongodb: Mock):
    """Test that updating builtin systems is rejected."""
    system_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Mock builtin system
    mock_systems.find_one.return_value = {
        "system_id": str(system_id),
        "is_builtin": True,
    }

    update_params = GameSystemUpdate(name="Hacked D&D")

    with pytest.raises(ValueError, match="Cannot modify builtin game systems"):
        mongodb_update_game_system(system_id, update_params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_nonexistent_system(mock_get_mongodb: Mock):
    """Test updating a non-existent system."""
    system_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems
    mock_systems.find_one.return_value = None

    update_params = GameSystemUpdate(name="Doesn't Matter")

    with pytest.raises(ValueError, match="not found"):
        mongodb_update_game_system(system_id, update_params)


# =============================================================================
# TEST: mongodb_delete_game_system
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_custom_system_success(mock_get_mongodb: Mock):
    """Test deleting a custom game system."""
    system_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Mock custom system
    mock_systems.find_one.return_value = {
        "system_id": str(system_id),
        "is_builtin": False,
    }

    mongodb_delete_game_system(system_id)

    # Verify delete was called
    assert mock_systems.delete_one.called
    delete_call = mock_systems.delete_one.call_args[0][0]
    assert delete_call == {"system_id": str(system_id)}


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_builtin_system_rejected(mock_get_mongodb: Mock):
    """Test that deleting builtin systems is rejected."""
    system_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Mock builtin system
    mock_systems.find_one.return_value = {
        "system_id": str(system_id),
        "is_builtin": True,
    }

    with pytest.raises(ValueError, match="Cannot delete builtin game systems"):
        mongodb_delete_game_system(system_id)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_nonexistent_system(mock_get_mongodb: Mock):
    """Test deleting a non-existent system."""
    system_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems
    mock_systems.find_one.return_value = None

    with pytest.raises(ValueError, match="not found"):
        mongodb_delete_game_system(system_id)


# =============================================================================
# TEST: mongodb_create_rule_override
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_rule_override_success(mock_get_mongodb: Mock):
    """Test creating a rule override."""
    scope_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides

    # Create override
    create_params = RuleOverrideCreate(
        scope=RuleOverrideScope.STORY,
        scope_id=scope_id,
        target="flanking",
        original="Flanking grants advantage",
        override="Flanking grants +2 bonus instead of advantage",
        reason="Table preference for numerical bonuses",
    )

    result = mongodb_create_rule_override(create_params)

    # Verify insert was called
    assert mock_overrides.insert_one.called
    inserted_doc = mock_overrides.insert_one.call_args[0][0]

    # Verify document structure
    assert inserted_doc["scope"] == "story"
    assert inserted_doc["scope_id"] == str(scope_id)
    assert inserted_doc["target"] == "flanking"
    assert inserted_doc["active"] is True
    assert inserted_doc["times_used"] == 0

    # Verify response
    assert result.scope == RuleOverrideScope.STORY
    assert result.target == "flanking"
    assert result.active is True


# =============================================================================
# TEST: mongodb_get_rule_override
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_rule_override_found(mock_get_mongodb: Mock):
    """Test retrieving a rule override."""
    override_id = uuid4()
    scope_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides

    # Mock override document
    mock_overrides.find_one.return_value = {
        "override_id": str(override_id),
        "scope": "scene",
        "scope_id": str(scope_id),
        "target": "critical_hits",
        "original": "Crit on 20",
        "override": "Crit on 19-20",
        "reason": "Champion fighter",
        "times_used": 3,
        "active": True,
        "created_at": datetime.now(timezone.utc),
    }

    result = mongodb_get_rule_override(override_id)

    # Verify result
    assert result is not None
    assert result.id == override_id
    assert result.scope == RuleOverrideScope.SCENE
    assert result.times_used == 3


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_rule_override_not_found(mock_get_mongodb: Mock):
    """Test retrieving a non-existent rule override."""
    override_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides
    mock_overrides.find_one.return_value = None

    result = mongodb_get_rule_override(override_id)

    assert result is None


# =============================================================================
# TEST: mongodb_list_rule_overrides
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_rule_overrides_by_scope(mock_get_mongodb: Mock):
    """Test listing rule overrides filtered by scope."""
    story_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides

    # Mock cursor with 2 overrides
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(
        [
            {
                "override_id": str(uuid4()),
                "scope": "story",
                "scope_id": str(story_id),
                "target": "flanking",
                "original": "Advantage",
                "override": "+2",
                "reason": "Preference",
                "times_used": 0,
                "active": True,
                "created_at": datetime.now(timezone.utc),
            },
            {
                "override_id": str(uuid4()),
                "scope": "story",
                "scope_id": str(story_id),
                "target": "crits",
                "original": "Double dice",
                "override": "Max + roll",
                "reason": "Feels better",
                "times_used": 2,
                "active": True,
                "created_at": datetime.now(timezone.utc),
            },
        ]
    )

    mock_overrides.find.return_value.sort.return_value = mock_cursor
    mock_overrides.count_documents.return_value = 2

    result = mongodb_list_rule_overrides(
        scope="story", scope_id=story_id, active_only=True
    )

    # Verify query
    called_query = mock_overrides.find.call_args[0][0]
    assert called_query["scope"] == "story"
    assert called_query["scope_id"] == str(story_id)
    assert called_query["active"] is True

    # Verify results
    assert len(result.overrides) == 2
    assert result.total == 2


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_rule_overrides_active_only(mock_get_mongodb: Mock):
    """Test listing only active rule overrides."""
    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides

    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter([])
    mock_overrides.find.return_value.sort.return_value = mock_cursor
    mock_overrides.count_documents.return_value = 0

    mongodb_list_rule_overrides(active_only=True)

    # Verify query included active filter
    called_query = mock_overrides.find.call_args[0][0]
    assert called_query["active"] is True


# =============================================================================
# TEST: mongodb_update_rule_override
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.mongodb_get_rule_override")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_rule_override_success(
    mock_get_mongodb: Mock,
    mock_get_override: Mock,
):
    """Test updating a rule override."""
    override_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides

    # Mock existing override
    mock_overrides.find_one.return_value = {
        "override_id": str(override_id),
    }

    # Mock the get after update
    mock_result = MagicMock()
    mock_result.id = override_id
    mock_result.times_used = 5
    mock_result.active = True
    mock_get_override.return_value = mock_result

    # Update
    update_params = RuleOverrideUpdate(
        times_used=5,
        active=True,
    )

    result = mongodb_update_rule_override(override_id, update_params)

    # Verify update was called
    assert mock_overrides.update_one.called
    update_call = mock_overrides.update_one.call_args[0]
    assert update_call[0] == {"override_id": str(override_id)}
    assert "times_used" in update_call[1]["$set"]

    # Verify result
    assert result.times_used == 5


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_nonexistent_override(mock_get_mongodb: Mock):
    """Test updating a non-existent override."""
    override_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides
    mock_overrides.find_one.return_value = None

    update_params = RuleOverrideUpdate(active=False)

    with pytest.raises(ValueError, match="not found"):
        mongodb_update_rule_override(override_id, update_params)


# =============================================================================
# TEST: mongodb_delete_rule_override
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_rule_override_success(mock_get_mongodb: Mock):
    """Test deleting a rule override."""
    override_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides

    # Mock existing override
    mock_overrides.find_one.return_value = {
        "override_id": str(override_id),
    }

    mongodb_delete_rule_override(override_id)

    # Verify delete was called
    assert mock_overrides.delete_one.called
    delete_call = mock_overrides.delete_one.call_args[0][0]
    assert delete_call == {"override_id": str(override_id)}


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_nonexistent_override(mock_get_mongodb: Mock):
    """Test deleting a non-existent override."""
    override_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_overrides = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_overrides
    mock_overrides.find_one.return_value = None

    with pytest.raises(ValueError, match="not found"):
        mongodb_delete_rule_override(override_id)


# =============================================================================
# TEST: Built-in Systems Seeding
# =============================================================================


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data='[{"name": "Test System", "is_builtin": true}]',
)
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_builtin_systems_seeded(mock_get_mongodb: Mock, mock_file: Mock):
    """Test that built-in systems are seeded on first access."""
    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # First call: no builtin systems exist
    mock_systems.count_documents.return_value = 0

    # Import and call the seeding function directly
    from monitor_data.tools.mongodb_tools import _ensure_builtin_systems_seeded

    _ensure_builtin_systems_seeded()

    # Verify seed file was loaded and systems upserted (to avoid race conditions)
    assert mock_systems.update_one.called


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data='[{"name": "Test System", "is_builtin": true}]',
)
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_builtin_systems_use_atomic_upsert(mock_get_mongodb: Mock, mock_file: Mock):
    """Test that built-in systems use atomic upsert to prevent duplicates."""
    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_systems = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_systems

    # Import and call the seeding function
    from monitor_data.tools.mongodb_tools import _ensure_builtin_systems_seeded

    _ensure_builtin_systems_seeded()

    # Verify upsert was called with correct parameters
    assert mock_systems.update_one.called
    call_args = mock_systems.update_one.call_args
    # Check that upsert=True was passed
    assert call_args[1]["upsert"] is True
    # Check that $setOnInsert was used (prevents overwriting existing data)
    assert "$setOnInsert" in call_args[0][1]

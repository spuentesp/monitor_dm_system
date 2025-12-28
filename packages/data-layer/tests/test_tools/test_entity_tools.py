"""
Unit tests for Neo4j entity operations (DL-2).

Tests cover:
- neo4j_create_entity (archetype and instance)
- neo4j_get_entity
- neo4j_list_entities
- neo4j_update_entity
- neo4j_delete_entity
- neo4j_set_state_tags
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.entities import (
    EntityCreate,
    EntityUpdate,
    EntityFilter,
    StateTagsUpdate,
)
from monitor_data.schemas.base import CanonLevel, EntityType, Authority
from monitor_data.tools.neo4j_tools import (
    neo4j_create_entity,
    neo4j_get_entity,
    neo4j_list_entities,
    neo4j_update_entity,
    neo4j_delete_entity,
    neo4j_set_state_tags,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def entity_archetype_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample entity archetype data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Wizard",
        "entity_type": "character",
        "is_archetype": True,
        "description": "A practitioner of arcane magic",
        "properties": {
            "archetype": "wizard",
            "default_abilities": ["spellcasting", "ritual magic"],
        },
        "state_tags": [],
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def entity_instance_data(
    universe_data: Dict[str, Any], entity_archetype_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Provide sample entity instance data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Gandalf",
        "entity_type": "character",
        "is_archetype": False,
        "description": "Istari wizard sent to Middle-earth",
        "properties": {
            "role": "NPC",
            "archetype": "wizard",
            "tags": ["wise", "powerful"],
        },
        "state_tags": ["alive", "traveling"],
        "archetype_id": entity_archetype_data["id"],
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": Authority.GM.value,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }


# =============================================================================
# TESTS: neo4j_create_entity - ARCHETYPE
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_archetype(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    entity_archetype_data: Dict[str, Any],
):
    """Test creating an EntityArchetype."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock entity creation
    mock_neo4j_client.execute_write.return_value = [{"e": entity_archetype_data}]

    params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name="Wizard",
        entity_type=EntityType.CHARACTER,
        is_archetype=True,
        description="A practitioner of arcane magic",
        properties={
            "archetype": "wizard",
            "default_abilities": ["spellcasting", "ritual magic"],
        },
    )

    result = neo4j_create_entity(params)

    assert result.name == "Wizard"
    assert result.entity_type == "character"
    assert result.is_archetype is True
    assert result.state_tags == []
    assert result.archetype_id is None
    assert mock_neo4j_client.execute_read.call_count == 1
    assert mock_neo4j_client.execute_write.call_count == 1


# =============================================================================
# TESTS: neo4j_create_entity - INSTANCE
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_instance(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    entity_instance_data: Dict[str, Any],
):
    """Test creating an EntityInstance without archetype."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock entity creation
    instance_without_archetype = entity_instance_data.copy()
    instance_without_archetype["archetype_id"] = None
    mock_neo4j_client.execute_write.return_value = [{"e": instance_without_archetype}]

    params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name="Gandalf",
        entity_type=EntityType.CHARACTER,
        is_archetype=False,
        description="Istari wizard sent to Middle-earth",
        state_tags=["alive", "traveling"],
    )

    result = neo4j_create_entity(params)

    assert result.name == "Gandalf"
    assert result.is_archetype is False
    assert result.state_tags == ["alive", "traveling"]
    assert result.archetype_id is None


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_instance_with_archetype(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    entity_archetype_data: Dict[str, Any],
    entity_instance_data: Dict[str, Any],
):
    """Test creating an EntityInstance with DERIVES_FROM relationship."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists, then archetype exists
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],
        [{"id": entity_archetype_data["id"]}],
    ]

    # Mock entity creation
    mock_neo4j_client.execute_write.return_value = [{"e": entity_instance_data}]

    params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name="Gandalf",
        entity_type=EntityType.CHARACTER,
        is_archetype=False,
        archetype_id=UUID(entity_archetype_data["id"]),
        description="Istari wizard sent to Middle-earth",
        state_tags=["alive", "traveling"],
    )

    result = neo4j_create_entity(params)

    assert result.archetype_id == UUID(entity_archetype_data["id"])
    assert mock_neo4j_client.execute_read.call_count == 2


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_entity_invalid_universe(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test entity creation with invalid universe_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = EntityCreate(
        universe_id=uuid4(),
        name="Test Entity",
        entity_type=EntityType.CHARACTER,
    )

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_create_entity(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_entity_invalid_archetype(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test instance creation with invalid archetype_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists, then archetype doesn't exist
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],
        [],
    ]

    params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name="Test Entity",
        entity_type=EntityType.CHARACTER,
        is_archetype=False,
        archetype_id=uuid4(),
    )

    with pytest.raises(ValueError, match="Archetype .* not found"):
        neo4j_create_entity(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_archetype_with_state_tags_fails(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test that archetypes cannot have state_tags."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name="Wizard",
        entity_type=EntityType.CHARACTER,
        is_archetype=True,
        state_tags=["alive"],  # Should fail
    )

    with pytest.raises(ValueError, match="state_tags cannot be set on EntityArchetype"):
        neo4j_create_entity(params)


# =============================================================================
# TESTS: neo4j_create_entity - ALL ENTITY TYPES
# =============================================================================


@pytest.mark.parametrize(
    "entity_type",
    [
        EntityType.CHARACTER,
        EntityType.FACTION,
        EntityType.LOCATION,
        EntityType.OBJECT,
        EntityType.CONCEPT,
        EntityType.ORGANIZATION,
    ],
)
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_entity_all_types(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    entity_type: EntityType,
):
    """Test creating entities of all supported types."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock entity creation
    entity_data = {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": f"Test {entity_type.value}",
        "entity_type": entity_type.value,
        "is_archetype": True,
        "description": f"A test {entity_type.value}",
        "properties": {},
        "state_tags": [],
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }
    mock_neo4j_client.execute_write.return_value = [{"e": entity_data}]

    params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name=f"Test {entity_type.value}",
        entity_type=entity_type,
        is_archetype=True,
    )

    result = neo4j_create_entity(params)

    assert result.entity_type == entity_type.value
    assert result.name == f"Test {entity_type.value}"


# =============================================================================
# TESTS: neo4j_get_entity
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_entity_exists(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_instance_data: Dict[str, Any],
):
    """Test getting an existing entity."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [
        {"e": entity_instance_data, "archetype_id": entity_instance_data["archetype_id"]}
    ]

    entity_id = UUID(entity_instance_data["id"])
    result = neo4j_get_entity(entity_id)

    assert result is not None
    assert result.id == entity_id
    assert result.name == entity_instance_data["name"]
    assert result.state_tags == entity_instance_data["state_tags"]
    assert result.archetype_id == UUID(entity_instance_data["archetype_id"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_entity_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test getting a non-existent entity."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_entity(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_list_entities
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_entities_by_type(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_archetype_data: Dict[str, Any],
):
    """Test filtering entities by entity_type."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"e": entity_archetype_data, "archetype_id": None}],
    ]

    filters = EntityFilter(entity_type=EntityType.CHARACTER)

    result = neo4j_list_entities(filters)

    assert result.total == 1
    assert len(result.entities) == 1
    assert result.entities[0].entity_type == "character"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_entities_by_tags(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_instance_data: Dict[str, Any],
):
    """Test filtering entities by state_tags."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"e": entity_instance_data, "archetype_id": entity_instance_data["archetype_id"]}],
    ]

    filters = EntityFilter(state_tags=["alive", "traveling"])

    result = neo4j_list_entities(filters)

    assert result.total == 1
    assert len(result.entities) == 1
    assert "alive" in result.entities[0].state_tags
    assert "traveling" in result.entities[0].state_tags


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_entities_pagination(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_archetype_data: Dict[str, Any],
):
    """Test entity list pagination."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 100}],
        [{"e": entity_archetype_data, "archetype_id": None}],
    ]

    filters = EntityFilter(limit=10, offset=20)

    result = neo4j_list_entities(filters)

    assert result.total == 100
    assert result.limit == 10
    assert result.offset == 20


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_entities_by_universe(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    entity_archetype_data: Dict[str, Any],
):
    """Test filtering entities by universe_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"e": entity_archetype_data, "archetype_id": None}],
    ]

    filters = EntityFilter(universe_id=UUID(universe_data["id"]))

    result = neo4j_list_entities(filters)

    assert result.total == 1
    assert result.entities[0].universe_id == UUID(universe_data["id"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_entities_archetype_only(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_archetype_data: Dict[str, Any],
):
    """Test filtering for only archetypes."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"e": entity_archetype_data, "archetype_id": None}],
    ]

    filters = EntityFilter(is_archetype=True)

    result = neo4j_list_entities(filters)

    assert result.total == 1
    assert all(e.is_archetype for e in result.entities)


# =============================================================================
# TESTS: neo4j_update_entity
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_entity(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_instance_data: Dict[str, Any],
):
    """Test updating entity fields."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity exists check
    mock_neo4j_client.execute_read.return_value = [{"id": entity_instance_data["id"]}]

    # Mock update
    updated_data = entity_instance_data.copy()
    updated_data["name"] = "Gandalf the White"
    updated_data["description"] = "Returned and more powerful"
    mock_neo4j_client.execute_write.return_value = [
        {"e": updated_data, "archetype_id": updated_data["archetype_id"]}
    ]

    params = EntityUpdate(
        name="Gandalf the White",
        description="Returned and more powerful",
    )

    result = neo4j_update_entity(UUID(entity_instance_data["id"]), params)

    assert result.name == "Gandalf the White"
    assert result.description == "Returned and more powerful"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_entity_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test updating non-existent entity."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = EntityUpdate(name="New Name")

    with pytest.raises(ValueError, match="Entity .* not found"):
        neo4j_update_entity(uuid4(), params)


# =============================================================================
# TESTS: neo4j_delete_entity
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_entity_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_archetype_data: Dict[str, Any],
):
    """Test deleting an entity with no dependencies."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity exists, no dependencies
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": entity_archetype_data["id"]}],
        [{"dependent_count": 0}],
    ]

    entity_id = UUID(entity_archetype_data["id"])
    result = neo4j_delete_entity(entity_id)

    assert result["deleted"] is True
    assert result["entity_id"] == str(entity_id)
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_entity_with_dependencies(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_instance_data: Dict[str, Any],
):
    """Test deletion fails when entity has dependent facts."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity exists, has dependencies
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": entity_instance_data["id"]}],
        [{"dependent_count": 5}],
    ]

    entity_id = UUID(entity_instance_data["id"])

    with pytest.raises(ValueError, match="has 5 dependent facts/events"):
        neo4j_delete_entity(entity_id, force=False)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_entity_force(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_instance_data: Dict[str, Any],
):
    """Test force deletion ignores dependencies."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity exists
    mock_neo4j_client.execute_read.return_value = [{"id": entity_instance_data["id"]}]

    entity_id = UUID(entity_instance_data["id"])
    result = neo4j_delete_entity(entity_id, force=True)

    assert result["deleted"] is True
    assert result["forced"] is True
    # Should skip dependency check when force=True
    assert mock_neo4j_client.execute_read.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_entity_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test deleting non-existent entity."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Entity .* not found"):
        neo4j_delete_entity(uuid4())


# =============================================================================
# TESTS: neo4j_set_state_tags
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_set_state_tags_add(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_instance_data: Dict[str, Any],
):
    """Test adding state tags."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity exists and is instance
    mock_neo4j_client.execute_read.return_value = [{"is_archetype": False}]

    # Mock update
    updated_data = entity_instance_data.copy()
    updated_data["state_tags"] = ["alive", "traveling", "wounded"]
    mock_neo4j_client.execute_write.return_value = [
        {"e": updated_data, "archetype_id": updated_data["archetype_id"]}
    ]

    params = StateTagsUpdate(add_tags=["wounded"])

    result = neo4j_set_state_tags(UUID(entity_instance_data["id"]), params)

    assert "wounded" in result.state_tags


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_set_state_tags_remove(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_instance_data: Dict[str, Any],
):
    """Test removing state tags."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity exists and is instance
    mock_neo4j_client.execute_read.return_value = [{"is_archetype": False}]

    # Mock update
    updated_data = entity_instance_data.copy()
    updated_data["state_tags"] = ["alive"]  # removed "traveling"
    mock_neo4j_client.execute_write.return_value = [
        {"e": updated_data, "archetype_id": updated_data["archetype_id"]}
    ]

    params = StateTagsUpdate(remove_tags=["traveling"])

    result = neo4j_set_state_tags(UUID(entity_instance_data["id"]), params)

    assert "traveling" not in result.state_tags


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_set_state_tags_add_and_remove(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_instance_data: Dict[str, Any],
):
    """Test adding and removing state tags atomically."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity exists and is instance
    mock_neo4j_client.execute_read.return_value = [{"is_archetype": False}]

    # Mock update
    updated_data = entity_instance_data.copy()
    updated_data["state_tags"] = ["alive", "wounded", "at_rivendell"]
    mock_neo4j_client.execute_write.return_value = [
        {"e": updated_data, "archetype_id": updated_data["archetype_id"]}
    ]

    params = StateTagsUpdate(add_tags=["wounded", "at_rivendell"], remove_tags=["traveling"])

    result = neo4j_set_state_tags(UUID(entity_instance_data["id"]), params)

    assert "wounded" in result.state_tags
    assert "at_rivendell" in result.state_tags
    assert "traveling" not in result.state_tags


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_set_state_tags_on_archetype_fails(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity_archetype_data: Dict[str, Any],
):
    """Test that state_tags cannot be set on archetypes."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity exists and is archetype
    mock_neo4j_client.execute_read.return_value = [{"is_archetype": True}]

    params = StateTagsUpdate(add_tags=["alive"])

    with pytest.raises(ValueError, match="Cannot set state_tags on EntityArchetype"):
        neo4j_set_state_tags(UUID(entity_archetype_data["id"]), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_set_state_tags_entity_not_found(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test setting state_tags on non-existent entity."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entity doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = StateTagsUpdate(add_tags=["alive"])

    with pytest.raises(ValueError, match="Entity .* not found"):
        neo4j_set_state_tags(uuid4(), params)


def test_set_state_tags_overlapping_tags_fails():
    """Test that overlapping tags in add and remove lists are rejected."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Tags cannot appear in both add_tags and remove_tags"):
        StateTagsUpdate(add_tags=["alive", "wounded"], remove_tags=["wounded", "dead"])


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_entity_lifecycle(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    entity_archetype_data: Dict[str, Any],
    entity_instance_data: Dict[str, Any],
):
    """Integration test: create archetype → create instance → update → delete."""
    mock_get_client.return_value = mock_neo4j_client

    # 1. Create archetype
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]
    mock_neo4j_client.execute_write.return_value = [{"e": entity_archetype_data}]

    archetype_params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name="Wizard",
        entity_type=EntityType.CHARACTER,
        is_archetype=True,
    )
    archetype = neo4j_create_entity(archetype_params)
    assert archetype.is_archetype is True

    # 2. Create instance with archetype
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],
        [{"id": entity_archetype_data["id"]}],
    ]
    mock_neo4j_client.execute_write.return_value = [{"e": entity_instance_data}]

    instance_params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name="Gandalf",
        entity_type=EntityType.CHARACTER,
        is_archetype=False,
        archetype_id=archetype.id,
        state_tags=["alive", "traveling"],
    )
    instance = neo4j_create_entity(instance_params)
    assert instance.archetype_id == archetype.id

    # 3. Update instance
    # Reset side_effect to None and use return_value
    mock_neo4j_client.execute_read.side_effect = None
    mock_neo4j_client.execute_read.return_value = [{"id": entity_instance_data["id"]}]
    updated_data = entity_instance_data.copy()
    updated_data["name"] = "Gandalf the White"
    mock_neo4j_client.execute_write.return_value = [
        {"e": updated_data, "archetype_id": updated_data["archetype_id"]}
    ]

    update_params = EntityUpdate(name="Gandalf the White")
    updated = neo4j_update_entity(instance.id, update_params)
    assert updated.name == "Gandalf the White"

    # 4. Delete instance (no dependencies)
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": entity_instance_data["id"]}],
        [{"dependent_count": 0}],
    ]

    result = neo4j_delete_entity(instance.id)
    assert result["deleted"] is True


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_entity_hierarchy(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    entity_archetype_data: Dict[str, Any],
):
    """Integration test: archetype with multiple instances."""
    mock_get_client.return_value = mock_neo4j_client

    # Create archetype
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]
    mock_neo4j_client.execute_write.return_value = [{"e": entity_archetype_data}]

    archetype_params = EntityCreate(
        universe_id=UUID(universe_data["id"]),
        name="Wizard",
        entity_type=EntityType.CHARACTER,
        is_archetype=True,
    )
    archetype = neo4j_create_entity(archetype_params)

    # Create multiple instances from same archetype
    for name in ["Gandalf", "Saruman", "Radagast"]:
        mock_neo4j_client.execute_read.side_effect = [
            [{"id": universe_data["id"]}],
            [{"id": entity_archetype_data["id"]}],
        ]

        instance_data = {
            "id": str(uuid4()),
            "universe_id": universe_data["id"],
            "name": name,
            "entity_type": "character",
            "is_archetype": False,
            "description": f"{name} the wizard",
            "properties": {},
            "state_tags": ["alive"],
            "archetype_id": entity_archetype_data["id"],
            "canon_level": CanonLevel.CANON.value,
            "confidence": 1.0,
            "authority": Authority.GM.value,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }
        mock_neo4j_client.execute_write.return_value = [{"e": instance_data}]

        instance_params = EntityCreate(
            universe_id=UUID(universe_data["id"]),
            name=name,
            entity_type=EntityType.CHARACTER,
            is_archetype=False,
            archetype_id=archetype.id,
            state_tags=["alive"],
        )
        instance = neo4j_create_entity(instance_params)
        assert instance.archetype_id == archetype.id
        assert instance.name == name

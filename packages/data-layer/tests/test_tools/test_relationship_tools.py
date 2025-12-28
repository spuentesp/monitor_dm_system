"""
Unit tests for Neo4j relationship operations (DL-14).

Tests cover:
- neo4j_create_relationship (all rel_types, validation)
- neo4j_get_relationship
- neo4j_list_relationships (filtering by entity, type, direction)
- neo4j_update_relationship
- neo4j_delete_relationship
- neo4j_update_state_tags (alias test)
- neo4j_get_state_tags
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.relationships import (
    RelationshipType,
    RelationshipCreate,
    RelationshipUpdate,
    RelationshipFilter,
)
from monitor_data.schemas.entities import StateTagsUpdate
from monitor_data.tools.neo4j_tools import (
    neo4j_create_relationship,
    neo4j_get_relationship,
    neo4j_list_relationships,
    neo4j_update_relationship,
    neo4j_delete_relationship,
    neo4j_update_state_tags,
    neo4j_get_state_tags,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def entity1_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample entity 1 data (character)."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Gandalf",
        "entity_type": "character",
        "is_archetype": False,
        "state_tags": ["alive"],
    }


@pytest.fixture
def entity2_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample entity 2 data (faction)."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Fellowship",
        "entity_type": "faction",
        "is_archetype": False,
        "state_tags": [],
    }


@pytest.fixture
def relationship_data(entity1_data: Dict[str, Any], entity2_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample relationship data."""
    return {
        "rel_id": 12345,
        "rel_type": "MEMBER_OF",
        "properties": {"joined_at": "2024-01-01", "role": "leader"},
        "from_id": entity1_data["id"],
        "from_name": entity1_data["name"],
        "to_id": entity2_data["id"],
        "to_name": entity2_data["name"],
    }


# =============================================================================
# TESTS: neo4j_create_relationship
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_relationship_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity1_data: Dict[str, Any],
    entity2_data: Dict[str, Any],
):
    """Test creating a relationship with valid parameters."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock both entities exist
    mock_neo4j_client.execute_read.return_value = [
        {
            "from_id": entity1_data["id"],
            "from_name": entity1_data["name"],
            "to_id": entity2_data["id"],
            "to_name": entity2_data["name"],
        }
    ]

    # Mock relationship creation
    mock_neo4j_client.execute_write.return_value = [
        {
            "rel_id": 12345,
            "rel_type": "MEMBER_OF",
            "properties": {"role": "leader"},
        }
    ]

    params = RelationshipCreate(
        from_entity_id=UUID(entity1_data["id"]),
        to_entity_id=UUID(entity2_data["id"]),
        rel_type=RelationshipType.MEMBER_OF,
        properties={"role": "leader"},
    )

    result = neo4j_create_relationship(params)

    assert result.id == "12345"
    assert result.from_entity_id == UUID(entity1_data["id"])
    assert result.to_entity_id == UUID(entity2_data["id"])
    assert result.rel_type == RelationshipType.MEMBER_OF
    assert result.properties == {"role": "leader"}
    assert result.from_entity_name == entity1_data["name"]
    assert result.to_entity_name == entity2_data["name"]
    assert mock_neo4j_client.execute_read.call_count == 1
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_relationship_entity_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity1_data: Dict[str, Any],
    entity2_data: Dict[str, Any],
):
    """Test creating a relationship when entities don't exist."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entities not found
    mock_neo4j_client.execute_read.return_value = []

    params = RelationshipCreate(
        from_entity_id=UUID(entity1_data["id"]),
        to_entity_id=UUID(entity2_data["id"]),
        rel_type=RelationshipType.MEMBER_OF,
    )

    with pytest.raises(ValueError, match="One or both entities not found"):
        neo4j_create_relationship(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@pytest.mark.parametrize(
    "rel_type",
    [
        RelationshipType.MEMBER_OF,
        RelationshipType.OWNS,
        RelationshipType.ALLY_OF,
        RelationshipType.ENEMY_OF,
        RelationshipType.LOCATED_IN,
        RelationshipType.PARTICIPATED_IN,
        RelationshipType.DERIVES_FROM,
    ],
)
def test_create_relationship_all_types(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity1_data: Dict[str, Any],
    entity2_data: Dict[str, Any],
    rel_type: RelationshipType,
):
    """Test creating relationships with all supported rel_types."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock entities exist
    mock_neo4j_client.execute_read.return_value = [
        {
            "from_id": entity1_data["id"],
            "from_name": entity1_data["name"],
            "to_id": entity2_data["id"],
            "to_name": entity2_data["name"],
        }
    ]

    # Mock relationship creation
    mock_neo4j_client.execute_write.return_value = [
        {
            "rel_id": 99999,
            "rel_type": rel_type.value,
            "properties": {},
        }
    ]

    params = RelationshipCreate(
        from_entity_id=UUID(entity1_data["id"]),
        to_entity_id=UUID(entity2_data["id"]),
        rel_type=rel_type,
    )

    result = neo4j_create_relationship(params)

    assert result.rel_type == rel_type


def test_create_relationship_same_entity():
    """Test that creating a relationship from entity to itself raises error."""
    entity_id = uuid4()

    with pytest.raises(ValueError, match="must be different"):
        RelationshipCreate(
            from_entity_id=entity_id,
            to_entity_id=entity_id,
            rel_type=RelationshipType.ALLY_OF,
        )


# =============================================================================
# TESTS: neo4j_get_relationship
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_relationship_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    relationship_data: Dict[str, Any],
):
    """Test getting a relationship by ID."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = [relationship_data]

    result = neo4j_get_relationship("12345")

    assert result is not None
    assert result.id == "12345"
    assert result.rel_type == RelationshipType.MEMBER_OF
    assert result.from_entity_name == relationship_data["from_name"]
    assert result.to_entity_name == relationship_data["to_name"]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_relationship_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test getting a non-existent relationship."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_relationship("99999")

    assert result is None


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_relationship_invalid_id(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test getting a relationship with invalid ID."""
    mock_get_client.return_value = mock_neo4j_client

    result = neo4j_get_relationship("not-a-number")

    assert result is None


# =============================================================================
# TESTS: neo4j_list_relationships
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_relationships_by_entity(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity1_data: Dict[str, Any],
    relationship_data: Dict[str, Any],
):
    """Test listing relationships filtered by entity_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [relationship_data],
    ]

    filters = RelationshipFilter(entity_id=UUID(entity1_data["id"]))
    result = neo4j_list_relationships(filters)

    assert result.total == 1
    assert len(result.relationships) == 1
    assert result.relationships[0].from_entity_id == UUID(entity1_data["id"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_relationships_by_type(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    relationship_data: Dict[str, Any],
):
    """Test listing relationships filtered by rel_type."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [relationship_data],
    ]

    filters = RelationshipFilter(rel_type=RelationshipType.MEMBER_OF)
    result = neo4j_list_relationships(filters)

    assert result.total == 1
    assert len(result.relationships) == 1
    assert result.relationships[0].rel_type == RelationshipType.MEMBER_OF


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@pytest.mark.parametrize("direction", ["outgoing", "incoming", "both"])
def test_list_relationships_by_direction(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    relationship_data: Dict[str, Any],
    direction: str,
):
    """Test listing relationships with direction filter."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [relationship_data],
    ]

    filters = RelationshipFilter(direction=direction)
    result = neo4j_list_relationships(filters)

    assert result.total == 1
    assert len(result.relationships) == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_relationships_pagination(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test pagination in list_relationships."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and empty list
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 100}],
        [],
    ]

    filters = RelationshipFilter(limit=10, offset=20)
    result = neo4j_list_relationships(filters)

    assert result.total == 100
    assert result.limit == 10
    assert result.offset == 20


# =============================================================================
# TESTS: neo4j_update_relationship
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_relationship_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    relationship_data: Dict[str, Any],
):
    """Test updating a relationship's properties."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock verify and update
    updated_data = relationship_data.copy()
    updated_data["properties"] = {"role": "member", "status": "active"}
    mock_neo4j_client.execute_read.return_value = [{"rel_id": 12345}]
    mock_neo4j_client.execute_write.return_value = [updated_data]

    params = RelationshipUpdate(properties={"role": "member", "status": "active"})
    result = neo4j_update_relationship("12345", params)

    assert result.id == "12345"
    assert result.properties == {"role": "member", "status": "active"}


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_relationship_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test updating a non-existent relationship."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = []

    params = RelationshipUpdate(properties={"role": "member"})

    with pytest.raises(ValueError, match="not found"):
        neo4j_update_relationship("99999", params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_relationship_invalid_id(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test updating a relationship with invalid ID."""
    mock_get_client.return_value = mock_neo4j_client

    params = RelationshipUpdate(properties={"role": "member"})

    with pytest.raises(ValueError, match="Invalid relationship ID"):
        neo4j_update_relationship("not-a-number", params)


# =============================================================================
# TESTS: neo4j_delete_relationship
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_relationship_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test deleting a relationship."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_write.return_value = [{"deleted_count": 1}]

    result = neo4j_delete_relationship("12345")

    assert result["relationship_id"] == "12345"
    assert result["deleted"] is True


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_relationship_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test deleting a non-existent relationship."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_write.return_value = [{"deleted_count": 0}]

    with pytest.raises(ValueError, match="not found"):
        neo4j_delete_relationship("99999")


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_relationship_invalid_id(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test deleting a relationship with invalid ID."""
    mock_get_client.return_value = mock_neo4j_client

    with pytest.raises(ValueError, match="Invalid relationship ID"):
        neo4j_delete_relationship("not-a-number")


# =============================================================================
# TESTS: neo4j_update_state_tags (alias test)
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.neo4j_set_state_tags")
def test_update_state_tags_alias(mock_set_state_tags: Mock):
    """Test that neo4j_update_state_tags is an alias for neo4j_set_state_tags."""
    entity_id = uuid4()
    params = StateTagsUpdate(add_tags=["wounded"], remove_tags=["healthy"])

    # Mock the return value
    mock_set_state_tags.return_value = Mock()

    neo4j_update_state_tags(entity_id, params)

    # Verify it calls neo4j_set_state_tags with same params
    mock_set_state_tags.assert_called_once_with(entity_id, params)


# =============================================================================
# TESTS: neo4j_get_state_tags
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_state_tags_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity1_data: Dict[str, Any],
):
    """Test getting state tags for an entity instance."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = [
        {"is_archetype": False, "state_tags": ["alive", "wounded"]}
    ]

    result = neo4j_get_state_tags(UUID(entity1_data["id"]))

    assert result == ["alive", "wounded"]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_state_tags_entity_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test getting state tags for non-existent entity."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="not found"):
        neo4j_get_state_tags(uuid4())


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_state_tags_archetype_error(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test that getting state tags from archetype raises error."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = [
        {"is_archetype": True, "state_tags": []}
    ]

    with pytest.raises(ValueError, match="Cannot get state_tags from EntityArchetype"):
        neo4j_get_state_tags(uuid4())


# =============================================================================
# INTEGRATION TEST: Relationship Lifecycle
# =============================================================================


@pytest.mark.integration
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_relationship_lifecycle(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    entity1_data: Dict[str, Any],
    entity2_data: Dict[str, Any],
):
    """Test complete relationship lifecycle: create → update → delete."""
    mock_get_client.return_value = mock_neo4j_client

    # Step 1: Create
    mock_neo4j_client.execute_read.return_value = [
        {
            "from_id": entity1_data["id"],
            "from_name": entity1_data["name"],
            "to_id": entity2_data["id"],
            "to_name": entity2_data["name"],
        }
    ]
    mock_neo4j_client.execute_write.return_value = [
        {
            "rel_id": 12345,
            "rel_type": "ALLY_OF",
            "properties": {"strength": "strong"},
        }
    ]

    create_params = RelationshipCreate(
        from_entity_id=UUID(entity1_data["id"]),
        to_entity_id=UUID(entity2_data["id"]),
        rel_type=RelationshipType.ALLY_OF,
        properties={"strength": "strong"},
    )
    created = neo4j_create_relationship(create_params)
    assert created.rel_type == RelationshipType.ALLY_OF

    # Step 2: Update
    mock_neo4j_client.execute_read.return_value = [{"rel_id": 12345}]
    mock_neo4j_client.execute_write.return_value = [
        {
            "rel_id": 12345,
            "rel_type": "ALLY_OF",
            "properties": {"strength": "weak"},
            "from_id": entity1_data["id"],
            "from_name": entity1_data["name"],
            "to_id": entity2_data["id"],
            "to_name": entity2_data["name"],
        }
    ]

    update_params = RelationshipUpdate(properties={"strength": "weak"})
    updated = neo4j_update_relationship(created.id, update_params)
    assert updated.properties["strength"] == "weak"

    # Step 3: Delete
    mock_neo4j_client.execute_write.return_value = [{"deleted_count": 1}]
    result = neo4j_delete_relationship(created.id)
    assert result["deleted"] is True

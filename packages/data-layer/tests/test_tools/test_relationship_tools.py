"""
Tests for Neo4j Relationship and State Tag operations (DL-14).

Tests cover:
- neo4j_create_relationship
- neo4j_get_relationship
- neo4j_list_relationships
- neo4j_update_relationship
- neo4j_delete_relationship
- neo4j_update_state_tags
- neo4j_get_state_tags
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.relationships import (
    RelationshipType,
    Direction,
    StateTag,
    RelationshipCreate,
    RelationshipUpdate,
    RelationshipFilter,
)
from monitor_data.tools.neo4j_tools import (
    neo4j_create_relationship,
    neo4j_get_relationship,
    neo4j_list_relationships,
    neo4j_update_relationship,
    neo4j_delete_relationship,
    neo4j_update_state_tags,
    neo4j_get_state_tags,
)
from monitor_data.schemas.relationships import StateTagUpdate


# =============================================================================
# TESTS: neo4j_create_relationship
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_relationship_success(mock_get_client: Mock):
    """Test creating a relationship between two entities."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()
    rel_id = "123"

    # Mock entity validation (both entities exist)
    mock_client.execute_read.side_effect = [
        [{"id": str(entity1_id)}],  # from_entity exists
        [{"id": str(entity2_id)}],  # to_entity exists
    ]

    # Mock relationship creation
    mock_client.execute_write.return_value = [
        {
            "rel_id": rel_id,
            "rel_type": "KNOWS",
            "props": {
                "since": "2020-01-01",
                "strength": 5,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    ]

    params = RelationshipCreate(
        from_entity_id=entity1_id,
        to_entity_id=entity2_id,
        rel_type=RelationshipType.KNOWS,
        properties={"since": "2020-01-01", "strength": 5},
    )

    result = neo4j_create_relationship(params)

    assert result.from_entity_id == entity1_id
    assert result.to_entity_id == entity2_id
    assert result.rel_type == RelationshipType.KNOWS
    assert result.properties["since"] == "2020-01-01"
    assert result.properties["strength"] == 5
    assert result.relationship_id == rel_id


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_relationship_from_entity_not_found(mock_get_client: Mock):
    """Test creating relationship with non-existent from_entity fails."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity2_id = uuid4()

    # Mock entity validation (from_entity doesn't exist)
    mock_client.execute_read.return_value = []

    params = RelationshipCreate(
        from_entity_id=uuid4(),  # Non-existent
        to_entity_id=entity2_id,
        rel_type=RelationshipType.KNOWS,
    )

    with pytest.raises(ValueError, match="From entity .* not found"):
        neo4j_create_relationship(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_relationship_to_entity_not_found(mock_get_client: Mock):
    """Test creating relationship with non-existent to_entity fails."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()

    # Mock entity validation (from exists, to doesn't)
    mock_client.execute_read.side_effect = [
        [{"id": str(entity1_id)}],  # from_entity exists
        [],  # to_entity doesn't exist
    ]

    params = RelationshipCreate(
        from_entity_id=entity1_id,
        to_entity_id=uuid4(),  # Non-existent
        rel_type=RelationshipType.KNOWS,
    )

    with pytest.raises(ValueError, match="To entity .* not found"):
        neo4j_create_relationship(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_relationship_all_types(mock_get_client: Mock):
    """Test creating relationships of all supported types."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()

    # Test each relationship type
    for rel_type in RelationshipType:
        # Mock entity validation
        mock_client.execute_read.side_effect = [
            [{"id": str(entity1_id)}],
            [{"id": str(entity2_id)}],
        ]

        # Mock relationship creation
        mock_client.execute_write.return_value = [
            {
                "rel_id": "123",
                "rel_type": rel_type.value,
                "props": {"created_at": datetime.now(timezone.utc).isoformat()},
            }
        ]

        params = RelationshipCreate(
            from_entity_id=entity1_id,
            to_entity_id=entity2_id,
            rel_type=rel_type,
        )

        result = neo4j_create_relationship(params)
        assert result.rel_type == rel_type


# =============================================================================
# TESTS: neo4j_get_relationship
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_relationship_success(mock_get_client: Mock):
    """Test retrieving a relationship by ID."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()
    rel_id = "123"

    mock_client.execute_read.return_value = [
        {
            "rel_id": rel_id,
            "from_id": str(entity1_id),
            "to_id": str(entity2_id),
            "rel_type": "KNOWS",
            "props": {
                "since": "2020-01-01",
                "strength": 5,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    ]

    result = neo4j_get_relationship(rel_id)

    assert result is not None
    assert result.relationship_id == rel_id
    assert result.from_entity_id == entity1_id
    assert result.to_entity_id == entity2_id
    assert result.rel_type == RelationshipType.KNOWS


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_relationship_not_found(mock_get_client: Mock):
    """Test retrieving non-existent relationship returns None."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    mock_client.execute_read.return_value = []

    result = neo4j_get_relationship("999")

    assert result is None


# =============================================================================
# TESTS: neo4j_list_relationships
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_relationships_all(mock_get_client: Mock):
    """Test listing all relationships without filters."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()

    # Mock count query
    mock_client.execute_read.side_effect = [
        [{"total": 2}],  # count query
        [  # data query
            {
                "rel_id": "1",
                "from_id": str(entity1_id),
                "to_id": str(entity2_id),
                "rel_type": "KNOWS",
                "props": {"created_at": datetime.now(timezone.utc).isoformat()},
            },
            {
                "rel_id": "2",
                "from_id": str(entity2_id),
                "to_id": str(entity1_id),
                "rel_type": "ALLIED_WITH",
                "props": {"created_at": datetime.now(timezone.utc).isoformat()},
            },
        ],
    ]

    params = RelationshipFilter(limit=50)
    result = neo4j_list_relationships(params)

    assert result.total == 2
    assert len(result.relationships) == 2
    assert result.relationships[0].rel_type == RelationshipType.KNOWS
    assert result.relationships[1].rel_type == RelationshipType.ALLIED_WITH


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_relationships_by_entity_outgoing(mock_get_client: Mock):
    """Test listing outgoing relationships from an entity."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()

    # Mock count and data queries
    mock_client.execute_read.side_effect = [
        [{"total": 1}],  # count query
        [  # data query
            {
                "rel_id": "1",
                "from_id": str(entity1_id),
                "to_id": str(entity2_id),
                "rel_type": "KNOWS",
                "props": {"created_at": datetime.now(timezone.utc).isoformat()},
            }
        ],
    ]

    params = RelationshipFilter(entity_id=entity1_id, direction=Direction.OUTGOING)
    result = neo4j_list_relationships(params)

    assert result.total == 1
    assert result.relationships[0].from_entity_id == entity1_id


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_relationships_by_entity_incoming(mock_get_client: Mock):
    """Test listing incoming relationships to an entity."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()

    # Mock count and data queries
    mock_client.execute_read.side_effect = [
        [{"total": 1}],  # count query
        [  # data query
            {
                "rel_id": "1",
                "from_id": str(entity2_id),
                "to_id": str(entity1_id),
                "rel_type": "KNOWS",
                "props": {"created_at": datetime.now(timezone.utc).isoformat()},
            }
        ],
    ]

    params = RelationshipFilter(entity_id=entity1_id, direction=Direction.INCOMING)
    result = neo4j_list_relationships(params)

    assert result.total == 1
    assert result.relationships[0].to_entity_id == entity1_id


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_relationships_by_type(mock_get_client: Mock):
    """Test listing relationships filtered by type."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()

    # Mock count and data queries
    mock_client.execute_read.side_effect = [
        [{"total": 1}],  # count query
        [  # data query
            {
                "rel_id": "1",
                "from_id": str(entity1_id),
                "to_id": str(entity2_id),
                "rel_type": "ALLIED_WITH",
                "props": {"created_at": datetime.now(timezone.utc).isoformat()},
            }
        ],
    ]

    params = RelationshipFilter(rel_type=RelationshipType.ALLIED_WITH)
    result = neo4j_list_relationships(params)

    assert result.total == 1
    assert result.relationships[0].rel_type == RelationshipType.ALLIED_WITH


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_relationships_direction_both(mock_get_client: Mock):
    """Test listing relationships in both directions."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()

    # Mock count and data queries
    mock_client.execute_read.side_effect = [
        [{"total": 2}],  # count query
        [  # data query
            {
                "rel_id": "1",
                "from_id": str(entity1_id),
                "to_id": str(entity2_id),
                "rel_type": "KNOWS",
                "props": {"created_at": datetime.now(timezone.utc).isoformat()},
            },
            {
                "rel_id": "2",
                "from_id": str(entity2_id),
                "to_id": str(entity1_id),
                "rel_type": "KNOWS",
                "props": {"created_at": datetime.now(timezone.utc).isoformat()},
            },
        ],
    ]

    params = RelationshipFilter(entity_id=entity1_id, direction=Direction.BOTH)
    result = neo4j_list_relationships(params)

    assert result.total == 2


# =============================================================================
# TESTS: neo4j_update_relationship
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_relationship_properties(mock_get_client: Mock):
    """Test updating relationship properties."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity1_id = uuid4()
    entity2_id = uuid4()
    rel_id = "123"

    # Mock get (to verify exists), then write, then get (to return updated)
    created_at_iso = datetime.now(timezone.utc).isoformat()
    mock_client.execute_read.side_effect = [
        # First get (verify exists)
        [
            {
                "rel_id": rel_id,
                "from_id": str(entity1_id),
                "to_id": str(entity2_id),
                "rel_type": "KNOWS",
                "props": {"created_at": created_at_iso},
            }
        ],
        # Second get (return updated)
        [
            {
                "rel_id": rel_id,
                "from_id": str(entity1_id),
                "to_id": str(entity2_id),
                "rel_type": "KNOWS",
                "props": {
                    "strength": 8,
                    "notes": "Updated relationship",
                    "created_at": created_at_iso,
                },
            }
        ],
    ]

    # Mock write
    mock_client.execute_write.return_value = [{"rel_id": rel_id}]

    params = RelationshipUpdate(
        properties={"strength": 8, "notes": "Updated relationship"}
    )

    result = neo4j_update_relationship(rel_id, params)

    assert result.relationship_id == rel_id
    assert result.properties["strength"] == 8
    assert result.properties["notes"] == "Updated relationship"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_relationship_not_found(mock_get_client: Mock):
    """Test updating non-existent relationship fails."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    # Mock get (not found)
    mock_client.execute_read.return_value = []

    params = RelationshipUpdate(properties={"strength": 8})

    with pytest.raises(ValueError, match="Relationship .* not found"):
        neo4j_update_relationship("999", params)


# =============================================================================
# TESTS: neo4j_delete_relationship
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_relationship_success(mock_get_client: Mock):
    """Test deleting a relationship."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    rel_id = "123"
    entity1_id = uuid4()
    entity2_id = uuid4()

    # Mock get (verify exists)
    mock_client.execute_read.return_value = [
        {
            "rel_id": rel_id,
            "from_id": str(entity1_id),
            "to_id": str(entity2_id),
            "rel_type": "KNOWS",
            "props": {},
        }
    ]

    # Mock successful delete
    mock_client.execute_write.return_value = [{"deleted_count": 1}]

    result = neo4j_delete_relationship(rel_id)

    assert result["deleted"] is True
    assert result["deleted_count"] == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_relationship_not_found(mock_get_client: Mock):
    """Test deleting non-existent relationship fails."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    # Mock get (not found)
    mock_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Relationship .* not found"):
        neo4j_delete_relationship("999")


# =============================================================================
# TESTS: neo4j_update_state_tags
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_state_tags_add(mock_get_client: Mock):
    """Test adding state tags to an entity."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity_id = uuid4()

    # Mock entity validation (is instance)
    mock_client.execute_read.return_value = [
        {"id": str(entity_id), "is_archetype": False}
    ]

    # Mock tag update
    mock_client.execute_write.return_value = [{"tags": ["alive", "wounded"]}]

    params = StateTagUpdate(
        entity_id=entity_id,
        add_tags=[StateTag.ALIVE, StateTag.WOUNDED],
    )

    result = neo4j_update_state_tags(params)

    assert result.entity_id == entity_id
    assert StateTag.ALIVE in result.state_tags
    assert StateTag.WOUNDED in result.state_tags


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_state_tags_remove(mock_get_client: Mock):
    """Test removing state tags from an entity."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity_id = uuid4()

    # Mock entity validation (is instance with existing tags)
    mock_client.execute_read.return_value = [
        {"id": str(entity_id), "is_archetype": False}
    ]

    # Mock tag update
    mock_client.execute_write.return_value = [{"tags": ["alive"]}]

    params = StateTagUpdate(
        entity_id=entity_id,
        remove_tags=[StateTag.WOUNDED],
    )

    result = neo4j_update_state_tags(params)

    assert result.entity_id == entity_id
    assert StateTag.ALIVE in result.state_tags
    assert StateTag.WOUNDED not in result.state_tags


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_state_tags_add_and_remove(mock_get_client: Mock):
    """Test adding and removing state tags atomically."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity_id = uuid4()

    # Mock entity validation
    mock_client.execute_read.return_value = [
        {"id": str(entity_id), "is_archetype": False}
    ]

    # Mock tag update
    mock_client.execute_write.return_value = [
        {"tags": ["dead"]}  # removed wounded, added dead
    ]

    params = StateTagUpdate(
        entity_id=entity_id,
        add_tags=[StateTag.DEAD],
        remove_tags=[StateTag.WOUNDED],
    )

    result = neo4j_update_state_tags(params)

    assert result.entity_id == entity_id
    assert StateTag.DEAD in result.state_tags
    assert StateTag.WOUNDED not in result.state_tags


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_state_tags_archetype_fails(mock_get_client: Mock):
    """Test that state tags cannot be applied to archetypes."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity_id = uuid4()

    # Mock entity validation (is archetype)
    mock_client.execute_read.return_value = [
        {"id": str(entity_id), "is_archetype": True}
    ]

    params = StateTagUpdate(
        entity_id=entity_id,
        add_tags=[StateTag.ALIVE],
    )

    with pytest.raises(ValueError, match="Cannot set state tags on archetype"):
        neo4j_update_state_tags(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_state_tags_entity_not_found(mock_get_client: Mock):
    """Test updating state tags for non-existent entity fails."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    # Mock entity not found
    mock_client.execute_read.return_value = []

    params = StateTagUpdate(
        entity_id=uuid4(),
        add_tags=[StateTag.ALIVE],
    )

    with pytest.raises(ValueError, match="Entity .* not found"):
        neo4j_update_state_tags(params)


# =============================================================================
# TESTS: neo4j_get_state_tags
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_state_tags_success(mock_get_client: Mock):
    """Test retrieving state tags for an entity."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity_id = uuid4()

    mock_client.execute_read.return_value = [{"tags": ["alive", "wounded", "prone"]}]

    result = neo4j_get_state_tags(entity_id)

    assert result.entity_id == entity_id
    assert len(result.state_tags) == 3
    assert StateTag.ALIVE in result.state_tags
    assert StateTag.WOUNDED in result.state_tags
    assert StateTag.PRONE in result.state_tags


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_state_tags_empty(mock_get_client: Mock):
    """Test retrieving state tags for entity with no tags."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    entity_id = uuid4()

    mock_client.execute_read.return_value = [{"tags": []}]

    result = neo4j_get_state_tags(entity_id)

    assert result.entity_id == entity_id
    assert len(result.state_tags) == 0


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_state_tags_entity_not_found(mock_get_client: Mock):
    """Test retrieving state tags for non-existent entity fails."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    # Mock entity not found
    mock_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Entity .* not found"):
        neo4j_get_state_tags(uuid4())

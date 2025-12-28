"""
Unit tests for Neo4j universe operations.

Tests cover:
- neo4j_create_universe
- neo4j_get_universe
- neo4j_list_universes
- neo4j_update_universe
- neo4j_delete_universe
- neo4j_create_multiverse
- neo4j_get_multiverse
- neo4j_ensure_omniverse
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.universe import (
    UniverseCreate,
    UniverseUpdate,
    UniverseFilter,
    MultiverseCreate,
)
from monitor_data.schemas.base import CanonLevel
from monitor_data.tools.neo4j_tools import (
    neo4j_create_universe,
    neo4j_get_universe,
    neo4j_list_universes,
    neo4j_update_universe,
    neo4j_delete_universe,
    neo4j_create_multiverse,
    neo4j_get_multiverse,
    neo4j_ensure_omniverse,
)


# =============================================================================
# TESTS: neo4j_create_universe
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_universe_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    multiverse_data: Dict[str, Any],
    universe_data: Dict[str, Any],
):
    """Test successful universe creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock multiverse exists check
    mock_neo4j_client.execute_read.return_value = [{"id": multiverse_data["id"]}]

    # Mock universe creation
    mock_neo4j_client.execute_write.return_value = [{"u": universe_data}]

    params = UniverseCreate(
        multiverse_id=UUID(multiverse_data["id"]),
        name="Test Universe",
        description="A test universe",
        genre="fantasy",
        tone="heroic",
        tech_level="medieval",
    )

    result = neo4j_create_universe(params)

    assert result.name == "Test Universe"
    assert result.multiverse_id == UUID(multiverse_data["id"])
    assert result.genre == "fantasy"
    assert result.canon_level == CanonLevel.CANON
    assert mock_neo4j_client.execute_read.call_count == 1
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_universe_invalid_multiverse(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test universe creation with invalid multiverse_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock multiverse doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = UniverseCreate(
        multiverse_id=uuid4(),
        name="Test Universe",
        description="A test universe",
    )

    with pytest.raises(ValueError, match="Multiverse .* not found"):
        neo4j_create_universe(params)


def test_create_universe_missing_required():
    """Test universe creation with missing required fields."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        # Missing name (required field)
        UniverseCreate(
            multiverse_id=uuid4(),
            description="A test universe",
        )  # type: ignore

    # Verify the error mentions the missing field
    assert "name" in str(exc_info.value).lower()


# =============================================================================
# TESTS: neo4j_get_universe
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_universe_exists(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test getting an existing universe."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"u": universe_data}]

    universe_id = UUID(universe_data["id"])
    result = neo4j_get_universe(universe_id)

    assert result is not None
    assert result.id == universe_id
    assert result.name == universe_data["name"]
    assert result.genre == universe_data["genre"]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_universe_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test getting a non-existent universe."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_universe(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_list_universes
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_universes_no_filter(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test listing all universes without filters."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [
        {"u": universe_data},
        {"u": {**universe_data, "id": str(uuid4()), "name": "Another Universe"}},
    ]

    result = neo4j_list_universes()

    assert len(result) == 2
    assert result[0].name == universe_data["name"]
    assert result[1].name == "Another Universe"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_universes_with_multiverse_filter(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    multiverse_data: Dict[str, Any],
    universe_data: Dict[str, Any],
):
    """Test listing universes filtered by multiverse_id."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"u": universe_data}]

    filters = UniverseFilter(multiverse_id=UUID(multiverse_data["id"]))
    result = neo4j_list_universes(filters)

    assert len(result) == 1
    assert result[0].multiverse_id == UUID(multiverse_data["id"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_universes_with_pagination(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test listing universes with pagination."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"u": universe_data}]

    filters = UniverseFilter(limit=10, offset=5)
    _ = neo4j_list_universes(filters)

    # Verify the query was called with correct pagination params
    call_args = mock_neo4j_client.execute_read.call_args
    assert call_args[0][1]["limit"] == 10
    assert call_args[0][1]["offset"] == 5


# =============================================================================
# TESTS: neo4j_update_universe
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_universe_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test successful universe update."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists check
    mock_neo4j_client.execute_read.return_value = [{"u": universe_data}]

    # Mock universe update
    updated_data = {**universe_data, "name": "Updated Universe", "tone": "dark"}
    mock_neo4j_client.execute_write.return_value = [{"u": updated_data}]

    universe_id = UUID(universe_data["id"])
    params = UniverseUpdate(name="Updated Universe", tone="dark")

    result = neo4j_update_universe(universe_id, params)

    assert result.name == "Updated Universe"
    assert result.tone == "dark"
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_universe_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test updating a non-existent universe."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = UniverseUpdate(name="Updated Universe")

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_update_universe(uuid4(), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_universe")
def test_update_universe_no_changes(
    mock_get_universe: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test updating a universe with no fields provided."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"u": universe_data}]

    # Mock the get call that happens when no updates are provided
    from monitor_data.schemas.universe import UniverseResponse

    mock_response = UniverseResponse(
        id=UUID(universe_data["id"]),
        multiverse_id=UUID(universe_data["multiverse_id"]),
        name=universe_data["name"],
        description=universe_data["description"],
        genre=universe_data.get("genre"),
        tone=universe_data.get("tone"),
        tech_level=universe_data.get("tech_level"),
        canon_level=universe_data["canon_level"],
        confidence=universe_data["confidence"],
        authority=universe_data["authority"],
        created_at=universe_data["created_at"],
    )
    mock_get_universe.return_value = mock_response

    universe_id = UUID(universe_data["id"])
    params = UniverseUpdate()  # No fields to update

    result = neo4j_update_universe(universe_id, params)

    # Should just return current state
    assert result.name == universe_data["name"]
    assert mock_neo4j_client.execute_write.call_count == 0


# =============================================================================
# TESTS: neo4j_delete_universe
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_universe_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test successful universe deletion."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.side_effect = [
        [{"u": universe_data}],  # verify exists
        [{"sources": 0, "axioms": 0, "entities": 0}],  # no dependencies
    ]

    # Mock deletion
    mock_neo4j_client.execute_write.return_value = [{"deleted_count": 1}]

    universe_id = UUID(universe_data["id"])
    result = neo4j_delete_universe(universe_id, force=False)

    assert result["deleted"] is True
    assert result["universe_id"] == str(universe_id)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_universe_with_dependencies_no_force(
    mock_get_client: Mock, mock_neo4j_client: Mock, universe_data: Dict[str, Any]
):
    """Test universe deletion fails when dependencies exist and force=False."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists with dependencies
    mock_neo4j_client.execute_read.side_effect = [
        [{"u": universe_data}],  # verify exists
        [{"sources": 2, "axioms": 3, "entities": 5}],  # has dependencies
    ]

    universe_id = UUID(universe_data["id"])

    with pytest.raises(ValueError, match="has dependent data"):
        neo4j_delete_universe(universe_id, force=False)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_universe_with_force(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test universe deletion with force=True cascades."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"u": universe_data}]

    # Mock cascade deletion
    mock_neo4j_client.execute_write.return_value = [{"deleted_count": 10}]

    universe_id = UUID(universe_data["id"])
    result = neo4j_delete_universe(universe_id, force=True)

    assert result["deleted"] is True
    assert result["force"] is True
    assert result["deleted_count"] == 10


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_universe_with_force_no_dependencies(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test universe deletion with force=True when there are no dependencies.
    
    This verifies that the cascade delete query correctly handles the edge case
    where the universe has no dependent data (empty dependents list).
    """
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"u": universe_data}]

    # Mock cascade deletion with only the universe itself (count=1)
    mock_neo4j_client.execute_write.return_value = [{"deleted_count": 1}]

    universe_id = UUID(universe_data["id"])
    result = neo4j_delete_universe(universe_id, force=True)

    assert result["deleted"] is True
    assert result["force"] is True
    assert result["deleted_count"] == 1  # Only the universe itself


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_universe_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test deleting a non-existent universe."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_delete_universe(uuid4())


# =============================================================================
# TESTS: neo4j_create_multiverse
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_multiverse_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    omniverse_data: Dict[str, Any],
    multiverse_data: Dict[str, Any],
):
    """Test successful multiverse creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock omniverse exists check
    mock_neo4j_client.execute_read.return_value = [{"id": omniverse_data["id"]}]

    # Mock multiverse creation
    mock_neo4j_client.execute_write.return_value = [{"m": multiverse_data}]

    params = MultiverseCreate(
        omniverse_id=UUID(omniverse_data["id"]),
        name="Test Multiverse",
        system_name="Test System",
        description="A test multiverse",
    )

    result = neo4j_create_multiverse(params)

    assert result.name == "Test Multiverse"
    assert result.system_name == "Test System"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_multiverse_invalid_omniverse(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test multiverse creation with invalid omniverse_id."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = MultiverseCreate(
        omniverse_id=uuid4(),
        name="Test Multiverse",
        system_name="Test System",
        description="A test multiverse",
    )

    with pytest.raises(ValueError, match="Omniverse .* not found"):
        neo4j_create_multiverse(params)


# =============================================================================
# TESTS: neo4j_get_multiverse
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_multiverse_exists(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    multiverse_data: Dict[str, Any],
):
    """Test getting an existing multiverse."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"m": multiverse_data}]

    multiverse_id = UUID(multiverse_data["id"])
    result = neo4j_get_multiverse(multiverse_id)

    assert result is not None
    assert result.id == multiverse_id
    assert result.name == multiverse_data["name"]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_multiverse_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test getting a non-existent multiverse."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_multiverse(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_ensure_omniverse
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_ensure_omniverse_already_exists(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test ensure_omniverse when omniverse already exists."""
    mock_get_client.return_value = mock_neo4j_client

    existing_id = str(uuid4())
    mock_neo4j_client.execute_read.return_value = [{"id": existing_id}]

    result = neo4j_ensure_omniverse()

    assert result["omniverse_id"] == existing_id
    assert result["created"] is False
    assert mock_neo4j_client.execute_write.call_count == 0


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_ensure_omniverse_creates_new(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test ensure_omniverse creates new omniverse when none exists."""
    mock_get_client.return_value = mock_neo4j_client

    # No existing omniverse
    mock_neo4j_client.execute_read.return_value = []

    new_id = str(uuid4())
    mock_neo4j_client.execute_write.return_value = [{"id": new_id}]

    result = neo4j_ensure_omniverse()

    assert result["created"] is True
    assert mock_neo4j_client.execute_write.call_count == 1

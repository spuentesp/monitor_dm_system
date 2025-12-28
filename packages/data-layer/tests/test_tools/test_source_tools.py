"""
Unit tests for Neo4j source operations.

Tests cover:
- neo4j_create_source
- neo4j_get_source
- neo4j_list_sources
- neo4j_update_source
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.sources import (
    SourceCreate,
    SourceUpdate,
    SourceFilter,
    SourceListResponse,
)
from monitor_data.schemas.base import SourceCanonLevel, SourceType
from monitor_data.tools.neo4j_tools import (
    neo4j_create_source,
    neo4j_get_source,
    neo4j_list_sources,
    neo4j_update_source,
)


# =============================================================================
# TESTS: neo4j_create_source
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_source_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test successful source creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists check
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock source creation
    mock_neo4j_client.execute_write.return_value = []

    params = SourceCreate(
        universe_id=UUID(universe_data["id"]),
        title="Player's Handbook",
        source_type=SourceType.RULEBOOK,
        edition="5th Edition",
        provenance="ISBN: 978-0786965601",
        canon_level=SourceCanonLevel.CANON,
        metadata={"author": "Wizards of the Coast"},
    )

    result = neo4j_create_source(params)

    assert result.title == "Player's Handbook"
    assert result.universe_id == UUID(universe_data["id"])
    assert result.source_type == SourceType.RULEBOOK
    assert result.edition == "5th Edition"
    assert result.canon_level == SourceCanonLevel.CANON
    assert mock_neo4j_client.execute_read.call_count == 1
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_source_invalid_universe(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test source creation with invalid universe_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = SourceCreate(
        universe_id=uuid4(),
        title="Test Source",
        source_type=SourceType.BOOK,
    )

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_create_source(params)


def test_create_source_missing_required():
    """Test source creation with missing required fields."""
    with pytest.raises(Exception):  # Pydantic validation error
        SourceCreate(
            universe_id=uuid4(),
            # Missing title and source_type
        )


# =============================================================================
# TESTS: neo4j_get_source
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_source_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    source_data: Dict[str, Any],
):
    """Test successful source retrieval."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = [{"s": source_data}]

    result = neo4j_get_source(UUID(source_data["id"]))

    assert result is not None
    assert result.id == UUID(source_data["id"])
    assert result.title == source_data["title"]
    assert result.source_type == SourceType(source_data["source_type"])
    assert result.canon_level == SourceCanonLevel(source_data["canon_level"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_source_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test source retrieval when source doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_source(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_list_sources
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_sources_no_filters(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    source_data: Dict[str, Any],
):
    """Test listing sources without filters."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count query
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"s": source_data}],
    ]

    filters = SourceFilter()
    result = neo4j_list_sources(filters)

    assert isinstance(result, SourceListResponse)
    assert result.total == 1
    assert len(result.sources) == 1
    assert result.sources[0].id == UUID(source_data["id"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_sources_with_filters(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    source_data: Dict[str, Any],
):
    """Test listing sources with filters."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count query
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"s": source_data}],
    ]

    filters = SourceFilter(
        universe_id=UUID(universe_data["id"]),
        source_type=SourceType.RULEBOOK,
        limit=10,
        offset=0,
    )
    result = neo4j_list_sources(filters)

    assert result.total == 1
    assert len(result.sources) == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_sources_empty(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test listing sources when none exist."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count query
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 0}],
        [],
    ]

    filters = SourceFilter()
    result = neo4j_list_sources(filters)

    assert result.total == 0
    assert len(result.sources) == 0


# =============================================================================
# TESTS: neo4j_update_source
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_source_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    source_data: Dict[str, Any],
):
    """Test successful source update."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock source exists check
    mock_neo4j_client.execute_read.return_value = [{"id": source_data["id"]}]

    # Mock update
    updated_data = {**source_data, "edition": "6th Edition"}
    mock_neo4j_client.execute_write.return_value = [{"s": updated_data}]

    params = SourceUpdate(edition="6th Edition")
    result = neo4j_update_source(UUID(source_data["id"]), params)

    assert result.edition == "6th Edition"
    assert mock_neo4j_client.execute_read.call_count == 1
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_source_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test updating non-existent source."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock source doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = SourceUpdate(title="Updated Title")

    with pytest.raises(ValueError, match="Source .* not found"):
        neo4j_update_source(uuid4(), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_source")
def test_update_source_no_changes(
    mock_get_source: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    source_data: Dict[str, Any],
):
    """Test updating source with no actual changes."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock source exists check
    mock_neo4j_client.execute_read.return_value = [{"id": source_data["id"]}]

    # Mock get_source for no-op case
    from monitor_data.schemas.sources import SourceResponse
    mock_get_source.return_value = SourceResponse(**source_data)

    params = SourceUpdate()  # No fields to update
    result = neo4j_update_source(UUID(source_data["id"]), params)

    assert result.id == UUID(source_data["id"])
    assert mock_neo4j_client.execute_write.call_count == 0  # No write should occur


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_source_canon_level(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    source_data: Dict[str, Any],
):
    """Test updating source canon_level."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock source exists check
    mock_neo4j_client.execute_read.return_value = [{"id": source_data["id"]}]

    # Mock update
    updated_data = {**source_data, "canon_level": "authoritative"}
    mock_neo4j_client.execute_write.return_value = [{"s": updated_data}]

    params = SourceUpdate(canon_level=SourceCanonLevel.AUTHORITATIVE)
    result = neo4j_update_source(UUID(source_data["id"]), params)

    assert result.canon_level == SourceCanonLevel.AUTHORITATIVE

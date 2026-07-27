"""Unit tests for the new Neo4j axiom/event mutation tools (F2-2 phase 1).

``neo4j_update_axiom`` / ``neo4j_delete_axiom`` / ``neo4j_update_event`` /
``neo4j_delete_event`` fill the update/delete gap the Fact tools already
covered. Mirrors the ``test_fact_tools.py`` mocking style.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.base import Authority, AxiomAuthority, CanonLevel, KnowledgeScope
from monitor_data.schemas.facts import (
    AxiomResponse,
    AxiomUpdate,
    EventResponse,
    EventUpdate,
)
from monitor_data.tools.neo4j_tools.facts import (
    neo4j_delete_axiom,
    neo4j_delete_event,
    neo4j_update_axiom,
    neo4j_update_event,
)

FACTS_MODULE = "monitor_data.tools.neo4j_tools.facts"


def _axiom_response(**over) -> AxiomResponse:
    data: dict[str, Any] = {
        "id": uuid4(),
        "universe_id": uuid4(),
        "statement": "Magic exists",
        "domain": "magic",
        "magnitude": 8,
        "scope": "global",
        "canon_level": CanonLevel.PROPOSED,
        "confidence": 0.9,
        "authority": AxiomAuthority.METAPHYSICS,
        "source_ref": None,
        "properties": None,
        "created_at": datetime.now(UTC),
    }
    data.update(over)
    return AxiomResponse(**data)


def _event_response(**over) -> EventResponse:
    data: dict[str, Any] = {
        "id": uuid4(),
        "universe_id": uuid4(),
        "title": "The bridge falls",
        "start_time": datetime.now(UTC),
        "canon_level": CanonLevel.PROPOSED,
        "knowledge_scope": KnowledgeScope.WORLD,
        "confidence": 1.0,
        "authority": Authority.GM,
        "created_at": datetime.now(UTC),
    }
    data.update(over)
    return EventResponse(**data)


# =============================================================================
# TESTS: neo4j_update_axiom
# =============================================================================


@patch(f"{FACTS_MODULE}.neo4j_get_axiom")
@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_update_axiom_statement(mock_get_client: Mock, mock_get_axiom: Mock, mock_neo4j_client: Mock):
    """Updating an axiom statement issues one write and returns the new state."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": str(uuid4())}]
    mock_neo4j_client.execute_write.return_value = [{"a": {}}]
    mock_get_axiom.return_value = _axiom_response(statement="Magic is rare")

    result = neo4j_update_axiom(uuid4(), AxiomUpdate(statement="Magic is rare"))

    assert result.statement == "Magic is rare"
    mock_neo4j_client.execute_write.assert_called_once()
    _, write_params = mock_neo4j_client.execute_write.call_args.args
    assert write_params["statement"] == "Magic is rare"


@patch(f"{FACTS_MODULE}.neo4j_get_axiom")
@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_update_axiom_no_fields_returns_current(mock_get_client: Mock, mock_get_axiom: Mock, mock_neo4j_client: Mock):
    """An empty update skips the write and returns current state."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": str(uuid4())}]
    mock_get_axiom.return_value = _axiom_response()

    result = neo4j_update_axiom(uuid4(), AxiomUpdate())

    assert result.statement == "Magic exists"
    mock_neo4j_client.execute_write.assert_not_called()


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_update_axiom_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Axiom .* not found"):
        neo4j_update_axiom(uuid4(), AxiomUpdate(statement="Nope"))


@patch(f"{FACTS_MODULE}.neo4j_get_axiom")
@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_update_axiom_properties_serialized(mock_get_client: Mock, mock_get_axiom: Mock, mock_neo4j_client: Mock):
    """Properties are serialized to a JSON string for Neo4j storage."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": str(uuid4())}]
    mock_neo4j_client.execute_write.return_value = [{"a": {}}]
    mock_get_axiom.return_value = _axiom_response(properties={"severity": "high"})

    neo4j_update_axiom(uuid4(), AxiomUpdate(properties={"severity": "high"}))

    _, write_params = mock_neo4j_client.execute_write.call_args.args
    assert write_params["properties"] == '{"severity": "high"}'


# =============================================================================
# TESTS: neo4j_delete_axiom
# =============================================================================


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_delete_axiom_success(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"canon_level": CanonLevel.PROPOSED.value}]

    result = neo4j_delete_axiom(uuid4())

    assert result["deleted"] is True
    mock_neo4j_client.execute_write.assert_called_once()


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_delete_axiom_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Axiom .* not found"):
        neo4j_delete_axiom(uuid4())


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_delete_canon_axiom_without_force(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"canon_level": CanonLevel.CANON.value}]

    with pytest.raises(ValueError, match="Cannot delete canon axiom"):
        neo4j_delete_axiom(uuid4(), force=False)

    mock_neo4j_client.execute_write.assert_not_called()


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_delete_canon_axiom_with_force(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"canon_level": CanonLevel.CANON.value}]

    result = neo4j_delete_axiom(uuid4(), force=True)

    assert result["deleted"] is True
    assert result["forced"] is True


# =============================================================================
# TESTS: neo4j_update_event
# =============================================================================


@patch(f"{FACTS_MODULE}.neo4j_get_event")
@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_update_event_title_and_magnitude(mock_get_client: Mock, mock_get_event: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": str(uuid4())}]
    mock_neo4j_client.execute_write.return_value = [{"ev": {}}]
    mock_get_event.return_value = _event_response(title="Renamed", magnitude=9)

    result = neo4j_update_event(uuid4(), EventUpdate(title="Renamed", magnitude=9))

    assert result.title == "Renamed"
    assert result.magnitude == 9
    _, write_params = mock_neo4j_client.execute_write.call_args.args
    assert write_params["title"] == "Renamed"
    assert write_params["magnitude"] == 9


@patch(f"{FACTS_MODULE}.neo4j_get_event")
@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_update_event_no_fields_returns_current(mock_get_client: Mock, mock_get_event: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": str(uuid4())}]
    mock_get_event.return_value = _event_response()

    result = neo4j_update_event(uuid4(), EventUpdate())

    assert result.title == "The bridge falls"
    mock_neo4j_client.execute_write.assert_not_called()


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_update_event_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Event .* not found"):
        neo4j_update_event(uuid4(), EventUpdate(title="Nope"))


# =============================================================================
# TESTS: neo4j_delete_event
# =============================================================================


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_delete_event_success(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"canon_level": CanonLevel.PROPOSED.value}]

    result = neo4j_delete_event(uuid4())

    assert result["deleted"] is True
    mock_neo4j_client.execute_write.assert_called_once()


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_delete_event_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Event .* not found"):
        neo4j_delete_event(uuid4())


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_delete_canon_event_without_force(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"canon_level": CanonLevel.CANON.value}]

    with pytest.raises(ValueError, match="Cannot delete canon event"):
        neo4j_delete_event(uuid4(), force=False)

    mock_neo4j_client.execute_write.assert_not_called()


@patch(f"{FACTS_MODULE}.get_neo4j_client")
def test_delete_canon_event_with_force(mock_get_client: Mock, mock_neo4j_client: Mock):
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"canon_level": CanonLevel.CANON.value}]

    result = neo4j_delete_event(uuid4(), force=True)

    assert result["deleted"] is True
    assert result["forced"] is True

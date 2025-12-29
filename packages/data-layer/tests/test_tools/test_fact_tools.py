"""
Unit tests for Neo4j fact and event operations.

Tests cover:
- neo4j_create_fact
- neo4j_get_fact
- neo4j_list_facts
- neo4j_update_fact
- neo4j_delete_fact
- neo4j_create_event
- neo4j_get_event
- neo4j_list_events
"""

from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.facts import (
    FactCreate,
    FactUpdate,
    FactFilter,
    FactType,
    EventCreate,
    EventFilter,
)
from monitor_data.schemas.base import CanonLevel, Authority
from monitor_data.tools.neo4j_tools import (
    neo4j_create_fact,
    neo4j_get_fact,
    neo4j_list_facts,
    neo4j_update_fact,
    neo4j_delete_fact,
    neo4j_create_event,
    neo4j_get_event,
    neo4j_list_events,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def fact_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample fact data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "statement": "The door is broken",
        "fact_type": FactType.STATE.value,
        "time_ref": None,
        "duration": None,
        "canon_level": CanonLevel.PROPOSED.value,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
        "replaces": None,
        "properties": None,
    }


@pytest.fixture
def event_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample event data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "scene_id": None,
        "title": "Orc attacks PC",
        "description": "A fierce orc swings its axe at the PC",
        "start_time": "2024-01-01T12:00:00",
        "end_time": "2024-01-01T12:01:00",
        "severity": 7,
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": Authority.GM.value,
        "created_at": "2024-01-01T00:00:00",
        "properties": None,
    }


@pytest.fixture
def entity_data() -> Dict[str, Any]:
    """Provide sample entity data."""
    return {
        "id": str(uuid4()),
        "universe_id": str(uuid4()),
        "name": "Test Entity",
        "entity_type": "character",
    }


# =============================================================================
# TESTS: neo4j_create_fact
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_fact")
def test_create_fact_success(
    mock_get_fact: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    fact_data: Dict[str, Any],
):
    """Test successful fact creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists check
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock fact creation
    mock_neo4j_client.execute_write.return_value = [{"f": fact_data}]

    # Mock get_fact to return created fact
    from monitor_data.schemas.facts import FactResponse
    
    mock_fact_response = FactResponse(
        id=UUID(fact_data["id"]),
        universe_id=UUID(fact_data["universe_id"]),
        statement=fact_data["statement"],
        fact_type=FactType.STATE,
        time_ref=None,
        duration=None,
        canon_level=CanonLevel.PROPOSED,
        confidence=fact_data["confidence"],
        authority=Authority.SYSTEM,
        created_at=datetime.fromisoformat(fact_data["created_at"]),
        replaces=None,
        properties=None,
    )
    mock_get_fact.return_value = mock_fact_response

    params = FactCreate(
        universe_id=UUID(universe_data["id"]),
        statement="The door is broken",
        fact_type=FactType.STATE,
    )

    result = neo4j_create_fact(params)

    assert result.statement == "The door is broken"
    assert result.universe_id == UUID(universe_data["id"])
    assert result.fact_type == FactType.STATE
    assert result.canon_level == CanonLevel.PROPOSED
    assert mock_neo4j_client.execute_read.call_count >= 1
    assert mock_neo4j_client.execute_write.call_count >= 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_fact_invalid_universe(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test fact creation with invalid universe_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = FactCreate(
        universe_id=uuid4(),
        statement="Test fact",
    )

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_create_fact(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_fact")
def test_create_fact_with_provenance(
    mock_get_fact: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    fact_data: Dict[str, Any],
):
    """Test fact creation with provenance edges (source_ids)."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock fact creation and edge creation
    mock_neo4j_client.execute_write.return_value = [{"f": fact_data}]

    source_id = uuid4()

    from monitor_data.schemas.facts import FactResponse
    
    mock_fact_response = FactResponse(
        id=UUID(fact_data["id"]),
        universe_id=UUID(fact_data["universe_id"]),
        statement="Test fact with source",
        fact_type=FactType.STATE,
        time_ref=None,
        duration=None,
        canon_level=CanonLevel.PROPOSED,
        confidence=fact_data["confidence"],
        authority=Authority.SYSTEM,
        created_at=datetime.fromisoformat(fact_data["created_at"]),
        replaces=None,
        properties=None,
        source_ids=[source_id],
    )
    mock_get_fact.return_value = mock_fact_response

    params = FactCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Test fact with source",
        source_ids=[source_id],
    )

    result = neo4j_create_fact(params)

    assert result.statement == "Test fact with source"
    assert source_id in result.source_ids
    # Verify edge creation was called
    assert mock_neo4j_client.execute_write.call_count >= 2  # create + edge


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_fact")
def test_create_fact_with_entities(
    mock_get_fact: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    entity_data: Dict[str, Any],
    fact_data: Dict[str, Any],
):
    """Test fact creation with entity references (INVOLVES edges)."""
    mock_get_client.return_value = mock_neo4j_client

    entity_id = UUID(entity_data["id"])

    # Mock universe exists, then entity exists
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # universe check
        [{"id": entity_data["id"]}],  # entity check
    ]

    # Mock fact creation and edge creation
    mock_neo4j_client.execute_write.return_value = [{"f": fact_data}]

    from monitor_data.schemas.facts import FactResponse
    
    mock_fact_response = FactResponse(
        id=UUID(fact_data["id"]),
        universe_id=UUID(fact_data["universe_id"]),
        statement="Test fact with entity",
        fact_type=FactType.STATE,
        time_ref=None,
        duration=None,
        canon_level=CanonLevel.PROPOSED,
        confidence=fact_data["confidence"],
        authority=Authority.SYSTEM,
        created_at=datetime.fromisoformat(fact_data["created_at"]),
        replaces=None,
        properties=None,
        entity_ids=[entity_id],
    )
    mock_get_fact.return_value = mock_fact_response

    params = FactCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Test fact with entity",
        entity_ids=[entity_id],
    )

    result = neo4j_create_fact(params)

    assert result.statement == "Test fact with entity"
    assert entity_id in result.entity_ids
    # Verify INVOLVES edge was created
    assert mock_neo4j_client.execute_write.call_count >= 2


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_fact")
def test_create_fact_with_retcon(
    mock_get_fact: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    fact_data: Dict[str, Any],
):
    """Test fact creation that replaces (retcons) another fact."""
    mock_get_client.return_value = mock_neo4j_client

    old_fact_id = uuid4()

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock fact creation and REPLACES edge
    mock_neo4j_client.execute_write.return_value = [{"f": fact_data}]

    from monitor_data.schemas.facts import FactResponse
    
    mock_fact_response = FactResponse(
        id=UUID(fact_data["id"]),
        universe_id=UUID(fact_data["universe_id"]),
        statement=fact_data["statement"],
        fact_type=FactType.STATE,
        time_ref=None,
        duration=None,
        canon_level=CanonLevel.PROPOSED,
        confidence=fact_data["confidence"],
        authority=Authority.SYSTEM,
        created_at=datetime.fromisoformat(fact_data["created_at"]),
        replaces=old_fact_id,
        properties=None,
    )
    mock_get_fact.return_value = mock_fact_response

    params = FactCreate(
        universe_id=UUID(universe_data["id"]),
        statement="New fact replacing old one",
        replaces=old_fact_id,
    )

    result = neo4j_create_fact(params)

    assert result.replaces == old_fact_id
    # Verify REPLACES edge was created
    assert mock_neo4j_client.execute_write.call_count >= 2


# =============================================================================
# TESTS: neo4j_get_fact
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_fact_with_relationships(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    fact_data: Dict[str, Any],
):
    """Test getting fact with all relationships and provenance chain."""
    mock_get_client.return_value = mock_neo4j_client

    entity_id = str(uuid4())
    source_id = str(uuid4())
    scene_id = str(uuid4())

    # Mock query result with relationships
    mock_neo4j_client.execute_read.return_value = [
        {
            "f": fact_data,
            "entity_ids": [entity_id],
            "source_ids": [source_id],
            "scene_ids": [scene_id],
        }
    ]

    result = neo4j_get_fact(UUID(fact_data["id"]))

    assert result is not None
    assert result.id == UUID(fact_data["id"])
    assert result.statement == fact_data["statement"]
    assert len(result.entity_ids) == 1
    assert len(result.source_ids) == 1
    assert len(result.scene_ids) == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_fact_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test getting non-existent fact returns None."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_fact(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_list_facts
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_facts_by_entity(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    fact_data: Dict[str, Any],
):
    """Test listing facts filtered by entity_id."""
    mock_get_client.return_value = mock_neo4j_client

    entity_id = uuid4()

    # Mock query result
    mock_neo4j_client.execute_read.return_value = [
        {
            "f": fact_data,
            "entity_ids": [str(entity_id)],
            "source_ids": [],
            "scene_ids": [],
        }
    ]

    filters = FactFilter(entity_id=entity_id)
    results = neo4j_list_facts(filters)

    assert len(results) == 1
    assert results[0].id == UUID(fact_data["id"])
    assert entity_id in results[0].entity_ids


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_facts_by_canon_level(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    fact_data: Dict[str, Any],
):
    """Test listing facts filtered by canon_level."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock query result
    mock_neo4j_client.execute_read.return_value = [
        {
            "f": fact_data,
            "entity_ids": [],
            "source_ids": [],
            "scene_ids": [],
        }
    ]

    filters = FactFilter(canon_level=CanonLevel.PROPOSED)
    results = neo4j_list_facts(filters)

    assert len(results) == 1
    assert results[0].canon_level == CanonLevel.PROPOSED


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_facts_by_fact_type(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    fact_data: Dict[str, Any],
):
    """Test listing facts filtered by fact_type."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock query result
    mock_neo4j_client.execute_read.return_value = [
        {
            "f": fact_data,
            "entity_ids": [],
            "source_ids": [],
            "scene_ids": [],
        }
    ]

    filters = FactFilter(fact_type=FactType.STATE)
    results = neo4j_list_facts(filters)

    assert len(results) == 1
    assert results[0].fact_type == FactType.STATE


# =============================================================================
# TESTS: neo4j_update_fact
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_fact")
def test_update_fact_canon_level(
    mock_get_fact: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    fact_data: Dict[str, Any],
):
    """Test updating fact canon_level (proposed → canon transition)."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock fact exists
    mock_neo4j_client.execute_read.return_value = [{"f": fact_data}]

    # Mock update
    updated_fact = fact_data.copy()
    updated_fact["canon_level"] = CanonLevel.CANON.value
    mock_neo4j_client.execute_write.return_value = [{"f": updated_fact}]

    from monitor_data.schemas.facts import FactResponse
    
    mock_fact_response = FactResponse(
        id=UUID(fact_data["id"]),
        universe_id=UUID(fact_data["universe_id"]),
        statement=fact_data["statement"],
        fact_type=FactType.STATE,
        time_ref=None,
        duration=None,
        canon_level=CanonLevel.CANON,
        confidence=fact_data["confidence"],
        authority=Authority.SYSTEM,
        created_at=datetime.fromisoformat(fact_data["created_at"]),
        replaces=None,
        properties=None,
    )
    mock_get_fact.return_value = mock_fact_response

    params = FactUpdate(canon_level=CanonLevel.CANON)
    result = neo4j_update_fact(UUID(fact_data["id"]), params)

    assert result.canon_level == CanonLevel.CANON
    mock_neo4j_client.execute_write.assert_called_once()


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_fact_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test updating non-existent fact raises error."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = FactUpdate(statement="Updated statement")

    with pytest.raises(ValueError, match="Fact .* not found"):
        neo4j_update_fact(uuid4(), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_fact")
def test_update_fact_statement(
    mock_get_fact: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    fact_data: Dict[str, Any],
):
    """Test updating fact statement."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock fact exists
    mock_neo4j_client.execute_read.return_value = [{"f": fact_data}]

    # Mock update
    updated_fact = fact_data.copy()
    updated_fact["statement"] = "Updated statement"
    mock_neo4j_client.execute_write.return_value = [{"f": updated_fact}]

    from monitor_data.schemas.facts import FactResponse
    
    mock_fact_response = FactResponse(
        id=UUID(fact_data["id"]),
        universe_id=UUID(fact_data["universe_id"]),
        statement="Updated statement",
        fact_type=FactType.STATE,
        time_ref=None,
        duration=None,
        canon_level=CanonLevel.PROPOSED,
        confidence=fact_data["confidence"],
        authority=Authority.SYSTEM,
        created_at=datetime.fromisoformat(fact_data["created_at"]),
        replaces=None,
        properties=None,
    )
    mock_get_fact.return_value = mock_fact_response

    params = FactUpdate(statement="Updated statement")
    result = neo4j_update_fact(UUID(fact_data["id"]), params)

    assert result.statement == "Updated statement"


# =============================================================================
# TESTS: neo4j_delete_fact
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_confirmed_fact_without_force(
    mock_get_client: Mock, mock_neo4j_client: Mock, fact_data: Dict[str, Any]
):
    """Test deleting canon fact without force raises error."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock fact exists and is canon
    canon_fact = fact_data.copy()
    canon_fact["canon_level"] = CanonLevel.CANON.value
    mock_neo4j_client.execute_read.return_value = [
        {"canon_level": CanonLevel.CANON.value}
    ]

    with pytest.raises(ValueError, match="Cannot delete canon fact"):
        neo4j_delete_fact(UUID(fact_data["id"]), force=False)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_confirmed_fact_with_force(
    mock_get_client: Mock, mock_neo4j_client: Mock, fact_data: Dict[str, Any]
):
    """Test deleting canon fact with force succeeds."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock fact exists and is canon
    mock_neo4j_client.execute_read.return_value = [
        {"canon_level": CanonLevel.CANON.value}
    ]
    mock_neo4j_client.execute_write.return_value = []

    result = neo4j_delete_fact(UUID(fact_data["id"]), force=True)

    assert result["deleted"] is True
    assert result["forced"] is True
    assert result["canon_level"] == CanonLevel.CANON.value


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_proposed_fact(
    mock_get_client: Mock, mock_neo4j_client: Mock, fact_data: Dict[str, Any]
):
    """Test deleting proposed fact succeeds without force."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock fact exists and is proposed
    mock_neo4j_client.execute_read.return_value = [
        {"canon_level": CanonLevel.PROPOSED.value}
    ]
    mock_neo4j_client.execute_write.return_value = []

    result = neo4j_delete_fact(UUID(fact_data["id"]), force=False)

    assert result["deleted"] is True
    assert result["forced"] is False


# =============================================================================
# TESTS: neo4j_create_event
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_event")
def test_create_event_success(
    mock_get_event: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    event_data: Dict[str, Any],
):
    """Test successful event creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock event creation
    mock_neo4j_client.execute_write.return_value = [{"ev": event_data}]

    from monitor_data.schemas.facts import EventResponse
    
    mock_event_response = EventResponse(
        id=UUID(event_data["id"]),
        universe_id=UUID(event_data["universe_id"]),
        scene_id=None,
        title=event_data["title"],
        description=event_data["description"],
        start_time=datetime.fromisoformat(event_data["start_time"]),
        end_time=datetime.fromisoformat(event_data["end_time"]),
        severity=event_data["severity"],
        canon_level=CanonLevel.CANON,
        confidence=event_data["confidence"],
        authority=Authority.GM,
        created_at=datetime.fromisoformat(event_data["created_at"]),
        properties=None,
    )
    mock_get_event.return_value = mock_event_response

    params = EventCreate(
        universe_id=UUID(universe_data["id"]),
        title="Orc attacks PC",
        description="A fierce orc swings its axe at the PC",
        start_time=datetime.fromisoformat(event_data["start_time"]),
        end_time=datetime.fromisoformat(event_data["end_time"]),
        severity=7,
        canon_level=CanonLevel.CANON,
        authority=Authority.GM,
    )

    result = neo4j_create_event(params)

    assert result.title == "Orc attacks PC"
    assert result.severity == 7
    assert mock_neo4j_client.execute_write.call_count >= 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_event")
def test_create_event_with_timeline(
    mock_get_event: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    event_data: Dict[str, Any],
):
    """Test event creation with timeline ordering (AFTER, BEFORE edges)."""
    mock_get_client.return_value = mock_neo4j_client

    after_event_id = uuid4()
    before_event_id = uuid4()

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock event creation and timeline edge creation
    mock_neo4j_client.execute_write.return_value = [{"ev": event_data}]

    from monitor_data.schemas.facts import EventResponse
    
    mock_event_response = EventResponse(
        id=UUID(event_data["id"]),
        universe_id=UUID(event_data["universe_id"]),
        scene_id=None,
        title=event_data["title"],
        description=event_data["description"],
        start_time=datetime.fromisoformat(event_data["start_time"]),
        end_time=datetime.fromisoformat(event_data["end_time"]),
        severity=event_data["severity"],
        canon_level=CanonLevel.CANON,
        confidence=event_data["confidence"],
        authority=Authority.GM,
        created_at=datetime.fromisoformat(event_data["created_at"]),
        properties=None,
        timeline_after=[after_event_id],
        timeline_before=[before_event_id],
    )
    mock_get_event.return_value = mock_event_response

    params = EventCreate(
        universe_id=UUID(universe_data["id"]),
        title="Event with timeline",
        start_time=datetime.now(timezone.utc),
        timeline_after=[after_event_id],
        timeline_before=[before_event_id],
    )

    result = neo4j_create_event(params)

    assert after_event_id in result.timeline_after
    assert before_event_id in result.timeline_before
    # Verify timeline edges were created (1 create + 2 edges)
    assert mock_neo4j_client.execute_write.call_count >= 3


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_event")
def test_create_event_with_causal(
    mock_get_event: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    event_data: Dict[str, Any],
):
    """Test event creation with causal relationships (CAUSES edges)."""
    mock_get_client.return_value = mock_neo4j_client

    caused_event_id = uuid4()

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock event creation and CAUSES edge creation
    mock_neo4j_client.execute_write.return_value = [{"ev": event_data}]

    from monitor_data.schemas.facts import EventResponse
    
    mock_event_response = EventResponse(
        id=UUID(event_data["id"]),
        universe_id=UUID(event_data["universe_id"]),
        scene_id=None,
        title=event_data["title"],
        description=event_data["description"],
        start_time=datetime.fromisoformat(event_data["start_time"]),
        end_time=datetime.fromisoformat(event_data["end_time"]),
        severity=event_data["severity"],
        canon_level=CanonLevel.CANON,
        confidence=event_data["confidence"],
        authority=Authority.GM,
        created_at=datetime.fromisoformat(event_data["created_at"]),
        properties=None,
        causes=[caused_event_id],
    )
    mock_get_event.return_value = mock_event_response

    params = EventCreate(
        universe_id=UUID(universe_data["id"]),
        title="Causal event",
        start_time=datetime.now(timezone.utc),
        causes=[caused_event_id],
    )

    result = neo4j_create_event(params)

    assert caused_event_id in result.causes
    # Verify CAUSES edge was created
    assert mock_neo4j_client.execute_write.call_count >= 2


# =============================================================================
# TESTS: neo4j_get_event
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_event_with_relationships(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    event_data: Dict[str, Any],
):
    """Test getting event with all relationships."""
    mock_get_client.return_value = mock_neo4j_client

    entity_id = str(uuid4())
    source_id = str(uuid4())

    # Mock query result with relationships
    mock_neo4j_client.execute_read.return_value = [
        {
            "ev": event_data,
            "entity_ids": [entity_id],
            "source_ids": [source_id],
            "timeline_after": [],
            "timeline_before": [],
            "causes": [],
        }
    ]

    result = neo4j_get_event(UUID(event_data["id"]))

    assert result is not None
    assert result.id == UUID(event_data["id"])
    assert result.title == event_data["title"]
    assert len(result.entity_ids) == 1


# =============================================================================
# TESTS: neo4j_list_events
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_events_by_scene(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    event_data: Dict[str, Any],
):
    """Test listing events filtered by scene_id."""
    mock_get_client.return_value = mock_neo4j_client

    scene_id = uuid4()
    event_with_scene = event_data.copy()
    event_with_scene["scene_id"] = str(scene_id)

    # Mock query result
    mock_neo4j_client.execute_read.return_value = [
        {
            "ev": event_with_scene,
            "entity_ids": [],
            "source_ids": [],
            "timeline_after": [],
            "timeline_before": [],
            "causes": [],
        }
    ]

    filters = EventFilter(scene_id=scene_id)
    results = neo4j_list_events(filters)

    assert len(results) == 1
    assert results[0].scene_id == scene_id


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_events_by_time_range(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    event_data: Dict[str, Any],
):
    """Test listing events filtered by time range."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock query result
    mock_neo4j_client.execute_read.return_value = [
        {
            "ev": event_data,
            "entity_ids": [],
            "source_ids": [],
            "timeline_after": [],
            "timeline_before": [],
            "causes": [],
        }
    ]

    start_after = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    start_before = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

    filters = EventFilter(start_after=start_after, start_before=start_before)
    results = neo4j_list_events(filters)

    assert len(results) == 1

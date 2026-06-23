"""Tests for traversal-oriented Neo4j read helpers."""

from __future__ import annotations

from unittest.mock import Mock, patch
from uuid import uuid4

from monitor_data.tools.neo4j_tools import (
    neo4j_find_ranked_paths,
    neo4j_get_entities_by_scene,
    neo4j_get_entity_neighborhood,
    neo4j_get_scene_relevant_entities,
)


# neo4j_get_entities_by_scene tests
@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entities_by_scene_returns_rows(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    scene_id = uuid4()
    mock_client.execute_read.return_value = [
        {
            "id": str(uuid4()),
            "name": "Captain Ilya",
            "entity_type": "character",
            "description": "A hardened officer",
            "canon_level": "canon",
        }
    ]

    rows = neo4j_get_entities_by_scene(scene_id, limit=10)

    assert len(rows) == 1
    assert rows[0]["name"] == "Captain Ilya"


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entities_by_scene_returns_empty_when_no_entities(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    scene_id = uuid4()
    mock_client.execute_read.return_value = []

    rows = neo4j_get_entities_by_scene(scene_id, limit=10)

    assert rows == []


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entities_by_scene_returns_multiple_entities(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    scene_id = uuid4()
    mock_client.execute_read.return_value = [
        {
            "id": str(uuid4()),
            "name": "Captain Ilya",
            "entity_type": "character",
            "description": "A hardened officer",
            "canon_level": "canon",
        },
        {
            "id": str(uuid4()),
            "name": "Prince Marcel",
            "entity_type": "character",
            "description": "A cunning noble",
            "canon_level": "canon",
        },
    ]

    rows = neo4j_get_entities_by_scene(scene_id, limit=10)

    assert len(rows) == 2
    assert rows[0]["name"] == "Captain Ilya"
    assert rows[1]["name"] == "Prince Marcel"


# neo4j_get_scene_relevant_entities tests
@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_scene_relevant_entities_is_alias(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    scene_id = uuid4()
    mock_client.execute_read.return_value = []

    rows = neo4j_get_scene_relevant_entities(scene_id, limit=5)

    assert rows == []


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_scene_relevant_entities_calls_underlying_function(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    scene_id = uuid4()
    mock_client.execute_read.return_value = [
        {
            "id": str(uuid4()),
            "name": "Captain Ilya",
            "entity_type": "character",
            "description": "A hardened officer",
            "canon_level": "canon",
        }
    ]

    rows = neo4j_get_scene_relevant_entities(scene_id, limit=10)

    assert len(rows) == 1
    assert rows[0]["name"] == "Captain Ilya"
    mock_client.execute_read.assert_called_once()


# neo4j_get_entity_neighborhood tests
@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entity_neighborhood_filters_by_direction_and_rel_types(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    entity_id = uuid4()

    mock_client.execute_read.return_value = [
        {
            "relationship_id": 77,
            "rel_type": "KNOWS",
            "properties": {"strength": 2},
            "from_entity_id": str(entity_id),
            "to_entity_id": str(uuid4()),
            "counterpart_entity_id": str(uuid4()),
            "counterpart_name": "Prince Marcel",
            "counterpart_entity_type": "character",
            "counterpart_canon_level": "canon",
        }
    ]

    rows = neo4j_get_entity_neighborhood(
        entity_id=entity_id,
        rel_types=["KNOWS"],
        direction="outgoing",
        limit=12,
    )

    assert len(rows) == 1
    assert rows[0]["rel_type"] == "KNOWS"


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entity_neighborhood_incoming_direction(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    entity_id = uuid4()

    mock_client.execute_read.return_value = [
        {
            "relationship_id": 78,
            "rel_type": "OWNS",
            "properties": {},
            "from_entity_id": str(uuid4()),
            "to_entity_id": str(entity_id),
            "counterpart_entity_id": str(uuid4()),
            "counterpart_name": "Prince Marcel",
            "counterpart_entity_type": "character",
            "counterpart_canon_level": "canon",
        }
    ]

    rows = neo4j_get_entity_neighborhood(
        entity_id=entity_id,
        rel_types=["OWNS"],
        direction="incoming",
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["rel_type"] == "OWNS"
    assert rows[0]["to_entity_id"] == str(entity_id)


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entity_neighborhood_outgoing_direction(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    entity_id = uuid4()

    mock_client.execute_read.return_value = [
        {
            "relationship_id": 79,
            "rel_type": "KNOWS",
            "properties": {},
            "from_entity_id": str(entity_id),
            "to_entity_id": str(uuid4()),
            "counterpart_entity_id": str(uuid4()),
            "counterpart_name": "Captain Ilya",
            "counterpart_entity_type": "character",
            "counterpart_canon_level": "canon",
        }
    ]

    rows = neo4j_get_entity_neighborhood(
        entity_id=entity_id,
        rel_types=["KNOWS"],
        direction="outgoing",
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["rel_type"] == "KNOWS"
    assert rows[0]["from_entity_id"] == str(entity_id)


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entity_neighborhood_both_direction_default(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    entity_id = uuid4()

    mock_client.execute_read.return_value = [
        {
            "relationship_id": 80,
            "rel_type": "KNOWS",
            "properties": {},
            "from_entity_id": str(entity_id),
            "to_entity_id": str(uuid4()),
            "counterpart_entity_id": str(uuid4()),
            "counterpart_name": "Captain Ilya",
            "counterpart_entity_type": "character",
            "counterpart_canon_level": "canon",
        }
    ]

    rows = neo4j_get_entity_neighborhood(
        entity_id=entity_id,
        rel_types=["KNOWS"],
        direction="both",
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["rel_type"] == "KNOWS"


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entity_neighborhood_no_rel_types_filter(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    entity_id = uuid4()

    mock_client.execute_read.return_value = [
        {
            "relationship_id": 81,
            "rel_type": "KNOWS",
            "properties": {},
            "from_entity_id": str(entity_id),
            "to_entity_id": str(uuid4()),
            "counterpart_entity_id": str(uuid4()),
            "counterpart_name": "Captain Ilya",
            "counterpart_entity_type": "character",
            "counterpart_canon_level": "canon",
        }
    ]

    rows = neo4j_get_entity_neighborhood(
        entity_id=entity_id,
        rel_types=None,
        direction="both",
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["rel_type"] == "KNOWS"


# neo4j_find_ranked_paths tests
@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_find_ranked_paths_returns_path_rows(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    seed_id = str(uuid4())
    mock_client.execute_read.return_value = [
        {
            "seed_entity_id": seed_id,
            "seed_name": "Captain Ilya",
            "target_entity_id": str(uuid4()),
            "target_name": "Prince Marcel",
            "rel_chain": ["KNOWS"],
            "hop_count": 1,
        }
    ]

    rows = neo4j_find_ranked_paths(
        seed_entity_ids=[seed_id],
        rel_types=["KNOWS"],
        hop_limit=2,
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["rel_chain"] == ["KNOWS"]


def test_find_ranked_paths_empty_seed_short_circuits() -> None:
    assert neo4j_find_ranked_paths(seed_entity_ids=[], rel_types=["KNOWS"]) == []


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_find_ranked_paths_multiple_hops(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    seed_id = str(uuid4())
    mock_client.execute_read.return_value = [
        {
            "seed_entity_id": seed_id,
            "seed_name": "Captain Ilya",
            "target_entity_id": str(uuid4()),
            "target_name": "Prince Marcel",
            "rel_chain": ["KNOWS", "OWNS"],
            "hop_count": 2,
        }
    ]

    rows = neo4j_find_ranked_paths(
        seed_entity_ids=[seed_id],
        rel_types=["KNOWS", "OWNS"],
        hop_limit=2,
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["hop_count"] == 2
    assert rows[0]["rel_chain"] == ["KNOWS", "OWNS"]


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_find_ranked_paths_multiple_seed_ids(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    seed_id_1 = str(uuid4())
    seed_id_2 = str(uuid4())
    mock_client.execute_read.return_value = [
        {
            "seed_entity_id": seed_id_1,
            "seed_name": "Captain Ilya",
            "target_entity_id": str(uuid4()),
            "target_name": "Prince Marcel",
            "rel_chain": ["KNOWS"],
            "hop_count": 1,
        },
        {
            "seed_entity_id": seed_id_2,
            "seed_name": "Prince Marcel",
            "target_entity_id": str(uuid4()),
            "target_name": "Queen Elena",
            "rel_chain": ["KNOWS"],
            "hop_count": 1,
        },
    ]

    rows = neo4j_find_ranked_paths(
        seed_entity_ids=[seed_id_1, seed_id_2],
        rel_types=["KNOWS"],
        hop_limit=2,
        limit=10,
    )

    assert len(rows) == 2
    assert rows[0]["seed_name"] == "Captain Ilya"
    assert rows[1]["seed_name"] == "Prince Marcel"


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_find_ranked_paths_respects_hop_limit(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    seed_id = str(uuid4())
    mock_client.execute_read.return_value = [
        {
            "seed_entity_id": seed_id,
            "seed_name": "Captain Ilya",
            "target_entity_id": str(uuid4()),
            "target_name": "Prince Marcel",
            "rel_chain": ["KNOWS"],
            "hop_count": 1,
        }
    ]

    rows = neo4j_find_ranked_paths(
        seed_entity_ids=[seed_id],
        rel_types=["KNOWS"],
        hop_limit=1,
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["hop_count"] == 1


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_find_ranked_paths_returns_empty_when_no_matches(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    seed_id = str(uuid4())
    mock_client.execute_read.return_value = []

    rows = neo4j_find_ranked_paths(
        seed_entity_ids=[seed_id],
        rel_types=["KNOWS"],
        hop_limit=2,
        limit=10,
    )

    assert rows == []


# =============================================================================
# ADDITIONAL TESTS FOR neo4j_get_entities_by_scene
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entities_by_scene_respects_limit(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    scene_id = uuid4()

    all_entities = [
        {
            "id": str(uuid4()),
            "name": f"Character {i}",
            "entity_type": "character",
            "description": f"A character {i}",
            "canon_level": "canon",
        }
        for i in range(10)
    ]

    def mock_execute_read(query, params):
        limit = params.get("limit", 10)
        return all_entities[:limit]

    mock_client.execute_read.side_effect = mock_execute_read

    rows = neo4j_get_entities_by_scene(scene_id, limit=5)

    assert len(rows) == 5


# =============================================================================
# ADDITIONAL TESTS FOR neo4j_get_entity_neighborhood
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entity_neighborhood_includes_properties(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    entity_id = uuid4()

    mock_client.execute_read.return_value = [
        {
            "relationship_id": 82,
            "rel_type": "KNOWS",
            "properties": {"strength": 5, "since": "2020"},
            "from_entity_id": str(entity_id),
            "to_entity_id": str(uuid4()),
            "counterpart_entity_id": str(uuid4()),
            "counterpart_name": "Prince Marcel",
            "counterpart_entity_type": "character",
            "counterpart_canon_level": "canon",
        }
    ]

    rows = neo4j_get_entity_neighborhood(
        entity_id=entity_id,
        rel_types=["KNOWS"],
        direction="outgoing",
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["properties"] == {"strength": 5, "since": "2020"}


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_get_entity_neighborhood_returns_empty_when_no_relationships(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client
    entity_id = uuid4()

    mock_client.execute_read.return_value = []

    rows = neo4j_get_entity_neighborhood(
        entity_id=entity_id,
        rel_types=["KNOWS"],
        direction="both",
        limit=10,
    )

    assert rows == []


# =============================================================================
# ADDITIONAL TESTS FOR neo4j_find_ranked_paths
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_find_ranked_paths_uses_rel_type_filter(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    seed_id = str(uuid4())
    mock_client.execute_read.return_value = [
        {
            "seed_entity_id": seed_id,
            "seed_name": "Captain Ilya",
            "target_entity_id": str(uuid4()),
            "target_name": "Prince Marcel",
            "rel_chain": ["KNOWS"],
            "hop_count": 1,
        }
    ]

    rows = neo4j_find_ranked_paths(
        seed_entity_ids=[seed_id],
        rel_types=["KNOWS", "OWNS"],
        hop_limit=2,
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["rel_chain"] == ["KNOWS"]


@patch("monitor_data.tools.neo4j_tools.traversal.get_neo4j_client")
def test_find_ranked_paths_sorts_by_hop_count(mock_get_client: Mock) -> None:
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    seed_id = str(uuid4())
    target_id_1 = str(uuid4())
    target_id_2 = str(uuid4())

    mock_client.execute_read.return_value = [
        {
            "seed_entity_id": seed_id,
            "seed_name": "Captain Ilya",
            "target_entity_id": target_id_1,
            "target_name": "Prince Marcel",
            "rel_chain": ["KNOWS"],
            "hop_count": 1,
        },
        {
            "seed_entity_id": seed_id,
            "seed_name": "Captain Ilya",
            "target_entity_id": target_id_2,
            "target_name": "Queen Elena",
            "rel_chain": ["KNOWS", "OWNS"],
            "hop_count": 2,
        },
    ]

    rows = neo4j_find_ranked_paths(
        seed_entity_ids=[seed_id],
        rel_types=["KNOWS", "OWNS"],
        hop_limit=2,
        limit=10,
    )

    assert len(rows) == 2
    assert rows[0]["hop_count"] == 1
    assert rows[1]["hop_count"] == 2

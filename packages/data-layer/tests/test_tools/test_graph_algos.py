"""Unit tests for the GDS graph-analytics tools (neo4j_tools/graph_algos.py).

Hermetic: the Neo4j client is a MagicMock; we assert on the Cypher shapes and
parameter clamping, not on a live database. GDS availability against a real
Neo4j+GDS container is covered by integration runs (RUN_INTEGRATION=1).
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.middleware.auth import AUTHORITY_MATRIX
from monitor_data.tools.neo4j_tools import graph_algos as tools


@pytest.fixture
def client():
    mock = MagicMock()
    with patch.object(tools, "get_neo4j_client", return_value=mock):
        yield mock


def _verify_row() -> list[dict]:
    """verify_node_exists consumes one execute_read before the tool runs."""
    return [{"id": "universe-exists"}]


def _wcc_rows() -> list[dict]:
    # nodeId 1,2 in component 0; nodeId 3 alone in component 1 (orphan)
    return [
        {"nodeId": 1, "componentId": 0},
        {"nodeId": 2, "componentId": 0},
        {"nodeId": 3, "componentId": 1},
    ]


def _lookup_rows() -> list[dict]:
    return [
        {"node_id": 1, "entity_id": "e1", "name": "Aldric"},
        {"node_id": 2, "entity_id": "e2", "name": "Bryn"},
        {"node_id": 3, "entity_id": "e3", "name": "Orphan"},
    ]


@pytest.mark.unit
def test_connected_components_projects_scopes_and_drops(client):
    uid = str(uuid4())
    client.execute_read.side_effect = [_verify_row(), _wcc_rows(), _lookup_rows()]
    result = tools.neo4j_universe_connected_components(uid)

    write_queries = [c.args[0] for c in client.execute_write.call_args_list]
    assert any("gds.graph.project.cypher" in q for q in write_queries)
    # Projection is scoped to the universe and dropped afterwards.
    project = next(q for q in write_queries if "gds.graph.project.cypher" in q)
    assert f"n.universe_id = '{uid}'" in project
    assert any("gds.graph.drop" in q for q in write_queries)

    read_queries = [c.args[0] for c in client.execute_read.call_args_list]
    assert any("gds.wcc.stream" in q for q in read_queries)

    assert result["component_count"] == 2
    assert result["orphan_count"] == 1
    assert result["orphans"] == [{"entity_id": "e3", "name": "Orphan"}]
    assert result["largest_components"][0]["size"] == 2


@pytest.mark.unit
def test_connected_components_rejects_bad_universe_id(client):
    with pytest.raises(ValueError):
        tools.neo4j_universe_connected_components("not-a-uuid")
    client.execute_write.assert_not_called()


@pytest.mark.unit
def test_node_similarity_maps_pairs_and_clamps(client):
    uid = str(uuid4())
    sim_rows = [{"node1": 1, "node2": 2, "similarity": 0.83}]
    client.execute_read.side_effect = [_verify_row(), sim_rows, _lookup_rows()]
    pairs = tools.neo4j_universe_node_similarity(uid, similarity_cutoff=1.5, top_k=999)

    algo_call = client.execute_read.call_args_list[1]
    assert "gds.nodeSimilarity.stream" in algo_call.args[0]
    # cutoff clamped to 1.0, top_k clamped to 100
    assert algo_call.args[1]["cutoff"] == 1.0
    assert algo_call.args[1]["top_k"] == 100

    assert pairs == [
        {
            "entity_a": "e1",
            "name_a": "Aldric",
            "entity_b": "e2",
            "name_b": "Bryn",
            "similarity": 0.83,
        }
    ]


@pytest.mark.unit
def test_centrality_kinds_and_invalid_kind(client):
    uid = str(uuid4())
    for kind, proc in [("degree", "gds.degree"), ("betweenness", "gds.betweenness"), ("pagerank", "gds.pageRank")]:
        client.reset_mock()
        client.execute_read.side_effect = [_verify_row(), [{"nodeId": 1, "score": 0.5}], _lookup_rows()]
        result = tools.neo4j_universe_centrality(uid, kind=kind, limit=5000)
        query = client.execute_read.call_args_list[1].args[0]
        assert proc in query
        assert client.execute_read.call_args_list[1].args[1]["limit"] == 100  # clamped
        assert result[0]["kind"] == kind
        assert result[0]["entity_id"] == "e1"

    with pytest.raises(ValueError, match="kind"):
        tools.neo4j_universe_centrality(uid, kind="closeness-ish")


@pytest.mark.unit
def test_shortest_path_returns_path_and_respects_max_hops(client):
    uid = str(uuid4())
    client.execute_read.side_effect = [
        [{"source": 10, "target": 12}],  # endpoint resolution
        _verify_row(),  # universe verify inside _universe_graph
        [{"nodeIds": [10, 11, 12], "totalCost": 2.0}],  # dijkstra
        [  # lookup
            {"node_id": 10, "entity_id": "a", "name": "A"},
            {"node_id": 11, "entity_id": "b", "name": "B"},
            {"node_id": 12, "entity_id": "c", "name": "C"},
        ],
    ]
    result = tools.neo4j_shortest_path(uid, "a", "c", max_hops=10)
    assert result is not None
    assert result["hops"] == 2
    assert [p["entity_id"] for p in result["path"]] == ["a", "b", "c"]
    dijkstra = client.execute_read.call_args_list[2]
    assert "gds.shortestPath.dijkstra.stream" in dijkstra.args[0]

    # Same path but max_hops=1 → None
    client.execute_read.side_effect = [
        [{"source": 10, "target": 12}],
        _verify_row(),
        [{"nodeIds": [10, 11, 12], "totalCost": 2.0}],
        [{"node_id": 10, "entity_id": "a", "name": "A"}],
    ]
    assert tools.neo4j_shortest_path(uid, "a", "c", max_hops=1) is None


@pytest.mark.unit
def test_shortest_path_unknown_endpoints_returns_none(client):
    uid = str(uuid4())
    client.execute_read.return_value = []  # no such entities
    assert tools.neo4j_shortest_path(uid, "x", "y") is None


@pytest.mark.unit
def test_graph_algorithms_available_handles_missing_plugin(client):
    client.execute_read.side_effect = Exception("no procedure gds.list")
    assert tools.neo4j_graph_algorithms_available() == {"available": False, "procedures": 0}

    client.execute_read.side_effect = None
    client.execute_read.side_effect = [[{"procedures": 432}], [{"version": "2.6.8"}]]
    result = tools.neo4j_graph_algorithms_available()
    assert result == {"available": True, "procedures": 432, "version": "2.6.8"}


@pytest.mark.unit
def test_new_tools_are_read_only_in_authority_matrix():
    for name in (
        "neo4j_universe_connected_components",
        "neo4j_universe_node_similarity",
        "neo4j_universe_centrality",
        "neo4j_shortest_path",
        "neo4j_graph_algorithms_available",
    ):
        assert AUTHORITY_MATRIX[name] == ["*"], name

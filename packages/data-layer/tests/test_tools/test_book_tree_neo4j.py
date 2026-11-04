"""Storing a book's structure in Neo4j: repeatable, CanonKeeper-only, and never canon (I-17)."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from monitor_data.invariants.canon_keeper import CANON_KEEPER_WRITE_TOOLS, SHARED_NEO4J_WRITE_TOOLS
from monitor_data.middleware.auth import AUTHORITY_MATRIX
from monitor_data.schemas.book_graph import BookNode, BookNodeKind, BookTree, DecompositionReport
from monitor_data.tools.neo4j_tools import book_tree as tools


def _tree(paragraphs: int = 2) -> BookTree:
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    for i in range(paragraphs):
        nodes.append(BookNode(id=f"p{i}", doc_id="d", kind=BookNodeKind.PARAGRAPH, parent_id="root", seq=i + 1, text="T", page_start=0, page_end=0))
    return BookTree(doc_id="d", title="T", decomposer_version="5", content_hash="x", nodes=nodes, report=DecompositionReport())


@pytest.fixture
def client():
    mock = MagicMock()
    with patch.object(tools, "get_neo4j_client", return_value=mock):
        yield mock


@pytest.mark.unit
def test_merge_writes_nodes_links_and_the_source_link(client):
    source = uuid4()
    assert tools.neo4j_merge_book_tree(_tree(), source) == 3
    calls = [c for c in client.execute_write.call_args_list if len(c.args) > 1]
    assert len(calls[0].args[1]["rows"]) == 3
    assert calls[1].args[1]["links"] == [{"id": "p0", "parent_id": "root"}, {"id": "p1", "parent_id": "root"}]
    assert calls[2].args[1] == {"book_id": "root", "source_id": str(source)}


@pytest.mark.unit
def test_every_write_is_repeatable_and_stays_off_canon_labels(client):
    tools.neo4j_merge_book_tree(_tree(), uuid4())
    for call in client.execute_write.call_args_list:
        query = call.args[0]
        if len(call.args) > 1:
            assert "MERGE" in query and "CREATE" not in query
        assert not any(label in query for label in (":Axiom", ":Fact", ":Entity", ":Universe"))


@pytest.mark.unit
def test_lookups_are_indexed_before_any_node_is_written(client):
    tools.neo4j_merge_book_tree(_tree(), uuid4())
    queries = [c.args[0] for c in client.execute_write.call_args_list]
    assert "CONSTRAINT" in queries[0] and "IF NOT EXISTS" in queries[0]
    assert "INDEX" in queries[1] and "MERGE" in queries[2]


@pytest.mark.unit
def test_large_trees_are_written_in_batches(client):
    tools.neo4j_merge_book_tree(_tree(2500), uuid4())
    calls = [c for c in client.execute_write.call_args_list if len(c.args) > 1]
    sizes = [len(c.args[1]["rows"]) for c in calls if "rows" in c.args[1]]
    assert sizes == [1000, 1000, 501]


@pytest.mark.unit
def test_delete_only_targets_book_nodes_of_that_document(client):
    tools.neo4j_delete_book_tree("d")
    query, params = client.execute_write.call_args.args
    assert ":BookNode" in query and params == {"doc_id": "d"}


@pytest.mark.unit
@pytest.mark.parametrize("tool", ["neo4j_merge_book_tree", "neo4j_delete_book_tree"])
def test_only_canonkeeper_may_write(tool):
    assert AUTHORITY_MATRIX[tool] == ["CanonKeeper"]
    assert tool in CANON_KEEPER_WRITE_TOOLS and tool not in SHARED_NEO4J_WRITE_TOOLS

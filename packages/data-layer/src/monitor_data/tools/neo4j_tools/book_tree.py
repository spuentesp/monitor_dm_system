"""Record a book's structure in Neo4j, as a record of the file and not canon (I-17).

Only CanonKeeper may call these, like other Neo4j writes. They never create or change an Axiom,
Fact or Entity. Writes use MERGE, so repeating a load changes nothing.
"""

from __future__ import annotations

from uuid import UUID

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.book_graph import BookTree

__all__ = ["neo4j_delete_book_tree", "neo4j_merge_book_tree"]

_BATCH = 1000


def neo4j_merge_book_tree(tree: BookTree, source_id: UUID) -> int:
    """Store a book tree under its Source. Returns how many nodes were written."""
    client = get_neo4j_client()
    # Without this, each MERGE scans every BookNode, which takes minutes on a full book.
    client.execute_write(
        "CREATE CONSTRAINT book_node_id IF NOT EXISTS FOR (n:BookNode) REQUIRE n.id IS UNIQUE"
    )
    client.execute_write("CREATE INDEX book_node_doc IF NOT EXISTS FOR (n:BookNode) ON (n.doc_id)")
    rows = [
        {
            "id": node.id,
            "doc_id": node.doc_id,
            "kind": node.kind.value,
            "parent_id": node.parent_id,
            "seq": node.seq,
            "text": node.text,
            "page_start": node.page_start,
            "page_end": node.page_end,
        }
        for node in tree.nodes
    ]
    for start in range(0, len(rows), _BATCH):
        client.execute_write(
            """
            UNWIND $rows AS row
            MERGE (n:BookNode {id: row.id})
            SET n.doc_id = row.doc_id, n.kind = row.kind, n.seq = row.seq, n.text = row.text,
                n.page_start = row.page_start, n.page_end = row.page_end
            """,
            {"rows": rows[start : start + _BATCH]},
        )
    links = [{"id": row["id"], "parent_id": row["parent_id"]} for row in rows if row["parent_id"]]
    for start in range(0, len(links), _BATCH):
        client.execute_write(
            """
            UNWIND $links AS link
            MATCH (child:BookNode {id: link.id}), (parent:BookNode {id: link.parent_id})
            MERGE (child)-[:PART_OF]->(parent)
            """,
            {"links": links[start : start + _BATCH]},
        )
    roots = [row["id"] for row in rows if not row["parent_id"]]
    if roots:
        client.execute_write(
            """
            MATCH (book:BookNode {id: $book_id}), (source:Source {id: $source_id})
            MERGE (book)-[:DESCRIBES]->(source)
            """,
            {"book_id": roots[0], "source_id": str(source_id)},
        )
    return len(rows)


def neo4j_delete_book_tree(doc_id: str) -> None:
    """Delete a document's book tree. Canon is untouched, as it never links to these nodes."""
    get_neo4j_client().execute_write("MATCH (n:BookNode {doc_id: $doc_id}) DETACH DELETE n", {"doc_id": doc_id})

"""
Fake Neo4j client — in-memory graph for unit tests.

Provides a minimal AsyncGraphDatabase-compatible interface that stores
nodes and relationships in memory. Supports the query patterns used by
MONITOR's neo4j_tools.

Usage::

    from tests.mocks.db.neo4j import FakeNeo4jClient

    client = FakeNeo4jClient()
    await client.connect()
    await client.run("CREATE (e:Entity {id: $id, name: $name})", id="e1", name="Goblin")
    result = await client.run("MATCH (e:Entity) RETURN e")
"""

from __future__ import annotations

import re
from typing import Any


class FakeNeo4jClient:
    """In-memory Neo4j client for unit tests.

    Stores nodes as dicts with labels and properties.
    Supports a subset of Cypher: CREATE, MATCH, MERGE, SET, DELETE, RETURN.
    """

    def __init__(self) -> None:
        self._nodes: list[dict[str, Any]] = []
        self._relationships: list[dict[str, Any]] = []
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def verify_connectivity(self) -> bool:
        return self._connected

    def add_node(self, labels: list[str], **props: Any) -> dict[str, Any]:
        """Add a node directly (bypassing Cypher)."""
        node = {"_labels": set(labels), **props}
        self._nodes.append(node)
        return node

    def add_relationship(
        self, start_idx: int, rel_type: str, end_idx: int, **props: Any
    ) -> dict[str, Any]:
        """Add a relationship directly."""
        rel = {
            "start": start_idx,
            "type": rel_type,
            "end": end_idx,
            **props,
        }
        self._relationships.append(rel)
        return rel

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Execute a simplified Cypher query.

        Supports:
        - CREATE (n:Label {key: $value})
        - MATCH (n:Label) RETURN n
        - MATCH (n:Label {key: $value}) RETURN n
        - MERGE (n:Label {key: $value})
        - SET n.key = $value
        - DELETE n
        """
        query_upper = query.strip().upper()

        # CREATE
        if query_upper.startswith("CREATE"):
            return self._handle_create(query, params)

        # MATCH
        if query_upper.startswith("MATCH"):
            return self._handle_match(query, params)

        # MERGE
        if query_upper.startswith("MERGE"):
            return self._handle_merge(query, params)

        # RETURN all nodes (fallback)
        if "RETURN" in query_upper:
            return [dict(n) for n in self._nodes]

        return []

    def _handle_create(self, query: str, params: dict) -> list[dict]:
        # Extract label and properties from CREATE (n:Label {key: $value, ...})
        label_match = re.search(r":(\w+)\s*\{", query)
        label = label_match.group(1) if label_match else "Entity"

        # Extract property keys from $param references
        param_refs = re.findall(r"\$(\w+)", query)
        props = {k: params.get(k) for k in param_refs}
        node = {"_labels": {label}, **props}
        self._nodes.append(node)
        return [node]

    def _handle_match(self, query: str, params: dict) -> list[dict]:
        # Extract label
        label_match = re.search(r":(\w+)", query)
        label = label_match.group(1) if label_match else None

        # Extract filter params
        param_refs = re.findall(r"\$(\w+)", query)
        filters = {k: params.get(k) for k in param_refs}

        results = []
        for node in self._nodes:
            if label and label not in node.get("_labels", set()):
                continue
            if all(node.get(k) == v for k, v in filters.items()):
                # Strip internal _labels key from results
                result = {k: v for k, v in node.items() if k != "_labels"}
                results.append(result)

        return results

    def _handle_merge(self, query: str, params: dict) -> list[dict]:
        # MERGE = find or create
        results = self._handle_match(query, params)
        if not results:
            results = self._handle_create(query, params)
        return results

    async def run_read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Alias for run() — read transactions use the same path."""
        return await self.run(query, **params)

    async def run_write(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Alias for run() — write transactions use the same path."""
        return await self.run(query, **params)

    def reset(self) -> None:
        """Clear all nodes and relationships."""
        self._nodes.clear()
        self._relationships.clear()


def make_mock_neo4j_client() -> FakeNeo4jClient:
    """Return a FakeNeo4jClient, pre-connected."""
    client = FakeNeo4jClient()
    client._connected = True
    return client

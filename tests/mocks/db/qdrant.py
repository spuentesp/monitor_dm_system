"""
Fake Qdrant client for unit tests.

Mirrors the async interface of monitor_data.db.qdrant.AsyncQdrantClient.
Stores points in memory with vector and payload.

Usage::

    from tests.mocks.db.qdrant import FakeQdrantClient

    client = FakeQdrantClient()
    await client.upsert(collection_name="memories", points=[
        {"id": "m1", "vector": [0.1, 0.2], "payload": {"text": "hello"}},
    ])
    results = await client.search(collection_name="memories", query_vector=[0.1, 0.2])
"""

from __future__ import annotations

import math
from typing import Any


class FakeQdrantClient:
    """In-memory Qdrant client for unit tests.

    Stores points per collection. Supports upsert, search (cosine similarity),
    delete, and collection management.
    """

    def __init__(self) -> None:
        self._collections: dict[str, list[dict[str, Any]]] = {}

    async def create_collection(
        self, collection_name: str, vectors_config: dict | None = None, **kwargs: Any
    ) -> None:
        if collection_name not in self._collections:
            self._collections[collection_name] = []

    async def delete_collection(self, collection_name: str) -> None:
        self._collections.pop(collection_name, None)

    async def get_collections(self) -> list[str]:
        return list(self._collections.keys())

    async def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self._collections

    async def upsert(
        self, collection_name: str, points: list[dict[str, Any]], **kwargs: Any
    ) -> None:
        if collection_name not in self._collections:
            self._collections[collection_name] = []
        for point in points:
            # Replace existing point with same ID
            existing = next(
                (
                    p
                    for p in self._collections[collection_name]
                    if p["id"] == point["id"]
                ),
                None,
            )
            if existing:
                existing.update(point)
            else:
                self._collections[collection_name].append(dict(point))

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        query_filter: dict | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search by cosine similarity."""
        if collection_name not in self._collections:
            return []

        scored = []
        for point in self._collections[collection_name]:
            vec = point.get("vector", [])
            if not vec:
                continue
            # Cosine similarity
            dot = sum(a * b for a, b in zip(query_vector, vec))
            mag_a = math.sqrt(sum(a * a for a in query_vector))
            mag_b = math.sqrt(sum(b * b for b in vec))
            if mag_a == 0 or mag_b == 0:
                score = 0.0
            else:
                score = dot / (mag_a * mag_b)

            # Apply payload filter
            if query_filter:
                payload = point.get("payload", {})
                if not self._match_filter(payload, query_filter):
                    continue

            scored.append(
                {
                    "id": point["id"],
                    "score": score,
                    "payload": point.get("payload", {}),
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def _match_filter(self, payload: dict, query_filter: dict) -> bool:
        """Minimal filter matching — must/should with field conditions."""
        if "must" in query_filter:
            for cond in query_filter["must"]:
                key = cond.get("key")
                match = cond.get("match", {})
                value = match.get("value")
                if payload.get(key) != value:
                    return False
        return True

    async def delete(
        self, collection_name: str, points_selector: list[str], **kwargs: Any
    ) -> None:
        if collection_name in self._collections:
            self._collections[collection_name] = [
                p
                for p in self._collections[collection_name]
                if p["id"] not in points_selector
            ]

    async def scroll(
        self,
        collection_name: str,
        limit: int = 10,
        offset: str | None = None,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Scroll through points."""
        if collection_name not in self._collections:
            return [], None
        points = self._collections[collection_name][:limit]
        return points, None

    def seed_collection(
        self, collection_name: str, points: list[dict[str, Any]]
    ) -> None:
        """Seed a collection with points directly."""
        self._collections[collection_name] = [dict(p) for p in points]

    def reset(self) -> None:
        """Clear all collections."""
        self._collections.clear()


def make_mock_qdrant_client() -> FakeQdrantClient:
    """Return a FakeQdrantClient with MONITOR's collections pre-created."""
    client = FakeQdrantClient()
    for name in ["scenes", "memories", "snippets", "entities", "knowledge"]:
        client._collections[name] = []
    return client

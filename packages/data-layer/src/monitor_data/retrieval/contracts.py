"""
Typed contracts for the retrieval boundary.

These are the shapes the ``RetrievalService`` exchanges with its callers.
Keep them small and transport-friendly — the whole point of the boundary is
that callers deal in Documents/Hits, never in raw vectors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class EmbeddingModelMismatchError(RuntimeError):
    """A collection was built with a different embedding model than the active one.

    Querying a collection built with model A using vectors from model B returns
    garbage (different vector spaces), or errors on a dimension mismatch. This
    is raised by ``RetrievalService.ensure_collection`` when the model recorded
    for a collection doesn't match the active embedding model, so a
    misconfiguration fails loud instead of silently corrupting retrieval.
    """


@dataclass
class Document:
    """A unit to index: text to embed + payload to store alongside its vector."""

    id: str
    text: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hit:
    """A retrieval result: the stored point + its similarity score."""

    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)
    text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "score": self.score, "payload": self.payload, "text": self.text}


@dataclass
class Scored:
    """A ranked candidate from ``nearest()`` — the demoted-classifier primitive.

    ``index`` is the position of the candidate in the input list (so callers can
    map the winner back to their own metadata, e.g. a schema skill row).
    """

    candidate: str
    index: int
    score: float

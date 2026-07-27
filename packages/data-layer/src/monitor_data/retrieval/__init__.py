"""
Retrieval boundary — the single owner of embeddings + Qdrant retrieval.

See ``service.py`` for the rationale. Callers import ``RetrievalService`` (or
the ``default_retrieval_service`` singleton) and deal in ``Document`` / ``Hit``
/ ``Scored`` — never raw vectors, never ``embed_text`` directly.
"""

from .config import RetrievalConfig
from .contracts import Document, EmbeddingModelMismatchError, Hit, Scored
from .service import (
    RetrievalService,
    default_retrieval_service,
    reset_retrieval_service,
)

__all__ = [
    "Document",
    "EmbeddingModelMismatchError",
    "Hit",
    "RetrievalConfig",
    "RetrievalService",
    "Scored",
    "default_retrieval_service",
    "reset_retrieval_service",
]

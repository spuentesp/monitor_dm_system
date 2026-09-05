"""
Semantic Search router.

Provides unified semantic search across all canon collections:
  - entities: NPC, location, faction, concept vectors
  - scenes: scene summary and turn vectors
  - snippets: ingested document chunks
  - knowledge: axioms, lore facts, setting events

Supports:
  - Free-text query (auto-embedded)
  - Optional pre-filter by universe_id, entity_type, canon_level, etc.
  - Keyword boost (AND-filter on text field)
  - Cross-collection merged ranking
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from monitor_data.schemas.vectors import (
    VectorFilter,
    VectorSearchRequest,
)
from monitor_data.tools.qdrant_tools import qdrant_search
from pydantic import BaseModel, Field

router = APIRouter()

# ─── Schema ──────────────────────────────────────────────────────────────────


class SearchResultItem(BaseModel):
    """Single ranked result from semantic search."""

    id: str = Field(description="Vector point ID (UUID string)")
    collection: str = Field(description="Collection this result came from")
    score: float = Field(description="Similarity score (0-1)")
    payload: dict[str, Any] = Field(default_factory=dict, description="Stored metadata payload")
    text: str | None = Field(
        default=None,
        description="Representative text snippet (from payload.text)",
    )
    entity_type: str | None = Field(
        default=None,
        description="Entity type if this is an entity result: character | location | faction | concept | object | organization",
    )
    universe_id: str | None = Field(default=None, description="Universe UUID string")
    story_id: str | None = Field(default=None, description="Story UUID string")
    scene_id: str | None = Field(default=None, description="Scene UUID string")
    node_type: str | None = Field(
        default=None,
        description="Knowledge node type: axiom | fact | lore_event",
    )
    canon_level: str | None = Field(default=None, description="Canon level: proposed | canon | retconned")


class SemanticSearchResponse(BaseModel):
    """Unified semantic search response across all collections."""

    query: str = Field(description="Original search query")
    collections_searched: list[str] = Field(description="Which collections were queried")
    total_results: int = Field(description="Total results across all collections")
    results: list[SearchResultItem] = Field(description="Ranked results, highest score first")


# ─── Helpers ─────────────────────────────────────────────────────────────────


# reason: bare helper accepting qdrant_client ScoredVector (untyped) + str + str | None and returning a typed SearchResultItem; mypy can't narrow ScoredVector's dynamic attribute access
def _build_result_item(scored_vector, collection: str, text: str | None = None) -> SearchResultItem:  # type: ignore
    """Convert a ScoredVector + collection into a SearchResultItem."""
    payload = scored_vector.payload or {}
    return SearchResultItem(
        id=str(scored_vector.id),
        collection=collection,
        score=scored_vector.score,
        payload=payload,
        text=text or payload.get("text"),
        entity_type=payload.get("entity_type"),
        universe_id=payload.get("universe_id"),
        story_id=payload.get("story_id"),
        scene_id=payload.get("scene_id"),
        node_type=payload.get("node_type"),
        canon_level=payload.get("canon_level"),
    )


def _embed_query_text(query_text: str) -> list[float]:
    """Embed query text through the RetrievalService — the single embed owner (sync)."""
    from monitor_data.retrieval import default_retrieval_service

    # reason: in-function import of qdrant_tools.run_sync — module isn't typed for the sync-bridge helper; suppress the import-time error
    from monitor_data.tools.qdrant_tools import run_sync  # type: ignore

    # reason: default_retrieval_service().embed_query returns Awaitable[list[float]]; run_sync expects Awaitable[Any] but the function signature promises list[float] — mypy sees the untyped bridge
    return run_sync(default_retrieval_service().embed_query(query_text))  # type: ignore


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.get("/search", response_model=SemanticSearchResponse)
async def semantic_search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query text"),
    universe_id: UUID | None = Query(default=None, description="Scope search to a specific universe"),
    entity_type: str | None = Query(
        default=None,
        description="Filter entities by type: character | faction | location | object | concept | organization",
    ),
    canon_level: str | None = Query(
        default=None,
        description="Filter by canon level: proposed | canon | retconned",
    ),
    collections: str | None = Query(
        default=None,
        description="Comma-separated collections to search (default: entities,scenes,snippets,knowledge)",
    ),
    limit: int = Query(default=10, ge=1, le=100, description="Max results per collection"),
    score_threshold: float | None = Query(
        default=None, ge=0.0, le=1.0, description="Minimum similarity score threshold"
    ),
) -> SemanticSearchResponse:
    """
    Perform semantic search across all canon collections.

    Searches entities, scenes, snippets, and knowledge collections by
    embedding the query text and finding the nearest vectors in Qdrant.

    Returns merged + ranked results from all collections with metadata
    extracted from the payload.
    """

    # Default collections
    target_collections = [
        c.strip()
        for c in (collections.split(",") if collections else ["entities", "scenes", "snippets", "knowledge"])
        if c.strip() in ("entities", "scenes", "snippets", "knowledge")
    ]

    # Build the filter
    vector_filter = None
    filter_params = {}
    if universe_id:
        filter_params["universe_id"] = str(universe_id)
    if entity_type:
        filter_params["entity_type"] = entity_type
    if canon_level:
        filter_params["canon_level"] = canon_level

    if filter_params:
        vector_filter = VectorFilter(**filter_params)

    # Embed the query text once
    try:
        query_vector = _embed_query_text(q)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to embed query: {exc}",
        ) from exc

    all_results: list[SearchResultItem] = []

    for collection in target_collections:
        try:
            search_params = VectorSearchRequest(
                collection=collection,
                query_vector=query_vector,
                top_k=limit,
                filter=vector_filter,
                score_threshold=score_threshold,
            )
            response = qdrant_search(search_params)

            for scored_vector in response.results:
                item = _build_result_item(scored_vector, collection)
                all_results.append(item)

        except ValueError:
            # Empty collection or bad filter — skip
            continue
        except Exception as exc:
            # Log but don't fail the whole search
            import structlog

            log = structlog.get_logger()
            log.warning("search_collection_failed", collection=collection, error=str(exc))
            continue

    # Sort by score descending
    all_results.sort(key=lambda r: r.score, reverse=True)

    return SemanticSearchResponse(
        query=q,
        collections_searched=target_collections,
        total_results=len(all_results),
        results=all_results,
    )


@router.get(
    "/universes/{universe_id}/search",
    response_model=SemanticSearchResponse,
)
async def universe_search(
    universe_id: UUID,
    q: str = Query(..., min_length=1, max_length=500, description="Search query text"),
    entity_type: str | None = Query(
        default=None,
        description="Filter entities by type",
    ),
    canon_level: str | None = Query(
        default=None,
        description="Filter by canon level",
    ),
    collections: str | None = Query(
        default=None,
        description="Comma-separated collections to search (default: entities,knowledge)",
    ),
    limit: int = Query(default=10, ge=1, le=100),
    score_threshold: float | None = Query(default=None, ge=0.0, le=1.0),
) -> SemanticSearchResponse:
    """
    Search within a specific universe.

    Convenience endpoint that always scopes to universe_id and defaults
    to searching entities and knowledge collections.
    """

    target_collections = [
        c.strip()
        for c in (collections.split(",") if collections else ["entities", "knowledge"])
        if c.strip() in ("entities", "scenes", "snippets", "knowledge")
    ]

    vector_filter = VectorFilter(
        universe_id=str(universe_id),
        entity_type=entity_type,
        canon_level=canon_level,
    )

    try:
        query_vector = _embed_query_text(q)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to embed query: {exc}") from exc

    all_results: list[SearchResultItem] = []

    for collection in target_collections:
        try:
            search_params = VectorSearchRequest(
                collection=collection,
                query_vector=query_vector,
                top_k=limit,
                filter=vector_filter,
                score_threshold=score_threshold,
            )
            response = qdrant_search(search_params)

            for scored_vector in response.results:
                item = _build_result_item(scored_vector, collection)
                all_results.append(item)
        except ValueError:
            continue
        except Exception as exc:
            import structlog

            log = structlog.get_logger()
            log.warning(
                "universe_search_collection_failed",
                collection=collection,
                error=str(exc),
            )
            continue

    all_results.sort(key=lambda r: r.score, reverse=True)

    return SemanticSearchResponse(
        query=q,
        collections_searched=target_collections,
        total_results=len(all_results),
        results=all_results,
    )

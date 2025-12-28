"""
Qdrant MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose Qdrant vector operations via the MCP server.
All operations are open to all agents (authority: *).
"""

from typing import Dict, List, Optional, Any

from monitor_data.db.qdrant import get_qdrant_client
from monitor_data.schemas.vectors import (
    VectorUpsert,
    VectorUpsertBatch,
    VectorSearch,
    VectorSearchResponse,
    VectorSearchResult,
    VectorDelete,
    VectorDeleteByFilter,
    VectorDeleteResponse,
    CollectionInfo,
    CollectionCreate,
)


# =============================================================================
# COLLECTION OPERATIONS
# =============================================================================


def qdrant_get_collection_info(collection: str) -> CollectionInfo:
    """
    Get information about a Qdrant collection.
    
    Authority: Any agent (read-only)
    Use Case: DL-10
    
    Args:
        collection: Collection name
        
    Returns:
        CollectionInfo with collection metadata
    """
    client = get_qdrant_client()
    
    info = client.get_collection_info(collection)
    
    return CollectionInfo(
        name=info["name"],
        vector_size=info["vector_size"],
        points_count=info["points_count"],
        exists=info["exists"],
        config=info.get("config"),
    )


def qdrant_create_collection(params: CollectionCreate) -> CollectionInfo:
    """
    Create a new Qdrant collection.
    
    Authority: Any agent
    Use Case: DL-10
    
    Args:
        params: Collection creation parameters
        
    Returns:
        CollectionInfo with created collection metadata
        
    Raises:
        ValueError: If collection already exists or parameters are invalid
    """
    client = get_qdrant_client()
    
    # Check if collection already exists
    if client.collection_exists(params.name):
        raise ValueError(f"Collection '{params.name}' already exists")
    
    # Create collection
    client.create_collection(
        collection_name=params.name,
        vector_size=params.vector_size,
        distance=params.distance,
    )
    
    # Return collection info
    return qdrant_get_collection_info(params.name)


# =============================================================================
# UPSERT OPERATIONS
# =============================================================================


def qdrant_upsert(params: VectorUpsert) -> Dict[str, Any]:
    """
    Upsert a single vector point to Qdrant.
    
    Creates collection if it doesn't exist.
    
    Authority: Any agent
    Use Case: DL-10
    
    Args:
        params: Vector upsert parameters
        
    Returns:
        Dict with upsert status
    """
    client = get_qdrant_client()
    
    # Create collection if it doesn't exist
    if not client.collection_exists(params.collection):
        vector_size = len(params.vector)
        client.create_collection(
            collection_name=params.collection,
            vector_size=vector_size,
            distance="Cosine",
        )
    
    # Upsert the point
    client.upsert(
        collection_name=params.collection,
        point_id=params.id,
        vector=params.vector,
        payload=params.payload.model_dump(),
    )
    
    return {
        "success": True,
        "collection": params.collection,
        "id": params.id,
        "vector_size": len(params.vector),
    }


def qdrant_upsert_batch(params: VectorUpsertBatch) -> Dict[str, Any]:
    """
    Upsert multiple vector points to Qdrant in batch.
    
    Creates collection if it doesn't exist.
    
    Authority: Any agent
    Use Case: DL-10
    
    Args:
        params: Batch upsert parameters
        
    Returns:
        Dict with batch upsert status
        
    Raises:
        ValueError: If points list is empty or vectors have inconsistent dimensions
    """
    client = get_qdrant_client()
    
    if not params.points:
        raise ValueError("Points list cannot be empty")
    
    # Verify all vectors have the same dimension
    vector_sizes = {len(point.vector) for point in params.points}
    if len(vector_sizes) > 1:
        raise ValueError(
            f"All vectors must have the same dimension. Found: {vector_sizes}"
        )
    
    vector_size = vector_sizes.pop()
    
    # Create collection if it doesn't exist
    if not client.collection_exists(params.collection):
        client.create_collection(
            collection_name=params.collection,
            vector_size=vector_size,
            distance="Cosine",
        )
    
    # Convert points to dict format
    points_data = [
        {
            "id": point.id,
            "vector": point.vector,
            "payload": point.payload,
        }
        for point in params.points
    ]
    
    # Upsert batch
    client.upsert_batch(
        collection_name=params.collection,
        points=points_data,
    )
    
    return {
        "success": True,
        "collection": params.collection,
        "count": len(params.points),
        "vector_size": vector_size,
    }


# =============================================================================
# SEARCH OPERATIONS
# =============================================================================


def qdrant_search(params: VectorSearch) -> VectorSearchResponse:
    """
    Search for similar vectors in Qdrant.
    
    Authority: Any agent
    Use Case: DL-10
    
    Args:
        params: Search parameters including query vector and filters
        
    Returns:
        VectorSearchResponse with search results
        
    Raises:
        ValueError: If collection doesn't exist
    """
    client = get_qdrant_client()
    
    # Check if collection exists
    if not client.collection_exists(params.collection):
        raise ValueError(f"Collection '{params.collection}' does not exist")
    
    # Build filter dict from VectorSearchFilter
    filter_dict = None
    if params.filter:
        filter_dict = {
            k: v 
            for k, v in params.filter.model_dump().items() 
            if v is not None
        }
    
    # Perform search
    results = client.search(
        collection_name=params.collection,
        query_vector=params.query_vector,
        limit=params.top_k,
        query_filter=filter_dict,
        score_threshold=params.score_threshold,
    )
    
    # Convert to response format
    search_results = [
        VectorSearchResult(
            id=result["id"],
            score=result["score"],
            payload=result["payload"],
        )
        for result in results
    ]
    
    return VectorSearchResponse(
        results=search_results,
        collection=params.collection,
        count=len(search_results),
    )


# =============================================================================
# DELETE OPERATIONS
# =============================================================================


def qdrant_delete(params: VectorDelete) -> VectorDeleteResponse:
    """
    Delete a single vector point from Qdrant.
    
    Authority: Any agent
    Use Case: DL-10
    
    Args:
        params: Delete parameters
        
    Returns:
        VectorDeleteResponse with deletion status
        
    Raises:
        ValueError: If collection doesn't exist
    """
    client = get_qdrant_client()
    
    # Check if collection exists
    if not client.collection_exists(params.collection):
        raise ValueError(f"Collection '{params.collection}' does not exist")
    
    # Delete the point
    client.delete(
        collection_name=params.collection,
        point_id=params.id,
    )
    
    return VectorDeleteResponse(
        deleted=True,
        count=1,
    )


def qdrant_delete_by_filter(params: VectorDeleteByFilter) -> VectorDeleteResponse:
    """
    Delete multiple vector points by filter from Qdrant.
    
    Authority: Any agent
    Use Case: DL-10
    
    Args:
        params: Delete by filter parameters
        
    Returns:
        VectorDeleteResponse with number of points deleted
        
    Raises:
        ValueError: If collection doesn't exist or filter is empty
    """
    client = get_qdrant_client()
    
    # Check if collection exists
    if not client.collection_exists(params.collection):
        raise ValueError(f"Collection '{params.collection}' does not exist")
    
    # Build filter dict
    filter_dict = {
        k: v 
        for k, v in params.filter.model_dump().items() 
        if v is not None
    }
    
    if not filter_dict:
        raise ValueError("At least one filter condition is required")
    
    # Delete points
    deleted_count = client.delete_by_filter(
        collection_name=params.collection,
        filter_dict=filter_dict,
    )
    
    return VectorDeleteResponse(
        deleted=True,
        count=deleted_count,
    )

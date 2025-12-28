"""
Qdrant client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (qdrant_client)
CALLED BY: qdrant_tools.py

This client provides a thin wrapper around the Qdrant client with
collection management and vector operations.
"""

import os
import threading
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient as QdrantClientLib
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)


# Thread-local storage for singleton client
_thread_local = threading.local()


class QdrantClient:
    """
    Qdrant vector database client for semantic search operations.
    
    This client provides operations for:
    - Upserting vectors (single and batch)
    - Searching for similar vectors
    - Deleting vectors
    - Managing collections
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize Qdrant client.
        
        Args:
            host: Qdrant host (default: from QDRANT_HOST env var or 'localhost')
            port: Qdrant port (default: from QDRANT_PORT env var or 6333)
            url: Full Qdrant URL (overrides host/port if provided)
            api_key: API key for authentication (from QDRANT_API_KEY env var)
        """
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.url = url or os.getenv("QDRANT_URL")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        
        self._client: Optional[QdrantClientLib] = None
    
    def connect(self) -> None:
        """Establish connection to Qdrant."""
        if self._client is None:
            if self.url:
                self._client = QdrantClientLib(url=self.url, api_key=self.api_key)
            else:
                self._client = QdrantClientLib(
                    host=self.host, 
                    port=self.port,
                    api_key=self.api_key
                )
    
    def close(self) -> None:
        """Close the Qdrant connection."""
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self) -> "QdrantClient":
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
    
    def _ensure_connected(self) -> QdrantClientLib:
        """Ensure client is connected and return the underlying client."""
        if not self._client:
            raise RuntimeError("Qdrant client not connected. Call connect() first.")
        return self._client
    
    def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            True if collection exists, False otherwise
        """
        client = self._ensure_connected()
        try:
            client.get_collection(collection_name)
            return True
        except Exception:
            return False
    
    def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: str = "Cosine",
    ) -> None:
        """
        Create a new collection.
        
        Args:
            collection_name: Name of the collection
            vector_size: Dimension of vectors
            distance: Distance metric (Cosine, Euclid, or Dot)
        
        Raises:
            ValueError: If distance metric is invalid
        """
        client = self._ensure_connected()
        
        # Map distance string to Distance enum
        distance_map = {
            "Cosine": Distance.COSINE,
            "Euclid": Distance.EUCLID,
            "Dot": Distance.DOT,
        }
        
        if distance not in distance_map:
            raise ValueError(
                f"Invalid distance metric: {distance}. "
                f"Must be one of: {', '.join(distance_map.keys())}"
            )
        
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=distance_map[distance]
            )
        )
    
    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        Get information about a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Dictionary with collection information
        """
        client = self._ensure_connected()
        
        if not self.collection_exists(collection_name):
            return {
                "name": collection_name,
                "exists": False,
                "vector_size": 0,
                "points_count": 0,
            }
        
        info = client.get_collection(collection_name)
        
        # Handle VectorParams which can be either a single VectorParams or dict
        vector_config = info.config.params.vectors
        if isinstance(vector_config, dict):
            # Multi-vector case - use the first vector config
            first_vector_config = next(iter(vector_config.values()))
            vector_size = first_vector_config.size if first_vector_config else 0
            distance_name = first_vector_config.distance.name if first_vector_config else "Unknown"
        else:
            # Single vector case
            vector_size = vector_config.size if vector_config else 0
            distance_name = vector_config.distance.name if vector_config else "Unknown"
        
        return {
            "name": collection_name,
            "exists": True,
            "vector_size": vector_size,
            "points_count": info.points_count,
            "config": {
                "distance": distance_name,
            }
        }
    
    def upsert(
        self,
        collection_name: str,
        point_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """
        Upsert a single vector point.
        
        Args:
            collection_name: Name of the collection
            point_id: Unique identifier for the point
            vector: Dense vector embedding
            payload: Metadata payload
        """
        client = self._ensure_connected()
        
        point = PointStruct(
            id=point_id,
            vector=vector,
            payload=payload
        )
        
        client.upsert(
            collection_name=collection_name,
            points=[point]
        )
    
    def upsert_batch(
        self,
        collection_name: str,
        points: List[Dict[str, Any]],
    ) -> None:
        """
        Upsert multiple vector points in batch.
        
        Args:
            collection_name: Name of the collection
            points: List of points, each with 'id', 'vector', and 'payload'
        """
        client = self._ensure_connected()
        
        point_structs = [
            PointStruct(
                id=point["id"],
                vector=point["vector"],
                payload=point["payload"]
            )
            for point in points
        ]
        
        client.upsert(
            collection_name=collection_name,
            points=point_structs
        )
    
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        query_filter: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            collection_name: Name of the collection
            query_vector: Query vector for similarity search
            limit: Maximum number of results
            query_filter: Optional filter for payload fields
            score_threshold: Minimum similarity score
            
        Returns:
            List of search results with id, score, and payload
        """
        client = self._ensure_connected()
        
        # Build Qdrant filter if provided
        qdrant_filter = None
        if query_filter:
            must_conditions: List[Any] = []
            
            for key, value in query_filter.items():
                if value is not None:
                    must_conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
            
            if must_conditions:
                qdrant_filter = Filter(must=must_conditions)
        
        results = client.search(  # type: ignore
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            score_threshold=score_threshold,
        )
        
        return [
            {
                "id": str(result.id),
                "score": result.score,
                "payload": result.payload or {},
            }
            for result in results
        ]
    
    def delete(
        self,
        collection_name: str,
        point_id: str,
    ) -> None:
        """
        Delete a single vector point.
        
        Args:
            collection_name: Name of the collection
            point_id: ID of the point to delete
        """
        client = self._ensure_connected()
        
        client.delete(
            collection_name=collection_name,
            points_selector=[point_id]
        )
    
    def delete_by_filter(
        self,
        collection_name: str,
        filter_dict: Dict[str, Any],
    ) -> int:
        """
        Delete multiple points by filter.
        
        Args:
            collection_name: Name of the collection
            filter_dict: Filter for points to delete
            
        Returns:
            Number of points deleted
        """
        client = self._ensure_connected()
        
        # Build Qdrant filter
        must_conditions: List[Any] = []
        for key, value in filter_dict.items():
            if value is not None:
                must_conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value)
                    )
                )
        
        if not must_conditions:
            raise ValueError("At least one filter condition is required")
        
        qdrant_filter = Filter(must=must_conditions)
        
        # Get count before deletion
        count_before: int = self.get_collection_info(collection_name)["points_count"]
        
        # Delete points
        client.delete(
            collection_name=collection_name,
            points_selector=qdrant_filter
        )
        
        # Get count after deletion
        count_after: int = self.get_collection_info(collection_name)["points_count"]
        
        return count_before - count_after


def get_qdrant_client() -> "QdrantClient":
    """
    Get or create a thread-local Qdrant client singleton.
    
    This ensures each thread has its own client instance while avoiding
    repeated initialization.
    
    Returns:
        QdrantClient instance
    """
    if not hasattr(_thread_local, "qdrant_client"):
        client = QdrantClient()
        client.connect()
        _thread_local.qdrant_client = client
    
    return _thread_local.qdrant_client  # type: ignore

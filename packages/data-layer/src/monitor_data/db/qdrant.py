"""
Qdrant client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (qdrant-client)
CALLED BY: qdrant_tools.py

This client provides a thin wrapper around the Qdrant client for:
- Scene embeddings: Semantic search across narrative scenes
- Memory embeddings: Character and agent memory recall
- Snippet embeddings: Document chunk search

Collections:
- scenes: Scene narrative embeddings
- memories: Character/agent memory embeddings
- snippets: Document chunk embeddings
"""

import os
from typing import Optional, Any, cast
from qdrant_client import QdrantClient as QdrantSDK
from qdrant_client.models import (
    Distance,
    VectorParams,
)


class QdrantClient:
    """
    Qdrant vector database client for MONITOR semantic search.

    Thread-safe singleton client for Qdrant operations.
    Manages connection lifecycle and provides vector operations.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize Qdrant client.

        Args:
            url: Qdrant server URL (default: from QDRANT_URL env var or localhost:6333)
            api_key: Qdrant API key (default: from QDRANT_API_KEY env var, optional)
        """
        self.url: str = cast(
            str, url or os.getenv("QDRANT_URL", "http://localhost:6333")
        )
        self.api_key: Optional[str] = api_key or os.getenv("QDRANT_API_KEY")
        self._client: Optional[QdrantSDK] = None

    def connect(self) -> None:
        """
        Establish connection to Qdrant.

        Creates client with URL and optional API key.
        """
        if self._client is None:
            if self.api_key:
                self._client = QdrantSDK(url=self.url, api_key=self.api_key)
            else:
                self._client = QdrantSDK(url=self.url)

    def close(self) -> None:
        """Close Qdrant connection."""
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

    def verify_connectivity(self) -> bool:
        """
        Verify Qdrant connection is working.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            if self._client is None:
                self.connect()
            assert self._client is not None
            # Try to get collections list
            self._client.get_collections()
            return True
        except Exception:
            return False

    def get_client(self) -> QdrantSDK:
        """
        Get the Qdrant client object.

        Returns:
            QdrantSDK client object

        Raises:
            RuntimeError: If not connected
        """
        if self._client is None:
            raise RuntimeError("Qdrant client not connected. Call connect() first.")
        return self._client

    def ensure_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: Distance = Distance.COSINE,
    ) -> None:
        """
        Ensure a collection exists with the specified configuration.

        Creates the collection if it doesn't exist.

        Args:
            collection_name: Name of the collection
            vector_size: Dimensionality of vectors
            distance: Distance metric (default: COSINE)
        """
        client = self.get_client()

        # Check if collection exists
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if collection_name not in collection_names:
            # Create collection
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance),
            )


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_qdrant_client_instance: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """
    Get or create the singleton Qdrant client.

    Returns:
        QdrantClient instance

    Thread-safe singleton pattern for database connections.
    """
    global _qdrant_client_instance

    if _qdrant_client_instance is None:
        _qdrant_client_instance = QdrantClient()
        _qdrant_client_instance.connect()

    return _qdrant_client_instance


def reset_qdrant_client() -> None:
    """
    Reset the Qdrant client singleton.

    Used for testing to ensure clean state between tests.
    """
    global _qdrant_client_instance

    if _qdrant_client_instance is not None:
        _qdrant_client_instance.close()
        _qdrant_client_instance = None

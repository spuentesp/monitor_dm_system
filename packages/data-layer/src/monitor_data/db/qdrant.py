"""
Qdrant client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (qdrant-client)
CALLED BY: qdrant_tools.py

This client provides a thin wrapper around the Qdrant client with
connection management for vector embedding operations.
"""

import os
import threading
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient as QdrantClientLib
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter


# Thread-local storage for singleton client
_local = threading.local()


class QdrantClient:
    """
    Qdrant vector database client for semantic search.

    This client provides access to Qdrant collections for storing and
    searching vector embeddings of scenes, memories, and snippets.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize Qdrant client.

        Args:
            url: Qdrant server URL (default: from QDRANT_URL env var)
            api_key: Qdrant API key (default: from QDRANT_API_KEY env var)
        """
        self.url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")

        self._client: Optional[QdrantClientLib] = None

    def connect(self) -> None:
        """Establish connection to Qdrant."""
        if self._client is None:
            if self.api_key:
                self._client = QdrantClientLib(
                    url=self.url,
                    api_key=self.api_key,
                )
            else:
                self._client = QdrantClientLib(url=self.url)

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

    def get_client(self) -> QdrantClientLib:
        """
        Get the underlying Qdrant client.

        Returns:
            QdrantClient instance

        Raises:
            RuntimeError: If not connected
        """
        if not self._client:
            raise RuntimeError(
                "Qdrant client not connected. Call connect() first."
            )
        return self._client

    def verify_connectivity(self) -> bool:
        """
        Verify Qdrant connection.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            if not self._client:
                self.connect()
            # Try to get collections list
            self._client.get_collections()
            return True
        except Exception:
            return False

    def ensure_collection(
        self,
        collection_name: str,
        vector_size: int = 1536,
        distance: Distance = Distance.COSINE,
    ) -> None:
        """
        Ensure a collection exists, create it if it doesn't.

        Args:
            collection_name: Name of the collection
            vector_size: Size of the vector embeddings (default: 1536 for OpenAI)
            distance: Distance metric (default: COSINE)

        Raises:
            RuntimeError: If not connected
        """
        if not self._client:
            raise RuntimeError(
                "Qdrant client not connected. Call connect() first."
            )

        try:
            # Check if collection exists
            self._client.get_collection(collection_name)
        except Exception:
            # Collection doesn't exist, create it
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance,
                ),
            )


def get_qdrant_client() -> QdrantClient:
    """
    Get or create a thread-local singleton Qdrant client.

    Returns:
        QdrantClient instance
    """
    if not hasattr(_local, "qdrant_client"):
        _local.qdrant_client = QdrantClient()
        _local.qdrant_client.connect()

    return _local.qdrant_client

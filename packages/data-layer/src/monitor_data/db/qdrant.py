"""
Qdrant client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (qdrant_client)
CALLED BY: qdrant_tools.py

This client provides a thin wrapper around qdrant_client for:
- Vector storage and retrieval
- Semantic search across narrative content
- Collection management with auto-creation

Collections:
- scenes: Scene embeddings for semantic search
- memories: Character and agent memory embeddings
- snippets: Document snippet embeddings
"""

import os
import threading
from typing import Any, Dict, Optional
from qdrant_client import QdrantClient as QdrantClientLib
from qdrant_client.models import (
    Distance,
    VectorParams,
)


# Default embedding dimension (OpenAI text-embedding-ada-002: 1536)
DEFAULT_VECTOR_SIZE = 1536

# Collection configurations
COLLECTION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "scenes": {"vector_size": DEFAULT_VECTOR_SIZE, "distance": Distance.COSINE},
    "memories": {"vector_size": DEFAULT_VECTOR_SIZE, "distance": Distance.COSINE},
    "snippets": {"vector_size": DEFAULT_VECTOR_SIZE, "distance": Distance.COSINE},
}


class QdrantClient:
    """
    Qdrant client for MONITOR vector storage and semantic search.

    Client for Qdrant operations.
    Manages connection lifecycle and collection auto-creation.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        path: Optional[str] = None,
    ):
        """
        Initialize Qdrant client.

        Args:
            url: Qdrant server URL (default: from QDRANT_URL env var)
            api_key: Qdrant API key (default: from QDRANT_API_KEY env var, optional)
            path: Local storage path for embedded Qdrant (default: from QDRANT_PATH env var)

        Note:
            If neither url nor path is provided, defaults to http://localhost:6333
        """
        self.url: Optional[str] = url or os.getenv("QDRANT_URL")
        self.api_key: Optional[str] = api_key or os.getenv("QDRANT_API_KEY")
        self.path: Optional[str] = path or os.getenv("QDRANT_PATH")

        # If no configuration provided, default to localhost
        if not self.url and not self.path:
            self.url = "http://localhost:6333"

        self._client: Optional[QdrantClientLib] = None
        self._collections_initialized: set = set()
        self._collection_lock = threading.Lock()

    def connect(self) -> None:
        """
        Establish connection to Qdrant.

        Creates client instance with appropriate configuration.
        Collections are created lazily on first use.
        """
        if self._client is None:
            if self.path:
                # Local embedded Qdrant
                self._client = QdrantClientLib(path=self.path)
            else:
                # Remote Qdrant server
                self._client = QdrantClientLib(
                    url=self.url,
                    api_key=self.api_key,
                )

    def close(self) -> None:
        """Close Qdrant connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._collections_initialized.clear()

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
            # Try to get collection list to verify connectivity
            self._client.get_collections()
            return True
        except Exception:
            return False

    def get_client(self) -> QdrantClientLib:
        """
        Get the Qdrant client object.

        Returns:
            qdrant_client QdrantClient object

        Raises:
            RuntimeError: If not connected
        """
        if self._client is None:
            raise RuntimeError("Qdrant client not connected. Call connect() first.")
        return self._client

    def ensure_collection(self, collection_name: str) -> None:
        """
        Ensure collection exists with correct configuration.

        Creates collection if it doesn't exist, using predefined configs.
        Thread-safe using lock to prevent race conditions.

        Args:
            collection_name: Name of the collection (scenes, memories, snippets)

        Raises:
            ValueError: If collection name is not in COLLECTION_CONFIGS
        """
        # Fast path: check without lock
        if collection_name in self._collections_initialized:
            return

        # Slow path: acquire lock for initialization
        with self._collection_lock:
            # Double-check after acquiring lock
            if collection_name in self._collections_initialized:
                return

            client = self.get_client()

            # Check if collection exists
            try:
                client.get_collection(collection_name)
                self._collections_initialized.add(collection_name)
                return
            except Exception:
                # Collection doesn't exist, create it
                pass

            # Get configuration
            if collection_name not in COLLECTION_CONFIGS:
                raise ValueError(
                    f"Unknown collection '{collection_name}'. "
                    f"Valid collections: {', '.join(COLLECTION_CONFIGS.keys())}"
                )

            config = COLLECTION_CONFIGS[collection_name]

            # Create collection
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=int(config["vector_size"]),
                    distance=config["distance"],  # Already Distance enum
                ),
            )

            self._collections_initialized.add(collection_name)


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_qdrant_client_instance: Optional[QdrantClient] = None
_client_lock = threading.Lock()


def get_qdrant_client() -> QdrantClient:
    """
    Get or create the singleton Qdrant client.

    Returns:
        QdrantClient instance

    Thread-safe singleton pattern using double-checked locking.
    """
    global _qdrant_client_instance

    # Fast path: check without lock
    if _qdrant_client_instance is None:
        # Slow path: acquire lock for initialization
        with _client_lock:
            # Double-check after acquiring lock
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

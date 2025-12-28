"""
MongoDB client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pymongo)
CALLED BY: mongodb_tools.py

This client provides a thin wrapper around the PyMongo client with
connection management for document operations.
"""

import os
import threading
from typing import Any, Dict, List, Optional

from pymongo import MongoClient as PyMongoClient
from pymongo.database import Database
from pymongo.collection import Collection


class MongoDBClient:
    """
    MongoDB client for narrative layer operations.

    This client provides access to MongoDB collections for scenes, turns,
    proposed changes, and other narrative artifacts.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        database_name: Optional[str] = None,
    ):
        """
        Initialize MongoDB client.

        Args:
            uri: MongoDB connection URI (default: from MONGODB_URI env var)
            database_name: Database name (default: from MONGODB_DATABASE env var or "monitor")

        Raises:
            ValueError: If URI is not provided and MONGODB_URI env var is not set
        """
        self.uri = uri or os.getenv(
            "MONGODB_URI", "mongodb://localhost:27017"
        )
        self.database_name = database_name or os.getenv(
            "MONGODB_DATABASE", "monitor"
        )

        if not self.uri:
            raise ValueError(
                "MongoDB URI is required. "
                "Provide it via the 'uri' parameter or set the MONGODB_URI environment variable."
            )

        self._client: Optional[PyMongoClient] = None
        self._database: Optional[Database] = None

    def connect(self) -> None:
        """Establish connection to MongoDB."""
        if self._client is None:
            self._client = PyMongoClient(self.uri)
            self._database = self._client[self.database_name]

    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._database = None

    def __enter__(self) -> "MongoDBClient":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def get_collection(self, collection_name: str) -> Collection:
        """
        Get a MongoDB collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Collection instance

        Raises:
            RuntimeError: If not connected
        """
        if not self._database:
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        return self._database[collection_name]

    def verify_connectivity(self) -> bool:
        """
        Verify connection to MongoDB.

        Returns:
            True if connected and can execute queries, False otherwise
        """
        try:
            if not self._client:
                return False
            # Ping the server to verify connectivity
            self._client.admin.command("ping")
            return True
        except Exception:
            return False


# Global client instance (can be initialized once at startup)
_client: Optional[MongoDBClient] = None
_client_lock = threading.Lock()


def get_mongodb_client() -> MongoDBClient:
    """
    Get or create the global MongoDB client instance (thread-safe).

    Returns:
        MongoDBClient instance

    Note:
        This returns a singleton client. Call connect() before using.
        Uses double-checked locking for thread-safe initialization.
    """
    global _client
    # First check without lock for performance
    if _client is None:
        # Acquire lock for initialization
        with _client_lock:
            # Second check with lock to prevent race condition
            if _client is None:
                _client = MongoDBClient()
                _client.connect()
    return _client

"""
MongoDB client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pymongo)
CALLED BY: mongodb_tools.py

This client provides a thin wrapper around the MongoDB driver with
connection management for narrative document operations.
"""

import os
import threading
from typing import Any, Dict, List, Optional

from pymongo import MongoClient as PyMongoClient
from pymongo.collection import Collection
from pymongo.database import Database


# Thread-local storage for singleton client
_local = threading.local()


class MongoDBClient:
    """
    MongoDB database client for narrative documents.

    This client provides access to MongoDB collections for scenes, turns,
    proposals, memories, and other narrative artifacts.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        database: Optional[str] = None,
    ):
        """
        Initialize MongoDB client.

        Args:
            uri: MongoDB connection URI (default: from MONGODB_URI env var)
            database: MongoDB database name (default: from MONGODB_DATABASE env var)
        """
        self.uri = uri or os.getenv(
            "MONGODB_URI", "mongodb://localhost:27017"
        )
        self.database_name = database or os.getenv(
            "MONGODB_DATABASE", "monitor"
        )

        self._client: Optional[PyMongoClient] = None
        self._db: Optional[Database] = None

    def connect(self) -> None:
        """Establish connection to MongoDB."""
        if self._client is None:
            self._client = PyMongoClient(self.uri)
            self._db = self._client[self.database_name]

    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

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
            PyMongo Collection object

        Raises:
            RuntimeError: If not connected
        """
        if not self._db:
            raise RuntimeError(
                "MongoDB client not connected. Call connect() first."
            )
        return self._db[collection_name]

    def verify_connectivity(self) -> bool:
        """
        Verify MongoDB connection.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            if not self._client:
                self.connect()
            # Ping the server
            self._client.admin.command("ping")
            return True
        except Exception:
            return False


def get_mongodb_client() -> MongoDBClient:
    """
    Get or create a thread-local singleton MongoDB client.

    Returns:
        MongoDBClient instance
    """
    if not hasattr(_local, "mongodb_client"):
        _local.mongodb_client = MongoDBClient()
        _local.mongodb_client.connect()

    return _local.mongodb_client

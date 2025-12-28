"""
MongoDB client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pymongo)
CALLED BY: mongodb_tools.py

This client provides a thin wrapper around the PyMongo driver with
connection management and collection access.
"""

import os
from typing import Any, Dict, List, Optional
from uuid import UUID

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


class MongoDBClientClass:
    """
    MongoDB database client for narrative documents and proposals.

    This client provides access to MongoDB collections for scenes, turns,
    documents, snippets, proposals, and other narrative artifacts.
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
            database: Database name (default: from MONGODB_DB env var or 'monitor')
        """
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.database_name = database or os.getenv("MONGODB_DB", "monitor")

        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    def connect(self) -> None:
        """Establish connection to MongoDB."""
        if self._client is None:
            self._client = MongoClient(self.uri)
            self._db = self._client[self.database_name]

    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    def __enter__(self) -> "MongoDBClientClass":
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
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        return self._db[collection_name]

    def verify_connectivity(self) -> bool:
        """
        Verify MongoDB connection.

        Returns:
            True if connected and can ping server
        """
        if not self._client:
            return False
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            return False


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_mongodb_client: Optional[MongoDBClientClass] = None


def get_mongodb_client() -> MongoDBClientClass:
    """
    Get the singleton MongoDB client instance.

    Returns:
        MongoDBClientClass instance

    Note:
        The client auto-connects on first use.
    """
    global _mongodb_client
    if _mongodb_client is None:
        _mongodb_client = MongoDBClientClass()
        _mongodb_client.connect()
    return _mongodb_client


def close_mongodb_client() -> None:
    """Close the singleton MongoDB client."""
    global _mongodb_client
    if _mongodb_client:
        _mongodb_client.close()
        _mongodb_client = None

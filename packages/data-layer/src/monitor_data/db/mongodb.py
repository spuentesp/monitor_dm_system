"""
MongoDB client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only
CALLED BY: mongodb_tools.py

This provides a thin wrapper around pymongo for narrative document storage.
Collections: scenes, turns, proposed_changes, resolutions, memories, etc.
"""

import os
import threading
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database


class MongoDBClient:
    """
    MongoDB client for MONITOR narrative documents.
    
    Provides access to MongoDB collections with connection pooling.
    The underlying PyMongo MongoClient is thread-safe and can be used
    across multiple threads/requests safely.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        database: str = "monitor",
    ):
        """
        Initialize MongoDB client.

        Args:
            uri: MongoDB connection URI (defaults to MONGODB_URI env var)
            database: Database name (defaults to "monitor")
        """
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.database_name = database
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    def connect(self) -> None:
        """Establish connection to MongoDB."""
        if self._client is None:
            self._client = MongoClient(self.uri)
            self._db = self._client[self.database_name]

    def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    @property
    def db(self) -> Database:
        """
        Get the MongoDB database instance.

        Returns:
            MongoDB Database object

        Raises:
            RuntimeError: If not connected
        """
        if self._db is None:
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        return self._db

    def verify_connectivity(self) -> bool:
        """
        Verify MongoDB connection is working.

        Returns:
            True if connection is healthy
        """
        try:
            if self._client:
                self._client.admin.command("ping")
                return True
            return False
        except Exception:
            return False


# =============================================================================
# SINGLETON CLIENT
# =============================================================================

_mongodb_client: Optional[MongoDBClient] = None
_mongodb_client_lock = threading.Lock()


def get_mongodb_client() -> MongoDBClient:
    """
    Get or create the singleton MongoDB client (thread-safe).

    Returns:
        MongoDBClient instance (connected)
    """
    global _mongodb_client
    if _mongodb_client is None:
        with _mongodb_client_lock:
            # Double-check pattern to avoid race condition
            if _mongodb_client is None:
                _mongodb_client = MongoDBClient()
                _mongodb_client.connect()
    return _mongodb_client


def close_mongodb_client() -> None:
    """Close the singleton MongoDB client."""
    global _mongodb_client
    if _mongodb_client:
        _mongodb_client.close()
        _mongodb_client = None

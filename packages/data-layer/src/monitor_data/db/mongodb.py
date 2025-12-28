"""
MongoDB client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pymongo)
CALLED BY: mongodb_tools.py

This module provides a MongoDB client with connection pooling and
error handling for MONITOR's narrative and document storage.
"""

import os
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError


class MongoDBClient:
    """
    MongoDB client for MONITOR Data Layer.

    Handles connection management, database selection, and error handling.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        database: str = "monitor",
        timeout: int = 5000,
    ):
        """
        Initialize MongoDB client.

        Args:
            uri: MongoDB connection URI (default: from MONGODB_URI env var)
            database: Database name (default: "monitor")
            timeout: Server selection timeout in milliseconds (default: 5000)
        """
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.database_name = database
        self.timeout = timeout
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    def connect(self) -> None:
        """
        Connect to MongoDB server.

        Raises:
            ConnectionFailure: If connection fails
            ServerSelectionTimeoutError: If server selection times out
        """
        if self._client is None:
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.timeout,
            )
            # Verify connection
            self._client.admin.command("ping")
            self._db = self._client[self.database_name]

    def close(self) -> None:
        """Close MongoDB connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

    def verify_connectivity(self) -> bool:
        """
        Verify MongoDB connection is active.

        Returns:
            True if connected and server is responding, False otherwise
        """
        try:
            if self._client is None:
                self.connect()
            self._client.admin.command("ping")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError):
            return False

    @property
    def db(self) -> Database:
        """
        Get database handle.

        Returns:
            MongoDB database object

        Raises:
            RuntimeError: If not connected
        """
        if self._db is None:
            raise RuntimeError("Not connected to MongoDB. Call connect() first.")
        return self._db


# =============================================================================
# GLOBAL CLIENT INSTANCE
# =============================================================================

_mongodb_client: Optional[MongoDBClient] = None


def get_mongodb_client() -> MongoDBClient:
    """
    Get or create the global MongoDB client instance.

    Returns:
        MongoDBClient instance

    Example:
        >>> client = get_mongodb_client()
        >>> client.connect()
        >>> db = client.db
        >>> scenes = db.scenes.find_one({"scene_id": "..."})
    """
    global _mongodb_client
    if _mongodb_client is None:
        _mongodb_client = MongoDBClient()
    if _mongodb_client._client is None:
        _mongodb_client.connect()
    return _mongodb_client


def close_mongodb_client() -> None:
    """Close the global MongoDB client if it exists."""
    global _mongodb_client
    if _mongodb_client is not None:
        _mongodb_client.close()
        _mongodb_client = None

"""
MongoDB client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pymongo)
CALLED BY: mongodb_tools.py

This client provides a thin wrapper around pymongo for:
- Scenes: Narrative episodes and their turns
- ProposedChanges: Staging area for canonization
- Memories: Agent and character memories
- Documents: Ingested source documents

Collections:
- scenes: Scene documents with embedded turns
- proposed_changes: Proposed changes awaiting canonization
- memories: Character and agent memories
- documents: Source documents and metadata
- snippets: Document snippets with embeddings
"""

import os
from typing import Optional, Dict, Any, List
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.collection import Collection


class MongoDBClient:
    """
    MongoDB client for MONITOR narrative and document storage.

    Thread-safe singleton client for MongoDB operations.
    Manages connection lifecycle and provides collection access.
    """

    _instance: Optional["MongoDBClient"] = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    def __init__(
        self,
        uri: Optional[str] = None,
        database: Optional[str] = None,
    ):
        """
        Initialize MongoDB client.

        Args:
            uri: MongoDB connection URI (default: from MONGODB_URI env var)
            database: Database name (default: from MONGODB_DATABASE env var or "monitor")
        """
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.database_name = database or os.getenv("MONGODB_DATABASE", "monitor")
        self._client = None
        self._db = None

    def connect(self) -> None:
        """
        Establish connection to MongoDB.

        Creates indexes for all collections on first connection.
        """
        if self._client is None:
            self._client = MongoClient(self.uri)
            self._db = self._client[self.database_name]
            self._create_indexes()

    def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    def verify_connectivity(self) -> bool:
        """
        Verify MongoDB connection is working.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            if self._client is None:
                self.connect()
            # Ping the server
            self._client.admin.command("ping")
            return True
        except Exception:
            return False

    def get_database(self) -> Database:
        """
        Get the MongoDB database object.

        Returns:
            pymongo Database object

        Raises:
            RuntimeError: If not connected
        """
        if self._db is None:
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        return self._db

    def get_collection(self, name: str) -> Collection:
        """
        Get a collection by name.

        Args:
            name: Collection name

        Returns:
            pymongo Collection object
        """
        db = self.get_database()
        return db[name]

    def _create_indexes(self) -> None:
        """
        Create indexes for all collections.

        Called automatically on first connection.
        """
        if self._db is None:
            return

        # Scenes collection indexes
        scenes = self._db["scenes"]
        scenes.create_index([("scene_id", ASCENDING)], unique=True)
        scenes.create_index([("story_id", ASCENDING), ("order", ASCENDING)])
        scenes.create_index([("status", ASCENDING)])
        scenes.create_index([("created_at", DESCENDING)])

        # Proposed changes collection indexes
        proposed_changes = self._db["proposed_changes"]
        proposed_changes.create_index([("proposal_id", ASCENDING)], unique=True)
        proposed_changes.create_index([("scene_id", ASCENDING), ("status", ASCENDING)])
        proposed_changes.create_index([("status", ASCENDING)])

        # Memories collection indexes
        memories = self._db["memories"]
        memories.create_index([("memory_id", ASCENDING)], unique=True)
        memories.create_index([("entity_id", ASCENDING)])
        memories.create_index([("created_at", DESCENDING)])

        # Documents collection indexes
        documents = self._db["documents"]
        documents.create_index([("doc_id", ASCENDING)], unique=True)
        documents.create_index([("universe_id", ASCENDING)])
        documents.create_index([("status", ASCENDING)])

        # Snippets collection indexes
        snippets = self._db["snippets"]
        snippets.create_index([("snippet_id", ASCENDING)], unique=True)
        snippets.create_index([("doc_id", ASCENDING)])


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_mongodb_client_instance: Optional[MongoDBClient] = None


def get_mongodb_client() -> MongoDBClient:
    """
    Get or create the singleton MongoDB client.

    Returns:
        MongoDBClient instance

    Thread-safe singleton pattern for database connections.
    """
    global _mongodb_client_instance

    if _mongodb_client_instance is None:
        _mongodb_client_instance = MongoDBClient()
        _mongodb_client_instance.connect()

    return _mongodb_client_instance


def reset_mongodb_client() -> None:
    """
    Reset the MongoDB client singleton.

    Used for testing to ensure clean state between tests.
    """
    global _mongodb_client_instance

    if _mongodb_client_instance is not None:
        _mongodb_client_instance.close()
        _mongodb_client_instance = None

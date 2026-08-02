"""
MongoDB client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pymongo, tenacity)
CALLED BY: mongodb_tools.py

The rest of the data-layer Mongo tools are synchronous functions, so this
wrapper exposes a synchronous PyMongo-compatible database/collection surface.
Connection setup is still routed through the shared background-loop singleton so
callers do not need to care whether they are running in sync or async contexts.

Collections:
- scenes            : Narrative episodes and their turns
- proposed_changes  : Staging area for CanonKeeper canonisation
- memories          : Agent and character memories
- documents         : Ingested source documents and metadata
- snippets          : Document chunks with embedding references
"""

import threading

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from tenacity import retry

from monitor_data.config import settings
from monitor_data.db._utils import DB_RETRY, run_sync


class MongoDBClient:
    """
    Async MongoDB client for MONITOR narrative and document storage.

    Lazily connects on first use.  All public methods are coroutines.
    """

    def __init__(
        self,
        uri: str | None = None,
        database: str | None = None,
    ) -> None:
        self._uri: str = uri or settings.mongodb_uri
        self._database_name: str = database or settings.mongodb_database
        self._client: MongoClient | None = None
        self._db: Database | None = None
        self._indexes_created: bool = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the Mongo client and create indexes (idempotent)."""
        if self._client is None:
            self._client = MongoClient(
                self._uri,
                tz_aware=True,
                serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
                connectTimeoutMS=settings.mongodb_connect_timeout_ms,
            )
            self._db = self._client[self._database_name]
        if not self._indexes_created:
            await self._create_indexes()
            self._indexes_created = True

    async def close(self) -> None:
        """Close the PyMongo client and release resources."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
            self._indexes_created = False

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @retry(**DB_RETRY)
    async def verify_connectivity(self) -> bool:
        """Ping MongoDB and return True if reachable."""
        try:
            if self._client is None:
                await self.connect()
            assert self._client is not None
            self._client.admin.command("ping")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_database(self) -> Database:
        """Return the PyMongo database object (auto-connects)."""
        if self._client is None:
            # We use run_sync here because this is often called from sync tool functions
            run_sync(self.connect())
        assert self._db is not None
        return self._db

    def get_collection(self, name: str) -> Collection:
        """Return a Mongo collection by name (auto-connects)."""
        return self.get_database()[name]

    def __getitem__(self, name: str) -> Collection:
        """Allow legacy code to access collections via client["collection"]."""
        return self.get_collection(name)

    # ------------------------------------------------------------------
    # Index creation
    # ------------------------------------------------------------------

    async def _create_indexes(self) -> None:
        """Create supporting indexes for all collections (idempotent)."""
        if self._db is None:
            return

        # Implementation continues...

        scenes: Collection = self._db["scenes"]
        scenes.create_index([("scene_id", ASCENDING)], unique=True)
        scenes.create_index([("story_id", ASCENDING), ("order", ASCENDING)])
        scenes.create_index([("status", ASCENDING)])
        scenes.create_index([("created_at", DESCENDING)])

        proposed: Collection = self._db["proposed_changes"]
        proposed.create_index([("proposal_id", ASCENDING)], unique=True)
        proposed.create_index([("scene_id", ASCENDING), ("status", ASCENDING)])
        proposed.create_index([("status", ASCENDING)])

        memories: Collection = self._db["memories"]
        memories.create_index([("memory_id", ASCENDING)], unique=True)
        memories.create_index([("entity_id", ASCENDING)])
        memories.create_index([("created_at", DESCENDING)])

        documents: Collection = self._db["documents"]
        documents.create_index([("doc_id", ASCENDING)], unique=True)
        documents.create_index([("universe_id", ASCENDING)])
        documents.create_index([("status", ASCENDING)])

        snippets: Collection = self._db["snippets"]
        snippets.create_index([("snippet_id", ASCENDING)], unique=True)
        snippets.create_index([("doc_id", ASCENDING)])

        ingestion_jobs: Collection = self._db["ingestion_jobs"]
        ingestion_jobs.create_index([("job_id", ASCENDING)], unique=True)
        ingestion_jobs.create_index([("source_id", ASCENDING)])
        ingestion_jobs.create_index([("universe_id", ASCENDING)])
        ingestion_jobs.create_index([("status", ASCENDING)])
        ingestion_jobs.create_index([("created_at", DESCENDING)])

        knowledge_packs: Collection = self._db["knowledge_packs"]
        knowledge_packs.create_index([("pack_id", ASCENDING)], unique=True)
        knowledge_packs.create_index([("status", ASCENDING)])
        knowledge_packs.create_index([("pack_type", ASCENDING)])
        knowledge_packs.create_index([("system_name", ASCENDING)])
        knowledge_packs.create_index([("created_at", DESCENDING)])

        chat_sessions: Collection = self._db["chat_sessions"]
        chat_sessions.create_index([("id", ASCENDING)], unique=True)
        chat_sessions.create_index([("universe_id", ASCENDING)])
        chat_sessions.create_index([("updated_at", DESCENDING)])

        chat_messages: Collection = self._db["chat_messages"]
        chat_messages.create_index([("id", ASCENDING)], unique=True)
        chat_messages.create_index([("session_id", ASCENDING), ("timestamp", ASCENDING)])

        world_library: Collection = self._db["world_library"]
        world_library.create_index([("entry_id", ASCENDING)], unique=True)
        world_library.create_index([("multiverse_id", ASCENDING)])
        world_library.create_index([("system_name", ASCENDING)])

        # Append-only Q-10 audit trail (R5). Queried by subject history,
        # type/author/transaction filters, and sorted by timestamp desc.
        change_log: Collection = self._db["change_log"]
        change_log.create_index([("change_id", ASCENDING)], unique=True)
        change_log.create_index([("subject_id", ASCENDING), ("timestamp", DESCENDING)])
        change_log.create_index([("subject_type", ASCENDING)])
        change_log.create_index([("transaction_id", ASCENDING)])
        change_log.create_index([("author", ASCENDING)])
        change_log.create_index([("timestamp", DESCENDING)])

        # Curated Session Zero / character-creation prompt collections.
        # Queried by category + system/universe binding when resolving the
        # authored interview for a session; sorted by updated_at desc in lists.
        prompt_collections: Collection = self._db["prompt_collections"]
        prompt_collections.create_index([("collection_id", ASCENDING)], unique=True)
        prompt_collections.create_index([("category", ASCENDING)])
        prompt_collections.create_index([("system_id", ASCENDING)])
        prompt_collections.create_index([("universe_id", ASCENDING)])
        prompt_collections.create_index([("updated_at", DESCENDING)])

        # Immutable published snapshots of prompt collections (versioning).
        prompt_collection_versions: Collection = self._db["prompt_collection_versions"]
        prompt_collection_versions.create_index([("version_id", ASCENDING)], unique=True)
        prompt_collection_versions.create_index([("collection_id", ASCENDING), ("published_at", DESCENDING)])

        # Generated image assets. Lookup indexes mirror the filters used by
        # image history/reference selection and keep newest-first scans cheap.
        generated_assets: Collection = self._db["generated_assets"]
        generated_assets.create_index([("asset_id", ASCENDING)], unique=True)
        generated_assets.create_index(
            [("entity_id", ASCENDING), ("universe_id", ASCENDING), ("created_at", DESCENDING)]
        )
        generated_assets.create_index([("character_id", ASCENDING), ("created_at", DESCENDING)])
        generated_assets.create_index([("scene_id", ASCENDING), ("created_at", DESCENDING)])
        generated_assets.create_index([("conversation_id", ASCENDING), ("created_at", DESCENDING)])

        # Versioned visual identities, queried by canonical or card anchor.
        visual_identities: Collection = self._db["visual_identities"]
        visual_identities.create_index([("identity_id", ASCENDING)], unique=True)
        visual_identities.create_index(
            [("entity_id", ASCENDING), ("universe_id", ASCENDING), ("status", ASCENDING)]
        )
        visual_identities.create_index(
            [("character_id", ASCENDING), ("universe_id", ASCENDING), ("status", ASCENDING)]
        )


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_mongodb_client_instance: MongoDBClient | None = None
_client_lock = threading.Lock()


def get_mongodb_client() -> MongoDBClient:
    """
    Return (and lazily initialise) the module-level MongoDBClient singleton.

    Synchronous — safe to call from any context including async FastAPI handlers.
    The underlying Motor operations run on a dedicated background thread loop.
    """
    global _mongodb_client_instance
    with _client_lock:
        if _mongodb_client_instance is None:
            _mongodb_client_instance = MongoDBClient()
    return _mongodb_client_instance


def reset_mongodb_client() -> None:
    """
    Close and discard the singleton. Used in tests for clean state.
    """
    global _mongodb_client_instance
    with _client_lock:
        if _mongodb_client_instance is not None:
            run_sync(_mongodb_client_instance.close())
            _mongodb_client_instance = None

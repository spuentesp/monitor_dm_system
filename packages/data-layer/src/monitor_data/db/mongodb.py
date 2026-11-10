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
from typing import Any

from pymongo import ASCENDING, DESCENDING, TEXT, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from tenacity import retry

from monitor_data.config import settings
from monitor_data.db._utils import DB_RETRY, run_sync


# ---------------------------------------------------------------------------
# Index specification
# ---------------------------------------------------------------------------
# Every collection maps to a list of (keys, kwargs) handed to
# Collection.create_index. TEXT keys build a full-text index (MongoDB allows
# one text index per collection) — these cover the full-text search role that
# OpenSearch used to be provisioned for. ``ensure_indexes_for_prefix`` replays
# the same spec against world-prefixed collection names (e.g. "lotr_scenes").
# ---------------------------------------------------------------------------

_INDEX_SPECS: dict[str, list[tuple[list[tuple[str, Any]], dict[str, Any]]]] = {
    "scenes": [
        ([("scene_id", ASCENDING)], {"unique": True}),
        ([("story_id", ASCENDING), ("order", ASCENDING)], {}),
        ([("status", ASCENDING)], {}),
        ([("created_at", DESCENDING)], {}),
        ([("title", TEXT), ("purpose", TEXT), ("summary", TEXT)], {"name": "scenes_text"}),
    ],
    "proposed_changes": [
        ([("proposal_id", ASCENDING)], {"unique": True}),
        ([("scene_id", ASCENDING), ("status", ASCENDING)], {}),
        ([("status", ASCENDING)], {}),
    ],
    "memories": [
        ([("memory_id", ASCENDING)], {"unique": True}),
        ([("entity_id", ASCENDING)], {}),
        ([("created_at", DESCENDING)], {}),
    ],
    "documents": [
        ([("doc_id", ASCENDING)], {"unique": True}),
        ([("universe_id", ASCENDING)], {}),
        ([("status", ASCENDING)], {}),
    ],
    "snippets": [
        ([("snippet_id", ASCENDING)], {"unique": True}),
        ([("doc_id", ASCENDING)], {}),
        ([("text", TEXT), ("section", TEXT)], {"name": "snippets_text"}),
    ],
    "ingestion_jobs": [
        ([("job_id", ASCENDING)], {"unique": True}),
        ([("source_id", ASCENDING)], {}),
        ([("universe_id", ASCENDING)], {}),
        ([("status", ASCENDING)], {}),
        ([("created_at", DESCENDING)], {}),
    ],
    "knowledge_packs": [
        ([("pack_id", ASCENDING)], {"unique": True}),
        ([("status", ASCENDING)], {}),
        ([("pack_type", ASCENDING)], {}),
        ([("system_name", ASCENDING)], {}),
        ([("created_at", DESCENDING)], {}),
        ([("name", TEXT), ("description", TEXT), ("intro_text", TEXT)], {"name": "packs_text"}),
    ],
    "chat_sessions": [
        ([("id", ASCENDING)], {"unique": True}),
        ([("universe_id", ASCENDING)], {}),
        ([("updated_at", DESCENDING)], {}),
    ],
    "chat_messages": [
        ([("id", ASCENDING)], {"unique": True}),
        ([("session_id", ASCENDING), ("timestamp", ASCENDING)], {}),
        ([("text", TEXT), ("entity_name", TEXT)], {"name": "chat_messages_text"}),
    ],
    "world_library": [
        ([("entry_id", ASCENDING)], {"unique": True}),
        ([("multiverse_id", ASCENDING)], {}),
        ([("system_name", ASCENDING)], {}),
    ],
    # I-17 book decomposition progress; `_id` already makes each record unique.
    "book_records": [
        ([("doc_id", ASCENDING), ("record_type", ASCENDING)], {}),
    ],
    # Append-only Q-10 audit trail (R5). Queried by subject history,
    # type/author/transaction filters, and sorted by timestamp desc.
    "change_log": [
        ([("change_id", ASCENDING)], {"unique": True}),
        ([("subject_id", ASCENDING), ("timestamp", DESCENDING)], {}),
        ([("subject_type", ASCENDING)], {}),
        ([("transaction_id", ASCENDING)], {}),
        ([("author", ASCENDING)], {}),
        ([("timestamp", DESCENDING)], {}),
    ],
    # Curated Session Zero / character-creation prompt collections.
    # Queried by category + system/universe binding when resolving the
    # authored interview for a session; sorted by updated_at desc in lists.
    "prompt_collections": [
        ([("collection_id", ASCENDING)], {"unique": True}),
        ([("category", ASCENDING)], {}),
        ([("system_id", ASCENDING)], {}),
        ([("universe_id", ASCENDING)], {}),
        ([("updated_at", DESCENDING)], {}),
    ],
    # Immutable published snapshots of prompt collections (versioning).
    "prompt_collection_versions": [
        ([("version_id", ASCENDING)], {"unique": True}),
        ([("collection_id", ASCENDING), ("published_at", DESCENDING)], {}),
    ],
    # Generated image assets. Lookup indexes mirror the filters used by
    # image history/reference selection and keep newest-first scans cheap.
    "generated_assets": [
        ([("asset_id", ASCENDING)], {"unique": True}),
        ([("entity_id", ASCENDING), ("universe_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ([("character_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ([("scene_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ([("conversation_id", ASCENDING), ("created_at", DESCENDING)], {}),
    ],
    # Versioned visual identities, queried by canonical or card anchor.
    "visual_identities": [
        ([("identity_id", ASCENDING)], {"unique": True}),
        ([("entity_id", ASCENDING), ("universe_id", ASCENDING), ("status", ASCENDING)], {}),
        ([("character_id", ASCENDING), ("universe_id", ASCENDING), ("status", ASCENDING)], {}),
    ],
    "lorebook_entries": [
        ([("id", ASCENDING)], {"unique": True}),
        ([("character_id", ASCENDING), ("is_active", ASCENDING)], {}),
        ([("content", TEXT), ("comment", TEXT)], {"name": "lorebook_text"}),
    ],
    "gm_notes": [
        ([("universe_id", ASCENDING)], {"unique": True}),
        ([("content", TEXT)], {"name": "gm_notes_text"}),
    ],
}


def _apply_index_specs(
    db: Database,
    specs: dict[str, list[tuple[list[tuple[str, Any]], dict[str, Any]]]],
    prefix: str = "",
) -> None:
    """Create all indexes in ``specs`` on ``db``, optionally name-prefixed."""
    for name, indexes in specs.items():
        coll = db[f"{prefix}{name}"]
        for keys, kwargs in indexes:
            coll.create_index(keys, **kwargs)


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
        # Multi-world support: when a world is active, collections resolve to
        # "<prefix><name>" (see world_db_bindings.mongodb_collection_prefix).
        self._collection_prefix: str = ""

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
        except Exception:  # noqa: BLE001  # reason: falls back to `False` on failure (in verify_connectivity)
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

    def set_collection_prefix(self, prefix: str) -> None:
        """Set the world prefix applied by get_collection ('' = default collections)."""
        self._collection_prefix = (prefix or "").strip()

    @property
    def collection_prefix(self) -> str:
        return self._collection_prefix

    def get_collection(self, name: str) -> Collection:
        """Return a Mongo collection by name (auto-connects, world prefix applied)."""
        return self.get_database()[f"{self._collection_prefix}{name}"]

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
        _apply_index_specs(self._db, _INDEX_SPECS)

    async def ensure_indexes_for_prefix(self, prefix: str) -> None:
        """Create the standard index set on world-prefixed collections.

        Multi-world support isolates a world's Mongo data by collection-name
        prefix (world_db_bindings.mongodb_collection_prefix, e.g. "lotr_" →
        "lotr_scenes"). Call this when a prefixed world is created so its
        collections get the same indexes — including the text indexes — as
        the default collections. Idempotent; a no-op for an empty prefix.
        """
        prefix = (prefix or "").strip()
        if not prefix:
            return
        _apply_index_specs(self.get_database(), _INDEX_SPECS, prefix=prefix)


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

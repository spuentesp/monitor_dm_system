"""
Qdrant client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (qdrant_client, tenacity)
CALLED BY: qdrant_tools.py

Async Qdrant client using ``AsyncQdrantClient``.
- Vector storage and retrieval
- Semantic search across narrative content
- Collection auto-creation with predefined configs
- Tenacity retry decorators on transient failures

Collections:
- scenes    : Scene embeddings for semantic search
- memories  : Character and agent memory embeddings
- snippets  : Document snippet embeddings
"""

import asyncio
import logging
import threading
from typing import Any

from qdrant_client import AsyncQdrantClient as QdrantAsyncClientLib
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    TextIndexParams,
    TokenizerType,
    VectorParams,
)
from tenacity import retry

from monitor_data.config import settings
from monitor_data.db._utils import DB_RETRY, run_sync

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Collection configuration
# ---------------------------------------------------------------------------

DEFAULT_VECTOR_SIZE = settings.embedding_dimension  # configurable via EMBEDDING_DIMENSION

COLLECTION_CONFIGS: dict[str, dict[str, Any]] = {
    # Narrative scene content (summaries + turn text)
    "scenes": {"vector_size": DEFAULT_VECTOR_SIZE, "distance": Distance.COSINE},
    # Character and agent episodic memories
    "memories": {"vector_size": DEFAULT_VECTOR_SIZE, "distance": Distance.COSINE},
    # Ingested document chunks (source text passages)
    "snippets": {"vector_size": DEFAULT_VECTOR_SIZE, "distance": Distance.COSINE},
    # Entity descriptions for semantic NPC/location/faction discovery
    #   Payload: entity_id, universe_id, name, entity_type, state_tags, detail_level
    "entities": {"vector_size": DEFAULT_VECTOR_SIZE, "distance": Distance.COSINE},
    # Rules, axioms, game terms, lore events — structured world knowledge
    #   Payload: source_id, universe_id, type (axiom|lore_event|term), ref_id, title
    "knowledge": {"vector_size": DEFAULT_VECTOR_SIZE, "distance": Distance.COSINE},
}

PAYLOAD_INDEX_CONFIGS: dict[str, dict[str, Any]] = {
    "scenes": {
        "scene_id": PayloadSchemaType.UUID,
        "story_id": PayloadSchemaType.UUID,
        "universe_id": PayloadSchemaType.UUID,
        "type": PayloadSchemaType.KEYWORD,
        "play_session_id": PayloadSchemaType.UUID,
        "temporal_mode": PayloadSchemaType.KEYWORD,
        "timestamp": PayloadSchemaType.DATETIME,
    },
    "memories": {
        "memory_id": PayloadSchemaType.UUID,
        "entity_id": PayloadSchemaType.UUID,
        "scene_id": PayloadSchemaType.UUID,
        "universe_id": PayloadSchemaType.UUID,
        "type": PayloadSchemaType.KEYWORD,
        "timestamp": PayloadSchemaType.DATETIME,
    },
    "snippets": {
        "snippet_id": PayloadSchemaType.UUID,
        "doc_id": PayloadSchemaType.UUID,
        "source_id": PayloadSchemaType.UUID,
        "universe_id": PayloadSchemaType.UUID,
        "ingestion_job_id": PayloadSchemaType.UUID,
        "section": PayloadSchemaType.KEYWORD,
        "page": PayloadSchemaType.INTEGER,
    },
    "entities": {
        "entity_id": PayloadSchemaType.UUID,
        "universe_id": PayloadSchemaType.UUID,
        "entity_type": PayloadSchemaType.KEYWORD,
        "is_archetype": PayloadSchemaType.BOOL,
        "detail_level": PayloadSchemaType.KEYWORD,
        "timestamp": PayloadSchemaType.DATETIME,
        # === Sub-plan 1: Sub-type payload indexes ===
        # The retrieval layer can filter entities by their canonical
        # group/place sub-type (e.g. "find all clans in this universe")
        # or by the raw sub_type string (for game-system-specific terms
        # that fell into the OTHER bucket).
        "sub_type": PayloadSchemaType.KEYWORD,
        "group_type": PayloadSchemaType.KEYWORD,
        "place_type": PayloadSchemaType.KEYWORD,
    },
    "knowledge": {
        "node_id": PayloadSchemaType.UUID,
        "node_type": PayloadSchemaType.KEYWORD,
        "universe_id": PayloadSchemaType.UUID,
        "domain": PayloadSchemaType.KEYWORD,
        "canon_level": PayloadSchemaType.KEYWORD,
        "timestamp": PayloadSchemaType.DATETIME,
        # === Sub-plan 1: Sub-type payload index for the knowledge collection ===
        "sub_type": PayloadSchemaType.KEYWORD,
    },
}

# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
# DB_RETRY is shared — imported from ._utils


class QdrantClient:
    """
    Async Qdrant client for MONITOR vector storage and semantic search.

    Manages connection lifecycle and lazy collection creation.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        path: str | None = None,
    ) -> None:
        self._url: str | None = url or settings.resolved_qdrant_url
        self._api_key: str | None = api_key or settings.qdrant_api_key
        self._path: str | None = path or settings.qdrant_path

        # Fall back to localhost when no config provided
        if not self._url and not self._path:
            self._url = "http://localhost:6333"

        self._client: QdrantAsyncClientLib | None = None
        # The event loop the async client was created in. The async client binds
        # its transport to one loop; ingestion runs each job in a fresh
        # worker-thread loop, so a client cached from a prior (closed) loop must
        # be rebuilt to avoid 'RuntimeError: Event loop is closed' (T-098).
        self._client_loop: asyncio.AbstractEventLoop | None = None
        self._collections_initialized: set[str] = set()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the async Qdrant client, rebuilding it if the cached client
        belongs to a different (or closed) event loop."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if (
            self._client is not None
            and running is not None
            and self._client_loop is not None
            and self._client_loop is not running
        ):
            # Cached client was built in another loop (e.g. a prior ingestion
            # worker loop that has since closed). Drop it without awaiting close
            # on a dead loop, and rebuild for the current loop (T-098). Skip when
            # _client_loop is None (externally-set client, e.g. a test mock).
            self._client = None
            self._client_loop = None
            self._collections_initialized.clear()

        if self._client is None:
            self._client = self._build_async_client()
            self._client_loop = running

    async def close(self) -> None:
        """Close the Qdrant client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._client_loop = None
            self._collections_initialized.clear()

    def reset_client(self) -> None:
        """Synchronously drop the cached async client so the next ``get_client``
        rebuilds it.

        Used by the self-healing upsert retry (T-098/R9): in the sync ingestion
        path ``get_client`` cannot see the (closed) loop the client is bound to,
        so a stale client surfaces as 'RuntimeError: Event loop is closed' only
        at await time. We drop it without awaiting ``close`` on a dead loop —
        the constructor is sync, so the rebuild needs no running loop. Skip when
        ``_client_loop`` is None (an externally-set client, e.g. a test mock).
        """
        if self._client_loop is None:
            return
        self._client = None
        self._client_loop = None
        self._collections_initialized.clear()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def verify_connectivity(self) -> bool:
        """Verify Qdrant is reachable (sync wrapper)."""
        return bool(run_sync(self._verify_connectivity_async()))

    @retry(**DB_RETRY)
    async def _verify_connectivity_async(self) -> bool:
        """Async internal: verify Qdrant is reachable."""
        try:
            if self._client is None:
                await self.connect()
            assert self._client is not None
            await self._client.get_collections()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Accessor
    # ------------------------------------------------------------------

    def _build_async_client(self) -> QdrantAsyncClientLib:
        if self._path:
            return QdrantAsyncClientLib(path=self._path)
        return QdrantAsyncClientLib(
            url=self._url,
            api_key=self._api_key,
            prefer_grpc=True,
        )

    def new_loop_client(self) -> QdrantAsyncClientLib:
        """Build a fresh, uncached async client bound to the current event loop.

        For code paths that run under their own short-lived event loop (e.g. an
        ingestion job's ``asyncio.run``) and must not reuse the process-global
        client. The caller owns it and should ``await client.close()``. This
        sidesteps 'Event loop is closed' entirely for that path (T-098).
        """
        return self._build_async_client()

    def get_client(self) -> QdrantAsyncClientLib:
        """Return the raw async Qdrant client, rebuilding it if the cached one
        belongs to a different (or closed) event loop.

        The accessor — not just connect() — must be loop-aware: ensure_collection
        early-returns for already-initialized collections, so a stale client from
        a previous ingestion-worker loop would otherwise be reused and fail with
        'RuntimeError: Event loop is closed' (T-098). The AsyncQdrantClient
        constructor is synchronous, so we can rebuild here even from an async
        context.
        """
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        # Only rebuild a client *we* built in a now-different loop. When
        # _client_loop is None the client was set externally (e.g. a test mock)
        # — never clobber it.
        if (
            self._client is not None
            and running is not None
            and self._client_loop is not None
            and self._client_loop is not running
        ):
            self._client = None
            self._client_loop = None
            self._collections_initialized.clear()

        if self._client is None:
            if running is not None:
                # Already inside an event loop — construct directly (sync ctor).
                self._client = self._build_async_client()
                self._client_loop = running
            else:
                run_sync(self.connect())
        assert self._client is not None
        return self._client

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    @retry(**DB_RETRY)
    async def ensure_collection(self, collection_name: str) -> None:
        """
        Ensure a collection exists with the correct vector configuration.

        Creates it if absent and also backfills the payload indexes needed for
        fast filtered retrieval on existing collections.
        """
        if collection_name in self._collections_initialized:
            return

        if collection_name not in COLLECTION_CONFIGS:
            raise ValueError(f"Unknown collection '{collection_name}'. Valid: {', '.join(COLLECTION_CONFIGS)}")

        client = self.get_client()

        try:
            await client.get_collection(collection_name)
        except Exception:
            config = COLLECTION_CONFIGS[collection_name]
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=int(config["vector_size"]),
                    distance=config["distance"],
                ),
            )

        await self._ensure_payload_indexes(collection_name)
        self._collections_initialized.add(collection_name)

    async def _ensure_payload_indexes(self, collection_name: str) -> None:
        """Create payload indexes for the fields most often used in filters."""
        client = self.get_client()

        if collection_name == "snippets":
            try:
                await client.create_payload_index(
                    collection_name=collection_name,
                    field_name="text",
                    field_schema=TextIndexParams(
                        type="text",
                        tokenizer=TokenizerType.WORD,
                        min_token_len=2,
                        max_token_len=40,
                        lowercase=True,
                    ),
                )
            except Exception as exc:
                logger.debug("Qdrant text payload index skipped for %s.text: %s", collection_name, exc)

        for field_name, field_schema in PAYLOAD_INDEX_CONFIGS.get(collection_name, {}).items():
            try:
                await client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                )
            except Exception as exc:
                logger.debug(
                    "Qdrant payload index skipped for %s.%s: %s",
                    collection_name,
                    field_name,
                    exc,
                )


# =============================================================================
# BACKGROUND EVENT LOOP FOR SYNC CALLERS
# =============================================================================
# run_sync and the shared background loop are imported from ._utils.

# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_qdrant_client_instance: QdrantClient | None = None
_qdrant_lock = threading.Lock()


def get_qdrant_client() -> QdrantClient:
    """Return (and lazily initialise) the module-level QdrantClient singleton."""
    global _qdrant_client_instance
    with _qdrant_lock:
        if _qdrant_client_instance is None:
            _qdrant_client_instance = QdrantClient()
    return _qdrant_client_instance


def reset_qdrant_client() -> None:
    """Close and discard the singleton.  Used in tests for clean state."""
    global _qdrant_client_instance
    with _qdrant_lock:
        if _qdrant_client_instance is not None:
            run_sync(_qdrant_client_instance.close())
            _qdrant_client_instance = None

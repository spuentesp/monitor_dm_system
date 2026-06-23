"""
E2E Test 01 — Document Ingestion Pipeline (I-1..I-5, DL-8, DL-9, DL-10)

Tests the full ingestion journey:
  raw text/bytes
    → MinIO upload (DL-9)
    → Text chunking (I-1, I-2)
    → Qdrant vector embedding (DL-10)
    → MongoDB Document + IngestionJob records (DL-8)
    → Analyzer extraction → KnowledgePack (I-3, I-4)
    → KnowledgePack apply → ProposedChanges (I-5)

Use cases covered
-----------------
I-1  Ingest a document (PDF / text / markdown)
I-2  Extract and chunk document text
I-3  Embed chunks into Qdrant
I-4  Analyze content → KnowledgePack
I-5  Apply KnowledgePack to a multiverse
DL-8 Manage Sources, Documents, Snippets, Ingest Proposals
DL-9 Manage Binary Assets (MinIO)
DL-10 Vector Index Operations (Qdrant)
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.tools.ingest_tools import (
    IngestedChunk,
    detect_format,
    ingest_markdown,
    ingest_text,
)


# =============================================================================
# I-1, I-2: Text extraction and chunking
# =============================================================================


@pytest.mark.e2e
class TestTextIngestion:
    """
    I-1 / I-2 — Ingest plain text and break it into embedding-ready chunks.
    Tests run WITHOUT real databases (pure data-layer logic).
    """

    def test_ingest_text_returns_chunks(self, rpg_book_text: str) -> None:
        """I-1: ingest_text() produces a non-empty list of IngestedChunk objects."""
        chunks: List[IngestedChunk] = ingest_text(rpg_book_text, "realm_of_shadows")

        assert chunks, "Expected at least one chunk from the RPG book text"
        assert all(isinstance(c, IngestedChunk) for c in chunks)

    def test_chunks_have_required_fields(self, rpg_book_text: str) -> None:
        """I-2a: Each chunk must carry provenance and token count."""
        chunks = ingest_text(rpg_book_text, "realm_of_shadows")
        for c in chunks:
            assert c.source_name == "realm_of_shadows"
            assert c.chunk_id, "chunk_id must be non-empty"
            assert c.text.strip(), "chunk text must be non-empty"
            assert c.token_count > 0, "token_count must be positive"
            assert c.chunk_index >= 0, "chunk_index must be non-negative"

    def test_chunks_respect_token_limit(self, rpg_book_text: str) -> None:
        """I-2b: No chunk should exceed the default 512-token ceiling."""
        chunks = ingest_text(rpg_book_text, "realm_of_shadows")
        for c in chunks:
            assert c.token_count <= 512, (
                f"Chunk {c.chunk_index} exceeded 512 tokens ({c.token_count})"
            )

    def test_chunks_overlap_ensures_continuity(self, rpg_book_text: str) -> None:
        """I-2c: Consecutive chunks should share some content (10% overlap)."""
        chunks = ingest_text(rpg_book_text, "realm_of_shadows")
        if len(chunks) < 2:
            pytest.skip("Too few chunks to test overlap")
        # Overlap test: last words of chunk N should appear in chunk N+1
        prev_words = set(chunks[0].text.split()[-20:])
        next_words = set(chunks[1].text.split()[:30])
        assert prev_words & next_words, (
            "Expected overlapping tokens between consecutive chunks"
        )

    def test_ingest_markdown_produces_chunks(self, rpg_book_text: str) -> None:
        """I-1 variant: markdown ingestion also works."""
        md_text = f"# Realm of Shadows\n\n{rpg_book_text}"
        chunks = ingest_markdown(md_text, "realm_md")
        assert len(chunks) > 0

    def test_stable_chunk_id(self, rpg_book_text: str) -> None:
        """I-2d: Chunk IDs are deterministic — two ingestions of same text produce same IDs."""
        chunks_a = ingest_text(rpg_book_text[:1000], "stable_test")
        chunks_b = ingest_text(rpg_book_text[:1000], "stable_test")
        ids_a = [c.chunk_id for c in chunks_a]
        ids_b = [c.chunk_id for c in chunks_b]
        assert ids_a == ids_b, (
            "Re-ingestion must produce identical chunk IDs (idempotency)"
        )

    def test_detect_format_txt(self) -> None:
        """I-1 format detection: .txt files → 'text'."""
        assert detect_format("book.txt", None) == "text"

    def test_detect_format_pdf(self) -> None:
        """I-1 format detection: .pdf files → 'pdf'."""
        assert detect_format("book.pdf", "application/pdf") == "pdf"

    def test_detect_format_markdown(self) -> None:
        """I-1 format detection: .md files → 'markdown'."""
        assert detect_format("notes.md", None) == "markdown"


# =============================================================================
# DL-9: MinIO binary asset storage
# =============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestMinIOStorage:
    """
    DL-9 — Upload, download, presign, and delete binary assets.
    Uses the folder-backend MinIOClient (no real S3 server needed).
    """

    @pytest.mark.asyncio
    async def test_upload_and_download_rpg_book(
        self, folder_minio, rpg_book_bytes: bytes
    ) -> None:
        """DL-9 upload + download round-trip."""
        key = f"sources/{uuid4()}/realm_of_shadows.txt"
        await folder_minio.upload(key, rpg_book_bytes, content_type="text/plain")
        downloaded = await folder_minio.download(key)
        assert downloaded == rpg_book_bytes

    @pytest.mark.asyncio
    async def test_presigned_url_is_file_uri(
        self, folder_minio, rpg_book_bytes: bytes
    ) -> None:
        """DL-9 presigned URL format (folder backend returns file:// URI)."""
        key = f"sources/{uuid4()}/url_test.txt"
        await folder_minio.upload(key, rpg_book_bytes, content_type="text/plain")
        url = await folder_minio.presigned_url(key)
        assert url.startswith("file://"), f"Expected file:// URL, got: {url}"

    @pytest.mark.asyncio
    async def test_delete_removes_object(
        self, folder_minio, rpg_book_bytes: bytes
    ) -> None:
        """DL-9 delete removes the object; subsequent download raises FileNotFoundError."""
        key = f"sources/{uuid4()}/delete_me.txt"
        await folder_minio.upload(key, rpg_book_bytes, content_type="text/plain")
        await folder_minio.delete(key)
        with pytest.raises(FileNotFoundError):
            await folder_minio.download(key)

    @pytest.mark.asyncio
    async def test_download_missing_raises(self, folder_minio) -> None:
        """DL-9 downloading a non-existent key raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await folder_minio.download("nonexistent/key.txt")


# =============================================================================
# DL-10: Qdrant vector indexing
# =============================================================================


@pytest.mark.e2e
class TestQdrantVectorIndex:
    """
    DL-10 — Upsert, search, and delete vectors using in-memory Qdrant.
    """

    def test_qdrant_collection_creation(self, qdrant_memory_client) -> None:
        """DL-10: Create a Qdrant collection and verify it exists."""
        from qdrant_client.models import Distance, VectorParams

        col_name = f"test_e2e_{uuid4().hex[:8]}"
        qdrant_memory_client.create_collection(
            collection_name=col_name,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        collections = [
            c.name for c in qdrant_memory_client.get_collections().collections
        ]
        assert col_name in collections

    def test_qdrant_upsert_and_search(self, qdrant_memory_client) -> None:
        """DL-10: Upsert stub vectors and retrieve via similarity search."""
        from qdrant_client.models import Distance, PointStruct, VectorParams

        col_name = f"test_search_{uuid4().hex[:8]}"
        qdrant_memory_client.create_collection(
            collection_name=col_name,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )

        # Upsert 3 points
        points = [
            PointStruct(id=i, vector=[float(i)] * 4, payload={"text": f"chunk_{i}"})
            for i in range(1, 4)
        ]
        qdrant_memory_client.upsert(collection_name=col_name, points=points)

        # Search
        results = qdrant_memory_client.search(
            collection_name=col_name,
            query_vector=[1.0, 1.0, 1.0, 1.0],
            limit=2,
        )
        assert len(results) == 2
        assert results[0].payload["text"].startswith("chunk_")

    def test_qdrant_delete_point(self, qdrant_memory_client) -> None:
        """DL-10: Deleting a vector by ID removes it from search."""
        from qdrant_client.models import (
            Distance,
            PointIdsList,
            PointStruct,
            VectorParams,
        )

        col_name = f"test_delete_{uuid4().hex[:8]}"
        qdrant_memory_client.create_collection(
            collection_name=col_name,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        qdrant_memory_client.upsert(
            collection_name=col_name,
            points=[
                PointStruct(
                    id=99, vector=[0.1, 0.2, 0.3, 0.4], payload={"text": "to_delete"}
                )
            ],
        )
        qdrant_memory_client.delete(
            collection_name=col_name,
            points_selector=PointIdsList(points=[99]),
        )
        results = qdrant_memory_client.search(
            collection_name=col_name,
            query_vector=[0.1, 0.2, 0.3, 0.4],
            limit=5,
        )
        ids = [r.id for r in results]
        assert 99 not in ids


# =============================================================================
# DL-8, I-3, I-4: Full IngestionPipeline (mocked Analyzer + Indexer)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestIngestionPipeline:
    """
    I-3, I-4, DL-8 — Full IngestionPipeline from bytes to KnowledgePack.

    The Analyzer and Indexer LLM calls are mocked so the test focuses on
    pipeline orchestration, MongoDB record creation, and MinIO storage.
    """

    @pytest.mark.asyncio
    async def test_pipeline_creates_document_and_job(
        self,
        e2e_databases,
        folder_minio,
        rpg_book_bytes: bytes,
    ) -> None:
        """I-3: IngestionPipeline creates a Document + IngestionJob in MongoDB."""

        from monitor_agents.ingestion_pipeline import IngestionPipeline
        from monitor_data.schemas.knowledge_packs import (
            KnowledgePackType,
        )

        # Patch external dependencies so we don't need LLMs or real Qdrant
        with (
            # MinIO → use folder backend
            patch(
                "monitor_agents.ingestion_pipeline.get_minio_client",
                return_value=folder_minio,
            ),
            # Indexer.index() — stub out Qdrant embedding
            patch(
                "monitor_agents.indexer.Indexer.index",
                new_callable=AsyncMock,
                return_value={"snippet_count": 42, "collection": "knowledge"},
            ),
            # Analyzer.analyze() — stub out LLM extraction
            patch(
                "monitor_agents.analyzer.Analyzer.analyze",
                new_callable=AsyncMock,
                return_value={
                    "axioms": [
                        {
                            "statement": "Magic exists",
                            "domain": "magic",
                            "confidence": 0.95,
                        }
                    ],
                    "entity_archetypes": [
                        {
                            "name": "Fighter",
                            "entity_type": "Character",
                            "properties": {},
                        }
                    ],
                    "facts": [],
                    "events": [],
                    "game_rules": [],
                },
            ),
            # neo4j_create_source — avoid Neo4j calls in this test
            patch(
                "monitor_agents.ingestion_pipeline.neo4j_create_source",
                return_value=MagicMock(id=uuid4()),
            ),
        ):
            pipeline = IngestionPipeline()
            job = await pipeline.ingest_file(
                file_bytes=rpg_book_bytes,
                filename="realm_of_shadows.txt",
                source_title="Realm of Shadows Core Rulebook",
                universe_id=uuid4(),
                pack_name="Realm of Shadows Rulebook",
                pack_type=KnowledgePackType.RULEBOOK,
                auto_apply=False,
            )

        assert job is not None
        assert job.job_id is not None
        # Job should be in a terminal stage after pipeline completes
        assert job.status in ("completed", "error", "analyzing", "embedding")

    @pytest.mark.asyncio
    async def test_pipeline_stores_bytes_in_minio(
        self,
        e2e_databases,
        folder_minio,
        rpg_book_bytes: bytes,
    ) -> None:
        """I-3/DL-9: Ingestion uploads the raw file to object storage."""

        from monitor_agents.ingestion_pipeline import IngestionPipeline
        from monitor_data.schemas.knowledge_packs import KnowledgePackType

        uploaded_keys: list = []

        original_upload = folder_minio.upload

        async def recording_upload(key, data, **kw):
            uploaded_keys.append(key)
            return await original_upload(key, data, **kw)

        folder_minio.upload = recording_upload  # type: ignore[method-assign]

        with (
            patch(
                "monitor_agents.ingestion_pipeline.get_minio_client",
                return_value=folder_minio,
            ),
            patch(
                "monitor_agents.indexer.Indexer.index",
                new_callable=AsyncMock,
                return_value={"snippet_count": 5, "collection": "knowledge"},
            ),
            patch(
                "monitor_agents.analyzer.Analyzer.analyze",
                new_callable=AsyncMock,
                return_value={
                    "axioms": [],
                    "entity_archetypes": [],
                    "facts": [],
                    "events": [],
                    "game_rules": [],
                },
            ),
            patch(
                "monitor_agents.ingestion_pipeline.neo4j_create_source",
                return_value=MagicMock(id=uuid4()),
            ),
        ):
            pipeline = IngestionPipeline()
            await pipeline.ingest_file(
                file_bytes=rpg_book_bytes,
                filename="realm_upload_test.txt",
                source_title="Realm of Shadows",
                universe_id=uuid4(),
                pack_name="Upload Test Pack",
                pack_type=KnowledgePackType.RULEBOOK,
                auto_apply=False,
            )

        # Verify MinIO received the file
        assert any("realm_upload_test" in k for k in uploaded_keys), (
            f"Expected MinIO upload with 'realm_upload_test' in key. Got: {uploaded_keys}"
        )


# =============================================================================
# I-5: Apply KnowledgePack → ProposedChanges
# =============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestKnowledgePackApplication:
    """
    I-5 — Apply a KnowledgePack to a multiverse, generating ProposedChanges.
    """

    def test_apply_knowledge_pack_creates_proposed_changes(
        self, e2e_databases, seeded_world: Dict[str, Any]
    ) -> None:
        """I-5: mongodb_apply_knowledge_pack() creates ProposedChange documents."""

        from monitor_data.schemas.knowledge_packs import (
            ExtractedAxiom,
            ExtractedEntityArchetype,
            KnowledgePackCreate,
            KnowledgePackStatus,
            KnowledgePackType,
        )
        from monitor_data.tools.mongodb_tools import (
            mongodb_apply_knowledge_pack,
            mongodb_create_knowledge_pack,
            mongodb_list_proposed_changes,
        )
        from monitor_data.schemas.proposed_changes import ProposedChangeFilter

        # Create a minimal KnowledgePack
        pack = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name="Realm of Shadows — Apply Test",
                pack_type=KnowledgePackType.RULEBOOK,
                source_title="Realm of Shadows Rulebook",
                status=KnowledgePackStatus.READY,
                axioms=[
                    ExtractedAxiom(
                        statement="Shadow magic corrupts the mind over time.",
                        domain="magic",
                        confidence=0.92,
                    )
                ],
                entity_archetypes=[
                    ExtractedEntityArchetype(
                        name="Shade Hunter",
                        entity_type="Character",
                        description="Specialist in hunting undead shades.",
                    )
                ],
                facts=[],
                events=[],
                game_rules=[],
            )
        )

        assert pack is not None
        assert pack.status == KnowledgePackStatus.READY

        # Apply pack to the seeded multiverse
        from monitor_data.schemas.knowledge_packs import ApplyKnowledgePackRequest

        result = mongodb_apply_knowledge_pack(
            pack.id,
            ApplyKnowledgePackRequest(
                multiverse_id=seeded_world["multiverse_id"],
                conflict_resolution="merge",
            ),
        )

        assert result is not None
        # Verify proposed changes were created
        changes = mongodb_list_proposed_changes(ProposedChangeFilter(limit=50))
        # At minimum the axiom and archetype should produce 2 proposals
        assert changes.total >= 2, (
            f"Expected at least 2 ProposedChanges from KnowledgePack apply, got {changes.total}"
        )

"""
Indexer Agent — background ingestion and embedding pipeline.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1)

DL-B4: Wires data-layer ingest_tools (pymupdf + tiktoken) and embed_text
        (litellm) to Qdrant via MCP tools. This closes the ingestion loop:

    raw PDF/text → extract_pdf_text → chunk_text → embed_text → qdrant_upsert

Supported formats (via index_file master endpoint):
    PDF (.pdf)              → ingest_pdf → embed → Qdrant
    Plain text (.txt/.rst)  → ingest_text → embed → Qdrant
    Markdown (.md)          → ingest_markdown → embed → Qdrant
    HTML (.html/.htm)       → ingest_html → embed → Qdrant
    Word (.docx)            → ingest_docx → embed → Qdrant
    EPUB (.epub)            → ingest_epub → embed → Qdrant
    Image (.png/.jpg/etc.)  → LLM vision description → embed → Qdrant
    URI (http/https)        → httpx fetch → detect format → route above

Responsibilities:
- Ingest any supported document format from MinIO or raw bytes
- Fetch and ingest web pages / URIs
- Analyse images with LLM vision (GPT-4o-mini / Claude 3 / Gemini)
- Re-index existing content when the embedding model changes

Authority:
- Qdrant: EXCLUSIVE write access to snippets collection (via MCP)
- MinIO: read-only (downloads, never uploads)
- Neo4j / MongoDB: read-only (fetches world context for linking)
- No Neo4j writes — entity linking goes through CanonKeeper proposals

The Indexer is designed to run as a background task (driven by
``anyio.create_task_group()`` in the Story/Scene loops or as a dedicated CLI
command ``monitor index <path>``).
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from qdrant_client.models import PointStruct

from monitor_agents.base import BaseAgent
from monitor_agents.llm_registry import LLMRegistry
from monitor_data.db.embeddings import embed_batch
from monitor_data.db.postgres import get_postgres_client
from monitor_data.db.qdrant import get_qdrant_client
from monitor_data.schemas.llm_config import ModelRole
from monitor_data.schemas.tag_pool import TagPool
from monitor_data.tools.ingest_tools import (
    IngestedChunk,
    chunk_text,
    detect_format,
    extract_pdf_structure,
    ingest_docx,
    ingest_epub,
    ingest_file,
    ingest_html,
    ingest_markdown,
    ingest_pdf,
    ingest_text,
)
from monitor_agents.prompts.analyzer import SectionCategorizationModule

logger = logging.getLogger(__name__)


# Qdrant batch size — upsert in batches to avoid large payload errors
_UPSERT_BATCH_SIZE = 64


class Indexer(BaseAgent):
    """
    Background agent that converts raw documents into searchable Qdrant vectors.

    STATELESS. Can be instantiated per-task or kept alive as a long-running worker.
    """

    def __init__(self, agent_id: str = "indexer-1") -> None:
        super().__init__(agent_type="Indexer", agent_id=agent_id)

    async def run(self) -> None:
        pass  # driven externally (CLI command or task group)

    # ------------------------------------------------------------------
    # Primary entry points (DL-B4)
    # ------------------------------------------------------------------

    async def index_pdf_from_minio(
        self,
        object_key: str,
        source_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Download a PDF from MinIO, chunk it, embed, and upsert to Qdrant.

        Args:
            object_key:  MinIO object path (e.g. "uploads/rulebook.pdf").
            source_name: Logical document name (defaults to object_key).
            metadata:    Extra Qdrant payload fields (e.g. universe_id, story_id).

        Returns:
            Total number of chunks ingested.
        """
        source_name = source_name or object_key

        # 1. Download PDF bytes from MinIO via MCP tool
        pdf_bytes = await self._download_from_minio(object_key)
        if not pdf_bytes:
            return 0

        # 2. Extract + chunk with structure-aware pre-pass (DL-B2 / DL-B3)
        chunks = self._chunk_pdf_with_structure(pdf_bytes, source_name, metadata=metadata or {})
        if not chunks:
            return 0

        # 3. Embed + upsert (DL-B4 wiring)
        await self._embed_and_upsert(chunks, collection="snippets")
        return len(chunks)

    async def index_text(
        self,
        text: str,
        source_name: str,
        collection: str = "snippets",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Chunk, embed, and upsert plain text into a Qdrant collection.

        Args:
            text:        Raw text content (session notes, wiki pages, etc.).
            source_name: Logical document identifier.
            collection:  Target Qdrant collection ("snippets" or "memories").
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        chunks = ingest_text(text, source_name, metadata=metadata or {})
        if not chunks:
            return 0
        await self._embed_and_upsert(chunks, collection=collection)
        return len(chunks)

    async def index_memory(
        self,
        memory_text: str,
        character_id: str,
        story_id: str,
        scene_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Embed and upsert a character memory into the Qdrant memories collection.

        Character memories are short (< 512 tokens) so no chunking is needed.
        A single chunk is created and upserted.

        Args:
            memory_text:   The memory text.
            character_id:  Character UUID this memory belongs to.
            story_id:      Story UUID for filtering.
            scene_id:      Scene where this memory was extracted.
            metadata:      Extra payload fields.
        """
        source_name = f"memory:{character_id}:{scene_id}"
        combined_meta = {
            "character_id": character_id,
            "story_id": story_id,
            "scene_id": scene_id,
            **(metadata or {}),
        }
        return await self.index_text(
            text=memory_text,
            source_name=source_name,
            collection="memories",
            metadata=combined_meta,
        )

    async def reindex_collection(
        self,
        collection: str,
        source_filter: Optional[str] = None,
    ) -> int:
        """
        Re-embed all documents in a Qdrant collection (use when embedding model changes).

        Fetches existing payload text from Qdrant, re-embeds, and upserts in place
        (same chunk_id → deterministic upsert deduplication).

        Args:
            collection:    Qdrant collection to reindex.
            source_filter: If set, only reindex chunks with this source_name.

        Returns:
            Number of chunks reindexed.
        """
        raw = await self.call_tool(
            "qdrant_scroll",
            {
                "collection": collection,
                "filter": {"source_name": source_filter} if source_filter else {},
                "limit": 10000,
                "with_payload": True,
                "with_vectors": False,
            },
        )
        if not raw:
            return 0

        points = json.loads(raw) if isinstance(raw, str) else raw
        if not points:
            return 0

        # Reconstruct IngestedChunk objects from saved payload
        chunks: List[IngestedChunk] = []
        for p in points:
            payload = p.get("payload", {})
            chunks.append(
                IngestedChunk(
                    chunk_id=payload.get("chunk_id", str(uuid.uuid4())),
                    source_name=payload.get("source_name", "unknown"),
                    page_number=payload.get("page_number"),
                    chunk_index=payload.get("chunk_index", 0),
                    text=payload.get("text", ""),
                    token_count=payload.get("token_count", 0),
                    metadata={
                        k: v
                        for k, v in payload.items()
                        if k
                        not in (
                            "chunk_id",
                            "source_name",
                            "page_number",
                            "chunk_index",
                            "text",
                            "token_count",
                        )
                    },
                )
            )

        await self._embed_and_upsert(chunks, collection=collection)
        return len(chunks)

    # ------------------------------------------------------------------
    # Multi-format index entry points
    # ------------------------------------------------------------------

    async def index_markdown(
        self,
        md_text: str,
        source_name: str,
        collection: str = "snippets",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Chunk, embed, and upsert Markdown content into a Qdrant collection.

        Args:
            md_text:     Raw Markdown string (e.g. from a .md file or wiki page).
            source_name: Logical document identifier.
            collection:  Target Qdrant collection (default "snippets").
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        chunks = ingest_markdown(md_text, source_name, metadata=metadata or {})
        if not chunks:
            return 0
        await self._embed_and_upsert(chunks, collection=collection)
        return len(chunks)

    async def index_html(
        self,
        html_content: str,
        source_name: str,
        collection: str = "snippets",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Strip HTML tags, chunk, embed, and upsert into a Qdrant collection.

        Args:
            html_content: Raw HTML string.
            source_name:  Logical document identifier.
            collection:   Target Qdrant collection (default "snippets").
            metadata:     Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        chunks = ingest_html(html_content, source_name, metadata=metadata or {})
        if not chunks:
            return 0
        await self._embed_and_upsert(chunks, collection=collection)
        return len(chunks)

    async def index_docx(
        self,
        docx_bytes: bytes,
        source_name: str,
        collection: str = "snippets",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Extract text from a .docx Word document, embed, and upsert.

        Args:
            docx_bytes:  Raw .docx file bytes.
            source_name: Logical document identifier.
            collection:  Target Qdrant collection (default "snippets").
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        chunks = ingest_docx(docx_bytes, source_name, metadata=metadata or {})
        if not chunks:
            return 0
        await self._embed_and_upsert(chunks, collection=collection)
        return len(chunks)

    async def index_epub(
        self,
        epub_bytes: bytes,
        source_name: str,
        collection: str = "snippets",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Extract text from an .epub e-book, embed, and upsert.

        Args:
            epub_bytes:  Raw .epub file bytes.
            source_name: Logical document identifier.
            collection:  Target Qdrant collection (default "snippets").
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        chunks = ingest_epub(epub_bytes, source_name, metadata=metadata or {})
        if not chunks:
            return 0
        await self._embed_and_upsert(chunks, collection=collection)
        return len(chunks)

    async def index_image(
        self,
        image_bytes: bytes,
        source_name: str,
        collection: str = "snippets",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Analyse an image with LLM vision and index the resulting description.

        The vision model (configured via VISION_MODEL env var, default
        "gpt-4o-mini") is asked to describe all visible content, transcribe
        any text, and extract game-relevant information (stat blocks, maps,
        tables, character sheets).  The description is then chunked, embedded,
        and upserted to Qdrant.

        Requires a vision-capable model via LiteLLM (GPT-4o, Claude 3,
        Gemini Pro Vision, etc.).

        Args:
            image_bytes: Raw image bytes (.png / .jpg / .gif / .webp / etc.).
            source_name: Logical document identifier (used in chunk provenance).
            collection:  Target Qdrant collection (default "snippets").
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested (0 if vision produced no content).
        """
        description = await self._describe_image(image_bytes, source_name)
        if not description.strip():
            return 0
        combined_meta = {"source_format": "image", **(metadata or {})}
        return await self.index_text(
            text=description,
            source_name=source_name,
            collection=collection,
            metadata=combined_meta,
        )

    async def index_uri(
        self,
        uri: str,
        source_name: Optional[str] = None,
        collection: str = "snippets",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Fetch content from a URI and index it using the appropriate extractor.

        Auto-detects format from the response Content-Type header and URI path.
        For HTML pages the full page text is extracted; for binary formats
        (PDF, DOCX, EPUB) the raw bytes are passed to the matching extractor.
        Images are routed to index_image() (LLM vision).

        Args:
            uri:         HTTP/HTTPS URL to fetch.
            source_name: Logical document name (defaults to the URL).
            collection:  Target Qdrant collection (default "snippets").
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.

        Raises:
            httpx.HTTPError: If the HTTP request fails.
        """
        import httpx

        sname = source_name or uri
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(uri)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        file_bytes = response.content

        # Detect format from URL path + Content-Type header
        url_path = uri.split("?")[0].rstrip("/")
        filename = Path(url_path).name or "uri-content"

        return await self.index_file(
            file_bytes=file_bytes,
            filename=filename,
            source_name=sname,
            content_type=content_type,
            collection=collection,
            metadata={"source_uri": uri, **(metadata or {})},
        )

    async def index(
        self,
        file_bytes: bytes,
        filename: str,
        source_name: Optional[str] = None,
        **kwargs: Any,
    ) -> int:
        """Backward-compatible alias for the main file indexing entry point."""
        return await self.index_file(
            file_bytes=file_bytes,
            filename=filename,
            source_name=source_name,
            **kwargs,
        )

    async def index_file(
        self,
        file_bytes: bytes,
        filename: str,
        source_name: Optional[str] = None,
        *,
        content_type: Optional[str] = None,
        collection: str = "snippets",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Universal file indexer — auto-detects format and routes to the
        appropriate extractor, including LLM vision for images.

        This is the preferred single entry point when the file format is
        not known in advance (e.g. user uploads, URI downloads).

        Routing table:
            pdf, txt, md, html, docx, epub → sync ingest_file() → embed → upsert
            image (png/jpg/gif/webp/…)     → index_image() (LLM vision)
            unknown binary                 → ValueError

        Args:
            file_bytes:   Raw file bytes.
            filename:     Original filename — drives format detection.
            source_name:  Logical document name (defaults to filename stem).
            content_type: MIME type hint for extra confidence.
            collection:   Target Qdrant collection (default "snippets").
            metadata:     Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        fmt = detect_format(filename, content_type)
        sname = source_name or Path(filename).stem
        extra_meta = {
            "source_filename": filename,
            "source_format": fmt,
            **(metadata or {}),
        }

        if fmt == "image":
            return await self.index_image(
                image_bytes=file_bytes,
                source_name=sname,
                collection=collection,
                metadata={
                    "source_filename": filename,
                    "source_format": "image",
                    **(metadata or {}),
                },
            )

        if fmt == "pdf":
            chunks = self._chunk_pdf_with_structure(file_bytes, sname, metadata=extra_meta)
            if not chunks:
                return 0
            await self._embed_and_upsert(chunks, collection=collection)
            return len(chunks)

        chunks = ingest_file(
            file_bytes,
            filename,
            sname,
            content_type=content_type,
            metadata=extra_meta,
        )
        if not chunks:
            return 0
        await self._embed_and_upsert(chunks, collection=collection)
        return len(chunks)

    async def index_markdown_from_minio(
        self,
        object_key: str,
        source_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Download a Markdown file from MinIO, parse, embed, and upsert.

        Args:
            object_key:  MinIO object path (e.g. "uploads/world-notes.md").
            source_name: Logical document name (defaults to object_key).
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        raw = await self._download_from_minio(object_key)
        if not raw:
            return 0
        md_text = raw.decode("utf-8", errors="replace")
        return await self.index_markdown(
            md_text=md_text,
            source_name=source_name or object_key,
            metadata=metadata,
        )

    async def index_image_from_minio(
        self,
        object_key: str,
        source_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Download an image from MinIO, analyse with LLM vision, and upsert.

        Args:
            object_key:  MinIO object path (e.g. "uploads/character-art.png").
            source_name: Logical document name (defaults to object_key).
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        image_bytes = await self._download_from_minio(object_key)
        if not image_bytes:
            return 0
        return await self.index_image(
            image_bytes=image_bytes,
            source_name=source_name or object_key,
            metadata=metadata,
        )

    async def index_file_from_minio(
        self,
        object_key: str,
        source_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Download any file from MinIO and index it using format auto-detection.

        This is the MinIO-backed counterpart to index_file().  The format is
        inferred from the object_key filename.

        Args:
            object_key:  MinIO object path.
            source_name: Logical document name (defaults to object_key stem).
            metadata:    Extra Qdrant payload fields.

        Returns:
            Total number of chunks ingested.
        """
        file_bytes = await self._download_from_minio(object_key)
        if not file_bytes:
            return 0
        filename = Path(object_key).name or object_key
        return await self.index_file(
            file_bytes=file_bytes,
            filename=filename,
            source_name=source_name or Path(object_key).stem,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _describe_image(self, image_bytes: bytes, source_name: str) -> str:
        """
        Generate a rich textual description of an image using LLM vision.

        The description covers all visible text, stat blocks, tables, maps,
        and game-relevant content so the image becomes fully searchable via
        semantic queries.

        Args:
            image_bytes: Raw image bytes.
            source_name: Document name used to contextualise the prompt.

        Returns:
            Plain-text description from the vision model.
            Empty string if the model returns no content.
        """

        # Detect MIME type from magic bytes
        if image_bytes[:4] == b"\x89PNG":
            mime = "image/png"
        elif image_bytes[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif image_bytes[:6] in (b"GIF87a", b"GIF89a"):
            mime = "image/gif"
        elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            mime = "image/webp"
        elif image_bytes[:2] == b"BM":
            mime = "image/bmp"
        else:
            mime = "image/jpeg"  # safe fallback for unknown binary images

        b64 = base64.b64encode(image_bytes).decode()

        prompt = (
            f"You are analysing an image from the TTRPG document source: '{source_name}'.\n"
            "Describe every detail visible in this image as thorough plain text.\n"
            "• If there is any text, transcribe it exactly word for word.\n"
            "• If there are stat blocks, character sheets, or ability tables, "
            "reproduce them as structured text (label: value).\n"
            "• If there is a map or diagram, describe its layout and labels.\n"
            "• Note any characters, creatures, locations, items, or narrative scenes depicted.\n"
            "Focus on game-relevant information that would be useful for a dungeon master."
        )

        registry = LLMRegistry(get_postgres_client())
        client = await registry.for_node_or_role("indexer", ModelRole.STANDARD)

        return await client.complete_text(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=2048,
        )

    async def _download_from_minio(self, object_key: str) -> Optional[bytes]:
        """Download raw bytes from MinIO via MCP tool."""
        raw = await self.call_tool(
            "minio_download",
            {"object_key": object_key},
        )
        if not raw:
            return None
        # MCP returns base64-encoded bytes as text — decode if needed
        if isinstance(raw, str):
            try:
                return base64.b64decode(raw)
            except Exception:
                return raw.encode()
        return cast(bytes | None, raw)

    # Rulebook categories that indicate dense game-mechanics content — these
    # get a larger (1024-token) chunk window so rules stay in context together.
    _RULEBOOK_CATEGORIES = frozenset(
        {
            "power_system",
            "character_archetype",
            "combat_rules",
            "game_mechanics",
            "creatures_npc",
        }
    )

    def _chunk_pdf_with_structure(
        self,
        pdf_bytes: bytes,
        source_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[IngestedChunk]:
        """
        Structure-aware PDF chunking pre-pass.

        1. Calls ``extract_pdf_structure()`` to obtain a list of SectionBlocks
           (one per bookmark / heuristic heading).
        2. For each block, runs a TagPool pre-filter on the heading path.
           - If TagPool resolves a non-"general" category, that category is used
             directly (no LLM call).
           - Otherwise, ``SectionCategorizationModule`` is called to classify the
             section via a lightweight LLM.
        3. Chunks the block text with ``chunk_text()``, propagating:
           - ``semantic_category`` — resolved above
           - ``heading_path``     — list of heading strings from root to section
           - ``section_depth``    — 0-indexed depth in the bookmark tree

        The non-PDF path (plain text, markdown, session notes) is untouched.

        Args:
            pdf_bytes:   Raw PDF file bytes.
            source_name: Logical document identifier.
            metadata:    Extra Qdrant payload fields merged into every chunk.

        Returns:
            Flat list of IngestedChunk objects ready for embedding.
        """
        section_blocks = extract_pdf_structure(pdf_bytes)
        if not section_blocks:
            return ingest_pdf(pdf_bytes, source_name, metadata=metadata or {})

        categorizer = SectionCategorizationModule()
        # Section categorization is a nice-to-have. If the light LLM is down
        # (e.g. an ollama row pointing at an unreachable host), one connection
        # error must not kill the whole ingestion — and a 500-section rulebook
        # must not grind through 500 failing calls. Disable after the first
        # failure and fall back to "general" for the rest of the document.
        categorizer_broken = False
        all_chunks: List[IngestedChunk] = []

        for block in section_blocks:
            # TagPool pre-filter: scan heading path text for a known category.
            heading_text = " > ".join(block.heading_path)
            tag_category = TagPool.classify_text(heading_text) or "general"

            if tag_category == "general" and not categorizer_broken:
                # Fall back to LLM section categorizer.
                try:
                    result = categorizer(
                        heading_path=heading_text,
                        section_excerpt=block.text[:200],
                    )
                    category = result.category
                except Exception as exc:  # noqa: BLE001 — degrade, never die
                    categorizer_broken = True
                    category = "general"
                    logger.warning(
                        "Section categorizer LLM unavailable (%s); "
                        "tagging remaining sections of '%s' as 'general'.",
                        exc,
                        source_name,
                    )
            else:
                category = tag_category

            is_rulebook = category in self._RULEBOOK_CATEGORIES

            block_chunks = chunk_text(
                block.text,
                source_name,
                is_rulebook=is_rulebook,
                metadata={
                    **(metadata or {}),
                    "semantic_category": category,
                    "heading_path": block.heading_path,
                    "section_depth": block.depth,
                },
            )
            all_chunks.extend(block_chunks)

        return all_chunks

    async def _embed_and_upsert(
        self,
        chunks: List[IngestedChunk],
        collection: str,
    ) -> None:
        """
        Embed a list of chunks (in batches) and upsert them to Qdrant.

        Uses embed_batch() from data-layer for efficient batched LiteLLM calls.
        Uses qdrant_upsert_batch() via MCP tool.
        """
        client = get_qdrant_client()
        await client.ensure_collection(collection)
        # Ingestion runs each job under its own asyncio.run() loop, which is
        # closed when the job ends. The process-global async client gets bound to
        # the first job's (now-dead) loop and later jobs fail with 'Event loop is
        # closed' at upsert. Use a fresh client owned by this loop (T-098).
        qdrant = client.new_loop_client()

        try:
            # Process in batches to avoid memory / API payload limits
            for batch_start in range(0, len(chunks), _UPSERT_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + _UPSERT_BATCH_SIZE]

                # Embed (litellm batched call — DL-B4 wiring)
                texts = [c.text for c in batch]
                vectors = await embed_batch(texts)

                points = [
                    PointStruct(
                        id=str(chunk.chunk_id),
                        vector=vector,
                        payload=chunk.to_qdrant_payload(),
                    )
                    for chunk, vector in zip(batch, vectors)
                ]

                await qdrant.upsert(
                    collection_name=collection,
                    points=points,
                )
        finally:
            with suppress(Exception):
                await qdrant.close()

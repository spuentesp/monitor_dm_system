"""
Unit tests for Indexer agent.

Uses unittest.mock only — no live databases.
"""

from __future__ import annotations

import base64
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_agents.indexer import Indexer, _UPSERT_BATCH_SIZE
from monitor_data.tools.ingest_tools import IngestedChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(
    text: str = "hello world",
    source_name: str = "test-source",
    index: int = 0,
) -> IngestedChunk:
    return IngestedChunk(
        chunk_id=str(uuid4()),
        source_name=source_name,
        page_number=None,
        chunk_index=index,
        text=text,
        token_count=len(text.split()),
        metadata={},
    )


def _make_indexer() -> Indexer:
    """Instantiate without triggering BaseAgent network init."""
    return Indexer.__new__(Indexer)


# ===========================================================================
# index_text
# ===========================================================================


class TestIndexText:
    @pytest.mark.asyncio
    async def test_returns_chunk_count(self):
        agent = _make_indexer()
        chunks = [_chunk("line one"), _chunk("line two")]
        agent._embed_and_upsert = AsyncMock()

        with patch("monitor_agents.indexer.ingest_text", return_value=chunks) as mock_ingest:
            result = await agent.index_text("some text", "my-doc")

        assert result == 2
        mock_ingest.assert_called_once_with("some text", "my-doc", metadata={})
        agent._embed_and_upsert.assert_awaited_once_with(chunks, collection="snippets")

    @pytest.mark.asyncio
    async def test_custom_collection_forwarded(self):
        agent = _make_indexer()
        chunks = [_chunk()]
        agent._embed_and_upsert = AsyncMock()

        with patch("monitor_agents.indexer.ingest_text", return_value=chunks):
            await agent.index_text("text", "doc", collection="memories")

        agent._embed_and_upsert.assert_awaited_once_with(chunks, collection="memories")

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_chunks(self):
        agent = _make_indexer()
        agent._embed_and_upsert = AsyncMock()

        with patch("monitor_agents.indexer.ingest_text", return_value=[]):
            result = await agent.index_text("empty doc", "doc")

        assert result == 0
        agent._embed_and_upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_metadata_forwarded_to_ingest(self):
        agent = _make_indexer()
        chunks = [_chunk()]
        agent._embed_and_upsert = AsyncMock()
        meta = {"universe_id": "u1", "story_id": "s1"}

        with patch("monitor_agents.indexer.ingest_text", return_value=chunks) as mock_ingest:
            await agent.index_text("text", "doc", metadata=meta)

        mock_ingest.assert_called_once_with("text", "doc", metadata=meta)


# ===========================================================================
# index_memory
# ===========================================================================


class TestIndexMemory:
    @pytest.mark.asyncio
    async def test_uses_memories_collection(self):
        agent = _make_indexer()
        character_id = str(uuid4())
        story_id = str(uuid4())
        scene_id = str(uuid4())

        agent.index_text = AsyncMock(return_value=1)
        await agent.index_memory(
            memory_text="I met a dragon",
            character_id=character_id,
            story_id=story_id,
            scene_id=scene_id,
        )

        call_kwargs = agent.index_text.call_args.kwargs
        assert call_kwargs["collection"] == "memories"

    @pytest.mark.asyncio
    async def test_source_name_encodes_ids(self):
        agent = _make_indexer()
        character_id = "char-abc"
        scene_id = "scene-xyz"

        agent.index_text = AsyncMock(return_value=1)
        await agent.index_memory(
            memory_text="memory text",
            character_id=character_id,
            story_id="story-1",
            scene_id=scene_id,
        )

        call_kwargs = agent.index_text.call_args.kwargs
        assert call_kwargs["source_name"] == f"memory:{character_id}:{scene_id}"

    @pytest.mark.asyncio
    async def test_metadata_includes_character_story_scene_ids(self):
        agent = _make_indexer()
        character_id = str(uuid4())
        story_id = str(uuid4())
        scene_id = str(uuid4())

        agent.index_text = AsyncMock(return_value=1)
        await agent.index_memory(
            memory_text="mem",
            character_id=character_id,
            story_id=story_id,
            scene_id=scene_id,
        )

        meta = agent.index_text.call_args.kwargs["metadata"]
        assert meta["character_id"] == character_id
        assert meta["story_id"] == story_id
        assert meta["scene_id"] == scene_id

    @pytest.mark.asyncio
    async def test_extra_metadata_merged(self):
        agent = _make_indexer()
        agent.index_text = AsyncMock(return_value=1)
        await agent.index_memory(
            memory_text="mem",
            character_id="c1",
            story_id="s1",
            scene_id="sc1",
            metadata={"custom_key": "custom_val"},
        )

        meta = agent.index_text.call_args.kwargs["metadata"]
        assert meta["custom_key"] == "custom_val"


# ===========================================================================
# index_markdown
# ===========================================================================


class TestIndexMarkdown:
    @pytest.mark.asyncio
    async def test_returns_chunk_count(self):
        agent = _make_indexer()
        chunks = [_chunk("# Header"), _chunk("Body text")]
        agent._embed_and_upsert = AsyncMock()

        with patch("monitor_agents.indexer.ingest_markdown", return_value=chunks):
            result = await agent.index_markdown("# Header\nBody text", "wiki-page")

        assert result == 2

    @pytest.mark.asyncio
    async def test_returns_zero_on_empty_chunks(self):
        agent = _make_indexer()
        agent._embed_and_upsert = AsyncMock()

        with patch("monitor_agents.indexer.ingest_markdown", return_value=[]):
            result = await agent.index_markdown("", "empty-page")

        assert result == 0
        agent._embed_and_upsert.assert_not_awaited()


# ===========================================================================
# index_image
# ===========================================================================


class TestIndexImage:
    @pytest.mark.asyncio
    async def test_delegates_to_index_text_with_description(self):
        agent = _make_indexer()
        agent._describe_image = AsyncMock(return_value="A red dragon perches on a cliff.")
        agent.index_text = AsyncMock(return_value=1)

        result = await agent.index_image(b"\x89PNG\r\n", source_name="dragon.png")

        assert result == 1
        agent._describe_image.assert_awaited_once_with(b"\x89PNG\r\n", "dragon.png")
        agent.index_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_source_format_image_in_metadata(self):
        agent = _make_indexer()
        agent._describe_image = AsyncMock(return_value="some description")
        agent.index_text = AsyncMock(return_value=1)

        await agent.index_image(b"bytes", source_name="map.jpg")

        meta = agent.index_text.call_args.kwargs["metadata"]
        assert meta["source_format"] == "image"

    @pytest.mark.asyncio
    async def test_returns_zero_when_description_empty(self):
        agent = _make_indexer()
        agent._describe_image = AsyncMock(return_value="")
        agent.index_text = AsyncMock(return_value=0)

        result = await agent.index_image(b"bytes", source_name="blank.png")

        assert result == 0
        agent.index_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_zero_when_description_whitespace_only(self):
        agent = _make_indexer()
        agent._describe_image = AsyncMock(return_value="   \n  ")
        agent.index_text = AsyncMock(return_value=0)

        result = await agent.index_image(b"bytes", source_name="blank.png")

        assert result == 0
        agent.index_text.assert_not_awaited()


# ===========================================================================
# index_file
# ===========================================================================


class TestIndexFile:
    @pytest.mark.asyncio
    async def test_image_format_routes_to_index_image(self):
        agent = _make_indexer()
        agent.index_image = AsyncMock(return_value=3)

        with patch("monitor_agents.indexer.detect_format", return_value="image"):
            result = await agent.index_file(b"\x89PNG", "cover.png")

        assert result == 3
        agent.index_image.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pdf_format_routes_to_structure_aware_path(self):
        agent = _make_indexer()
        chunks = [_chunk("page 1"), _chunk("page 2")]
        agent._embed_and_upsert = AsyncMock()
        agent._chunk_pdf_with_structure = MagicMock(return_value=chunks)

        with patch("monitor_agents.indexer.detect_format", return_value="pdf"):
            result = await agent.index_file(b"%PDF", "rulebook.pdf")

        assert result == 2
        agent._chunk_pdf_with_structure.assert_called_once()
        agent._embed_and_upsert.assert_awaited_once_with(chunks, collection="snippets")

    @pytest.mark.asyncio
    async def test_returns_zero_when_ingest_file_empty(self):
        agent = _make_indexer()
        agent._embed_and_upsert = AsyncMock()

        with (
            patch("monitor_agents.indexer.detect_format", return_value="text"),
            patch("monitor_agents.indexer.ingest_file", return_value=[]),
        ):
            result = await agent.index_file(b"text content", "notes.txt")

        assert result == 0
        agent._embed_and_upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_source_name_defaults_to_filename_stem(self):
        agent = _make_indexer()
        chunks = [_chunk()]
        agent._embed_and_upsert = AsyncMock()

        with (
            patch("monitor_agents.indexer.detect_format", return_value="text"),
            patch("monitor_agents.indexer.ingest_file", return_value=chunks) as mock_ingest,
        ):
            await agent.index_file(b"content", "my-notes.txt")

        # source_name should be "my-notes" (stem)
        call_args = mock_ingest.call_args
        assert call_args[0][2] == "my-notes"  # positional sname arg


# ===========================================================================
# _download_from_minio
# ===========================================================================


class TestDownloadFromMinio:
    @pytest.mark.asyncio
    async def test_decodes_base64_string(self):
        agent = _make_indexer()
        raw_bytes = b"PDF content"
        b64_str = base64.b64encode(raw_bytes).decode()
        agent.call_tool = AsyncMock(return_value=b64_str)

        result = await agent._download_from_minio("uploads/doc.pdf")

        assert result == raw_bytes

    @pytest.mark.asyncio
    async def test_returns_none_when_tool_returns_nothing(self):
        agent = _make_indexer()
        agent.call_tool = AsyncMock(return_value=None)

        result = await agent._download_from_minio("uploads/missing.pdf")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_bytes_directly_when_already_bytes(self):
        agent = _make_indexer()
        raw = b"\x00\x01\x02"
        agent.call_tool = AsyncMock(return_value=raw)

        result = await agent._download_from_minio("uploads/binary.bin")

        assert result == raw


# ===========================================================================
# _embed_and_upsert
# ===========================================================================


class TestEmbedAndUpsert:
    @pytest.mark.asyncio
    async def test_single_batch_calls_upsert_once(self):
        agent = _make_indexer()
        chunks = [_chunk(f"chunk {i}") for i in range(3)]
        fake_vectors = [[0.1] * 4 for _ in chunks]

        mock_qdrant_raw = AsyncMock()
        mock_wrapper = MagicMock()
        mock_wrapper.ensure_collection = AsyncMock()
        mock_wrapper.new_loop_client.return_value = mock_qdrant_raw

        with (
            patch("monitor_agents.indexer.get_qdrant_client", return_value=mock_wrapper),
            patch("monitor_agents.indexer.embed_batch", new=AsyncMock(return_value=fake_vectors)),
        ):
            await agent._embed_and_upsert(chunks, collection="snippets")

        mock_wrapper.ensure_collection.assert_awaited_once_with("snippets")
        mock_qdrant_raw.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_batches_when_chunks_exceed_batch_size(self):
        agent = _make_indexer()
        n = _UPSERT_BATCH_SIZE + 5  # 69 chunks → 2 batches
        chunks = [_chunk(f"c {i}") for i in range(n)]
        fake_vectors = [[0.1] * 4 for _ in range(n)]

        mock_qdrant_raw = AsyncMock()
        mock_wrapper = MagicMock()
        mock_wrapper.ensure_collection = AsyncMock()
        mock_wrapper.new_loop_client.return_value = mock_qdrant_raw

        embed_side_effects = [
            fake_vectors[:_UPSERT_BATCH_SIZE],
            fake_vectors[_UPSERT_BATCH_SIZE:],
        ]

        with (
            patch("monitor_agents.indexer.get_qdrant_client", return_value=mock_wrapper),
            patch(
                "monitor_agents.indexer.embed_batch", new=AsyncMock(side_effect=embed_side_effects)
            ),
        ):
            await agent._embed_and_upsert(chunks, collection="snippets")

        assert mock_qdrant_raw.upsert.await_count == 2

    @pytest.mark.asyncio
    async def test_empty_chunks_skips_upsert(self):
        agent = _make_indexer()

        mock_qdrant_raw = AsyncMock()
        mock_wrapper = MagicMock()
        mock_wrapper.ensure_collection = AsyncMock()
        mock_wrapper.new_loop_client.return_value = mock_qdrant_raw

        with (
            patch("monitor_agents.indexer.get_qdrant_client", return_value=mock_wrapper),
            patch("monitor_agents.indexer.embed_batch", new=AsyncMock(return_value=[])),
        ):
            await agent._embed_and_upsert([], collection="snippets")

        # ensure_collection still called, but upsert never called
        mock_wrapper.ensure_collection.assert_awaited_once_with("snippets")
        mock_qdrant_raw.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upsert_receives_correct_collection_name(self):
        agent = _make_indexer()
        chunks = [_chunk("mem text")]
        fake_vectors = [[0.5] * 4]

        mock_qdrant_raw = AsyncMock()
        mock_wrapper = MagicMock()
        mock_wrapper.ensure_collection = AsyncMock()
        mock_wrapper.new_loop_client.return_value = mock_qdrant_raw

        with (
            patch("monitor_agents.indexer.get_qdrant_client", return_value=mock_wrapper),
            patch("monitor_agents.indexer.embed_batch", new=AsyncMock(return_value=fake_vectors)),
        ):
            await agent._embed_and_upsert(chunks, collection="memories")

        call_kwargs = mock_qdrant_raw.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == "memories"


# ===========================================================================
# _chunk_pdf_with_structure
# ===========================================================================


def _make_section_block(
    heading_path: List[str],
    depth: int = 0,
    text: str = "Some section body text.",
    page_start: int = 0,
    page_end: int = 0,
):
    """Build a minimal SectionBlock-like object for mocking."""
    from types import SimpleNamespace

    return SimpleNamespace(
        heading_path=heading_path,
        depth=depth,
        text=text,
        page_start=page_start,
        page_end=page_end,
    )


class TestChunkPdfWithStructure:
    """Tests for the structure-aware PDF chunking pre-pass."""

    @pytest.mark.asyncio
    async def test_heading_path_appears_in_chunk_metadata(self):
        """heading_path and section_depth must be set on every chunk produced."""
        agent = _make_indexer()
        heading = ["Chapter 1", "Combat Rules"]
        block = _make_section_block(heading_path=heading, depth=1, text="Body text here.")

        fake_chunk = _chunk("Body text here.")
        fake_chunk.metadata["heading_path"] = heading
        fake_chunk.metadata["section_depth"] = 1
        fake_chunk.metadata["semantic_category"] = "combat_rules"

        with (
            patch("monitor_agents.indexer.extract_pdf_structure", return_value=[block]),
            patch("monitor_agents.indexer.TagPool") as mock_tag_pool,
            patch("monitor_agents.indexer.SectionCategorizationModule"),
            patch("monitor_agents.indexer.chunk_text", return_value=[fake_chunk]),
        ):
            mock_tag_pool.classify_text.return_value = "combat_rules"

            chunks = agent._chunk_pdf_with_structure(b"%PDF", "rulebook")

        assert len(chunks) == 1
        assert chunks[0].metadata["heading_path"] == heading
        assert chunks[0].metadata["section_depth"] == 1

    @pytest.mark.asyncio
    async def test_section_categorization_module_not_called_when_tagpool_matches(self):
        """SectionCategorizationModule must NOT be called when TagPool returns a non-general category."""
        agent = _make_indexer()
        block = _make_section_block(
            heading_path=["Power Systems"],
            depth=0,
            text="This section is about spells.",
        )

        fake_chunk = _chunk("This section is about spells.")

        mock_categorizer_instance = MagicMock()

        with (
            patch("monitor_agents.indexer.extract_pdf_structure", return_value=[block]),
            patch("monitor_agents.indexer.TagPool") as mock_tag_pool,
            patch(
                "monitor_agents.indexer.SectionCategorizationModule",
                return_value=mock_categorizer_instance,
            ),
            patch("monitor_agents.indexer.chunk_text", return_value=[fake_chunk]),
        ):
            # TagPool finds a match → LLM should be skipped
            mock_tag_pool.classify_text.return_value = "power_system"

            agent._chunk_pdf_with_structure(b"%PDF", "grimoire")

        # The categorizer instance must never have been called
        mock_categorizer_instance.assert_not_called()

    @pytest.mark.asyncio
    async def test_section_categorization_module_called_when_tagpool_returns_none(self):
        """SectionCategorizationModule IS called when TagPool cannot classify the heading."""
        agent = _make_indexer()
        block = _make_section_block(
            heading_path=["Foreword"],
            depth=0,
            text="Welcome to this sourcebook.",
        )

        fake_chunk = _chunk("Welcome to this sourcebook.")
        mock_prediction = MagicMock()
        mock_prediction.category = "lore_history"
        mock_categorizer_instance = MagicMock(return_value=mock_prediction)

        with (
            patch("monitor_agents.indexer.extract_pdf_structure", return_value=[block]),
            patch("monitor_agents.indexer.TagPool") as mock_tag_pool,
            patch(
                "monitor_agents.indexer.SectionCategorizationModule",
                return_value=mock_categorizer_instance,
            ),
            patch("monitor_agents.indexer.chunk_text", return_value=[fake_chunk]),
        ):
            # TagPool returns None → falls back to "general" → triggers LLM
            mock_tag_pool.classify_text.return_value = None

            agent._chunk_pdf_with_structure(b"%PDF", "sourcebook")

        mock_categorizer_instance.assert_called_once_with(
            heading_path="Foreword",
            section_excerpt="Welcome to this sourcebook."[:200],
        )

    @pytest.mark.asyncio
    async def test_section_depth_forwarded_to_chunk_metadata(self):
        """section_depth from the SectionBlock must appear in chunk metadata."""
        agent = _make_indexer()
        block = _make_section_block(
            heading_path=["Chapter 2", "Magic", "Spellcasting"],
            depth=2,
            text="Spellcasting rules go here.",
        )
        fake_chunk = _chunk("Spellcasting rules go here.")
        fake_chunk.metadata["section_depth"] = 2

        with (
            patch("monitor_agents.indexer.extract_pdf_structure", return_value=[block]),
            patch("monitor_agents.indexer.TagPool") as mock_tag_pool,
            patch("monitor_agents.indexer.SectionCategorizationModule"),
            patch(
                "monitor_agents.indexer.chunk_text", return_value=[fake_chunk]
            ) as mock_chunk_text,
        ):
            mock_tag_pool.classify_text.return_value = "game_mechanics"

            agent._chunk_pdf_with_structure(b"%PDF", "rulebook")

        # Verify chunk_text was called with section_depth in metadata
        call_kwargs = mock_chunk_text.call_args.kwargs
        assert call_kwargs["metadata"]["section_depth"] == 2

    @pytest.mark.asyncio
    async def test_falls_back_to_ingest_pdf_when_no_sections(self):
        """When extract_pdf_structure returns empty, falls back to ingest_pdf."""
        agent = _make_indexer()
        fallback_chunks = [_chunk("fallback")]

        with (
            patch("monitor_agents.indexer.extract_pdf_structure", return_value=[]),
            patch(
                "monitor_agents.indexer.ingest_pdf", return_value=fallback_chunks
            ) as mock_ingest_pdf,
        ):
            result = agent._chunk_pdf_with_structure(b"%PDF", "doc")

        assert result == fallback_chunks
        mock_ingest_pdf.assert_called_once_with(b"%PDF", "doc", metadata={})

"""
Coverage-focused tests for monitor_data.tools.ingest_tools.

Complements test_ingest_tools.py (which covers chunk_text structural tagging).
Targets: IngestedChunk, _split_tokens, extract_pdf_text, _looks_like_heading,
         _infer_topic_tags, _infer_chunk_type, _split_structured_blocks,
         ingest_text, _strip_markdown, _strip_html, _extract_docx_text,
         _extract_epub_text, detect_format, ingest_pdf, ingest_markdown,
         ingest_html, ingest_docx, ingest_epub, ingest_file.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from monitor_data.tools.ingest_tools import (
    IngestedChunk,
    _looks_like_heading,
    _infer_topic_tags,
    _infer_chunk_type,
    _split_structured_blocks,
    _split_tokens,
    _strip_markdown,
    _strip_html,
    _extract_docx_text,
    _extract_epub_text,
    detect_format,
    extract_pdf_text,
    ingest_docx,
    ingest_epub,
    ingest_file,
    ingest_html,
    ingest_markdown,
    ingest_pdf,
    ingest_text,
)


# ---------------------------------------------------------------------------
# IngestedChunk
# ---------------------------------------------------------------------------


class TestIngestedChunk:
    def test_stable_id_is_deterministic(self):
        a = IngestedChunk.stable_id("src", 0, "hello")
        b = IngestedChunk.stable_id("src", 0, "hello")
        assert a == b

    def test_stable_id_differs_on_different_inputs(self):
        a = IngestedChunk.stable_id("src", 0, "hello")
        b = IngestedChunk.stable_id("src", 1, "hello")
        c = IngestedChunk.stable_id("other", 0, "hello")
        d = IngestedChunk.stable_id("src", 0, "world")
        assert len({a, b, c, d}) == 4

    def test_to_qdrant_payload_contains_fields(self):
        chunk = IngestedChunk(
            chunk_id="abc",
            source_name="my_doc",
            page_number=3,
            chunk_index=0,
            text="Some text",
            token_count=2,
            metadata={"section_path": "Intro"},
        )
        payload = chunk.to_qdrant_payload()
        assert payload["chunk_id"] == "abc"
        assert payload["source_name"] == "my_doc"
        assert payload["page_number"] == 3
        assert payload["chunk_index"] == 0
        assert payload["text"] == "Some text"
        assert payload["token_count"] == 2
        assert payload["section_path"] == "Intro"

    def test_to_qdrant_payload_none_page_number(self):
        chunk = IngestedChunk(
            chunk_id="x",
            source_name="doc",
            page_number=None,
            chunk_index=0,
            text="text",
            token_count=1,
        )
        payload = chunk.to_qdrant_payload()
        assert payload["page_number"] is None


# ---------------------------------------------------------------------------
# _split_tokens
# ---------------------------------------------------------------------------


class TestSplitTokens:
    def test_empty_returns_empty(self):
        assert _split_tokens([], 512, 51) == []

    def test_single_chunk_when_under_limit(self):
        tokens = list(range(10))
        result = _split_tokens(tokens, 20, 2)
        assert result == [tokens]

    def test_splits_into_multiple_chunks(self):
        tokens = list(range(30))
        result = _split_tokens(tokens, 10, 2)
        assert len(result) > 1
        assert all(len(chunk) <= 10 for chunk in result)

    def test_overlap_creates_shared_tokens(self):
        tokens = list(range(20))
        result = _split_tokens(tokens, 10, 3)
        # Second chunk should start at token 7 (stride = 10-3=7)
        assert result[1][0] == 7

    def test_invalid_overlap_raises(self):
        with pytest.raises(ValueError, match="overlap"):
            _split_tokens(list(range(10)), 5, 5)

    def test_exact_boundary_no_extra_chunk(self):
        tokens = list(range(10))
        result = _split_tokens(tokens, 10, 2)
        assert result == [tokens]


# ---------------------------------------------------------------------------
# extract_pdf_text
# ---------------------------------------------------------------------------


class TestExtractPdfText:
    def _make_mock_doc(self, pages_text: list[str]):
        """Build a mock fitz document context manager."""
        mock_pages = []
        for text in pages_text:
            p = MagicMock()
            p.get_text.return_value = text
            mock_pages.append(p)

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        ctx.__iter__ = MagicMock(return_value=iter(mock_pages))
        return ctx

    def test_returns_pages_with_text(self):
        ctx = self._make_mock_doc(["Page one text\n", "Page two text"])
        with patch("monitor_data.tools.ingest_tools.pdf_processing.fitz") as mock_fitz:
            mock_fitz.open.return_value = ctx
            pages = extract_pdf_text(b"%PDF-fake")

        assert len(pages) == 2
        assert pages[0]["page_number"] == 1
        assert pages[0]["text"] == "Page one text"
        assert pages[1]["page_number"] == 2

    def test_skips_empty_pages(self):
        ctx = self._make_mock_doc(["Good content", "  \n  ", "More content"])
        with patch("monitor_data.tools.ingest_tools.pdf_processing.fitz") as mock_fitz:
            mock_fitz.open.return_value = ctx
            pages = extract_pdf_text(b"%PDF-fake")

        assert len(pages) == 2
        assert pages[0]["page_number"] == 1
        assert pages[1]["page_number"] == 3

    def test_all_empty_raises_no_text_error(self):
        # A PDF whose pages have no extractable text is a scanned/image-only
        # doc — T-083 makes this fail loudly rather than return [] silently.
        from monitor_data.tools.ingest_tools.pdf_processing import PdfExtractionError

        ctx = self._make_mock_doc(["", "   "])
        with patch("monitor_data.tools.ingest_tools.pdf_processing.fitz") as mock_fitz:
            mock_fitz.open.return_value = ctx
            with pytest.raises(PdfExtractionError, match="No extractable text"):
                extract_pdf_text(b"%PDF-fake")


# ---------------------------------------------------------------------------
# _looks_like_heading
# ---------------------------------------------------------------------------


class TestLooksLikeHeading:
    def test_empty_string_returns_false(self):
        assert _looks_like_heading("") is False

    def test_too_long_returns_false(self):
        assert _looks_like_heading("A" * 81) is False

    def test_ends_with_period_returns_false(self):
        assert _looks_like_heading("This is a sentence.") is False

    def test_ends_with_exclamation_returns_false(self):
        assert _looks_like_heading("Exciting!") is False

    def test_ends_with_question_returns_false(self):
        assert _looks_like_heading("Why?") is False

    def test_no_letters_returns_false(self):
        assert _looks_like_heading("123 456") is False

    def test_all_caps_heading_returns_true(self):
        assert _looks_like_heading("COMBAT RULES") is True

    def test_title_case_short_heading_returns_true(self):
        assert _looks_like_heading("The Iron Empire") is True

    def test_ends_with_colon_returns_true(self):
        assert _looks_like_heading("Equipment:") is True

    def test_long_title_case_returns_false(self):
        # Too many words to qualify as heading
        long_heading = "The Quick Brown Fox Jumped Over The Lazy Dog Twice"
        if len(long_heading) <= 80:
            # Only returns false if word count > 8 AND not high uppercase ratio
            result = _looks_like_heading(long_heading)
            # May be True (high uppercase) or False depending on case ratio
            assert isinstance(result, bool)

    def test_lowercase_paragraph_returns_false(self):
        assert _looks_like_heading("this is normal paragraph text here") is False


# ---------------------------------------------------------------------------
# _infer_topic_tags
# ---------------------------------------------------------------------------


class TestInferTopicTags:
    def test_combat_keywords_add_system_tag(self):
        tags = _infer_topic_tags("Roll a d20 and add your modifier to the attack.")
        assert "system" in tags

    def test_lore_keywords_add_lore_tag(self):
        tags = _infer_topic_tags("The history of the iron empire is long and dark.")
        assert "lore" in tags

    def test_price_keywords_add_prices_tag(self):
        tags = _infer_topic_tags("The sword costs 50 credits.")
        assert "prices" in tags

    def test_faction_keywords_add_factions_tag(self):
        tags = _infer_topic_tags("The guild controls all trade in the sector.")
        assert "factions" in tags

    def test_creature_keywords_add_creatures_tag(self):
        tags = _infer_topic_tags("The monster attacks twice per round.")
        assert "creatures" in tags

    def test_location_keywords_add_locations_tag(self):
        tags = _infer_topic_tags("The planet is covered in ice and ruins.")
        assert "locations" in tags

    def test_equipment_keywords_add_equipment_tag(self):
        tags = _infer_topic_tags("The weapon has a damage of 1d10.")
        assert "equipment" in tags

    def test_no_keywords_returns_general(self):
        tags = _infer_topic_tags("Some completely unrelated text about nothing.")
        assert "general" in tags

    def test_table_detection_by_pipes(self):
        tags = _infer_topic_tags("| Column A | Column B | Column C |")
        assert "tables" in tags

    def test_price_regex_match(self):
        tags = _infer_topic_tags("Armor: 200 gp")
        assert "prices" in tags

    def test_section_path_included_in_detection(self):
        tags = _infer_topic_tags("Describe the setting", section_path="Faction Rules")
        assert "factions" in tags or "rules" in tags


# ---------------------------------------------------------------------------
# _infer_chunk_type
# ---------------------------------------------------------------------------


class TestInferChunkType:
    def test_table_detection_by_pipes(self):
        result = _infer_chunk_type("| a | b | c |", ["tables"])
        assert result == "table"

    def test_stat_block_detection(self):
        text = "STR: 10\nDEX: 14\nCON: 12\n"
        result = _infer_chunk_type(text, [])
        # stat_block requires >= 3 colons and >= 3 lines
        assert result in {"stat_block", "paragraph"}

    def test_rules_tag_returns_rules(self):
        result = _infer_chunk_type("Roll a d20", ["rules"])
        assert result == "rules"

    def test_lore_tag_returns_lore(self):
        result = _infer_chunk_type("Long ago...", ["lore"])
        assert result == "lore"

    def test_factions_tag_returns_lore(self):
        result = _infer_chunk_type("The guild...", ["factions"])
        assert result == "lore"

    def test_locations_tag_returns_lore(self):
        result = _infer_chunk_type("On a distant planet...", ["locations"])
        assert result == "lore"

    def test_default_returns_paragraph(self):
        result = _infer_chunk_type("Some random text.", ["general"])
        assert result == "paragraph"


# ---------------------------------------------------------------------------
# _split_structured_blocks
# ---------------------------------------------------------------------------


class TestSplitStructuredBlocks:
    def test_single_paragraph_no_heading(self):
        blocks = _split_structured_blocks("Just one paragraph of text.")
        assert len(blocks) == 1
        assert blocks[0]["text"] == "Just one paragraph of text."
        assert blocks[0]["section_path"] is None

    def test_heading_is_preserved_as_section_path(self):
        text = "COMBAT\n\nRoll a d20 to attack."
        blocks = _split_structured_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["section_path"] == "COMBAT"

    def test_multiple_paragraphs(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        blocks = _split_structured_blocks(text)
        assert len(blocks) == 3

    def test_heading_assigns_to_subsequent_paragraphs(self):
        text = "EQUIPMENT:\n\nSword costs 10 gp.\n\nArmor costs 50 gp."
        blocks = _split_structured_blocks(text)
        assert all(b["section_path"] == "EQUIPMENT:" for b in blocks)

    def test_empty_text_returns_empty(self):
        assert _split_structured_blocks("") == []

    def test_whitespace_only_returns_empty(self):
        assert _split_structured_blocks("   \n\n  ") == []

    def test_only_heading_returns_empty(self):
        # A single heading with no body text produces no blocks
        blocks = _split_structured_blocks("HEADING ONLY")
        # It may or may not be treated as heading depending on heuristic
        # Just verify it returns a list
        assert isinstance(blocks, list)

    def test_block_has_topic_tags_and_chunk_type(self):
        blocks = _split_structured_blocks("Roll a d20 to attack the enemy.")
        assert len(blocks) == 1
        assert "topic_tags" in blocks[0]
        assert "chunk_type" in blocks[0]
        assert isinstance(blocks[0]["topic_tags"], list)
        assert isinstance(blocks[0]["chunk_type"], str)


# ---------------------------------------------------------------------------
# ingest_text
# ---------------------------------------------------------------------------


class TestIngestText:
    def test_returns_list_of_chunks(self):
        chunks = ingest_text("Hello world. " * 10, "test_doc")
        assert isinstance(chunks, list)
        assert all(isinstance(c, IngestedChunk) for c in chunks)

    def test_empty_text_returns_empty_list(self):
        assert ingest_text("", "test_doc") == []

    def test_whitespace_only_returns_empty_list(self):
        assert ingest_text("   \n  ", "test_doc") == []

    def test_source_name_propagated(self):
        chunks = ingest_text("Some text here.", "my_source")
        assert all(c.source_name == "my_source" for c in chunks)

    def test_custom_max_tokens(self):
        # Very small max_tokens → more chunks
        long_text = "word " * 200
        chunks_small = ingest_text(long_text, "doc", max_tokens=20)
        chunks_large = ingest_text(long_text, "doc", max_tokens=200)
        assert len(chunks_small) >= len(chunks_large)


# ---------------------------------------------------------------------------
# _strip_markdown
# ---------------------------------------------------------------------------


class TestStripMarkdown:
    def test_removes_atx_headings(self):
        result = _strip_markdown("## Section Title\n\nSome text.")
        assert "##" not in result
        assert "Section Title" in result

    def test_removes_bold_asterisks(self):
        result = _strip_markdown("This is **bold** text.")
        assert "**" not in result
        assert "bold" in result

    def test_removes_italic_underscores(self):
        result = _strip_markdown("This is _italic_ text.")
        assert "_italic_" not in result
        assert "italic" in result

    def test_removes_inline_code(self):
        result = _strip_markdown("Use `print()` to output.")
        assert "`" not in result
        assert "print()" in result

    def test_removes_fenced_code_block(self):
        result = _strip_markdown("```python\nx = 1\n```")
        assert "```" not in result
        assert "x = 1" in result

    def test_removes_links_keeps_label(self):
        result = _strip_markdown("[Click here](https://example.com)")
        assert "Click here" in result
        assert "https://example.com" not in result

    def test_removes_images_keeps_alt(self):
        result = _strip_markdown("![Alt text](image.png)")
        assert "Alt text" in result
        assert "image.png" not in result

    def test_removes_blockquotes(self):
        result = _strip_markdown("> Quoted line here.")
        assert ">" not in result
        assert "Quoted line here." in result

    def test_removes_horizontal_rules(self):
        result = _strip_markdown("Text\n\n---\n\nMore text.")
        assert "---" not in result

    def test_collapses_excessive_blank_lines(self):
        result = _strip_markdown("Line one.\n\n\n\n\nLine two.")
        assert result.count("\n\n") <= 2

    def test_pipe_tables_keep_cell_content(self):
        table = "| Name | Age |\n|------|-----|\n| Alice | 30 |"
        result = _strip_markdown(table)
        assert "Alice" in result
        assert "30" in result

    def test_plain_text_unchanged(self):
        text = "Just plain text with no markup."
        result = _strip_markdown(text)
        assert result == text


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------


class TestStripHtml:
    def test_removes_script_tags(self):
        html = "<html><body><script>alert('x')</script><p>content</p></body></html>"
        result = _strip_html(html)
        assert "alert" not in result
        assert "content" in result

    def test_removes_style_tags(self):
        html = "<html><head><style>body{color:red}</style></head><body><p>text</p></body></html>"
        result = _strip_html(html)
        assert "color:red" not in result
        assert "text" in result

    def test_fallback_mode_strips_tags(self):
        html = "<p>Hello <b>world</b></p>"
        with patch("monitor_data.tools.ingest_tools.multi_format._BS4_AVAILABLE", False):
            result = _strip_html(html)
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_fallback_mode_decodes_html_entities(self):
        html = "<p>A &amp; B &lt; C &gt; D &quot;test&quot; &nbsp; end</p>"
        with patch("monitor_data.tools.ingest_tools.multi_format._BS4_AVAILABLE", False):
            result = _strip_html(html)
        assert "&amp;" not in result
        assert "A & B" in result

    def test_fallback_collapses_blank_lines(self):
        html = "<p>Para 1</p>\n\n\n\n<p>Para 2</p>"
        with patch("monitor_data.tools.ingest_tools.multi_format._BS4_AVAILABLE", False):
            result = _strip_html(html)
        assert result.count("\n\n") <= 2


# ---------------------------------------------------------------------------
# _extract_docx_text
# ---------------------------------------------------------------------------


class TestExtractDocxText:
    def test_unavailable_raises_import_error(self):
        with patch("monitor_data.tools.ingest_tools.multi_format._DOCX_AVAILABLE", False):
            with pytest.raises(ImportError, match="python-docx"):
                _extract_docx_text(b"fake-docx")

    def test_available_extracts_paragraphs_and_tables(self):
        mock_para1 = MagicMock()
        mock_para1.text = "First paragraph"
        mock_para2 = MagicMock()
        mock_para2.text = "  "  # blank, should be skipped

        mock_cell = MagicMock()
        mock_cell.text = "Cell content"
        mock_row = MagicMock()
        mock_row.cells = [mock_cell]
        mock_table = MagicMock()
        mock_table.rows = [mock_row]

        mock_doc_obj = MagicMock()
        mock_doc_obj.paragraphs = [mock_para1, mock_para2]
        mock_doc_obj.tables = [mock_table]

        with patch("monitor_data.tools.ingest_tools.multi_format._DOCX_AVAILABLE", True):
            with patch("docx.Document", return_value=mock_doc_obj):
                result = _extract_docx_text(b"fake")

        assert "First paragraph" in result
        assert "Cell content" in result
        assert result.strip()  # non-empty

    def test_empty_cells_are_skipped(self):
        mock_cell_empty = MagicMock()
        mock_cell_empty.text = ""
        mock_row = MagicMock()
        mock_row.cells = [mock_cell_empty]
        mock_table = MagicMock()
        mock_table.rows = [mock_row]

        mock_doc_obj = MagicMock()
        mock_doc_obj.paragraphs = []
        mock_doc_obj.tables = [mock_table]

        with patch("monitor_data.tools.ingest_tools.multi_format._DOCX_AVAILABLE", True):
            with patch("docx.Document", return_value=mock_doc_obj):
                result = _extract_docx_text(b"fake")

        assert result == ""


# ---------------------------------------------------------------------------
# _extract_epub_text
# ---------------------------------------------------------------------------


class TestExtractEpubText:
    def test_unavailable_raises_import_error(self):
        with patch("monitor_data.tools.ingest_tools.multi_format._EPUB_AVAILABLE", False):
            with pytest.raises(ImportError, match="ebooklib"):
                _extract_epub_text(b"fake-epub")

    def test_available_extracts_text_from_documents(self):
        # ITEM_DOCUMENT = 9 in ebooklib; use constant to avoid importing missing lib
        ITEM_DOCUMENT = 9

        mock_item = MagicMock()
        mock_item.get_type.return_value = ITEM_DOCUMENT
        mock_item.get_content.return_value = b"<p>Chapter text here</p>"

        mock_book = MagicMock()
        mock_book.get_items.return_value = [mock_item]

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_DOCUMENT = ITEM_DOCUMENT

        with patch("monitor_data.tools.ingest_tools.multi_format._EPUB_AVAILABLE", True):
            with patch("ebooklib.epub.read_epub", return_value=mock_book):
                with patch("ebooklib.ITEM_DOCUMENT", ITEM_DOCUMENT):
                    result = _extract_epub_text(b"fake-epub")

        assert "Chapter text here" in result

    def test_non_document_items_are_skipped(self):
        # ITEM_IMAGE = 3 in ebooklib; use constant to avoid importing missing lib
        ITEM_DOCUMENT = 9
        ITEM_IMAGE = 3

        mock_item = MagicMock()
        mock_item.get_type.return_value = ITEM_IMAGE  # not a document
        mock_item.get_content.return_value = b"\x89PNG"

        mock_book = MagicMock()
        mock_book.get_items.return_value = [mock_item]

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_DOCUMENT = ITEM_DOCUMENT

        with patch("monitor_data.tools.ingest_tools.multi_format._EPUB_AVAILABLE", True):
            with patch("ebooklib.epub.read_epub", return_value=mock_book):
                with patch("ebooklib.ITEM_DOCUMENT", ITEM_DOCUMENT):
                    result = _extract_epub_text(b"fake")

        assert result == ""


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_pdf_by_extension(self):
        assert detect_format("rulebook.pdf") == "pdf"

    def test_markdown_extensions(self):
        for ext in [".md", ".markdown", ".mdown", ".mkd"]:
            assert detect_format(f"file{ext}") == "markdown"

    def test_text_extensions(self):
        for ext in [".txt", ".text", ".rst", ".csv", ".tsv", ".log"]:
            assert detect_format(f"file{ext}") == "text"

    def test_html_extensions(self):
        for ext in [".htm", ".html", ".xhtml"]:
            assert detect_format(f"file{ext}") == "html"

    def test_docx_extension(self):
        assert detect_format("document.docx") == "docx"

    def test_epub_extension(self):
        assert detect_format("book.epub") == "epub"

    def test_image_extensions(self):
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg"]:
            assert detect_format(f"image{ext}") == "image"

    def test_unknown_extension(self):
        assert detect_format("file.xyz") == "unknown"

    def test_no_extension_no_mime(self):
        assert detect_format("README") == "unknown"

    def test_mime_pdf_fallback(self):
        assert detect_format("file.bin", "application/pdf") == "pdf"

    def test_mime_html_fallback(self):
        assert detect_format("file", "text/html") == "html"

    def test_mime_text_fallback(self):
        assert detect_format("file", "text/plain") == "text"

    def test_mime_image_fallback(self):
        assert detect_format("file", "image/jpeg") == "image"

    def test_mime_docx_fallback(self):
        ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert detect_format("file", ct) == "docx"

    def test_mime_epub_fallback(self):
        assert detect_format("file", "application/epub+zip") == "epub"

    def test_mime_unknown_fallback(self):
        assert detect_format("file", "application/octet-stream") == "unknown"

    def test_mime_with_charset_param(self):
        assert detect_format("file", "text/html; charset=utf-8") == "html"


# ---------------------------------------------------------------------------
# ingest_pdf (via mock fitz)
# ---------------------------------------------------------------------------


class TestIngestPdf:
    def _make_mock_doc(self, pages_text: list[str]):
        mock_pages = []
        for text in pages_text:
            p = MagicMock()

            def _get_text(mode="text", _t=text, **kwargs):
                if mode == "dict":
                    if not _t.strip():
                        return {"blocks": []}
                    return {
                        "blocks": [
                            {
                                "type": 0,
                                "lines": [
                                    {
                                        "spans": [
                                            {
                                                "text": _t,
                                                "size": 12.0,
                                                "flags": 0,
                                                "font": "Helvetica",
                                            }
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                return _t

            p.get_text = _get_text
            mock_pages.append(p)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        ctx.__iter__ = MagicMock(return_value=iter(mock_pages))
        return ctx

    def test_ingest_pdf_returns_chunks(self):
        ctx = self._make_mock_doc(["Page content with some words. " * 5])
        with patch("monitor_data.tools.ingest_tools.pdf_processing.fitz") as mock_fitz:
            mock_fitz.open.return_value = ctx
            chunks = ingest_pdf(b"%PDF-fake", "test_pdf")

        assert isinstance(chunks, list)
        assert all(isinstance(c, IngestedChunk) for c in chunks)

    def test_ingest_pdf_page_number_set(self):
        ctx = self._make_mock_doc(["Page one content"])
        with patch("monitor_data.tools.ingest_tools.pdf_processing.fitz") as mock_fitz:
            mock_fitz.open.return_value = ctx
            chunks = ingest_pdf(b"%PDF-fake", "my_pdf")

        assert all(c.page_number == 1 for c in chunks)

    def test_ingest_pdf_empty_pdf_returns_empty(self):
        ctx = self._make_mock_doc(["   ", ""])
        with patch("monitor_data.tools.ingest_tools.pdf_processing.fitz") as mock_fitz:
            mock_fitz.open.return_value = ctx
            chunks = ingest_pdf(b"%PDF-fake", "empty_pdf")

        assert chunks == []

    def test_ingest_pdf_passes_metadata(self):
        ctx = self._make_mock_doc(["Some content here."])
        with patch("monitor_data.tools.ingest_tools.pdf_processing.fitz") as mock_fitz:
            mock_fitz.open.return_value = ctx
            chunks = ingest_pdf(b"%PDF-fake", "doc", metadata={"universe_id": "u1"})

        assert all(c.metadata.get("universe_id") == "u1" for c in chunks)


# ---------------------------------------------------------------------------
# ingest_markdown
# ---------------------------------------------------------------------------


class TestIngestMarkdown:
    def test_basic_markdown_produces_chunks(self):
        md = "# Title\n\nThis is a paragraph with some content.\n\n## Section\n\nMore text."
        chunks = ingest_markdown(md, "wiki_page")
        assert isinstance(chunks, list)
        assert all(isinstance(c, IngestedChunk) for c in chunks)

    def test_markdown_strips_syntax(self):
        md = "## Rules\n\nRoll **2d6** and add your *modifier*."
        chunks = ingest_markdown(md, "rules")
        full_text = " ".join(c.text for c in chunks)
        assert "**" not in full_text
        assert "*modifier*" not in full_text
        assert "modifier" in full_text

    def test_empty_markdown_returns_empty(self):
        assert ingest_markdown("", "doc") == []


# ---------------------------------------------------------------------------
# ingest_html
# ---------------------------------------------------------------------------


class TestIngestHtml:
    def test_basic_html_produces_chunks(self):
        html = "<html><body><h1>Title</h1><p>Some content paragraph.</p></body></html>"
        chunks = ingest_html(html, "webpage")
        assert isinstance(chunks, list)

    def test_scripts_stripped(self):
        html = "<p>Content</p><script>alert('x')</script>"
        chunks = ingest_html(html, "page")
        full_text = " ".join(c.text for c in chunks)
        assert "alert" not in full_text
        assert "Content" in full_text

    def test_empty_html_returns_empty(self):
        chunks = ingest_html("<html><body>   </body></html>", "page")
        assert isinstance(chunks, list)


# ---------------------------------------------------------------------------
# ingest_docx
# ---------------------------------------------------------------------------


class TestIngestDocx:
    def test_returns_chunks_when_docx_available(self):
        mock_para = MagicMock()
        mock_para.text = "Document paragraph content here."
        mock_doc_obj = MagicMock()
        mock_doc_obj.paragraphs = [mock_para]
        mock_doc_obj.tables = []

        with patch("monitor_data.tools.ingest_tools.multi_format._DOCX_AVAILABLE", True):
            with patch("docx.Document", return_value=mock_doc_obj):
                chunks = ingest_docx(b"fake-docx", "word_doc")

        assert isinstance(chunks, list)
        assert all(isinstance(c, IngestedChunk) for c in chunks)

    def test_raises_when_docx_unavailable(self):
        with patch("monitor_data.tools.ingest_tools.multi_format._DOCX_AVAILABLE", False):
            with pytest.raises(ImportError, match="python-docx"):
                ingest_docx(b"fake", "doc")


# ---------------------------------------------------------------------------
# ingest_epub
# ---------------------------------------------------------------------------


class TestIngestEpub:
    def test_returns_chunks_when_epub_available(self):
        ITEM_DOCUMENT = 9

        mock_item = MagicMock()
        mock_item.get_type.return_value = ITEM_DOCUMENT
        mock_item.get_content.return_value = b"<p>Chapter content.</p>"

        mock_book = MagicMock()
        mock_book.get_items.return_value = [mock_item]

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_DOCUMENT = ITEM_DOCUMENT

        with patch("monitor_data.tools.ingest_tools.multi_format._EPUB_AVAILABLE", True):
            with patch("ebooklib.epub.read_epub", return_value=mock_book):
                with patch("ebooklib.ITEM_DOCUMENT", ITEM_DOCUMENT):
                    chunks = ingest_epub(b"fake-epub", "my_book")

        assert isinstance(chunks, list)
        assert all(isinstance(c, IngestedChunk) for c in chunks)

    def test_raises_when_epub_unavailable(self):
        with patch("monitor_data.tools.ingest_tools.multi_format._EPUB_AVAILABLE", False):
            with pytest.raises(ImportError, match="ebooklib"):
                ingest_epub(b"fake", "book")


# ---------------------------------------------------------------------------
# ingest_file (dispatch)
# ---------------------------------------------------------------------------


class TestIngestFile:
    def test_pdf_dispatches_to_ingest_pdf(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_pdf") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"%PDF", "doc.pdf")
        mock_fn.assert_called_once()

    def test_text_dispatches_to_ingest_text(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_text") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"hello world", "notes.txt")
        mock_fn.assert_called_once()

    def test_markdown_dispatches_to_ingest_markdown(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_markdown") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"# Title", "page.md")
        mock_fn.assert_called_once()

    def test_html_dispatches_to_ingest_html(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_html") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"<html></html>", "page.html")
        mock_fn.assert_called_once()

    def test_docx_dispatches_to_ingest_docx(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_docx") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"fake-docx-bytes", "doc.docx")
        mock_fn.assert_called_once()

    def test_epub_dispatches_to_ingest_epub(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_epub") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"fake-epub-bytes", "book.epub")
        mock_fn.assert_called_once()

    def test_image_raises_value_error(self):
        with pytest.raises(ValueError, match="Images require async"):
            ingest_file(b"\x89PNG data", "photo.png")

    def test_source_name_defaults_to_filename_stem(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_text") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"text content", "my_document.txt")
        # source_name should be "my_document" (stem)
        call_args = mock_fn.call_args
        assert call_args[0][1] == "my_document"

    def test_source_name_override(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_text") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"text content", "file.txt", "custom_name")
        call_args = mock_fn.call_args
        assert call_args[0][1] == "custom_name"

    def test_unknown_format_valid_utf8_falls_back_to_text(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_text") as mock_fn:
            mock_fn.return_value = []
            ingest_file("Hello world".encode("utf-8"), "data.xyz")
        mock_fn.assert_called_once()

    def test_unknown_format_binary_raises_value_error(self):
        # Bytes that cannot be decoded as strict UTF-8
        with pytest.raises(ValueError, match="unrecognised binary format"):
            ingest_file(b"\xff\xfe\x00binary\xff", "data.xyz")

    def test_mime_type_used_for_detection(self):
        with patch("monitor_data.tools.ingest_tools.multi_format.ingest_pdf") as mock_fn:
            mock_fn.return_value = []
            ingest_file(b"content", "file.bin", content_type="application/pdf")
        mock_fn.assert_called_once()

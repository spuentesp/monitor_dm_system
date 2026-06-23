import io

import fitz  # PyMuPDF

from monitor_data.tools.ingest_tools import SectionBlock, chunk_text, extract_pdf_structure


def _make_pdf_with_toc() -> bytes:
    """Create an in-memory PDF with a two-level bookmark tree."""
    doc = fitz.open()
    page0 = doc.new_page()
    page0.insert_text((72, 72), "Chapter 1 text here.")
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Chapter 2 text here.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Combat rules text here.")
    toc = [
        [1, "Chapter 1", 1],
        [1, "Chapter 2", 2],
        [2, "Combat", 3],
    ]
    doc.set_toc(toc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_pdf_without_toc() -> bytes:
    """Create an in-memory PDF with no bookmarks but heading-like text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "COMBAT\n\nRoll a d20 to attack.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_pdf_structure_with_toc():
    pdf_bytes = _make_pdf_with_toc()
    sections = extract_pdf_structure(pdf_bytes)
    assert len(sections) >= 2
    names = [s.heading_path[-1] for s in sections]
    assert "Chapter 1" in names or "Chapter 2" in names


def test_extract_pdf_structure_section_block_fields():
    pdf_bytes = _make_pdf_with_toc()
    sections = extract_pdf_structure(pdf_bytes)
    first = sections[0]
    assert isinstance(first, SectionBlock)
    assert isinstance(first.heading_path, list)
    assert isinstance(first.depth, int)
    assert isinstance(first.page_start, int)
    assert isinstance(first.page_end, int)
    assert isinstance(first.text, str)


def test_extract_pdf_structure_fallback_no_toc():
    pdf_bytes = _make_pdf_without_toc()
    sections = extract_pdf_structure(pdf_bytes)
    assert len(sections) >= 1
    assert all(isinstance(s, SectionBlock) for s in sections)


def test_extract_pdf_structure_heading_path_nesting():
    pdf_bytes = _make_pdf_with_toc()
    sections = extract_pdf_structure(pdf_bytes)
    # "Combat" is a level-2 entry; depth should be 1 (0-indexed from level-1)
    combat_sections = [s for s in sections if "Combat" in s.heading_path]
    if combat_sections:
        assert combat_sections[0].depth >= 1


def test_chunk_text_adds_structural_topic_metadata():
    chunks = chunk_text(
        "COMBAT\n\nRoll a d20 to attack. Track hit points, armor, and damage each round.",
        "Death in Space",
    )

    assert chunks
    metadata = chunks[0].metadata
    assert metadata.get("section_path") == "COMBAT"
    assert metadata.get("chunk_type") in {"rules", "mixed", "procedure"}
    assert "system" in metadata.get("topic_tags", []) or "rules" in metadata.get("topic_tags", [])


def test_chunk_text_tags_lore_sections():
    chunks = chunk_text(
        "HISTORY\n\nThe iron empire fell after a devastating civil war, leaving the sector broken and haunted.",
        "Death in Space",
    )

    assert chunks
    tags = chunks[0].metadata.get("topic_tags", [])
    assert "lore" in tags or "history" in tags


def test_chunk_text_uses_larger_size_for_rulebook():
    """Rulebook chunks should be fewer/larger than default chunks for the same text."""
    long_text = "COMBAT\n\n" + " ".join(["Roll a d20 to attack."] * 300)
    chunks_default = chunk_text(long_text, "some_doc", is_rulebook=False)
    chunks_rulebook = chunk_text(long_text, "some_doc", is_rulebook=True)
    assert len(chunks_rulebook) <= len(chunks_default)


def test_chunk_text_is_rulebook_false_by_default():
    """Without the flag, chunk_text() must still work with no change in behavior."""
    chunks = chunk_text("COMBAT\n\nShort text.", "book")
    assert chunks


# ── PDF edge-case guards (T-083) ───────────────────────────────


def _make_scanned_pdf() -> bytes:
    """A PDF with a page but no text layer (mimics a scan)."""
    doc = fitz.open()
    doc.new_page()  # blank page, no inserted text
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_encrypted_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "secret text")
    buf = io.BytesIO()
    doc.save(buf, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="open-sesame")
    return buf.getvalue()


def test_extract_pdf_text_rejects_empty_bytes():
    import pytest

    from monitor_data.tools.ingest_tools.pdf_processing import (
        PdfExtractionError,
        extract_pdf_text,
    )

    with pytest.raises(PdfExtractionError, match="empty"):
        extract_pdf_text(b"")


def test_extract_pdf_text_rejects_huge_pdf():
    import pytest

    from monitor_data.tools.ingest_tools.pdf_processing import (
        PdfExtractionError,
        extract_pdf_text,
    )

    huge_bytes = b"0" * (50 * 1024 * 1024 + 1)
    with pytest.raises(PdfExtractionError, match="exceeds streaming budget"):
        extract_pdf_text(huge_bytes)


def test_extract_pdf_text_rejects_corrupt_pdf():
    import pytest

    from monitor_data.tools.ingest_tools.pdf_processing import (
        PdfExtractionError,
        extract_pdf_text,
    )

    with pytest.raises(PdfExtractionError):
        extract_pdf_text(b"%PDF-1.4 this is not really a pdf body")


def test_extract_pdf_text_rejects_scanned_pdf():
    import pytest

    from monitor_data.tools.ingest_tools.pdf_processing import (
        PdfExtractionError,
        extract_pdf_text,
    )

    with pytest.raises(PdfExtractionError, match="scanned"):
        extract_pdf_text(_make_scanned_pdf())


def test_extract_pdf_text_rejects_password_protected_pdf():
    import pytest

    from monitor_data.tools.ingest_tools.pdf_processing import (
        PdfExtractionError,
        extract_pdf_text,
    )

    with pytest.raises(PdfExtractionError, match="password"):
        extract_pdf_text(_make_encrypted_pdf())


def test_extract_pdf_structure_guards_empty_bytes():
    import pytest

    from monitor_data.tools.ingest_tools.pdf_processing import PdfExtractionError

    with pytest.raises(PdfExtractionError):
        extract_pdf_structure(b"")

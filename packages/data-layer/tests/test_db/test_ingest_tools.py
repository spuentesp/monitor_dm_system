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


# [G-8](d) — extract_pdf_structure wraps an in-memory SHA-256 LRU.
# Tests pin (a) cache hit on identical bytes (b) mutation isolation
# (c) cache miss on different bytes (d) LRU eviction at 5th distinct PDF.


def test_extract_pdf_structure_cache_returns_same_sections_for_same_bytes():
    """Identical bytes → identical SectionBlock list (cache hit)."""
    pdf_bytes = _make_pdf_with_toc()
    first = extract_pdf_structure(pdf_bytes)
    second = extract_pdf_structure(pdf_bytes)
    assert len(first) == len(second)
    for a, b in zip(first, second, strict=False):
        assert a.heading_path == b.heading_path
        assert a.depth == b.depth
        assert a.page_start == b.page_start
        assert a.page_end == b.page_end
        assert a.text == b.text


def test_extract_pdf_structure_cache_isolates_mutations():
    """Mutating the returned list doesn't affect a subsequent cache hit.

    If two returns shared references (no copy), appending to the first
    call's heading_path or replacing the text would surface in the second
    call. The wrapper builds fresh instances via ``_deep_copy_sections``.
    """
    pdf_bytes = _make_pdf_with_toc()
    first = extract_pdf_structure(pdf_bytes)

    # Mutate the first call's structures aggressively.
    first[0].heading_path.append("EVIL")  # mutate the list
    first[0].text = "POISONED"  # mutate the str (rebinds)

    # Second call returns a fresh copy — mutations must NOT appear.
    second = extract_pdf_structure(pdf_bytes)
    assert "EVIL" not in second[0].heading_path
    assert second[0].text != "POISONED"
    assert first[0].heading_path != second[0].heading_path


def test_extract_pdf_structure_cache_misses_on_different_bytes():
    """Different bytes → different sections (different PDFs are not aliased)."""
    pdf_a = _make_pdf_with_toc()
    pdf_b = _make_pdf_without_toc()
    sections_a = extract_pdf_structure(pdf_a)
    sections_b = extract_pdf_structure(pdf_b)
    # The bookmarks PDF has 3 sections (2 chapter + 1 combat); the
    # bookmarkless one fallbacks to a heuristic that yields at least 1.
    assert len(sections_a) != len(sections_b) or any(
        a.heading_path != b.heading_path for a, b in zip(sections_a, sections_b, strict=False)
    )


def test_extract_pdf_structure_lru_evicts_at_fifth_distinct_pdf():
    """4-entry LRU evicts the LEAST RECENTLY USED entry on the 5th insert.

    With LRU semantics, after touching 5 distinct PDFs the oldest one
    is no longer in cache. We verify by mutating the first call's return
    and ensuring the 5th call (different bytes) is not aliased — but the
    deterministic check is: inserting 5 distinct PDFs and confirming the
    total cache size stays at 4.
    """
    from monitor_data.tools.ingest_tools.pdf_processing import (
        _PDF_STRUCTURE_CACHE_MAX,
        extract_pdf_structure,
    )

    # Build 5 distinct PDFs.
    pdfs = [_make_pdf_with_toc() for _ in range(_PDF_STRUCTURE_CACHE_MAX + 1)]
    # Sanity: 5 distinct contents.
    assert len({hash(p) for p in pdfs}) == _PDF_STRUCTURE_CACHE_MAX + 1

    for p in pdfs:
        extract_pdf_structure(p)

    # After the 5th call the cache must hold exactly the last 4 entries
    # (the first was evicted FIFO/LRU).
    from monitor_data.tools.ingest_tools.pdf_processing import (
        _PDF_STRUCTURE_CACHE,
    )

    assert len(_PDF_STRUCTURE_CACHE) == _PDF_STRUCTURE_CACHE_MAX


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


def test_extract_pdf_text_rejects_large_invalid_bytes():
    """Large non-PDF byte sequences raise PdfExtractionError (corrupt/truncated).

    The streaming budget was raised to 64 MB and large valid PDFs are now
    handled via a temp-file spill (not hard-rejected). Invalid bytes of any
    size still raise PdfExtractionError with a 'corrupt or truncated' message.
    """
    import pytest

    from monitor_data.tools.ingest_tools.pdf_processing import (
        PdfExtractionError,
        extract_pdf_text,
    )

    huge_bytes = b"0" * (50 * 1024 * 1024 + 1)
    with pytest.raises(PdfExtractionError, match="corrupt or truncated"):
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

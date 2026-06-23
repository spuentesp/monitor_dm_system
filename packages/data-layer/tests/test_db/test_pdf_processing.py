"""Unit tests for PDF extraction guards (T-083 edge-case matrix).

Covers the bad-input rows of `docs/FORGE_INGESTION_PLAN.md §A2` that previously
had a code guard but no test: empty file, oversized (>50MB streaming budget),
corrupt/truncated, and the happy path. All bad inputs must raise the
user-facing ``PdfExtractionError`` with a readable message — never hang or
leak a stack trace.

Hermetic: builds its fixtures in-memory with pymupdf, no network or DB.
"""

import fitz
import pytest

from monitor_data.tools.ingest_tools.pdf_processing import (
    PdfExtractionError,
    extract_pdf_text,
)


def _make_text_pdf(text: str = "Millhaven lies under an unnatural mist.") -> bytes:
    """Build a minimal one-page text PDF in memory."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_empty_file_rejected():
    with pytest.raises(PdfExtractionError, match="empty"):
        extract_pdf_text(b"")


def test_oversized_pdf_hits_streaming_budget():
    # 50MB + 1 byte — just over the budget. Zero-filled allocation is cheap.
    oversized = bytes(50 * 1024 * 1024 + 1)
    with pytest.raises(PdfExtractionError, match="streaming budget"):
        extract_pdf_text(oversized)


def test_corrupt_pdf_rejected():
    with pytest.raises(PdfExtractionError):
        extract_pdf_text(b"%PDF-1.4 this is not actually a valid pdf body")


def test_error_is_user_facing():
    # The message is surfaced verbatim in the job error, so the marker must hold.
    assert PdfExtractionError.user_facing is True
    err = PdfExtractionError("The file is empty (0 bytes).")
    assert "empty" in str(err)


def test_happy_path_extracts_text():
    pages = extract_pdf_text(_make_text_pdf())
    assert len(pages) == 1
    assert pages[0]["page_number"] == 1
    assert "Millhaven" in pages[0]["text"]

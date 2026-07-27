"""
ingest_tools — Document ingestion and chunking.

LAYER: 1 (data-layer)

This package provides document extraction, chunking, and format detection
for the MONITOR data-layer.  It is organized into four sub-modules:

    _models          — Data classes (IngestedChunk, SectionBlock), constants,
                       tokenization helpers, optional-dependency guards.

    _chunking        — Token-level text splitting, topic inference, semantic
                       classification, section-level chunk assembly.

    pdf_processing   — PDF text extraction (basic + structure-aware), font
                       analysis, heading detection, column layout sorting.

    multi_format     — Non-PDF format ingestion (text, Markdown, HTML, DOCX,
                       EPUB), universal ``ingest_file`` dispatcher, format
                       detection.

The public API is re-exported here for backward compatibility — existing
``from monitor_data.tools.ingest_tools import X`` statements continue to
work unchanged after the module-to-package conversion.
"""

# Data classes & constants
# Core chunking
from monitor_data.tools.ingest_tools._chunking import (
    _infer_chunk_type,
    _infer_topic_tags,
    _looks_like_heading,
    _split_structured_blocks,
    chunk_text,
)

# ---------------------------------------------------------------------------
# Private helpers re-exported for test access
# ---------------------------------------------------------------------------
# Tests import these directly via ``from monitor_data.tools.ingest_tools import ...``
# They are NOT part of the public API and are excluded from __all__.
from monitor_data.tools.ingest_tools._models import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OVERLAP_RATIO,
    ENCODING,
    RULEBOOK_CHUNK_SIZE,
    IngestedChunk,
    SectionBlock,
    _detokenize,
    _split_tokens,
    _tokenize,
)

# Contradiction detection (EPIC 2)
from monitor_data.tools.ingest_tools.contradiction_detection import (
    detect_contradictions,
)

# Multi-format ingestion & format detection
from monitor_data.tools.ingest_tools.multi_format import (
    _extract_docx_text,
    _extract_epub_text,
    _strip_html,
    _strip_markdown,
    detect_format,
    ingest_docx,
    ingest_epub,
    ingest_file,
    ingest_html,
    ingest_markdown,
    ingest_text,
)

# PDF extraction & ingestion
from monitor_data.tools.ingest_tools.pdf_processing import (
    extract_pdf_structure,
    extract_pdf_text,
    ingest_pdf,
)

__all__ = [
    # Data classes
    "IngestedChunk",
    "SectionBlock",
    # Constants
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_OVERLAP_RATIO",
    "RULEBOOK_CHUNK_SIZE",
    "ENCODING",
    # Chunking
    "chunk_text",
    # PDF
    "extract_pdf_text",
    "extract_pdf_structure",
    "ingest_pdf",
    # Multi-format
    "ingest_text",
    "ingest_markdown",
    "ingest_html",
    "ingest_docx",
    "ingest_epub",
    "ingest_file",
    "detect_format",
    # Contradiction detection
    "detect_contradictions",
    # Private helpers re-exported for tests
    "_split_tokens",
    "_tokenize",
    "_detokenize",
    "_looks_like_heading",
    "_infer_topic_tags",
    "_infer_chunk_type",
    "_split_structured_blocks",
    "_strip_markdown",
    "_strip_html",
    "_extract_docx_text",
    "_extract_epub_text",
]

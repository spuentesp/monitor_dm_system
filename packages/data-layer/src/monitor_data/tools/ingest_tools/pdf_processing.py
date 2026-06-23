"""
PDF-specific extraction and ingestion.

LAYER: 1 (data-layer)
IMPORTS FROM: pymupdf (fitz), _models, _chunking

Handles PDF text extraction (basic and structure-aware), heading detection
via font metadata, column layout sorting, and section grouping.  The
``ingest_pdf`` entry point combines extraction with section-level chunking.
"""

from __future__ import annotations

import atexit
import logging
import os
import tempfile
from typing import Any, List, Optional

import fitz  # pymupdf

from monitor_data.tools.ingest_tools._chunking import (
    _chunk_section,
    _looks_like_heading,
)
from monitor_data.tools.ingest_tools._models import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OVERLAP_RATIO,
    IngestedChunk,
    SectionBlock,
)

logger = logging.getLogger(__name__)


class PdfExtractionError(ValueError):
    """Raised when a PDF cannot be turned into usable text, with a human reason.

    The message is surfaced verbatim in the ingestion job's error, so it must
    read like guidance ("scanned image, no text layer") not a stack trace.
    """

    # The ingestion pipeline shows this message to the user as-is, without the
    # exception class name prefix (see _truncate_error).
    user_facing = True


# Above this size we open the PDF from a temp file on disk (PyMuPDF memory-maps
# it) instead of holding a second full copy in an in-memory fitz stream buffer.
# This lets large rulebooks (e.g. a 100+ MB corebook) ingest instead of being
# hard-rejected. Configurable via env for tighter-memory deployments.
_PDF_STREAM_BUDGET_BYTES: int = int(
    os.environ.get("MONITOR_PDF_STREAM_BUDGET_BYTES", str(64 * 1024 * 1024))
)
# Temp files created for large PDFs, cleaned up at process exit.
_PDF_TEMP_FILES: set[str] = set()


def _cleanup_pdf_temp_files() -> None:
    for path in list(_PDF_TEMP_FILES):
        try:
            os.unlink(path)
        except OSError:
            pass
        _PDF_TEMP_FILES.discard(path)


atexit.register(_cleanup_pdf_temp_files)


def _open_pdf(pdf_bytes: bytes) -> "fitz.Document":
    """Open a PDF with clear, actionable errors for the common bad inputs.

    Small PDFs are opened from an in-memory stream. Large PDFs (over the stream
    budget) are spilled to a temp file and opened by path so PyMuPDF can
    memory-map them, keeping peak memory bounded for big rulebooks.
    """
    if not pdf_bytes:
        raise PdfExtractionError("The file is empty (0 bytes).")
    try:
        if len(pdf_bytes) > _PDF_STREAM_BUDGET_BYTES:
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            try:
                tmp.write(pdf_bytes)
                tmp.flush()
                tmp.close()
                doc = fitz.open(tmp.name, filetype="pdf")
                # Tie the temp file's lifetime to the document; remove it on close.
                _PDF_TEMP_FILES.add(tmp.name)
                _orig_close = doc.close

                def _close_and_cleanup() -> None:
                    _orig_close()
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
                    _PDF_TEMP_FILES.discard(tmp.name)

                doc.close = _close_and_cleanup  # type: ignore[method-assign]
            except Exception:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
                raise
        else:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except PdfExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 — fitz raises a variety of types
        raise PdfExtractionError(
            f"This file could not be opened as a PDF (corrupt or truncated): {exc}"
        ) from exc
    # Password-protected PDFs report needs_pass; try the empty password once.
    if getattr(doc, "needs_pass", False):
        if not doc.authenticate(""):
            doc.close()
            raise PdfExtractionError(
                "This PDF is password-protected. Remove the password and re-upload."
            )
    if doc.page_count == 0:
        doc.close()
        raise PdfExtractionError("This PDF has no pages.")
    return doc


# ---------------------------------------------------------------------------
# Basic PDF text extraction
# ---------------------------------------------------------------------------


def extract_pdf_text(pdf_bytes: bytes) -> List[dict]:
    """
    Extract text from a PDF, page by page.

    DL-B2: Uses pymupdf for high-fidelity text extraction that handles
    multi-column layouts, rotated pages, and embedded fonts better than
    pdfminer or pypdf.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        List of {"page_number": int, "text": str} dicts (1-indexed pages).
        Pages with no extractable text are omitted.

    Raises:
        PdfExtractionError: empty/corrupt/encrypted PDF, or a scanned document
            with no extractable text layer.
    """
    pages: List[dict[str, Any]] = []
    doc = _open_pdf(pdf_bytes)
    try:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append({"page_number": page_num, "text": text})
    finally:
        doc.close()
    if not pages:
        raise PdfExtractionError(
            "No extractable text found — this looks like a scanned/image-only "
            "PDF. OCR it first, then re-upload."
        )
    return pages


# ---------------------------------------------------------------------------
# Structure-aware PDF extraction
# ---------------------------------------------------------------------------


def extract_pdf_structure(pdf_bytes: bytes) -> list:
    """
    Extract PDF bookmark tree and assign page text to each section span.

    Uses fitz.get_toc() for heading hierarchy when bookmarks exist.
    Falls back to _looks_like_heading() heuristic when no bookmarks are found.

    Returns a list of SectionBlock ordered by page_start.
    """
    doc = _open_pdf(pdf_bytes)
    toc = doc.get_toc(simple=False)  # [[level, title, page_1indexed, ...], ...]

    if toc:
        sections = []
        for i, entry in enumerate(toc):
            level = entry[0]
            title = entry[1]
            page_1indexed = entry[2]
            page_start = page_1indexed - 1  # convert to 0-indexed

            # page_end = start of next entry at same or higher level, minus 1
            page_end = doc.page_count - 1
            for j in range(i + 1, len(toc)):
                if toc[j][0] <= level:
                    page_end = max(page_start, toc[j][2] - 2)
                    break

            # Build heading_path by collecting ancestor titles at lower levels
            path: list[str] = []
            current_level = level
            for k in range(i - 1, -1, -1):
                if toc[k][0] < current_level:
                    path.insert(0, toc[k][1])
                    current_level = toc[k][0]
                    if current_level == 1:
                        break
            path.append(title)

            # Collect text from page range
            text_parts = [
                doc[p].get_text()
                for p in range(max(0, page_start), min(doc.page_count, page_end + 1))
            ]
            text = "\n".join(text_parts).strip()

            sections.append(
                SectionBlock(
                    heading_path=path,
                    depth=level - 1,
                    page_start=page_start,
                    page_end=page_end,
                    text=text,
                )
            )
        doc.close()
        return sections

    # Fallback: no bookmarks — use heuristic heading detection page by page
    sections = []
    current_heading = ["(untitled)"]
    current_depth = 0
    current_start = 0
    current_texts: List[str] = []

    for page_num in range(doc.page_count):
        page_text = doc[page_num].get_text()
        lines = page_text.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped and _looks_like_heading(stripped):
                if current_texts:
                    sections.append(
                        SectionBlock(
                            heading_path=current_heading,
                            depth=current_depth,
                            page_start=current_start,
                            page_end=page_num,
                            text="\n".join(current_texts).strip(),
                        )
                    )
                current_heading = [stripped]
                current_depth = 0
                current_start = page_num
                current_texts = []
            else:
                current_texts.append(line)

    # Flush last section
    if current_texts or not sections:
        sections.append(
            SectionBlock(
                heading_path=current_heading,
                depth=current_depth,
                page_start=current_start,
                page_end=doc.page_count - 1,
                text="\n".join(current_texts).strip(),
            )
        )

    doc.close()
    return sections


# ---------------------------------------------------------------------------
# PDF font / layout helpers
# ---------------------------------------------------------------------------


def _is_bold_span(span: dict) -> bool:
    """Return True if a pymupdf span is bold via font name or flags."""
    font_name = span.get("font", "").lower()
    if any(m in font_name for m in ("bold", "black", "heavy", "demi", "extb")):
        return True
    return bool(span.get("flags", 0) & 16)


def _sort_page_blocks_reading_order(blocks: list[dict], page_width: float) -> list[dict]:
    """
    Sort text blocks from a single page into natural reading order.

    Single-column: sort top-to-bottom (y0 ascending).
    Two-column: detect the column split, sort left column top-to-bottom then
    right column top-to-bottom.  Full-width blocks (chapter banners, running
    headers/footers) are merged back in at their original y0 position.

    Two-column heuristic: both halves of the page must have ≥ 2 blocks, and
    none of the candidate column blocks may span more than 65% of the page
    width (a block that wide is almost certainly a full-width element).

    Requires each block dict to carry '_x0', '_y0', '_x1' bbox fields.
    """
    if len(blocks) < 2 or page_width <= 0:
        return blocks

    midpoint = page_width / 2
    full_width_threshold = page_width * 0.65

    full_width: list[dict] = []
    column_blocks: list[dict] = []
    for b in blocks:
        if (b["_x1"] - b["_x0"]) >= full_width_threshold:
            full_width.append(b)
        else:
            column_blocks.append(b)

    left = [b for b in column_blocks if b["_x0"] < midpoint]
    right = [b for b in column_blocks if b["_x0"] >= midpoint]
    is_two_column = len(left) >= 2 and len(right) >= 2

    if is_two_column:
        left.sort(key=lambda b: b["_y0"])
        right.sort(key=lambda b: b["_y0"])
        column_ordered = left + right
    else:
        column_ordered = sorted(column_blocks, key=lambda b: (b["_y0"], b["_x0"]))

    # Re-insert full-width blocks at their vertical position
    fw_sorted = sorted(full_width, key=lambda b: b["_y0"])
    result: list[dict] = []
    fw_idx = 0
    for cb in column_ordered:
        while fw_idx < len(fw_sorted) and fw_sorted[fw_idx]["_y0"] <= cb["_y0"]:
            result.append(fw_sorted[fw_idx])
            fw_idx += 1
        result.append(cb)
    while fw_idx < len(fw_sorted):
        result.append(fw_sorted[fw_idx])
        fw_idx += 1

    return result


def _extract_pdf_structure(pdf_bytes: bytes) -> tuple[list[dict], float, int]:
    """
    Extract text blocks from a PDF with per-block font metadata.

    Uses pymupdf ``dict`` mode to expose span-level font sizes and bold flags
    so headings can be detected by size/weight rather than text heuristics.

    Returns:
        (raw_blocks, body_font_size) where each block is:
            {"text": str, "page_number": int, "font_size": float, "is_bold": bool}
        body_font_size is the most common font size weighted by character count.
    """
    raw_blocks: list[dict] = []
    image_block_count = 0

    doc = _open_pdf(pdf_bytes)
    try:
        for page_num, page in enumerate(doc, start=1):
            page_width = page.rect.width
            page_raw: list[dict] = []
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # 0 = text, 1 = image
                    if block.get("type") == 1:
                        image_block_count += 1
                    continue

                spans: list[dict] = []
                lines_text: list[str] = []
                for line in block.get("lines", []):
                    line_parts: list[str] = []
                    for span in line.get("spans", []):
                        t = span.get("text", "")
                        if t.strip():
                            spans.append(span)
                            line_parts.append(t)
                    if line_parts:
                        lines_text.append("".join(line_parts))

                if not spans:
                    continue

                block_text = "\n".join(lines_text).strip()
                if not block_text:
                    continue

                total_chars = sum(len(s.get("text", "")) for s in spans)
                dom_size: float = 12.0
                if total_chars:
                    dom_size = (
                        sum(s.get("size", 12.0) * len(s.get("text", "")) for s in spans)
                        / total_chars
                    )

                bold_chars = sum(len(s.get("text", "")) for s in spans if _is_bold_span(s))
                is_bold = bool(total_chars and bold_chars / total_chars >= 0.6)
                bbox = block.get("bbox", (0.0, 0.0, 0.0, 0.0))

                page_raw.append(
                    {
                        "text": block_text,
                        "page_number": page_num,
                        "font_size": round(dom_size, 2),
                        "is_bold": is_bold,
                        "_x0": float(bbox[0]),
                        "_y0": float(bbox[1]),
                        "_x1": float(bbox[2]),
                    }
                )

            # Sort blocks in reading order, correctly handling two-column layouts.
            raw_blocks.extend(
                {k: v for k, v in b.items() if not k.startswith("_")}
                for b in _sort_page_blocks_reading_order(page_raw, page_width)
            )
    finally:
        doc.close()

    if not raw_blocks:
        return [], 12.0, image_block_count

    # Body size = font size with the most total characters
    size_weight: dict[float, int] = {}
    for b in raw_blocks:
        sz = round(b["font_size"], 1)
        size_weight[sz] = size_weight.get(sz, 0) + len(b["text"])
    body_size = max(size_weight, key=lambda s: size_weight[s])

    return raw_blocks, body_size, image_block_count


def _is_table_header(text: str) -> bool:
    """Return True for bold blocks that are table column headers, not section headings."""
    # Tab-separated or multi-space column headers (e.g. "Successes\t\tResult")
    if "\t" in text or "      " in text:
        return True
    # Attribution lines like "- The Book of Nod" or bullet-prefixed lines
    stripped = text.strip()
    if stripped.startswith(("- ", "• ", "* ", "— ")):
        return True
    return False


def _classify_heading_levels(raw_blocks: list[dict], body_size: float) -> list[dict]:
    """
    Annotate blocks with heading_level (1/2/3) or None for body text.

    Level assignment (checked in order):
        1 — font_size >= 1.35× body AND ≤ 12 words AND ≤ 120 chars
        2 — font_size >= 1.15× body AND ≤ 12 words AND ≤ 120 chars
        3 — bold AND font_size >= body AND ≤ 10 words AND not a table header
              AND no trailing sentence punct
    """
    for block in raw_blocks:
        text = block["text"].strip()
        size = block["font_size"]
        bold = block["is_bold"]
        words = text.split()
        short = len(words) <= 12 and len(text) <= 120
        ends_sentence = bool(words) and text[-1] in ".!?"

        if size >= body_size * 1.35 and short:
            block["heading_level"] = 1
        elif size >= body_size * 1.15 and short:
            block["heading_level"] = 2
        elif (
            bold
            and size >= body_size
            and len(words) <= 10
            and not ends_sentence
            and text
            and not _is_table_header(text)
        ):
            block["heading_level"] = 3
        else:
            block["heading_level"] = None

    return raw_blocks


def _group_blocks_by_section(blocks: list[dict]) -> list[dict]:
    """
    Group consecutive body blocks under their current heading context.

    A level-1 heading clears levels 2 and 3; level-2 clears level 3.
    Body text from consecutive pages under the same heading is merged into
    one section, giving the chunker cross-page continuity.

    Returns list of:
        {"headings": List[str], "body": [{"text": str, "page_number": int}]}
    """
    heading_stack: list[Optional[str]] = [None, None, None]
    sections: list[dict] = []
    current_body: list[dict] = []
    current_headings: list[str] = []

    def _clean_heading(text: str) -> str:
        """Collapse internal whitespace/newlines in a heading to a single space."""
        return " ".join(text.split())

    def flush() -> None:
        if current_body:
            sections.append({"headings": list(current_headings), "body": list(current_body)})
            current_body.clear()

    for block in blocks:
        level = block.get("heading_level")
        if level is not None:
            flush()
            idx = level - 1
            heading_stack[idx] = _clean_heading(block["text"])
            for i in range(idx + 1, len(heading_stack)):
                heading_stack[i] = None
            current_headings = [h for h in heading_stack if h]
        else:
            current_body.append(
                {
                    "text": block["text"],
                    "page_number": block["page_number"],
                }
            )

    flush()
    return sections


# ---------------------------------------------------------------------------
# Public PDF ingestion API
# ---------------------------------------------------------------------------


def ingest_pdf(
    pdf_bytes: bytes,
    source_name: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
    metadata: Optional[dict] = None,
) -> List[IngestedChunk]:
    """
    Extract text from a PDF and chunk into section-tagged, embedding-ready pieces.

    Uses pymupdf font metadata (size and bold weight) to detect chapter,
    section, and subsection headings.  Body text is collected across page
    boundaries under the same heading context, eliminating the per-page
    splits that caused ~78 % of chunks to end mid-sentence.  Chunks are
    split at paragraph/sentence boundaries rather than raw token offsets.

    Each chunk's metadata includes:
        section_path      — "Chapter 4: Disciplines > Animalism" (string)
        section_headings  — ["Chapter 4: Disciplines", "Animalism"] (list)
        chunk_type        — "rules" | "lore" | "table" | "stat_block" | …
        topic_tags        — ["system", "rules", "character_creation", …]
        page_number       — first page of the section body

    Args:
        pdf_bytes:    Raw PDF file bytes (from MinIO or upload).
        source_name:  Logical document name / slug (provenance key).
        max_tokens:   Token limit per chunk (default 512).
        overlap_ratio: Overlap fraction between consecutive chunks (default 10 %).
        metadata:     Additional payload fields stored alongside each chunk.

    Returns:
        Flat list of IngestedChunk objects in document order.
    """
    raw_blocks, body_size, image_block_count = _extract_pdf_structure(pdf_bytes)
    if image_block_count:
        logger.warning(
            "'%s': skipped %d image block(s) during PDF extraction "
            "(embedded images are not transcribed — use OCR or alt-text for visual content).",
            source_name,
            image_block_count,
        )
    if not raw_blocks:
        return []

    blocks = _classify_heading_levels(raw_blocks, body_size)
    sections = _group_blocks_by_section(blocks)
    if not sections:
        return []

    overlap_tokens = max(1, int(max_tokens * overlap_ratio))
    base_metadata = dict(metadata or {})
    all_chunks: list[IngestedChunk] = []

    for section in sections:
        section_chunks = _chunk_section(
            section,
            source_name,
            len(all_chunks),
            max_tokens,
            overlap_tokens,
            base_metadata,
        )
        all_chunks.extend(section_chunks)

    return all_chunks


def extract_pdf_tables(pdf_bytes: bytes) -> List[dict]:
    """
    Extract structured tables from PDF pages using pymupdf's table detection.

    Uses page.find_tables() to detect table boundaries, then extracts
    text content from each cell. Tables are returned as structured dicts
    with row data preserved.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        List of table dicts with keys:
          - page_number: int (1-indexed)
          - table_bounding_box: (x0, y0, x1, y1) tuple
          - extracted_table: list of lists of strings (rows x cols)
          - row_count: int
          - col_count: int
        Pages with no detectable tables return empty list.
    """
    tables: List[dict[str, Any]] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_num, page in enumerate(doc, start=1):
            table_finder = page.find_tables()
            for table in table_finder.tables:
                try:
                    extracted = table.extract()
                except Exception:
                    extracted = []
                if extracted:
                    tables.append(
                        {
                            "page_number": page_num,
                            "table_bounding_box": table.bbox,
                            "extracted_table": extracted,
                            "row_count": table.row_count,
                            "col_count": table.col_count,
                        }
                    )
    return tables


def extract_tables_as_sections(pdf_bytes: bytes) -> List[SectionBlock]:
    """
    Convert detected PDF tables into SectionBlock items for downstream DSPy processing.

    Each detected table becomes a SectionBlock with:
      - heading_path: ["Random Tables", <page_number>]
      - text: tab-separated table content (one row per line)
      - page_start/page_end: same page (tables don't span pages here)

    This makes tables available as sections for random_table_extraction DSPy module.
    """
    tables = extract_pdf_tables(pdf_bytes)
    sections: List[SectionBlock] = []
    for t in tables:
        # Build tab-separated table text
        rows = t["extracted_table"]
        tab_text = "\t".join("\t".join(str(cell) for cell in row) for row in rows)
        sections.append(
            SectionBlock(
                heading_path=[f"Random Tables (page {t['page_number']})"],
                depth=0,
                page_start=t["page_number"] - 1,
                page_end=t["page_number"] - 1,
                text=tab_text,
            )
        )
    return sections

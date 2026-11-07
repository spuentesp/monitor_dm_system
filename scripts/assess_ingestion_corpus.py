#!/usr/bin/env python3
"""Measure PDF text and bookmark coverage using local files and no LLM calls.

Run: uv run python scripts/assess_ingestion_corpus.py examples/*.pdf
The JSON output contains counts and timings, never extracted source text.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import fitz
from monitor_data.tools.ingest_tools.pdf_processing import extract_pdf_structure


def assess(path: Path) -> dict:
    data = path.read_bytes()
    with fitz.open(stream=data, filetype="pdf") as doc:
        page_count = len(doc)
        bookmarks = len(doc.get_toc())
        chars = [len(page.get_text().strip()) for page in doc]

    started = time.perf_counter()
    sections = extract_pdf_structure(data)
    elapsed = time.perf_counter() - started
    covered = {
        page
        for section in sections
        for page in range(max(0, section.page_start), min(page_count, section.page_end + 1))
    }
    return {
        "file": path.name,
        "bytes": len(data),
        "pages": page_count,
        "bookmarks": bookmarks,
        "pages_without_text": sum(count == 0 for count in chars),
        "pages_under_100_characters": sum(count < 100 for count in chars),
        "text_characters": sum(chars),
        "sections": len(sections),
        "sections_without_text": sum(not section.text.strip() for section in sections),
        "pages_outside_sections": page_count - len(covered),
        "section_extraction_seconds": round(elapsed, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="+", type=Path)
    args = parser.parse_args()
    results = []
    failed = False
    for path in args.pdf:
        try:
            results.append(assess(path))
        except (OSError, ValueError, RuntimeError) as exc:
            failed = True
            results.append({"file": path.name, "error": str(exc)})
    print(json.dumps(results, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

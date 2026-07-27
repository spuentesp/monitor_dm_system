"""Section digest dataclass and builder functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SectionDigest:
    """One coherent section of source text with its heading path and chunk provenance."""

    section_path: str
    text: str
    min_page: int
    min_chunk_index: int
    chunk_ids: list[str] = field(default_factory=list)
    semantic_category: str | None = None
    chunk_records: list[dict[str, Any]] = field(default_factory=list)


def append_section_chunk(
    sections: dict[str, dict[str, Any]],
    *,
    section_path: str,
    page: int,
    idx: int,
    text: str,
    chunk_id: str | None = None,
    semantic_category: str | None = None,
) -> None:
    """Accumulate chunk text into a per-section buffer while tracking order and provenance."""
    if section_path not in sections:
        sections[section_path] = {
            "texts": [],
            "min_page": page,
            "min_chunk_index": idx,
        }
    else:
        if page < sections[section_path]["min_page"]:
            sections[section_path]["min_page"] = page
        if idx < sections[section_path]["min_chunk_index"]:
            sections[section_path]["min_chunk_index"] = idx

    sections[section_path]["texts"].append(
        {
            "page": page,
            "idx": idx,
            "text": text,
            "chunk_id": chunk_id,
            "semantic_category": semantic_category,
        }
    )


def build_section_digests(
    sections: dict[str, dict[str, Any]],
    *,
    max_words: int,
) -> list[SectionDigest]:
    """Convert accumulated section buffers into ordered, trimmed digests."""
    digests: list[SectionDigest] = []
    for section_path, data in sections.items():
        ordered = sorted(data["texts"], key=lambda t: (t["page"], t["idx"]))
        combined = " ".join(t["text"] for t in ordered)
        words = combined.split()
        if len(words) > max_words:
            combined = " ".join(words[:max_words])

        semantic_category = next(
            (item.get("semantic_category") for item in ordered if item.get("semantic_category")),
            None,
        )
        chunk_ids = [str(item["chunk_id"]) for item in ordered if item.get("chunk_id")]

        digests.append(
            SectionDigest(
                section_path=section_path,
                text=combined,
                min_page=data["min_page"],
                min_chunk_index=data["min_chunk_index"],
                chunk_ids=chunk_ids,
                semantic_category=semantic_category,
                chunk_records=list(ordered),
            )
        )

    digests.sort(key=lambda section: (section.min_page, section.min_chunk_index))
    return digests


def format_section_context(section: SectionDigest) -> str:
    """Format a section digest as a labeled heading plus body for DSPy prompts."""
    heading = section.section_path or "General"
    return f"# Section: {heading}\n\n{section.text}"

"""
Chunking logic — topic tagging, semantic classification, and text splitting.

LAYER: 1 (data-layer)
IMPORTS FROM: tiktoken (via _models), monitor_data.schemas.tag_pool

This module contains the structure-aware text chunker (``chunk_text``) and
all the helper functions it depends on for topic inference, semantic
classification, and boundary detection.  It also provides ``_chunk_section``
used by both PDF and multi-format ingestion paths.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from monitor_data.tools.ingest_tools._models import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OVERLAP_RATIO,
    IngestedChunk,
    _detokenize,
    _split_tokens,
    _tokenize,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heading heuristic
# ---------------------------------------------------------------------------


def _looks_like_heading(text: str) -> bool:
    """Heuristic check for short section headings."""
    normalized = " ".join(text.split())
    if not normalized or len(normalized) > 80:
        return False
    if normalized.endswith((".", "!", "?")):
        return False
    letters = [ch for ch in normalized if ch.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
    return (
        upper_ratio >= 0.7
        or (len(normalized.split()) <= 8 and normalized == normalized.title())
        or normalized.endswith(":")
    )


# ---------------------------------------------------------------------------
# Topic inference
# ---------------------------------------------------------------------------


_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "system": (
        "d20",
        "d12",
        "d10",
        "d8",
        "d6",
        "dice",
        "roll",
        "check",
        "save",
        "modifier",
        "hit points",
        "hp",
        "initiative",
        "combat",
        "round",
        "turn",
        "attack",
        "damage",
        "skill",
        "ability",
        "strength",
        "dexterity",
        "armor",
    ),
    "rules": (
        "when you",
        "if you",
        "on a failure",
        "on a success",
        "must",
        "may",
        "test",
        "combat",
        "initiative",
        "damage",
        "attack",
        "difficulty",
        "skill check",
    ),
    "character_creation": (
        "background",
        "class",
        "origin",
        "character creation",
        "level",
        "xp",
        "advancement",
        "trait",
        "attribute",
        "ability score",
    ),
    "equipment": (
        "weapon",
        "armor",
        "gear",
        "equipment",
        "inventory",
        "item",
        "tool",
        "ammo",
        "repair",
        "ship module",
    ),
    "prices": ("cost", "price", "credits", "currency", "silver", "gold", "debt"),
    "lore": (
        "history",
        "legend",
        "myth",
        "empire",
        "sector",
        "station",
        "world",
        "culture",
        "religion",
        "war",
        "catastrophe",
        "ruin",
        "faction",
        "society",
    ),
    "factions": ("faction", "guild", "order", "cult", "corporation", "crew", "union"),
    "locations": ("planet", "sector", "city", "station", "moon", "region", "location"),
    "creatures": ("creature", "monster", "beast", "alien", "npc", "enemy"),
}


def _infer_topic_tags(text: str, section_path: Optional[str] = None) -> List[str]:
    """Attach coarse topic tags used by later focused extraction passes."""
    haystack = f"{section_path or ''}\n{text}".lower()
    tags: set[str] = set()

    for tag, keywords in _TOPIC_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            tags.add(tag)

    if (
        re.search(r"\b\d+\s+(credits|gp|sp|cp)\b", haystack)
        or "price" in haystack
        or "cost" in haystack
    ):
        tags.add("prices")
    if haystack.count("|") >= 2 or re.search(r"\b\d{1,3}\b.*\b\d{1,3}\b", haystack):
        tags.add("tables")
    if not tags:
        tags.add("general")

    return sorted(tags)


def _infer_chunk_type(text: str, topic_tags: List[str]) -> str:
    """Classify chunk shape for UI/debugging and targeted retrieval."""
    normalized = text.strip()
    if normalized.count("|") >= 2 or "tables" in topic_tags:
        return "table"
    if normalized.count(":") >= 3 and len(normalized.splitlines()) >= 3:
        return "stat_block"
    if "system" in topic_tags or "rules" in topic_tags:
        return "rules"
    if "lore" in topic_tags or "factions" in topic_tags or "locations" in topic_tags:
        return "lore"
    return "paragraph"


# ---------------------------------------------------------------------------
# Semantic category classifier
# ---------------------------------------------------------------------------
# Delegates entirely to TagPool — no vocabulary is hardcoded here.
# ---------------------------------------------------------------------------


def _classify_semantic_category(
    headings: list[str],
    body_text: str,
    topic_tags: list[str],
) -> str:
    """
    Assign a universal ontological category to a chunk via TagPool.

    Priority: headings (most reliable) → topic_tags → body text scan.
    """
    from monitor_data.schemas.tag_pool import TagPool

    # 1. Headings — scan from most-specific (deepest) to least-specific
    for heading in reversed(headings):
        cat = TagPool.classify_text(heading)
        if cat:
            return cat

    # 2. Normalise topic_tags through the pool
    for tag in topic_tags:
        cat = TagPool.normalize(tag)
        if cat and cat != "general":
            return cat

    # 3. Body text scan (first 400 chars is enough for section openers)
    cat = TagPool.classify_text(body_text[:400])
    if cat:
        return cat

    return "general"


# ---------------------------------------------------------------------------
# Block splitting
# ---------------------------------------------------------------------------


def _split_structured_blocks(text: str) -> List[dict]:
    """Break raw text into logical blocks while preserving nearby headings."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    blocks: List[dict] = []
    current_heading: Optional[str] = None

    for paragraph in paragraphs:
        if _looks_like_heading(paragraph):
            current_heading = " ".join(paragraph.split())[:160]
            continue

        topic_tags = _infer_topic_tags(paragraph, current_heading)
        blocks.append(
            {
                "text": paragraph,
                "section_path": current_heading,
                "topic_tags": topic_tags,
                "chunk_type": _infer_chunk_type(paragraph, topic_tags),
            }
        )

    if not blocks and text.strip():
        topic_tags = _infer_topic_tags(text)
        blocks.append(
            {
                "text": text.strip(),
                "section_path": None,
                "topic_tags": topic_tags,
                "chunk_type": _infer_chunk_type(text, topic_tags),
            }
        )
    return blocks


# ---------------------------------------------------------------------------
# Public chunking API
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    source_name: str,
    is_rulebook: bool = False,
    *,
    page_number: Optional[int] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
    metadata: Optional[dict] = None,
) -> List[IngestedChunk]:
    """
    Split text into structure-aware, topic-tagged chunks.

    Chunks still respect the token budget, but they now try to keep logical
    paragraph/section boundaries together and store coarse topic metadata so
    downstream passes can retrieve only likely rules, lore, system, or table
    sections.

    Args:
        is_rulebook: When True, uses 1024-token chunks instead of the default
                     512-token chunks. Rulebook sources benefit from larger
                     chunks to keep rules context together.
    """
    if not text.strip():
        return []

    from monitor_data.tools.ingest_tools._models import RULEBOOK_CHUNK_SIZE

    chunk_size = RULEBOOK_CHUNK_SIZE if is_rulebook else max_tokens
    overlap_tokens = max(1, int(chunk_size * overlap_ratio))
    max_tokens = chunk_size
    base_metadata = dict(metadata or {})
    blocks = _split_structured_blocks(text)

    chunks: List[IngestedChunk] = []
    buffer_texts: List[str] = []
    buffer_types: List[str] = []
    buffer_tags: set[str] = set()
    buffer_tokens = 0
    buffer_section: Optional[str] = None
    chunk_index = 0

    def flush_buffer() -> None:
        nonlocal buffer_texts, buffer_types, buffer_tags, buffer_tokens, buffer_section, chunk_index
        if not buffer_texts:
            return
        chunk_text_str = "\n\n".join(buffer_texts).strip()
        token_count = len(_tokenize(chunk_text_str))
        chunk_metadata = {
            **base_metadata,
            "section_path": buffer_section,
            "chunk_type": buffer_types[0] if len(set(buffer_types)) == 1 else "mixed",
            "topic_tags": sorted(buffer_tags) or ["general"],
            "semantic_category": _classify_semantic_category(
                [buffer_section] if buffer_section else [],
                chunk_text_str,
                sorted(buffer_tags) or ["general"],
            ),
        }
        chunk_id = IngestedChunk.stable_id(source_name, chunk_index, chunk_text_str)
        chunks.append(
            IngestedChunk(
                chunk_id=chunk_id,
                source_name=source_name,
                page_number=page_number,
                chunk_index=chunk_index,
                text=chunk_text_str,
                token_count=token_count,
                metadata=chunk_metadata,
            )
        )
        chunk_index += 1
        buffer_texts = []
        buffer_types = []
        buffer_tags = set()
        buffer_tokens = 0
        buffer_section = None

    for block in blocks:
        block_text = block["text"]
        block_tokens = len(_tokenize(block_text))

        if block_tokens > max_tokens:
            flush_buffer()
            token_ids = _tokenize(block_text)
            for sub_ids in _split_tokens(token_ids, max_tokens, overlap_tokens):
                sub_text = _detokenize(sub_ids)
                chunk_metadata = {
                    **base_metadata,
                    "section_path": block.get("section_path"),
                    "chunk_type": block.get("chunk_type", "paragraph"),
                    "topic_tags": block.get("topic_tags", ["general"]),
                    "semantic_category": _classify_semantic_category(
                        [str(block["section_path"])] if block.get("section_path") else [],
                        sub_text,
                        block.get("topic_tags", ["general"]),
                    ),
                }
                chunk_id = IngestedChunk.stable_id(source_name, chunk_index, sub_text)
                chunks.append(
                    IngestedChunk(
                        chunk_id=chunk_id,
                        source_name=source_name,
                        page_number=page_number,
                        chunk_index=chunk_index,
                        text=sub_text,
                        token_count=len(sub_ids),
                        metadata=chunk_metadata,
                    )
                )
                chunk_index += 1
            continue

        if buffer_texts and buffer_tokens + block_tokens > max_tokens:
            previous_chunk_text = "\n\n".join(buffer_texts).strip()
            overlap_seed = _detokenize(_tokenize(previous_chunk_text)[-overlap_tokens:]).strip()
            flush_buffer()
            if overlap_seed:
                overlap_seed_tokens = len(_tokenize(overlap_seed))
                if overlap_seed_tokens + block_tokens < max_tokens:
                    buffer_texts = [overlap_seed]
                    buffer_types = [block.get("chunk_type", "paragraph")]
                    buffer_tags = set(block.get("topic_tags", []))
                    buffer_tokens = overlap_seed_tokens
                    buffer_section = block.get("section_path")

        if buffer_section is None:
            buffer_section = block.get("section_path")
        buffer_texts.append(block_text)
        buffer_types.append(block.get("chunk_type", "paragraph"))
        buffer_tags.update(block.get("topic_tags", []))
        buffer_tokens += block_tokens

    flush_buffer()
    return chunks


# ---------------------------------------------------------------------------
# Section-level chunking (used by PDF and Markdown ingestion)
# ---------------------------------------------------------------------------


def _split_at_boundaries(text: str) -> list[str]:
    """
    Split text at paragraph then sentence boundaries.

    Paragraph splits (double newline) are preferred.  Long paragraphs
    (> 80 tokens) are further split at sentence endings so chunk edges do
    not fall mid-sentence.
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    parts: list[str] = []
    for para in paragraphs:
        if len(_tokenize(para)) <= 80:
            parts.append(para)
            continue
        # Split at sentence endings before a capital letter or bullet
        sents = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\u2022\(\[])", para)
        parts.extend(s.strip() for s in sents if s.strip())
    return parts or [text.strip()]


def _chunk_section(
    section: dict,
    source_name: str,
    start_index: int,
    max_tokens: int,
    overlap_tokens: int,
    base_metadata: dict,
) -> list[IngestedChunk]:
    """
    Chunk a single section's body into token-limited IngestedChunks.

    Splits at sentence/paragraph boundaries; falls back to token-level
    splitting only when a single sentence exceeds max_tokens.
    """
    headings: list[str] = section["headings"]
    body: list[dict] = section["body"]
    if not body:
        return []

    section_path = " > ".join(headings) if headings else None
    first_page: int = body[0]["page_number"]
    combined = "\n\n".join(b["text"] for b in body)
    topic_tags = _infer_topic_tags(combined, section_path)
    chunk_type = _infer_chunk_type(combined, topic_tags)
    semantic_category = _classify_semantic_category(headings, combined, topic_tags)
    section_meta: dict = {
        **base_metadata,
        "section_path": section_path,
        "section_headings": headings,
        "chunk_type": chunk_type,
        "topic_tags": topic_tags,
        "semantic_category": semantic_category,
    }

    parts = _split_at_boundaries(combined)
    chunks: list[IngestedChunk] = []
    idx = start_index
    buffer: list[str] = []
    buf_tokens = 0

    def emit(text: str) -> None:
        nonlocal idx
        text = text.strip()
        if not text:
            return
        chunks.append(
            IngestedChunk(
                chunk_id=IngestedChunk.stable_id(source_name, idx, text),
                source_name=source_name,
                page_number=first_page,
                chunk_index=idx,
                text=text,
                token_count=len(_tokenize(text)),
                metadata=section_meta,
            )
        )
        idx += 1

    for part in parts:
        part_toks = len(_tokenize(part))

        if part_toks > max_tokens:
            # Oversized part — flush buffer then split by tokens with overlap
            if buffer:
                joined = "\n\n".join(buffer)
                emit(joined)
                overlap_text = _detokenize(_tokenize(joined)[-overlap_tokens:]).strip()
                buffer = [overlap_text] if overlap_text else []
                buf_tokens = len(_tokenize(overlap_text)) if overlap_text else 0
            for sub_ids in _split_tokens(_tokenize(part), max_tokens, overlap_tokens):
                emit(_detokenize(sub_ids))
            continue

        if buf_tokens + part_toks > max_tokens:
            joined = "\n\n".join(buffer)
            emit(joined)
            overlap_text = _detokenize(_tokenize(joined)[-overlap_tokens:]).strip()
            buffer = [overlap_text] if overlap_text else []
            buf_tokens = len(_tokenize(overlap_text)) if overlap_text else 0

        buffer.append(part)
        buf_tokens += part_toks

    if buffer:
        emit("\n\n".join(buffer))

    return chunks

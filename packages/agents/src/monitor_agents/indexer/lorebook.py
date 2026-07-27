"""
DSPy modules for lorebook intelligence.

- LorebookKeywordExtractor: extracts trigger keywords from content
- LorebookIngestionModule: analyzes a document chunk and proposes lorebook entries

2026-07-22 migration: bare dspy.Predict string literals were rejected
by DSPy 3.x's signature parser (requires arrow separator). Converted
to proper dspy.Signature classes following the pattern in
prompts/memory_extraction.py and prompts/session_ingest.py.
"""

from __future__ import annotations

import json
import re

import dspy
from monitor_data.schemas.lorebook import LorebookEntryDraft

# ---------------------------------------------------------------------------
# Signatures — declared as dspy.Signature classes so the framework can
# parse input/output fields cleanly.
# ---------------------------------------------------------------------------


class LorebookKeywordExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """Extract 3-8 lowercase trigger keywords from a piece of lore text.

    Keywords should be:
    - 1-2 words maximum
    - Specific (proper nouns, significant terms)
    - Lowercase
    - Avoid articles (the, a, an), prepositions (of, in, at), conjunctions
    """

    content: str = dspy.InputField(desc="The lore text to extract keywords from.")

    keywords: str = dspy.OutputField(
        desc=('A JSON list of 3-8 lowercase keywords. Example: ["dragon", "mithril", "smaug"]'),
    )


class LorebookIngestionSignature(dspy.Signature):  # type: ignore[misc]
    """Propose one lorebook entry from a document chunk.

    Rules:
    - content should be 1-3 sentences, factual, and game-relevant
    - keywords must be things a PLAYER would type in conversation
    - avoid duplicate keywords already in use (see existing_keywords)
    - tags help scene-aware filtering (e.g., "combat", "royalty", "dungeon")
    - confidence: 0.9 = highly confident (clear facts), 0.6 = uncertain
    """

    chunk: str = dspy.InputField(desc="A text chunk from a world-building document.")
    existing_keywords: str = dspy.InputField(
        desc="Comma-separated keywords already in use; avoid duplicates.",
    )
    tags_str: str = dspy.InputField(
        desc="Comma-separated tags hint for scene-aware filtering.",
    )

    entry: str = dspy.OutputField(
        desc=(
            "A JSON object with fields: "
            '{"keywords": [...], "content": "...", "priority": 50, '
            '"tags": [...], "confidence": 0.8}'
        ),
    )


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "but",
        "for",
        "nor",
        "yet",
        "his",
        "her",
        "its",
    }
)


def _fallback_keywords(content: str, limit: int = 8) -> list[str]:
    """If the LLM output isn't valid JSON, fall back to extracting
    capitalized proper-noun-ish words from the content."""
    nouns = re.findall(r"\b[A-Z][a-z]{2,}\b", content)
    seen: list[str] = []
    for w in nouns:
        low = w.lower()
        if low in _STOPWORDS:
            continue
        if low in seen:
            continue
        seen.append(low)
        if len(seen) >= limit:
            break
    return seen


class LorebookKeywordExtractor(dspy.Module):  # type: ignore[misc]
    """Extract trigger keywords from a piece of lore text."""

    def __init__(self) -> None:
        super().__init__()
        self._extract = dspy.Predict(LorebookKeywordExtractionSignature)

    def forward(self, content: str) -> list[str]:
        if not content or not content.strip():
            return []
        result = self._extract(content=content)
        raw = getattr(result, "keywords", "")
        try:
            keywords = json.loads(str(raw).strip())
            if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
                return [k.lower().strip() for k in keywords[:8] if k.strip()]
        except Exception:
            pass
        return _fallback_keywords(content)


class LorebookIngestionModule(dspy.Module):  # type: ignore[misc]
    """Analyze a document chunk and propose one or more lorebook entry drafts.

    Designed to be called per chunk during bulk document ingestion.
    """

    def __init__(self) -> None:
        super().__init__()
        self._propose = dspy.Predict(LorebookIngestionSignature)

    def forward(
        self,
        chunk: str,
        existing_keywords: list[str] | None = None,
        priority_hint: int = 50,
        tags: list[str] | None = None,
    ) -> LorebookEntryDraft:
        existing_str = ", ".join(existing_keywords or [])
        tags_str = ", ".join(tags or [])

        result = self._propose(
            chunk=chunk,
            existing_keywords=existing_str,
            tags_str=tags_str,
        )

        raw_entry = getattr(result, "entry", "")
        try:
            draft = json.loads(str(raw_entry).strip())
            return LorebookEntryDraft(
                keywords=[k.lower().strip() for k in (draft.get("keywords") or [])],
                content=str(draft.get("content", "")),
                priority=int(draft.get("priority", priority_hint)),
                tags=list(draft.get("tags") or []),
                confidence=float(draft.get("confidence", 0.5)),
            )
        except Exception:
            return LorebookEntryDraft(
                keywords=[],
                content=chunk[:500],
                priority=priority_hint,
                tags=list(tags or []),
                confidence=0.3,
            )

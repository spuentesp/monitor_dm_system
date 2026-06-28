"""
DSPy modules for lorebook intelligence.

- LorebookKeywordExtractor: extracts trigger keywords from content
- LorebookIngestionModule: analyzes a document chunk and proposes lorebook entries
"""

from __future__ import annotations

import dspy

from monitor_data.schemas.lorebook import LorebookEntryDraft


class LorebookKeywordExtractor(dspy.Module):
    """
    Extract 3-8 trigger keywords from a lorebook content string.

    Keywords should be short (1-2 words), specific, and likely to appear
    in player speech. Avoid generic terms like "the", "a", "and", etc.
    """

    def forward(self, content: str) -> list[str]:
        """
        Args:
            content: The lore text to extract keywords from.

        Returns:
            List of 3-8 lowercase keywords, deduplicated.
        """
        extract = dspy.Predict("""
You are a keyword extraction assistant for a tabletop RPG lorebook system.

Given a piece of lore text, extract 3-8 trigger keywords that a player
would likely type when referencing this lore. Keywords should be:
- 1-2 words maximum
- Specific (proper nouns, significant terms)
- Lowercase
- Avoid articles (the, a, an), prepositions (of, in, at), conjunctions

Input: "{content}"

Output a JSON list of lowercase keywords, e.g.: ["dragon", "mithril", "smaug"]
""")
        result = extract(content=content)
        try:
            import json

            keywords = json.loads(result.strip())
            if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
                return [k.lower().strip() for k in keywords[:8] if k.strip()]
        except Exception:
            pass

        # Fallback: extract capitalized words
        import re

        nouns = re.findall(r"\b[A-Z][a-z]{2,}\b", content)
        seen = []
        for w in nouns:
            if w.lower() not in ("the", "and", "but", "for", "nor", "yet", "his", "her", "its"):
                seen.append(w.lower())
        return list(dict.fromkeys(seen))[:8]


class LorebookIngestionModule(dspy.Module):
    """
    Analyze a document chunk and propose one or more lorebook entry drafts.

    Designed to be called per chunk during bulk document ingestion.
    """

    def forward(
        self,
        chunk: str,
        existing_keywords: list[str] | None = None,
        priority_hint: int = 50,
        tags: list[str] | None = None,
    ) -> LorebookEntryDraft:
        """
        Analyze a chunk and propose a lorebook entry.

        Args:
            chunk: Text chunk to analyze (up to ~2000 chars).
            existing_keywords: Known keywords to avoid (prevent duplicates).
            priority_hint: Suggested base priority (0-100).
            tags: Suggested tags for this chunk.

        Returns:
            LorebookEntryDraft with proposed keywords, content, priority, tags.
        """
        existing_str = ", ".join(existing_keywords or [])
        tags_str = ", ".join(tags or [])

        propose = dspy.Predict("""
You are analyzing a text chunk from a world-building document for a tabletop RPG lorebook.

Your task: create a lorebook entry that captures the most important facts from this chunk.
A lorebook entry is a KEY-VALUE pair of world knowledge that NPCs can reference during play.

Rules:
- Content should be 1-3 sentences, factual, and game-relevant
- Keywords must be things a PLAYER would type in conversation (short, natural language)
- Avoid duplicate keywords already in use: {existing_keywords}
- Tags help scene-aware filtering (e.g., "combat", "royalty", "dungeon")
- Confidence: 0.9 = highly confident (clear facts), 0.6 = uncertain (interpretive)

Input chunk:
---
{chunk}
---

Output a JSON object with fields:
{{
  "keywords": ["keyword1", "keyword2"],
  "content": "1-3 sentence lore fact",
  "priority": 50,
  "tags": ["tag1"],
  "confidence": 0.8
}}
""")
        result = propose(
            chunk=chunk,
            existing_keywords=existing_str,
            tags_str=tags_str,
        )

        try:
            import json

            draft = json.loads(result.strip())
            return LorebookEntryDraft(
                keywords=[k.lower().strip() for k in (draft.get("keywords") or [])],
                content=draft.get("content", ""),
                priority=draft.get("priority", priority_hint),
                tags=draft.get("tags") or [],
                confidence=draft.get("confidence", 0.5),
            )
        except Exception:
            return LorebookEntryDraft(
                keywords=[],
                content=chunk[:500],
                priority=priority_hint,
                tags=list(tags or []),
                confidence=0.3,
            )

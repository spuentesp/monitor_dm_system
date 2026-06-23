"""
Perception tools — fast entity detection for conversation pre-processing.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries + monitor_data.schemas.perception
CALLED BY: (standalone — not yet wired into MCP server)

The perception layer provides a lightweight "fast path" for entity detection
that runs BEFORE the heavy LLM agent loop.  This enables:

1. **Context pre-filtering**: Only load relevant entities from the vector store.
2. **Intent routing**: Skip LLM routing for obvious combat / OOC / dialogue.
3. **Novelty detection**: Flag new entities that aren't in the knowledge graph
   so CanonKeeper can prioritize them.

Backends
--------
- ``RegexPerceptionBackend``: Pure Python regex + heuristics.  Zero extra
  dependencies.  ~1-5 ms per sentence.  Good enough for most TTRPG inputs.
- ``SpacyPerceptionBackend``: spaCy transformer NER.  Requires ``spacy``
  + a model (``en_core_web_trf``).  ~20-50 ms.  Better for freeform text.
- ``GlinerPerceptionBackend``: GLiNER zero-shot NER.  Requires ``gliner``.
  ~15-30 ms.  Best for custom entity types without fine-tuning.

Usage (standalone)
------------------
>>> from monitor_data.tools.perception_tools import PerceptionPipeline
>>> pipe = PerceptionPipeline()
>>> result = await pipe.detect("I attack the Dragon with my Flame Sword")
>>> print(result.entities)
[DetectedEntity(text='Dragon', entity_type='character', ...),
 DetectedEntity(text='Flame Sword', entity_type='object', ...)]
>>> print(result.intent)
IntentType.COMBAT
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

import structlog

from monitor_data.schemas.perception import (
    DetectedEntity,
    DetectedEntityType,
    DetectionBackend,
    IntentType,
    PerceptionInput,
    PerceptionOutput,
)

logger = structlog.get_logger(__name__)

# =============================================================================
# REGEX BACKEND (zero dependencies)
# =============================================================================

# Patterns for entity detection.  These are intentionally broad — the LLM
# agent loop does the heavy validation.  We just need "good enough" fast
# detection to avoid wasting LLM tokens.

# Multi-word capitalized phrases (proper nouns).
# Matches sequences like "Dark Lord", "Shadow King", "Flame Sword".
# Each word must start with uppercase + lowercase letters, min 2 chars.
_CAPITALIZED_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")

# Quoted strings — potential entity names
_QUOTED_RE = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]+)["\u201c\u201d]')

# Known TTRPG patterns
_SPELL_RE = re.compile(
    r"\b("
    r"Fireball|Lightning Bolt|Heal|Cure\s+\w+|Magic Missile|"
    r"Shield|Invisibility|Fly|Teleport|Disintegrate|"
    r"[A-Z][a-z]+\s+(?:Strike|Bolt|Blast|Arrow|Wave|Barrage|Burst)"
    r")\b"
)

# Action keywords for intent detection
_COMBAT_KEYWORDS = {
    "attack",
    "hit",
    "strike",
    "slash",
    "stab",
    "shoot",
    "cast",
    "fire",
    "slash",
    "smite",
    "charge",
    "defend",
    "dodge",
    "block",
    "parry",
    "counter",
    "retreat",
    "flee",
    "kill",
    "damage",
    "hp",
    "initiative",
    "roll",
    "critical",
    "crit",
    "miss",
    "armor",
}

_EXPLORATION_KEYWORDS = {
    "look",
    "examine",
    "search",
    "investigate",
    "open",
    "close",
    "enter",
    "leave",
    "climb",
    "descend",
    "unlock",
    "lock",
    "pick",
    "trap",
    "secret",
    "hidden",
    "door",
    "chest",
    "room",
    "corridor",
    "hallway",
    "stairs",
    "map",
}

_DIALOGUE_KEYWORDS = {
    "say",
    "tell",
    "ask",
    "talk",
    "speak",
    "whisper",
    "shout",
    "yell",
    "reply",
    "respond",
    "greet",
    "convince",
    "persuade",
    "intimidate",
    "deceive",
    "lie",
    "bribe",
    "negotiate",
}

_SOCIAL_KEYWORDS = {
    " persuade",
    "intimidate",
    "deception",
    "insight",
    "persuasion",
    "charm",
    "barter",
    "trade",
    "buy",
    "sell",
    "hire",
    "recruit",
    "ally",
    "betray",
    "trust",
    "reputation",
}

_INVESTIGATION_KEYWORDS = {
    "clue",
    "evidence",
    "trace",
    "track",
    "footprint",
    "witness",
    "suspect",
    "motive",
    "alibi",
    "deduce",
    "analyze",
    "mystery",
}

_OOC_KEYWORDS = {
    "ooc",
    "out of character",
    "wait",
    "actually",
    "sorry",
    "let me",
    "i meant",
    "correction",
    "undo",
    "retcon",
    "((",
    "[[",
    "meta",
}

# Entity-type hint words (appear near the entity name)
_CHARACTER_HINTS = {
    "king",
    "queen",
    "prince",
    "princess",
    "lord",
    "lady",
    "sir",
    "knight",
    "wizard",
    "witch",
    "priest",
    "cleric",
    "rogue",
    "fighter",
    "barbarian",
    "ranger",
    "paladin",
    "bard",
    "druid",
    "monk",
    "warlock",
    "sorcerer",
    "npc",
    "dragon",
    "goblin",
    "orc",
    "elf",
    "dwarf",
    "halfling",
    "troll",
    "demon",
    "angel",
    "merchant",
    "guard",
    "captain",
    "sergeant",
    "general",
    "master",
    "mistress",
    "elder",
    "chief",
}

_LOCATION_HINTS = {
    "city",
    "town",
    "village",
    "castle",
    "fortress",
    "dungeon",
    "cave",
    "forest",
    "mountain",
    "river",
    "lake",
    "sea",
    "ocean",
    "island",
    "temple",
    "church",
    "shrine",
    "tavern",
    "inn",
    "shop",
    "market",
    "port",
    "harbor",
    "bridge",
    "tower",
    "ruins",
    "swamp",
    "desert",
    "plains",
    "valley",
    "garden",
    "room",
    "hall",
    "chamber",
    "crypt",
    "sewer",
    "mine",
}

_OBJECT_HINTS = {
    "sword",
    "axe",
    "bow",
    "shield",
    "armor",
    "helmet",
    "ring",
    "amulet",
    "potion",
    "scroll",
    "wand",
    "staff",
    "dagger",
    "mace",
    "spear",
    "crossbow",
    "cloak",
    "boots",
    "gauntlets",
    "key",
    "gem",
    "coin",
    "chest",
    "book",
    "map",
}

_FACTION_HINTS = {
    "guild",
    "order",
    "clan",
    "tribe",
    "cult",
    "brotherhood",
    "sisterhood",
    "council",
    "court",
    "army",
    "legion",
    "band",
    "company",
    "syndicate",
    "faction",
    "house",
    "kingdom",
    "empire",
    "republic",
}


def _classify_entity_type(text: str, context: str) -> DetectedEntityType:
    """Guess entity type from the text and surrounding context.

    Uses a simple keyword-matching heuristic.  This is intentionally
    conservative — false negatives are fine (the LLM will catch them).
    """
    text_lower = text.lower()
    context_lower = context.lower()

    # Check for spell patterns
    if _SPELL_RE.search(text):
        return DetectedEntityType.SPELL

    # Check hint words in entity text
    words = set(text_lower.split())

    if words & _CHARACTER_HINTS:
        return DetectedEntityType.CHARACTER
    if words & _LOCATION_HINTS:
        return DetectedEntityType.LOCATION
    if words & _OBJECT_HINTS:
        return DetectedEntityType.OBJECT
    if words & _FACTION_HINTS:
        return DetectedEntityType.FACTION

    # Check context (surrounding words)
    context_words = set(context_lower.split())

    # Score each type
    scores: dict[DetectedEntityType, int] = {
        DetectedEntityType.CHARACTER: len(context_words & _CHARACTER_HINTS),
        DetectedEntityType.LOCATION: len(context_words & _LOCATION_HINTS),
        DetectedEntityType.OBJECT: len(context_words & _OBJECT_HINTS),
        DetectedEntityType.FACTION: len(context_words & _FACTION_HINTS),
    }

    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best

    # Default: proper noun → character (most common in TTRPG)
    if text[0].isupper():
        return DetectedEntityType.CHARACTER

    return DetectedEntityType.CONCEPT


class RegexPerceptionBackend:
    """Pure regex + heuristic entity detector.

    Zero external dependencies.  Fast (~1-5 ms per input).
    Good enough for most structured TTRPG inputs where entity names
    are capitalized or quoted.
    """

    def detect_entities(self, text: str) -> List[DetectedEntity]:
        """Detect entities using regex patterns."""
        entities: list[DetectedEntity] = []
        seen_spans: set[tuple[int, int]] = set()

        # 1. Quoted strings — highest confidence
        for m in _QUOTED_RE.finditer(text):
            span = (m.start(), m.end())
            if span not in seen_spans:
                entity_text = m.group(1)
                entities.append(
                    DetectedEntity(
                        text=entity_text,
                        entity_type=_classify_entity_type(entity_text, text),
                        start=m.start() + 1,  # skip opening quote
                        end=m.end() - 1,  # skip closing quote
                        confidence=0.95,
                        metadata={"source": "quoted_string"},
                    )
                )
                seen_spans.add(span)

        # 2. Spell names
        for m in _SPELL_RE.finditer(text):
            span = (m.start(), m.end())
            if span not in seen_spans:
                entities.append(
                    DetectedEntity(
                        text=m.group(1),
                        entity_type=DetectedEntityType.SPELL,
                        start=m.start(),
                        end=m.end(),
                        confidence=0.9,
                        metadata={"source": "spell_pattern"},
                    )
                )
                seen_spans.add(span)

        # 3. Capitalized multi-word phrases (proper nouns)
        for m in _CAPITALIZED_RE.finditer(text):
            span = (m.start(), m.end())
            if span not in seen_spans:
                entity_text = m.group(1)

                # Skip common sentence starters
                if entity_text.lower() in {
                    "i",
                    "the",
                    "a",
                    "an",
                    "my",
                    "we",
                    "he",
                    "she",
                    "it",
                    "they",
                    "this",
                    "that",
                    "there",
                    "here",
                    "what",
                    "when",
                    "where",
                    "who",
                    "how",
                    "why",
                    "yes",
                    "no",
                    "ok",
                    "and",
                    "but",
                    "or",
                    "so",
                    "if",
                    "then",
                    "now",
                    "just",
                    "not",
                    "all",
                }:
                    continue

                # Skip if first word of text (likely sentence start)
                if m.start() == 0:
                    # Still check — could be a name starting the sentence
                    words = entity_text.split()
                    if len(words) == 1 and len(words[0]) <= 3:
                        continue

                # Skip short single words at sentence start
                if len(entity_text) <= 3 and m.start() < 5:
                    continue

                entities.append(
                    DetectedEntity(
                        text=entity_text,
                        entity_type=_classify_entity_type(entity_text, text),
                        start=m.start(),
                        end=m.end(),
                        confidence=0.7,
                        metadata={"source": "capitalized_pattern"},
                    )
                )
                seen_spans.add(span)

        # Deduplicate overlapping spans (keep longest)
        entities = _deduplicate_overlaps(entities)

        return entities

    def classify_intent(self, text: str) -> tuple[IntentType, float]:
        """Classify the intent of the input text.

        Returns (intent_type, confidence).
        """
        text_lower = text.lower()
        words = set(text_lower.split())

        # Score each intent
        scores = {
            IntentType.COMBAT: len(words & _COMBAT_KEYWORDS),
            IntentType.EXPLORATION: len(words & _EXPLORATION_KEYWORDS),
            IntentType.DIALOGUE: len(words & _DIALOGUE_KEYWORDS),
            IntentType.SOCIAL: len(words & _SOCIAL_KEYWORDS),
            IntentType.INVESTIGATION: len(words & _INVESTIGATION_KEYWORDS),
        }

        # Check OOC patterns
        ooc_count = sum(1 for kw in _OOC_KEYWORDS if kw in text_lower)
        if ooc_count >= 1:
            # OOC is very distinctive — high confidence even with 1 match
            return IntentType.OOC, min(0.9, 0.6 + ooc_count * 0.15)

        best_intent = max(scores, key=lambda k: scores[k])
        best_score = scores[best_intent]

        if best_score == 0:
            return IntentType.UNKNOWN, 0.0

        # Confidence based on keyword density
        confidence = min(0.95, 0.4 + best_score * 0.15)

        return best_intent, confidence


def _deduplicate_overlaps(entities: List[DetectedEntity]) -> List[DetectedEntity]:
    """Remove overlapping entities, keeping the longest / highest confidence."""
    if not entities:
        return entities

    # Sort by start position
    entities.sort(key=lambda e: e.start)

    result: list[DetectedEntity] = [entities[0]]
    for entity in entities[1:]:
        prev = result[-1]
        # If overlapping, keep the one with higher confidence or longer span
        if entity.start < prev.end:
            if entity.confidence > prev.confidence or (
                entity.confidence == prev.confidence
                and (entity.end - entity.start) > (prev.end - prev.start)
            ):
                result[-1] = entity
        else:
            result.append(entity)

    return result


# =============================================================================
# ABSTRACT BACKEND INTERFACE
# =============================================================================


class PerceptionBackend(ABC):
    """Abstract interface for perception backends."""

    @abstractmethod
    async def detect_entities(self, text: str) -> List[DetectedEntity]:
        """Detect entities in the given text."""

    @abstractmethod
    async def classify_intent(self, text: str) -> tuple[IntentType, float]:
        """Classify the intent of the text.  Returns (intent, confidence)."""


class RegexBackend(PerceptionBackend):
    """Regex backend wrapped as async PerceptionBackend."""

    def __init__(self) -> None:
        self._impl = RegexPerceptionBackend()

    async def detect_entities(self, text: str) -> List[DetectedEntity]:
        return self._impl.detect_entities(text)

    async def classify_intent(self, text: str) -> tuple[IntentType, float]:
        return self._impl.classify_intent(text)


# =============================================================================
# PLACEHOLDER BACKENDS (install optional deps to activate)
# =============================================================================


class SpacyBackend(PerceptionBackend):
    """spaCy NER backend.  Requires ``spacy`` + model.

    Usage:
        python -m spacy download en_core_web_trf
    """

    def __init__(self, model_name: str = "en_core_web_trf") -> None:
        try:
            import spacy

            self._nlp = spacy.load(model_name)
            logger.info("spacy_backend_loaded", model=model_name)
        except ImportError:
            raise ImportError(
                "spaCy not installed.  Install with: "
                "pip install spacy && python -m spacy download en_core_web_trf"
            )

    async def detect_entities(self, text: str) -> List[DetectedEntity]:
        doc = self._nlp(text)
        entities: list[DetectedEntity] = []
        for ent in doc.ents:
            # Map spaCy labels to our types
            type_map = {
                "PERSON": DetectedEntityType.CHARACTER,
                "GPE": DetectedEntityType.LOCATION,
                "LOC": DetectedEntityType.LOCATION,
                "FAC": DetectedEntityType.LOCATION,
                "ORG": DetectedEntityType.FACTION,
                "PRODUCT": DetectedEntityType.OBJECT,
                "WEAPON": DetectedEntityType.OBJECT,
                "WORK_OF_ART": DetectedEntityType.OBJECT,
                "LAW": DetectedEntityType.CONCEPT,
                "EVENT": DetectedEntityType.ACTION,
            }
            mapped = type_map.get(ent.label_, DetectedEntityType.CONCEPT)
            entities.append(
                DetectedEntity(
                    text=ent.text,
                    entity_type=mapped,
                    start=ent.start_char,
                    end=ent.end_char,
                    confidence=min(1.0, ent._.confidence if hasattr(ent._, "confidence") else 0.8),
                    metadata={"source": "spacy", "spacy_label": ent.label_},
                )
            )
        return entities

    async def classify_intent(self, text: str) -> tuple[IntentType, float]:
        # Fallback to regex intent classification for now
        return RegexPerceptionBackend().classify_intent(text)


class GlinerBackend(PerceptionBackend):
    """GLiNER zero-shot NER backend.  Requires ``gliner``.

    Usage:
        pip install gliner
    """

    # Entity labels for TTRPG domain
    TTRPG_LABELS = [
        "character",
        "location",
        "weapon",
        "armor",
        "spell",
        "item",
        "faction",
        "creature",
        "race",
        "class",
        "action",
    ]

    def __init__(
        self,
        model_name: str = "urchade/gliner_multi-v2.1",
        labels: Optional[List[str]] = None,
    ) -> None:
        try:
            from gliner import GLiNER

            self._model = GLiNER.from_pretrained(model_name)
            self._labels = labels or self.TTRPG_LABELS
            logger.info("gliner_backend_loaded", model=model_name)
        except ImportError:
            raise ImportError("GLiNER not installed.  Install with: pip install gliner")

    async def detect_entities(self, text: str) -> List[DetectedEntity]:
        entities_raw = self._model.predict_entities(text, self._labels)
        entities: list[DetectedEntity] = []

        label_to_type = {
            "character": DetectedEntityType.CHARACTER,
            "creature": DetectedEntityType.CHARACTER,
            "race": DetectedEntityType.CHARACTER,
            "class": DetectedEntityType.CHARACTER,
            "location": DetectedEntityType.LOCATION,
            "weapon": DetectedEntityType.OBJECT,
            "armor": DetectedEntityType.OBJECT,
            "item": DetectedEntityType.OBJECT,
            "spell": DetectedEntityType.SPELL,
            "faction": DetectedEntityType.FACTION,
            "action": DetectedEntityType.ACTION,
        }

        for ent in entities_raw:
            mapped = label_to_type.get(ent["label"], DetectedEntityType.CONCEPT)
            entities.append(
                DetectedEntity(
                    text=ent["text"],
                    entity_type=mapped,
                    start=ent["start"],
                    end=ent["end"],
                    confidence=ent.get("score", 0.8),
                    metadata={"source": "gliner", "gliner_label": ent["label"]},
                )
            )

        return _deduplicate_overlaps(entities)

    async def classify_intent(self, text: str) -> tuple[IntentType, float]:
        # Fallback to regex intent classification for now
        return RegexPerceptionBackend().classify_intent(text)


# =============================================================================
# PIPELINE (main entry point)
# =============================================================================


class PerceptionPipeline:
    """Main perception pipeline — fast entity detection + intent routing.

    This is the primary public API.  Use it standalone:

        >>> pipe = PerceptionPipeline()           # regex backend (default)
        >>> pipe = PerceptionPipeline("gliner")   # GLiNER backend
        >>> result = await pipe.detect("I attack the Dragon")

    Or integrate into an agent loop later (not wired yet).
    """

    def __init__(
        self,
        backend: str = "regex",
        known_entities: Optional[Sequence[str]] = None,
    ) -> None:
        self._backend: PerceptionBackend
        self._backend_name: DetectionBackend

        if backend == "regex":
            self._backend = RegexBackend()
            self._backend_name = DetectionBackend.REGEX
        elif backend == "spacy":
            self._backend = SpacyBackend()
            self._backend_name = DetectionBackend.SPACY
        elif backend == "gliner":
            self._backend = GlinerBackend()
            self._backend_name = DetectionBackend.GLINER
        else:
            raise ValueError(f"Unknown backend: {backend!r}. Choose from: regex, spacy, gliner")

        self._known_entities: set[str] = set(e.lower() for e in (known_entities or []))
        logger.info(
            "perception_pipeline_initialized",
            backend=self._backend_name.value,
            known_entities=len(self._known_entities),
        )

    @property
    def backend_name(self) -> DetectionBackend:
        return self._backend_name

    async def detect(self, text: str) -> PerceptionOutput:
        """Run the full perception pipeline on the given text.

        Parameters
        ----------
        text:
            Raw player / GM input.

        Returns
        -------
        PerceptionOutput
            Detected entities, classified intent, novelty info, timing.
        """
        t0 = time.perf_counter()

        entities = await self._backend.detect_entities(text)
        intent, intent_confidence = await self._backend.classify_intent(text)

        # Novelty detection
        novel: list[DetectedEntity] = []
        if self._known_entities:
            for entity in entities:
                is_known = entity.text.lower() in self._known_entities
                entity.is_known = is_known
                if not is_known:
                    novel.append(entity)
        else:
            novel = list(entities)  # no known list → all are "novel"

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return PerceptionOutput(
            entities=entities,
            intent=intent,
            intent_confidence=intent_confidence,
            novel_entities=novel,
            processing_time_ms=round(elapsed_ms, 2),
            backend=self._backend_name,
        )

    async def detect_with_input(self, inp: PerceptionInput) -> PerceptionOutput:
        """Run perception with a structured PerceptionInput.

        This overload supports passing ``known_entities`` for novelty detection
        and a ``session_id`` for future caching.
        """
        # Temporarily update known entities if provided
        if inp.known_entities is not None:
            old_known = self._known_entities
            self._known_entities = set(e.lower() for e in inp.known_entities)
            try:
                return await self.detect(inp.text)
            finally:
                self._known_entities = old_known
        return await self.detect(inp.text)

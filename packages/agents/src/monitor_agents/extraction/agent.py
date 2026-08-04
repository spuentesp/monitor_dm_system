import json
import logging
import re
from typing import Any
from uuid import UUID

import anyio
from monitor_agents.base import BaseAgent
from monitor_agents.loops.scene_support import (
    merge_entity_proposals,
    parse_entity_tags,
    turn_is_mechanically_bound,
)
from monitor_agents.extraction.memory_extraction import MemoryExtractor
from monitor_agents.extraction.narrative_entity_extraction import (
    NarrativeEntityExtractionModule,
)

logger = logging.getLogger(__name__)


_ARTICLES = {"the", "a", "an"}


def _significant_words(s: str) -> list[str]:
    """Lower-case split, drop common English articles and very short tokens."""
    return [w for w in (s or "").lower().split() if w and w not in _ARTICLES and len(w) >= 3]


def _is_partial_match(new_name: str, known_names: list[str]) -> bool:
    """Heuristic: does `new_name` likely refer to a known entity?

    True when:
      - the new name is a substring of a known name (new_name >= 3 chars, known >= 4), or
      - the new name's significant words (articles dropped) overlap with the
        significant words of a known name.

    The asymmetric threshold keeps short-but-specific new names (e.g. "Vex")
    matching while preventing false positives on common titles like "Sir"
    against unrelated entities.
    """
    n = (new_name or "").strip().lower()
    if len(n) < 3:
        return False
    n_significant = _significant_words(n)
    for known in known_names:
        if known is None:
            continue
        k = (known or "").strip().lower()
        if not k or len(k) < 4:
            continue
        if n in k or k in n:
            return True
        k_significant = _significant_words(k)
        # Match when at least one significant word from `new_name` is in the
        # known's significant words (article-dropped). Catches "the captain" ≈
        # "Captain Vex" (captain is significant in both).
        if n_significant and k_significant and any(w in k_significant for w in n_significant):
            return True
    return False


class ExtractionAgent(BaseAgent):
    """
    Agent responsible for extracting entities, memories, and facts from narrative text.
    """

    def __init__(self, agent_id: str, model: str | None = None) -> None:
        super().__init__(agent_type="extractor", agent_id=agent_id, model=model)

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        pass

    async def extract_new_entities(
        self,
        narrative_text: str | None,
        entity_context: list[dict[str, Any]],
        game_context: dict[str, Any],
        universe_id: UUID | None,
        pending_proposals: list[dict[str, Any]],
        resolution: dict[str, Any] | None,
        scene_id: UUID,
    ) -> dict[str, Any]:
        """
        P-7 / On-the-fly creation: Detect new entities mentioned in narration.
        """
        if not narrative_text:
            return {}

        known_names = [e.get("name", "") for e in entity_context if e.get("name")]
        known_entities_str = ", ".join(known_names) if known_names else "(empty world)"

        universe_context = ""
        if game_context:
            universe_context = game_context.get("name", "") or game_context.get("description", "")

        extractor = NarrativeEntityExtractionModule()
        try:
            result = await anyio.to_thread.run_sync(
                extractor.forward,
                narrative_text,
                known_entities_str,
                universe_context,
            )
        except Exception:
            logger.warning("Narrative entity extraction failed", exc_info=True)
            return {}

        raw_output = getattr(result, "new_entities", "[]")
        try:
            new_entities = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse new_entities JSON: %s", raw_output[:200])
            return {}

        if not isinstance(new_entities, list):
            return {}

        MIN_CONFIDENCE = 0.7
        proposals: list[dict[str, Any]] = []
        for entity in new_entities:
            if not isinstance(entity, dict):
                continue
            confidence = float(entity.get("confidence", 0.0))
            if confidence < MIN_CONFIDENCE:
                continue
            name = entity.get("name", "").strip()
            if not name:
                continue
            if name.lower() in [n.lower() for n in known_names]:
                continue
            if _is_partial_match(name, known_names):
                logger.debug("extract_new_entities: dropping %r (partial match of known)", name)
                continue

            proposal: dict[str, Any] = {
                "proposal_type": "ENTITY",
                "content": {
                    "name": name,
                    "entity_type": entity.get("entity_type", "CONCEPT"),
                    "description": entity.get("description", ""),
                    "is_archetype": False,
                },
                "summary": f"New entity detected in narration: {name}",
                "confidence": confidence,
                "authority": "SYSTEM",
                "proposer": "narrator",
                "universe_id": str(universe_id) if universe_id else "",
            }
            if universe_id:
                proposal["content"]["universe_id"] = str(universe_id)
            proposals.append(proposal)

        tags = parse_entity_tags(narrative_text)
        detected_names_lower = {p["content"]["name"].lower() for p in proposals}
        known_names_lower = {n.lower() for n in known_names}
        for tag in tags:
            name = tag["name"]
            if name.lower() in detected_names_lower or name.lower() in known_names_lower:
                continue
            proposal = {
                "proposal_type": "ENTITY",
                "content": {
                    "name": name,
                    "entity_type": "CONCEPT",
                    "description": "",
                    "is_archetype": False,
                    **({"universe_id": str(universe_id)} if universe_id else {}),
                },
                "summary": f"Tagged entity detected in narration: {name}",
                "confidence": 0.7,
                "authority": "SYSTEM",
                "proposer": "narrator",
                "universe_id": str(universe_id) if universe_id else "",
            }
            proposals.append(proposal)
            detected_names_lower.add(name.lower())

        mechanically_bound = turn_is_mechanically_bound(resolution)
        merged = merge_entity_proposals(
            pending_proposals, proposals, tags=tags, is_mechanically_bound=mechanically_bound
        )
        if merged == pending_proposals:
            return {}

        logger.info(
            "Extracted %d new entity proposals from narration (scene %s)",
            len(proposals),
            scene_id,
        )
        return {"pending_proposals": merged}

    async def extract_memories(
        self,
        narrative_text: str | None,
        actor_context: dict[str, Any] | None,
        resolution: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Task 4: Extract salient character memories from the narrative prose.
        """
        if not narrative_text or not actor_context:
            return {"memories_to_persist": []}

        actor_name = actor_context.get("name") or "the character"
        extractor = MemoryExtractor()
        try:
            memories = await anyio.to_thread.run_sync(
                extractor.forward,
                narrative_text,
                str(resolution.get("success_level") if resolution else "narrative"),
                actor_name,
            )
        except Exception:
            logger.warning("Memory extraction failed", exc_info=True)
            return {"memories_to_persist": []}

        return {"memories_to_persist": memories}

    async def extract_facts(
        self,
        narrative_text: str | None,
        established_facts: list[str],
        scene_id: UUID,
    ) -> dict[str, Any]:
        """
        Extract concrete facts from narration for continuity tracking.
        """
        if not narrative_text:
            return {}

        facts: list[str] = []

        entity_pattern = re.compile(r"\b(?:name(?:d|s)? (?:the |a |an )?)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
        seen_names: set[str] = set()
        for match in entity_pattern.finditer(narrative_text):
            name = match.group(1).strip()
            if name.lower() in {
                "the",
                "a",
                "an",
                "i",
                "you",
                "he",
                "she",
                "it",
                "they",
                "your",
                "his",
                "her",
                "its",
                "their",
                "this",
                "that",
                "roll",
                "strength",
                "dexterity",
                "intelligence",
                "charisma",
                "wisdom",
                "constitution",
            }:
                continue
            if name not in seen_names:
                seen_names.add(name)
                if " " in name or name not in {"I", "You", "He", "She", "It", "They"}:
                    facts.append(f"Named entity mentioned: {name}")

        state_patterns = [
            (
                re.compile(
                    r"\b(\w+)\s+(?:is|are|lies|remains)\s+(?:dead|motionless|destroyed|broken|sealed|open|closed)\b",
                    re.IGNORECASE,
                ),
                "State change: {0} is now {1}",
            ),
            (
                re.compile(
                    r"\b(?:you|the player)\s+(?:find|found|retrieve|retrieved|grab|grabbed|take|took)\s+(?:the\s+)?(\w+(?:\s+\w+)?)\b",
                    re.IGNORECASE,
                ),
                "Item acquired: {0}",
            ),
            (
                re.compile(
                    r"\b(?:door|hatch|panel|seal)\s+(?:opens|opened|breaks|broke|shatters|shattered)\b",
                    re.IGNORECASE,
                ),
                "Barrier breached",
            ),
        ]
        for pattern, template in state_patterns:
            for match in pattern.finditer(narrative_text):
                groups = match.groups()
                fact = template.format(*groups) if groups else template
                if fact not in facts:
                    facts.append(fact)

        existing = set(established_facts)
        new_facts = [f for f in facts if f not in existing]
        all_facts = list(established_facts) + new_facts

        if len(all_facts) > 50:
            all_facts = all_facts[-50:]

        if not new_facts:
            return {}

        logger.info(
            "Extracted %d new facts from narration (scene %s)",
            len(new_facts),
            scene_id,
        )
        return {"established_facts": all_facts}

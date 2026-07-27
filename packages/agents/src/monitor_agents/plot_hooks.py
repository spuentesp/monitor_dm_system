"""
PlotHookAgent — Detects dangling plot threads and suggests narrative hooks.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts
CALLED BY: CLI (Layer 3), UI backend

Use Cases: CF-4 (Plot hook suggestions), CF-5 (Contradiction detection)

This agent:
1. Queries Neo4j for open plot threads and unresolved facts
2. Queries MongoDB for recent scene history and turn outcomes
3. Uses LLM reasoning to suggest plot hooks, detect contradictions,
   and generate session prep materials
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_agents.base import BaseAgent

logger = logging.getLogger(__name__)


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class PlotHook(BaseModel):
    """A suggested narrative hook for the GM."""

    thread_id: str | None = Field(None, description="Related plot thread ID, if any")
    title: str = Field(description="Short title for the hook")
    description: str = Field(description="What the hook involves")
    urgency: str = Field(
        default="medium",
        description="How urgent this hook is: low, medium, high, critical",
    )
    suggested_scene_type: str = Field(
        default="exploration",
        description="Suggested scene type: action, dialogue, exploration, rest, combat, revelation",
    )
    connected_entities: list[str] = Field(
        default_factory=list,
        description="Entity names connected to this hook",
    )


class Contradiction(BaseModel):
    """A detected contradiction in the canon."""

    fact_a: str = Field(description="First conflicting fact")
    fact_b: str = Field(description="Second conflicting fact")
    severity: str = Field(
        default="medium",
        description="How serious: low (flavor), medium (notable), high (plot-breaking)",
    )
    explanation: str = Field(description="Why these facts contradict")
    suggestion: str = Field(description="How to resolve the contradiction")


class SessionPrep(BaseModel):
    """Session preparation materials for the GM."""

    recap: str = Field(description="Brief recap of recent events")
    open_threads: list[str] = Field(default_factory=list, description="Unresolved plot threads")
    hooks: list[PlotHook] = Field(default_factory=list, description="Suggested narrative hooks")
    npc_reminders: list[str] = Field(default_factory=list, description="NPCs the GM should remember")
    world_state_changes: list[str] = Field(default_factory=list, description="Recent changes to the world state")


class Handout(BaseModel):
    """A player handout generated from world data."""

    title: str = Field(description="Handout title")
    content: str = Field(description="Handout content in markdown format")
    handout_type: str = Field(
        default="letter",
        description="Type of handout: letter, map_note, prophecy, journal_entry, notice, rumor",
    )
    related_entities: list[str] = Field(default_factory=list, description="Entity names referenced in the handout")
    tone: str = Field(
        default="mysterious",
        description="Tone of the handout: mysterious, urgent, warm, ominous, neutral",
    )
    spoiler_level: str = Field(
        default="safe",
        description="Spoiler level: safe (no secrets), partial (some hints), full (reveals secrets)",
    )


# =============================================================================
# PLOT HOOK AGENT
# =============================================================================


class PlotHookAgent(BaseAgent):
    """
    Detects dangling plot threads and suggests narrative hooks.

    Use Cases:
        CF-4: Plot hook suggestions
        CF-5: Contradiction detection
        CF-7: Session prep assistant
    """

    def __init__(
        self,
        agent_type: str = "PlotHookAgent",
        agent_id: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(
            agent_type=agent_type,
            agent_id=agent_id or "plot-hook-agent",
            model=model,
        )

    # ------------------------------------------------------------------
    # CF-4: Plot Hook Suggestions
    # ------------------------------------------------------------------

    async def suggest_hooks(
        self,
        universe_id: UUID,
        story_id: UUID | None = None,
        max_hooks: int = 5,
    ) -> list[PlotHook]:
        """
        Suggest narrative hooks based on open plot threads and recent events.

        Args:
            universe_id: The universe to analyze
            story_id: Optional story to focus on
            max_hooks: Maximum number of hooks to return

        Returns:
            List of PlotHook suggestions
        """
        # 1. Fetch open plot threads from Neo4j
        threads_result = await self.call_tool(
            "neo4j_list_plot_threads",
            {"params": {"status": "active"}},
        )
        threads = self._parse_result(threads_result, "threads", [])

        # 2. Fetch recent scenes from MongoDB
        scenes_result = await self.call_tool(
            "mongodb_list_scenes",
            {"params": {"universe_id": str(universe_id), "limit": 10}},
        )
        scenes = self._parse_result(scenes_result, "scenes", [])

        # 3. Fetch entities with unresolved state tags
        entities_result = await self.call_tool(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "limit": 20}},
        )
        entities = self._parse_result(entities_result, "entities", [])

        # 4. Build context for LLM
        thread_summaries = []
        for t in threads[:10]:
            thread_summaries.append(
                f"- {t.get('title', 'Untitled')}: {t.get('description', 'No description')} "
                f"[status: {t.get('status', 'unknown')}]"
            )

        scene_summaries = []
        for s in scenes[:5]:
            scene_summaries.append(f"- {s.get('title', 'Untitled scene')}: {s.get('summary', 'No summary')}")

        entity_summaries = []
        for e in entities[:10]:
            tags = e.get("state_tags", [])
            if tags:
                entity_summaries.append(
                    f"- {e.get('name', 'Unknown')} ({e.get('entity_type', 'unknown')}): tags={tags}"
                )

        # 5. Use LLM to generate hooks
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a narrative advisor for a tabletop RPG. "
                    "Given the current state of the story (open threads, recent scenes, "
                    "and entity states), suggest compelling plot hooks that the GM can use "
                    "to drive the narrative forward. Each hook should be specific, actionable, "
                    "and connected to existing story elements."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Open plot threads:\n{chr(10).join(thread_summaries) or 'None'}\n\n"
                    f"Recent scenes:\n{chr(10).join(scene_summaries) or 'None'}\n\n"
                    f"Entities with state:\n{chr(10).join(entity_summaries) or 'None'}\n\n"
                    f"Suggest up to {max_hooks} plot hooks."
                ),
            },
        ]

        try:
            result: PlotHookListResponse = await self.call_llm_structured(
                PlotHookListResponse,
                messages,
                max_tokens=2048,
            )
            canon_names = extract_canon_entity_names(entities)
            grounded = filter_ungrounded_hooks(result.hooks, canon_names, min_grounded=1)
            return grounded[:max_hooks]
        except Exception:
            logger.warning("LLM hook generation failed, using heuristics", exc_info=True)
            return self._heuristic_hooks(threads, scenes, entities, max_hooks)

    # ------------------------------------------------------------------
    # CF-5: Contradiction Detection
    # ------------------------------------------------------------------

    async def detect_contradictions(
        self,
        universe_id: UUID,
        focus_entity_id: UUID | None = None,
    ) -> list[Contradiction]:
        """
        Detect contradictions in the canon for a given universe.

        Args:
            universe_id: The universe to check
            focus_entity_id: Optional entity to focus on

        Returns:
            List of detected Contradictions
        """
        # 1. Fetch facts for the universe
        facts_result = await self.call_tool(
            "neo4j_list_facts",
            {"filters": {"universe_id": str(universe_id), "limit": 50}},
        )
        facts = self._parse_result(facts_result, "facts", [])

        # 2. Fetch entity relationships
        entity_summaries = []
        if focus_entity_id:
            entities_result = await self.call_tool(
                "neo4j_get_entity",
                {"entity_id": str(focus_entity_id)},
            )
            entity_data = self._parse_result(entities_result, {}, {})
            if entity_data:
                entity_summaries.append(
                    f"- {entity_data.get('name', 'Unknown')} ({entity_data.get('entity_type', 'unknown')})"
                )
        else:
            entities_result = await self.call_tool(
                "neo4j_list_entities",
                {"filters": {"universe_id": str(universe_id), "limit": 20}},
            )
            entities_list = self._parse_result(entities_result, "entities", [])
            for e in entities_list[:10]:
                entity_summaries.append(f"- {e.get('name', 'Unknown')} ({e.get('entity_type', 'unknown')})")

        # 3. Build fact list for contradiction analysis
        fact_list = []
        for f in facts[:30]:
            fact_list.append(f"- [{f.get('canon_level', 'unknown')}] {f.get('content', f.get('text', 'No content'))}")

        # 4. Use LLM to detect contradictions
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a canon consistency checker for a tabletop RPG. "
                    "Analyze the following facts and identify any contradictions "
                    "(statements that cannot both be true). Rate severity as: "
                    "low (flavor inconsistency), medium (notable contradiction), "
                    "high (plot-breaking contradiction)."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Facts in this universe:\n{chr(10).join(fact_list) or 'No facts found'}\n\n"
                    f"Entities:\n{chr(10).join(entity_summaries) or 'No entities found'}\n\n"
                    "Identify any contradictions."
                ),
            },
        ]

        try:
            result: ContradictionListResponse = await self.call_llm_structured(
                ContradictionListResponse,
                messages,
                max_tokens=2048,
            )
            return result.contradictions
        except Exception:
            logger.warning("LLM contradiction detection failed", exc_info=True)
            return self._heuristic_contradictions(facts)

    # ------------------------------------------------------------------
    # CF-7: Session Prep
    # ------------------------------------------------------------------

    async def generate_session_prep(
        self,
        universe_id: UUID,
        story_id: UUID,
        session_number: int | None = None,
    ) -> SessionPrep:
        """
        Generate session preparation materials for the GM.

        Args:
            universe_id: The universe
            story_id: The story/campaign
            session_number: Optional session number for context

        Returns:
            SessionPrep with recap, hooks, NPC reminders, and world state changes
        """
        # 1. Fetch recent scenes
        scenes_result = await self.call_tool(
            "mongodb_list_scenes",
            {"params": {"story_id": str(story_id), "limit": 5}},
        )
        scenes = self._parse_result(scenes_result, "scenes", [])

        # 2. Fetch open threads
        threads_result = await self.call_tool(
            "neo4j_list_plot_threads",
            {"params": {"status": "active"}},
        )
        threads = self._parse_result(threads_result, "threads", [])

        # 3. Fetch hooks
        hooks = await self.suggest_hooks(universe_id, story_id, max_hooks=3)

        # 4. Build recap from recent scenes
        recap_parts = []
        for s in scenes[:3]:
            title = s.get("title", "Untitled")
            summary = s.get("summary", "No summary available")
            recap_parts.append(f"{title}: {summary}")

        recap = "\n".join(recap_parts) if recap_parts else "No recent scenes found."

        # 5. Extract NPC reminders from entities
        npc_reminders: list[str] = []
        for t in threads[:5]:
            involved = t.get("involved_entities", [])
            if isinstance(involved, list):
                npc_reminders.extend(str(e) for e in involved[:2])

        # 6. Get world state changes from recent facts
        facts_result = await self.call_tool(
            "neo4j_list_facts",
            {"universe_id": str(universe_id), "limit": 10},
        )
        facts = self._parse_result(facts_result, "facts", [])
        world_changes = [
            f.get("content", f.get("text", "")) for f in facts[:5] if f.get("canon_level") in ("canon", "established")
        ]

        return SessionPrep(
            recap=recap,
            open_threads=[t.get("title", "Untitled") for t in threads[:5]],
            hooks=hooks,
            npc_reminders=list(set(npc_reminders))[:5],
            world_state_changes=world_changes,
        )

    # ------------------------------------------------------------------
    # CF-6: Player Handouts
    # ------------------------------------------------------------------

    async def generate_handout(
        self,
        universe_id: UUID,
        handout_type: str = "letter",
        focus_entity_id: UUID | None = None,
        tone: str = "mysterious",
        spoiler_level: str = "safe",
    ) -> Handout:
        """
        Generate a player handout from world data.

        Creates an in-world document (letter, map note, prophecy, journal entry,
        notice, or rumor) that can be given to players as a physical or digital
        handout.

        Args:
            universe_id: The universe to draw from
            handout_type: Type of handout to generate
            focus_entity_id: Optional entity to center the handout around
            tone: Desired tone of the handout
            spoiler_level: How much secret information to include

        Returns:
            Handout with title, content, and metadata
        """
        # 1. Fetch relevant entities
        entity_summaries = []
        if focus_entity_id:
            entity_result = await self.call_tool(
                "neo4j_get_entity",
                {"entity_id": str(focus_entity_id)},
            )
            entity_data = self._parse_result(entity_result, {}, {})
            if entity_data:
                entity_summaries.append(
                    f"- {entity_data.get('name', 'Unknown')} "
                    f"({entity_data.get('entity_type', 'unknown')}): "
                    f"{entity_data.get('description', 'No description')}"
                )
        else:
            entities_result = await self.call_tool(
                "neo4j_list_entities",
                {"universe_id": str(universe_id), "limit": 10},
            )
            entities = self._parse_result(entities_result, "entities", [])
            for e in entities[:8]:
                entity_summaries.append(f"- {e.get('name', 'Unknown')} ({e.get('entity_type', 'unknown')})")

        # 2. Fetch relevant facts
        facts_result = await self.call_tool(
            "neo4j_list_facts",
            {"universe_id": str(universe_id), "limit": 15},
        )
        facts = self._parse_result(facts_result, "facts", [])

        fact_list = []
        for f in facts[:10]:
            canon = f.get("canon_level", "unknown")
            content = f.get("content", f.get("text", ""))
            # Filter by spoiler level
            if spoiler_level == "safe" and canon in ("secret", "hidden"):
                continue
            fact_list.append(f"- [{canon}] {content}")

        # 3. Fetch open threads for narrative hooks
        threads_result = await self.call_tool(
            "neo4j_list_plot_threads",
            {"params": {"status": "active"}},
        )
        threads = self._parse_result(threads_result, "threads", [])
        thread_summaries = [f"- {t.get('title', 'Untitled')}: {t.get('description', '')}" for t in threads[:5]]

        # 4. Use LLM to generate handout
        handout_type_descriptions = {
            "letter": "a personal letter from one character to another",
            "map_note": "a note or annotation found on a map or scroll",
            "prophecy": "a cryptic prophecy or omen",
            "journal_entry": "a diary or journal entry from a character",
            "notice": "a public notice, poster, or announcement",
            "rumor": "a piece of hearsay or tavern gossip",
        }
        type_desc = handout_type_descriptions.get(handout_type, "a document")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a creative writer for a tabletop RPG. "
                    "Generate an immersive in-world handout that the GM can give to players. "
                    "The handout should feel authentic, be written in-character, and "
                    "provide useful narrative information without breaking immersion. "
                    "Write the content in markdown format."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Generate {type_desc} for the players.\n\n"
                    f"Entities in the world:\n{chr(10).join(entity_summaries) or 'None'}\n\n"
                    f"Known facts:\n{chr(10).join(fact_list) or 'None'}\n\n"
                    f"Open plot threads:\n{chr(10).join(thread_summaries) or 'None'}\n\n"
                    f"Handout type: {handout_type}\n"
                    f"Tone: {tone}\n"
                    f"Spoiler level: {spoiler_level}\n\n"
                    "Create a compelling handout."
                ),
            },
        ]

        try:
            result: HandoutListResponse = await self.call_llm_structured(
                HandoutListResponse,
                messages,
                max_tokens=2048,
            )
            if result.handouts:
                return result.handouts[0]
        except Exception:
            logger.warning("LLM handout generation failed, using template", exc_info=True)

        return self._template_handout(handout_type, tone, spoiler_level, entity_summaries, fact_list)

    # ------------------------------------------------------------------
    # BaseAgent compliance
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Implemented for BaseAgent compliance; usually called via specific methods."""
        pass

    # ------------------------------------------------------------------
    # HEURISTIC FALLBACKS (when LLM is unavailable)
    # ------------------------------------------------------------------

    def _heuristic_hooks(
        self,
        threads: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        entities: list[dict[str, Any]],
        max_hooks: int,
    ) -> list[PlotHook]:
        """Generate hooks from heuristics when LLM is unavailable."""
        hooks = []

        # Open threads become hooks
        for t in threads[:max_hooks]:
            hooks.append(
                PlotHook(
                    thread_id=t.get("thread_id", t.get("id")),
                    title=f"Thread: {t.get('title', 'Untitled')}",
                    description=t.get("description", "An unresolved plot thread."),
                    urgency="high",
                    suggested_scene_type="revelation",
                    connected_entities=t.get("involved_entities", []),
                )
            )

        # Entities with state tags suggest hooks
        for e in entities[: max_hooks - len(hooks)]:
            tags = e.get("state_tags", [])
            if tags:
                hooks.append(
                    PlotHook(
                        title=f"State: {e.get('name', 'Unknown')}",
                        description=(
                            f"{e.get('name', 'Unknown')} has states: {', '.join(tags)}. "
                            "Consider how these affect the story."
                        ),
                        urgency="medium",
                        suggested_scene_type="dialogue",
                        connected_entities=[e.get("name", "")],
                    )
                )

        return hooks[:max_hooks]

    def _heuristic_contradictions(self, facts: list[dict[str, Any]]) -> list[Contradiction]:
        """Detect contradictions using simple heuristics.

        Patterns detected:
        - Negation: "X is alive" vs "X is not alive"
        - Status antonyms: alive/dead, married/single, free/captive,
          ally/enemy, friend/foe, present/absent
        - Location: "X is in <place>" vs "X is in <different place>"
        - Identity: "X is <role>" vs "X is <different role>"
        """
        import re as _re_loc

        contradictions: list[Contradiction] = []

        # Status antonyms (deeper detection beyond simple negation)
        status_antonym_pairs = [
            ("alive", "dead"),
            ("living", "dead"),
            ("married", "single"),
            ("free", "captive"),
            ("free", "imprisoned"),
            ("ally", "enemy"),
            ("friend", "foe"),
            ("present", "absent"),
            ("well", "sick"),
            ("healthy", "sick"),
            ("awake", "asleep"),
        ]

        # Group facts by entity
        entity_facts: dict[str, list[dict[str, Any]]] = {}
        for f in facts:
            entity_id = f.get("entity_id", f.get("source_id", ""))
            if entity_id:
                entity_facts.setdefault(entity_id, []).append(f)

        for entity_id, entity_fact_list in entity_facts.items():  # noqa: B007
            if len(entity_fact_list) < 2:
                continue
            for i, fa in enumerate(entity_fact_list):
                for fb in entity_fact_list[i + 1 :]:
                    text_a = fa.get("content", fa.get("text", ""))
                    text_b = fb.get("content", fb.get("text", ""))
                    content_a = text_a.lower()
                    content_b = text_b.lower()

                    # Pattern 1: negation
                    negation_words = ["not ", "never ", "no ", "isn't ", "doesn't "]
                    is_negation = False
                    for neg in negation_words:
                        if neg in content_a and neg.replace(" ", "") not in content_b:
                            if any(word in content_b for word in content_a.split()[:3]):
                                is_negation = True
                                break
                    if is_negation:
                        contradictions.append(
                            Contradiction(
                                fact_a=text_a,
                                fact_b=text_b,
                                severity="medium",
                                explanation="Negation-based contradiction detected.",
                                suggestion=("Review both facts and determine which is canonical."),
                            )
                        )
                        continue

                    # Pattern 2: status antonyms
                    for word_a, word_b in status_antonym_pairs:
                        if word_a in content_a and word_b in content_b:
                            contradictions.append(
                                Contradiction(
                                    fact_a=text_a,
                                    fact_b=text_b,
                                    severity="high",
                                    explanation=(f"Status contradiction: '{word_a}' vs '{word_b}'."),
                                    suggestion=(f"Resolve the {word_a}/{word_b} conflict for this entity."),
                                )
                            )
                            break

                    # Pattern 3: location conflict ("X is in/at <Place>")
                    loc_re = _re_loc.compile(
                        r"\b(?:is|in|at|lives? in|located in|found in)\s+"
                        r"([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)*)"
                    )
                    locs_a = loc_re.findall(text_a)
                    locs_b = loc_re.findall(text_b)
                    if locs_a and locs_b:
                        set_a = {loc.lower() for loc in locs_a}
                        set_b = {loc.lower() for loc in locs_b}
                        if set_a and set_b and not (set_a & set_b):
                            contradictions.append(
                                Contradiction(
                                    fact_a=text_a,
                                    fact_b=text_b,
                                    severity="medium",
                                    explanation=(f"Location contradiction: {locs_a} vs {locs_b}."),
                                    suggestion=("Determine where this entity currently is."),
                                )
                            )

        return contradictions[:10]

    def _template_handout(
        self,
        handout_type: str,
        tone: str,
        spoiler_level: str,
        entity_summaries: list[str],
        fact_list: list[str],
    ) -> Handout:
        """Generate a handout from templates when LLM is unavailable."""
        templates: dict[str, str] = {
            "letter": ("# A Letter Found\n\nTo whoever finds this,\n\n{content}\n\n— Written in haste"),
            "map_note": ("# Map Annotation\n\nA note scrawled in the margin of a map:\n\n{content}"),
            "prophecy": ('# An Ancient Prophecy\n\n*"{content}"*\n\n— Inscribed on weathered stone'),
            "journal_entry": ("# Journal Entry\n\n{content}\n\n— The journal ends here"),
            "notice": ("# Public Notice\n\n{content}\n\n— Posted for all to see"),
            "rumor": ('# Tavern Gossip\n\n*"{content}"*\n\n— Overheard at the inn'),
        }

        # Build content from available facts and entities
        content_parts = []
        if entity_summaries:
            content_parts.append("Regarding: " + "; ".join(entity_summaries[:3]))
        if fact_list:
            content_parts.append(fact_list[0].lstrip("- ") if fact_list else "Whispers of something yet to come.")

        content = "\n\n".join(content_parts) if content_parts else "The world holds many secrets yet to be discovered."
        template = templates.get(handout_type, templates["letter"])

        return Handout(
            title=f"Handout: {handout_type.replace('_', ' ').title()}",
            content=template.format(content=content),
            handout_type=handout_type,
            related_entities=[s.split("(")[0].strip().lstrip("- ") for s in entity_summaries[:3]],
            tone=tone,
            spoiler_level=spoiler_level,
        )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _parse_result(self, result: Any, key: str | dict[str, Any], default: Any) -> Any:
        """Parse MCP tool result, handling JSON strings and dicts."""
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return default
        if isinstance(result, dict):
            if isinstance(key, str):
                return result.get(key, default)
            return result
        return default


# =============================================================================
# RESPONSE WRAPPER SCHEMAS (for LLM structured output)
# =============================================================================


class PlotHookListResponse(BaseModel):
    """LLM response wrapper for plot hook suggestions."""

    hooks: list[PlotHook] = Field(default_factory=list)


class ContradictionListResponse(BaseModel):
    """LLM response wrapper for contradiction detection."""

    contradictions: list[Contradiction] = Field(default_factory=list)


class HandoutListResponse(BaseModel):
    """LLM response wrapper for handout generation."""

    handouts: list[Handout] = Field(default_factory=list)


# =============================================================================
# HOOK QUALITY GROUNDING (CF-4 enhancement)
# =============================================================================


def extract_canon_entity_names(entities: list[dict[str, Any]]) -> list[str]:
    """Extract canonical entity names from a list of entity dicts.

    Used to ground generated hooks to real entities from the scene/world
    so hooks are concrete rather than generic.

    Args:
        entities: List of entity dicts (from Neo4j)

    Returns:
        List of entity names, deduped, lowercased for matching
    """
    names: list[str] = []
    seen: set[str] = set()
    for e in entities:
        name = e.get("name")
        if not name:
            continue
        lowered = str(name).strip().lower()
        if lowered and lowered not in seen:
            seen.add(lowered)
            names.append(str(name).strip())
    return names


def _normalize_text(text: str) -> str:
    """Lowercase and strip non-alphanumeric chars (except spaces).

    Used for fuzzy matching entity names against hook text so that
    "Aldric's Quest" still matches canon entity "Aldric the Bold".
    """
    return "".join(c if c.isalnum() or c.isspace() else " " for c in text.lower())


def hook_is_grounded(hook: PlotHook, canon_entity_names: list[str]) -> bool:
    """Check whether a hook references at least one canon entity.

    The hook is grounded if:
    - Any name in canon_entity_names matches (tokenized) in hook.title, OR
    - Any name appears in hook.connected_entities, OR
    - canon_entity_names is empty (no canon available, accept hook as-is)

    Matching is normalized (apostrophes/punctuation treated as spaces)
    and token-based so that "Aldric" matches both "Aldric the Bold" and
    "Aldric's Quest".

    Args:
        hook: The hook to validate
        canon_entity_names: Lowercased list of known entity names

    Returns:
        True if hook is grounded to the canon, False otherwise
    """
    if not canon_entity_names:
        # No canon to ground against — accept
        return True

    # Check connected_entities field directly (exact name match allowed)
    for ce in hook.connected_entities:
        if any(ce.lower() == name.lower() for name in canon_entity_names):
            return True

    # Tokenize title and canon names; match if any canon token appears in title
    title_tokens = set(_normalize_text(hook.title).split())
    for canon_name in canon_entity_names:
        canon_tokens = [t for t in _normalize_text(canon_name).split() if t]
        if not canon_tokens:
            continue
        if any(token in title_tokens for token in canon_tokens):
            return True
    return False


def filter_ungrounded_hooks(
    hooks: list[PlotHook],
    canon_entity_names: list[str],
    min_grounded: int = 1,
) -> list[PlotHook]:
    """Filter a list of hooks to keep only those grounded to canon entities.

    If the filtered result would be smaller than min_grounded, this returns
    the original list (we never want zero hooks when canon is known).

    Args:
        hooks: Candidate hooks
        canon_entity_names: Lowercased list of canon entity names
        min_grounded: Minimum number of grounded hooks to keep

    Returns:
        Filtered list of hooks grounded to canon (or all hooks if filtering
        would drop below min_grounded)
    """
    if not canon_entity_names:
        return hooks
    grounded = [h for h in hooks if hook_is_grounded(h, canon_entity_names)]
    if len(grounded) < min_grounded:
        # Not enough grounded hooks — return originals and let downstream handle
        return hooks
    return grounded

"""
GmTableAgent — the human-GM assistant's model calls for a real table.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data.schemas (ModelRole only), monitor_agents.base
CALLED BY: UI backend routers/gm_tools.py (GM Assistant /gm page)

Phase 7 Part B. Four flows, each one typed LLM call where judgment is
needed (no keyword tables, no counters — the DE-heuristic principle):

1. **Prep to table (CF-7).** The GM's session notes are extracted into
   tonight's NPCs (name, description, what they want), locations and plot
   threads, grounded against canonical entity names fetched via MCP.
2. **At the table (CF-3/Q-2/Q-4/Q-7).** Lookups that need judgment: selecting
   what the party knows about a topic from candidate facts, answering a rules
   question with its source, and improvising a name or a complication.
3. **After the session (CF-5/CF-8).** A pasted session log is extracted into
   world-state statements that the router stages as ProposedChange items and
   checks against canon (direct + G-9 implication depth).
4. **World clock (CF-11).** ``advance_and_summarize`` moves the story's
   in-fiction time, reports the deadlines that flipped (deterministic,
   Layer 1), and — when time actually passed — drafts the "what NPCs did
   off-screen" paragraph for the next prep briefing as one typed LLM call
   over canon.

Every fetch of world data goes through ``call_tool`` (MCP). Every judgment
goes through ``call_llm_structured`` with a Pydantic response model — the
prompt is the test surface and the output is typed. Failures propagate to the
caller (the router turns them into 500s): nothing here silently degrades.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_agents.base import BaseAgent
from monitor_data.schemas.llm_config import ModelRole
from monitor_data.schemas.world_clock import (
    WorldClockAdvanceResult,
    WorldClockDeadlineView,
    WorldClockResponse,
)

# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class PrepNpcItem(BaseModel):
    """One NPC extracted from the GM's prep notes."""

    name: str = Field(description="The NPC's canonical or planned name")
    description: str = Field(default="", description="Who they are, in one or two sentences")
    want: str = Field(default="", description="What they want tonight (drive/goal)")
    existing_entity_id: str | None = Field(
        default=None,
        description="Canon entity this NPC matches, filled by name resolution after extraction",
    )


class PrepLocationItem(BaseModel):
    """One location extracted from the GM's prep notes."""

    name: str = Field(description="The location's name")
    description: str = Field(default="", description="What the place is like / what is there")
    existing_entity_id: str | None = None


class PrepThreadItem(BaseModel):
    """One plot thread extracted from the GM's prep notes."""

    title: str = Field(description="Short thread title")
    description: str = Field(default="", description="What hangs in the balance")
    urgency: str = Field(default="medium", description="low | medium | high | immediate")


class PrepExtraction(BaseModel):
    """What tonight's session needs, extracted from the GM's notes."""

    npcs: list[PrepNpcItem] = Field(default_factory=list)
    locations: list[PrepLocationItem] = Field(default_factory=list)
    threads: list[PrepThreadItem] = Field(default_factory=list)
    notes_summary: str = Field(default="", description="One-paragraph summary of the notes")


class KnownFact(BaseModel):
    """One candidate fact in a party-knowledge lookup."""

    statement: str
    index: int = Field(description="1-based position of the fact in the candidate list")


class PartyKnowledgeAnswer(BaseModel):
    """What the party knows about a topic."""

    topic: str = ""
    summary: str = Field(default="", description="Short answer to 'what do they know?'")
    facts: list[KnownFact] = Field(default_factory=list)


class RulesAnswer(BaseModel):
    """A rules question answered from the system's own rules, with source."""

    answer: str = Field(description="The ruling/answer in one or two sentences")
    source: str = Field(
        default="",
        description="The rule name (and section if given) the answer comes from",
    )
    covered: bool = Field(
        default=True,
        description="False when the system's rules do not cover the question",
    )


class NameSuggestions(BaseModel):
    """On-demand names for a table need."""

    names: list[str] = Field(default_factory=list)
    rationale: str = Field(default="", description="Why these names fit this world")


class ComplicationSuggestions(BaseModel):
    """On-demand complications/twists for a table need."""

    complications: list[str] = Field(default_factory=list)
    rationale: str = Field(default="", description="Why these complications fit now")


class SessionLogStatement(BaseModel):
    """One world-state claim extracted from a pasted session log."""

    statement: str = Field(description="A single world-state claim ('the key is now with Mira')")
    participants: list[str] = Field(default_factory=list, description="Characters involved")
    locations: list[str] = Field(default_factory=list, description="Locations involved")


class SessionLogExtraction(BaseModel):
    """World-state claims extracted from a session log."""

    statements: list[SessionLogStatement] = Field(default_factory=list)


class OffScreenSummary(BaseModel):
    """What the NPCs/world did while the clock advanced (CF-7 prep briefing)."""

    summary: str = Field(default="", description="Two or three sentences of off-screen activity")
    npc_activities: list[str] = Field(
        default_factory=list,
        description="One short off-screen activity per NPC, each grounded in the provided canon",
    )


class AdvanceOutcome(BaseModel):
    """Result of ``advance_and_summarize``: clock, deadline flips, summary."""

    clock: WorldClockResponse
    changed: bool = False
    initialized: bool = False
    crossed: list[WorldClockDeadlineView] = Field(default_factory=list)
    due: list[WorldClockDeadlineView] = Field(default_factory=list)
    offscreen: OffScreenSummary | None = None


# =============================================================================
# AGENT
# =============================================================================


def _parse_tool_result(result: Any, key: str | None = None, default: Any = None) -> Any:
    """Normalize an MCP tool result.

    Tool results arrive as parsed JSON: a list for list-returning tools
    (``neo4j_list_facts`` returns a bare array) or a dict for model-returning
    tools (``neo4j_list_entities`` returns ``{"entities": [...]}``). Handles
    both, plus raw JSON strings, and an optional lookup key for dicts.
    """
    import json

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return default
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        if key is not None:
            return result.get(key, default)
        return result
    return default


class GmTableAgent(BaseAgent):
    """Typed model calls for the GM assistant's prep, lookup and wrap-up flows.

    ``tier`` picks the model role: STANDARD for extraction/answers that feed
    canon, LIGHT for on-demand improv (names, complications) and cheap
    selection passes.
    """

    def __init__(
        self,
        agent_type: str = "GmTableAgent",
        agent_id: str | None = None,
        model: str | None = None,
        tier: ModelRole = ModelRole.STANDARD,
    ) -> None:
        super().__init__(
            agent_type=agent_type,
            agent_id=agent_id or "gm-table-agent",
            model=model,
        )
        self._tier = tier

    def _default_model_role(self) -> ModelRole:
        return self._tier

    async def run(self) -> None:
        pass  # every method is called directly by the /gm router

    # ------------------------------------------------------------------
    # Prep to table (CF-7)
    # ------------------------------------------------------------------

    async def extract_prep(
        self,
        universe_id: UUID,
        notes: str,
    ) -> PrepExtraction:
        """Extract tonight's NPCs, locations and threads from the GM's notes.

        Grounding: canonical entity names are fetched via MCP and offered to
        the model (it should prefer them), then every extracted name is
        resolved against the canon so the review step can show which items
        already exist.
        """
        names_result = await self.call_tool(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "limit": 100}},
        )
        entities = _parse_tool_result(names_result, "entities", []) or []
        known_names = [str(e.get("name") or "") for e in entities if e.get("name")]

        extraction: PrepExtraction = await self.call_llm_structured(
            PrepExtraction,
            [
                {
                    "role": "system",
                    "content": (
                        "You prepare a tabletop session from a human GM's notes. "
                        "Extract what tonight's session needs: NPCs (name, who they are, "
                        "what they want tonight), locations, and plot threads. "
                        "Only extract what the notes actually mention or clearly imply — "
                        "never invent people or places. Prefer canonical names from the "
                        "KNOWN NAMES list when the notes clearly refer to them. "
                        "Candidate facts and descriptions must be grounded in the notes."
                    ),
                },
                {
                    "role": "user",
                    "content": (f"KNOWN NAMES:\n{chr(10).join(known_names) or '(none yet)'}\n\nGM NOTES:\n{notes}"),
                },
            ],
            max_tokens=2048,
        )

        wanted = [npc.name for npc in extraction.npcs] + [loc.name for loc in extraction.locations]
        if wanted:
            resolved = await self.call_tool(
                "neo4j_get_entities_by_names",
                {"universe_id": str(universe_id), "names": wanted},
            )
            matches = _parse_tool_result(resolved, default=[]) or []
            by_name = {
                str(m.get("name") or "").strip().lower(): str(m.get("id") or "") for m in matches if m.get("name")
            }
            for npc in extraction.npcs:
                npc.existing_entity_id = by_name.get(npc.name.strip().lower()) or None
            for loc in extraction.locations:
                loc.existing_entity_id = by_name.get(loc.name.strip().lower()) or None

        return extraction

    # ------------------------------------------------------------------
    # At the table (CF-3 / Q-2 / Q-4 / Q-7)
    # ------------------------------------------------------------------

    async def party_knowledge(
        self,
        universe_id: UUID,
        character_ids: list[UUID],
        topic: str | None = None,
    ) -> PartyKnowledgeAnswer:
        """What the party knows about a topic (or in general).

        Candidates are canon facts fetched via MCP; the party's knowledge is
        every fact they witnessed plus common knowledge (facts with no
        witnesses). When a topic is given, one LIGHT call selects the relevant
        facts and answers in one short summary.
        """
        character_keys = {str(cid) for cid in character_ids}

        facts: list[dict[str, Any]] = []
        topic_entity_id: str | None = None
        if topic and topic.strip():
            resolved = await self.call_tool(
                "neo4j_get_entities_by_names",
                {"universe_id": str(universe_id), "names": [topic.strip()]},
            )
            matches = _parse_tool_result(resolved, default=[]) or []
            if matches:
                topic_entity_id = str(matches[0].get("id") or "") or None

        filters: dict[str, Any] = {"universe_id": str(universe_id), "limit": 100}
        if topic_entity_id:
            filters = {"universe_id": str(universe_id), "entity_id": topic_entity_id, "limit": 50}
        facts_result = await self.call_tool("neo4j_list_facts", {"filters": filters})
        raw_facts = _parse_tool_result(facts_result, "facts", []) or []
        facts = [f for f in raw_facts if isinstance(f, dict)]

        def _is_known(fact: dict[str, Any]) -> bool:
            from monitor_agents.cast import fact_visible_to

            if character_keys:
                return any(fact_visible_to(fact, character_id) for character_id in character_keys)
            witnesses = [str(w) for w in (fact.get("witnesses") or [])]
            return not witnesses

        known = [f for f in facts if _is_known(f)]
        statements = [str(f.get("statement") or "") for f in known if f.get("statement")]

        if not topic or not topic.strip() or not statements:
            return PartyKnowledgeAnswer(
                topic=topic or "",
                summary="",
                facts=[KnownFact(statement=s, index=i + 1) for i, s in enumerate(statements)],
            )

        selection = await self.call_llm_structured(
            PartyKnowledgeAnswer,
            [
                {
                    "role": "system",
                    "content": (
                        "A GM asks what their party knows about a topic. Select the "
                        "candidate facts the party would know and care about for that "
                        "topic, and answer the question in one short summary. "
                        "In the 'facts' output, list each selected fact with its "
                        "1-based index from the candidate list and its statement "
                        "verbatim. Select only from the candidates — never invent facts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"TOPIC: {topic}\n\nCANDIDATE FACTS (numbered):\n"
                        + chr(10).join(f"{i + 1}. {s}" for i, s in enumerate(statements))
                    ),
                },
            ],
            max_tokens=1024,
        )

        # Re-ground the answer on the candidate list: indexes map back to the
        # real statements, so prose can never smuggle in a non-candidate fact.
        grounded: list[KnownFact] = []
        for item in selection.facts:
            idx = item.index
            if 1 <= idx <= len(statements):
                grounded.append(KnownFact(statement=statements[idx - 1], index=idx))
        return PartyKnowledgeAnswer(
            topic=topic.strip(),
            summary=selection.summary,
            facts=grounded,
        )

    async def answer_rules(self, system_id: UUID, question: str) -> RulesAnswer:
        """Answer a rules question from the system's own rules, with its source."""
        system_result = await self.call_tool(
            "mongodb_get_game_system",
            {"system_id": str(system_id)},
        )
        system = _parse_tool_result(system_result, default=None)
        if not isinstance(system, dict):
            return RulesAnswer(
                answer="That game system could not be loaded.",
                source="",
                covered=False,
            )

        lines: list[str] = []
        core = system.get("core_mechanic") or {}
        if isinstance(core, dict):
            if core.get("formula"):
                lines.append(f"Core mechanic: {core['formula']}")
            if core.get("description"):
                lines.append(str(core["description"]))
        for rule in system.get("rules") or []:
            if not isinstance(rule, dict):
                continue
            name = str(rule.get("name") or "rule")
            bits = [str(rule.get("description") or "").strip()]
            if rule.get("formula"):
                bits.append(f"formula: {rule['formula']}")
            if rule.get("rule_type"):
                bits.append(f"type: {rule['rule_type']}")
            lines.append(f"- {name}: {' '.join(b for b in bits if b)}")
        for attr in system.get("attributes") or []:
            if isinstance(attr, dict) and attr.get("name"):
                lines.append(
                    f"- attribute {attr['name']}"
                    f" ({attr.get('abbreviation') or attr['name']}):"
                    f" {attr.get('description') or ''}"
                )

        rules_answer: RulesAnswer = await self.call_llm_structured(
            RulesAnswer,
            [
                {
                    "role": "system",
                    "content": (
                        "You answer tabletop rules questions strictly from the RULES "
                        "TEXT provided. Cite the rule name your answer comes from in "
                        "'source'. If the rules text does not cover the question, set "
                        "'covered' to false and say so in one sentence — never guess "
                        "at rules that are not in the text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"RULES TEXT for {system.get('name', 'this system')}:\n"
                        f"{chr(10).join(lines) or '(no rules text)'}\n\n"
                        f"QUESTION: {question}"
                    ),
                },
            ],
            max_tokens=1024,
        )
        return rules_answer

    async def suggest_names(
        self,
        universe_id: UUID,
        context: str,
        count: int = 3,
    ) -> NameSuggestions:
        """On-demand names that fit this world's existing naming."""
        names_result = await self.call_tool(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "limit": 50}},
        )
        entities = _parse_tool_result(names_result, "entities", []) or []
        existing = [str(e.get("name") or "") for e in entities if e.get("name")]

        names: NameSuggestions = await self.call_llm_structured(
            NameSuggestions,
            [
                {
                    "role": "system",
                    "content": (
                        "A GM needs a name at the table, right now. Suggest names that "
                        "fit the world's naming style without reusing EXISTING NAMES. "
                        "Return exactly the number asked for."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"EXISTING NAMES (style guide):\n{chr(10).join(existing) or '(none)'}\n\n"
                        f"CONTEXT: {context or 'a person in this world'}\n\n"
                        f"Suggest {count} names."
                    ),
                },
            ],
            max_tokens=512,
        )
        return names

    async def suggest_complications(
        self,
        universe_id: UUID,
        context: str,
        count: int = 3,
        story_id: UUID | None = None,
    ) -> ComplicationSuggestions:
        """On-demand complications that press on the story's open threads."""
        thread_args: dict[str, Any] = {"params": {"status": "active"}}
        if story_id is not None:
            thread_args = {"params": {"status": "active", "story_id": str(story_id)}}
        threads_result = await self.call_tool("neo4j_list_plot_threads", thread_args)
        threads = _parse_tool_result(threads_result, "threads", []) or []
        open_threads = [
            f"- {t.get('title', 'Untitled')}: {t.get('gm_notes') or t.get('description') or ''}"
            for t in threads[:10]
            if isinstance(t, dict)
        ]

        complications: ComplicationSuggestions = await self.call_llm_structured(
            ComplicationSuggestions,
            [
                {
                    "role": "system",
                    "content": (
                        "A GM is stuck at the table and needs a complication. Suggest "
                        "complications that make the current moment harder or more "
                        "interesting, ideally pressing on an OPEN THREAD. Each "
                        "complication is one sentence, actionable right now. "
                        "Return exactly the number asked for."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"OPEN THREADS:\n{chr(10).join(open_threads) or '(none)'}\n\n"
                        f"CONTEXT: {context or 'the current scene'}\n\n"
                        f"Suggest {count} complications."
                    ),
                },
            ],
            max_tokens=512,
        )
        return complications

    # ------------------------------------------------------------------
    # After the session (CF-5 / CF-8)
    # ------------------------------------------------------------------

    async def extract_session_log(
        self,
        universe_id: UUID,
        log_text: str,
    ) -> SessionLogExtraction:
        """Extract world-state statements from a pasted session log.

        Each statement becomes one pending ProposedChange (staged by the
        router for the CF-8 queue), so the extraction must contain only real
        world-state changes — no dialogue, no trivia, no speculation.
        """
        names_result = await self.call_tool(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "limit": 100}},
        )
        entities = _parse_tool_result(names_result, "entities", []) or []
        known_names = [str(e.get("name") or "") for e in entities if e.get("name")]

        session_log: SessionLogExtraction = await self.call_llm_structured(
            SessionLogExtraction,
            [
                {
                    "role": "system",
                    "content": (
                        "A human GM pastes what happened at their table. Extract every "
                        "world-state change the session established: one claim per "
                        "statement ('the key is now with Mira', 'the docks burned', "
                        "'the baron is dead'). Only extract changes the log actually "
                        "establishes — no dialogue, no speculation, no trivia. "
                        "Prefer canonical names from the KNOWN NAMES list."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"KNOWN NAMES:\n{chr(10).join(known_names) or '(none yet)'}\n\nSESSION LOG:\n{log_text}"
                    ),
                },
            ],
            max_tokens=2048,
        )
        return session_log

    # ------------------------------------------------------------------
    # World clock (CF-11)
    # ------------------------------------------------------------------

    async def advance_and_summarize(
        self,
        universe_id: UUID,
        story_id: UUID,
        delta: str | None = None,
        target_time: datetime | None = None,
    ) -> AdvanceOutcome:
        """Advance the story's world clock and draft the off-screen tick (CF-11).

        The clock move and the deadline flip are deterministic: Layer 1
        enforces monotonicity and computes due/overdue statuses, and this
        method only narrows them to the current ``due`` set and the deadlines
        this move crossed. Only the "what the NPCs did while time passed"
        paragraph goes through the LLM, a generation over canon (facts and
        names fetched via MCP) — not a simulation. The caller persists the
        summary onto the clock for the next CF-7 prep briefing.
        """
        key = {"universe_id": str(universe_id), "story_id": str(story_id)}

        advance_raw = await self.call_tool(
            "mongodb_advance_world_clock",
            {
                **key,
                "delta": delta,
                "target_time": target_time.isoformat() if target_time is not None else None,
            },
        )
        parsed = _parse_tool_result(advance_raw, default=None)
        if not isinstance(parsed, dict):
            # Tool errors come back as raw text ("Error executing tool: …");
            # surface them as ValueError so the router maps them to 422s.
            raise ValueError(str(advance_raw))
        advance = WorldClockAdvanceResult.model_validate(parsed)
        clock = advance.clock
        due = [d for d in clock.deadlines if d.status in ("due", "overdue")]

        if not advance.changed or advance.initialized:
            return AdvanceOutcome(
                clock=clock,
                changed=advance.changed,
                initialized=advance.initialized,
                crossed=advance.crossed,
                due=due,
            )

        # Time actually passed — ground the off-screen generation in canon.
        names_result = await self.call_tool(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "limit": 100}},
        )
        entities = _parse_tool_result(names_result, "entities", []) or []
        known_names = [str(e.get("name") or "") for e in entities if isinstance(e, dict) and e.get("name")]

        facts_result = await self.call_tool(
            "neo4j_list_facts",
            {"filters": {"universe_id": str(universe_id), "limit": 30}},
        )
        raw_facts = _parse_tool_result(facts_result, "facts", []) or []
        statements = [str(f.get("statement") or "") for f in raw_facts if isinstance(f, dict) and f.get("statement")]

        last = clock.advances[0] if clock.advances else None
        elapsed = last.delta if last else "unknown"

        if not known_names and not statements and not advance.crossed:
            # Nothing to ground on — deterministic fallback, no LLM call.
            return AdvanceOutcome(
                clock=clock,
                changed=True,
                crossed=advance.crossed,
                due=due,
                offscreen=OffScreenSummary(
                    summary=f"Time passed ({elapsed}); the world now reads {clock.display}.",
                    npc_activities=[],
                ),
            )

        crossed_lines = (
            "\n".join(f"- {d.title} (due {d.due_at.date().isoformat()}) — {d.status}" for d in advance.crossed)
            or "(none crossed by this advance)"
        )
        due_lines = "\n".join(f"- {d.title} (due {d.due_at.date().isoformat()}) — {d.status}" for d in due) or "(none)"

        offscreen: OffScreenSummary = await self.call_llm_structured(
            OffScreenSummary,
            [
                {
                    "role": "system",
                    "content": (
                        "A human GM advanced the story's world clock between sessions. "
                        "Write the off-screen tick for the next prep briefing: two or "
                        "three sentences about what the NPCs and the world did while "
                        "that time passed. This is a generation over the CANON provided "
                        "— not a simulation: never invent people, places, or permanent "
                        "world changes. Crossed deadlines are established facts; fold "
                        "them in. In 'npc_activities', list one short activity per NPC "
                        "that plausibly follows from the canon facts; leave it empty "
                        "when nothing can be grounded."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"TIME ADVANCED BY: {elapsed}\n"
                        f"WORLD TIME NOW: {clock.display}\n"
                        f"NEWLY CROSSED DEADLINES:\n{crossed_lines}\n\n"
                        f"DUE / OVERDUE DEADLINES:\n{due_lines}\n\n"
                        f"KNOWN NAMES:\n{chr(10).join(known_names) or '(none yet)'}\n\n"
                        f"RECENT CANON FACTS:\n"
                        f"{chr(10).join(f'{i + 1}. {s}' for i, s in enumerate(statements)) or '(none yet)'}"
                    ),
                },
            ],
            max_tokens=1024,
        )
        return AdvanceOutcome(
            clock=clock,
            changed=True,
            crossed=advance.crossed,
            due=due,
            offscreen=offscreen,
        )


# LIGHT-tier instance factory for on-demand improv (names, complications).
def light_table_agent() -> GmTableAgent:
    """A LIGHT-tier GmTableAgent for on-demand improv (names, complications)."""
    return GmTableAgent(
        agent_type="GmTableLightAgent",
        agent_id="gm-table-light",
        tier=ModelRole.LIGHT,
    )

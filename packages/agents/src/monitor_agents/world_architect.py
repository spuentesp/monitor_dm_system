"""
World Architect Agent — conversational world-building partner.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts

Responsibilities:
- Guide users through collaborative world creation via conversation
- Extract entities, axioms, and lore facts from user descriptions
- Build structured proposals from extracted elements
- Delegate canonization to CanonKeeper
- Track what's been defined and suggest what to define next

The World Architect does NOT write to Neo4j directly.  It produces
proposals that CanonKeeper auto-accepts (since the user is deliberately
defining their world).

Pipeline per turn:
  1. Load current world state from Neo4j (entities, axioms, facts)
  2. WorldArchitectModule (DSPy) → response + extracted proposals
  3. CanonKeeper auto-commits proposals to Neo4j
  4. Return response to user
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from monitor_agents.base import BaseAgent
from monitor_agents.prompts.world_architect import (
    WorldArchitectModule,
    WorldGapAnalysisModule,
)
from monitor_agents.utils.world_profile_support import (
    build_priority_gaps,
    build_world_profile,
    render_world_profile_context,
)

logger = logging.getLogger(__name__)


class WorldArchitect(BaseAgent):
    """
    Conversational world-building agent.

    Stateless — all world state lives in Neo4j; conversation state in MongoDB.
    """

    def __init__(self, agent_id: str = "world-architect-1") -> None:
        super().__init__(agent_type="WorldArchitect", agent_id=agent_id)
        self._architect_module = WorldArchitectModule()
        self._gap_module = WorldGapAnalysisModule()
        self.multiverse_id: Optional[UUID] = None

    async def run(self) -> None:
        pass  # driven by WorldBuildingLoop

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    async def process_turn(
        self,
        user_message: str,
        universe_id: Optional[UUID],
        conversation_history: List[Dict[str, Any]],
        multiverse_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Process one world-building turn.

        Args:
            user_message: The user's latest input.
            universe_id:  Target universe (may be None for first turn).
            conversation_history: Prior messages [{role, content}, ...].
            multiverse_id: Target multiverse ID.

        Returns:
            Dict with keys:
              - response: str — the architect's conversational reply
              - proposals: list — structured proposals extracted
              - committed: int — how many proposals were committed to Neo4j
              - errors: list — any commit errors
              - newly_created: dict — IDs of new containers (multiverse_id, universe_id)
        """
        self.multiverse_id = multiverse_id
        # 1. Load current world state and derive a deterministic world profile
        world_summary = await self._load_world_state(universe_id)
        prior_profile = None
        if universe_id:
            try:
                from monitor_data.tools.mongodb_tools import mongodb_get_world_profile

                prior_profile = mongodb_get_world_profile(universe_id)
            except Exception:  # noqa: BLE001
                pass
        world_profile = build_world_profile(
            world_summary,
            user_message=user_message,
            conversation_history=conversation_history,
            prior_profile=prior_profile,
        )
        if universe_id:
            try:
                from monitor_data.tools.mongodb_tools import mongodb_upsert_world_profile

                mongodb_upsert_world_profile(universe_id, world_profile)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Could not persist world profile: %s", exc)
        world_profile_context = render_world_profile_context(world_profile)
        coverage_summary = world_profile.coverage_summary
        known_open_questions = world_profile.known_open_questions
        priority_gaps = build_priority_gaps(world_summary, world_profile)

        # 2. Format conversation history for the prompt
        history_text = self._format_history(conversation_history)

        # 3. Run DSPy module
        import anyio
        import dspy

        def _run_architect_sync() -> dspy.Prediction:
            return self._architect_module(
                user_message=user_message,
                conversation_history=history_text,
                world_state_summary=json.dumps(world_summary, default=str),
                world_profile_context=world_profile_context,
                coverage_summary=coverage_summary,
                known_open_questions=json.dumps(known_open_questions[:6], default=str),
            )

        result = await anyio.to_thread.run_sync(_run_architect_sync)

        response_text = result.response
        proposals = self._parse_proposals(result.extracted_proposals, universe_id)

        # Determinism guard (T-096): if the user explicitly asked to create an
        # entity but the LLM extraction produced none, synthesize it directly so
        # the create reliably commits instead of silently no-op'ing.
        if not any(p.get("change_type") == "entity" for p in proposals):
            fallback = self._fallback_entity_proposal(user_message, universe_id)
            if fallback:
                proposals.append(fallback)

        # 4. Auto-commit proposals via CanonKeeper
        committed = 0
        errors: List[str] = []
        newly_created: Dict[str, UUID] = {}

        # We always attempt to commit, even if universe_id is None (for Multiverse/Universe creation)
        committed, errors, newly_created = await self._commit_proposals(proposals, universe_id)

        return {
            "response": response_text,
            "proposals": proposals,
            "committed": committed,
            "errors": errors,
            "newly_created": newly_created,
            "world_profile": world_profile.model_dump(mode="json"),
            "coverage_summary": coverage_summary,
            "known_open_questions": known_open_questions,
            "priority_gaps": priority_gaps,
        }

    async def suggest_next(self, universe_id: Optional[UUID]) -> str:
        """
        Analyze gaps in the world and return a suggestion message.

        Used when the user asks "what should I define next?" or on session start.
        """
        world_summary = await self._load_world_state(universe_id)
        world_profile = build_world_profile(world_summary)

        import anyio
        import dspy

        def _run_gap_sync() -> dspy.Prediction:
            return self._gap_module(
                world_state_summary=json.dumps(world_summary, default=str),
                world_profile_context=render_world_profile_context(world_profile),
                coverage_summary=world_profile.coverage_summary,
                known_open_questions=json.dumps(
                    world_profile.known_open_questions[:6], default=str
                ),
            )

        result = await anyio.to_thread.run_sync(_run_gap_sync)

        fallback_gaps = build_priority_gaps(world_summary, world_profile)
        try:
            gaps = json.loads(result.gaps)
        except (json.JSONDecodeError, TypeError):
            gaps = fallback_gaps

        if not gaps:
            gaps = fallback_gaps
        if not gaps:
            return "Your world is shaping up nicely! What else would you like to add?"

        lines = ["Here are some areas you might want to flesh out:\n"]
        for gap in gaps[:5]:
            area = gap.get("area", "")
            suggestion = gap.get("suggestion", "")
            example = gap.get("example_prompt", "")
            lines.append(f"- **{area}**: {suggestion}")
            if example:
                lines.append(f'  _Try: "{example}"_')
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # P-19: Procedural Scene Population
    # ------------------------------------------------------------------

    async def seed_universe(
        self,
        universe_id: UUID,
        num_entities: int = 10,
        location_count: int = 3,
        npc_count: int = 5,
    ) -> Dict[str, Any]:
        """
        Seed a universe with procedurally generated entities from random tables.

        Args:
            universe_id:    Target universe to seed.
            num_entities:   Total number of entities to generate.
            location_count: Number of locations to generate.
            npc_count:      Number of NPCs to generate.

        Returns:
            Dict with:
              - generated: int — total entities created
              - entities: list — created entity summaries
              - errors: list — any failures
        """
        from monitor_data.tools.mongodb_tools.random_tables import (
            mongodb_list_random_tables,
            mongodb_roll_on_table,
        )
        from monitor_data.schemas.random_tables import RandomTableFilter, RandomTableType
        from monitor_data.tools.neo4j_tools.entities import neo4j_create_entity
        from monitor_data.schemas.entities import EntityCreate
        from monitor_data.schemas.base import EntityType, Authority, CanonLevel

        errors: List[str] = []
        created: List[Dict[str, Any]] = []

        # 1. Fetch random tables for this universe
        filter_params = RandomTableFilter(universe_id=universe_id, limit=50)
        try:
            table_list = mongodb_list_random_tables(filter_params)
        except Exception as exc:
            logger.warning("Could not list random tables: %s", exc)
            table_list = None

        tables = table_list.tables if table_list else []

        # 2. Classify tables by type
        npc_tables = [t for t in tables if t.table_type == RandomTableType.NPC]
        location_tables = [t for t in tables if t.table_type == RandomTableType.LOCATION]
        feature_tables = [t for t in tables if t.table_type == RandomTableType.FEATURE]
        name_tables = [t for t in tables if t.table_type == RandomTableType.NAME]

        def _roll_table(table_list: list, default: str = "Unknown") -> Dict[str, Any]:
            """Roll on first available table, returning name and description."""
            for tbl in table_list:
                try:
                    result = mongodb_roll_on_table(UUID(tbl.table_id))
                    return {
                        "name": result.get("value", default),
                        "description": f"Generated from {tbl.name}: {result.get('value', default)}",
                        "source_table": tbl.name,
                    }
                except Exception:
                    continue
            return {"name": default, "description": f"Procedurally generated {default}"}

        # 3. Generate locations
        location_entities = []
        for i in range(location_count):
            loc = _roll_table(location_tables + feature_tables, f"Generated Location {i + 1}")
            location_entities.append(
                {
                    "name": loc["name"],
                    "entity_type": EntityType.LOCATION,
                    "description": loc["description"],
                    "properties": {
                        "source": "procedural_seed",
                        "source_table": loc.get("source_table"),
                    },
                }
            )

        # 4. Generate NPCs
        npc_entities = []
        for i in range(npc_count):
            name = _roll_table(name_tables, f"Generated NPC {i + 1}")["name"]
            npc = _roll_table(npc_tables, "wanderer")
            npc_entities.append(
                {
                    "name": name,
                    "entity_type": EntityType.CHARACTER,
                    "description": npc["description"],
                    "properties": {
                        "source": "procedural_seed",
                        "source_table": npc.get("source_table"),
                    },
                }
            )

        # 5. Create entities via Neo4j tool
        all_entities = location_entities + npc_entities
        for ent in all_entities:
            try:
                params = EntityCreate(
                    universe_id=universe_id,
                    name=ent["name"],
                    entity_type=ent["entity_type"],
                    is_archetype=False,
                    description=ent.get("description", ""),
                    properties=ent.get("properties", {}),
                    authority=Authority.SYSTEM,
                    canon_level=CanonLevel.CANON,
                    confidence=0.8,
                )
                result = neo4j_create_entity(params)
                created.append(
                    {
                        "id": str(result.id),
                        "name": result.name,
                        "entity_type": result.entity_type.value,
                    }
                )
            except Exception as exc:
                errors.append(f"Failed to create {ent['name']}: {exc}")

        return {
            "generated": len(created),
            "entities": created,
            "errors": errors,
            "target_universe": str(universe_id),
        }

    async def populate_scene_procedurally(
        self,
        universe_id: UUID,
        scene_id: UUID,
        location_type: str = "generic",
    ) -> List[Dict[str, Any]]:
        """
        Procedurally generate content for a scene based on location type.
        Uses Random Tables (DL-21) to seed entities.
        """
        from monitor_data.tools.mongodb_tools import (
            mongodb_list_random_tables,
            mongodb_roll_on_table,
        )
        from monitor_data.schemas.random_tables import RandomTableFilter, RandomTableType

        proposals = []

        # 1. Identify relevant tables for the location
        # For MVP, we search for tables matching the location_type in their name
        # or generic tables of type 'encounter' or 'feature'.
        filters = RandomTableFilter(universe_id=universe_id, limit=20)
        table_list = mongodb_list_random_tables(filters)

        relevant_tables = []
        for table in table_list.tables:
            name_low = table.name.lower()
            if location_type.lower() in name_low or "generic" in name_low:
                relevant_tables.append(table)

        if not relevant_tables:
            # Fallback to any encounter/feature tables
            relevant_tables = [
                t
                for t in table_list.tables
                if t.table_type in (RandomTableType.ENCOUNTER, RandomTableType.FEATURE)
            ]

        # 2. Roll on a few tables to generate "Seeds"
        seeds = []
        # Roll on up to 3 relevant tables
        for table in relevant_tables[:3]:
            try:
                roll_res = mongodb_roll_on_table(UUID(table.table_id))
                seeds.append(roll_res)
            except Exception as exc:
                logger.warning("Failed to roll on table %s: %s", table.table_id, exc)

        # 3. Convert seeds to Entity Proposals
        for seed in seeds:
            # Simple conversion: the 'value' from the table becomes an entity
            proposal_id = str(uuid4())
            val = seed.get("value", "Unknown Entity")

            # Heuristic: if it sounds like an NPC (contains names or titles),
            # make it an NPC, otherwise a Feature/Item.
            entity_type = "feature"
            if any(
                kw in val.lower()
                for kw in ["guard", "orc", "goblin", "merchant", "beast", "spirit"]
            ):
                entity_type = "npc"

            proposals.append(
                {
                    "proposal_id": proposal_id,
                    "proposal_type": "entity",
                    "change_type": "entity",
                    "universe_id": str(universe_id),
                    "summary": f"Procedural seed: {val}",
                    "content": {"source_table": seed.get("table_name")},
                    "payload": {
                        "name": val,
                        "entity_type": entity_type,
                        "description": f"Procedurally generated via {seed.get('table_name')}",
                        "properties": {
                            "origin": "procedural_generation",
                            "scene_id": str(scene_id),
                        },
                        "confidence": 0.8,
                    },
                    "source": "world_architect_procedural",
                    "status": "pending",
                }
            )

        # 4. Auto-commit these proposals
        if proposals:
            await self._commit_proposals(proposals, universe_id)

        return proposals

    # ------------------------------------------------------------------
    # World state loading
    # ------------------------------------------------------------------

    async def _load_world_state(self, universe_id: Optional[UUID]) -> Dict[str, Any]:
        """Load a summary of the current universe and its library from Neo4j/MongoDB."""
        if not universe_id:
            return {}

        import anyio

        summary: Dict[str, Any] = {
            "entities": [],
            "axioms": [],
            "facts": [],
            "library_sources": [],
            "entity_count": 0,
            "axiom_count": 0,
            "fact_count": 0,
        }

        try:
            from monitor_data.tools.neo4j_tools import (
                neo4j_list_axioms,
                neo4j_list_entities,
                neo4j_list_facts,
            )
            from monitor_data.tools.neo4j_tools.core import neo4j_get_universe
            from monitor_data.schemas.entities import EntityFilter
            from monitor_data.schemas.facts import AxiomFilter, FactFilter
            from monitor_agents.utils.world_library import WorldLibrary

            # 1. Entities
            entity_result = await anyio.to_thread.run_sync(
                lambda: neo4j_list_entities(EntityFilter(universe_id=universe_id, limit=50))
            )
            entities = entity_result.entities if entity_result else []
            summary["entity_count"] = len(entities)
            summary["entities"] = [
                {
                    "name": e.name,
                    "type": e.entity_type,
                    "description": (e.description or "")[:100],
                }
                for e in entities[:20]
            ]

            # 2. Axioms
            axioms = await anyio.to_thread.run_sync(
                lambda: neo4j_list_axioms(AxiomFilter(universe_id=universe_id))
            )
            summary["axiom_count"] = len(axioms)
            summary["axioms"] = [
                {"statement": a.statement, "domain": a.domain} for a in axioms[:15]
            ]

            # 3. Facts
            facts = await anyio.to_thread.run_sync(
                lambda: neo4j_list_facts(FactFilter(universe_id=universe_id))
            )
            summary["fact_count"] = len(facts)
            summary["facts"] = [{"statement": f.statement, "type": f.fact_type} for f in facts[:15]]

            # 4. Library Sources (Files and URLs)
            universe = neo4j_get_universe(universe_id)
            if universe:
                library = WorldLibrary()
                sources = await library.list_by_system(universe.system_name or "generic")
                summary["library_sources"] = [
                    {
                        "type": s["source_type"],
                        "uri": s["uri"],
                        "title": s.get("metadata", {}).get("title"),
                    }
                    for s in sources[:10]
                ]

        except Exception as exc:  # noqa: BLE001
            logger.debug("_load_world_state failed: %s", exc)

        return summary

    # ------------------------------------------------------------------
    # Proposal parsing and commitment
    # ------------------------------------------------------------------

    # Explicit-create intent: "create/add/make/spawn/introduce ... [a] NPC/...".
    _CREATE_INTENT = re.compile(r"\b(create|add|make|spawn|introduce|commit)\b", re.IGNORECASE)
    _ENTITY_KIND = re.compile(
        r"\b(npc|character|person|faction|guild|group|cult|order|location|place|"
        r"city|town|village|item|object|artifact|entity)\b",
        re.IGNORECASE,
    )
    _KIND_TO_TYPE = {
        "npc": "character",
        "character": "character",
        "person": "character",
        "faction": "faction",
        "guild": "faction",
        "group": "faction",
        "cult": "faction",
        "order": "faction",
        "location": "location",
        "place": "location",
        "city": "location",
        "town": "location",
        "village": "location",
        "item": "object",
        "object": "object",
        "artifact": "object",
        "entity": "concept",
    }
    # Capture a proper-noun name after "named/called X" or "<kind>: X" / "<kind> X".
    _NAME_PATTERNS = [
        re.compile(r"\b(?:named|called)\s+([A-Z][\w''\-]+(?:\s+[A-Z][\w''\-]+){0,3})"),
        re.compile(
            r"\b(?:npc|character|person|faction|location|place|item|entity)\b"
            r"\s*[:\-]?\s+([A-Z][\w''\-]+(?:\s+[A-Z][\w''\-]+){0,3})",
            re.IGNORECASE,
        ),
    ]

    def _fallback_entity_proposal(
        self,
        user_message: str,
        universe_id: Optional[UUID],
    ) -> Optional[Dict[str, Any]]:
        """Synthesize an entity proposal for an explicit create request.

        The DSPy extraction occasionally returns no structured proposals even
        when the user clearly said "create an NPC named X" (T-096). When the
        intent is explicit and a name is recoverable, build the proposal
        directly so the create reliably commits.
        """
        if not user_message or not universe_id:
            return None
        if not self._CREATE_INTENT.search(user_message):
            return None
        kind_match = self._ENTITY_KIND.search(user_message)
        if not kind_match:
            return None

        name = ""
        for pat in self._NAME_PATTERNS:
            m = pat.search(user_message)
            if m:
                name = m.group(1).strip(" .,:;\"'")
                break
        if not name or len(name) < 2:
            return None

        kind = kind_match.group(1).lower()
        entity_type = self._KIND_TO_TYPE.get(kind, "character")

        # Description: prose after the name (often ", a haunted gravekeeper…").
        description = ""
        idx = user_message.find(name)
        if idx != -1:
            tail = user_message[idx + len(name) :].lstrip(" ,:-—").strip()
            description = tail[:400]

        logger.info(
            "world_architect: deterministic fallback entity proposal '%s' (%s)",
            name,
            entity_type,
        )
        return {
            "proposal_id": str(uuid4()),
            "proposal_type": "entity",
            "change_type": "entity",
            "universe_id": str(universe_id),
            "summary": f"Create entity: {name}",
            "content": {"name": name, "entity_type": entity_type, "description": description},
            "payload": {
                "name": name,
                "entity_type": entity_type,
                "description": description,
                "properties": {},
                "confidence": 0.85,
            },
            "source": "world_architect_fallback",
            "status": "pending",
        }

    def _parse_proposals(
        self,
        raw_proposals: str,
        universe_id: Optional[UUID],
    ) -> List[Dict[str, Any]]:
        """Parse the DSPy extracted_proposals JSON into proposal dicts."""
        try:
            items = json.loads(raw_proposals)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(items, list):
            return []

        proposals: List[Dict[str, Any]] = []
        uid = str(universe_id) if universe_id else ""

        for item in items:
            item_type = item.get("type", "").lower()
            proposal_id = str(uuid4())

            if item_type == "multiverse":
                proposals.append(
                    {
                        "proposal_id": proposal_id,
                        "proposal_type": "multiverse",
                        "change_type": "multiverse",
                        "summary": f"Create world: {item.get('name', 'unnamed')}",
                        "content": item,
                        "payload": {
                            "name": item.get("name", ""),
                            "system_name": item.get("system_name", "generic"),
                            "description": item.get("description", ""),
                        },
                        "source": "world_architect",
                        "status": "pending",
                    }
                )
            elif item_type == "universe":
                proposals.append(
                    {
                        "proposal_id": proposal_id,
                        "proposal_type": "universe",
                        "change_type": "universe",
                        "summary": f"Create instance: {item.get('name', 'unnamed')}",
                        "content": item,
                        "payload": {
                            "name": item.get("name", ""),
                            "description": item.get("description", ""),
                            "genre": item.get("genre"),
                            "tone": item.get("tone"),
                        },
                        "source": "world_architect",
                        "status": "pending",
                    }
                )
            elif item_type == "web_fetch":
                proposals.append(
                    {
                        "proposal_id": proposal_id,
                        "proposal_type": "web_fetch",
                        "change_type": "web_fetch",
                        "summary": f"Fetch data from URL: {item.get('url', 'unknown')}",
                        "content": item,
                        "payload": {
                            "url": item.get("url", ""),
                            "reason": item.get("reason", ""),
                        },
                        "source": "world_architect",
                        "status": "pending",
                    }
                )
            elif item_type == "entity":
                proposals.append(
                    {
                        "proposal_id": proposal_id,
                        "proposal_type": "entity",
                        "change_type": "entity",
                        "universe_id": uid,
                        "summary": f"Create entity: {item.get('name', 'unnamed')}",
                        "content": item,
                        "payload": {
                            "name": item.get("name", ""),
                            "entity_type": item.get("entity_type", "concept"),
                            "description": item.get("description", ""),
                            "properties": item.get("properties", {}),
                            "confidence": 0.9,
                        },
                        "source": "world_architect",
                        "status": "pending",
                    }
                )
            elif item_type == "axiom":
                proposals.append(
                    {
                        "proposal_id": proposal_id,
                        "proposal_type": "axiom",
                        "change_type": "axiom",
                        "universe_id": uid,
                        "summary": f"Create axiom: {item.get('statement', '')[:60]}",
                        "content": item,
                        "payload": {
                            "statement": item.get("statement", ""),
                            "domain": item.get("domain", "general"),
                            "confidence": 0.9,
                        },
                        "source": "world_architect",
                        "status": "pending",
                    }
                )
            elif item_type == "lore_fact":
                proposals.append(
                    {
                        "proposal_id": proposal_id,
                        "proposal_type": "fact",
                        "change_type": "fact",
                        "universe_id": uid,
                        "summary": f"Create fact: {item.get('statement', '')[:60]}",
                        "content": item,
                        "payload": {
                            "statement": item.get("statement", ""),
                            "fact_type": item.get("fact_type", "state"),
                            "entity_names": item.get("entity_names", []),
                            "confidence": 0.9,
                        },
                        "source": "world_architect",
                        "status": "pending",
                    }
                )

        return proposals

    async def _commit_proposals(
        self,
        proposals: List[Dict[str, Any]],
        universe_id: Optional[UUID],
    ) -> tuple[int, List[str], Dict[str, UUID]]:
        """
        Auto-commit proposals via CanonKeeper.

        In World Architect mode, proposals are accepted immediately since
        the user is deliberately defining their world.
        """
        from monitor_agents.canonkeeper import CanonKeeper
        from monitor_data.schemas.agent_responses import (
            CanonKeeperDecision,
            CanonKeeperVerdict,
        )

        keeper = CanonKeeper()
        committed = 0
        errors: List[str] = []
        newly_created: Dict[str, UUID] = {}

        # Partition proposals: containers must be created before children
        container_types = {"multiverse", "universe"}
        containers = [p for p in proposals if p.get("change_type") in container_types]
        children = [p for p in proposals if p.get("change_type") not in container_types]

        for proposal in containers + children:
            p_type = proposal.get("change_type")

            if p_type == "multiverse":
                try:
                    res = await keeper.create_multiverse(proposal.get("payload", {}))
                    if res and "id" in res:
                        newly_created["multiverse_id"] = UUID(res["id"])
                    committed += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"multiverse: {exc}")
                continue

            if p_type == "universe":
                try:
                    # If we just created a multiverse, we might need its ID.
                    # For now assume the user is creating one in the current/default multiverse.
                    payload = dict(proposal.get("payload", {}))
                    if not payload.get("multiverse_id"):
                        # Use newly created multiverse if available
                        if "multiverse_id" in newly_created:
                            payload["multiverse_id"] = str(newly_created["multiverse_id"])
                        else:
                            m_list = await keeper.list_multiverses()
                            if m_list:
                                payload["multiverse_id"] = str(m_list[0]["id"])
                            else:
                                # Create a default multiverse first?
                                m_res = await keeper.create_multiverse(
                                    {
                                        "name": "Default World",
                                        "system_name": "generic",
                                        "description": "Auto-created world",
                                    }
                                )
                                payload["multiverse_id"] = m_res["id"]
                                newly_created["multiverse_id"] = UUID(m_res["id"])

                    res = await keeper.create_universe(payload)
                    if res and "id" in res:
                        newly_created["universe_id"] = UUID(res["id"])
                    committed += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"universe: {exc}")
                continue

            if p_type == "web_fetch":
                try:
                    from monitor_agents.indexer import Indexer
                    from monitor_agents.utils.world_library import WorldLibrary

                    indexer = Indexer()
                    library = WorldLibrary()

                    url = proposal.get("payload", {}).get("url")
                    if url:
                        # 1. Trigger async indexing
                        import asyncio

                        asyncio.create_task(
                            indexer.index_uri(
                                url,
                                metadata={"universe_id": str(universe_id)} if universe_id else {},
                            )
                        )

                        # 2. Record in library
                        m_id = newly_created.get("multiverse_id") or self.multiverse_id
                        if m_id:
                            # Try to get system_name from context
                            sys_name = "generic"
                            if universe_id:
                                try:
                                    from monitor_data.tools.neo4j_tools.core import (
                                        neo4j_get_universe,
                                    )

                                    u_doc = neo4j_get_universe(universe_id)
                                    if u_doc:
                                        sys_name = u_doc.default_system_name or "generic"
                                except Exception:
                                    pass

                            await library.add_source(
                                multiverse_id=m_id,
                                source_type="url",
                                uri=url,
                                system_name=sys_name,
                                metadata={"reason": proposal.get("payload", {}).get("reason")},
                            )
                        committed += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"web_fetch: {exc}")
                continue

            # Default logic for entity/axiom/fact (requires universe_id)
            if not universe_id:
                # If we just created a universe, we can't easily add entities to it in the SAME turn
                # because the extraction happened without a universe_id.
                # In the next turn, universe_id will be available.
                continue

            verdict = CanonKeeperVerdict(
                proposal_id=UUID(proposal["proposal_id"]),
                decision=CanonKeeperDecision.ACCEPTED,
                reasoning="Auto-accepted: user-defined world element via World Architect",
                canon_node_type=proposal.get("change_type", "entity"),
                canon_properties=proposal.get("payload", {}),
            )
            try:
                await keeper._commit_to_neo4j(verdict, proposal)
                committed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{proposal.get('summary', 'unknown')}: {exc}")
                logger.warning("Failed to commit proposal: %s", exc)

        return committed, errors, newly_created

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_history(history: List[Dict[str, Any]]) -> str:
        """Format message history into a text block for the prompt."""
        if not history:
            return ""

        lines: List[str] = []
        for msg in history[-20:]:  # last 20 messages for context window
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("player", "user"):
                lines.append(f"User: {content}")
            elif role in ("gm", "architect", "system"):
                lines.append(f"Architect: {content}")
        return "\n\n".join(lines)

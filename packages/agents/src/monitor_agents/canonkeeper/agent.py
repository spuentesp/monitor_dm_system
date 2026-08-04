"""
CanonKeeper Agent — sole arbiter of Neo4j writes.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts

CRITICAL RULE: Only CanonKeeper writes to Neo4j (enforced by middleware).

Responsibilities:
- Evaluate ProposedChange documents from MongoDB (accumulated during a scene)
- Run DSPy reasoning chain to assess canon consistency
- Run policy gate to catch hard violations
- Issue CanonKeeperVerdict for each proposal via instructor (strict schema)
- Commit accepted changes to Neo4j via MCP tool
- Write Story completion record on story finalize

Pipeline per proposal:
  1. PolicyCheckModule (fast gate — catches hard blocks)
  2. CanonKeeperReasoningModule (canon consistency reasoning chain)
  3. call_llm_structured(CanonKeeperVerdict) — strict verdict via instructor
  4. If ACCEPT → neo4j_create_entity/neo4j_create_fact via MCP
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from monitor_data.schemas.agent_responses import (
    CanonKeeperDecision,
    CanonKeeperVerdict,
)
from monitor_data.schemas.base import ProposalStatus
from monitor_data.tools.neo4j_tools.mechanics import (
    neo4j_create_ability_system,
    neo4j_create_condition,
    neo4j_create_resolution_mechanic,
    neo4j_create_track,
)
from pydantic import BaseModel

from monitor_agents.base import BaseAgent
from monitor_agents.canonkeeper.canonkeeper_support import gate_entity_proposals
from monitor_agents.commit_dispatcher import CommitDispatcherMixin
from monitor_agents.canonkeeper.canonkeeper import (
    CanonKeeperReasoningModule,
    PolicyCheckModule,
)
from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource

logger = logging.getLogger(__name__)


def _safe_uuid(value: Any) -> UUID | None:
    """Best-effort UUID parse for error-record correlation. None on failure —
    never fabricate a UUID that wouldn't correlate to a real record."""
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _axiom_authority_for_domain(domain: str) -> str:
    """Map a free-text axiom domain to a valid ``AxiomAuthority`` value.

    The graph's ``AxiomAuthority`` is a closed enum (physics/society/
    metaphysics/genre). Ingested and quick-world axioms carry free-text
    domains ('magic', 'general', 'technology', …); without this mapping the
    commit passes an invalid authority and the axiom is rejected.
    """
    d = (domain or "").strip().lower()
    physics = {"physics", "technology", "tech", "science", "nature", "biology"}
    society = {"society", "politics", "culture", "economy", "law", "social"}
    genre = {"genre", "theme", "tone", "convention"}
    if d in physics:
        return "physics"
    if d in society:
        return "society"
    if d in genre:
        return "genre"
    # magic, religion, divine, cosmic, metaphysics, general/unknown → metaphysics
    return "metaphysics"


def _normalise_state_tag_update(raw_props: dict[str, Any]) -> dict[str, Any]:
    """Coerce flexible state-change payloads into the `neo4j_update_state_tags` shape.
    Tags are passed through directly without hardcoded alias filtering."""
    props = dict(raw_props or {})
    entity_id = props.get("entity_id") or props.get("target_entity_id") or props.get("actor_id")
    add_tags = list(props.get("add_tags") or props.get("condition_tags") or props.get("conditions") or [])
    remove_tags = list(props.get("remove_tags") or [])

    normalized_add: list[str] = []
    for tag in add_tags:
        cleaned = str(tag).lower().strip()
        if cleaned and cleaned not in normalized_add:
            normalized_add.append(cleaned)

    normalized_remove: list[str] = []
    for tag in remove_tags:
        cleaned = str(tag).lower().strip()
        if cleaned and cleaned not in normalized_remove:
            normalized_remove.append(cleaned)

    return {
        "entity_id": entity_id,
        "add_tags": normalized_add,
        "remove_tags": normalized_remove,
    }


def _derive_detail_level(
    entity_type: str,
    base_properties: dict[str, Any],
    random_table_refs: list[str] | None = None,
) -> str:
    """Derive the appropriate DetailLevel for a newly created entity template.

    Characters with archetype data and random tables get 'sketched' (they have
    enough structure to be usable but need play to elaborate). Entities with
    rich backstory data get 'detailed'. Concepts and minimal entities stay 'stub'.

    Detail levels:
        stub       — Name + type only
        sketched   — Basic description + a few traits
        detailed   — Full backstory, relationships, motivations
        elaborated — Richly developed through play
    """
    has_props = bool(base_properties and any(v not in (None, [], {}, "") for v in base_properties.values()))
    has_tables = bool(random_table_refs)

    if entity_type == "character":
        # Characters with archetype data and random tables are sketched
        # (they'll be elaborated through play)
        if has_props and has_tables:
            return "sketched"
        if has_props:
            return "sketched"
        # Minimal character template — just a name
        return "stub"

    if entity_type in ("location", "object"):
        # Locations and objects with properties are sketched
        if has_props:
            return "sketched"
        return "stub"

    if entity_type in ("faction", "organization"):
        # Factions with properties get detailed treatment
        if has_props:
            return "detailed"
        return "sketched"

    if entity_type == "concept":
        # Concepts are inherently abstract
        return "stub"

    # Default: sketched if we have properties, stub otherwise
    return "sketched" if has_props else "stub"


class CanonKeeper(CommitDispatcherMixin, BaseAgent):
    """
    Evaluates world-state proposals and commits accepted changes to Neo4j.

    Stateless — all proposal state lives in MongoDB; all canon state in Neo4j.
    """

    def __init__(self, agent_id: str = "canonkeeper-1") -> None:
        super().__init__(agent_type="CanonKeeper", agent_id=agent_id)
        self._policy_check = PolicyCheckModule()
        self._reasoning = CanonKeeperReasoningModule()

    # ------------------------------------------------------------------
    # Proposal-type commit ordering (entities must precede relationships)
    # ------------------------------------------------------------------
    _COMMIT_ORDER = {
        "create_axiom": 0,
        "create_entity_archetype": 1,
        "create_lore_fact": 2,
        "create_random_table": 3,
        "create_tone_profile": 3,
        "create_character_profile": 4,
        "create_generation_template": 5,
        "entity_relationship": 6,
    }

    # ------------------------------------------------------------------
    # Entity type normalization (for proposal payloads)
    # ------------------------------------------------------------------
    _ENTITY_TYPE_MAP = {
        "npc": "character",
        "creature": "character",
        "monster": "character",
        "person": "character",
        "hero": "character",
        "villain": "character",
        "item": "object",
        "weapon": "object",
        "armor": "object",
        "artifact": "object",
        "guild": "organization",
        "group": "organization",
        "place": "location",
        "region": "location",
        "city": "location",
        "spell": "concept",
        "rule": "concept",
        "magic": "concept",
    }

    # ------------------------------------------------------------------
    # Relationship type normalization (maps aliases → Neo4j rel type)
    # ------------------------------------------------------------------
    _REL_TYPE_MAP = {
        # Legacy mappings (kept for backward compatibility)
        "member_of": "MEMBER_OF",
        "part_of": "PART_OF",
        "subgroup_of": "SUBGROUP_OF",
        "affiliated_with": "AFFILIATED_WITH",
        "allied_with": "ALLIED_WITH",
        "enemy_of": "HOSTILE_TO",
        "opposes": "HOSTILE_TO",
        "hostile_to": "HOSTILE_TO",
        "owns": "OWNS",
        "located_in": "LOCATED_IN",
        "contains": "CONTAINS",
        "leads": "LEADS",
        "serves": "WORKS_FOR",
        "controlled_by": "CONTROLLED_BY",
        "controls": "CONTROLS",
        "works_for": "WORKS_FOR",
        "created_by": "DERIVES_FROM",
        "descends_from": "DERIVES_FROM",
        "derives_from": "DERIVES_FROM",
        "instance_of": "INSTANCE_OF",
        "subtype_of": "SUBTYPE_OF",
        "worships": "REVERES",
        "reveres": "REVERES",
        "participates_in": "PARTICIPATES_IN",
        "knows": "KNOWS",
        "related_to": "RELATED_TO",
        # === Sub-plan 1: Game-system-agnostic group/place/power types ===
        # The LLM may emit these canonical names directly, in which case
        # we pass them through (lowercase → uppercase conversion).
        "member_of_group": "MEMBER_OF_GROUP",
        "subgroup_of_group": "SUBGROUP_OF_GROUP",
        "leads_group": "LEADS_GROUP",
        "founded_group": "FOUNDED_GROUP",
        "controls_group": "CONTROLS_GROUP",
        "allied_with_group": "ALLIED_WITH_GROUP",
        "hostile_to_group": "HOSTILE_TO_GROUP",
        "affected_by": "AFFECTED_BY",
        "grants_power": "GRANTS_POWER",
        "practices_discipline": "PRACTICES_DISCIPLINE",
        "located_in_place": "LOCATED_IN_PLACE",
        "contains_place": "CONTAINS_PLACE",
        "is_background": "IS_BACKGROUND",
        "is_touchstone": "IS_TOUCHSTONE",
        "is_resource": "IS_RESOURCE",
        # Aliases the LLM commonly emits (game-system-specific terms).
        # Each one resolves to the canonical game-system-agnostic type.
        "member_of_sect": "MEMBER_OF_GROUP",
        "member_of_clan": "MEMBER_OF_GROUP",
        "member_of_faction": "MEMBER_OF_GROUP",
        "member_of_organization": "MEMBER_OF_GROUP",
        "member_of_party": "MEMBER_OF_GROUP",
        "member_of_race": "MEMBER_OF_GROUP",
        "member_of_team": "MEMBER_OF_GROUP",
        "member_of_crew": "MEMBER_OF_GROUP",
        "member_of_house": "MEMBER_OF_GROUP",
        "member_of_tribe": "MEMBER_OF_GROUP",
        "member_of_brood": "MEMBER_OF_GROUP",
        "member_of_coven": "MEMBER_OF_GROUP",
        "member_of_cult": "MEMBER_OF_GROUP",
        "member_of_band": "MEMBER_OF_GROUP",
        "member_of_gang": "MEMBER_OF_GROUP",
        "member_of_dynasty": "MEMBER_OF_GROUP",
        "member_of_cabal": "MEMBER_OF_GROUP",
        "member_of_fellowship": "MEMBER_OF_GROUP",
        "member_of_alliance": "MEMBER_OF_GROUP",
        "belongs_to": "MEMBER_OF_GROUP",
        "belongs_to_clan": "MEMBER_OF_GROUP",
        "belongs_to_sect": "MEMBER_OF_GROUP",
        "serves_in": "MEMBER_OF_GROUP",
        "is_a_member_of": "MEMBER_OF_GROUP",
        "of_clan": "MEMBER_OF_GROUP",
        "of_sect": "MEMBER_OF_GROUP",
        "of_faction": "MEMBER_OF_GROUP",
        # Sub-group aliases
        "subclan_of": "SUBGROUP_OF_GROUP",
        "subfaction_of": "SUBGROUP_OF_GROUP",
        "house_of": "SUBGROUP_OF_GROUP",
        "under_sect": "SUBGROUP_OF_GROUP",
        # Leadership aliases
        "leads_sect": "LEADS_GROUP",
        "leads_clan": "LEADS_GROUP",
        "leads_faction": "LEADS_GROUP",
        "commands": "LEADS_GROUP",
        "rules_over": "LEADS_GROUP",
        "founded": "FOUNDED_GROUP",
        "created": "FOUNDED_GROUP",
        # Power aliases
        "grants": "GRANTS_POWER",
        "gives": "GRANTS_POWER",
        "has_power": "PRACTICES_DISCIPLINE",
        "practices": "PRACTICES_DISCIPLINE",
        "uses_power": "PRACTICES_DISCIPLINE",
        "learns": "PRACTICES_DISCIPLINE",
        "knows_power": "PRACTICES_DISCIPLINE",
        "has_discipline": "PRACTICES_DISCIPLINE",
        "has_ability": "PRACTICES_DISCIPLINE",
        "cursed_by": "AFFECTED_BY",
        "blessed_by": "AFFECTED_BY",
        "has_background": "IS_BACKGROUND",
        "has_merit": "IS_BACKGROUND",
        "has_flaw": "IS_BACKGROUND",
        "has_edge": "IS_BACKGROUND",
        "has_hindrance": "IS_BACKGROUND",
        "has_touchstone": "IS_TOUCHSTONE",
        "has_conviction": "IS_TOUCHSTONE",
        "has_tenet": "IS_TOUCHSTONE",
        "has_resource": "IS_RESOURCE",
        # Place aliases
        "based_in": "LOCATED_IN_PLACE",
        "found_in": "LOCATED_IN_PLACE",
        "in_city": "LOCATED_IN_PLACE",
        "in_world": "LOCATED_IN_PLACE",
        "in_region": "LOCATED_IN_PLACE",
        "within": "LOCATED_IN_PLACE",
    }

    # Neo4j rel_type → RelationshipCategory value. neo4j_create_relationship
    # requires `category`; without it every entity_relationship commit fails
    # validation ("params.category: Field required").
    _REL_CATEGORY_MAP = {
        # Legacy mappings (kept for backward compatibility)
        "MEMBER_OF": "membership",
        "PART_OF": "membership",
        "SUBGROUP_OF": "membership",
        "AFFILIATED_WITH": "generic",
        "ALLIED_WITH": "social",
        "HOSTILE_TO": "social",
        "KNOWS": "social",
        "REVERES": "social",
        "OWNS": "ownership",
        "LOCATED_IN": "spatial",
        "CONTAINS": "spatial",
        "LEADS": "power",
        "WORKS_FOR": "power",
        "CONTROLLED_BY": "power",
        "CONTROLS": "power",
        "DERIVES_FROM": "taxonomic",
        "INSTANCE_OF": "taxonomic",
        "SUBTYPE_OF": "taxonomic",
        "PARTICIPATES_IN": "temporal",
        "RELATED_TO": "generic",
        # === Sub-plan 1: Game-system-agnostic group/place/power types ===
        # Group types — all map to "membership" so graph queries can
        # find every group relationship generically.
        "MEMBER_OF_GROUP": "membership",
        "SUBGROUP_OF_GROUP": "membership",
        "LEADS_GROUP": "membership",
        "FOUNDED_GROUP": "membership",
        "CONTROLS_GROUP": "membership",
        "ALLIED_WITH_GROUP": "membership",
        "HOSTILE_TO_GROUP": "membership",
        # Place types — all map to "spatial".
        "LOCATED_IN_PLACE": "spatial",
        "CONTAINS_PLACE": "spatial",
        # Power/cost/condition types — all map to "taxonomic" so they
        # sit alongside SUBTYPE_OF / INSTANCE_OF for graph traversals.
        "AFFECTED_BY": "taxonomic",
        "GRANTS_POWER": "taxonomic",
        "PRACTICES_DISCIPLINE": "taxonomic",
        "IS_BACKGROUND": "taxonomic",
        "IS_TOUCHSTONE": "taxonomic",
        "IS_RESOURCE": "taxonomic",
    }

    # LLM extraction over garbled/OCR'd source text occasionally emits a
    # placeholder token ("none", "unknown", …) as an entity or relationship
    # target name instead of omitting the field. Left unchecked, these become
    # real canon nodes/edges (e.g. a literal "None" entity with several
    # unrelated archetypes proposed as its "subtype" — live 2026-07-22
    # Fallout 2d20 Settlers Supplement ingest). Checked case-insensitively.
    _PLACEHOLDER_NAMES = frozenset(
        {
            "none",
            "unknown",
            "n/a",
            "na",
            "unspecified",
            "unnamed",
            "null",
            "nil",
            "tbd",
            "-",
        }
    )

    @classmethod
    def _is_placeholder_name(cls, name: str | None) -> bool:
        """True for empty/whitespace names and known LLM placeholder tokens."""
        stripped = (name or "").strip().lower()
        return not stripped or stripped in cls._PLACEHOLDER_NAMES

    _RANDOM_TABLE_TYPE_MAP = {
        "custom": "custom",
        "misc": "custom",
        "names": "name",
        "name": "name",
        "trait": "trait",
        "traits": "trait",
        "encounter": "encounter",
        "encounters": "encounter",
        "loot": "loot",
        "weather": "weather",
        "rumor": "rumor",
        "rumors": "rumor",
        "npc": "npc",
        "npcs": "npc",
        "event": "event",
        "events": "event",
        "location": "location",
        "locations": "location",
        "complication": "complication",
        "complications": "complication",
    }

    # _COMMIT_HANDLERS dispatch table and _commit_to_neo4j() live in
    # CommitDispatcherMixin (commit_dispatcher.py) — SRP separation.

    async def run(self) -> None:
        pass  # driven by scene_loop.canonize_checkpoint()

    # ------------------------------------------------------------------
    # Contradiction detection (CF-5)
    # ------------------------------------------------------------------

    async def verify_fact(
        self,
        new_fact: str,
        context: list[str],
    ) -> dict[str, Any]:
        """
        Check if a new fact contradicts established context.

        Uses the PolicyCheckModule for fast gate checks and
        CanonKeeperReasoningModule for deeper analysis.

        Args:
            new_fact: The fact to verify.
            context: List of established facts to check against.

        Returns:
            Dict with 'has_contradiction' (bool) and 'explanation' (str).
        """
        from monitor_agents.canonkeeper.verification import ContradictionModule

        module = ContradictionModule()
        try:
            result = await asyncio.to_thread(
                module.forward,
                context=" ".join(context),
                new_fact=new_fact,
            )
            return result
        except Exception:  # pragma: no cover — fallback path
            logger.warning(
                "Contradiction detection failed, using heuristic fallback",
                exc_info=True,
            )
            return self._heuristic_contradiction_check(new_fact, context)

    def _heuristic_contradiction_check(self, new_fact: str, context: list[str]) -> dict[str, Any]:
        """Simple heuristic contradiction detection as fallback."""
        new_lower = new_fact.lower()
        negation_words = ["not ", "never ", "no ", "isn't ", "doesn't ", "cannot "]
        for ctx in context:
            ctx_lower = ctx.lower()
            for neg in negation_words:
                if neg in new_lower and neg.replace(" ", "") not in ctx_lower:
                    # Check if the non-negated part overlaps
                    stripped = new_lower.replace(neg, "").strip()
                    if any(word in ctx_lower for word in stripped.split()[:3]):
                        return {
                            "has_contradiction": True,
                            "explanation": f"'{new_fact}' may contradict '{ctx}'",
                        }
        return {"has_contradiction": False, "explanation": ""}

    async def check_live_entry(
        self,
        universe_id: UUID,
        entry_text: str,
    ) -> dict[str, Any]:
        """
        Advisory contradiction check for a live capture entry (CF-1).

        Assembles its own canon context (facts + axioms) and delegates the
        actual check to verify_fact. Used by the GM Session Recorder to flag
        entries that collide with canon while they are being logged.

        Advisory and read-only: never creates proposals, never writes to
        Neo4j. Costs at most one LLM call per invocation (skipped entirely
        when the entry is empty or the universe has no canon context).

        Args:
            universe_id: Universe whose canon facts/axioms form the context.
            entry_text: The raw capture entry text to check.

        Returns:
            Dict with 'has_contradiction' (bool) and 'explanation' (str).
        """
        entry = (entry_text or "").strip()
        if not entry:
            return {"has_contradiction": False, "explanation": ""}

        facts = await self._fetch_canon_facts(universe_id)
        axioms = await self._fetch_canon_axioms(universe_id)

        context_lines = []
        for ax in axioms:
            context_lines.append(f"Axiom: {ax.get('statement')}")
        for f in facts:
            context_lines.append(f"Fact: {f.get('statement')}")

        context = "\n".join(context_lines)

        # If no context, we can't check for contradictions
        if not context:
            return {"has_contradiction": False, "explanation": ""}

        return await self.verify_fact(entry, context_lines)

    # ------------------------------------------------------------------
    # Primary entry points
    # ------------------------------------------------------------------

    async def evaluate_proposals(
        self,
        scene_id: UUID,
        proposals: list[dict[str, Any]],
    ) -> list[CanonKeeperVerdict]:
        """
        Evaluate all pending proposals for a scene and commit accepted ones.

        Called by scene_loop.canonize_checkpoint() at scene end or checkpoint.

        Args:
            scene_id:  The scene whose proposals are being evaluated.
            proposals: List of proposal dicts from MongoDb (via pending_proposals state).

        Returns:
            List of CanonKeeperVerdict — one per proposal.
        """
        verdicts: list[CanonKeeperVerdict] = []

        if not proposals:
            return verdicts

        # Entity-promotion gate: topology/anchor/flavor-threshold decisions
        # skip the expensive LLM pipeline entirely (see canonkeeper_support.py
        # and docs/2_architecture/data_model_workflow.md).
        gated, proposals = gate_entity_proposals(proposals)
        for proposal, verdict in gated:
            verdicts.append(verdict)
            logger.info(
                "CanonKeeper gate verdict: %s -> %s (%s)",
                (proposal.get("content") or {}).get("name", "?"),
                verdict.decision.value,
                verdict.reasoning,
            )
            if verdict.decision == CanonKeeperDecision.ACCEPTED:
                await self._commit_to_neo4j(verdict, proposal)
            elif verdict.decision == CanonKeeperDecision.REJECTED:
                await self._record_visual_identity_rejection(proposal, verdict)
            await self._record_verdict(scene_id, verdict)

        if not proposals:
            return verdicts

        # Fetch context once (shared across all proposals in this batch)
        world_rules = await self._fetch_world_rules(scene_id)
        protected_entities = await self._fetch_protected_entities(scene_id)

        for proposal in proposals:
            verdict = await self._evaluate_single(
                proposal=proposal,
                world_rules=world_rules,
                protected_entities=protected_entities,
            )
            verdicts.append(verdict)

            # Commit immediately on ACCEPT so partial batches are durable
            if verdict.decision == CanonKeeperDecision.ACCEPTED:
                await self._commit_to_neo4j(verdict, proposal)
            elif verdict.decision == CanonKeeperDecision.REJECTED:
                await self._record_visual_identity_rejection(proposal, verdict)

            # Record verdict in MongoDB for audit trail
            await self._record_verdict(scene_id, verdict)

        return verdicts

    async def bulk_commit_proposals(
        self,
        proposals: list[dict[str, Any]],
        *,
        universe_id: UUID | None = None,
        source_ids: list[UUID] | None = None,
        contradiction_check: bool = True,
    ) -> dict[str, Any]:
        """Commit already-analyzed proposals straight to Neo4j.

        **Opt-in.** Used only when ``MONITOR_AUTO_CANONIZE=1`` is
        set on the ingestion pipeline. The default ingestion flow now
        routes to :meth:`bulk_enqueue_proposals`, which keeps the
        proposals ``status=pending`` (tagged ``source=ingestion_job:<id>``)
        for human review instead.

        Proposals produced by the Analyzer have already been extracted and
        validated, so the heavyweight per-proposal LLM evaluation used by
        ``evaluate_proposals`` at scene runtime (policy gate + per-fact
        contradiction call + reasoning CoT + structured verdict — ~4 LLM calls
        *each*) is wasteful here.

        Instead we:
          1. (optional) run ONE *batched* contradiction check of all candidate
             facts against the universe's PRE-EXISTING canon. For a fresh
             universe there is no prior canon, so this is a no-op (zero LLM
             calls). For a populated universe it costs one call per ~15 facts
             rather than one per proposal.
          2. commit the non-conflicting proposals to Neo4j in dependency order
             (axioms → entities → facts → relationships).

        Returns ``{"committed": int, "rejected": int, "errors": [str]}``.
        """
        if not proposals:
            return {"committed": 0, "rejected": 0, "errors": []}

        from monitor_data.db.mongodb import get_mongodb_client

        mongodb = get_mongodb_client()
        proposals_coll = mongodb.get_collection("proposed_changes")

        ordered = sorted(
            proposals,
            key=lambda p: self._COMMIT_ORDER.get(p.get("proposal_type", ""), 2),
        )

        rejected_ids: dict[str, str] = {}
        if contradiction_check and universe_id is not None:
            try:
                rejected_ids = await self._batch_contradiction_check(ordered, universe_id)
            except Exception as exc:
                logger.warning("Batched contradiction check failed (committing anyway): %s", exc)
                await RoleplayErrorRecorder.record(
                    source=RoleplayErrorSource.CANONKEEPER,
                    category=RoleplayErrorCategory.CANONKEEPER_WRITE_FAILED,
                    message=str(exc),
                    fatal=False,
                    universe_id=universe_id,
                )

        committed = 0
        rejected = 0
        errors: list[str] = []
        for proposal in ordered:
            pid = str(proposal.get("proposal_id") or "")
            if pid in rejected_ids:
                rejected += 1
                proposals_coll.update_one(
                    {"proposal_id": pid},
                    {"$set": {"status": "rejected", "rejection_reason": rejected_ids[pid]}},
                )
                continue
            try:
                verdict = CanonKeeperVerdict(
                    proposal_id=UUID(pid),
                    decision=CanonKeeperDecision.ACCEPTED,
                    reasoning="Auto-accepted during bulk ingestion canonization",
                )
                await self._commit_to_neo4j(verdict, proposal, source_ids=source_ids)
                proposals_coll.update_one(
                    {"proposal_id": pid},
                    {"$set": {"status": "committed"}},
                )
                committed += 1
            except Exception as exc:
                errors.append(f"{pid}: {exc}")

        logger.info(
            "Bulk commit complete: %d committed, %d rejected, %d errors",
            committed,
            rejected,
            len(errors),
        )
        return {"committed": committed, "rejected": rejected, "errors": errors}

    async def bulk_enqueue_proposals(
        self,
        proposals: list[dict[str, Any]],
        *,
        ingestion_job_id: UUID,
        source_ids: list[UUID] | None = None,
    ) -> dict[str, Any]:
        """Mark analyzed proposals as pending human review for one ingest.

        **Default** ingestion flow (``MONITOR_AUTO_CANONIZE=0``).
        Keeps ``status=pending`` (the schema-valid ``ProposalStatus``
        for a proposal awaiting review), retags ``source`` to
        ``ingestion_job:<job_id>`` so
        :class:`packages.ui.backend.monitor_ui.routers.canon_review` can
        scope UI listing to a single ingest, and sets
        ``meta.requires_review=True``.

        No Neo4j writes. No LLM calls. Idempotent: re-running on the
        same proposal set is safe (status stays ``pending``).

        Returns ``{"enqueued": int, "errors": [str]}``.
        """
        if not proposals:
            return {"enqueued": 0, "errors": []}

        from monitor_data.db.mongodb import get_mongodb_client

        mongodb = get_mongodb_client()
        proposals_coll = mongodb.get_collection("proposed_changes")

        enqueued = 0
        errors: list[str] = []
        source_key = f"ingestion_job:{ingestion_job_id}"
        for proposal in proposals:
            pid = str(proposal.get("proposal_id") or "")
            if not pid:
                errors.append("proposal missing proposal_id")
                continue
            try:
                proposals_coll.update_one(
                    {"proposal_id": pid},
                    {
                        "$set": {
                            "status": ProposalStatus.PENDING.value,
                            "source": source_key,
                            "meta.batch_id": str(ingestion_job_id),
                            "meta.requires_review": True,
                            "meta.enqueued_at": datetime.now(UTC),
                        }
                    },
                )
                enqueued += 1
            except Exception as exc:
                errors.append(f"{pid}: {exc}")

        logger.info(
            "Bulk enqueue for review complete: job=%s, %d enqueued, %d errors",
            ingestion_job_id,
            enqueued,
            len(errors),
        )
        return {"enqueued": enqueued, "errors": errors}

    async def _batch_contradiction_check(
        self,
        proposals: list[dict[str, Any]],
        universe_id: UUID,
    ) -> dict[str, str]:
        """
        Check all candidate facts against PRE-EXISTING canon in chunked LLM calls.

        Returns ``{proposal_id: explanation}`` for proposals that directly
        contradict existing canon. Returns ``{}`` (no LLM call) when the universe
        has no prior canon to contradict — e.g. the first ingest into a fresh
        universe.
        """
        facts = await self._fetch_canon_facts(universe_id)
        axioms = await self._fetch_canon_axioms(universe_id)
        context_lines = [f"Axiom: {a.get('statement')}" for a in axioms if a.get("statement")]
        context_lines += [f"Fact: {f.get('statement')}" for f in facts if f.get("statement")]
        context = "\n".join(context_lines)
        if not context:
            return {}

        candidates: list[tuple[str, str]] = []
        for p in proposals:
            content = p.get("content", {})
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    content = {}
            text = content.get("statement") or p.get("summary")
            pid = str(p.get("proposal_id") or "")
            if text and pid:
                candidates.append((pid, text))
        if not candidates:
            return {}

        from monitor_agents.canonkeeper.verification import BatchContradictionModule

        module = BatchContradictionModule()
        rejected: dict[str, str] = {}
        chunk_size = 15
        for start in range(0, len(candidates), chunk_size):
            chunk = candidates[start : start + chunk_size]
            numbered = "\n".join(f"{i + 1}. {text}" for i, (_, text) in enumerate(chunk))
            flagged = await asyncio.to_thread(module.forward, context=context, new_facts=numbered)
            for one_based_idx, explanation in flagged.items():
                ci = one_based_idx - 1
                if 0 <= ci < len(chunk):
                    rejected[chunk[ci][0]] = explanation
        return rejected

    async def apply_pack_to_universe(
        self,
        pack_id: UUID,
        multiverse_id: UUID,
        universe_id: UUID | None = None,
        auto_accept: bool = False,
        request_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Apply a KnowledgePack to a multiverse.

        By default (auto_accept=False) this creates PENDING proposals only,
        leaving them for human review.  Set auto_accept=True to immediately
        commit all proposals to Neo4j (legacy behaviour used by CLI / tests).

        Args:
            pack_id:       KnowledgePack to apply.
            multiverse_id: Target multiverse.
            universe_id:   Optional universe to scope entities/axioms.
            auto_accept:   If True, auto-commit all proposals (legacy).
            request_overrides: Optional extra ``ApplyKnowledgePackRequest``
                fields (subset indices, item overrides, apply_* flags)
                forwarded to ``mongodb_apply_knowledge_pack``.

        Returns:
            Dict with proposals_created, committed, errors.
        """
        from monitor_data.db.mongodb import get_mongodb_client
        from monitor_data.schemas.knowledge_packs import ApplyKnowledgePackRequest
        from monitor_data.tools.mongodb_tools import mongodb_apply_knowledge_pack

        mongodb = get_mongodb_client()
        proposals_coll = mongodb.get_collection("proposed_changes")

        # Skip proposal creation if this pack+universe was already committed.
        # Re-use any still-pending proposals from a previous partial run instead.
        source_key = f"knowledge_pack:{pack_id}"
        already_committed = proposals_coll.count_documents({"source": source_key, "status": "committed"})

        if already_committed == 0:
            # Step 1: Materialise ProposedChanges from the pack
            result = mongodb_apply_knowledge_pack(
                pack_id,
                ApplyKnowledgePackRequest(
                    multiverse_id=multiverse_id,
                    universe_id=universe_id,
                    conflict_resolution="merge",
                    **(request_overrides or {}),
                ),
            )
            proposals_created: int = result.get("proposals_created", 0)
        else:
            proposals_created = 0  # no new ones needed

        # When auto_accept is False, stop here — proposals are PENDING for review.
        if not auto_accept:
            # Mark pack as REVIEW_PENDING so the UI shows the review badge.
            from monitor_data.schemas.knowledge_packs import KnowledgePackStatus as KPS

            mongodb.get_collection("knowledge_packs").update_one(
                {"pack_id": str(pack_id)},
                {"$set": {"status": KPS.REVIEW_PENDING.value}},
            )
            return {
                "proposals_created": proposals_created,
                "committed": 0,
                "errors": [],
                "review_status": "pending",
            }

        # Step 2: Fetch all pending proposals for this pack
        proposals = list(proposals_coll.find({"source": source_key, "status": "pending"}))

        if not proposals and proposals_created == 0:
            return {"proposals_created": 0, "committed": 0, "errors": []}

        # Sort proposals so entities are committed before relationships (GAP-14 fix).
        # entity_relationship proposals look up both endpoints by name in Neo4j —
        # they must arrive after create_entity_archetype proposals have been committed.
        proposals.sort(key=lambda p: self._COMMIT_ORDER.get(p.get("proposal_type", ""), 2))

        # Step 3: Resolve pack source_document_ids → Neo4j Source node UUIDs.
        # MongoDB documents carry a `source_id` field that references the Neo4j
        # Source node created during ingestion.  We look that up once per pack
        # so every entity/axiom/fact created below can carry SUPPORTED_BY edges.
        neo4j_source_ids: list[UUID] = []
        pack_doc = mongodb.get_collection("knowledge_packs").find_one({"pack_id": str(pack_id)})
        if pack_doc:
            for doc_id_str in pack_doc.get("source_document_ids", []):
                mongo_doc = mongodb.get_collection("documents").find_one({"doc_id": str(doc_id_str)})
                if mongo_doc and mongo_doc.get("source_id"):
                    with suppress(ValueError):
                        neo4j_source_ids.append(UUID(mongo_doc["source_id"]))

        # Step 4: Auto-commit each proposal to Neo4j
        committed = 0
        errors: list[str] = []
        for proposal in proposals:
            verdict = CanonKeeperVerdict(
                proposal_id=UUID(proposal["proposal_id"]),
                decision=CanonKeeperDecision.ACCEPTED,
                reasoning="Auto-accepted during knowledge pack ingestion",
                confidence=1.0,
            )
            try:
                await self._commit_to_neo4j(verdict, proposal, source_ids=neo4j_source_ids or None)
                # Mark proposal as committed so it won't be re-processed
                proposals_coll.update_one(
                    {"proposal_id": proposal["proposal_id"]},
                    {"$set": {"status": "committed"}},
                )
                committed += 1
            except Exception as exc:
                errors.append(str(exc))

        # Step 5: Write mechanic reference nodes when game_system_data exists
        if pack_doc and pack_doc.get("game_system_data"):
            from monitor_data.schemas.knowledge_packs import EmbeddedGameSystem

            try:
                gs = EmbeddedGameSystem(**pack_doc["game_system_data"])
                system_id = gs.name or "unknown_system"
                for ability in gs.tiered_abilities or []:
                    neo4j_create_ability_system(
                        name=ability.name,
                        system_id=system_id,
                        parent_category=ability.parent_category,
                    )
                for track in gs.tracks or []:
                    neo4j_create_track(
                        name=track.name,
                        system_id=system_id,
                        track_type=track.track_type,
                    )
                for condition in gs.conditions or []:
                    neo4j_create_condition(
                        name=condition.name,
                        system_id=system_id,
                    )
                for rm in gs.resolution_mechanics or []:
                    neo4j_create_resolution_mechanic(
                        name=rm.dice_formula,
                        system_id=system_id,
                        mechanic_type=rm.mechanic_type.value,
                    )
            except Exception as exc:
                logger.warning("Failed to write mechanic nodes: %s", exc)
                errors.append(f"mechanic_nodes: {exc}")
                await RoleplayErrorRecorder.record(
                    source=RoleplayErrorSource.CANONKEEPER,
                    category=RoleplayErrorCategory.CANONKEEPER_WRITE_FAILED,
                    message=str(exc),
                    fatal=False,
                    universe_id=_safe_uuid(pack_doc.get("universe_id")) if pack_doc else None,
                )

        return {
            "proposals_created": proposals_created,
            "committed": committed,
            "errors": errors,
        }

    async def commit_accepted(
        self,
        pack_id: UUID,
    ) -> dict[str, Any]:
        """
        Commit all ACCEPTED proposals for a pack to Neo4j.

        Called after human review — only proposals the user accepted are
        committed.  Rejected proposals are left in MongoDB for audit.

        Args:
            pack_id: KnowledgePack whose proposals to commit.

        Returns:
            Dict with committed count and errors.
        """
        from monitor_data.db.mongodb import get_mongodb_client
        from monitor_data.schemas.agent_responses import (
            CanonKeeperDecision,
            CanonKeeperVerdict,
        )
        from monitor_data.schemas.knowledge_packs import KnowledgePackStatus as KPS

        mongodb = get_mongodb_client()
        proposals_coll = mongodb.get_collection("proposed_changes")
        source_key = f"knowledge_pack:{pack_id}"

        # Fetch ACCEPTED proposals (set by the review UI)
        proposals = list(proposals_coll.find({"source": source_key, "status": "accepted"}))

        if not proposals:
            return {"committed": 0, "errors": []}

        # Resolve Neo4j Source node UUIDs
        neo4j_source_ids: list[UUID] = []
        pack_doc = mongodb.get_collection("knowledge_packs").find_one({"pack_id": str(pack_id)})
        if pack_doc:
            for doc_id_str in pack_doc.get("source_document_ids", []):
                mongo_doc = mongodb.get_collection("documents").find_one({"doc_id": str(doc_id_str)})
                if mongo_doc and mongo_doc.get("source_id"):
                    with suppress(ValueError):
                        neo4j_source_ids.append(UUID(mongo_doc["source_id"]))

        # Sort so entities are committed before relationships
        proposals.sort(key=lambda p: self._COMMIT_ORDER.get(p.get("proposal_type", ""), 2))

        committed = 0
        errors: list[str] = []
        for proposal in proposals:
            verdict = CanonKeeperVerdict(
                proposal_id=UUID(proposal["proposal_id"]),
                decision=CanonKeeperDecision.ACCEPTED,
                reasoning="Accepted during human review",
                confidence=1.0,
            )
            try:
                await self._commit_to_neo4j(verdict, proposal, source_ids=neo4j_source_ids or None)
                proposals_coll.update_one(
                    {"proposal_id": proposal["proposal_id"]},
                    {"$set": {"status": "committed"}},
                )
                committed += 1
            except Exception as exc:
                errors.append(str(exc))

        # Write mechanic reference nodes when game_system_data exists
        if pack_doc and pack_doc.get("game_system_data"):
            from monitor_data.schemas.knowledge_packs import EmbeddedGameSystem

            try:
                gs = EmbeddedGameSystem(**pack_doc["game_system_data"])
                system_id = gs.name or "unknown_system"
                for ability in gs.tiered_abilities or []:
                    neo4j_create_ability_system(
                        name=ability.name,
                        system_id=system_id,
                        parent_category=ability.parent_category,
                    )
                for track in gs.tracks or []:
                    neo4j_create_track(
                        name=track.name,
                        system_id=system_id,
                        track_type=track.track_type,
                    )
                for condition in gs.conditions or []:
                    neo4j_create_condition(
                        name=condition.name,
                        system_id=system_id,
                    )
                for rm in gs.resolution_mechanics or []:
                    neo4j_create_resolution_mechanic(
                        name=rm.dice_formula,
                        system_id=system_id,
                        mechanic_type=rm.mechanic_type.value,
                    )
            except Exception as exc:
                logger.warning("Failed to write mechanic nodes: %s", exc)
                errors.append(f"mechanic_nodes: {exc}")
                await RoleplayErrorRecorder.record(
                    source=RoleplayErrorSource.CANONKEEPER,
                    category=RoleplayErrorCategory.CANONKEEPER_WRITE_FAILED,
                    message=str(exc),
                    fatal=False,
                    universe_id=_safe_uuid(pack_doc.get("universe_id")) if pack_doc else None,
                )

        # Mark pack as APPLIED once all accepted proposals are committed
        mongodb.get_collection("knowledge_packs").update_one(
            {"pack_id": str(pack_id)},
            {"$set": {"status": KPS.APPLIED.value}},
        )

        return {"committed": committed, "errors": errors}

    async def commit_accepted_for_job(
        self,
        ingestion_job_id: UUID,
    ) -> dict[str, Any]:
        """
        Commit all ACCEPTED proposals for one ingestion job to Neo4j.

        By-ingest counterpart of :meth:`commit_accepted`: proposals
        enqueued by :meth:`bulk_enqueue_proposals` carry
        ``source=ingestion_job:<job_id>`` (not ``knowledge_pack:<id>``),
        so the pack commit path never sees them. Called after human
        review — only proposals the user accepted are committed.
        Rejected proposals are left in MongoDB for audit.

        Args:
            ingestion_job_id: Ingestion job whose proposals to commit.

        Returns:
            Dict with committed count and errors.
        """
        from monitor_data.db.mongodb import get_mongodb_client
        from monitor_data.schemas.agent_responses import (
            CanonKeeperDecision,
            CanonKeeperVerdict,
        )

        mongodb = get_mongodb_client()
        proposals_coll = mongodb.get_collection("proposed_changes")
        source_key = f"ingestion_job:{ingestion_job_id}"

        # Fetch ACCEPTED proposals (set by the review UI)
        proposals = list(proposals_coll.find({"source": source_key, "status": "accepted"}))

        if not proposals:
            return {"committed": 0, "errors": []}

        # Resolve the Neo4j Source node for SUPPORTED_BY provenance edges.
        # The ingestion job's source_id IS the Neo4j Source node UUID
        # (created by the pipeline before analysis).
        neo4j_source_ids: list[UUID] = []
        job_doc = mongodb.get_collection("ingestion_jobs").find_one({"job_id": str(ingestion_job_id)})
        if job_doc and job_doc.get("source_id"):
            with suppress(ValueError):
                neo4j_source_ids.append(UUID(str(job_doc["source_id"])))

        # Sort so entities are committed before relationships
        proposals.sort(key=lambda p: self._COMMIT_ORDER.get(p.get("proposal_type", ""), 2))

        committed = 0
        errors: list[str] = []
        for proposal in proposals:
            verdict = CanonKeeperVerdict(
                proposal_id=UUID(proposal["proposal_id"]),
                decision=CanonKeeperDecision.ACCEPTED,
                reasoning="Accepted during human review",
                confidence=1.0,
            )
            try:
                await self._commit_to_neo4j(verdict, proposal, source_ids=neo4j_source_ids or None)
                proposals_coll.update_one(
                    {"proposal_id": proposal["proposal_id"]},
                    {"$set": {"status": "committed"}},
                )
                committed += 1
            except Exception as exc:
                errors.append(str(exc))

        return {"committed": committed, "errors": errors}

    async def finalize_story(self, story_id: UUID) -> None:
        """
        Mark a Story node as complete in Neo4j.

        Called by story_loop.finalize_story() at campaign end.
        Only CanonKeeper may write this (enforced by Neo4j middleware).
        """
        await self.call_tool(
            "neo4j_update_story_status",
            {
                "story_id": str(story_id),
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
            },
        )

    async def end_scene(
        self,
        scene_id: UUID,
        story_id: UUID,
        actor_id: UUID | None = None,
        universe_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Scene-end bookkeeping hook.

        Called by scene_loop.complete_current_scene() when a scene is
        complete but before the story advances. Records the scene-end
        marker and surfaces any deferred proposals for the GM to review.

        Returns a small dict so callers can log it. The actual canonical
        writes are owned by the calling scene/story loops; this method
        only emits the bookkeeping signal so CanonKeeper has a single
        lifecycle entry point.
        """
        logger.info(
            "CanonKeeper.end_scene: scene_id=%s story_id=%s actor_id=%s",
            scene_id,
            story_id,
            actor_id,
        )
        # Best-effort: log a scene-end marker fact. If the call fails
        # (e.g., Neo4j down), we do not block scene completion; the
        # state transitions above are the source of truth.
        try:
            if universe_id is not None:
                # neo4j_create_fact takes a single FactCreate payload under
                # the "params" key; scene/story go into properties.
                await self.call_tool(
                    "neo4j_create_fact",
                    {
                        "params": {
                            "universe_id": str(universe_id),
                            "statement": f"Scene {scene_id} ended",
                            "fact_type": "occurrence",
                            "properties": {
                                "kind": "scene_end",
                                "scene_id": str(scene_id),
                                "story_id": str(story_id),
                            },
                        }
                    },
                )
        except Exception as exc:
            logger.warning("CanonKeeper.end_scene: fact write failed (non-fatal): %s", exc)
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.CANONKEEPER,
                category=RoleplayErrorCategory.CANONKEEPER_WRITE_FAILED,
                message=str(exc),
                fatal=False,
                universe_id=universe_id,
                story_id=story_id,
                scene_id=scene_id,
                entity_id=actor_id,
            )
        return {
            "scene_id": str(scene_id),
            "story_id": str(story_id),
            "actor_id": str(actor_id) if actor_id else None,
            "ended_at": datetime.now(UTC).isoformat(),
        }

    async def create_story(
        self,
        story_id: UUID,
        universe_id: UUID,
        title: str = "New Story",
        story_type: str = "campaign",
    ) -> dict[str, Any]:
        """
        Create a new Story node in Neo4j.

        Authority: CanonKeeper only.
        """
        from monitor_data.schemas.stories import StoryStatus

        raw = await self.call_tool(
            "neo4j_create_story",
            {
                "params": {
                    "id": str(story_id),
                    "universe_id": str(universe_id),
                    "title": title,
                    "story_type": story_type,
                    "status": StoryStatus.ACTIVE.value,
                }
            },
        )
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
                return {"id": str(story_id)}
            except json.JSONDecodeError:
                return {"id": str(story_id)}
        if isinstance(raw, dict):
            return raw
        return {"id": str(story_id)}

    async def ensure_omniverse(self) -> UUID:
        """Ensure an Omniverse exists and return its ID."""
        raw = await self.call_tool("neo4j_ensure_omniverse", {})
        data = json.loads(raw) if isinstance(raw, str) else raw
        return UUID(data["omniverse_id"])

    async def create_multiverse(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new Multiverse in Neo4j.

        Authority: CanonKeeper only.
        """
        if "omniverse_id" not in params:
            params["omniverse_id"] = str(await self.ensure_omniverse())

        raw = await self.call_tool(
            "neo4j_create_multiverse",
            {"params": params},
        )
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return dict(parsed) if isinstance(parsed, dict) else {"error": raw}
            except (json.JSONDecodeError, TypeError):
                return {"error": raw}
        if isinstance(raw, dict):
            return cast(dict[str, Any], dict(raw))
        return {}

    async def create_fact(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new Fact in Neo4j.

        Authority: CanonKeeper only.
        """
        raw = await self.call_tool(
            "neo4j_create_fact",
            {"params": params},
        )
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return dict(parsed) if isinstance(parsed, dict) else {"error": raw}
            except (json.JSONDecodeError, TypeError):
                return {"error": raw}
        if isinstance(raw, dict):
            return cast(dict[str, Any], dict(raw))
        return {}

    async def replace_fact(
        self,
        old_fact_id: UUID,
        new_fact_params: dict[str, Any],
        scene_id: UUID | None = None,
        reason: str = "Fact updated during scene revision",
    ) -> dict[str, Any]:
        """
        Replace an existing fact with a new version (Temporal & Contradiction Gap).

        This creates a new fact with the `replaces` field pointing to the old fact,
        and optionally tombstones the old fact to mark it as superseded.

        Authority: CanonKeeper only.

        Args:
            old_fact_id: The fact being replaced.
            new_fact_params: Parameters for the new fact.
            scene_id: Scene causing the replacement.
            reason: Why the replacement is occurring.

        Returns:
            Dict with new_fact_id and replacement tracking info.
        """
        # Add the `replaces` field to the new fact
        new_fact_params["replaces"] = str(old_fact_id)

        # Create the new fact
        result = await self.create_fact(new_fact_params)

        if "error" in result:
            logger.error(f"Failed to create replacement fact: {result['error']}")
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.CANONKEEPER,
                category=RoleplayErrorCategory.CANONKEEPER_WRITE_FAILED,
                message=str(result["error"]),
                fatal=False,
                universe_id=_safe_uuid(new_fact_params.get("universe_id")),
                scene_id=scene_id,
                entity_id=old_fact_id,
            )
            return result

        new_fact_id = result.get("id")

        # Tombstone the old fact (mark as replaced)
        try:
            await self.call_tool(
                "neo4j_update_fact",
                {
                    "fact_id": str(old_fact_id),
                    "updates": {
                        "replaced_by": str(new_fact_id),
                        "replaced_at": datetime.now(UTC).isoformat(),
                        "replaced_reason": reason,
                    },
                },
            )
            logger.info(f"Replaced fact {old_fact_id} with {new_fact_id} (scene: {scene_id}, reason: {reason})")
        except Exception as e:
            logger.warning(f"Failed to tombstone old fact {old_fact_id}: {e}")
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.CANONKEEPER,
                category=RoleplayErrorCategory.CANONKEEPER_WRITE_FAILED,
                message=str(e),
                fatal=False,
                universe_id=_safe_uuid(new_fact_params.get("universe_id")),
                scene_id=scene_id,
                entity_id=old_fact_id,
            )

        # Track replacement in MongoDB for audit trail
        await self._track_fact_replacement(
            old_fact_id=old_fact_id,
            new_fact_id=UUID(str(new_fact_id)) if new_fact_id else None,
            scene_id=scene_id,
            reason=reason,
        )

        return {
            "old_fact_id": str(old_fact_id),
            "new_fact_id": str(new_fact_id) if new_fact_id else None,
            "scene_id": str(scene_id) if scene_id else None,
            "reason": reason,
            "replacement_time": datetime.now(UTC).isoformat(),
        }

    async def _track_fact_replacement(
        self,
        old_fact_id: UUID,
        new_fact_id: UUID | None,
        scene_id: UUID | None,
        reason: str,
    ) -> None:
        """
        Track fact replacements in MongoDB for audit trail (Temporal & Contradiction Gap).

        Args:
            old_fact_id: The fact that was replaced.
            new_fact_id: The new fact that replaced it.
            scene_id: Scene causing the replacement.
            reason: Why the replacement occurred.
        """
        from monitor_data.db.mongodb import get_mongodb_client

        mongodb = get_mongodb_client()
        replacements_coll = mongodb.get_collection("fact_replacements")

        replacements_coll.insert_one(
            {
                "old_fact_id": str(old_fact_id),
                "new_fact_id": str(new_fact_id) if new_fact_id else None,
                "scene_id": str(scene_id) if scene_id else None,
                "reason": reason,
                "replacement_time": datetime.now(UTC).isoformat(),
                "tracked_by": "canonkeeper",
            }
        )

    async def story_exists(self, story_id: UUID) -> bool:
        """
        Check if a Story node exists in Neo4j.

        Returns:
            True if the story exists, False otherwise.
        """
        try:
            raw = await self.call_tool(
                "neo4j_get_story",
                {
                    "story_id": str(story_id),
                },
            )
            # If we get a result back (not None and not empty), the story exists
            return raw is not None and raw != {}
        except Exception as e:
            logger.error(f"Error checking if story {story_id} exists: {e}")
            return False

    async def list_universes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        List all available universes from Neo4j.

        Args:
            filters: Optional dictionary of filter parameters (multiverse_id, canon_level, genre, limit, offset)

        Returns:
            List of universe dictionaries.
        """
        raw = await self.call_tool(
            "neo4j_list_universes",
            {"filters": filters or {}},
        )
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        if isinstance(raw, list):
            return raw
        return []

    async def list_multiverses(self, omniverse_id: UUID | None = None) -> list[dict[str, Any]]:
        """
        List all available multiverses from Neo4j.

        Args:
            omniverse_id: Optional filter by parent omniverse.

        Returns:
            List of multiverse dictionaries.
        """
        raw = await self.call_tool(
            "neo4j_list_multiverses",
            {"omniverse_id": str(omniverse_id) if omniverse_id else None},
        )
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        if isinstance(raw, list):
            return raw
        return []

    async def create_universe(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new Universe in Neo4j.

        Authority: CanonKeeper only.

        Args:
            params: Universe creation parameters.

        Returns:
            Created universe dictionary.
        """
        raw = await self.call_tool(
            "neo4j_create_universe",
            {"params": params},
        )
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return dict(parsed) if isinstance(parsed, dict) else {"error": raw}
            except (json.JSONDecodeError, TypeError):
                return {"error": raw}
        if isinstance(raw, dict):
            return cast(dict[str, Any], dict(raw))
        return {}

    async def get_universe(self, universe_id: UUID) -> dict[str, Any] | None:
        """
        Get a specific Universe from Neo4j.

        Args:
            universe_id: UUID of the universe.

        Returns:
            Universe dictionary or None if not found.
        """
        raw = await self.call_tool(
            "neo4j_get_universe",
            {"universe_id": str(universe_id)},
        )
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return dict(parsed) if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, TypeError):
                return None
        if isinstance(raw, dict):
            return cast(dict[str, Any], dict(raw))
        return None

    async def create_entity(self, entity_create: Any) -> dict[str, Any]:
        """
        Create a new Entity node in Neo4j.

        Authority: CanonKeeper only.

        Args:
            entity_create: EntityCreate schema with entity data

        Returns:
            Dict with created entity data including 'id'
        """

        # Convert EntityCreate to dict for the tool call
        params = {
            "universe_id": str(entity_create.universe_id),
            "id": str(entity_create.id) if entity_create.id else None,
            "name": entity_create.name,
            "entity_type": entity_create.entity_type.value,
            "sub_type": entity_create.sub_type,
            "is_archetype": entity_create.is_archetype,
            "description": entity_create.description,
            "properties": entity_create.properties,
            "state_tags": entity_create.state_tags,
            "archetype_id": str(entity_create.archetype_id) if entity_create.archetype_id else None,
            "authority": entity_create.authority.value,
            "canon_level": entity_create.canon_level.value,
            "confidence": entity_create.confidence,
            "detail_level": entity_create.detail_level.value,
        }

        raw = await self.call_tool(
            "neo4j_create_entity",
            {"params": params},
        )

        # Parse the response
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return dict(parsed)
                return {"id": str(entity_create.id) if entity_create.id else str(parsed)}
            except (json.JSONDecodeError, TypeError):
                return {"id": str(entity_create.id) if entity_create.id else "unknown"}
        if isinstance(raw, dict):
            return cast(dict[str, Any], dict(raw))
        return {"id": str(entity_create.id) if entity_create.id else "unknown"}

    # ------------------------------------------------------------------
    # Private evaluation pipeline
    # ------------------------------------------------------------------

    async def _evaluate_single(
        self,
        proposal: dict[str, Any],
        world_rules: str,
        protected_entities: str,
    ) -> CanonKeeperVerdict:
        """Run the four-phase pipeline for a single proposal."""
        proposal_id = proposal.get("proposal_id", "unknown")
        proposal_content = json.dumps(proposal.get("content", {}), default=str)
        proposal_summary = proposal.get("summary", "")

        # Phase 1 — policy gate (fast, no CoT)
        policy = self._policy_check(
            proposal_content=proposal_content,
            protected_entities=protected_entities,
            world_rules=world_rules,
        )
        if policy.violation_found.upper() == "YES":
            return CanonKeeperVerdict(
                proposal_id=proposal_id,
                decision=CanonKeeperDecision.REJECTED,
                reasoning=f"Policy violation: {policy.violation_detail}",
                canon_node_type=proposal.get("change_type", "unknown"),
                canon_properties={},
                decided_at=datetime.now(UTC),
            )

        # Phase 1.5 — contradiction detection (Temporal & Contradiction Gap)
        # Check if this proposal contradicts existing canon before proceeding
        contradiction_result = await self._check_contradiction(proposal)
        if contradiction_result and contradiction_result.critical_severity_count > 0:
            # Critical contradictions block the proposal
            contradictions_text = "\n".join(
                [f"- {m.explanation}" for m in contradiction_result.all_matches if m.severity.value == "critical"]
            )
            return CanonKeeperVerdict(
                proposal_id=proposal_id,
                decision=CanonKeeperDecision.REJECTED,
                reasoning=(
                    f"Critical contradiction(s) detected:\n{contradictions_text}\n\n"
                    "Resolve contradictions before committing."
                ),
                canon_node_type=proposal.get("change_type", "unknown"),
                canon_properties={},
                decided_at=datetime.now(UTC),
            )

        # Phase 2 — canon consistency reasoning (DSPy ChainOfThought)
        existing_canon = await self._fetch_related_canon(proposal)

        # Include contradiction warnings in the reasoning context if any
        contradiction_context = ""
        if contradiction_result and contradiction_result.high_severity_count > 0:
            contradiction_context = "\n\nWARNING: Contradictions detected:\n" + "\n".join(
                [
                    f"- {m.explanation} (severity: {m.severity.value})"
                    for m in contradiction_result.all_matches
                    if m.severity.value in ("high", "critical")
                ]
            )

        reasoning_result = self._reasoning(
            proposal_summary=proposal_summary,
            proposal_content=proposal_content,
            existing_canon=existing_canon,
            story_arcs="",  # future: fetch active arcs from Neo4j
        )

        # Phase 3 — final verdict via instructor (strict schema enforcement)
        verdict: CanonKeeperVerdict = await self.call_llm_structured(
            CanonKeeperVerdict,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Based on the following reasoning, issue a CanonKeeper verdict "
                        "for this proposed world-state change.\n\n"
                        f"Proposal ID: {proposal_id}\n"
                        f"Summary: {proposal_summary}\n"
                        f"Content: {proposal_content}\n\n"
                        f"Reasoning:\n{reasoning_result.reasoning}\n"
                        f"{contradiction_context}\n\n"
                        "Return a CanonKeeperVerdict with decision=ACCEPT or REJECT, "
                        "reasoning, canon_node_type, and canon_properties."
                    ),
                }
            ],
            max_tokens=1024,
        )
        return verdict

    # _commit_to_neo4j(), _audit_commit(), _AUDIT_SUBJECT, and
    # _last_commit_neo4j_id live in CommitDispatcherMixin (commit_dispatcher.py).

    # ------------------------------------------------------------------
    # Per-type commit handlers (called by CommitDispatcherMixin._commit_to_neo4j)
    # ------------------------------------------------------------------

    async def _commit_multiverse(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        await self.create_multiverse(payload)

    async def _commit_universe(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        await self.create_universe(payload)

    async def _commit_entity(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}

        # Canon-anchored visual identity edits (staged by the UI router) merge
        # into an EXISTING entity's properties — never the new-entity branch.
        if payload.get("operation") == "set_visual_identity":
            await self._commit_set_visual_identity(proposals_coll, proposal_id, payload)
            return

        # Social/profile updates are durable Mongo changes, not new Neo4j entities.
        profile_updates = dict(payload.get("profile_updates", {}) or {})
        if payload.get("field") and "new_value" in payload:
            profile_updates[str(payload["field"])] = payload.get("new_value")
        if payload.get("entity_id") and profile_updates:
            await self.call_tool(
                "mongodb_update_npc_profile",
                {
                    "entity_id": str(payload["entity_id"]),
                    "params": profile_updates,
                },
            )
            return

        entity_name = payload.get("name", "")
        if self._is_placeholder_name(entity_name):
            logger.warning(
                "Skipping entity proposal: placeholder name %r is not a real entity",
                entity_name,
            )
            return

        entity_type, sub_type = self._normalise_entity_type(payload, verdict)

        result_text = await self.call_tool(
            "neo4j_create_entity",
            {
                "params": {
                    "universe_id": proposal.get("universe_id") or "",
                    "name": payload.get("name", ""),
                    "entity_type": entity_type,
                    "sub_type": sub_type,
                    "description": payload.get("description", ""),
                    "is_archetype": payload.get("is_archetype", True),
                    "properties": payload.get("properties", {}),
                    "confidence": payload.get("confidence", 1.0),
                    "authority": "source",
                    "canon_level": payload.get("canon_level", "proposed"),
                }
            },
        )
        self._check_tool_error(result_text, "neo4j_create_entity")
        self._store_neo4j_id_on_proposal(proposals_coll, str(proposal_id), result_text)

    async def _commit_set_visual_identity(
        self,
        proposals_coll: Any,
        proposal_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Canonize a UI-staged visual identity onto an existing entity.

        Reads the current entity via the read-only ``neo4j_get_entity`` tool,
        merges the compact visual identity into ``properties["visual_identity"]``
        (preserving all unrelated properties), and writes through the
        CanonKeeper-authorized ``neo4j_update_entity`` tool. On success the
        staged identity version is marked ``approved`` with provenance back to
        the deciding proposal.
        """
        entity_id = str(payload.get("entity_id") or "")
        visual_identity = payload.get("visual_identity") or {}

        raw = await self.call_tool("neo4j_get_entity", {"entity_id": entity_id})
        self._check_tool_error(raw, "neo4j_get_entity")
        entity = self._parse_tool_result(raw)
        if not entity:
            raise RuntimeError(f"set_visual_identity: entity {entity_id} not found")

        properties = dict(entity.get("properties") or {})
        properties["visual_identity"] = visual_identity
        result_text = await self.call_tool(
            "neo4j_update_entity",
            {"entity_id": entity_id, "params": {"properties": properties}},
        )
        self._check_tool_error(result_text, "neo4j_update_entity")
        # Feed the audit/back-link path like every other commit branch: stash
        # the entity id for _audit_commit and link it back on the proposal doc.
        self._store_neo4j_id_on_proposal(proposals_coll, str(proposal_id), result_text)

        identity_id = visual_identity.get("identity_id")
        if identity_id:
            status_result = await self.call_tool(
                "mongodb_update_visual_identity_status",
                {
                    "identity_id": str(identity_id),
                    "status": "approved",
                    "decision_proposal_id": str(proposal_id) or None,
                },
            )
            self._check_tool_error(status_result, "mongodb_update_visual_identity_status")

    async def _record_visual_identity_rejection(
        self,
        proposal: dict[str, Any],
        verdict: CanonKeeperVerdict,
    ) -> None:
        """Store the decision reference on a rejected visual-identity version.

        The identity version stays draft; only the provenance back to the
        deciding proposal is persisted. No-op for any other proposal shape.
        """
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        if payload.get("operation") != "set_visual_identity":
            return
        visual_identity = payload.get("visual_identity") or {}
        identity_id = visual_identity.get("identity_id")
        if not identity_id:
            return
        decision_ref = str(verdict.proposal_id or proposal.get("proposal_id") or "") or None
        status_result = await self.call_tool(
            "mongodb_update_visual_identity_status",
            {
                "identity_id": str(identity_id),
                "status": "draft",
                "decision_proposal_id": decision_ref,
            },
        )
        self._check_tool_error(status_result, "mongodb_update_visual_identity_status")

    async def _commit_axiom(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("payload", {})
        canon_props = verdict.canon_properties or {}
        domain = payload.get("domain") or canon_props.get("domain", "general")
        result_text = await self.call_tool(
            "neo4j_create_axiom",
            {
                "params": {
                    "universe_id": proposal.get("universe_id") or "",
                    "statement": payload.get("statement") or canon_props.get("statement", ""),
                    "domain": domain,
                    "confidence": payload.get("confidence") or canon_props.get("confidence", 0.9),
                    "source_ref": payload.get("source_ref"),
                    "tags": payload.get("tags", []),
                    "canon_level": payload.get("canon_level", "proposed"),
                    # AxiomAuthority is a closed enum (physics/society/metaphysics/
                    # genre) — "source" (valid for entities) is NOT valid here and
                    # silently dropped every ingested/quick-world axiom. Derive a
                    # valid authority from the free-text domain instead.
                    "authority": _axiom_authority_for_domain(domain),
                    "source_ids": source_id_strs,
                }
            },
        )
        self._check_tool_error(result_text, "neo4j_create_axiom")
        self._store_neo4j_id_on_proposal(proposals_coll, str(proposal_id), result_text)

    async def _commit_update_agenda_clock(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        await self.call_tool(
            "neo4j_update_agenda_clock",
            {
                "agenda_id": str(payload.get("agenda_id")),
                "tick": int(payload.get("tick", 0)),
            },
        )

    async def _commit_create_agenda(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        await self.call_tool(
            "neo4j_create_agenda",
            {
                "params": {
                    "universe_id": str(proposal.get("universe_id")),
                    "owner_id": str(payload.get("owner_id")) if payload.get("owner_id") else None,
                    "title": payload.get("title"),
                    "description": payload.get("description"),
                    "agenda_type": payload.get("agenda_type"),
                    "status": payload.get("status", "active"),
                    "total_segments": payload.get("total_segments", 6),
                    "current_segments": payload.get("current_segments", 0),
                }
            },
        )

    async def _commit_spatial_topology(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        from_name = str(payload.get("from_location") or "").strip()
        to_name = str(payload.get("to_location") or "").strip()
        universe_id = proposal.get("universe_id") or ""

        if not from_name or not to_name:
            logger.warning("Skipping spatial_topology proposal: missing from_location or to_location")
            return

        # Resolve location names → Neo4j UUIDs. neo4j_create_relationship needs
        # from_entity_id/to_entity_id (UUIDs) and a category — the previous
        # payload passed bare names with rel_type CONNECTED_TO (not a valid
        # RelationshipType) and no category, so it always failed validation.
        from_id = await self._resolve_name_to_uuid(from_name, universe_id)
        to_id = await self._resolve_name_to_uuid(to_name, universe_id)
        if not from_id or not to_id:
            logger.warning(
                "Skipping spatial_topology '%s → %s': one or both locations not found in Neo4j",
                from_name,
                to_name,
            )
            return

        result_text = await self.call_tool(
            "neo4j_create_relationship",
            {
                "params": {
                    "from_entity_id": from_id,
                    "to_entity_id": to_id,
                    "rel_type": "RELATED_TO",
                    "category": "spatial",
                    "properties": {
                        "description": payload.get("description", ""),
                        "confidence": float(payload.get("confidence", 0.8)),
                        "connection_type": payload.get("connection_type", "adjacent"),
                        "spatial_scale": payload.get("scale", "local"),
                        "authority": "source",
                        "canon_level": "proposed",
                    },
                }
            },
        )
        self._check_tool_error(result_text, "neo4j_create_relationship")

    async def _commit_relationship(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("content", {}) or proposal.get("payload", {}) or {}
        if payload.get("from_entity_id") and payload.get("to_entity_id"):
            rel_type = str(payload.get("rel_type") or "KNOWS").strip().upper()
            rel_category = payload.get("category") or self._REL_CATEGORY_MAP.get(rel_type, "generic")
            rel_properties = dict(payload.get("properties", {}) or {})
            rel_properties.setdefault("confidence", proposal.get("confidence", 0.8))
            rel_properties.setdefault("authority", "canon")
            rel_properties.setdefault("canon_level", "proposed")

            result_text = await self.call_tool(
                "neo4j_create_relationship",
                {
                    "params": {
                        "from_entity_id": str(payload["from_entity_id"]),
                        "to_entity_id": str(payload["to_entity_id"]),
                        "rel_type": rel_type,
                        "category": rel_category,
                        "properties": rel_properties,
                    }
                },
            )
            self._check_tool_error(result_text, "neo4j_create_relationship")
            self._store_neo4j_id_on_proposal(proposals_coll, str(proposal_id), result_text)

            profile_updates = payload.get("profile_updates", {}) or {}
            if payload.get("from_entity_id") and profile_updates:
                await self.call_tool(
                    "mongodb_update_npc_profile",
                    {
                        "entity_id": str(payload["from_entity_id"]),
                        "params": profile_updates,
                    },
                )
        else:
            await self._commit_fact_branch(
                proposals_coll,
                proposal_id,
                proposal,
                source_id_strs,
                verdict.canon_properties,
            )

    async def _commit_fact(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        content = proposal.get("content", {}) or proposal.get("payload", {}) or {}
        if proposal.get("change_type") == "event" and ("start_time" in content or "operation" in content):
            # This is a temporal event (from UI or similar), not an occurrence fact
            operation = content.get("operation", "create")
            if operation == "create":
                from monitor_data.schemas.facts import EventCreate

                payload = dict(content)
                payload.pop("operation", None)
                create_params = EventCreate(**payload)
                result = await self.call_tool("neo4j_create_event", {"params": create_params.model_dump()})
                self._store_neo4j_id_on_proposal(
                    proposals_coll,
                    proposal_id,
                    result.get("id", ""),
                )
            elif operation == "update":
                from monitor_data.schemas.facts import EventUpdate

                payload = dict(content)
                payload.pop("operation", None)
                event_id = payload.pop("event_id")
                update_params = EventUpdate(**payload)
                result = await self.call_tool(
                    "neo4j_update_event",
                    {"event_id": event_id, "updates": update_params.model_dump(exclude_unset=True)},
                )
                self._store_neo4j_id_on_proposal(
                    proposals_coll,
                    proposal_id,
                    result.get("id", ""),
                )
            elif operation == "delete":
                event_id = content.get("event_id")
                force = content.get("force", False)
                await self.call_tool("neo4j_delete_event", {"event_id": event_id, "force": force})
            return

        await self._commit_fact_branch(
            proposals_coll,
            proposal_id,
            proposal,
            source_id_strs,
            verdict.canon_properties if hasattr(verdict, "canon_properties") else None,
        )

    async def _commit_entity_relationship(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        payload = proposal.get("payload", {})
        from_name = payload.get("from_entity", "").strip()
        to_name = payload.get("to_entity", "").strip()
        rel_type_str = payload.get("rel_type", "related_to").strip().lower()
        description = payload.get("description", "")
        confidence = float(payload.get("confidence", 0.8))
        universe_id = proposal.get("universe_id") or ""

        if not from_name and not to_name:
            logger.warning("Skipping entity_relationship proposal: missing from_entity or to_entity")
            return

        if self._is_placeholder_name(from_name) or self._is_placeholder_name(to_name):
            logger.warning(
                "Skipping entity_relationship '%s -> %s': placeholder entity name",
                from_name,
                to_name,
            )
            return

        neo4j_rel_type = self._REL_TYPE_MAP.get(rel_type_str, "RELATED_TO")
        rel_category = self._REL_CATEGORY_MAP.get(neo4j_rel_type, "generic")

        from_id = await self._resolve_name_to_uuid(from_name, universe_id)
        to_id = await self._resolve_name_to_uuid(to_name, universe_id)
        if not from_id or not to_id:
            logger.warning(
                "Skipping entity_relationship '%s → %s': one or both entities not found in Neo4j",
                from_name,
                to_name,
            )
            return

        result_text = await self.call_tool(
            "neo4j_create_relationship",
            {
                "params": {
                    "from_entity_id": from_id,
                    "to_entity_id": to_id,
                    "rel_type": neo4j_rel_type,
                    "category": rel_category,
                    "properties": {
                        "description": description,
                        "confidence": confidence,
                        "authority": "source",
                        "canon_level": "proposed",
                    },
                }
            },
        )
        self._check_tool_error(result_text, "neo4j_create_relationship")

    async def _commit_state_change(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        raw_state_props = verdict.canon_properties or proposal.get("payload", {}) or proposal.get("content", {})
        state_params = _normalise_state_tag_update(raw_state_props)

        if state_params.get("entity_id") and (state_params.get("add_tags") or state_params.get("remove_tags")):
            await self.call_tool(
                "neo4j_update_state_tags",
                {"params": state_params},
            )
        elif raw_state_props:
            await self.call_tool(
                "neo4j_update_state_tags",
                {"params": raw_state_props},
            )

        entity_id = raw_state_props.get("entity_id")
        profile_updates = raw_state_props.get("profile_updates", {}) or {}
        if entity_id and profile_updates:
            await self.call_tool(
                "mongodb_update_npc_profile",
                {"entity_id": str(entity_id), "params": profile_updates},
            )

    # ------------------------------------------------------------------
    # Commit helpers — extract reusable patterns from _commit_to_neo4j
    # ------------------------------------------------------------------

    def _normalise_entity_type(
        self,
        payload: dict[str, Any],
        verdict: CanonKeeperVerdict,
    ) -> tuple[str, str | None]:
        """Return (entity_type, sub_type) normalised from payload+verdict."""
        raw_type = (payload.get("entity_type") or verdict.canon_node_type or "concept").lower()
        entity_type = self._ENTITY_TYPE_MAP.get(raw_type)
        sub_type = payload.get("sub_type")
        if not entity_type:
            if not sub_type and raw_type not in ("entity", "concept"):
                sub_type = raw_type
            entity_type = "concept"
        return entity_type, sub_type

    def _store_neo4j_id_on_proposal(
        self,
        proposals_coll: Any,
        proposal_id: str,
        result_text: Any,
    ) -> None:
        """Parse JSON result and store Neo4j node UUID back on the proposal doc."""
        neo4j_id = self._parse_tool_result(result_text).get("id")
        if neo4j_id:
            # Stash for the audit trail — works even when the proposal lives
            # only in memory (e.g. World Architect) and not in MongoDB.
            self._last_commit_neo4j_id = str(neo4j_id)
            if proposal_id:
                proposals_coll.update_one(
                    {"proposal_id": proposal_id},
                    {"$set": {"neo4j_id": str(neo4j_id)}},
                )

    def _parse_tool_result(self, result: Any) -> dict[str, Any]:
        """Return a dict for parsed MCP tool output, tolerating raw JSON text."""
        if isinstance(result, dict):
            return result
        if isinstance(result, BaseModel):
            dumped = result.model_dump(mode="json")
            return dumped if isinstance(dumped, dict) else {}
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    async def _resolve_name_to_uuid(self, name: str, universe_id: str) -> str | None:
        """Resolve an entity name to its Neo4j UUID, or None if not found.

        Uses case-insensitive EXACT name match. Does not rely on the fuzzy
        fulltext index that ``neo4j_list_entities`` activates when a ``name``
        filter is supplied — a partial-token match there was resolving
        ``from_entity`` and ``to_entity`` of SUBTYPE_OF proposals to the
        same node, which Neo4j then rejected as a self-loop. Fetching all
        entities in the universe and matching in Python keeps the resolution
        deterministic at the cost of one extra round-trip per relationship.
        """
        if not name or not name.strip():
            return None
        target = name.strip().lower()
        result = await self.call_tool(
            "neo4j_list_entities",
            {"filters": {"universe_id": universe_id, "limit": 200}},
        )
        data = self._parse_tool_result(result)
        for entity in data.get("entities", []):
            if (entity.get("name") or "").strip().lower() == target:
                return entity["id"]
        return None

    def _store_runtime_ref_on_proposal(
        self,
        proposals_coll: Any,
        proposal_id: str,
        result_text: Any,
        ref_field: str,
        id_fields: tuple[str, ...],
    ) -> None:
        """Store a Mongo/runtime artifact UUID back on the proposal document."""
        if not proposal_id:
            return
        result = self._parse_tool_result(result_text)
        runtime_id = next((result.get(field) for field in id_fields if result.get(field)), None)
        if not runtime_id:
            return
        proposals_coll.update_one(
            {"proposal_id": proposal_id},
            {
                "$set": {
                    ref_field: str(runtime_id),
                    "runtime_activation_status": "active",
                }
            },
        )

    def _mark_runtime_activation_status(
        self,
        proposals_coll: Any,
        proposal_id: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        """Record non-fatal runtime activation state for accepted pack artifacts."""
        if not proposal_id:
            return
        update_doc: dict[str, Any] = {"runtime_activation_status": status}
        if reason:
            update_doc["runtime_activation_reason"] = reason
        proposals_coll.update_one({"proposal_id": proposal_id}, {"$set": update_doc})

    def _extract_pack_id_from_source(self, proposal: dict[str, Any]) -> str | None:
        """Return the source KnowledgePack UUID string, if the proposal came from one."""
        source = str(proposal.get("source") or "")
        prefix = "knowledge_pack:"
        if not source.startswith(prefix):
            return None
        pack_id = source[len(prefix) :].strip()
        try:
            UUID(pack_id)
        except (TypeError, ValueError):
            return None
        return pack_id

    def _normalise_random_table_type(self, table_type: Any) -> str:
        """Map extracted/free-form table categories onto RandomTableType values."""
        normalized = str(table_type or "custom").strip().lower().replace(" ", "_")
        return self._RANDOM_TABLE_TYPE_MAP.get(normalized, "custom")

    def _safe_dice_formula(self, dice_formula: Any) -> str:
        """Keep extracted dice formulas inside the RandomTableCreate contract."""
        formula = str(dice_formula or "1d100").strip()
        if not formula or len(formula) > 50:
            return "1d100"
        return formula

    async def _commit_random_table(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        """Create a runtime RandomTable from an accepted pack proposal."""
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        entries: list[dict[str, Any]] = []
        for entry in payload.get("entries", []) or []:
            value = str(entry.get("value") or "").strip()
            if not value:
                continue
            table_entry: dict[str, Any] = {
                "min_roll": int(entry.get("min_roll") or 1),
                "max_roll": int(entry.get("max_roll") or entry.get("min_roll") or 1),
                "value": value,
            }
            if entry.get("subtable_name"):
                table_entry["conditions"] = {"unresolved_subtable_name": entry["subtable_name"]}
            entries.append(table_entry)

        if not entries:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "skipped",
                "Random table proposal had no usable entries.",
            )
            return

        result_text = await self.call_tool(
            "mongodb_create_random_table",
            {
                "params": {
                    "universe_id": proposal.get("universe_id"),
                    "name": payload.get("name") or "Untitled Random Table",
                    "description": payload.get("description") or "",
                    "table_type": self._normalise_random_table_type(payload.get("table_type")),
                    "dice_formula": self._safe_dice_formula(payload.get("dice_formula")),
                    "weighted": False,
                    "entries": entries,
                }
            },
        )
        self._check_tool_error(result_text, "mongodb_create_random_table")
        self._store_runtime_ref_on_proposal(
            proposals_coll,
            proposal_id,
            result_text,
            "random_table_id",
            ("table_id", "id"),
        )

    async def _commit_tone_profile(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        """Create a runtime ToneProfile from an accepted pack proposal."""
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        instruction = str(payload.get("instruction") or payload.get("description") or "").strip()
        if not instruction:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "skipped",
                "Tone profile proposal had no instruction text.",
            )
            return

        trigger_tags = [str(tag).strip() for tag in payload.get("trigger_tags", []) or [] if str(tag).strip()]
        result_text = await self.call_tool(
            "mongodb_create_tone_profile",
            {
                "params": {
                    "name": payload.get("name") or "Untitled Tone Profile",
                    "description": payload.get("description") or "",
                    "instruction": instruction,
                    "trigger_tags": trigger_tags,
                    "category": payload.get("category") or "narrative",
                    "pack_id": self._extract_pack_id_from_source(proposal),
                    "is_builtin": False,
                    "example_output": payload.get("example_output"),
                }
            },
        )
        self._check_tool_error(result_text, "mongodb_create_tone_profile")
        self._store_runtime_ref_on_proposal(
            proposals_coll,
            proposal_id,
            result_text,
            "tone_profile_id",
            ("profile_id", "id"),
        )

    async def _commit_character_profile(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        """Attach an extracted character profile to the matching Neo4j entity."""
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        name = str(payload.get("name") or "").strip()
        if not name:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "skipped",
                "Character profile proposal had no name.",
            )
            return

        filters: dict[str, Any] = {"name": name, "limit": 1}
        if proposal.get("universe_id"):
            filters["universe_id"] = proposal.get("universe_id")
        entity_result = await self.call_tool("neo4j_list_entities", {"filters": filters})
        entities = self._parse_tool_result(entity_result).get("entities", [])
        if not entities:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "unresolved",
                f"No Neo4j entity found for character profile '{name}'.",
            )
            return

        entity_id = entities[0].get("id") or entities[0].get("entity_id")
        if not entity_id:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "unresolved",
                f"Matched entity for character profile '{name}' had no id.",
            )
            return

        profile_updates: dict[str, Any] = {}
        for field_name in (
            "traits",
            "values",
            "fears",
            "desires",
            "speech_style",
            "mannerisms",
        ):
            value = payload.get(field_name)
            if value not in (None, {}, []):
                profile_updates[field_name] = value
        if payload.get("source_ref"):
            profile_updates["gm_notes"] = f"Extracted from {payload['source_ref']}"

        if not profile_updates:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "skipped",
                f"Character profile '{name}' had no profile fields to apply.",
            )
            return

        result_text = await self.call_tool(
            "mongodb_update_npc_profile",
            {
                "entity_id": str(entity_id),
                "params": profile_updates,
            },
        )
        self._check_tool_error(result_text, "mongodb_update_npc_profile")
        self._store_runtime_ref_on_proposal(
            proposals_coll,
            proposal_id,
            result_text,
            "npc_profile_id",
            ("profile_id", "id"),
        )
        proposals_coll.update_one(
            {"proposal_id": proposal_id},
            {"$set": {"profile_entity_id": str(entity_id)}},
        )

    async def _commit_generation_template(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        """Create an EntityTemplate from an accepted NPC generation template."""
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        universe_id = proposal.get("universe_id")
        if not universe_id:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "unresolved",
                "Generation template proposals require a universe_id.",
            )
            return

        name = str(payload.get("name") or payload.get("archetype_name") or "").strip()
        if not name:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "skipped",
                "Generation template proposal had no name.",
            )
            return

        base_properties = {
            "archetype_name": payload.get("archetype_name"),
            "stat_block_name": payload.get("stat_block_name"),
            "profile_name": payload.get("profile_name"),
            "random_table_refs": payload.get("random_table_refs", []) or [],
            "tier_override": payload.get("tier_override"),
            "source_ref": payload.get("source_ref"),
            "confidence": payload.get("confidence"),
        }
        result_text = await self.call_tool(
            "mongodb_create_entity_template",
            {
                "params": {
                    "universe_id": universe_id,
                    "name": name,
                    "description": f"NPC generation template for {payload.get('archetype_name') or name}",
                    "entity_type": "character",
                    "base_properties": {
                        key: value for key, value in base_properties.items() if value not in (None, [], {})
                    },
                    "variable_properties": [
                        {
                            "property_path": "properties.random_table_refs",
                            "generation_type": "llm",
                            "llm_hint": (
                                "Use the named random tables when generating this NPC: "
                                + ", ".join(payload.get("random_table_refs", []) or [])
                            ),
                        }
                    ]
                    if payload.get("random_table_refs")
                    else [],
                    "naming_pattern": {"type": "llm"},
                    "default_state_tags": [],
                    "default_detail_level": _derive_detail_level(
                        payload.get("entity_type", "character"),
                        base_properties,
                        payload.get("random_table_refs"),
                    ),
                }
            },
        )
        self._check_tool_error(result_text, "mongodb_create_entity_template")
        self._store_runtime_ref_on_proposal(
            proposals_coll,
            proposal_id,
            result_text,
            "entity_template_id",
            ("template_id", "id"),
        )

    async def _commit_plot_thread(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: Any,
        verdict: CanonKeeperVerdict,
    ) -> None:
        """Create a PlotThread node in Neo4j from an accepted proposal."""
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        story_id = proposal.get("story_id")
        if not story_id:
            # Fallback: try to find an active story for the universe
            universe_id = proposal.get("universe_id")
            if universe_id:
                stories_json = await self.call_tool(
                    "neo4j_list_stories", {"universe_id": str(universe_id), "status": "active"}
                )
                stories_data = json.loads(stories_json)
                if stories_data.get("stories"):
                    story_id = stories_data["stories"][0]["story_id"]

        if not story_id:
            self._mark_runtime_activation_status(
                proposals_coll,
                proposal_id,
                "unresolved",
                "Plot thread proposals require a story_id or an active story in the universe.",
            )
            return

        result_text = await self.call_tool(
            "neo4j_create_plot_thread",
            {
                "params": {
                    "story_id": str(story_id),
                    "title": payload.get("title", "Untitled Thread"),
                    "thread_type": payload.get("category", "mystery"),
                    "status": "open",
                    "priority": payload.get("priority", "minor"),
                    "urgency": payload.get("urgency", "low"),
                    "entity_names": payload.get("entity_names", []),
                    "source_hint": payload.get("source_hint") or payload.get("source_ref"),
                }
            },
        )
        self._check_tool_error(result_text, "neo4j_create_plot_thread")
        self._store_runtime_ref_on_proposal(
            proposals_coll,
            proposal_id,
            result_text,
            "plot_thread_id",
            ("thread_id", "id"),
        )

    async def _commit_fact_branch(
        self,
        proposals_coll: Any,
        proposal_id: str,
        proposal: dict[str, Any],
        source_id_strs: list[str] | None,
        verdict_canon_properties: dict[str, Any] | None = None,
    ) -> None:
        """Shared logic for fact/event/lore_fact branches."""
        payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}
        # Coerce the LLM-supplied fact_type to a valid FactType enum value.
        # Extraction sometimes emits free-form types (e.g. 'lore', 'rule',
        # 'description') that neo4j_create_fact rejects, silently dropping facts.
        _VALID_FACT_TYPES = {"state", "relationship", "attribute", "occurrence"}
        _FACT_TYPE_ALIASES = {
            "lore": "state",
            "rule": "state",
            "description": "state",
            "fact": "state",
            "concept": "state",
            "trait": "attribute",
            "property": "attribute",
            "stat": "attribute",
            "event": "occurrence",
            "action": "occurrence",
            "relation": "relationship",
            "connection": "relationship",
        }
        raw_fact_type = str(payload.get("fact_type", "state") or "state").strip().lower()
        fact_type = (
            raw_fact_type if raw_fact_type in _VALID_FACT_TYPES else _FACT_TYPE_ALIASES.get(raw_fact_type, "state")
        )
        result_text = await self.call_tool(
            "neo4j_create_fact",
            {
                "params": {
                    "universe_id": proposal.get("universe_id") or "",
                    "statement": payload.get("statement") or (verdict_canon_properties or {}).get("statement", ""),
                    "fact_type": fact_type,
                    "canon_level": payload.get("canon_level", "proposed"),
                    "knowledge_scope": payload.get("knowledge_scope", "world"),
                    "confidence": payload.get("confidence", 0.8),
                    "authority": "source",
                    "source_ids": source_id_strs,
                    "time_ref": payload.get("time_ref") or proposal.get("time_ref"),
                }
            },
        )
        self._check_tool_error(result_text, "neo4j_create_fact")
        self._store_neo4j_id_on_proposal(proposals_coll, str(proposal_id), result_text)

    def _check_tool_error(self, result_text: str, tool_name: str) -> None:
        """Raise RuntimeError if the tool call returned an error string."""
        if isinstance(result_text, str) and (
            result_text.startswith("Error")
            or result_text.startswith("Authorization error")
            or result_text.startswith("Validation error")
        ):
            raise RuntimeError(f"{tool_name} failed: {result_text}")

    async def _record_verdict(self, scene_id: UUID, verdict: CanonKeeperVerdict) -> None:
        """Persist verdict to MongoDB for audit trail."""
        await self.call_tool(
            "mongodb_record_verdict",
            {
                "scene_id": str(scene_id),
                "proposal_id": str(verdict.proposal_id) if verdict.proposal_id else None,
                "decision": verdict.decision.value,
                "reasoning": verdict.reasoning,
                "decided_at": verdict.decided_at.isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # Context fetch helpers
    # ------------------------------------------------------------------

    async def _fetch_world_rules(self, scene_id: UUID) -> str:
        """Return world rules (content flags, tone) for the policy gate.

        NOTE: there is no dedicated ``neo4j_get_world_rules`` tool — that feature
        was never implemented. Calling a non-existent tool only produced
        ERROR-level log spam and a traceback, then fell back to this default
        anyway. Until per-scene content rules are persisted, return the default
        directly so the policy gate has a stable, non-failing baseline.
        """
        return "- No explicit content restrictions\n- Maintain internal consistency"

    async def _fetch_protected_entities(self, scene_id: UUID) -> str:
        """Return protected entity IDs (none by default).

        NOTE: ``neo4j_get_protected_entities`` is likewise unimplemented; see
        _fetch_world_rules. Return an empty list rather than calling a phantom
        tool that always errors and falls back here.
        """
        return "[]"

    async def _fetch_related_canon(self, proposal: dict[str, Any]) -> str:
        """Fetch existing canon relevant to the proposal for consistency check."""
        entity_names = proposal.get("entity_names", []) or proposal.get("payload", {}).get("entity_names", [])
        universe_id = proposal.get("universe_id", "")
        if not entity_names:
            return "{}"
        raw = await self.call_tool(
            "neo4j_get_entities_by_names",
            {"universe_id": universe_id, "names": entity_names},
        )
        return raw or "{}"

    async def _fetch_canon_facts(self, universe_id: UUID) -> list[dict[str, Any]]:
        """Fetch all canonical facts for a universe."""
        try:
            raw = await self.call_tool(
                "neo4j_list_facts",
                {"filters": {"universe_id": str(universe_id), "canon_level": "canon"}},
            )
            if isinstance(raw, str):
                return json.loads(raw)  # type: ignore[no-any-return]
            if isinstance(raw, list):
                return raw
            return []
        except Exception as e:
            logger.error(f"Error fetching canon facts: {e}")
            return []

    async def _fetch_canon_axioms(self, universe_id: UUID) -> list[Any]:
        """Fetch all canonical axioms for a universe."""
        try:
            raw = await self.call_tool(
                "neo4j_list_axioms",
                {"filters": {"universe_id": str(universe_id), "canon_level": "canon"}},
            )
            if isinstance(raw, str):
                return json.loads(raw)  # type: ignore[no-any-return]
            if isinstance(raw, list):
                return raw
            return []
        except Exception as e:
            logger.error(f"Error fetching canon axioms: {e}")
            return []

    async def _check_contradiction(
        self,
        proposal: dict[str, Any],
    ) -> Any | None:
        """
        Check if a proposal contradicts existing canon (Temporal & Contradiction Gap).

        This uses the DSPy-based ContradictionModule to detect semantic conflicts.

        Args:
            proposal: The proposal to check for contradictions.

        Returns:
            ContradictionResult if contradictions found, None otherwise.
        """
        import asyncio
        import json
        import traceback

        from monitor_data.schemas.contradiction import (
            ContradictionFact,
            ContradictionMatch,
            ContradictionResolution,
            ContradictionResult,
            ContradictionSeverity,
            ContradictionType,
        )

        from monitor_agents.canonkeeper.verification import ContradictionModule

        if isinstance(proposal, str):
            try:
                proposal = json.loads(proposal)
            except json.JSONDecodeError:
                proposal = {}

        # Get universe_id from proposal content or proposal itself
        content = proposal.get("content", {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = {}
        universe_id_str = content.get("universe_id") or proposal.get("universe_id")

        if not universe_id_str:
            logger.warning(f"Proposal {proposal.get('proposal_id')} has no universe_id, skipping contradiction check")
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.CANONKEEPER,
                category=RoleplayErrorCategory.CANONKEEPER_MISSING_UNIVERSE_ID,
                message=f"Proposal {proposal.get('proposal_id')} has no universe_id, skipping contradiction check",
                fatal=False,
            )
            return None

        proposal_id = proposal.get("proposal_id", "unknown")
        summary = proposal.get("summary", "")
        # Use statement for facts/axioms, otherwise fallback to summary
        new_fact_text = content.get("statement") or summary

        if not new_fact_text:
            return None

        try:
            universe_id = UUID(str(universe_id_str))

            # 1. Fetch context (facts and axioms)
            facts = await self._fetch_canon_facts(universe_id)
            axioms = await self._fetch_canon_axioms(universe_id)

            context_lines = []
            for ax in axioms:
                context_lines.append(f"Axiom: {ax.get('statement')}")
            for f in facts:
                context_lines.append(f"Fact: {f.get('statement')}")

            context = "\n".join(context_lines)

            # If no context, we can't check for contradictions
            if not context:
                return None

            # 2. Call ContradictionModule
            module = ContradictionModule()
            # Wrap sync DSPy call
            result = await asyncio.to_thread(module.forward, context=context, new_fact=new_fact_text)

            if result.get("has_contradiction"):
                explanation = result.get("explanation", "No explanation provided.")
                logger.info(f"Contradiction detected for proposal {proposal_id}: {explanation}")

                # 3. Construct ContradictionResult
                match = ContradictionMatch(
                    contradiction_id=f"contra:canonkeeper:{proposal_id}",
                    contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
                    severity=ContradictionSeverity.CRITICAL,
                    new_fact=ContradictionFact(statement=new_fact_text, fact_type=proposal.get("change_type", "fact")),
                    existing_fact=ContradictionFact(statement="Established canon", fact_type="canon"),
                    explanation=explanation,
                    recommended_resolution=ContradictionResolution.REVIEW,
                )

                res = ContradictionResult(
                    checked_against_universe=universe_id,
                    all_matches=[match],
                    total_contradictions=1,
                    critical_severity_count=1,
                )
                return res

            return None
        except Exception as e:
            # Silent failure risk addressed: Log with stack trace
            logger.error(f"Error checking contradictions for proposal {proposal_id}: {e}\n{traceback.format_exc()}")
            # Don't block the proposal on contradiction check errors
            return None

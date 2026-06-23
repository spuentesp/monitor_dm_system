"""
Quick-world builder — one seed → a small, playable universe.

The Emochi/SillyTavern-style on-ramp to the World Forge. A single structured
LLM call expands a seed idea into a premise, an axiom, a few entities with
wants, lore facts, an opening scene and a suggested PC; the result is committed
to the graph as canon via the same CanonKeeper path the lorebook ingestion
uses, so a quick world is indistinguishable from a hand-built one once made.

LAYER: 2 (agents)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

import anyio

logger = logging.getLogger(__name__)

# entity_type values the pack/graph accept; anything else is coerced to concept.
_VALID_ENTITY_TYPES = {"character", "location", "faction", "object", "organization", "concept"}


@dataclass
class QuickWorldResult:
    """Outcome of a quick-world build."""

    multiverse_id: UUID
    universe_id: UUID
    world_name: str
    world_description: str
    axiom: str
    opening_scene: str
    pc_concept: str
    entities: List[Dict[str, Any]] = field(default_factory=list)
    lore_facts: List[str] = field(default_factory=list)
    committed: int = 0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "multiverse_id": str(self.multiverse_id),
            "universe_id": str(self.universe_id),
            "world_name": self.world_name,
            "world_description": self.world_description,
            "axiom": self.axiom,
            "opening_scene": self.opening_scene,
            "pc_concept": self.pc_concept,
            "entities": self.entities,
            "lore_facts": self.lore_facts,
            "committed": self.committed,
            "errors": self.errors,
        }


def _coerce_json_list(raw: Any) -> List[Any]:
    """Parse an LLM JSON-list field defensively (handles code fences / junk)."""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return []
    text = raw.strip()
    if text.startswith("```"):
        # strip a ```json ... ``` fence
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    # find the outermost array if there's leading/trailing prose
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception:  # noqa: BLE001
        return []


class QuickWorldBuilder:
    """Generate and commit a small playable world from a seed."""

    async def build(
        self,
        *,
        seed: str,
        genre: str = "",
        tone: str = "",
        name: Optional[str] = None,
    ) -> QuickWorldResult:
        blueprint = await self._generate(seed=seed, genre=genre, tone=tone)

        world_name = (name or blueprint.get("world_name") or "Untitled World").strip()[:120]
        world_description = (blueprint.get("world_description") or "").strip()
        axiom = (blueprint.get("axiom") or "").strip()
        opening_scene = (blueprint.get("opening_scene") or "").strip()
        pc_concept = (blueprint.get("pc_concept") or "").strip()

        entities = self._clean_entities(_coerce_json_list(blueprint.get("entities_json")))
        lore_facts = [
            str(x).strip() for x in _coerce_json_list(blueprint.get("lore_json")) if str(x).strip()
        ][:6]

        mv_id, universe_id = await anyio.to_thread.run_sync(
            self._create_world, world_name, world_description, genre
        )

        committed, errors = await self._canonize(
            mv_id=mv_id,
            universe_id=universe_id,
            world_name=world_name,
            axiom=axiom,
            entities=entities,
            lore_facts=lore_facts,
        )

        return QuickWorldResult(
            multiverse_id=mv_id,
            universe_id=universe_id,
            world_name=world_name,
            world_description=world_description,
            axiom=axiom,
            opening_scene=opening_scene,
            pc_concept=pc_concept,
            entities=entities,
            lore_facts=lore_facts,
            committed=committed,
            errors=errors,
        )

    # ── generation ────────────────────────────────────────────

    async def _generate(self, *, seed: str, genre: str, tone: str) -> Dict[str, Any]:
        from monitor_agents.prompts.quick_world import QuickWorldModule

        module = QuickWorldModule()

        def _run() -> Any:
            return module(seed=seed, genre=genre, tone=tone)

        try:
            result = await anyio.to_thread.run_sync(_run)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Quick-world generation failed: %s", exc)
            raise RuntimeError(f"World generation failed: {exc}") from exc

        return {
            "world_name": getattr(result, "world_name", ""),
            "world_description": getattr(result, "world_description", ""),
            "axiom": getattr(result, "axiom", ""),
            "entities_json": getattr(result, "entities_json", "[]"),
            "lore_json": getattr(result, "lore_json", "[]"),
            "opening_scene": getattr(result, "opening_scene", ""),
            "pc_concept": getattr(result, "pc_concept", ""),
        }

    @staticmethod
    def _clean_entities(raw: List[Any]) -> List[Dict[str, Any]]:
        cleaned: List[Dict[str, Any]] = []
        for item in raw[:6]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            etype = str(item.get("type") or "character").strip().lower()
            if etype not in _VALID_ENTITY_TYPES:
                etype = "concept"
            tags = item.get("tags")
            tag_list = (
                [str(t).strip() for t in tags if str(t).strip()] if isinstance(tags, list) else []
            )
            cleaned.append(
                {
                    "name": name[:200],
                    "type": etype,
                    "description": str(item.get("description") or "").strip()[:1000],
                    "want": str(item.get("want") or "").strip()[:300],
                    "tags": tag_list[:8],
                }
            )
        return cleaned

    # ── persistence ───────────────────────────────────────────

    @staticmethod
    def _create_world(world_name: str, description: str, genre: str) -> tuple[UUID, UUID]:
        """Create a (non-template) multiverse + universe to hold the world."""
        from monitor_data.schemas.universe import (
            MultiverseCreate as DLMultiverseCreate,
            UniverseCreate as DLUniverseCreate,
        )
        from monitor_data.tools.neo4j_tools import (
            neo4j_create_multiverse,
            neo4j_create_universe,
            neo4j_ensure_omniverse,
        )
        from monitor_data.tools.mongodb_tools import mongodb_list_game_systems

        # Query MongoDB for "Mistlands Core" system ID
        systems_res = mongodb_list_game_systems(include_builtin=True, limit=50)
        mistlands_id = None
        for sys in getattr(systems_res, "systems", systems_res):
            if sys.name == "Mistlands Core":
                mistlands_id = sys.id
                break

        omni = neo4j_ensure_omniverse()
        mv = neo4j_create_multiverse(
            DLMultiverseCreate(
                omniverse_id=UUID(omni["omniverse_id"]),
                name=world_name,
                system_name="Mistlands Core",
                description=(description or f"Quick world: {world_name}")[:500],
                is_template=False,
                source_document_id=None,
                parent_multiverse_id=None,
            )
        )
        universe = neo4j_create_universe(
            DLUniverseCreate(
                multiverse_id=mv.id,
                name=world_name,
                description=(description or "")[:500] or None,
                genre=(genre or None),
                tone=None,
                tech_level=None,
                parent_universe_id=None,
                is_template=False,
                default_game_system_id=mistlands_id,
                default_system_source_type="generic_library" if mistlands_id else None,
                default_system_source_id=str(mistlands_id) if mistlands_id else None,
                default_system_name="Mistlands Core" if mistlands_id else None,
            )
        )
        return mv.id, universe.id

    async def _canonize(
        self,
        *,
        mv_id: UUID,
        universe_id: UUID,
        world_name: str,
        axiom: str,
        entities: List[Dict[str, Any]],
        lore_facts: List[str],
    ) -> tuple[int, List[str]]:
        """Build a KnowledgePack from the blueprint and commit it as canon."""
        from monitor_agents.canonkeeper import CanonKeeper
        from monitor_data.schemas.knowledge_packs import (
            ExtractedAxiom,
            ExtractedEntityArchetype,
            ExtractedLoreFact,
            KnowledgePackCreate,
            KnowledgePackStatus,
            KnowledgePackType,
        )
        from monitor_data.tools.mongodb_tools import mongodb_create_knowledge_pack

        entity_archetypes = [
            ExtractedEntityArchetype(
                name=e["name"],
                entity_type=e["type"],
                description=e["description"],
                properties={"want": e["want"]} if e.get("want") else {},
                tags=e.get("tags", []),
                source_ref="quick-world",
            )
            for e in entities
        ]
        lore = [
            ExtractedLoreFact(statement=stmt[:1000], source_ref="quick-world")
            for stmt in lore_facts
        ]
        axioms = [ExtractedAxiom(statement=axiom[:500], source_ref="quick-world")] if axiom else []

        def _make_pack() -> Any:
            return mongodb_create_knowledge_pack(
                KnowledgePackCreate(
                    name=f"{world_name} — Quick World",
                    description="Generated from a seed via Forge Quick Start.",
                    pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
                    status=KnowledgePackStatus.READY,
                    entity_archetypes=entity_archetypes,
                    lore_facts=lore,
                    axioms=axioms,
                    ingestion_job_id=None,
                )
            )

        try:
            pack = await anyio.to_thread.run_sync(_make_pack)
        except Exception as exc:  # noqa: BLE001
            return 0, [f"Could not create content pack: {exc}"]

        try:
            keeper = CanonKeeper()
            result = await keeper.apply_pack_to_universe(
                pack_id=pack.id,
                multiverse_id=mv_id,
                universe_id=universe_id,
                auto_accept=True,
            )
            return int(result.get("committed", 0)), list(result.get("errors", []))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Quick-world canonization failed: %s", exc)
            return 0, [f"Canonization failed: {exc}"]

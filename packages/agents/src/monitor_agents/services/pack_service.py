"""
Knowledge Pack Service — Extracts pack merging, conflict detection, and application logic.

LAYER: 2 (agents)
"""

from typing import Any
from collections.abc import Hashable, Callable
from uuid import UUID
import json
from contextlib import suppress

from monitor_data.schemas.knowledge_packs import KnowledgePackResponse, KnowledgePackStatus, KnowledgePackCreate
from monitor_data.schemas.universe import UniverseFilter
from monitor_data.schemas.entities import EntityFilter
from monitor_data.schemas.facts import AxiomFilter, FactFilter
from monitor_data.tools.mongodb_tools import mongodb_get_knowledge_pack, mongodb_create_knowledge_pack
from monitor_data.tools.neo4j_tools import (
    neo4j_list_universes,
    neo4j_list_entities,
    neo4j_list_axioms,
    neo4j_list_facts,
    neo4j_update_universe,
)
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_data.tools.ingest_tools.contradiction_detection import detect_contradictions


class KnowledgePackService:
    """Service handling Knowledge Pack operations, specifically application to Universes."""

    @staticmethod
    def _norm_key(value: str | None) -> str:
        return (value or "").lower().strip()

    @staticmethod
    def _enum_str(value: Any) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _subset_indices(total: int, indices: list[int]) -> list[int]:
        if not indices:
            return list(range(total))
        return [i for i in indices if 0 <= i < total]

    @staticmethod
    def _pack_conflict_dict(
        item_type: str,
        item_name: str,
        pack_value: Any,
        world_value: Any,
    ) -> dict[str, Any]:
        return {
            "item_type": item_type,
            "item_name": item_name,
            "pack_value": pack_value,
            "world_value": world_value,
            "resolution": None,
            "resolved_value": None,
            "llm_suggestion": None,
            "resolved_by": None,
            "auto_committed": False,
        }

    @staticmethod
    def _propagate_system_to_universe(pack: Any, universe_id: UUID) -> None:
        """Best-effort: bind the universe to the pack's authoritative rules source."""
        if not universe_id:
            return

        gsid = getattr(pack, "game_system_id", None)
        embedded = getattr(pack, "game_system_data", None)
        system_name = getattr(embedded, "name", None) or getattr(pack, "system_name", None) or getattr(pack, "name", None)
        pack_source_id = getattr(pack, "id", None) or getattr(pack, "pack_id", None)

        update_kwargs: dict[str, object] = {
            "default_system_name": system_name,
        }
        if gsid:
            update_kwargs["default_game_system_id"] = gsid

        if embedded is not None:
            update_kwargs["default_system_source_type"] = "pack_embedded"
            if pack_source_id:
                update_kwargs["default_system_source_id"] = str(pack_source_id)
        elif gsid:
            update_kwargs["default_system_source_type"] = "generic_library"
            update_kwargs["default_system_source_id"] = str(gsid)
        else:
            return

        try:
            from monitor_data.schemas.universe import UniverseUpdate as DLUniverseUpdate
            neo4j_update_universe(universe_id, DLUniverseUpdate(**update_kwargs))
        except Exception:
            pass

    @staticmethod
    def _detect_pack_world_conflicts(
        pack: KnowledgePackResponse,
        universe_uid: UUID,
        mv_id: UUID,
        entity_idx: list[int],
        axiom_idx: list[int],
        lore_idx: list[int],
    ) -> tuple[list[dict[str, Any]], dict[str, set[int]]]:
        conflicts: list[dict[str, Any]] = []
        conflicting: dict[str, set[int]] = {"entity": set(), "axiom": set(), "lore": set()}

        # --- Entities ---
        world_entities = neo4j_list_entities(EntityFilter(universe_id=universe_uid, limit=1000)).entities
        world_by_name = {KnowledgePackService._norm_key(e.name): e for e in world_entities}
        for i in entity_idx:
            entity = pack.entity_archetypes[i]
            world = world_by_name.get(KnowledgePackService._norm_key(entity.name))
            if world is None:
                continue
            same_content = (
                KnowledgePackService._norm_key(world.description) == KnowledgePackService._norm_key(entity.description)
                and KnowledgePackService._enum_str(world.entity_type) == entity.entity_type
                and (world.sub_type or None) == (entity.sub_type or None)
            )
            if same_content:
                continue
            conflicts.append(
                KnowledgePackService._pack_conflict_dict(
                    "entity",
                    entity.name,
                    pack_value=entity.model_dump(mode="json"),
                    world_value={
                        "name": world.name,
                        "entity_type": KnowledgePackService._enum_str(world.entity_type),
                        "sub_type": world.sub_type,
                        "description": world.description,
                    },
                )
            )
            conflicting["entity"].add(i)

        # --- Axioms & lore ---
        canon_axioms = [
            {
                "statement": a.statement,
                "source_ref": a.source_ref,
                "canon_level": KnowledgePackService._enum_str(a.canon_level),
                "confidence": a.confidence,
            }
            for a in neo4j_list_axioms(AxiomFilter(universe_id=universe_uid, limit=200))
        ]
        canon_facts = [
            {
                "statement": f.statement,
                "source_ref": None,
                "canon_level": KnowledgePackService._enum_str(f.canon_level),
                "confidence": f.confidence,
            }
            for f in neo4j_list_facts(FactFilter(universe_id=universe_uid, limit=100))
        ]

        selected_axioms = [pack.axioms[i] for i in axiom_idx]
        selected_lore = [pack.lore_facts[i] for i in lore_idx]
        if (selected_axioms and canon_axioms) or (selected_lore and canon_facts):
            view = pack.model_copy(
                update={
                    "axioms": selected_axioms,
                    "lore_facts": selected_lore,
                    "entity_archetypes": [],
                }
            )
            result = detect_contradictions(
                new_pack=view,
                canon_axioms=canon_axioms,
                canon_facts=canon_facts,
                multiverse_id=mv_id,
                universe_id=universe_uid,
            )
            for match in result.axiom_contradictions:
                orig_idx = axiom_idx[match.item_index]
                conflicts.append(
                    KnowledgePackService._pack_conflict_dict(
                        "axiom",
                        match.new_fact.statement,
                        pack_value=selected_axioms[match.item_index].model_dump(mode="json"),
                        world_value={
                            "statement": match.existing_fact.statement,
                            "canon_level": match.existing_fact.canon_level,
                        },
                    )
                )
                conflicting["axiom"].add(orig_idx)
            for match in result.lore_contradictions:
                orig_idx = lore_idx[match.item_index]
                conflicts.append(
                    KnowledgePackService._pack_conflict_dict(
                        "lore",
                        match.new_fact.statement,
                        pack_value=selected_lore[match.item_index].model_dump(mode="json"),
                        world_value={
                            "statement": match.existing_fact.statement,
                            "canon_level": match.existing_fact.canon_level,
                        },
                    )
                )
                conflicting["lore"].add(orig_idx)

        return conflicts, conflicting

    @staticmethod
    def _conflict_key_index(pack: KnowledgePackResponse) -> dict[tuple[str, str], int]:
        index: dict[tuple[str, str], int] = {}
        for i, entity in enumerate(pack.entity_archetypes):
            index.setdefault(("entity", KnowledgePackService._norm_key(entity.name)), i)
        for i, axiom in enumerate(pack.axioms):
            index.setdefault(("axiom", KnowledgePackService._norm_key(axiom.statement)), i)
        for i, fact in enumerate(pack.lore_facts):
            index.setdefault(("lore", KnowledgePackService._norm_key(fact.statement)), i)
        return index

    @staticmethod
    def _human_picked_override(item_type: str, resolved_value: Any) -> dict[str, Any]:
        if item_type == "entity":
            if isinstance(resolved_value, str):
                with suppress(ValueError):
                    parsed = json.loads(resolved_value)
                    if isinstance(parsed, dict):
                        allowed = {"name", "description", "entity_type", "sub_type", "properties", "tags"}
                        return {k: v for k, v in parsed.items() if k in allowed}
            return {"description": str(resolved_value)}
        return {"statement": str(resolved_value)}

    @classmethod
    async def apply_pack_to_existing_world(
        cls,
        pack_uid: UUID,
        universe_uid: UUID,
        resolved_conflicts: list[dict[str, Any]],
        entity_indices: list[int],
        axiom_indices: list[int],
        lore_indices: list[int],
    ) -> dict[str, Any]:
        """Core logic for applying a pack to a universe, handling both conflict detection and resolution."""
        pack = mongodb_get_knowledge_pack(pack_uid)
        if not pack:
            raise ValueError("KnowledgePack not found")
            
        if pack.status == KnowledgePackStatus.ARCHIVED:
            raise ValueError("Cannot apply an archived pack")
            
        if pack.status == KnowledgePackStatus.PENDING:
            raise ValueError(f"KnowledgePack '{pack.name}' is still being built.")

        universes = neo4j_list_universes(UniverseFilter(limit=500))
        mv_id = next(
            (universe.multiverse_id for universe in universes if str(universe.id) == str(universe_uid)),
            None,
        )
        if mv_id is None:
            raise ValueError("Universe not found in the graph")

        if resolved_conflicts:
            # Phase 2: Resolve conflicts
            key_to_index = cls._conflict_key_index(pack)
            apply_indices: dict[str, list[int]] = {"entity": [], "axiom": [], "lore": []}
            overrides: dict[str, dict[str, Any]] = {}
            notes: list[str] = []
            counts = {"pack_wins": 0, "world_wins": 0, "llm_merged": 0, "human_picked": 0}

            for entry in resolved_conflicts:
                item_type = str(entry.get("item_type", ""))
                item_name = str(entry.get("item_name", ""))
                resolution = str(entry.get("resolution") or "world_wins")
                idx = key_to_index.get((item_type, cls._norm_key(item_name)))
                if idx is None:
                    notes.append(f"Skipped unknown conflict {item_type}:{item_name[:60]}")
                    continue
                if resolution == "pack_wins":
                    apply_indices[item_type].append(idx)
                    counts["pack_wins"] += 1
                elif resolution == "human_picked":
                    apply_indices[item_type].append(idx)
                    overrides[f"{item_type}:{idx}"] = cls._human_picked_override(item_type, entry.get("resolved_value"))
                    counts["human_picked"] += 1
                elif resolution == "llm_merged":
                    counts["llm_merged"] += 1
                    notes.append(f"llm_merged is not supported yet — kept world value for {item_type}:{item_name[:60]}")
                else:
                    counts["world_wins"] += 1

            result: dict[str, Any] = {"proposals_created": 0, "errors": [], "review_status": "pending"}
            if any(apply_indices.values()):
                keeper = CanonKeeper()
                result = await keeper.apply_pack_to_universe(
                    pack_id=pack_uid,
                    multiverse_id=mv_id,
                    universe_id=universe_uid,
                    auto_accept=False,
                    request_overrides={
                        "entity_indices": apply_indices["entity"],
                        "axiom_indices": apply_indices["axiom"],
                        "lore_indices": apply_indices["lore"],
                        "item_overrides": overrides,
                        "apply_relationships": False,
                        "apply_random_tables": False,
                        "apply_agendas": False,
                        "apply_topologies": False,
                        "apply_tone_profiles": False,
                        "apply_character_profiles": False,
                        "apply_generation_templates": False,
                        "apply_plot_threads": False,
                    },
                )

            cls._propagate_system_to_universe(pack, universe_uid)
            return {
                "status": "review_pending",
                "proposals_created": result["proposals_created"],
                "review_status": result.get("review_status", "pending"),
                "errors": result["errors"],
                "resolutions_applied": counts,
                "notes": notes,
            }

        # Phase 1: Detect Conflicts
        e_idx = cls._subset_indices(len(pack.entity_archetypes), entity_indices)
        a_idx = cls._subset_indices(len(pack.axioms), axiom_indices)
        l_idx = cls._subset_indices(len(pack.lore_facts), lore_indices)

        conflicts, conflicting = cls._detect_pack_world_conflicts(
            pack, universe_uid, mv_id, e_idx, a_idx, l_idx
        )
        request_overrides = None
        if conflicts or entity_indices or axiom_indices or lore_indices:
            request_overrides = {
                "entity_indices": [i for i in e_idx if i not in conflicting["entity"]],
                "axiom_indices": [i for i in a_idx if i not in conflicting["axiom"]],
                "lore_indices": [i for i in l_idx if i not in conflicting["lore"]],
            }
            
        keeper = CanonKeeper()
        result = await keeper.apply_pack_to_universe(
            pack_id=pack_uid,
            multiverse_id=mv_id,
            universe_id=universe_uid,
            auto_accept=False,
            request_overrides=request_overrides,
        )

        cls._propagate_system_to_universe(pack, universe_uid)

        return {
            "status": "conflicts_detected" if conflicts else "review_pending",
            "conflicts": conflicts,
            "proposals_created": result["proposals_created"],
            "review_status": result.get("review_status", "pending"),
            "errors": result["errors"],
            "pack_id": str(pack_uid),
            "universe_id": str(universe_uid),
        }

    @staticmethod
    def _deduplicate_by_key(
        packs: list[KnowledgePackResponse],
        attr: str,
        key_fn: Callable[[Any], Hashable],
        strategy: str = "first_wins",
        desc_len_fn: Callable[[Any], int] | None = None,
    ) -> dict[Hashable, Any]:
        """
        Merge lists of KnowledgePack items (e.g. axioms, entities), avoiding duplicates.
        """
        seen: dict[Hashable, Any] = {}
        for pack in packs:
            for item in getattr(pack, attr, None) or []:
                key = key_fn(item)
                if key not in seen:
                    seen[key] = item
                elif strategy == "longest_description" and desc_len_fn is not None:
                    if desc_len_fn(item) > desc_len_fn(seen[key]):
                        seen[key] = item
        return seen

    @classmethod
    def merge_packs(
        cls,
        pack_uids: list[UUID],
        strategy: str = "first_wins",
        merged_name: str | None = None,
    ) -> KnowledgePackResponse:
        """Merge multiple KnowledgePacks into a new deduplicated pack."""
        if len(pack_uids) < 2:
            raise ValueError("At least 2 pack_ids required for merge")

        raw_packs = [mongodb_get_knowledge_pack(uid) for uid in pack_uids]
        if not all(raw_packs):
            raise ValueError("One or more knowledge packs could not be found.")
        packs: list[KnowledgePackResponse] = [p for p in raw_packs if p is not None]

        first = packs[0]

        # --- deduplicate using generic helper ---
        seen_entities = cls._deduplicate_by_key(
            packs,
            attr="entity_archetypes",
            key_fn=lambda e: e.name.lower().strip(),
            strategy=strategy,
            desc_len_fn=lambda e: len(e.description),
        )
        seen_axioms = cls._deduplicate_by_key(
            packs,
            attr="axioms",
            key_fn=lambda a: a.statement.lower().strip(),
        )
        seen_lore = cls._deduplicate_by_key(
            packs,
            attr="lore_facts",
            key_fn=lambda f: f.statement.lower().strip(),
        )
        seen_rels = cls._deduplicate_by_key(
            packs,
            attr="entity_relationships",
            key_fn=lambda r: (
                r.from_entity.lower().strip(),
                r.rel_type.lower().strip(),
                r.to_entity.lower().strip(),
            ),
        )
        seen_tables = cls._deduplicate_by_key(
            packs,
            attr="random_tables",
            key_fn=lambda t: t.name.lower().strip(),
        )
        seen_agendas = cls._deduplicate_by_key(
            packs,
            attr="agendas",
            key_fn=lambda a: a.title.lower().strip(),
        )
        seen_topologies = cls._deduplicate_by_key(
            packs,
            attr="topologies",
            key_fn=lambda t: (
                t.from_location.lower().strip(),
                t.to_location.lower().strip(),
                t.connection_type.lower().strip(),
            ),
        )
        seen_tones = cls._deduplicate_by_key(
            packs,
            attr="tone_profiles",
            key_fn=lambda t: t.name.lower().strip(),
        )
        seen_character_profiles = cls._deduplicate_by_key(
            packs,
            attr="character_profiles",
            key_fn=lambda p: p.name.lower().strip(),
        )
        seen_generation_templates = cls._deduplicate_by_key(
            packs,
            attr="generation_templates",
            key_fn=lambda g: g.name.lower().strip(),
        )
        seen_plot_threads: dict[Hashable, Any] = cls._deduplicate_by_key(
            packs,
            attr="plot_threads",
            key_fn=lambda t: t.title.lower().strip(),
        )

        system_names = [pack.system_name for pack in packs if pack.system_name]
        merged_system = system_names[0] if system_names else None
        game_system_ids = [pack.game_system_id for pack in packs if pack.game_system_id]
        merged_gsid = game_system_ids[0] if game_system_ids else None
        source_doc_ids = []
        for pack in packs:
            for document_id in pack.source_document_ids:
                if document_id not in source_doc_ids:
                    source_doc_ids.append(document_id)
        
        final_name = merged_name or f"{first.name} (merged)"

        new_pack = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name=final_name,
                description=f"Merged from {len(packs)} packs: " + ", ".join(pack.name for pack in packs),
                pack_type=first.pack_type,
                status=KnowledgePackStatus.READY,
                system_name=merged_system,
                source_document_ids=source_doc_ids,
                ingestion_job_id=None,
                tags=["merged"],
                axioms=list(seen_axioms.values()),
                entity_archetypes=list(seen_entities.values()),
                lore_facts=list(seen_lore.values()),
                entity_relationships=list(seen_rels.values()),
                random_tables=list(seen_tables.values()),
                agendas=list(seen_agendas.values()),
                topologies=list(seen_topologies.values()),
                tone_profiles=list(seen_tones.values()),
                character_profiles=list(seen_character_profiles.values()),
                generation_templates=list(seen_generation_templates.values()),
                plot_threads=list(seen_plot_threads.values()),
                game_system_id=merged_gsid,
            )
        )

        return new_pack

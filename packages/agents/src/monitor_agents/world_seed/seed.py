"""WorldSeed — the starting-situation agent (Phase 2 guided start).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents (same layer), dspy.

Given a universe, WorldSeed returns 2-4 concrete start options grounded in
what the universe holds: entities, lore facts, agendas, plot threads, pack
character_profiles and topologies. When the universe is sparse, the reused
Quick World signature synthesizes grounding material first and the result
is marked generated.

Public surface:

    seed = WorldSeed()
    result = await seed.generate_start_options(universe_id=..., ...)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from uuid import UUID

from monitor_agents.base import BaseAgent
from monitor_agents.world_seed.gather import gather_universe_material
from monitor_agents.world_seed.models import (
    StartOption,
    StartOptionNPC,
    StartOptionThread,
    UniverseMaterial,
    WorldSeedResult,
)

logger = logging.getLogger(__name__)

MIN_OPTIONS = 2
MAX_OPTIONS = 4
MIN_NPCS = 2
MAX_NPCS = 4
MIN_THREADS = 2
MAX_THREADS = 3


def _coerce_json_list(raw: Any) -> list[Any]:
    """Parse an LLM JSON-list field defensively (handles code fences / junk)."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:80] or "option"


class WorldSeed(BaseAgent):
    """Build a starting situation for a universe: 2-4 grounded start options."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(agent_type="WorldSeed", agent_id="world-seed-1", model=model)

    async def run(self) -> None:
        """BaseAgent contract — WorldSeed is driven by generate_start_options."""

    async def generate_start_options(
        self,
        *,
        universe_id: str | UUID,
        pack_ids: list[str] | None = None,
        system_name: str | None = None,
        tone: str | None = None,
    ) -> WorldSeedResult:
        """Return the start options for one universe.

        Options are drawn from what the universe holds; when it is sparse the
        Quick World signature synthesizes material first and every option is
        marked generated.
        """
        material = await gather_universe_material(universe_id, pack_ids=pack_ids)
        generated = material.is_sparse()
        if generated:
            await self._expand_sparse(material)

        options = await self._compose_options(
            material,
            generated=generated,
            system_name=system_name or material.system_name,
            tone=tone or material.tone,
        )
        return WorldSeedResult(
            universe_id=str(universe_id),
            options=options,
            source="generated" if generated else "canon",
            material_digest=material.digest()[:2000],
        )

    # ── sparse-universe expansion (reuses the Quick World signature) ──

    async def _expand_sparse(self, material: UniverseMaterial) -> None:
        """Synthesize grounding material for a sparse universe.

        Reuses QuickWorldModule rather than a second generator. Best-effort:
        if generation fails the universe stays sparse and the fallback
        composition runs instead of the LLM composition.
        """
        seed = material.description.strip() or material.universe_name.strip() or "an untold world"
        try:
            from monitor_agents.quick_world.quick_world import QuickWorldModule

            def _run() -> Any:
                return QuickWorldModule()(seed=seed, genre=material.genre or "", tone=material.tone or "")

            blueprint = await asyncio.to_thread(_run)
        except Exception as exc:  # noqa: BLE001  # reason: a failed expansion degrades to sparse fallback, never a failed session (in _expand_sparse)
            logger.warning("world_seed: sparse expansion failed: %s", exc)
            return

        entities = _coerce_json_list(getattr(blueprint, "entities_json", "[]"))
        for item in entities[:8]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()[:200]
            if not name:
                continue
            entry = {
                "name": name,
                "description": str(item.get("description") or "").strip()[:500],
                "want": str(item.get("want") or "").strip()[:300],
            }
            etype = str(item.get("type") or "character").strip().lower()
            if etype == "location":
                material.locations.append({"name": name, "description": entry["description"]})
            elif etype in {"faction", "organization"}:
                material.factions.append({"name": name, "description": entry["description"]})
            else:
                material.characters.append(entry)

        for stmt in _coerce_json_list(getattr(blueprint, "lore_json", "[]")):
            text = str(stmt).strip()[:500]
            if text:
                material.facts.append(text)

        opening = str(getattr(blueprint, "opening_scene", "") or "").strip()
        if opening:
            material.plot_threads.append(
                {
                    "title": "The opening situation",
                    "description": opening[:500],
                    "category": "world_event",
                    "urgency": "high",
                }
            )
        pc_concept = str(getattr(blueprint, "pc_concept", "") or "").strip()
        if pc_concept and not material.description:
            material.description = str(getattr(blueprint, "world_description", "") or "").strip()[:1000]

        # Carry the generated opening/PC-concept into the composition hints.
        material.character_profiles.append({"name": "__pc_concept__", "summary": pc_concept[:300]})

    # ── option composition ────────────────────────────────────────────

    async def _compose_options(
        self,
        material: UniverseMaterial,
        *,
        generated: bool,
        system_name: str | None,
        tone: str | None,
    ) -> list[StartOption]:
        try:
            options = await self._compose_with_model(material, system_name=system_name, tone=tone)
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades to deterministic composition (in _compose_options)
            logger.warning("world_seed: option composition LLM failed: %s", exc)
            options = []
        if not options:
            options = self._compose_fallback(material)
        return self._normalize_options(options, material, generated=generated)

    async def _compose_with_model(
        self,
        material: UniverseMaterial,
        *,
        system_name: str | None,
        tone: str | None,
    ) -> list[StartOption]:
        from monitor_agents.world_seed.signatures import StartOptionsModule

        module = StartOptionsModule()

        def _run() -> Any:
            return module.forward(
                world_material=material.digest() or "(the universe is empty — invent a small, sharp setting)",
                system_name=system_name or material.universe_name or "Unknown setting",
                tone=tone or "dramatic",
                min_options=MIN_OPTIONS,
                max_options=MAX_OPTIONS,
            )

        prediction = await asyncio.to_thread(_run)
        raw = _coerce_json_list(getattr(prediction, "options_json", "[]"))
        options: list[StartOption] = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()[:200]
            location = str(item.get("location") or "").strip()[:200]
            if not title and not location:
                continue
            npcs = [
                StartOptionNPC(
                    name=str(npc.get("name") or "").strip()[:200],
                    description=str(npc.get("description") or "").strip()[:1000],
                    want=str(npc.get("want") or "").strip()[:300],
                )
                for npc in item.get("npcs") or []
                if isinstance(npc, dict) and str(npc.get("name") or "").strip()
            ]
            threads = [
                StartOptionThread(
                    title=str(thread.get("title") or "").strip()[:300],
                    description=str(thread.get("description") or "").strip()[:2000],
                    category=str(thread.get("category") or "mystery").strip().lower()[:50],
                    urgency=str(thread.get("urgency") or "medium").strip().lower()[:20],
                )
                for thread in item.get("threads") or []
                if isinstance(thread, dict) and str(thread.get("title") or "").strip()
            ]
            options.append(
                StartOption(
                    option_id=_slugify(title or location) + f"-{idx + 1}",
                    title=title or location,
                    summary=str(item.get("summary") or "").strip()[:500],
                    location=location
                    or (material.locations[0]["name"] if material.locations else "the starting place"),
                    location_description=str(item.get("location_description") or "").strip()[:1000],
                    npcs=npcs,
                    hook=str(item.get("hook") or "").strip()[:500],
                    player_role=str(item.get("player_role") or "").strip()[:300],
                    threads=threads,
                )
            )
        return options

    def _compose_fallback(self, material: UniverseMaterial) -> list[StartOption]:
        """Deterministic composition when the LLM is unavailable.

        Not a heuristic judge — it only assembles whatever the universe (or
        the synthesized expansion) actually holds, in a fixed order.
        """
        options: list[StartOption] = []
        pc_hint = ""
        for profile in material.character_profiles:
            if profile.get("name") == "__pc_concept__":
                pc_hint = profile.get("summary", "")
        locations = material.locations or [{"name": "the starting place", "description": ""}]
        for idx, location in enumerate(locations[:MAX_OPTIONS]):
            npcs = [
                StartOptionNPC(name=c["name"], description=c.get("description", ""), want=c.get("want", ""))
                for c in material.characters
                if c.get("name")
            ][:MAX_NPCS]
            threads = [
                StartOptionThread(
                    title=t["title"],
                    description=t.get("description", ""),
                    category=t.get("category", "mystery"),
                    urgency=t.get("urgency", "medium"),
                )
                for t in material.plot_threads
                if t.get("title")
            ][:MAX_THREADS]
            if not threads and material.agendas:
                threads = [
                    StartOptionThread(title=a["title"], description=a.get("description", ""), category="world_event")
                    for a in material.agendas
                    if a.get("title")
                ][:MAX_THREADS]
            hook = threads[0].description if threads else (material.facts[0] if material.facts else "")
            options.append(
                StartOption(
                    option_id=_slugify(location["name"]) + f"-{idx + 1}",
                    title=f"Begin at {location['name']}",
                    summary=hook[:200],
                    location=location["name"],
                    location_description=location.get("description", ""),
                    npcs=npcs,
                    hook=hook[:500],
                    player_role=pc_hint,
                    threads=threads,
                )
            )
        return options

    # ── normalization (bounds the brief pins) ─────────────────────────

    def _normalize_options(
        self,
        options: list[StartOption],
        material: UniverseMaterial,
        *,
        generated: bool,
    ) -> list[StartOption]:
        normalized: list[StartOption] = []
        seen_ids: set[str] = set()
        filler_npcs = [
            StartOptionNPC(name=c["name"], description=c.get("description", ""), want=c.get("want", ""))
            for c in material.characters
            if c.get("name")
        ]
        filler_threads = [
            StartOptionThread(
                title=t["title"],
                description=t.get("description", ""),
                category=t.get("category", "mystery"),
                urgency=t.get("urgency", "medium"),
            )
            for t in material.plot_threads
            if t.get("title")
        ]
        for option in options[:MAX_OPTIONS]:
            option_id = option.option_id
            while option_id in seen_ids:
                option_id += "x"
            seen_ids.add(option_id)

            npcs = [npc for npc in option.npcs if npc.name][:MAX_NPCS]
            for filler in filler_npcs:
                if len(npcs) >= MIN_NPCS:
                    break
                if all(npc.name != filler.name for npc in npcs):
                    npcs.append(filler)
            threads = [thread for thread in option.threads if thread.title][:MAX_THREADS]
            for filler in filler_threads:
                if len(threads) >= MIN_THREADS:
                    break
                if all(thread.title != filler.title for thread in threads):
                    threads.append(filler)
            if len(threads) < MIN_THREADS:
                # Guarantee the 2-3 opening threads the brief pins, derived
                # from the option's own hook and summary when nothing else is
                # available to pad with.
                synthetic = [
                    StartOptionThread(
                        title=option.hook[:80] or option.title,
                        description=option.hook,
                        category="world_event",
                    ),
                    StartOptionThread(
                        title=f"{option.location} holds its breath",
                        description=option.summary or option.location_description,
                        category="mystery",
                    ),
                ]
                for candidate in synthetic:
                    if len(threads) >= MIN_THREADS:
                        break
                    if all(thread.title != candidate.title for thread in threads):
                        threads.append(candidate)

            normalized.append(
                option.model_copy(
                    update={
                        "option_id": option_id,
                        "npcs": npcs,
                        "threads": threads,
                        "generated": generated,
                    }
                )
            )
        return normalized

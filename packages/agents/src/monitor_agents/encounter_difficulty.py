"""
Encounter difficulty for the GM table (CF-13 / G06).

The estimate is arithmetic, not opinion: the pure estimator in
``monitor_agents.game_system.difficulty`` does the math, and this agent
supplies it with the numbers — resolving a character's hit points from
their sheet, a foe's from its entity record, and the system's own
difficulty rules from the bound game system.

Nothing here writes anything, and nothing here calls a model: the point of
the feature is that the number is the same every time and can be shown to
the GM with its arithmetic attached.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1 schemas + MCP tools), external libraries
CALLED BY: UI backend routers (Layer 3)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog
from monitor_agents.base import BaseAgent
from monitor_agents.game_system.difficulty import (
    DifficultyEstimate,
    Foe,
    PartyMember,
    estimate_difficulty,
)

log = structlog.get_logger()

# The property names an entity may carry its hit points under.
_FOE_HP_KEYS = ("hit_points", "hitpoints", "hp", "health")
_FOE_ATTACK_KEYS = ("attack_bonus", "attack", "attack_rating")
_FOE_LEVEL_KEYS = ("level", "challenge_rating", "cr")

# The resource names that count as "how much punishment this character can
# take" when a sheet carries several resources.
_HIT_POINT_RESOURCE_NAMES = ("health", "hp", "hit points", "hitpoints", "vitality")


def _as_dict(raw: Any) -> dict[str, Any]:
    """A tool result as a dict (the MCP layer may hand back JSON text)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _first_int(source: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    """The first of ``keys`` that carries a usable number."""
    for key in keys:
        value = source.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _sheet_hit_points(sheet: dict[str, Any]) -> int | None:
    """A character's hit points, read from their sheet.

    A sheet carries several resources; the hit-point-like one wins, and
    when none of them is recognisable the largest pool is used — the
    character's biggest resource is the one that decides the fight.
    """
    resources = sheet.get("resources")
    if not isinstance(resources, dict):
        return None
    best: int | None = None
    for name, value in resources.items():
        if not isinstance(value, dict):
            continue
        maximum = value.get("max")
        if not isinstance(maximum, (int, float)):
            maximum = value.get("current")
        if not isinstance(maximum, (int, float)):
            continue
        if str(name).strip().lower() in _HIT_POINT_RESOURCE_NAMES:
            return int(maximum)
        best = int(maximum) if best is None else max(best, int(maximum))
    return best


class EncounterDifficultyAgent(BaseAgent):
    """Estimates how fair a proposed encounter is for a party (CF-13)."""

    def __init__(self, agent_id: str | None = None, model: str | None = None) -> None:
        super().__init__(
            agent_type="EncounterDifficultyAgent",
            agent_id=agent_id or "encounter-difficulty-agent",
            model=model,
        )

    async def run(self) -> None:
        """Implemented for BaseAgent compliance; routes call the method below."""

    async def estimate(
        self,
        universe_id: UUID,
        foes: list[dict[str, Any]],
        party: list[dict[str, Any]],
        system_doc: dict[str, Any] | None = None,
    ) -> DifficultyEstimate:
        """Estimate an encounter against a party.

        Args:
            universe_id: The universe the encounter belongs to.
            foes: The opponents. Each may carry ``name``, ``count``,
                ``hit_points``, ``attack_bonus`` and an ``entity_id`` to
                resolve the missing numbers from.
            party: The party that would face them. Each may carry ``name``,
                ``level``, ``hit_points`` and a ``character_id`` to resolve
                the missing numbers from.
            system_doc: The bound game system's document (may be empty).

        Returns:
            The estimate. ``unrated`` when there is nothing to compare.
        """
        resolved_foes = await self._resolve_foes(universe_id, foes)
        resolved_party = await self._resolve_party(party)
        estimate = estimate_difficulty(resolved_foes, resolved_party, system_doc)
        log.info(
            "encounter_difficulty_estimated",
            universe_id=str(universe_id),
            label=estimate.label,
            basis=estimate.basis,
        )
        return estimate

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    async def estimate_for_story(
        self,
        universe_id: UUID,
        story_id: UUID | None,
        foe_names: list[str],
        foe_count: int = 1,
    ) -> DifficultyEstimate:
        """Estimate an encounter the prep assistant proposed.

        The party is read from the story's own party and character sheets —
        the numbers the campaign has actually been playing with. The foes
        are the names the prep proposed; when the canon says nothing about
        their hit points, each one is costed at the generic threat value,
        which makes the estimate an action-economy judgement rather than a
        guess at their statistics.

        Args:
            universe_id: The universe the story belongs to.
            story_id: The story whose party faces the encounter.
            foe_names: The proposed opponents' names.
            foe_count: How many of them there are.

        Returns:
            The estimate; ``unrated`` when the story has no party to compare
            against.
        """
        party = await self._resolve_story_party(story_id)
        system_doc = await self._resolve_system_doc(universe_id)
        foes = [Foe(name=name or "Opponent", count=foe_count) for name in (foe_names or ["Opponent"])]
        estimate = estimate_difficulty(foes, party, system_doc)
        log.info(
            "encounter_difficulty_estimated",
            universe_id=str(universe_id),
            story_id=str(story_id) if story_id else None,
            label=estimate.label,
            basis=estimate.basis,
        )
        return estimate

    async def _resolve_story_party(self, story_id: UUID | None) -> list[PartyMember]:
        """The story's party, with the numbers their sheets carry."""
        if story_id is None:
            return []
        try:
            raw = await self.call_tool("neo4j_list_parties", {"params": {"story_id": str(story_id), "limit": 1}})
        except Exception as exc:  # noqa: BLE001  # reason: an unreadable party means "no estimate", not a failure
            log.warning("could not read the party of story %s: %s", story_id, exc)
            return []
        payload = _as_dict(raw)
        parties = payload.get("parties")
        if not isinstance(parties, list) or not parties:
            return []
        members = parties[0].get("members") if isinstance(parties[0], dict) else None
        if not isinstance(members, list):
            return []
        party: list[PartyMember] = []
        for member in members:
            if not isinstance(member, dict):
                continue
            entity_id = member.get("entity_id")
            if not entity_id:
                continue
            sheet = await self._fetch_sheet(str(entity_id))
            party.append(
                PartyMember(
                    name=str(sheet.get("character_name") or entity_id),
                    level=(int(sheet["total_level"]) if isinstance(sheet.get("total_level"), (int, float)) else None),
                    hit_points=_sheet_hit_points(sheet),
                )
            )
        return party

    async def _resolve_system_doc(self, universe_id: UUID) -> dict[str, Any] | None:
        """The universe's bound game-system document, if it has one."""
        try:
            raw = await self.call_tool("neo4j_get_universe", {"universe_id": str(universe_id)})
        except Exception as exc:  # noqa: BLE001  # reason: no binding means the generic convention
            log.debug("could not read the universe binding: %s", exc)
            return None
        universe = _as_dict(raw)
        system_id = universe.get("default_game_system_id")
        if not system_id:
            return None
        try:
            doc = await self.call_tool("mongodb_get_game_system", {"system_id": str(system_id)})
        except Exception as exc:  # noqa: BLE001  # reason: a missing system means the generic convention
            log.debug("could not read the game system: %s", exc)
            return None
        return _as_dict(doc) or None

    async def _resolve_foes(self, universe_id: UUID, foes: list[dict[str, Any]]) -> list[Foe]:
        """Turn the request's foes into foes with numbers."""
        resolved: list[Foe] = []
        for raw in foes:
            name = str(raw.get("name") or "Opponent").strip() or "Opponent"
            count = int(raw.get("count") or 1)
            hit_points = _first_int(raw, ("hit_points", "hitpoints", "hp"))
            attack_bonus = _first_int(raw, ("attack_bonus",))

            entity_id = raw.get("entity_id")
            if entity_id and (hit_points is None or attack_bonus is None):
                entity = await self._fetch_entity(str(entity_id), universe_id)
                if entity:
                    properties = entity.get("properties")
                    properties = properties if isinstance(properties, dict) else {}
                    if hit_points is None:
                        hit_points = _first_int(properties, _FOE_HP_KEYS)
                        if hit_points is None:
                            hit_points = _first_int(entity, _FOE_HP_KEYS)
                    if attack_bonus is None:
                        attack_bonus = _first_int(properties, _FOE_ATTACK_KEYS)
                    if not name or name == "Opponent":
                        name = str(entity.get("name") or name)

            resolved.append(
                Foe(
                    name=name,
                    count=max(1, count),
                    hit_points=hit_points,
                    attack_bonus=attack_bonus,
                )
            )
        return resolved

    async def _fetch_entity(self, entity_id: str, universe_id: UUID) -> dict[str, Any]:
        """One entity's record, or an empty dict."""
        try:
            raw = await self.call_tool("neo4j_get_entity", {"entity_id": entity_id})
        except Exception as exc:  # noqa: BLE001  # reason: an unreadable entity means "unknown numbers", not a failure
            log.warning("could not read entity %s: %s", entity_id, exc)
            return {}
        entity = _as_dict(raw)
        if not entity:
            return {}
        if entity.get("universe_id") and str(entity["universe_id"]) != str(universe_id):
            # A foe from another universe would make the numbers meaningless.
            return {}
        return entity

    async def _resolve_party(self, party: list[dict[str, Any]]) -> list[PartyMember]:
        """Turn the request's party into members with numbers."""
        resolved: list[PartyMember] = []
        for raw in party:
            name = str(raw.get("name") or "Adventurer").strip() or "Adventurer"
            level = _first_int(raw, ("level",))
            hit_points = _first_int(raw, ("hit_points", "hitpoints", "hp"))

            character_id = raw.get("character_id")
            if character_id and (hit_points is None or level is None):
                sheet = await self._fetch_sheet(str(character_id))
                if sheet:
                    if hit_points is None:
                        hit_points = _sheet_hit_points(sheet)
                    if level is None:
                        total_level = sheet.get("total_level")
                        if isinstance(total_level, (int, float)):
                            level = int(total_level)

            resolved.append(PartyMember(name=name, level=level, hit_points=hit_points))
        return resolved

    async def _fetch_sheet(self, character_id: str) -> dict[str, Any]:
        """A character's active sheet, or an empty dict."""
        try:
            raw = await self.call_tool(
                "mongodb_list_character_sheets",
                {"params": {"entity_id": character_id, "is_active": True, "limit": 1}},
            )
        except Exception as exc:  # noqa: BLE001  # reason: a missing sheet means "unknown numbers", not a failure
            log.warning("could not read character sheet for %s: %s", character_id, exc)
            return {}
        payload = _as_dict(raw)
        sheets = payload.get("character_sheets") or payload.get("sheets") or []
        if not isinstance(sheets, list) or not sheets:
            return {}
        first = sheets[0]
        return first if isinstance(first, dict) else {}


__all__ = ["EncounterDifficultyAgent"]

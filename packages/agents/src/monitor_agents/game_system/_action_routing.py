"""Action routing — semantic (embeddings), not keyword heuristics.

Route a player's action to the stat / difficulty / subsystem the world's own
schema defines, by *embedding similarity* — never keyword tables.

WHY THIS REPLACED THE OLD IMPLEMENTATION
----------------------------------------
The previous version matched literal keyword tables built from schema text
(``build_skill_routes``/``build_attribute_routes``) plus hardcoded English
signal regexes (``SOCIAL_SIGNALS``/``SHIP_SIGNALS``/``COMBAT_SIGNALS``). That
is brittle: it misses synonyms, breaks across genres/languages, and can only
route phrasings it was hand-fed. Matching now runs through
:meth:`RetrievalService.nearest` — the one embedding owner.

HOW IT WORKS NOW
----------------
The world schema still authors the vocabulary — every route's *target* comes
from the system's own skills / attributes / rules. Only the *matching* changed:

* Each skill / attribute becomes a route whose text (``name. description``) is
  embedded once. At call time we embed the player's action and pick the route
  whose text is closest in embedding space → its linked attribute + DC.
* ``action_type`` (``dialogue`` vs ``action``) comes from comparing the action
  to a small set of natural-language *exemplar* sentences (not keywords).
* ``subsystem_hint`` is the nearest rule-family (``applies_to_subject``) above a
  similarity threshold, else ``None``.

FAIL LOUD
---------
Embeddings come from the data-layer ``embed_text`` / ``embed_batch``, which
raise :class:`EmbeddingProviderError` when no provider is available. We do NOT
fabricate vectors or silently fall back to keyword matching. Routing only runs
inside dice resolution (``resolver`` Branch 3), the same turns that already
require embeddings for roll necessity — so a raise here is exactly when the
turn should stop and alert rather than guess.

CACHING
-------
``GameSystemRuntime`` is reconstructed per turn, so the router is cached by
*system identity* (:func:`_get_router`). The candidate *vectors* are cached one
layer down, inside the ``RetrievalService``: each ``nearest`` call passes a
content-stable ``candidates_key``, so the stat/action-type/subsystem candidate
lists are embedded once and only the per-turn query is re-embedded.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import structlog

from monitor_agents.utils.runtime_profile_support import expand_query_with_profile

from ._types import SystemData

logger = structlog.get_logger()


# ===========================================================================
# Anchors — natural-language exemplars separating verbal/social from physical
# ===========================================================================
#
# These are *sentences*, embedded semantically — not keyword lists. They let us
# tag an action ``dialogue`` vs ``action`` without hardcoding English verbs.

_SOCIAL_ANCHORS: list[str] = [
    "I try to persuade the guard to let me pass",
    "I intimidate the merchant into lowering his price",
    "I lie to the noble about who I really am",
    "I plead with the captain to spare the prisoners",
    "I charm the crowd with a rousing speech",
    "I negotiate the terms of the truce with the envoy",
    "I question the witness about what they saw",
    "I taunt the duelist to make him lose his temper",
]

_PHYSICAL_ANCHORS: list[str] = [
    "I climb the crumbling wall to reach the ledge",
    "I swing my sword at the snarling orc",
    "I sprint across the courtyard to the gate",
    "I pick the lock on the iron chest",
    "I shove the heavy door open with my shoulder",
    "I leap across the gap between the rooftops",
    "I fire my pistol at the fleeing bandit",
    "I search the room for a hidden compartment",
]

# Only assign a subsystem hint when the nearest rule-family is at least this
# close — otherwise the action doesn't clearly belong to any subsystem.
_SUBSYSTEM_MIN_SIMILARITY = 0.35


# ===========================================================================
# Route metadata (built from the schema, embedded lazily)
# ===========================================================================


@dataclass(frozen=True)
class _StatRoute:
    """A skill/attribute the action could target."""

    text: str  # embedded to compare against the player's action
    stat_abbr: str
    difficulty_class: int


@dataclass(frozen=True)
class _SubsystemRoute:
    """A rule family the action could belong to."""

    text: str
    subject: str


def _candidates_key(texts: list[str]) -> str:
    """Content-addressed cache key for a candidate list (RetrievalService.nearest).

    Hashing the texts means a schema edit yields a different key — a stale
    cache can never be silently reused for a changed candidate set.
    """
    h = hashlib.sha1("\x00".join(texts).encode("utf-8")).hexdigest()
    return f"action_routing:{h}"


def _attr_dc(attr_def: dict[str, Any]) -> int:
    """Difficulty class derived from an attribute's value range (schema-driven)."""
    width = attr_def.get("max_value", 20) - attr_def.get("min_value", 0)
    return 12 if width <= 10 else 13


def _default_stat(sd: SystemData) -> tuple[str, int]:
    """First primary attribute (or a neutral default) when nothing else fits."""
    first = sd.primary_attributes
    if first:
        abbr = (first[0].get("abbreviation") or first[0].get("name", "STAT")[:4]).upper()
        return abbr, _attr_dc(first[0])
    return "STR", 12


def _build_stat_routes(sd: SystemData) -> list[_StatRoute]:
    """One route per skill (linked to its attribute) plus per primary attribute."""
    routes: list[_StatRoute] = []

    name_to_abbr: dict[str, str] = {}
    for attr in sd.attrs:
        aname = (attr.get("name") or "").lower()
        abbr = (attr.get("abbreviation") or attr.get("name", "")[:4]).upper()
        if aname:
            name_to_abbr[aname] = abbr

    for skill in sd.skills:
        linked = (skill.get("linked_attribute") or "").strip()
        abbr = name_to_abbr.get(linked.lower()) or linked.upper()[:4]
        if not abbr:
            continue
        name = skill.get("name") or ""
        desc = skill.get("description") or ""
        text = f"{name}. {desc}".strip()
        if not text or text == ".":
            continue
        attr_def = sd.attr_by_abbr.get(abbr, {})
        routes.append(_StatRoute(text=text, stat_abbr=abbr, difficulty_class=_attr_dc(attr_def)))

    for attr in sd.primary_attributes:
        abbr = (attr.get("abbreviation") or attr.get("name", "STAT")[:4]).upper()
        text = f"{attr.get('name', '')}. {attr.get('description', '')}".strip()
        if not text or text == ".":
            continue
        routes.append(_StatRoute(text=text, stat_abbr=abbr, difficulty_class=_attr_dc(attr)))

    return routes


def _build_subsystem_routes(sd: SystemData) -> list[_SubsystemRoute]:
    """One route per rule, tagged with the rule's ``applies_to_subject``."""
    routes: list[_SubsystemRoute] = []
    for rule in sd.rules:
        subject = str(rule.get("applies_to_subject") or "").strip().lower() or "character"
        text = f"{rule.get('name', '')}. {rule.get('description', '')}".strip()
        if not text or text == ".":
            continue
        routes.append(_SubsystemRoute(text=text, subject=subject))
    return routes


# ===========================================================================
# Router
# ===========================================================================


class SemanticActionRouter:
    """Routes an action to a stat / DC / subsystem via ``RetrievalService.nearest``.

    Holds the schema's candidate text lists (cheap — no embedding at
    construction). Each turn, delegates the actual embedding + cosine ranking
    to the RetrievalService, the single owner of embeddings. Cache one per
    system (see :func:`_get_router`) so the candidate lists build once.
    """

    def __init__(self, sd: SystemData) -> None:
        self._sd = sd
        self._stat_routes: list[_StatRoute] = _build_stat_routes(sd)
        self._subsystem_routes: list[_SubsystemRoute] = _build_subsystem_routes(sd)
        # Action-type is decided by whether the action reads social or physical:
        # the anchor sets are concatenated; index < len(social) means dialogue.
        self._action_type_candidates: list[str] = list(_SOCIAL_ANCHORS) + list(_PHYSICAL_ANCHORS)
        self._n_social = len(_SOCIAL_ANCHORS)
        # Content-stable cache keys so the RetrievalService embeds each candidate
        # list once (not every turn). Derived from the texts themselves, so a
        # schema change produces a new key rather than a stale cache hit.
        self._stat_key = _candidates_key([r.text for r in self._stat_routes])
        self._subsystem_key = _candidates_key([r.text for r in self._subsystem_routes])
        self._action_type_key = _candidates_key(self._action_type_candidates)

    async def infer_action_context(
        self,
        user_input: str,
        source_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return action routing details via nearest-candidate ranking.

        The input is enriched with the source profile's lexicon (e.g. Vampire
        canon signal terms) before ranking, so setting-native framing is
        captured — same intent the old keyword router got by expanding the
        haystack, but semantically. All embedding is delegated to the
        RetrievalService; this method only maps the ranked winner back to the
        schema-derived stat / DC / subsystem.
        """
        text = (user_input or "").strip()
        if not text:
            abbr, dc = _default_stat(self._sd)
            return {
                "action_type": "action",
                "stat_name": abbr,
                "difficulty_class": dc,
                "subsystem_hint": None,
            }

        expanded_text = expand_query_with_profile(text, text, source_profile or {}, limit=16).strip() or text

        from monitor_data.retrieval import default_retrieval_service

        retriever = default_retrieval_service()

        # 1. Stat + DC: nearest schema skill/attribute route.
        stat_name, dc = _default_stat(self._sd)
        stat_texts = [r.text for r in self._stat_routes]
        if stat_texts:
            ranked = await retriever.nearest(expanded_text, stat_texts, top_k=1, candidates_key=self._stat_key)
            if ranked:
                route = self._stat_routes[ranked[0].index]
                stat_name, dc = route.stat_abbr, route.difficulty_class

        # 2. action_type: nearest social/physical anchor.
        action_type = "action"
        at_ranked = await retriever.nearest(
            expanded_text,
            self._action_type_candidates,
            top_k=1,
            candidates_key=self._action_type_key,
        )
        if at_ranked and at_ranked[0].index < self._n_social:
            action_type = "dialogue"

        # 3. subsystem_hint: nearest rule family above the similarity threshold.
        subsystem_hint: str | None = None
        sub_texts = [r.text for r in self._subsystem_routes]
        if sub_texts:
            sub_ranked = await retriever.nearest(expanded_text, sub_texts, top_k=1, candidates_key=self._subsystem_key)
            if sub_ranked and sub_ranked[0].score >= _SUBSYSTEM_MIN_SIMILARITY:
                subsystem_hint = self._subsystem_routes[sub_ranked[0].index].subject
        if subsystem_hint is None and action_type == "dialogue":
            subsystem_hint = "social"

        return {
            "action_type": action_type,
            "stat_name": stat_name,
            "difficulty_class": dc,
            "subsystem_hint": subsystem_hint,
        }


# ===========================================================================
# Per-system router cache + module-level API (the test/patch seam)
# ===========================================================================

_ROUTER_CACHE: dict[str, SemanticActionRouter] = {}


def _system_key(sd: SystemData) -> str:
    """Stable identity for a game system so its route vectors are cached once."""
    doc = sd.doc or {}
    return str(doc.get("_id") or doc.get("id") or doc.get("name") or id(doc))


def _get_router(sd: SystemData) -> SemanticActionRouter:
    key = _system_key(sd)
    router = _ROUTER_CACHE.get(key)
    if router is None:
        router = SemanticActionRouter(sd)
        _ROUTER_CACHE[key] = router
    return router


def reset_action_router_cache() -> None:
    """Drop cached routers (tests + system reloads)."""
    _ROUTER_CACHE.clear()


async def infer_action_context(
    sd: SystemData,
    user_input: str,
    source_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Semantic action routing — see :class:`SemanticActionRouter`."""
    return await _get_router(sd).infer_action_context(user_input, source_profile=source_profile)


async def infer_action_stat(
    sd: SystemData,
    user_input: str,
    source_profile: dict[str, Any] | None = None,
) -> tuple[str, str, int]:
    """Backward-compatible tuple wrapper around :func:`infer_action_context`."""
    routed = await infer_action_context(sd, user_input, source_profile=source_profile)
    return (
        str(routed.get("action_type", "action")),
        str(routed.get("stat_name", "STR")),
        int(routed.get("difficulty_class", 12)),
    )


async def infer_subsystem_hint(
    sd: SystemData,
    user_input: str,
    source_profile: dict[str, Any] | None = None,
) -> str | None:
    """Infer the most likely rule family/subsystem for the current action."""
    routed = await infer_action_context(sd, user_input, source_profile=source_profile)
    hint = routed.get("subsystem_hint")
    return str(hint) if hint else None

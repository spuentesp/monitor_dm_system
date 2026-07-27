"""
Chat opening helpers — story/scene bootstrap and GM opening messages.

Extracted from chat.py to isolate session initialisation from the router.

Layer 2/3 is a strict-downward import path: data-layer is required (no
graceful-degradation fallback) so a missing dependency fails loud during
router import rather than producing a half-working session later.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

# Layer-2 helper — same module, re-exported here for back-compat. The
# canonical home is ``monitor_agents.loops.session_bootstrap`` so Layer-3
# callers (this router + the e2e harness) can depend on it without
# crossing a peer boundary.
from monitor_agents.loops.session_bootstrap import bootstrap_story_scene  # noqa: F401

# Layer-2 imports for the LLM-opening path.
from monitor_agents.narrator.agent import Narrator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Opening hook — lore + entity-driven scene introduction
# ---------------------------------------------------------------------------


async def fetch_opening_hook(session: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch lore material for the opening scene: axioms, lore facts, location entities.

    Returns a dict with keys: axioms, facts, locations, system_name, tone.
    All values are lists of strings (or empty lists on failure).
    """
    universe_id = session.get("universe_id")
    result: dict[str, Any] = {
        "axioms": [],
        "facts": [],
        "locations": [],
        "system_name": session.get("system_label") or session.get("multiverse_label") or "",
        "tone": session.get("tone", "dramatic"),
    }
    if not universe_id:
        return result
    try:
        from monitor_data.db.neo4j import get_neo4j_client

        neo = get_neo4j_client()

        # Axioms — world-level truths
        axiom_rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (a:Axiom) WHERE a.universe_id = $uid RETURN a.statement AS s ORDER BY a.confidence DESC LIMIT 5",
            {"uid": universe_id},
        )
        if not axiom_rows:
            axiom_rows = await asyncio.to_thread(
                neo.execute_read,
                "MATCH (a:Axiom) RETURN a.statement AS s ORDER BY a.confidence DESC LIMIT 5",
                {},
            )
        result["axioms"] = [r["s"] for r in axiom_rows if r.get("s")]

        # LoreFacts — grounded narrative facts for scene atmosphere
        fact_rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (f:Fact) WHERE f.universe_id = $uid RETURN f.statement AS s ORDER BY f.confidence DESC LIMIT 6",
            {"uid": universe_id},
        )
        if not fact_rows:
            fact_rows = await asyncio.to_thread(
                neo.execute_read,
                "MATCH (f:Fact) RETURN f.statement AS s ORDER BY f.confidence DESC LIMIT 6",
                {},
            )
        result["facts"] = [r["s"] for r in fact_rows if r.get("s")]

        # Location entities — for concrete scene anchoring
        loc_rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (e:Entity) WHERE e.entity_type = 'location' "
            "AND (e.universe_id = $uid OR e.is_archetype = true) "
            "RETURN e.name AS name, e.description AS desc LIMIT 4",
            {"uid": universe_id},
        )
        result["locations"] = [f"{r['name']}: {r.get('desc', '')}" for r in loc_rows if r.get("name")]

    except Exception as exc:
        logger.debug("fetch_opening_hook failed: %s", exc)
    return result


# ---------------------------------------------------------------------------
# Opening message builder — evocative single GM message
# ---------------------------------------------------------------------------


async def _fetch_module_intro(session: dict[str, Any]) -> str:
    """Return the session's pack-authored verbatim opening, or ``""``.

    [G-2] Resolves ``session["pack_id"]`` via
    ``mongodb_get_knowledge_pack`` (sync-in-async — matches the existing
    pattern in this file) and returns ``pack.intro_text`` if it carries
    a substantive read-aloud intro (>40 chars). Returns ``""`` for any
    miss/error so the caller falls back to the resume or generated
    cold-open path. See ``docs/architecture/GAP_REMEDIATION_PLAN.md``
    G-2(c) and ``docs/STATUS.md`` [G-2].
    """
    pack_id_raw = session.get("pack_id")
    if not pack_id_raw:
        return ""
    try:
        from monitor_data.tools.mongodb_tools import (
            mongodb_get_knowledge_pack,
        )

        pack = mongodb_get_knowledge_pack(uuid.UUID(str(pack_id_raw)))
    except Exception as exc:
        logger.debug("build_gm_opening module_intro fetch failed: %s", exc)
        return ""
    if pack is None:
        return ""
    intro = (getattr(pack, "intro_text", None) or "").strip()
    return intro if len(intro) > 40 else ""


async def build_gm_opening(
    session_id: str,
    session: dict[str, Any],
    *,
    session_game_system_doc: Any,
    is_resume: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build a single immersive GM opening message.

    Three paths (PLAY_AND_FORGE_DIRECTION.md S5), in precedence order:
    1. **Module-intro (verbatim)** — fresh sessions whose session pack carries
       an ``intro_text > 40`` chars use it as-is, no LLM. See ``_fetch_module_intro``.
    2. **Resume recap** — ``is_resume`` and a story already exists → synthesize
       "the story so far" via RecapAgent.
    3. **Cold open** (default) — generate an in-fiction scene-setting
       paragraph via the LLM; fall through to a non-LLM template if that
       call fails.
    """
    # P&F S5 case 1: the ingested module's own authored intro, verbatim.
    # Fresh sessions only — resume keeps priority for its recap branch below.
    if not is_resume:
        intro = await _fetch_module_intro(session)
        if intro:
            return intro, {"type": "gm_opening", "module_intro": True}

    if is_resume:
        story_id = session.get("story_id")
        universe_id = session.get("universe_id")
        if story_id and universe_id:
            try:
                from monitor_agents.recap.agent import RecapAgent

                recap = RecapAgent()
                recap_text = await recap.generate_recap(
                    uuid.UUID(str(story_id)),
                    uuid.UUID(str(universe_id)),
                    tone_context=f"{session.get('tone', 'dramatic')} recap, ending on a forward-looking hook.",
                )
                recap_text = (recap_text or "").strip()
                if recap_text and len(recap_text) > 40:
                    return recap_text, {"type": "gm_opening", "resume": True}
            except Exception as exc:
                logger.debug("build_gm_opening resume-recap failed: %s", exc)
        # Falls through to the cold-open path below if the recap couldn't
        # be produced (e.g. a story_id with no prior scenes yet) -- better
        # to give a real opening than none.

    lore = await fetch_opening_hook(session)
    tone = lore["tone"]
    system_name = lore["system_name"]
    axioms = lore["axioms"]
    facts = lore["facts"]
    locations = lore["locations"]
    story_premise = session.get("story_premise")

    # A stated premise alone is reason enough to run the LLM path -- the
    # non-LLM fallback below is a fixed lore-snippet template that can't
    # honor free-text steering, so a premise-only session (no lore yet)
    # must not silently discard it.
    if axioms or facts or system_name or story_premise:
        try:
            from monitor_data.tools.mongodb_tools import mongodb_get_gm_profile

            # Load GM profile if configured
            gm_profile: dict[str, Any] | None = None
            gm_profile_id = session.get("gm_profile_id")
            if gm_profile_id:
                try:
                    profile_res = mongodb_get_gm_profile(uuid.UUID(gm_profile_id))
                    if profile_res:
                        gm_profile = profile_res.model_dump()
                except Exception as e:
                    logger.debug("Failed to load GM profile for opening: %s", e)

            lore_context = []
            if locations:
                lore_context.append("Locations: " + "; ".join(locations[:2]))
            if facts:
                lore_context.append("World facts: " + " | ".join(facts[:3]))
            if axioms:
                lore_context.append("World truths: " + " | ".join(axioms[:2]))

            narrator = Narrator()
            narrative = (
                await narrator.generate_opening(
                    user_input="(session opening — set the scene and ask who the player is)",
                    context={
                        "entities": [{"context": "\n".join(lore_context)}] if lore_context else [],
                        "memories": [],
                        "turns": [],
                    },
                    game_context=session_game_system_doc(session),
                    session_tone=tone,
                    gm_profile=gm_profile,
                    story_premise=story_premise,
                )
            ).strip()
            if narrative and len(narrative) > 40:
                return narrative, {
                    "type": "gm_opening",
                    "lore_used": bool(lore_context),
                    "premise_used": bool(story_premise),
                }
        except Exception as exc:
            logger.debug("build_gm_opening LLM call failed: %s", exc)

    # Fallback: compose from lore strings without LLM. Reached when there's
    # no lore AND no premise (gate above), or the LLM call itself failed --
    # in the latter case still surface the stated premise rather than a
    # fully generic question.
    parts: list[str] = []
    if story_premise:
        parts.append(f"The story you want: {story_premise}.")

    opener_candidates = facts[:2] + axioms[:2]
    if locations:
        parts.append(locations[0].split(":")[0].strip() + ".")
    if opener_candidates:
        for stmt in opener_candidates[:2]:
            s = stmt.rstrip(".")
            if s:
                parts.append(s + ".")

    _OPENING_QUESTIONS = {
        "grim": "Who are you, and what broke to bring you here?",
        "horror": "You are here. Who are you — and what did you bring with you?",
        "dramatic": "Who are you, and what do you want from this?",
        "heroic": "Who are you — and what quest drives you forward?",
        "mystery": "You are here for a reason. Who are you, really?",
        "adventure": "So — who are you, and what's the plan?",
    }
    parts.append(_OPENING_QUESTIONS.get(tone.lower(), "Who are you, and where does your story begin?"))

    text = "  ".join(parts) if parts else "Who are you, and where does your story begin?"
    return text, {"type": "gm_opening"}

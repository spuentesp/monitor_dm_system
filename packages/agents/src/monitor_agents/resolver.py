"""
Resolver Agent implementation.

LAYER: 2 (agents)
Authority: MongoDB (resolutions, proposals), Character State

ARCHITECTURE NOTE
-----------------
The resolver uses TWO LLM-driven decision points:

1. **GMAwareness** (DSPy) — replaces the old regex-based forced-narrative
   detection. The GM (LLM) consciously reads the player's text and returns
   a structured verdict: did the player declare an outcome? Does it violate
   causality? What should the resolver do? This is the "conscious thought
   process of the GM" — no regex, no keyword lists.

2. **Roll necessity** — the GMAgent LLM emits ``roll_necessity`` directly
   in its verdict (trivial / propose_roll / contested). The resolver trusts
   that verdict and only falls back to ``_fallback_roll_necessity`` — a
   thin intent→necessity map — when the verdict isn't real (e.g. the LLM is
   unavailable). No regex, no embedding classifier.

Both branches are LLM-driven; the resolver is a thin state machine that
shapes the GM's verdict into the legacy resolution dict.
"""

import asyncio
import json
import logging
import re
from contextlib import suppress
from typing import Any, Optional
from uuid import UUID

from monitor_data.utils.dice import calculate_modifier, roll_dice

from monitor_agents.base import BaseAgent
from monitor_agents.game_system import GameSystemRuntime

# LLM-driven causality check (replaces legacy regex forced-narrative detection).
# Imported at module level so tests can patch ``monitor_agents.resolver.check_gm_awareness``.
from monitor_agents.gm_awareness import (
    ActionType,
    CausalityAction,
    IntentType,
    check_gm_awareness,
)
from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource

# Snapshot of the original check_gm_awareness — used to detect when a test
# has patched it (the patched function will differ from this reference).
# When patched, the resolver honors the patched function and converts its
# GMAwareness return to a GMVerdict for the rest of the pipeline.
_ORIGINAL_CHECK_GM_AWARENESS = check_gm_awareness

logger = logging.getLogger(__name__)

# Default D&D-style modifier formula used when no game-system schema is loaded
_DEFAULT_MODIFIER_FORMULA = "(VALUE - 10) // 2"

# Final action-profile fallback when no GameSystemRuntime is available
# AND no keyword / LLM routing produced one, AND embeddings themselves are
# unavailable (see ``_infer_generic_stat`` below, which is what actually
# supplies the stat in the common case). The schema-driven path
# (``GameSystemRuntime.infer_action_context``) is preferred whenever a
# game system is loaded.
_DEFAULT_ACTION_PROFILE = ("action", "Strength", 12)

# Generic (schema-free) ability fallback for dice_standard / no-schema turns.
# Even without a bound game system, the stat should reflect what the player
# is actually attempting -- not a fixed "Strength" regardless of content
# (that produced e.g. a Strength check for a stealth/reconnaissance action
# with no combat or lifting involved). Routed via embedding similarity
# against six generic D&D-style abilities (matching
# ``_DEFAULT_MODIFIER_FORMULA``, already D&D-shaped) -- the same semantic
# approach ``GameSystemRuntime`` uses when a schema IS loaded, never a
# keyword table.
_GENERIC_ABILITIES: tuple[tuple[str, str], ...] = (
    (
        "Strength",
        "Raw physical power: lifting, breaking, forcing doors, striking hard, carrying heavy loads, grappling.",
    ),
    (
        "Dexterity",
        "Agility, balance, reflexes, stealth, fine motor control: sneaking, "
        "dodging, picking locks, aiming, moving quietly without being noticed.",
    ),
    (
        "Constitution",
        "Endurance and toughness: resisting poison, disease, or exhaustion, holding out under strain or pain.",
    ),
    (
        "Intelligence",
        "Reasoning and deduction: recalling knowledge, solving puzzles, "
        "analyzing evidence, understanding how something works.",
    ),
    (
        "Wisdom",
        "Perception and intuition: noticing hidden details, reading a "
        "situation, sensing danger, staying alert to your surroundings.",
    ),
    (
        "Charisma",
        "Force of personality: persuading, deceiving, intimidating, "
        "performing, negotiating, making an impression in conversation.",
    ),
)


def _generic_ability_cache_key() -> str:
    """Content-addressed cache key so ``RetrievalService.nearest`` embeds
    the six generic ability texts once per process, not every turn."""
    import hashlib

    h = hashlib.sha1("\x00".join(text for _, text in _GENERIC_ABILITIES).encode("utf-8")).hexdigest()
    return f"resolver:generic_ability:{h}"


_GENERIC_ABILITY_CACHE_KEY = _generic_ability_cache_key()


async def _infer_generic_stat(user_input: str) -> str:
    """Semantic stat routing for schema-free turns (no game system bound).

    Falls back to the fixed "Strength" default (matching the prior, always-
    wrong behavior) only if embeddings are genuinely unavailable -- this is
    the resolver's final line of defense, so unlike the schema-bound router
    (``GameSystemRuntime.infer_action_context``, which fails loud) it must
    never raise.
    """
    text = (user_input or "").strip()
    if not text:
        return _GENERIC_ABILITIES[0][0]
    try:
        from monitor_data.retrieval import default_retrieval_service

        retriever = default_retrieval_service()
        ranked = await retriever.nearest(
            text,
            [desc for _, desc in _GENERIC_ABILITIES],
            top_k=1,
            candidates_key=_GENERIC_ABILITY_CACHE_KEY,
        )
        if ranked:
            return _GENERIC_ABILITIES[ranked[0].index][0]
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _infer_generic_stat)
        logger.debug("generic stat routing unavailable; using fixed default", exc_info=True)
    return _GENERIC_ABILITIES[0][0]


def _is_narrative_core(gsr: GameSystemRuntime | None) -> bool:
    """Return True when the loaded game system is explicitly pure narrative."""
    if gsr is None:
        return False
    return str(gsr._sd.core.get("type", "")).lower() == "narrative"


_VALID_NECESSITY = ("trivial", "propose_roll", "contested")


def _fallback_roll_necessity(intent_type: str) -> str:
    """Roll-necessity when the GM verdict didn't supply one.

    The GMAgent is the authority — it emits ``roll_necessity`` directly. This
    is only reached when the verdict was *not* real (its DSPy call failed and
    the seed fallback fired). We no longer run a separate embeddings-based
    classifier here (the GM already decides); we apply one structural guard
    (query/ooc/meta never rolls) and otherwise default to the safe middle:
    ``propose_roll`` — offer a roll, don't force or skip.

    Tests pin the outcome by patching this function
    (``force_roll_necessity`` in ``_roll_helpers``).
    """
    if intent_type in ("query", "ooc", "meta"):
        return "trivial"
    return "propose_roll"


# The GM can choose these action types. Combat stays with the game-system router
# because a "combat" value makes SceneLoop start a CombatLoop.
_GM_ACTION_TYPES = frozenset({ActionType.DIALOGUE, ActionType.STEALTH, ActionType.EXPLORATION, ActionType.MOVEMENT})
_MAX_GM_DC = 60


def _lookup_stat(attributes: dict[str, int], names: list[str]) -> int | None:
    """Find a stat by name or 3+ letter abbreviation, ignoring case."""
    by_lower = {key.lower(): value for key, value in attributes.items()}
    wanted = [name.lower() for name in names if name]
    for name in wanted:
        if name in by_lower:
            return by_lower[name]
    for name in wanted:
        for key, value in by_lower.items():
            if len(name) >= 3 and len(key) >= 3 and (name.startswith(key) or key.startswith(name)):
                return value
    return None


def _system_stat(gsr: GameSystemRuntime, name: str) -> str | None:
    """Return the system's abbreviation for a stat given by name or abbreviation."""
    wanted = name.strip().lower()
    for abbr, attr in gsr._attr_by_abbr.items():
        if wanted in (abbr.lower(), str(attr.get("name") or "").lower()):
            return str(abbr)
    return None


def _uses_roll_under(gsr: GameSystemRuntime | None) -> bool:
    """Detect roll-under d20 systems from the stored core mechanic text."""
    if gsr is None:
        return False
    core = gsr._sd.core
    text = " ".join(str(core.get(key, "")) for key in ("formula", "success_threshold", "critical_success")).lower()
    return "roll under" in text or "under or equal" in text or "<=" in text


def _pool_die_sides(core: dict[str, Any]) -> int:
    formula = str(core.get("formula") or "")
    sides_match = re.search(r"d(\d+)", formula, re.IGNORECASE)
    return max(2, int(sides_match.group(1))) if sides_match else 10


def _parse_pool_threshold(threshold_val: Any, *, die_sides: int = 10) -> int:
    """Extract a valid per-die success threshold (never concatenating multi-band text)."""
    default = min(6, die_sides)
    try:
        if isinstance(threshold_val, str):
            m = re.search(r"\d+", threshold_val)
            parsed = int(m.group(0)) if m else default
        else:
            parsed = int(threshold_val)
    except (ValueError, TypeError):
        return default
    if parsed < 1 or parsed > die_sides:
        return default
    return parsed


def _is_count_successes_pool(core: dict[str, Any] | None) -> bool:
    """Return True only for genuine count-successes dice pools (excluding 2d6+stat PbtA / 4dF Fate)."""
    if not core or "dice_pool" not in str(core.get("type", "")).lower():
        return False
    formula = str(core.get("formula") or "")
    if "df" in formula.lower():
        return False
    die_sides = _pool_die_sides(core)
    raw_threshold = core.get("success_threshold")
    if isinstance(raw_threshold, str):
        m = re.search(r"\d+", raw_threshold)
        if m and int(m.group(0)) > die_sides:
            return False
    elif isinstance(raw_threshold, (int, float)) and int(raw_threshold) > die_sides:
        return False
    return True


def _pool_proposal_fields(
    gsr: GameSystemRuntime | None,
    stat_value: int | None,
    pool_bonus: int,
) -> dict[str, Any]:
    """Return dice-pool metadata when ``gsr`` uses a pool mechanic, else ``{}``."""
    if gsr is None or not _is_count_successes_pool(gsr._sd.core):
        return {}
    core = gsr._sd.core
    formula = str(core.get("formula") or "")
    die_sides = _pool_die_sides(core)
    threshold = _parse_pool_threshold(core.get("success_threshold", 6), die_sides=die_sides)

    if stat_value is not None:
        try:
            pool_size = int(stat_value) + int(pool_bonus)
        except (ValueError, TypeError):
            pool_size = 1
    else:
        cnt_match = re.match(r"^\s*(\d+)d\d+", formula, re.IGNORECASE)
        base_pool = int(cnt_match.group(1)) if cnt_match else 1
        pool_size = base_pool + int(pool_bonus)
    if pool_size < 1:
        pool_size = 1

    return {
        "mechanic_type": "dice_pool",
        "pool_size": pool_size,
        "pool_die_sides": die_sides,
        "success_threshold": threshold,
    }


def _resolve_base_dc(gsr: GameSystemRuntime | None, fallback_dc: int) -> int:
    """Prefer the system's declared base target when one is embedded in the mechanic text."""
    if gsr is None:
        return fallback_dc
    core = gsr._sd.core
    text = " ".join(str(core.get(key, "")) for key in ("formula", "success_threshold")).lower()
    if not text:
        return fallback_dc

    # Ignore dice notation like 1d20 so we can pick out the real target number.
    text = re.sub(r"\b\d*d\d+\b", " ", text)
    match = re.search(r"\b(\d{1,2})\b", text)
    if not match:
        return fallback_dc

    try:
        target = int(match.group(1))
    except ValueError:
        return fallback_dc

    return target if 2 <= target <= 20 else fallback_dc


def _strip_ooc_wrappers(text: str) -> str:
    """Strip OOC ``((…))`` blocks from ``text``.

    Two cases:
      - A standalone OOC wrapper: ``((Roll for initiative))`` → unwrap
      - A trailing likelihood marker: ``Is there a guard? ((Likely))`` →
        strip the marker so the question can be classified

    The LLM GMAwareness verdict carries the authoritative intent; this
    helper only exists to clean the visible text used by intent /
    world-truth / target-extraction fallbacks and by the oracle's
    question display.
    """
    cleaned = (text or "").strip()
    # Standalone OOC wrapper: leading AND trailing ``((...))`` around
    # the whole message → unwrap to the inner content.
    match = re.match(r"^\s*\(\((.*?)\)\)\s*$", cleaned, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    # Otherwise just strip any embedded ``((...))`` marker (likelihood
    # hint, parenthetical aside, etc.) so intent classifiers can read
    # the rest of the sentence.
    cleaned = re.sub(r"\s*\(\(.*?\)\)\s*", " ", cleaned, flags=re.DOTALL)
    return cleaned.strip() or (text or "").strip()


def _extract_target(text: str) -> str:
    """Best-effort fallback used only when the LLM verdict didn't
    supply a target. The schema-aware path uses entity context instead."""
    stripped = _strip_ooc_wrappers(text).lower()
    for pattern in (
        r"\b(?:the|at|toward|towards|to|from)\s+([a-z][a-z0-9_\-']{2,})",
        r"\bwith\s+([a-z][a-z0-9_\-']{2,})",
    ):
        match = re.search(pattern, stripped)
        if match:
            return match.group(1)
    return "environment" if stripped.endswith("?") else "none"


def _is_world_truth_question(text: str) -> bool:
    """Coarse check used by the Oracle branch. The LLM verdict's
    intent_type is the authoritative signal for question routing; this
    only narrows to yes/no binary world-truths (e.g. "Is the door locked?").
    Anything more open-ended (``What should I know about…?``) falls through
    to the dice-or-trivial branches and gets a ``risk_preview``."""
    stripped = _strip_ooc_wrappers(text).lower()
    if not stripped.endswith("?"):
        return False
    starters = (
        "is ",
        "are ",
        "do ",
        "does ",
        "was ",
        "were ",
        "can ",
        "could ",
        "has ",
        "have ",
    )
    return any(stripped.startswith(s) for s in starters)


# Lookup-question starters — questions that ask "what is X" / "explain X"
# and need a RAG-based answer rather than a yes/no oracle response.
# These are detected by the LLM-side intent classifier (IntentType.LOOKUP)
# but this regex lets the resolver fall back to a LOOKUP routing when the
# LLM signal is unavailable.
_LOOKUP_STARTERS = (
    "what is",
    "what are",
    "what was",
    "what were",
    "who is",
    "who are",
    "who was",
    "who were",
    "tell me about",
    "tell us about",
    "explain",
    "describe",
    "define",
    "what does",
    "what do",
    "how is",
    "how are",
    "how does",
    "how do",
)


def _is_lookup_question(text: str) -> bool:
    """Coarse check used by the LOOKUP branch. Matches "what is X" /
    "explain X" patterns. The LLM verdict's intent_type is the
    authoritative signal for routing; this regex only kicks in when
    the LLM signal is missing or the verdict is unavailable."""
    stripped = _strip_ooc_wrappers(text).lower().rstrip("?.! ")
    if not stripped:
        return False
    return any(stripped.startswith(s) for s in _LOOKUP_STARTERS)


_LIKELIHOOD_MARKER_MAP = {
    "certain": "certain",
    "nearly certain": "nearly_certain",
    "very likely": "very_likely",
    "likely": "likely",
    "50/50": "50_50",
    "unlikely": "unlikely",
    "very unlikely": "very_unlikely",
    "nearly impossible": "nearly_impossible",
    "impossible": "impossible",
}


def _parse_likelihood_marker(text: str) -> str:
    """Return the OOC ``((…))`` likelihood marker, or ``"50_50"``.

    The Oracle branch threads this into ``Oracle.resolve_question`` so
    the GM can bias the answer from the player side. The marker is
    stripped from the displayed question by ``_strip_ooc_wrappers``.
    """
    match = re.search(r"\(\((.*?)\)\)", text or "")
    if match:
        key = match.group(1).strip().lower()
        if key in _LIKELIHOOD_MARKER_MAP:
            return _LIKELIHOOD_MARKER_MAP[key]
    return "50_50"


def _infer_intent_type(text: str, action_type: str) -> str:
    """Coarse intent default. The LLM verdict's intent_type is the
    authoritative signal; this only fills the gap when the LLM is
    silent or returned the safe fallback verdict."""
    stripped = _strip_ooc_wrappers(text).strip()
    if not stripped:
        return "meta"
    if stripped.startswith("/"):
        return "meta"
    if stripped.lower().startswith("ooc"):
        return "ooc"
    if stripped.endswith("?"):
        return "query"
    return "dialogue" if action_type == "dialogue" else "action"


def _build_risk_preview(action_type: str, stat_name: str | None, dc: int | None) -> str:
    """Return a short player-facing summary of what is at stake for this move."""
    stat_label = stat_name or "the relevant approach"
    dc_hint = f" around DC {dc}" if dc is not None else ""

    if action_type == "dialogue":
        return (
            f"Social pressure is in play here: pushing with {stat_label} can win leverage, "
            f"but it can also expose motives or harden the other side{dc_hint}."
        )
    if action_type == "query":
        return (
            "This is a clarification beat: the main risk is acting on incomplete information. "
            "Use the answer to decide whether to commit, retreat, or change approach."
        )
    return (
        f"This move carries concrete danger: failure can cost position, time, or resources, "
        f"and the check is likely to hinge on {stat_label}{dc_hint}."
    )


def _build_consequence_options(action_type: str, success_level: str) -> list[str]:
    """Offer player-facing consequence choices for mixed or pressured outcomes."""
    if success_level == "partial_success":
        if action_type == "dialogue":
            return [
                "Get the answer, but reveal a vulnerability.",
                "Hold your ground, but raise the NPC's suspicion.",
                "Keep the exchange calm, but lose momentum or leverage.",
            ]
        return [
            "Succeed, but spend extra time or a limited resource.",
            "Succeed, but attract danger or unwanted attention.",
            "Pull back to stay safe and give up immediate momentum.",
        ]

    if success_level in {"failure", "critical_failure"}:
        return [
            "Push through and accept a sharper setback.",
            "Back off, regroup, and try a different approach.",
            "Ask for more information before escalating the risk.",
        ]

    if success_level == "critical_success":
        return [
            "Press the advantage for extra information or position.",
            "Take the clean win and keep the scene stable.",
        ]

    return []


class Resolver(BaseAgent):
    """
    Agent responsible for resolving rules, mechanic checks, and character state changes.

    T5 (gm-tool-authority): the Resolver is now a THIN STATE-MACHINE. It builds
    scene state, asks the GMAgent to decide, and shapes the verdict into the
    legacy resolution dict. The semantic classifiers, action routing, and
    roll-necessity decisions live inside the GMAgent's ReAct loop — the
    Resolver just orchestrates the dice mechanics (when to roll, what
    modifiers apply, what the success level looks like) and packages the
    final dict for downstream consumers.

    Public surface unchanged. ``resolve_turn`` returns the same shape.
    """

    def __init__(
        self,
        agent_id: str = "resolver-cli-1",
        gm_agent: Any | None = None,
    ) -> None:
        super().__init__(agent_type="Resolver", agent_id=agent_id)
        # Lazy import to avoid circular dependency at module load.
        if gm_agent is None:
            from monitor_agents.gm_agent import default_gm_agent

            gm_agent = default_gm_agent()
        self._gm_agent = gm_agent

    async def _handle_lookup(
        self,
        question: str,
        universe_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Sub-plan 3 Task 2: RAG-based explanation handler for LOOKUP
        questions. Searches the entities, knowledge, and snippets
        Qdrant collections for the most relevant passages, then
        composes a structured answer with citations.

        Returns a resolution dict compatible with `_attach_gm_verdict`
        (so it flows through the same downstream contract), or None
        if the lookup could not be answered (in which case the caller
        falls through to the normal flow).

        The handler is deliberately conservative: it returns a structured
        answer with the top-3 hits from each collection, joined
        together. It does NOT call an LLM to compose the prose — the
        hits are presented as bullet points with citations, and the
        front-end (or a downstream narrator pass) can summarise.
        """
        from monitor_data.retrieval.service import RetrievalService

        question_clean = (question or "").strip().rstrip("?.! ")
        if not question_clean:
            return None
        # Without a universe the search would span every world's content.
        if not universe_id:
            return None

        # Try to identify the focal entity by extracting the noun phrase
        # after the lookup starter (e.g. "What is the Beast?" → "the Beast").
        focal = question_clean
        for starter in _LOOKUP_STARTERS:
            if question_clean.lower().startswith(starter):
                focal = question_clean[len(starter) :].strip()
                break
        # Strip leading articles / determiners for better matching.
        for prefix in ("the ", "a ", "an "):
            if focal.lower().startswith(prefix):
                focal = focal[len(prefix) :]
                break

        # Search across entities, knowledge, and snippets in parallel.
        # The retrieval service handles embedding + Qdrant search.
        try:
            retrieval = RetrievalService()
            filters = {"universe_id": universe_id}
            entity_hits = await retrieval.retrieve(
                "entities",
                question_clean,
                filters=filters,
                limit=3,
            )
            knowledge_hits = await retrieval.retrieve(
                "knowledge",
                question_clean,
                filters=filters,
                limit=3,
            )
            snippet_hits = await retrieval.retrieve(
                "snippets",
                question_clean,
                filters=filters,
                limit=3,
            )
        except Exception:  # noqa: BLE001  # reason: intentional boundary: documented failure tolerance (in _handle_lookup)
            # Don't break the resolver if retrieval is unavailable; the
            # caller will fall through to the normal flow.
            return None

        # Compose a structured answer. Each citation carries enough
        # metadata for the GM assistant UI to render it.
        answer_lines = [f"# {question.strip().rstrip('?.!')}", ""]
        citations: list[dict[str, Any]] = []

        if entity_hits:
            answer_lines.append("## Entities")
            for hit in entity_hits[:3]:
                payload = hit.payload or {}
                name = payload.get("name", "?")
                desc = payload.get("description", "")
                sub_type = payload.get("sub_type", "")
                group_type = payload.get("group_type", "")
                place_type = payload.get("place_type", "")
                meta_bits = [b for b in (sub_type, group_type, place_type) if b]
                meta = f" ({', '.join(meta_bits)})" if meta_bits else ""
                if desc:
                    answer_lines.append(f"- **{name}**{meta} — {desc}")
                else:
                    answer_lines.append(f"- **{name}**{meta}")
                citations.append(
                    {
                        "source": "entity",
                        "name": name,
                        "sub_type": sub_type,
                        "score": hit.score,
                    }
                )
            answer_lines.append("")

        if knowledge_hits:
            answer_lines.append("## Rules & facts")
            for hit in knowledge_hits[:3]:
                payload = hit.payload or {}
                text = payload.get("text", payload.get("statement", ""))
                node_type = payload.get("node_type", "")
                if text:
                    suffix = f" _{node_type}_" if node_type else ""
                    answer_lines.append(f"- {text}{suffix}")
                citations.append(
                    {
                        "source": "knowledge",
                        "node_type": node_type,
                        "score": hit.score,
                    }
                )
            answer_lines.append("")

        if snippet_hits:
            answer_lines.append("## Source passages")
            for hit in snippet_hits[:3]:
                payload = hit.payload or {}
                text = payload.get("text", "")
                section = payload.get("section_path") or payload.get("section") or ""
                page = payload.get("page_number", "")
                ref = f" ({section}, p. {page})" if page else (f" ({section})" if section else "")
                if text:
                    snippet = text[:240] + ("…" if len(text) > 240 else "")
                    answer_lines.append(f"- {snippet}{ref}")
                citations.append(
                    {
                        "source": "snippet",
                        "section": section,
                        "page": page,
                        "score": hit.score,
                    }
                )

        if not (entity_hits or knowledge_hits or snippet_hits):
            return None

        return {
            "scene_id": None,
            "action_type": "lookup",
            "intent_type": "lookup",
            "resolution_type": "rag_lookup",
            "answer": "\n".join(answer_lines),
            "focal_entity": focal,
            "citations": citations,
            "narrative_pressure": "stable",
            "proposals": [],
            "success": True,
            "success_level": "n/a",
        }

    async def run(self) -> None:
        pass

    def _default_action_profile(self) -> tuple[str, str, int]:
        """Final fallback for ``dice_standard`` mode (no schema loaded).

        The schema-driven path (``GameSystemRuntime.infer_action_context``)
        is preferred whenever a game system is loaded. This is the
        conservative default that gets used when no schema, no LLM
        verdict, and no keyword routing produced an action profile.
        """
        return _DEFAULT_ACTION_PROFILE

    # ------------------------------------------------------------------
    # Resolution + verdict hand-off
    # ------------------------------------------------------------------
    # ``resolve_turn`` returns ``(resolution_dict, gm_verdict)`` so the
    # Narrator downstream can refine the GM's draft against the outcome.
    # ``gm_verdict`` is ``None`` on paths where GMAgent didn't run (oracle,
    # narrative mode, propose_roll when GMAgent fell through to its seed)
    # or when the patched ``check_gm_awareness`` seam produced nothing —
    # the Narrator falls back to its legacy ``_generate`` path on ``None``.
    def _attach_gm_verdict(self, resolution: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
        """Finalize the resolver's return: pair the resolution dict with the
        most-recent ``GMVerdict`` (if any) captured during this turn.

        The verdict is also copied into ``resolution["_gm_verdict"]`` so
        existing callers that ignore the tuple still see the verdict
        should they look — but the canonical hand-off is the second tuple
        element.
        """
        verdict = getattr(self, "_last_gm_verdict", None)
        # Snapshot, then clear so the next turn doesn't leak the verdict.
        self._last_gm_verdict = None
        if verdict is not None:
            # Internal sentinel — Narrator's refine path prefers the tuple.
            resolution = dict(resolution)
            resolution["_gm_verdict"] = verdict
        return resolution, verdict

    async def _evaluate_scenery_and_conditions(
        self,
        context: dict[str, Any] | None,
        user_input: str,
        roll_mode: str = "normal",
        gsr: Optional["GameSystemRuntime"] = None,
    ) -> dict[str, Any]:
        """
        Evaluate actor conditions and active location scenery in the scene context.
        Calculates dynamic roll modifiers and resolves the actual roll mode.
        If a GameSystemRuntime is provided, delegates to it for system-specific logic.
        """
        if gsr:
            return await gsr.evaluate_scenery_and_conditions(context, user_input, roll_mode)

        # Base case (no modifiers) when no GameSystemRuntime is available
        return {
            "total_modifier": 0,
            "cond_modifier": 0,
            "scenery_modifier": 0,
            "roll_mode": roll_mode,
            "has_advantage": roll_mode == "advantage",
            "has_disadvantage": roll_mode == "disadvantage",
            "reasons": [],
            "conditions": [],
        }

    async def resolve_turn(
        self,
        scene_id: str,
        user_input: str,
        context: dict[str, Any] | None = None,
        game_context: dict[str, Any] | None = None,
        play_mode: str = "dice_game_system",
        roll_mode: str = "normal",
        tension_score: float = 0.5,
    ) -> tuple[dict[str, Any], Any | None]:
        """
        Resolve a full player turn for the SceneLoop.

        Returns ``(resolution_dict, gm_verdict)``. ``gm_verdict`` is the
        ``GMVerdict`` that GMAgent (or the patched ``check_gm_awareness``
        seam) produced for this turn — it carries the GM's ``narrative_draft``
        so the Narrator downstream can refine it against the outcome. It is
        ``None`` on paths where GMAgent didn't run (oracle, narrative mode,
        etc.) or fell through to its permissive seed.

        ``play_mode`` controls resolution behaviour:
        - ``"narrative"``        — pure fiction, no dice ever
        - ``"dice_standard"``    — d20 + modifier, no game-system schema
        - ``"dice_game_system"`` — schema-driven dice via GameSystemRuntime

        ``roll_mode`` controls advantage/disadvantage:
        - ``"normal"``       — standard 1d20 roll
        - ``"advantage"``    — roll 2d20, keep highest
        - ``"disadvantage"`` — roll 2d20, keep lowest

        In both dice modes the player can assert a narrative outcome directly
        (forced narrative); those turns are flagged so the GM can review them.
        """
        context = context or {}
        source_profile = context.get("source_profile", {}) if isinstance(context, dict) else {}

        # Auto-roll mode (solo / automated play): instead of pausing to ask the
        # player to roll (propose_roll → "pending"), the resolver rolls the dice
        # itself and returns a real outcome. Downstream advantage logic still
        # expects normal/advantage/disadvantage, so normalise roll_mode here.
        auto_roll = roll_mode == "auto"
        if auto_roll:
            roll_mode = "normal"

        # Initial action_type defaults to "action"; the LLM GMAwareness
        # verdict upgrades it later if a real call reached a completion.
        # Intent classification is mostly driven by the LLM verdict; we
        # only fill the gap with a coarse shape-based default.
        initial_action_type = "action"
        intent_type = _infer_intent_type(user_input or "", initial_action_type)

        # roll_type is a cosmetic label for the dice result; the LLM
        # verdict's action_type is what actually drove routing. Default
        # to "action" and let the schema-driven path override it.
        roll_type = "action"
        intent_target = _extract_target(user_input or "")
        requires_clarification = intent_type in ("meta", "ooc", "query")

        # ------------------------------------------------------------------
        # Branch 1 — Pure narrative mode: never roll dice
        # ------------------------------------------------------------------
        if play_mode == "narrative":
            return self._attach_gm_verdict(
                {
                    "scene_id": scene_id,
                    "action_type": "action",
                    "intent_type": intent_type,
                    "roll_type": roll_type,
                    "intent_target": intent_target,
                    "requires_clarification": requires_clarification,
                    "stat": None,
                    "difficulty_class": None,
                    "attribute_value": None,
                    "modifier": None,
                    "roll_total": None,
                    "roll_breakdown": "narrative — no roll",
                    "resolution_type": "narrative",
                    "forced_narrative": False,
                    "success": True,
                    "success_level": "success",
                    "effects": ["fiction_advances"],
                    "risk_preview": _build_risk_preview(intent_type, None, None),
                    "consequence_options": [],
                    "requires_player_choice": False,
                    "narrative_pressure": "steady",
                    "proposals": [],
                }
            )

        # ------------------------------------------------------------------
        # Branch 2 — Forced narrative / causality (LLM-driven via GMAwareness)
        # ------------------------------------------------------------------
        # The GM (LLM) consciously reads the player's text and decides:
        #   1. Did the player DECLARE a completed outcome?
        #   2. If so, does it violate causality (deus ex machina, skipped
        #      rolls, contradicted facts)?
        #   3. What should the resolver do? (ACCEPT / PUSH_BACK /
        #      REQUEST_CLARIFICATION / NARRATIVE_OVERRIDE)
        #
        # NO regex, NO keyword lists. The LLM's structured verdict drives
        # routing. If the LLM says the player is ATTEMPTING (not declaring),
        # we fall through to Branch 3 (dice resolution).
        # ------------------------------------------------------------------
        scene_context_for_awareness: dict[str, Any] = dict(context or {})
        scene_context_for_awareness.setdefault("entities", [])
        scene_context_for_awareness.setdefault("turns", [])
        scene_context_for_awareness.setdefault("source_profile", {})
        # Session-Zero table agreements (lines and veils) are session-scoped
        # player constraints, not canon. The GMAgent and downstream nar-
        # rative nodes must see them so prompt instructions can override
        # the LLM's normal willingness to depict restricted content.
        if "agreements" not in scene_context_for_awareness:
            scene_context_for_awareness["agreements"] = {
                "lines": [],
                "veils": [],
            }

        established_facts: list[str] = []
        sp = scene_context_for_awareness.get("source_profile") or {}
        if isinstance(sp, dict):
            established_facts = list(sp.get("established_facts") or [])
            scene_context_for_awareness["character_name"] = sp.get("character_name") or sp.get("name") or "the player"
            scene_context_for_awareness["character_role"] = sp.get("class") or sp.get("role") or "adventurer"

        # T5: Run the GMAgent to decide. The verdict carries intent_type,
        # action_type, roll_necessity, causality_action, suggested_stat,
        # suggested_dc — same surface as the previous GMAwareness. The
        # resolver shapes the verdict into the legacy resolution dict
        # downstream. When GMAgent fails entirely we fall back to the
        # GMAwareness seed (and ultimately to the permissive propose-roll
        # fallback), preserving prior behavior.
        #
        # Backward compat: tests (and third-party callers) that patch
        # ``monitor_agents.resolver.check_gm_awareness`` continue to work.
        # When the patched function is detected, the resolver delegates
        # to it and converts the result to a GMVerdict for the rest of
        # the pipeline. This preserves the existing test seam.
        gm_verdict: Any | None = None

        # Detect a patched check_gm_awareness — if the module-level binding
        # is no longer the original function, the test has overridden it.
        check_gm_awareness_patched = (
            getattr(check_gm_awareness, "__module__", None) is not None
            and check_gm_awareness is not _ORIGINAL_CHECK_GM_AWARENESS
        )

        if check_gm_awareness_patched:
            # Honor the patched function — its return is a GMAwareness.
            # We ``await`` it because test fixtures sometimes wrap the
            # already-async ``check_gm_awareness`` in ``AsyncMock``, and
            # calling an AsyncMock without ``await`` returns the mock (not
            # its configured value).
            try:
                patched_result = check_gm_awareness(
                    agent=self,
                    user_input=user_input or "",
                    scene_context=scene_context_for_awareness,
                    play_mode=play_mode or "",
                    established_facts=established_facts,
                    roll_mode=(auto_roll and "auto") or "normal",
                )
                if asyncio.iscoroutine(patched_result):
                    patched_result = await patched_result  # type: ignore[assignment]
                from monitor_agents.gm_agent import gmverdict_from_awareness

                gm_verdict = gmverdict_from_awareness(patched_result, upstream_action_context=None)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001  # reason: falls back to `None` on failure (in resolve_turn)
                gm_verdict = None
        else:
            # Production path: GMAgent ReAct loop + fall through to seed.
            try:
                gm_verdict = await self._gm_agent.decide(
                    scene_id=str(scene_id),
                    user_input=user_input or "",
                    scene_context=scene_context_for_awareness,
                    source_profile=scene_context_for_awareness.get("source_profile"),
                    game_context=game_context,
                    established_facts=established_facts,
                    upstream_action_context=None,
                    upstream_pending_roll=context.get("pending_roll") if isinstance(context, dict) else None,
                    play_mode=play_mode or "dice_game_system",
                    roll_mode=(auto_roll and "auto") or "normal",
                )
            except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in resolve_turn)
                logger.warning(
                    "GMAgent.decide raised unexpectedly (%s); falling through to seed verdict",
                    exc,
                )
                gm_verdict = None

        # Stash the verdict so every return path below can pair it with the
        # resolution dict. We capture BEFORE the null-on-attempting branch
        # below so dice turns still surface the GM's draft to the Narrator
        # (the Narrator reconciles draft against the rolled outcome).
        self._last_gm_verdict = gm_verdict  # type: ignore[assignment]

        question_resolution = await self._route_question(
            scene_id, user_input or "", context, tension_score, gm_verdict, intent_type
        )
        if question_resolution is not None:
            # Oracle and lookup outcomes are the answer; a draft written without
            # them would contradict it, so the Narrator works from the outcome.
            self._last_gm_verdict = None
            return self._attach_gm_verdict(question_resolution)

        # Capture the LLM verdict's roll_necessity *before* we may null the
        # verdict below — it's the principled fallback for the semantic
        # classifier (used only when embeddings are unavailable). No keywords.
        #
        # ``llm_verdict_was_real`` distinguishes "real" LLM reach (any
        # action_type other than the fallback's NONE) from the permissive
        # "GM-awareness unavailable" fallback that gm_awareness.py returns on
        # DSPy failure — the latter hard-codes propose-roll and would bias
        # every classification if we trusted it.
        llm_roll_necessity: str | None = None
        llm_verdict_was_real: bool = False
        if gm_verdict is not None:
            try:
                llm_roll_necessity = gm_verdict.roll_necessity.value
                llm_verdict_was_real = gm_verdict.action_type != ActionType.NONE
            except Exception:  # noqa: BLE001  # reason: falls back to `None` on failure (in resolve_turn)
                llm_roll_necessity = None
                llm_verdict_was_real = False

        # Kept for the dice branch: the verdict is nulled below on attempted actions.
        gm_stat: str | None = None
        gm_dc: int | None = None
        gm_action: ActionType | None = None
        gm_intent: str | None = None
        if gm_verdict is not None and llm_verdict_was_real:
            gm_stat = gm_verdict.suggested_stat
            gm_dc = gm_verdict.suggested_dc
            gm_action = gm_verdict.action_type
            gm_intent = gm_verdict.intent_type.value

        gsr: GameSystemRuntime | None = None
        if play_mode == "dice_game_system" and game_context:
            with suppress(Exception):
                gsr = GameSystemRuntime(game_context)

        # If the LLM says the player is ATTEMPTING (not declaring), fall
        # through to Branch 3 (dice resolution).
        if gm_verdict is not None and not gm_verdict.declares_outcome:
            gm_verdict = None  # route through dice resolution below

        # PUSH_BACK → request a roll from the player
        if gm_verdict is not None and gm_verdict.causality_action == CausalityAction.PUSH_BACK:
            suggested_stat = (
                (gm_verdict.suggested_stat and gsr and _system_stat(gsr, gm_verdict.suggested_stat))
                or gm_verdict.suggested_stat
                or "Strength"
            )
            suggested_dc = gm_verdict.suggested_dc or 12
            pushback_value, pushback_base_mod = self._actor_stat(context, gsr, suggested_stat)
            pushback_sc = await self._evaluate_scenery_and_conditions(context, user_input or "", roll_mode, gsr)
            pushback_modifier = pushback_base_mod + pushback_sc["total_modifier"]
            pushback_roll_mode = pushback_sc.get("roll_mode") or roll_mode or "normal"
            if pushback_roll_mode not in ("normal", "advantage", "disadvantage"):
                pushback_roll_mode = "normal"
            pushback_pool = _pool_proposal_fields(gsr, pushback_value, pushback_modifier)
            if pushback_pool:
                pushback_roll_mode = "normal"
            return self._attach_gm_verdict(
                {
                    "scene_id": scene_id,
                    "action_type": "action",
                    "intent_type": intent_type,
                    "roll_type": roll_type,
                    "intent_target": intent_target,
                    "requires_clarification": False,
                    "stat": suggested_stat,
                    "difficulty_class": suggested_dc,
                    "attribute_value": pushback_value,
                    "modifier": pushback_modifier,
                    "roll_mode": pushback_roll_mode,
                    "roll_under": _uses_roll_under(gsr),
                    **pushback_pool,
                    "resolution_type": "forced_narrative_pushback",
                    "forced_narrative": True,
                    "success": None,
                    "success_level": "pending",
                    "pushback_prompt": gm_verdict.pushback_prompt
                    or (f"That's a bold claim — roll {suggested_stat} (DC {suggested_dc}) to see if it lands."),
                    "causality_reasons": list(gm_verdict.reasons or []),
                    "causality_severity": gm_verdict.severity,
                    "requires_player_choice": True,
                    "narrative_pressure": "spiking",
                    "proposals": [],
                    "gm_reasoning": gm_verdict.reasoning,
                }
            )

        # REQUEST_CLARIFICATION → ask the player for missing info
        if gm_verdict is not None and gm_verdict.causality_action == CausalityAction.REQUEST_CLARIFICATION:
            return self._attach_gm_verdict(
                {
                    "scene_id": scene_id,
                    "action_type": "action",
                    "intent_type": intent_type,
                    "roll_type": roll_type,
                    "intent_target": intent_target,
                    "requires_clarification": True,
                    "stat": None,
                    "difficulty_class": None,
                    "resolution_type": "forced_narrative_clarification",
                    "forced_narrative": True,
                    "success": None,
                    "success_level": "pending",
                    "pushback_prompt": gm_verdict.pushback_prompt or "Can you clarify where that came from?",
                    "causality_reasons": list(gm_verdict.reasons or []),
                    "causality_severity": gm_verdict.severity,
                    "requires_player_choice": True,
                    "narrative_pressure": "steady",
                    "proposals": [],
                    "gm_reasoning": gm_verdict.reasoning,
                }
            )

        # ACCEPT / NARRATIVE_OVERRIDE → declared outcome advances without a roll
        if gm_verdict is not None and gm_verdict.causality_action in (
            CausalityAction.ACCEPT,
            CausalityAction.NARRATIVE_OVERRIDE,
        ):
            return self._attach_gm_verdict(
                {
                    "scene_id": scene_id,
                    "action_type": "action",
                    "intent_type": intent_type,
                    "roll_type": roll_type,
                    "intent_target": intent_target,
                    "requires_clarification": requires_clarification,
                    "stat": None,
                    "difficulty_class": None,
                    "attribute_value": None,
                    "modifier": None,
                    "roll_total": None,
                    "roll_breakdown": "forced narrative — player declared outcome",
                    "resolution_type": "forced_narrative",
                    "forced_narrative": True,
                    "success": True,
                    "success_level": "success",
                    "effects": ["fiction_advances"],
                    "risk_preview": _build_risk_preview(intent_type, None, None),
                    "consequence_options": [],
                    "requires_player_choice": False,
                    "narrative_pressure": "surging",
                    "proposals": [],
                    "gm_reasoning": gm_verdict.reasoning,
                }
            )

        # Unknown / no-verdict / declares_outcome=False → fall through to dice

        # ------------------------------------------------------------------
        # Branch 3 — Dice resolution (dice_standard or dice_game_system)
        # ------------------------------------------------------------------
        # Action routing and modifier calculation via schema (dice_game_system)
        # or simple generic fallback (dice_standard)
        if _is_narrative_core(gsr):
            return self._attach_gm_verdict(
                {
                    "scene_id": scene_id,
                    "action_type": "action",
                    "intent_type": intent_type,
                    "roll_type": roll_type,
                    "intent_target": intent_target,
                    "requires_clarification": requires_clarification,
                    "stat": None,
                    "difficulty_class": None,
                    "attribute_value": None,
                    "modifier": None,
                    "roll_total": None,
                    "roll_breakdown": "narrative system — no roll",
                    "resolution_type": "narrative",
                    "forced_narrative": False,
                    "success": True,
                    "success_level": "success",
                    "effects": ["fiction_advances"],
                    "risk_preview": _build_risk_preview(intent_type, None, None),
                    "consequence_options": [],
                    "requires_player_choice": False,
                    "narrative_pressure": "steady",
                    "proposals": [],
                    "subsystem_hint": None,
                }
            )

        subsystem_hint = None
        if gsr:
            routed = await gsr.infer_action_context(user_input, source_profile=source_profile)
            action_type = str(routed.get("action_type", "action"))
            stat_name = (gm_stat and _system_stat(gsr, gm_stat)) or str(routed.get("stat_name", "STR"))
            dc = _resolve_base_dc(gsr, int(routed.get("difficulty_class", 12)))
            subsystem_hint = routed.get("subsystem_hint")
        else:
            action_type, _, dc = self._default_action_profile()
            stat_name = gm_stat or await _infer_generic_stat(user_input or "")
            subsystem_hint = None

        # The GM is the authority on the roll when it gave a usable answer.
        if gm_dc and 0 < gm_dc <= _MAX_GM_DC:
            dc = gm_dc
        if gm_action in _GM_ACTION_TYPES:
            action_type = gm_action.value
            if gsr is None and gm_action == ActionType.DIALOGUE:
                subsystem_hint = "social"

        # ------------------------------------------------------------------
        # Roll necessity classification (UC-GM-6)
        # Only roll when failure would be interesting and outcome uncertain.
        # A selected dice-backed system controls *how* to roll, not whether
        # ordinary risky actions bypass player consent.
        #
        # The LLM GMAwareness verdict (when its DSPy call reached a real
        # completion — *not* the permissive propose-roll fallback) is the
        # authority. When the verdict isn't real (LLM silent or degraded to
        # the safe seed), we do NOT trust its necessity — a permissive
        # ``propose_roll`` seed would mask genuinely contested actions.
        # Instead we fall back to ``_fallback_roll_necessity``, a thin
        # intent→necessity map. ``llm_verdict_was_real`` distinguishes them.
        # ------------------------------------------------------------------
        intent_type = gm_intent or _infer_intent_type(user_input or "", action_type)
        if llm_verdict_was_real and llm_roll_necessity in _VALID_NECESSITY:
            roll_necessity = llm_roll_necessity
        else:
            roll_necessity = _fallback_roll_necessity(intent_type)

        # ------------------------------------------------------------------
        # Pending roll auto-resolution (server-authoritative)
        # ------------------------------------------------------------------
        # If the previous turn PROPOSED a roll, resolve it here: roll on the
        # server using the proposed spec and let the Narrator weave the outcome.
        # We deliberately do NOT gate the narrative behind a magic keyword
        # ("roll"/"dice"). That keyword parser was brittle and produced a
        # stuck-`pending` loop whenever the player narrated naturally instead of
        # typing the trigger word. A structured roll action (the player tapping
        # the die) and an explicit "I roll" now land here and resolve
        # identically — never a pushback nag.
        pending_roll = context.get("pending_roll") if isinstance(context, dict) else None
        if pending_roll and not auto_roll:
            pr_stat = str(pending_roll.get("stat") or stat_name or "the relevant stat")
            pr_dc = pending_roll.get("dc")
            pr_modifier = int(pending_roll.get("modifier") or 0)
            pr_roll_mode = pending_roll.get("roll_mode") or roll_mode
            if pr_roll_mode not in ("normal", "advantage", "disadvantage"):
                pr_roll_mode = "normal"
            return self._attach_gm_verdict(
                self._execute_roll(
                    scene_id=scene_id,
                    user_input=user_input or "",
                    action_type=action_type,
                    roll_type=roll_type,
                    intent_target=intent_target,
                    requires_clarification=False,
                    stat_name=pr_stat,
                    dc=int(pr_dc) if pr_dc is not None else int(dc),
                    stat_value=pending_roll.get("attribute_value"),
                    base_modifier=pr_modifier,
                    modifier=pr_modifier,
                    actual_roll_mode=pr_roll_mode,
                    gsr=gsr,
                    subsystem_hint=subsystem_hint,
                    roll_necessity="pending_roll",
                    intent_type=gm_intent,
                )
            )

        if roll_necessity == "trivial":
            return self._attach_gm_verdict(
                {
                    "scene_id": scene_id,
                    "action_type": action_type,
                    "intent_type": intent_type,
                    "roll_type": roll_type,
                    "intent_target": intent_target,
                    "requires_clarification": requires_clarification,
                    "stat": stat_name,
                    "difficulty_class": dc,
                    "attribute_value": None,
                    "modifier": None,
                    "roll_total": None,
                    "roll_breakdown": "trivial — no roll needed",
                    "resolution_type": "trivial",
                    "forced_narrative": False,
                    "success": True,
                    "success_level": "success",
                    "effects": ["fiction_advances"],
                    "risk_preview": "This is a routine action — no stakes beyond the narrative.",
                    "consequence_options": [],
                    "requires_player_choice": False,
                    "narrative_pressure": "steady",
                    "proposals": [],
                    "subsystem_hint": subsystem_hint,
                    "roll_necessity": roll_necessity,
                }
            )

        if roll_necessity == "propose_roll" and not auto_roll:
            # Compute the stat context but do NOT roll dice.
            # The Narrator will frame the invitation for the player to accept.
            stat_value, base_modifier = self._actor_stat(context, gsr, stat_name)
            sc_eval = await self._evaluate_scenery_and_conditions(context, user_input or "", roll_mode, gsr)
            dynamic_mod = int(sc_eval["total_modifier"])
            modifier = base_modifier + dynamic_mod
            actual_roll_mode = sc_eval.get("roll_mode") or roll_mode or "normal"
            if actual_roll_mode not in ("normal", "advantage", "disadvantage"):
                actual_roll_mode = "normal"
            pool_fields = _pool_proposal_fields(gsr, stat_value, dynamic_mod)
            if pool_fields:
                actual_roll_mode = "normal"
                breakdown = (
                    f"propose_roll — {stat_name} pool "
                    f"({pool_fields['pool_size']}d{pool_fields['pool_die_sides']}, "
                    f"diff {pool_fields['success_threshold']})"
                )
            else:
                breakdown = f"propose_roll — {stat_name} check (DC {dc})"

            return self._attach_gm_verdict(
                {
                    "scene_id": scene_id,
                    "action_type": action_type,
                    "intent_type": intent_type,
                    "roll_type": roll_type,
                    "intent_target": intent_target,
                    "requires_clarification": requires_clarification,
                    "stat": stat_name,
                    "difficulty_class": dc,
                    "attribute_value": stat_value,
                    "modifier": modifier,
                    "roll_mode": actual_roll_mode,
                    "roll_total": None,
                    "roll_breakdown": breakdown,
                    "resolution_type": "propose_roll",
                    "forced_narrative": False,
                    "success": None,
                    "success_level": "pending",
                    "effects": [],
                    "risk_preview": _build_risk_preview(intent_type, stat_name, dc),
                    "consequence_options": [],
                    "requires_player_choice": True,
                    "narrative_pressure": "rising",
                    "proposals": [],
                    "subsystem_hint": subsystem_hint,
                    "roll_necessity": roll_necessity,
                    "roll_under": _uses_roll_under(gsr),
                    **pool_fields,
                    "roll_invitation": (
                        f"That sounds risky — roll your {stat_name} for me."
                        if dc is not None
                        else f"That could go wrong — shall I roll {stat_name}?"
                    ),
                }
            )

        # roll_necessity == "contested" → proceed with dice
        stat_value, base_modifier = self._actor_stat(context, gsr, stat_name)

        # Evaluate scenery and conditions for dynamic adjustments
        sc_eval = await self._evaluate_scenery_and_conditions(context, user_input or "", roll_mode, gsr)
        dynamic_mod = sc_eval["total_modifier"]
        actual_roll_mode = sc_eval["roll_mode"]
        modifier = base_modifier + dynamic_mod

        return self._attach_gm_verdict(
            self._execute_roll(
                scene_id=scene_id,
                user_input=user_input or "",
                action_type=action_type,
                roll_type=roll_type,
                intent_target=intent_target,
                requires_clarification=requires_clarification,
                stat_name=stat_name,
                dc=dc,
                stat_value=stat_value,
                base_modifier=base_modifier,
                modifier=modifier,
                actual_roll_mode=actual_roll_mode,
                gsr=gsr,
                subsystem_hint=subsystem_hint,
                roll_necessity=roll_necessity,
                sc_eval=sc_eval,
                intent_type=gm_intent,
            )
        )

    async def _route_question(
        self,
        scene_id: str,
        user_input: str,
        context: dict[str, Any],
        tension_score: float,
        gm_verdict: Any | None,
        shape_intent: str,
    ) -> dict[str, Any] | None:
        """Answer the turn from the oracle or from retrieval when it is a question.

        A real GM verdict decides. Text shape is only consulted when there is no
        real verdict, because a line like "Can I pick the lock?" is an action and
        "Explain to the guard..." is dialogue.
        """
        gm_intent = getattr(gm_verdict, "intent_type", None)
        verdict_is_real = gm_verdict is not None and not (
            gm_intent == IntentType.ACTION and gm_verdict.action_type == ActionType.NONE
        )

        if verdict_is_real:
            wants_lookup = gm_intent == IntentType.LOOKUP
            wants_oracle = gm_intent == IntentType.QUERY and _is_world_truth_question(user_input)
        else:
            wants_lookup = shape_intent != "query" and _is_lookup_question(user_input)
            wants_oracle = shape_intent == "query" and _is_world_truth_question(user_input)

        if wants_lookup:
            lookup = await self._handle_lookup(question=user_input, universe_id=context.get("universe_id"))
            if lookup is not None:
                return lookup

        if wants_oracle:
            from monitor_agents.oracle import Likelihood, Oracle

            oracle_res = Oracle().resolve_question(
                question=user_input,
                likelihood=Likelihood(_parse_likelihood_marker(user_input)),
                tension_score=tension_score,
            )
            return {
                "scene_id": scene_id,
                "action_type": "query",
                "intent_type": "query",
                "resolution_type": "oracle",
                "oracle_result": oracle_res,
                "success": oracle_res["is_yes"],
                "success_level": oracle_res["outcome"],
                "narrative_pressure": "increased" if oracle_res["is_exceptional"] else "stable",
                "proposals": [],
            }
        return None

    def _execute_roll(
        self,
        *,
        scene_id: str,
        user_input: str,
        action_type: str,
        roll_type: str,
        intent_target: str,
        requires_clarification: bool,
        stat_name: str,
        dc: int,
        stat_value: Any,
        base_modifier: int,
        modifier: int,
        actual_roll_mode: str,
        gsr: "GameSystemRuntime | None",
        subsystem_hint: Any,
        roll_necessity: str,
        sc_eval: dict[str, Any] | None = None,
        intent_type: str | None = None,
    ) -> dict[str, Any]:
        """Roll dice server-side and grade the outcome into a resolution dict.

        Single source of truth for turning a ``(stat, dc, modifier, roll_mode)``
        spec into a graded ``resolution_type == "dice"`` outcome. The roll is
        performed here on the server — authoritative, never trusted from the
        client. Callers: the contested/normal dice branch of ``resolve_turn``,
        the pending-roll auto-resolution path (player narrated past a proposed
        roll), and the structured roll action (player tapped the die).

        ``sc_eval`` (scenery/conditions evaluation) is optional; when omitted no
        dynamic-modifier explanation is appended (used by the pending path,
        where the proposed modifier is already final).
        """
        sc_eval = sc_eval or {"cond_modifier": 0, "scenery_modifier": 0, "reasons": []}

        explain_parts = []
        if sc_eval.get("cond_modifier", 0) != 0:
            explain_parts.append(f"conditions: {sc_eval['cond_modifier']}")
        if sc_eval.get("scenery_modifier", 0) != 0:
            reasons_str = f" ({', '.join(sc_eval.get('reasons') or [])})" if sc_eval.get("reasons") else ""
            explain_parts.append(f"scenery: {sc_eval['scenery_modifier']}{reasons_str}")

        explain_str = ""
        if explain_parts:
            explain_str = f" [base: {base_modifier}, " + ", ".join(explain_parts) + "]"

        if gsr and _is_count_successes_pool(gsr._sd.core):
            from monitor_agents.dice import default_dice_registry

            core = gsr._sd.core
            die_sides = _pool_die_sides(core)
            threshold = _parse_pool_threshold(core.get("success_threshold", 6), die_sides=die_sides)
            pool_bonus = int(modifier) - int(base_modifier)
            try:
                pool_size = int(stat_value) + pool_bonus if stat_value is not None else 1 + pool_bonus
            except (ValueError, TypeError):
                pool_size = 1
            if pool_size < 1:
                pool_size = 1

            if die_sides == 10:
                engine = default_dice_registry.get("pool")
                roll_res = engine.resolve_check(pool_size=pool_size, difficulty=threshold)
                total = roll_res.successes
                botched = roll_res.botches > 0 and total == 0
                raw_rolls = roll_res.raw_rolls
            else:
                pool_res = roll_dice(f"{pool_size}d{die_sides}")
                total = sum(1 for r in pool_res.rolls if r >= threshold)
                botched = any(r == 1 for r in pool_res.rolls) and total == 0
                raw_rolls = pool_res.rolls

            if botched:
                success_level = "critical_failure"
            elif total >= 1:
                success_level = "success"
            else:
                success_level = "failure"

            mode_label = "normal"
            actual_roll_mode = "normal"
            roll_formula = f"{pool_size}d{die_sides}"
            rolls = raw_rolls
            kept_rolls = raw_rolls

            spec = f"{pool_size}d{die_sides}"
            roll_breakdown = f"Pool {pool_size} ({rolls}): {total} successes (diff {threshold}){explain_str}"
            roll_reason = f"{stat_name} check (pool {pool_size}, diff {threshold}){explain_str}"
        else:
            roll_under = _uses_roll_under(gsr)
            # Select roll formula based on actual_roll_mode (roll-under inverts kh/kl)
            if actual_roll_mode == "advantage":
                roll_formula = "2d20kl1" if roll_under else "2d20kh1"
                mode_label = "advantage"
            elif actual_roll_mode == "disadvantage":
                roll_formula = "2d20kh1" if roll_under else "2d20kl1"
                mode_label = "disadvantage"
            else:
                roll_formula = "1d20"
                mode_label = "normal"

            roll = roll_dice(roll_formula)
            rolls = roll.rolls
            kept_rolls = roll.kept_rolls if roll.kept_rolls else roll.rolls
            natural = kept_rolls[0] if kept_rolls else (rolls[0] if rolls else roll.total)
            total = roll.total + modifier

            if roll_under:
                target = dc + modifier
                if natural == 1:
                    success_level = "critical_success"
                elif natural == 20:
                    success_level = "critical_failure"
                elif natural <= target:
                    success_level = "success"
                elif natural <= target + 2:
                    success_level = "partial_success"
                else:
                    success_level = "failure"
            else:
                if natural == 20:
                    success_level = "critical_success"
                elif natural == 1:
                    success_level = "critical_failure"
                elif total >= dc:
                    success_level = "success"
                elif total >= dc - 2:
                    success_level = "partial_success"
                else:
                    success_level = "failure"

            if roll_under:
                spec = roll_formula
            else:
                spec = f"{roll_formula}+{modifier}" if modifier >= 0 else f"{roll_formula}{modifier}"

            if roll_under:
                target = dc + modifier
                roll_breakdown = f"{roll_formula}({natural}) <= {dc} + {modifier} = {target}{explain_str}"
                roll_reason = f"{stat_name} check (target {target}, roll-under, {mode_label}){explain_str}"
            else:
                roll_breakdown = f"{roll_formula}({natural}) + {modifier} = {total} vs DC {dc}{explain_str}"
                roll_reason = f"{stat_name} check (DC {dc}, {mode_label}){explain_str}"

        effects = []
        if success_level in {"success", "critical_success"}:
            effects.append("momentum_gained")
        elif success_level == "partial_success":
            effects.append("mixed_outcome")
        else:
            effects.append("setback")

        if action_type == "dialogue":
            effects.append("npc_reacts")
        else:
            effects.append("fiction_advances")

        intent_type = intent_type or _infer_intent_type(user_input or "", action_type)
        consequence_options = _build_consequence_options(
            intent_type if intent_type != "action" else action_type, success_level
        )
        requires_player_choice = success_level == "partial_success" and bool(consequence_options)
        narrative_pressure = {
            "critical_success": "surging",
            "success": "steady",
            "partial_success": "rising",
            "failure": "high",
            "critical_failure": "spiking",
        }.get(success_level, "steady")

        return {
            "scene_id": scene_id,
            "action_type": action_type,
            "intent_type": intent_type,
            "roll_type": roll_type,
            "intent_target": intent_target,
            "requires_clarification": requires_clarification,
            "stat": stat_name,
            "difficulty_class": dc,
            "attribute_value": stat_value,
            "modifier": modifier,
            "roll_total": total,
            "roll_breakdown": roll_breakdown,
            "roll_detail": {
                "spec": spec,
                "total": total,
                "rolls": rolls,
                "kept_rolls": kept_rolls,
                "reason": roll_reason,
                "roll_mode": actual_roll_mode,
            },
            "resolution_type": "dice",
            "forced_narrative": False,
            "success": success_level in {"success", "critical_success"},
            "success_level": success_level,
            "effects": effects,
            "risk_preview": _build_risk_preview(intent_type if intent_type != "action" else action_type, stat_name, dc),
            "consequence_options": consequence_options,
            "requires_player_choice": requires_player_choice,
            "narrative_pressure": narrative_pressure,
            "proposals": [],
            "subsystem_hint": subsystem_hint,
            "roll_necessity": roll_necessity,
            "roll_mode": actual_roll_mode,
            "opposed_target": None,
            "opposed_target_roll": None,
            "opposed_margin": None,
        }

    async def resolve_opposed_check(
        self,
        actor_id: str,
        target_id: str,
        stat_name: str,
        context: dict[str, Any],
        gsr: GameSystemRuntime | None = None,
        roll_mode: str = "normal",
    ) -> dict[str, Any]:
        """
        Resolve an opposed check between two entities.

        Both roll 1d20 + modifier. Higher total wins.
        Returns the winner, margin, and both roll details.

        Used for combat (attack vs defense), contested social checks,
        and any situation where two actors directly oppose each other.
        """
        # 1. Extract attributes for both actors
        actor_attrs = {}
        target_attrs = {}
        for entity in context.get("entities", []):
            props = entity.get("properties", {}) if isinstance(entity, dict) else {}
            eid = str(entity.get("id", ""))
            if eid == str(actor_id):
                if isinstance(props, dict):
                    nested = props.get("attributes", {})
                    if isinstance(nested, dict) and nested:
                        actor_attrs = {k: int(v) for k, v in nested.items() if isinstance(v, (int, float))}
                    else:
                        actor_attrs = {k: int(v) for k, v in props.items() if isinstance(v, (int, float))}
            elif eid == str(target_id) and isinstance(props, dict):
                nested = props.get("attributes", {})
                if isinstance(nested, dict) and nested:
                    target_attrs = {k: int(v) for k, v in nested.items() if isinstance(v, (int, float))}
                else:
                    target_attrs = {k: int(v) for k, v in props.items() if isinstance(v, (int, float))}

        # 2. Calculate modifiers
        actor_stat = 0
        for key in (stat_name, stat_name.upper(), stat_name.lower(), stat_name.title()):
            if key in actor_attrs:
                actor_stat = int(actor_attrs[key])
                break

        target_stat = 0
        for key in (stat_name, stat_name.upper(), stat_name.lower(), stat_name.title()):
            if key in target_attrs:
                target_stat = int(target_attrs[key])
                break

        actor_mod = (
            gsr.calc_modifier(stat_name, actor_stat)
            if gsr
            else calculate_modifier(actor_stat, _DEFAULT_MODIFIER_FORMULA)
        )
        target_mod = (
            gsr.calc_modifier(stat_name, target_stat)
            if gsr
            else calculate_modifier(target_stat, _DEFAULT_MODIFIER_FORMULA)
        )

        # 3. Select roll formulas based on system type
        m_type = "d20"
        if gsr and gsr._sd.core:
            m_type = gsr._sd.core.get("type", "d20").lower()

        if "d20" in m_type:
            if roll_mode == "advantage":
                formula = "2d20kh1"
            elif roll_mode == "disadvantage":
                formula = "2d20kl1"
            else:
                formula = "1d20"

            # 4. Roll for both
            actor_roll = roll_dice(formula)
            target_roll = roll_dice(formula)

            actor_total = actor_roll.total + actor_mod
            target_total = target_roll.total + target_mod

            actor_natural = (
                actor_roll.kept_rolls[0] if actor_roll.kept_rolls else (actor_roll.rolls[0] if actor_roll.rolls else 0)
            )
            target_natural = (
                target_roll.kept_rolls[0]
                if target_roll.kept_rolls
                else (target_roll.rolls[0] if target_roll.rolls else 0)
            )

        elif "dice_pool" in m_type:
            # Sub-plan 4: route pool-vs-difficulty games through the
            # VtM V20 dice engine. Provides hunger dice, willpower
            # reroll, and bestial-failure detection that the old
            # hand-rolled branch lacked. Hunger dice are passed via
            # context (0 by default; callers can extend).
            from monitor_agents.dice import default_dice_registry

            threshold = 6
            if gsr and gsr._sd.core:
                threshold = _parse_pool_threshold(
                    gsr._sd.core.get("success_threshold", 6),
                    die_sides=_pool_die_sides(gsr._sd.core),
                )

            engine = default_dice_registry.get("pool")
            # Resources aren't in the resolver signature today, so we
            # pass None context. The engine still does the right thing.
            actor_roll = engine.resolve_check(
                pool_size=actor_stat,
                difficulty=threshold,
            )
            target_roll = engine.resolve_check(
                pool_size=target_stat,
                difficulty=threshold,
            )

            actor_total = actor_roll.successes
            target_total = target_roll.successes

            actor_natural = actor_total
            target_natural = target_total

            # For dice pools, success level is based on number of successes
            actor_mod = 0  # Not used for pools
            target_mod = 0
        else:
            # Fallback to d20
            formula = "1d20"
            actor_roll = roll_dice(formula)
            target_roll = roll_dice(formula)
            actor_total = actor_roll.total + actor_mod
            target_total = target_roll.total + target_mod
            actor_natural = actor_roll.rolls[0] if actor_roll.rolls else 0
            target_natural = target_roll.rolls[0] if target_roll.rolls else 0

        # 5. Determine winner
        margin = actor_total - target_total
        if margin > 0:
            winner = "actor"
            success_level = "success"
        elif margin < 0:
            winner = "target"
            margin = abs(margin)
            success_level = "failure"
        else:
            winner = "tie"
            success_level = "partial_success"

        return {
            "winner": winner,
            "margin": margin,
            "actor_roll": {
                "total": actor_total,
                "natural": actor_natural,
                "modifier": actor_mod,
                "rolls": actor_roll.rolls,
                "kept_rolls": actor_roll.kept_rolls if actor_roll.kept_rolls else actor_roll.rolls,
            },
            "target_roll": {
                "total": target_total,
                "natural": target_natural,
                "modifier": target_mod,
                "rolls": target_roll.rolls,
                "kept_rolls": target_roll.kept_rolls if target_roll.kept_rolls else target_roll.rolls,
            },
            "opposed_stat": stat_name,
            "success_level": success_level,
        }

    def _extract_attributes(
        self,
        context: dict[str, Any],
        gsr: GameSystemRuntime | None = None,
    ) -> dict[str, int]:
        """
        Pull the first available attribute map from the assembled scene context.

        Recognises stat keys by comparing against the attribute abbreviations
        defined in the game system schema (via ``gsr``).  Falls back to any
        nested ``attributes`` dict when no runtime is available.
        """
        # Collect known stat abbreviations from the schema
        known_abbrs: set[str] = set()
        if gsr:
            known_abbrs = {abbr.upper() for abbr in gsr._attr_by_abbr}

        def from_entity(entity: Any) -> dict[str, int]:
            props = entity.get("properties", {}) if isinstance(entity, dict) else {}
            if not isinstance(props, dict):
                return {}
            # Nested attributes dict (common in D&D-style schemas)
            attributes = props.get("attributes")
            if isinstance(attributes, dict) and attributes:
                return {k: int(v) for k, v in attributes.items() if isinstance(v, (int, float))}
            # Flat stat keys matched against the active system's abbreviations
            return {k: int(v) for k, v in props.items() if k.upper() in known_abbrs and isinstance(v, (int, float))}

        entities = context.get("entities", [])
        raw_actor = context.get("actor")
        actor: dict[str, Any] = raw_actor if isinstance(raw_actor, dict) else {}
        actor_id = context.get("actor_id") or actor.get("id")
        if actor_id:
            # A known actor rolls with its own sheet, or none: never an NPC's.
            sheet = actor.get("attributes") or actor.get("stats")
            if isinstance(sheet, dict) and sheet:
                return {k: int(v) for k, v in sheet.items() if isinstance(v, (int, float))}
            return next((from_entity(e) for e in entities if str(e.get("id")) == str(actor_id)), {})

        for entity in entities:
            matched = from_entity(entity)
            if matched:
                return matched
        return {}

    def _actor_stat(
        self,
        context: dict[str, Any],
        gsr: GameSystemRuntime | None,
        stat_name: str,
    ) -> tuple[int | None, int]:
        """Return the actor's value for a stat and its modifier.

        A stat the sheet doesn't have is neutral (no value, modifier 0). Treating
        it as a score of 0 gave every roll on an empty sheet a large penalty.
        """
        attr_def = gsr._attr_by_abbr.get(stat_name.upper(), {}) if gsr else {}
        value = _lookup_stat(
            self._extract_attributes(context, gsr),
            [stat_name, str(attr_def.get("name") or ""), str(attr_def.get("abbreviation") or "")],
        )
        if value is None:
            return None, 0
        modifier = gsr.calc_modifier(stat_name, value) if gsr else calculate_modifier(value, _DEFAULT_MODIFIER_FORMULA)
        return value, modifier

    async def resolve_check(
        self,
        entity_id: str,
        stat_name: str,
        dc: int = 15,
        roll_mode: str = "normal",
    ) -> dict[str, Any]:
        """
        Resolve a statistic check (Attribute/Skill) for an entity.

        Workflow:
        1. Get Entity -> Universe -> Multiverse -> System Name.
        2. Get Game System rules.
        3. Get Entity working state (not strictly needed for basic attrib check, but good for context).
        4. Get Entity properties (attributes).
        5. Calculate modifier.
        6. Roll dice.
        7. Determine outcome.
        """
        try:
            # 1. Get Entity to find Universe/System
            # We need to parse the JSON result from call_tool
            entity_json = await self.call_tool("neo4j_get_entity", {"entity_id": entity_id})
            if not entity_json:
                return {"error": "Entity not found"}

            entity_data = json.loads(entity_json)
            # entity_data is { ... } response model

            universe_id = entity_data.get("universe_id")

            # 2. Get Universe to find Multiverse
            universe_json = await self.call_tool("neo4j_get_universe", {"universe_id": str(universe_id)})
            if not universe_json:
                return {"error": "Universe not found"}
            universe_data = json.loads(universe_json)
            multiverse_id = universe_data.get("multiverse_id")

            # 3. Get Multiverse to find System Name
            multiverse_json = await self.call_tool("neo4j_get_multiverse", {"multiverse_id": str(multiverse_id)})
            if not multiverse_json:
                # Fallback: cannot determine system — return error
                system_name = None
            else:
                multiverse_data = json.loads(multiverse_json)
                system_name = multiverse_data.get("system_name")

            # 4. Get Game System
            # list systems and filter by name (since we don't have get_by_name yet, or we simulate it)
            # For now, we grab the first matching one
            systems_json = await self.call_tool(
                "mongodb_list_game_systems",
                {"limit": 100, "include_builtin": True, "offset": 0},
            )
            systems_data = json.loads(systems_json)

            if not system_name:
                # Multiverse record missing — fall back to the first available game system
                systems_list = systems_data.get("systems", [])
                if systems_list:
                    system_name = systems_list[0]["name"]
                else:
                    return {"error": "Could not determine game system for multiverse"}

            system = None
            for sys in systems_data.get("systems", []):
                if sys["name"] == system_name:
                    system = sys
                    break

            if not system:
                return {"error": f"Game system '{system_name}' not found"}

            # 5. Get Entity Attributes (Properties)
            # Assuming 'properties' field in Entity contains attributes map: {"Strength": 16, ...}
            # Or formatted as {"attributes": {"Strength": 16}}
            props = entity_data.get("properties", {})
            attributes = props.get("attributes", {})

            # Handle case where props form is flat {"Strength": 16}
            if not attributes:
                attributes = props

            # Find attribute definition in system
            target_attr_def = next(
                (a for a in system["attributes"] if a["name"].lower() == stat_name.lower()),
                None,
            )

            if not target_attr_def:
                # Is it a skill?
                target_skill_def = next(
                    (s for s in system["skills"] if s["name"].lower() == stat_name.lower()),
                    None,
                )
                if target_skill_def:
                    # It's a skill check - use linked attribute for modifier
                    linked_attr = target_skill_def["linked_attribute"]
                    # Find the linked attribute definition
                    linked_attr_def = next(
                        (a for a in system["attributes"] if a["name"] == linked_attr),
                        None,
                    )
                    if not linked_attr_def:
                        return {"error": f"Linked attribute '{linked_attr}' not found for skill '{stat_name}'"}

                    stat_value = attributes.get(linked_attr, linked_attr_def.get("default_value", 10))

                    # Calculate modifier using linked attribute's formula
                    mod_formula = linked_attr_def.get("modifier_formula")
                    modifier = calculate_modifier(stat_value, mod_formula) if mod_formula else 0
                    # Could add proficiency bonus here in future
                else:
                    return {"error": f"Stat '{stat_name}' not found in system '{system_name}'"}
            else:
                # It's an attribute
                stat_value = attributes.get(target_attr_def["name"], target_attr_def.get("default_value", 10))

                # 6. Calculate Modifier
                mod_formula = target_attr_def.get("modifier_formula")
                modifier = calculate_modifier(stat_value, mod_formula) if mod_formula else 0

            # 7. Roll Dice
            core_mechanic = system["core_mechanic"]
            m_type = core_mechanic["type"]

            # Simple implementation for D20 and Dice Pool
            if "d20" in m_type:
                if roll_mode == "advantage":
                    formula = "2d20kh1"
                elif roll_mode == "disadvantage":
                    formula = "2d20kl1"
                else:
                    formula = "1d20"
                base_roll = roll_dice(formula)
                total = base_roll.total + modifier
                success = total >= dc
                details = f"Rolled {formula} ({base_roll.rolls}) + Mod {modifier} = {total} (DC {dc})"

            elif _is_count_successes_pool(core_mechanic):
                # Sub-plan 4: route pool-vs-difficulty games through
                # the VtM V20 dice engine. Provides hunger dice,
                # willpower reroll, and bestial-failure detection.
                from monitor_agents.dice import default_dice_registry

                pool_size = stat_value
                threshold = _parse_pool_threshold(
                    core_mechanic.get("success_threshold", 6),
                    die_sides=_pool_die_sides(core_mechanic),
                )
                engine = default_dice_registry.get("pool")
                dice_res = engine.resolve_check(
                    pool_size=pool_size,
                    difficulty=threshold,
                )
                successes = dice_res.successes
                total = successes
                success = dice_res.passed
                details = (
                    f"Rolled {pool_size}d10: {dice_res.raw_rolls} -> "
                    f"{successes} successes (threshold {threshold}, "
                    f"engine={dice_res.engine})"
                )

            else:
                return {"error": f"Unsupported mechanic type: {core_mechanic['type']}"}

            return {
                "success": success,
                "total": total,
                "details": details,
                "system": system_name,
                "stat": stat_name,
                "modifier": modifier,
            }

        except Exception as e:
            logger.exception("Error resolving check")
            try:
                parsed_entity_id: UUID | None = UUID(str(entity_id))
            except (TypeError, ValueError):
                parsed_entity_id = None
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.RESOLVER,
                category=RoleplayErrorCategory.RESOLVER_CHECK_FAILED,
                message=str(e),
                fatal=True,
                entity_id=parsed_entity_id,
            )
            return {"error": str(e)}

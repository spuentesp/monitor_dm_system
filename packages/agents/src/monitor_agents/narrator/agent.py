"""
Narrator Agent — produces GM narrative prose for each turn.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts

Responsibilities:
- Generate immersive GM prose (via DSPy NarratorModule)
- Extract proposed world-state changes from DSPy output (single LLM call)
- Persist the GM turn record to MongoDB (via MCP tool)

Single-phase approach:
  DSPy ChainOfThought produces both narrative prose and proposed_changes
  (JSON array string) in one LLM call.  The proposed_changes are parsed
  and validated locally — no second LLM call needed.
"""

from __future__ import annotations

import json
import re
import typing
from typing import Any
from uuid import UUID, uuid4

import structlog
from monitor_data.schemas.base import Speaker

from monitor_agents.base import BaseAgent
from monitor_agents.dspy_runtime import resolve_dynamic_role
from monitor_agents.llm_errors import (
    LLMErrorClass,
    LLMProviderUnavailable,
    classify_llm_error,
)
from monitor_agents.narrator.narrator import (
    CompatCheckModule,
    NarratorModule,
)
from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource
from monitor_agents.utils.runtime_profile_support import (
    build_narrative_profile_context,
    build_tone_hints_from_profile,
    normalize_source_profile,
)
from monitor_agents.utils.tone_resolver import ToneResolver

logger = structlog.get_logger()

# Strip helper duplicated here to avoid a load-time circular import:
# monitor_agents.narrator.agent → monitor_agents.loops.scene_support →
# monitor_agents.loops.scene_loop → monitor_agents.agent_factory →
# monitor_agents.narrator.agent. The duplication is a regex + sub; behavior
# is locked in lockstep with scene_support.strip_entity_tags via the
# round-trip test in tests/test_entity_promotion_support.py
# (test_strip_round_trip_with_parse).
_ENTITY_TAG_STRIP_RE = re.compile(r"\[([^\]]+)\]\(entity:(?:anchor|flavor)\)")


def _strip_entity_tags(text: str) -> str:
    """Strip [Name](entity:anchor|flavor) tags from GM narration.

    Same regex + behavior as monitor_agents.loops.scene_support.strip_entity_tags.
    Kept inline here to break the load-time circular import. The two
    functions MUST stay in sync — the round-trip test in
    test_entity_promotion_support.py catches drift.
    """
    return _ENTITY_TAG_STRIP_RE.sub(r"\1", text or "")


if typing.TYPE_CHECKING:
    from monitor_agents.loops.story_loop import StoryState


class AgentToolAdapter:
    """Adapts BaseAgent.call_tool to the interface expected by ToneResolver."""

    def __init__(self, agent: BaseAgent):
        self.agent = agent

    async def mongodb_get_tone_library(self, library_id: UUID):  # type: ignore[no-untyped-def]
        result = await self.agent.call_tool("mongodb_get_tone_library", {"library_id": str(library_id)})
        if result:
            from monitor_data.schemas.tone_libraries import ToneLibraryResponse

            return ToneLibraryResponse(**result)
        return None

    async def mongodb_get_default_tone_library(self):  # type: ignore[no-untyped-def]
        result = await self.agent.call_tool("mongodb_get_default_tone_library", {})
        if result:
            from monitor_data.schemas.tone_libraries import ToneLibraryResponse

            return ToneLibraryResponse(**result)
        return None

    async def mongodb_get_tone_profiles_batch(self, profile_ids: list[UUID]):  # type: ignore[no-untyped-def]
        result = await self.agent.call_tool(
            "mongodb_get_tone_profiles_batch", {"profile_ids": [str(pid) for pid in profile_ids]}
        )
        return result or []

    async def mongodb_normalize_tag(self, tag: str):  # type: ignore[no-untyped-def]
        result = await self.agent.call_tool("mongodb_normalize_tag", {"tag": tag})
        return result or tag


def _table_talk_block(ooc_exchanges: Any, *, cap: int = 8, max_chars: int = 300) -> str:
    """Render OOC Q&A pairs as a labeled, capped context block ("" when empty)."""
    if not isinstance(ooc_exchanges, list) or not ooc_exchanges:
        return ""
    lines = ""
    count = 0
    for pair in ooc_exchanges[-cap:]:
        if not isinstance(pair, dict):
            continue
        q = str(pair.get("question") or "")[:max_chars].strip()
        a = str(pair.get("answer") or "")[:max_chars].strip()
        if not q and not a:
            continue
        lines += f"Q: {q}\nA: {a}\n"
        count += 1
    if not count:
        return ""
    return (
        "\n\nTABLE TALK (out-of-character discussion — background only; "
        "never reference this channel in fiction):\n" + lines
    )


def _recent_chat_block(recent_chat: Any, *, max_tokens: int = 500) -> str:
    """Render the raw chat tail as a labeled block, hard-capped by tokens."""
    if not isinstance(recent_chat, list) or not recent_chat:
        return ""
    from monitor_agents.token_budget import count_tokens

    lines: list[str] = []
    used = 0
    for item in reversed(recent_chat):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        label = "[OOC]" if str(item.get("mode") or "ic").lower() == "ooc" else "[IC]"
        line = f"{label} {item.get('role') or '?'}: {content}"
        cost = count_tokens(line)
        if used + cost > max_tokens:
            break
        lines.append(line)
        used += cost
    if not lines:
        return ""
    lines.reverse()
    return (
        "\n\nRECENT TABLE CONVERSATION (provenance labels, not content — "
        "never address OOC remarks in fiction):\n" + "\n".join(lines) + "\n"
    )


class Narrator(BaseAgent):
    """
    Generates GM narrative prose and extracts world-state change proposals.

    Called by:
    - scene_loop.narrate() — after Resolver produces a resolution
    - turn_loop.generate_response() — innermost turn generation
    """

    def __init__(self, agent_id: str = "narrator-1") -> None:
        super().__init__(agent_type="Narrator", agent_id=agent_id)
        self._narrator_module = NarratorModule()
        self._compat_check = CompatCheckModule()
        self._tone_resolver = ToneResolver(AgentToolAdapter(self))

    async def run(self) -> None:
        pass  # driven by loop nodes

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    async def narrate_turn(
        self,
        scene_id: UUID,
        user_input: str | None,
        resolution: dict[str, Any] | None,
        context: dict[str, Any],
        game_context: dict[str, Any] | None = None,
        session_tone: str = "dramatic",
        gm_profile: dict[str, Any] | None = None,
        lorebook_context: list[str] | None = None,
        story_state: StoryState | None = None,
        gm_verdict: Any | None = None,
        persist_turn: bool = True,
    ) -> dict[str, Any]:
        """
        Generate GM narrative for a single turn and persist it to MongoDB.

        The narrator is a DOWNSTREAM REFINER of the GMAgent verdict. When
        ``gm_verdict`` is provided, the narrator uses ``gm_verdict.narrative_draft``
        as the starting point and runs a smaller DSPy refinement pass to
        produce voice/pacing polish. When ``gm_verdict`` is ``None`` (legacy
        call), the narrator falls back to its full ChainOfThought-from-resolution
        path — useful when GMAgent is unavailable (test env, missing provider).

        Args:
            scene_id:     Current scene UUID.
            user_input:   Player's action/speech.
            resolution:   Resolver outcome dict (legacy field — used when
                          ``gm_verdict`` is None).
            context:      {entities, memories, turns} from ContextAssembly.
            game_context: Raw game-system MongoDB document.
            session_tone: Tone label from session (dramatic/grim/heroic/etc.).
            gm_profile:   Optional GMProfile dict.
            lorebook_context: Optional list of relevant lorebook entries.
            story_state:  Optional story state (arc, tension, threads).
            gm_verdict:   Optional GMVerdict (from GMAgent.decide). When present,
                          narrator refines ``narrative_draft`` instead of writing
                          from scratch.
            persist_turn: When False, skip writing the exchange to the scene's
                          turn log (used for OOC/meta calls with no real scene).

        Returns:
            {
                "narrative_text": str,
                "proposals":      List[dict],
                "turn_id":        str,
            }
        """
        # --- Path selection: refine the GM's draft, or generate from scratch ---
        if gm_verdict is not None:
            (
                narrative_text,
                raw_proposals,
                minutes_elapsed,
                suggested_actions,
                degraded,
            ) = await self._reconcile_gm_draft(  # type: ignore[no-untyped-call]
                gm_verdict=gm_verdict,
                resolution=resolution,
                context=context,
                game_context=game_context,
                session_tone=session_tone,
                gm_profile=gm_profile,
                lorebook_context=lorebook_context,
                story_state=story_state,
            )
        else:
            # --- Legacy path: single LLM call from resolution dict ---
            (
                narrative_text,
                raw_proposals,
                minutes_elapsed,
                suggested_actions,
                degraded,
            ) = await self._generate_narrative_and_proposals(  # type: ignore[misc]
                user_input=user_input,
                resolution=resolution,
                context=context,
                game_context=game_context,
                session_tone=session_tone,
                gm_profile=gm_profile,
                lorebook_context=lorebook_context,
                story_state=story_state,
            )

        # --- Persist turn to MongoDB ---
        # OOC/meta calls (persist_turn=False) run against a synthetic scene id
        # — persisting would 404 on mongodb_append_turn and pollute the scene
        # record used for canon extraction with out-of-fiction chatter.
        turn_id = ""
        if persist_turn:
            turn_id = await self._persist_turn(
                scene_id=scene_id,
                user_input=user_input,
                narrative_text=narrative_text,
                resolution=resolution,
            )

        return {
            "narrative_text": narrative_text,
            "proposals": raw_proposals,
            "turn_id": turn_id,
            "degraded": (
                {"error_class": degraded.info.error_class.value, "message": degraded.user_message}
                if degraded is not None
                else None
            ),
            "minutes_elapsed": minutes_elapsed,
            "suggested_actions": suggested_actions,
        }

    @staticmethod
    def _parse_minutes(raw: str) -> int:
        """Coerce string minutes to int, defaulting to 1 for tiny beats."""
        try:
            val = int(re.sub(r"[^\d]", "", raw))
            return max(1, val)
        except (ValueError, TypeError):
            return 1

    @staticmethod
    def _build_actor_block(actor: dict[str, Any] | None) -> str:
        """Build the ACTOR PROFILE block for the narrator's profile_context.

        [G-4 hallucination guard, 2026-07-23] When the actor's
        identity-bearing fields are all absent (no stats, no inventory,
        no conditions, no personality, no state tags), prepend a
        ``[CHARACTER SHEET IS EMPTY]`` sentinel so the prompt-level rule
        against inventing clan / class / faction / items / stats /
        relationships actually fires. Without the sentinel, the narrator
        has been observed live inventing a clan the player never picked —
        see ``docs/STATUS.md`` [G-4] and
        ``tests/test_narrator_hallucination_guard.py``.

        Returns ``""`` when ``actor`` is None.
        """
        if not actor:
            return ""
        actor_name = actor.get("name", "the character")
        role = actor.get("role", "pc")
        personality = (actor.get("personality") or "").strip()
        state_tags = actor.get("state_tags") or []
        tags = ", ".join(state_tags)
        stats = actor.get("stats")
        inventory = actor.get("inventory")
        conditions = actor.get("conditions")

        actor_block = f"\n\nACTOR PROFILE ({actor_name}):\n- Role: {role}\n"
        if personality:
            actor_block += f"- Personality: {personality}\n"
        if tags:
            actor_block += f"- State: {tags}\n"
        if stats and isinstance(stats, dict):
            stats_str = ", ".join(f"{k}: {v}" for k, v in stats.items())
            actor_block += f"- Stats: {stats_str}\n"
        if inventory and isinstance(inventory, list) and inventory:
            actor_block += f"- Inventory: {', '.join(inventory)}\n"
        if conditions and isinstance(conditions, list) and conditions:
            actor_block += f"- Conditions: {', '.join(conditions)}\n"

        # Empty-sheet detection: every identity-bearing field is empty.
        # Tag the block so the prompt-level 'do not invent' rule fires.
        sheet_empty = (
            not (stats and isinstance(stats, dict) and stats)
            and not (inventory and isinstance(inventory, list) and inventory)
            and not (conditions and isinstance(conditions, list) and conditions)
            and not personality
            and not tags
        )
        if sheet_empty:
            actor_block = (
                "\n\n[CHARACTER SHEET IS EMPTY — do not invent identity facts. "
                "Narrate without assigning clan/class/faction/items/stats/"
                "relationships.]\n" + actor_block
            )
        return actor_block

    async def generate_opening(
        self,
        user_input: str | None,
        context: dict[str, Any],
        game_context: dict[str, Any] | None = None,
        session_tone: str = "dramatic",
        gm_profile: dict[str, Any] | None = None,
        story_premise: str | None = None,
    ) -> str:
        """Generate one-off GM opening prose without persisting turns or proposals.

        ``story_premise`` is the player's own pitch for what this story
        should be about ("heist against a rival Prince", "survival horror,
        no combat") -- a hard steering constraint on content, distinct from
        ``session_tone`` (mood only). See
        CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md Q3.
        """
        return await self._generate_narrative_text(
            user_input=user_input,
            resolution=None,
            context=context,
            game_context=game_context,
            session_tone=session_tone,
            gm_profile=gm_profile,
            story_premise=story_premise,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    # NOTE: Built-in tone profiles have been moved to
    # monitor_agents.utils.tone_resolver.BUILTIN_TONE_PROFILES
    # (single source of truth — DRY).

    async def _generate_narrative_and_proposals(
        self,
        *,
        user_input: str | None,
        resolution: dict[str, Any] | None,
        context: dict[str, Any],
        game_context: dict[str, Any] | None = None,
        session_tone: str = "dramatic",
        gm_profile: dict[str, Any] | None = None,
        lorebook_context: list[str] | None = None,
        story_state: StoryState | None = None,
        story_premise: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], int]:
        """Run the DSPy narrator module and parse proposals from the output.

        Returns:
            (narrative_text, proposals, minutes_elapsed)
        """
        # The explicit story_premise kwarg (opening-time, one-off calls) wins
        # when given; otherwise fall back to the persisted StoryState's own
        # story_premise (ongoing scene turns) so a stated premise keeps
        # steering content turn after turn, not just at the cold open.
        story_premise = story_premise or getattr(story_state, "story_premise", None)

        resolution_summary = self._format_resolution(resolution)

        compact_gc: dict[str, Any] = {}
        system_name = ""
        if game_context:
            try:
                from monitor_agents.game_system import GameSystemRuntime

                compact_gc = GameSystemRuntime(game_context).compact_for_narrator()
                system_name = compact_gc.get("name", "")
            except Exception:
                logger.debug("GameSystemRuntime unavailable, using raw game_context name")
                compact_gc = {"name": game_context.get("name", "")}
                system_name = game_context.get("name", "")

        source_profile = normalize_source_profile(context.get("source_profile", {}))
        tone_context = await self._resolve_tone_context(
            session_tone=session_tone,
            system_name=system_name,
            source_profile=source_profile,
            gm_profile=gm_profile,
        )
        profile_context = build_narrative_profile_context(source_profile)

        # Inject ACTOR PROFILE block. [G-4] empty-sheet sentinel handled by
        # ``Narrator._build_actor_block`` (see hallucination guard). The local
        # ``actor`` is reused below when building the setting_anchor.
        actor = context.get("actor")
        actor_block = self._build_actor_block(actor)
        if actor_block:
            profile_context += actor_block

        # Inject lorebook entries into profile_context
        lore_to_inject = lorebook_context or context.get("lorebook_context")
        if lore_to_inject:
            profile_context += "\n\nRELEVANT LOREBOOK ENTRIES:\n" + "\n".join(lore_to_inject)

        # Inject story state (Task 2)
        if story_state:
            arc_label = getattr(story_state, "arc_label", "Ongoing")
            tension = getattr(story_state, "tension_score", 0.5)
            threads = getattr(story_state, "active_threads", [])
            threads_str = ", ".join(threads) if threads else "None"

            story_block = (
                f"\n\nSTORY ARC CONTEXT:\n"
                f"- Phase: {arc_label}\n"
                f"- Tension: {tension}/1.0\n"
                f"- Active Threads: {threads_str}\n"
            )
            profile_context += story_block

        # Inject established facts for continuity (prevents name/setting drift)
        established_facts = context.get("established_facts")
        if established_facts and isinstance(established_facts, list) and established_facts:
            facts_block = "\n\nESTABLISHED FACTS (do not contradict these):\n"
            for fact in established_facts[-20:]:  # cap at 20 most recent
                facts_block += f"- {fact}\n"
            profile_context += facts_block

        # Inject OOC table talk (player questions + GM answers) as background.
        profile_context += _table_talk_block(context.get("ooc_exchanges"))

        # Inject the raw recent chat tail (IC + OOC, labeled).
        profile_context += _recent_chat_block(context.get("recent_chat"))

        # Inject turn context for spatial/situational awareness
        turn_ctx = context.get("turn_context")
        if turn_ctx:
            if isinstance(turn_ctx, dict):
                from monitor_agents.turn_context import TurnContext

                try:
                    tc = TurnContext(**turn_ctx)
                    tc_prompt = tc.to_narrator_prompt()
                    if tc_prompt:
                        profile_context += "\n\nTURN CONTEXT:\n" + tc_prompt
                except Exception:
                    # If TurnContext construction fails, inject raw dict
                    profile_context += "\n\nTURN CONTEXT:\n" + json.dumps(turn_ctx, default=str)[:2000]
            elif hasattr(turn_ctx, "to_narrator_prompt"):
                tc_prompt = turn_ctx.to_narrator_prompt()
                if tc_prompt:
                    profile_context += "\n\nTURN CONTEXT:\n" + tc_prompt

        # Build setting anchor: genre + setting + character identity.
        # This locks the genre and setting to prevent drift mid-session.
        setting_parts: list[str] = []
        # A player-stated story premise is the most specific steering signal
        # available -- lead with it, ahead of genre/setting, and reinforce it
        # in the CRITICAL directive below (plan doc Q3: "hard steering
        # constraint on the opening scene's content, not just its mood").
        if story_premise:
            setting_parts.append(f"PLAYER-STATED PREMISE (build this scene around it): {story_premise}")
        genre = ""
        if isinstance(source_profile, dict):
            genre = source_profile.get("genre", "") or source_profile.get("taxonomy", {}).get("genre", "")
            setting_summary = source_profile.get("setting_summary", "") or source_profile.get("description", "")
            if genre:
                setting_parts.append(f"GENRE: {genre.upper()}")
            if setting_summary:
                setting_parts.append(f"SETTING: {setting_summary}")
        if actor:
            actor_name = actor.get("name", "")
            actor_role = actor.get("role", "")
            if actor_name:
                setting_parts.append(f"CHARACTER: {actor_name}")
            if actor_role:
                setting_parts.append(f"ROLE: {actor_role}")
        if system_name:
            setting_parts.append(f"SYSTEM: {system_name}")
        setting_parts.append(
            "CRITICAL: Never change the genre, setting, or character identity mid-session. "
            "Never describe technology as magic or vice versa."
            + (
                " Build this opening around the player-stated premise above, not just its mood."
                if story_premise
                else ""
            )
        )
        # Table agreements (lines and veils) are session-scoped player
        # constraints. We surface them as a hard directive in the setting
        # anchor so the narrator respects them on every turn.
        agreements = context.get("agreements") if isinstance(context, dict) else None
        if isinstance(agreements, dict):
            lines = [
                str(item).strip()
                for item in (agreements.get("lines") or [])
                if str(item).strip()
            ]
            veils = [
                str(item).strip()
                for item in (agreements.get("veils") or [])
                if str(item).strip()
            ]
            if lines:
                lines_listing = "; ".join(lines)
                setting_parts.append(
                    "TABLE LINES (never depict, introduce, or make central): "
                    f"{lines_listing}."
                )
            if veils:
                veils_listing = "; ".join(veils)
                setting_parts.append(
                    "TABLE VEILS (acknowledge but fade to black without detail): "
                    f"{veils_listing}."
                )
        setting_anchor = " | ".join(setting_parts)

        # Resolve dynamic model role based on dramatic intensity.
        dynamic_role = resolve_dynamic_role(
            "narrator",
            player_action=user_input or "",
            resolution=resolution,
        )

        module_kwargs = {
            "tone_context": tone_context,
            "game_system_context": json.dumps(compact_gc, ensure_ascii=False, default=str),
            "scene_context": json.dumps(context.get("entities", [])[:5], default=str),
            "profile_context": profile_context,
            "memory_context": json.dumps(context.get("memories", [])[:3], default=str),
            "prior_turns": json.dumps(context.get("turns", [])[-8:], default=str),
            "player_action": user_input or "(scene description)",
            "resolution_summary": resolution_summary,
            "setting_anchor": setting_anchor,
            "context_summary": context.get("context_summary", ""),
            "role": dynamic_role,
        }
        # Resilience: some providers (notably MiniMax) intermittently return a
        # response that the DSPy JSON adapter can't fully parse — e.g. it omits
        # the trailing ``narrative_time_elapsed`` field, which makes DSPy *raise*
        # AdapterParseError and would otherwise crash the whole turn. Try up to
        # twice; on persistent (unrecognized/format) failure degrade gracefully
        # to an empty-but-safe result so the session continues instead of dying.
        #
        # A PROVIDER-LEVEL failure (rate limit, quota exhaustion, auth,
        # misconfiguration) is a different case: retrying won't fix it, and
        # silently returning empty text hides the failure from the player
        # entirely (they just see a blank GM turn). Those are re-raised as
        # LLMProviderUnavailable so the caller can fall back to the GM's
        # draft text (see _reconcile_gm_draft) and/or surface a clear
        # message instead of a blank turn.
        prediction = None
        narrative_text = ""
        last_provider_error: LLMProviderUnavailable | None = None
        for attempt in range(2):
            try:
                prediction = self._narrator_module(**module_kwargs)
                narrative_text = getattr(prediction, "narrative_text", "") or ""
                last_provider_error = None
                if narrative_text.strip():
                    break
                logger.warning("Narrator returned empty narrative_text (attempt %d)", attempt + 1)
            except Exception as exc:
                info = classify_llm_error(exc)
                if info.error_class == LLMErrorClass.UNKNOWN:
                    # Unrecognized failure shape — almost certainly the DSPy
                    # adapter's own transient JSON-parse hiccup. Keep the
                    # original silent-retry-then-degrade behavior.
                    logger.warning("Narrator parse failed (attempt %d): %s", attempt + 1, exc)
                    prediction = None
                    last_provider_error = None
                else:
                    # A real provider-level failure. Remember it; raise once
                    # the retry budget is exhausted rather than swallowing it.
                    logger.warning(
                        "Narrator LLM call failed (attempt %d, class=%s): %s",
                        attempt + 1,
                        info.error_class.value,
                        exc,
                    )
                    prediction = None
                    last_provider_error = LLMProviderUnavailable(info)

        if last_provider_error is not None:
            raise last_provider_error

        if prediction is None:
            return narrative_text, [], 1, [], None  # type: ignore[return-value]

        # Parse proposed_changes from DSPy output (JSON array string)
        proposals = self._parse_proposed_changes(getattr(prediction, "proposed_changes", "[]"))
        minutes_elapsed = self._parse_minutes(getattr(prediction, "narrative_time_elapsed", "0"))
        suggested_actions = self._parse_suggested_actions(getattr(prediction, "suggested_actions", "[]"))
        return narrative_text, proposals, minutes_elapsed, suggested_actions, None  # type: ignore[return-value]

    async def _generate_narrative_text(
        self,
        *,
        user_input: str | None,
        resolution: dict[str, Any] | None,
        context: dict[str, Any],
        game_context: dict[str, Any] | None = None,
        session_tone: str = "dramatic",
        gm_profile: dict[str, Any] | None = None,
        story_premise: str | None = None,
    ) -> str:
        """Run the DSPy narrator module — returns prose only (for opening narratives)."""
        text, _, _, _, _ = await self._generate_narrative_and_proposals(  # type: ignore[misc]
            user_input=user_input,
            resolution=resolution,
            context=context,
            game_context=game_context,
            session_tone=session_tone,
            gm_profile=gm_profile,
            story_premise=story_premise,
        )
        return text  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Path 1 — 3-step reconcile: GM draft + outcome -> polished prose.
    # ------------------------------------------------------------------
    # (Replaces the single-step _refine_gm_draft from Phase A; same external
    # contract: returns (narrative_text, proposals, minutes, suggested).)
    #
    # User-confirmed reading (b): GM = voice / draft / anticipation. Narrator
    # = outcome + polish. The draft anticipates the outcome; the actual
    # outcome may contradict it. A small `dspy.Predict` (CompatCheckModule)
    # judges draft<->outcome compat and dispatches:
    #
    #   COMPATIBLE     -> refine the draft with tone/lorebook (voice wins).
    #   DIVERGES       -> refine, but anchor the prompt to the outcome so
    #                    the polish step reconciles the contradiction.
    #   INCOMPATIBLE   -> drop the draft; regenerate from the outcome
    #                    (the draft would mislead more than help).
    #   NO ROLL        -> there's no outcome to contradict the draft; the
    #                    draft IS the story. Same as COMPATIBLE, no anchor.
    #
    # Empty-draft + LLM-error paths fall back to the legacy _generate path
    # (the same behavior _refine_gm_draft had).

    _OUTCOME_ROLLED_TYPES = {"dice", "contested", "pending_roll"}

    @staticmethod
    def _outcome_summary(resolution):  # type: ignore[no-untyped-def]
        """One-line factual summary of the resolution for the compat check."""
        if not resolution:
            return "no outcome yet"
        rtype = resolution.get("resolution_type") or "unknown"
        sl = resolution.get("success_level") or "-"
        rb = resolution.get("roll_breakdown") or ""
        fx = resolution.get("effects") or []
        parts = [f"type={rtype}", f"success={sl}"]
        if rb:
            parts.append(f"roll={rb}")
        if fx:
            parts.append("effects=" + ",".join(map(str, fx)))
        return "; ".join(parts)

    @staticmethod
    def _normalize_compat(raw):  # type: ignore[no-untyped-def]
        """Coerce a model-emitted compat label to a known value.

        Fail-soft: an unknown / malformed label maps to DIVERGES (the
        safe middle - the outcome anchor will reconcile).
        """
        label = str(raw or "").strip().upper()
        if label == "COMPATIBLE":
            return "COMPATIBLE"
        if label == "INCOMPATIBLE":
            return "INCOMPATIBLE"
        return "DIVERGES"

    async def _reconcile_gm_draft(  # type: ignore[no-untyped-def]
        self,
        *,
        gm_verdict,
        resolution=None,
        context,
        game_context=None,
        session_tone="dramatic",
        gm_profile=None,
        lorebook_context=None,
        story_state=None,
    ):
        """Reconcile the GM's pre-roll draft with the outcome into prose.

        Empty draft -> legacy generate. Rolled outcome -> compat check, then
        refine (with anchor when DIVERGES) or regenerate (when INCOMPATIBLE).
        No roll / non-dice turn -> just refine (the draft IS the story).

        Returns: (narrative_text, proposals, minutes_elapsed, suggested_actions)
        """
        # Empty draft: fall back to legacy generation.
        draft_text = getattr(gm_verdict, "narrative_draft", None) or ""
        if not draft_text.strip():
            logger.info("narrator.refine.empty_draft; falling back to legacy _generate path")
            return await self._generate_narrative_and_proposals(
                user_input=getattr(gm_verdict, "reasoning", "") or None,
                resolution=None,
                context=context,
                game_context=game_context,
                session_tone=session_tone,
                gm_profile=gm_profile,
                lorebook_context=lorebook_context,
                story_state=story_state,
            )

        # Did a roll actually happen? If so the outcome may contradict
        # the draft -> compat check + possibly anchor. If not, the draft
        # is the only signal -> just refine.
        rtype = (resolution or {}).get("resolution_type")
        a_roll_happened = rtype in self._OUTCOME_ROLLED_TYPES

        compat = "COMPATIBLE"  # default for non-rolled turns
        if a_roll_happened:
            outcome_summary = self._outcome_summary(resolution)  # type: ignore[no-untyped-call]
            try:
                pred = self._compat_check(draft=draft_text, outcome_summary=outcome_summary)
                compat = self._normalize_compat(getattr(pred, "verdict", None))  # type: ignore[no-untyped-call]
            except Exception as exc:
                logger.info(
                    "narrator.reconcile.compat_check_failed (%s); using DIVERGES",
                    exc,
                )
                compat = "DIVERGES"
                info = classify_llm_error(exc)
                await RoleplayErrorRecorder.record(
                    source=RoleplayErrorSource.NARRATOR,
                    category=RoleplayErrorCategory.LLM,
                    message=info.message,
                    fatal=False,
                    llm_error_class=info.error_class.value,
                )

        # Incompatible: drop the draft, regenerate from outcome.
        if compat == "INCOMPATIBLE":
            logger.info("narrator.reconcile.INCOMPATIBLE; regenerating from outcome")
            return await self._generate_narrative_and_proposals(
                user_input=getattr(gm_verdict, "reasoning", "") or None,
                resolution=resolution,
                context=context,
                game_context=game_context,
                session_tone=session_tone,
                gm_profile=gm_profile,
                lorebook_context=lorebook_context,
                story_state=story_state,
            )

        # Compatible or Diverges: refine, anchoring to the outcome when
        # the roll contradicted the draft (Diverges) so the polish step
        # reconciles. For no-roll + Compatible, no anchor (the draft IS
        # the story).
        resolution_summary = {
            "scene_id": getattr(gm_verdict, "scene_id", None),
            "intent_type": getattr(gm_verdict, "intent_type", None).value  # type: ignore[union-attr]
            if hasattr(getattr(gm_verdict, "intent_type", None), "value")
            else None,
            "action_type": getattr(gm_verdict, "action_type", None).value  # type: ignore[union-attr]
            if hasattr(getattr(gm_verdict, "action_type", None), "value")
            else None,
            "roll_necessity": getattr(gm_verdict, "roll_necessity", None).value  # type: ignore[union-attr]
            if hasattr(getattr(gm_verdict, "roll_necessity", None), "value")
            else None,
            "causality_action": getattr(gm_verdict, "causality_action", None).value  # type: ignore[union-attr]
            if hasattr(getattr(gm_verdict, "causality_action", None), "value")
            else None,
            "subsystem_hint": getattr(gm_verdict, "subsystem_hint", None),
            "success_level": (resolution or {}).get("success_level") or "pending",
            "gm_reasoning": getattr(gm_verdict, "reasoning", ""),
            "gm_draft": draft_text,
            "tool_calls_made": list(getattr(gm_verdict, "tool_calls_made", []) or []),
        }
        if compat == "DIVERGES":
            resolution_summary["outcome_anchor"] = self._outcome_summary(resolution)  # type: ignore[no-untyped-call]

        # NOTE(pre-G-4 lint cleanup): removed dead ``source_profile`` /
        # ``compact_gc`` / ``system_name`` / ``tone_context`` /
        # ``profile_context`` assignments flagged by ``ruff F841`` (this method
        # was resolved-then-discarded before the downstream
        # ``_generate_narrative_text`` extracted the same logic). The legacy
        # resolution now lives only in ``_generate_narrative_and_proposals``.

        degraded: LLMProviderUnavailable | None = None
        try:
            narrative_text = await self._generate_narrative_text(
                user_input=getattr(gm_verdict, "reasoning", "") or None,
                resolution=resolution_summary,
                context=context,
                game_context=game_context,
                session_tone=session_tone,
                gm_profile=gm_profile,
            )
        except Exception as exc:
            logger.warning("narrator.refine.failed; using gm_draft verbatim: %s", exc)
            narrative_text = draft_text
            degraded = (
                exc if isinstance(exc, LLMProviderUnavailable) else LLMProviderUnavailable(classify_llm_error(exc))
            )
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.NARRATOR,
                category=RoleplayErrorCategory.LLM,
                message=degraded.info.message,
                fatal=False,
                llm_error_class=degraded.info.error_class.value,
            )

        proposals = []  # type: ignore[var-annotated]
        minutes_elapsed = 1
        suggested_actions = []  # type: ignore[var-annotated]

        return narrative_text, proposals, minutes_elapsed, suggested_actions, degraded

    # Backward-compat alias: the old name still works for any external caller.
    # New code should call _reconcile_gm_draft directly.
    async def _refine_gm_draft(  # type: ignore[no-untyped-def]
        self,
        *,
        gm_verdict,
        context,
        game_context=None,
        session_tone="dramatic",
        gm_profile=None,
        lorebook_context=None,
        story_state=None,
    ):
        """Deprecated shim - delegates to :meth:`_reconcile_gm_draft`.

        Kept for backward-compat (the Path 1 dispatch in narrate_turn still
        references this name; tests may also import it). When called without
        ``resolution`` (legacy callers), this shim treats the turn as
        no-roll - the draft refines cleanly.
        """
        return await self._reconcile_gm_draft(  # type: ignore[no-untyped-call]
            gm_verdict=gm_verdict,
            resolution=None,
            context=context,
            game_context=game_context,
            session_tone=session_tone,
            gm_profile=gm_profile,
            lorebook_context=lorebook_context,
            story_state=story_state,
        )

    @staticmethod
    def _parse_proposed_changes(raw: str) -> list[dict[str, Any]]:
        """Safely parse the proposed_changes JSON string from DSPy output.

        Accepts: valid JSON array, empty string, None-like values.
        Returns: list of dicts, each with at least change_type and summary.
        """
        if not raw or not raw.strip():
            return []

        text = raw.strip()
        # Strip markdown code fences if present (```json ... ```)
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (fence markers)
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # DSPy sometimes wraps the JSON in prose — try to extract the array
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "narrator: JSON parse failed after DSPy prose extraction, returning []",
                        exc_info=True,
                    )
                    return []
            else:
                return []

        if not isinstance(parsed, list):
            return []

        # Validate each entry has the minimum required shape
        valid = [
            {
                "change_type": item.get("change_type", "narrative_implication"),
                "summary": item.get("summary", ""),
                "content": item.get("content", {}),
            }
            for item in parsed
            if isinstance(item, dict)
        ]
        return valid

    @staticmethod
    def _parse_suggested_actions(raw: str) -> list[str]:
        """Parse the suggested_actions JSON array of short strings from DSPy output.

        Tolerant of empty/None, markdown fences, and prose-wrapped JSON (same
        shapes as ``_parse_proposed_changes``). Returns at most 3 trimmed,
        non-empty strings; ``[]`` on any failure so a bad field never breaks a turn.
        """
        if not raw or not raw.strip():
            return []

        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.split("\n") if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except (json.JSONDecodeError, TypeError):
                    return []
            else:
                return []

        if not isinstance(parsed, list):
            return []

        actions: list[str] = []
        for item in parsed:
            if isinstance(item, str) and item.strip():
                actions.append(item.strip())
            if len(actions) >= 3:
                break
        return actions

    async def _resolve_tone_context(
        self,
        session_tone: str = "dramatic",
        system_name: str = "",
        source_profile: dict[str, Any] | None = None,
        gm_profile: dict[str, Any] | None = None,
    ) -> str:
        """
        Build the tone_context string injected into the Narrator prompt.

        Resolution order:
          1. GMProfile (if provided) → self._tone_resolver.resolve_from_profile
          2. Legacy session_tone → self._tone_resolver.resolve_from_profile (using fallback_tone)
          3. Append system_name + source_profile hints
        """
        # Step 1: Resolve base tone from GMProfile or legacy tone
        # We now always use the ToneResolver to get the benefit of caching and extensible profiles.
        base = await self._tone_resolver.resolve_from_profile(
            gm_profile,
            fallback_tone=session_tone,
        )

        # Step 2: Append system + source profile hints
        extra_parts: list[str] = []
        if system_name:
            extra_parts.append(f"Setting: {system_name}.")

        profile_tone = build_tone_hints_from_profile(source_profile or {})
        if profile_tone:
            extra_parts.append(profile_tone)

        if extra_parts:
            return base + " " + " ".join(extra_parts)
        return base

    def _format_resolution(self, resolution: dict[str, Any] | None) -> str:
        """Convert a Resolver outcome dict to a summary string for the Narrator prompt."""
        if not resolution:
            return "narrative"
        res_type = resolution.get("resolution_type", "")
        success = resolution.get("success_level", "unknown")
        stat = resolution.get("stat")
        dc = resolution.get("difficulty_class")
        roll = resolution.get("roll_total")

        # P-18: Oracle resolution summary
        if res_type == "oracle":
            ora = resolution.get("oracle_result", {})
            out = ora.get("outcome", "unknown")
            is_yes = ora.get("is_yes")
            lik = ora.get("likelihood")
            return f"ORACLE RESOLUTION: Result is {out} (Yes: {is_yes}) based on {lik} likelihood. Ground your description in this fixed truth."

        # Propose-roll: GM should invite the player to roll, not narrate an outcome
        if res_type == "propose_roll":
            stat_label = stat or "the relevant stat"
            dc_hint = f" (DC {dc})" if dc else ""
            return f"propose_roll:{stat_label}{dc_hint}"

        # Pure narrative or trivial — no dice context
        if res_type in ("narrative", "trivial", "forced_narrative"):
            return "narrative"

        # Dice outcome already resolved
        parts = [success]
        if roll is not None and stat:
            parts.append(f"Roll: {roll} ({stat})")
        effects = resolution.get("effects", [])
        if effects:
            parts.append(f"Effects: {', '.join(str(e) for e in effects)}")
        return ". ".join(parts)

    async def _persist_turn(
        self,
        scene_id: UUID,
        user_input: str | None,
        narrative_text: str,
        resolution: dict[str, Any] | None,
    ) -> str:
        """Write the player + GM exchange to MongoDB via the scene turn tool."""
        if user_input:
            await self.call_tool(
                "mongodb_append_turn",
                {
                    "scene_id": str(scene_id),
                    "params": {
                        "speaker": Speaker.USER.value,
                        "text": user_input,
                    },
                },
            )

        raw_response = await self.call_tool(
            "mongodb_append_turn",
            {
                "scene_id": str(scene_id),
                "params": {
                    "speaker": Speaker.GM.value,
                    # Strip the [Name](entity:anchor|flavor) tags here so
                    # the canonical turn record matches what the player
                    # sees in the chat output. The parser still ran on the
                    # raw narrative_text earlier (feeding entity promotion
                    # via parse_entity_tags); this only cleans the text
                    # that gets persisted + sent to the client.
                    #
                    # Deferred import: scene_support re-exports through
                    # monitor_agents.loops → scene_loop → agent_factory,
                    # which back-references this module. Importing at
                    # function scope breaks the load-time cycle.
                    "text": _strip_entity_tags(narrative_text),
                },
            },
        )

        if isinstance(raw_response, dict):
            parsed = raw_response
        else:
            try:
                parsed = json.loads(raw_response) if raw_response else {}
            except (json.JSONDecodeError, TypeError):
                parsed = {}

        return str(parsed.get("turn_id", str(uuid4())))

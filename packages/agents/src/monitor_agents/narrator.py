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
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from monitor_agents.base import BaseAgent
from monitor_agents.dspy_runtime import resolve_dynamic_role
from monitor_agents.prompts.narrator import NarratorModule
from monitor_agents.utils.runtime_profile_support import (
    build_narrative_profile_context,
    build_tone_hints_from_profile,
    normalize_source_profile,
)
from monitor_agents.utils.tone_resolver import ToneResolver
from monitor_data.schemas.base import Speaker

import structlog

logger = structlog.get_logger()

if typing.TYPE_CHECKING:
    from monitor_agents.loops.story_loop import StoryState


class AgentToolAdapter:
    """Adapts BaseAgent.call_tool to the interface expected by ToneResolver."""

    def __init__(self, agent: BaseAgent):
        self.agent = agent

    async def mongodb_get_tone_library(self, library_id: UUID):
        result = await self.agent.call_tool(
            "mongodb_get_tone_library", {"library_id": str(library_id)}
        )
        if result:
            from monitor_data.schemas.tone_libraries import ToneLibraryResponse

            return ToneLibraryResponse(**result)
        return None

    async def mongodb_get_default_tone_library(self):
        result = await self.agent.call_tool("mongodb_get_default_tone_library", {})
        if result:
            from monitor_data.schemas.tone_libraries import ToneLibraryResponse

            return ToneLibraryResponse(**result)
        return None

    async def mongodb_get_tone_profiles_batch(self, profile_ids: List[UUID]):
        result = await self.agent.call_tool(
            "mongodb_get_tone_profiles_batch", {"profile_ids": [str(pid) for pid in profile_ids]}
        )
        return result or []

    async def mongodb_normalize_tag(self, tag: str):
        result = await self.agent.call_tool("mongodb_normalize_tag", {"tag": tag})
        return result or tag


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
        self._tone_resolver = ToneResolver(AgentToolAdapter(self))

    async def run(self) -> None:
        pass  # driven by loop nodes

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    async def narrate_turn(
        self,
        scene_id: UUID,
        user_input: Optional[str],
        resolution: Optional[Dict[str, Any]],
        context: Dict[str, Any],
        game_context: Optional[Dict[str, Any]] = None,
        session_tone: str = "dramatic",
        gm_profile: Optional[Dict[str, Any]] = None,
        lorebook_context: Optional[List[str]] = None,
        story_state: Optional[StoryState] = None,
    ) -> Dict[str, Any]:
        """
        Generate GM narrative for a single turn and persist it to MongoDB.

        Single-phase approach: DSPy ChainOfThought produces both narrative prose
        and proposed world-state changes in one LLM call.  The ``proposed_changes``
        output field (JSON array string) is parsed directly — no second LLM call.

        Args:
            scene_id:     Current scene UUID.
            user_input:   Player's action/speech.
            resolution:   Resolver outcome dict (may be None for pure narrative turns).
            context:      {entities, memories, turns} from ContextAssembly.
            game_context: Raw game-system MongoDB document (passed through from SceneState).
            session_tone: Tone label from session (dramatic/grim/heroic/etc.).
            gm_profile:   Optional GMProfile dict — overrides session_tone when present.
            lorebook_context: Optional list of relevant lorebook entries.
            story_state:  Optional story state (arc, tension, threads) to guide pacing.

        Returns:
            {
                "narrative_text": str,
                "proposals":      List[dict],
                "turn_id":        str,
            }
        """
        # --- Single LLM call: DSPy creative generation + proposal extraction ---
        (
            narrative_text,
            raw_proposals,
            minutes_elapsed,
        ) = await self._generate_narrative_and_proposals(
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
            "minutes_elapsed": minutes_elapsed,
        }

    @staticmethod
    def _parse_minutes(raw: str) -> int:
        """Coerce string minutes to int, defaulting to 1 for tiny beats."""
        try:
            val = int(re.sub(r"[^\d]", "", raw))
            return max(1, val)
        except (ValueError, TypeError):
            return 1

    async def generate_opening(
        self,
        user_input: Optional[str],
        context: Dict[str, Any],
        game_context: Optional[Dict[str, Any]] = None,
        session_tone: str = "dramatic",
        gm_profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate one-off GM opening prose without persisting turns or proposals."""
        return await self._generate_narrative_text(
            user_input=user_input,
            resolution=None,
            context=context,
            game_context=game_context,
            session_tone=session_tone,
            gm_profile=gm_profile,
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
        user_input: Optional[str],
        resolution: Optional[Dict[str, Any]],
        context: Dict[str, Any],
        game_context: Optional[Dict[str, Any]] = None,
        session_tone: str = "dramatic",
        gm_profile: Optional[Dict[str, Any]] = None,
        lorebook_context: Optional[List[str]] = None,
        story_state: Optional[StoryState] = None,
    ) -> tuple[str, List[Dict[str, Any]], int]:
        """Run the DSPy narrator module and parse proposals from the output.

        Returns:
            (narrative_text, proposals, minutes_elapsed)
        """
        resolution_summary = self._format_resolution(resolution)

        compact_gc: dict[str, Any] = {}
        system_name = ""
        if game_context:
            try:
                from monitor_agents.game_system import GameSystemRuntime

                compact_gc = GameSystemRuntime(game_context).compact_for_narrator()
                system_name = compact_gc.get("name", "")
            except Exception:  # noqa: BLE001 — game system optional, continue with limited context
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

        # Gap 1: Inject actor personality, role, and tags into profile_context
        actor = context.get("actor")
        if actor:
            actor_name = actor.get("name", "the character")
            role = actor.get("role", "pc")
            personality = actor.get("personality", "")
            tags = ", ".join(actor.get("state_tags", []))
            actor_block = f"\n\nACTOR PROFILE ({actor_name}):\n- Role: {role}\n"
            if personality:
                actor_block += f"- Personality: {personality}\n"
            if tags:
                actor_block += f"- State: {tags}\n"
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

        # Resolve dynamic model role based on dramatic intensity.
        dynamic_role = resolve_dynamic_role(
            "narrator",
            player_action=user_input or "",
            resolution=resolution,
        )

        module_kwargs = dict(
            tone_context=tone_context,
            game_system_context=json.dumps(compact_gc, ensure_ascii=False, default=str),
            scene_context=json.dumps(context.get("entities", [])[:5], default=str),
            profile_context=profile_context,
            memory_context=json.dumps(context.get("memories", [])[:3], default=str),
            prior_turns=json.dumps(context.get("turns", [])[-3:], default=str),
            player_action=user_input or "(scene description)",
            resolution_summary=resolution_summary,
            role=dynamic_role,
        )
        # Resilience: some providers (notably MiniMax) intermittently return a
        # response that the DSPy JSON adapter can't fully parse — e.g. it omits
        # the trailing ``narrative_time_elapsed`` field, which makes DSPy *raise*
        # AdapterParseError and would otherwise crash the whole turn. Try up to
        # twice; on persistent failure degrade gracefully to an empty-but-safe
        # result so the session continues instead of dying.
        prediction = None
        narrative_text = ""
        for attempt in range(2):
            try:
                prediction = self._narrator_module(**module_kwargs)
                narrative_text = getattr(prediction, "narrative_text", "") or ""
                if narrative_text.strip():
                    break
                logger.warning("Narrator returned empty narrative_text (attempt %d)", attempt + 1)
            except Exception as exc:  # noqa: BLE001 — DSPy AdapterParseError et al.
                logger.warning("Narrator parse failed (attempt %d): %s", attempt + 1, exc)
                prediction = None

        if prediction is None:
            return narrative_text, [], 1

        # Parse proposed_changes from DSPy output (JSON array string)
        proposals = self._parse_proposed_changes(getattr(prediction, "proposed_changes", "[]"))
        minutes_elapsed = self._parse_minutes(getattr(prediction, "narrative_time_elapsed", "0"))
        return narrative_text, proposals, minutes_elapsed

    async def _generate_narrative_text(
        self,
        *,
        user_input: Optional[str],
        resolution: Optional[Dict[str, Any]],
        context: Dict[str, Any],
        game_context: Optional[Dict[str, Any]] = None,
        session_tone: str = "dramatic",
        gm_profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Run the DSPy narrator module — returns prose only (for opening narratives)."""
        text, _, _ = await self._generate_narrative_and_proposals(
            user_input=user_input,
            resolution=resolution,
            context=context,
            game_context=game_context,
            session_tone=session_tone,
            gm_profile=gm_profile,
        )
        return text

    @staticmethod
    def _parse_proposed_changes(raw: str) -> List[Dict[str, Any]]:
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
                except (json.JSONDecodeError, TypeError):  # noqa: BLE001
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

    async def _resolve_tone_context(
        self,
        session_tone: str = "dramatic",
        system_name: str = "",
        source_profile: Optional[Dict[str, Any]] = None,
        gm_profile: Optional[Dict[str, Any]] = None,
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
        extra_parts: List[str] = []
        if system_name:
            extra_parts.append(f"Setting: {system_name}.")

        profile_tone = build_tone_hints_from_profile(source_profile or {})
        if profile_tone:
            extra_parts.append(profile_tone)

        if extra_parts:
            return base + " " + " ".join(extra_parts)
        return base

    def _format_resolution(self, resolution: Optional[Dict[str, Any]]) -> str:
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
        user_input: Optional[str],
        narrative_text: str,
        resolution: Optional[Dict[str, Any]],
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
                    "text": narrative_text,
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

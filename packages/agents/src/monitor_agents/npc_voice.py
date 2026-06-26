"""
NPCVoice Agent — speaks directly as an NPC character.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts

Responsibilities:
- Generate in-character NPC responses for direct dialogue (DIRECT mode)
- Generate actor-mode reflections for GM prep (ACTOR mode)
- Persist conversation turns to MongoDB
- Stage relationship-change and profile-update proposals

Authority:
- MongoDB: read (entity profiles, memories) + write (conversation turns)
- Neo4j: READ ONLY (entity + fact lookup)
- No Neo4j writes — proposals go to MongoDB for CanonKeeper

LLM Role: ModelRole.LIGHT (fast + cheap)
  - Context is small (NPC profile + last N turns, no full scene)
  - Latency matters — live dialogue should feel responsive
  - Recommended: Claude Haiku 3.5, Gemini 2.0 Flash, GPT-4o-mini class

The in-scene variant (Mode 1 / SCENE) is handled by the Narrator agent.
NPCVoice is only for DIRECT and ACTOR modes.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from monitor_agents.base import BaseAgent
from monitor_agents.prompts.npc_voice import NPCDirectVoiceModule, NPCActorModule
from monitor_agents.utils.runtime_profile_support import (
    build_npc_profile_context,
    normalize_source_profile,
)


# =============================================================================
# RESPONSE MODELS (instructor-validated outputs)
# =============================================================================

from pydantic import BaseModel


class NPCDirectResponse(BaseModel):
    """Structured output from a direct NPC dialogue turn."""

    npc_response: str
    emotional_state_after: str
    relationship_delta: str  # 'trust:+0.1' | 'hostility:+0.2' | 'none'


class NPCActorResponse(BaseModel):
    """Structured output from an actor-mode reflection."""

    actor_response: str
    canon_insight: str  # 'update_profile:<field>=<value>' | 'new_fact:<stmt>' | 'none'


# =============================================================================
# AGENT
# =============================================================================


class NPCVoice(BaseAgent):
    """
    Generates NPC speech for direct dialogue and actor-mode reflection.

    Usage:
        agent = NPCVoice()

        # Direct in-character dialogue:
        result = await agent.respond_direct(
            conversation_id=uuid,
            npc_id=uuid,
            player_said="Who are you?",
        )

        # Actor-mode reflection:
        result = await agent.respond_actor(
            conversation_id=uuid,
            npc_id=uuid,
            gm_question="What would you do if the PC betrayed you?",
        )
    """

    def __init__(self, agent_id: str = "npc-voice-1") -> None:
        super().__init__(agent_type="NPCVoice", agent_id=agent_id)
        self._direct_module = NPCDirectVoiceModule()
        self._actor_module = NPCActorModule()

    async def run(self) -> None:
        pass  # driven by ConversationLoop

    # ------------------------------------------------------------------
    # Mode 2: Direct in-character dialogue
    # ------------------------------------------------------------------

    async def respond_direct(
        self,
        conversation_id: UUID,
        npc_id: UUID,
        player_said: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        player_entity_id: Optional[UUID] = None,
        scene_id: Optional[UUID] = None,
        story_id: Optional[UUID] = None,
        source_profile: Optional[Dict[str, Any]] = None,
        npc_data: Optional[Dict[str, Any]] = None,
        *,
        universe_id: Optional[UUID] = None,
        include_cross_incarnation: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate a direct in-character NPC response.

        Args:
            conversation_id: Active ConversationSession UUID.
            npc_id:          NPC EntityInstance UUID.
            player_said:     The player's input text.
            conversation_history: Prior turns in this session (optional).
            player_entity_id: The speaking player character, if known.
            scene_id: Current scene context for proposal staging.
            story_id: Current story context for proposal staging.
            universe_id: Per-universe incarnation scope. When set, recall +
                state + proposals are partitioned by this universe. Legacy
                callers that omit it keep the historical entity_id-only
                recall and write to the legacy profile fields.
            include_cross_incarnation: Broadens recall beyond the current
                incarnation. Only meaningful when universe_id is set.

        Returns:
            {
                "npc_response":           str,
                "emotional_state_after":  str,
                "relationship_delta":     str,
                "social_read":            dict,
                "relationship_snapshot":  dict,
                "proposals":              List[dict],
            }
        """
        # 1. Load NPC data from Neo4j + MongoDB profile
        npc_data = npc_data or await self._load_npc_data(npc_id)
        profile = npc_data["profile"]
        relationship_snapshot_before = self._relationship_snapshot(
            profile, player_entity_id, universe_id=universe_id
        )

        # 2. Recall NPC's memories of the player from Qdrant (universe-scoped)
        memories = await self._recall_memories(
            npc_id,
            player_said,
            universe_id=universe_id,
            include_cross_incarnation=include_cross_incarnation,
        )

        # 3. Build trigger context (only non-hidden ones at surface level)
        active_triggers = self._evaluate_triggers(profile.get("triggers", []), player_said)

        # 4. Run DSPy direct voice module (LIGHT model)
        history_text = self._format_history(conversation_history or [])
        profile_context = build_npc_profile_context(
            normalize_source_profile(source_profile or {}),
            npc_name=npc_data["name"],
            npc_role=npc_data["role"],
            npc_facts=npc_data.get("facts", []),
        )
        prediction = self._direct_module(
            npc_name=npc_data["name"],
            npc_role=npc_data["role"],
            personality_summary=self._format_personality(profile, relationship_snapshot_before),
            current_emotional_state=self._format_emotional_context(
                profile, relationship_snapshot_before, universe_id=universe_id
            ),
            relevant_memories=json.dumps(memories[:5], default=str),
            known_facts=json.dumps(npc_data.get("facts", [])[:8], default=str),
            active_triggers=json.dumps(active_triggers, default=str),
            conversation_history=history_text,
            profile_context=profile_context,
            player_said=player_said,
        )

        # 5. Extract structured fields from prediction
        npc_response = prediction.npc_response
        emotional_state_after = prediction.emotional_state_after
        relationship_delta = prediction.relationship_delta
        relationship_snapshot_after = self._build_relationship_snapshot(
            profile=profile,
            player_entity_id=player_entity_id,
            relationship_delta=relationship_delta,
            emotional_state_after=emotional_state_after,
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
            reason=f'Player said: "{player_said}" | NPC replied: "{npc_response}"',
        )
        social_read = {
            "target_entity_id": str(player_entity_id) if player_entity_id else None,
            "stance_after": relationship_snapshot_after.get("stance")
            if relationship_snapshot_after
            else None,
            "deltas": relationship_snapshot_after.get("last_delta", {})
            if relationship_snapshot_after
            else {},
            "reason": relationship_snapshot_after.get("last_shift_reason")
            if relationship_snapshot_after
            else None,
            "confidence": max(
                0.55,
                min(
                    0.95,
                    0.65
                    + abs((self._parse_relationship_delta(relationship_delta) or ("none", 0.0))[1]),
                ),
            ),
        }

        # 6. Persist NPC turn to MongoDB
        await self._persist_npc_turn(
            conversation_id=conversation_id,
            npc_id=npc_id,
            npc_name=npc_data["name"],
            text=npc_response,
            emotional_state=emotional_state_after,
        )

        # 7. Update the NPC's working social state in MongoDB (best-effort)
        await self._update_working_social_state(
            npc_id=npc_id,
            emotional_state_after=emotional_state_after,
            relationship_snapshot=relationship_snapshot_after,
            player_entity_id=player_entity_id,
            universe_id=universe_id,
        )

        # 8. Build proposals (relationship change + emotional state update)
        proposals = self._build_proposals(
            npc_id=npc_id,
            relationship_delta=relationship_delta,
            emotional_state_after=emotional_state_after,
            profile=profile,
            player_entity_id=player_entity_id,
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
        )

        # 9. Write NPC memory of this exchange
        await self._write_npc_memory(
            npc_id=npc_id,
            player_said=player_said,
            npc_said=npc_response,
            conversation_id=conversation_id,
            emotional_state_after=emotional_state_after,
            relationship_delta=relationship_delta,
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
        )

        return {
            "npc_response": npc_response,
            "emotional_state_after": emotional_state_after,
            "relationship_delta": relationship_delta,
            "social_read": social_read,
            "relationship_snapshot": relationship_snapshot_after,
            "proposals": proposals,
        }

    # ------------------------------------------------------------------
    # Mode 3: Actor-mode reflection
    # ------------------------------------------------------------------

    async def respond_actor(
        self,
        conversation_id: UUID,
        npc_id: UUID,
        gm_question: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        source_profile: Optional[Dict[str, Any]] = None,
        npc_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate an actor-mode reflection response.

        Args:
            conversation_id: Active ConversationSession UUID.
            npc_id:          NPC EntityInstance UUID.
            gm_question:     GM's question for the actor.
            conversation_history: Prior turns in this session.

        Returns:
            {
                "actor_response":  str,
                "canon_insight":   str,
                "proposals":       List[dict],
            }
        """
        # 1. Load full NPC profile (including secrets for actor mode)
        npc_data = npc_data or await self._load_npc_data(npc_id, include_secrets=True)
        profile = npc_data["profile"]

        # 2. Get story context from recent facts
        story_context = await self._get_story_context(npc_id)

        # 3. Run DSPy actor module (LIGHT model, CoT)
        history_text = self._format_history(conversation_history or [])
        profile_context = build_npc_profile_context(
            normalize_source_profile(source_profile or {}),
            npc_name=npc_data["name"],
            npc_role=npc_data["role"],
            npc_facts=npc_data.get("facts", []),
        )
        prediction = self._actor_module(
            npc_name=npc_data["name"],
            full_profile=json.dumps(profile, default=str),
            story_context=story_context,
            profile_context=profile_context,
            conversation_history=history_text,
            gm_question=gm_question,
        )

        actor_response = prediction.actor_response
        canon_insight = prediction.canon_insight

        # 4. Persist actor turn to MongoDB
        await self._persist_npc_turn(
            conversation_id=conversation_id,
            npc_id=npc_id,
            npc_name=npc_data["name"],
            text=actor_response,
            emotional_state=None,
        )

        # 5. Build proposals from canon_insight (if any)
        proposals = self._build_insight_proposals(npc_id, canon_insight)

        return {
            "actor_response": actor_response,
            "canon_insight": canon_insight,
            "proposals": proposals,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_npc_data(
        self,
        npc_id: UUID,
        include_secrets: bool = False,
    ) -> Dict[str, Any]:
        """Load NPC entity + profile from Neo4j / MongoDB via MCP tools."""
        entity, profile_raw, facts_result = await asyncio.gather(
            self.call_tool("neo4j_get_entity", {"entity_id": str(npc_id)}),
            self.call_tool("mongodb_get_npc_profile", {"entity_id": str(npc_id)}),
            self.call_tool("neo4j_list_facts", {"entity_id": str(npc_id), "limit": 10}),
        )
        if not entity:
            raise ValueError(f"NPC entity {npc_id} not found in Neo4j")

        props = entity.get("properties", {})
        profile: Dict[str, Any] = profile_raw or {}

        if not include_secrets:
            profile.pop("secrets", None)
            profile.pop("gm_notes", None)

        # Mask hidden triggers (is_hidden=True) for DIRECT mode
        if not include_secrets and "triggers" in profile:
            profile["triggers"] = [t for t in profile["triggers"] if not t.get("is_hidden", True)]

        facts = facts_result if isinstance(facts_result, list) else []

        return {
            "name": entity.get("name", "Unknown"),
            "role": props.get("role", "character"),
            "profile": profile,
            "facts": [f.get("statement", "") for f in facts],
        }

    async def _recall_memories(
        self,
        npc_id: UUID,
        query: str,
        *,
        universe_id: Optional[UUID] = None,
        include_cross_incarnation: bool = False,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic memory recall from Qdrant for this NPC.

        By default filters strictly by (entity_id, universe_id) — no cross-
        incarnation leak. Pass include_cross_incarnation=True to broaden the
        filter to the entity as a whole (entity_id only). Legacy callers
        that omit universe_id keep the historical entity_id-only recall.
        """
        search_kwargs: Dict[str, Any] = {
            "entity_id": str(npc_id),
            "query_text": query,
            "top_k": top_k,
        }
        # When cross-incarnation recall is requested, drop the universe
        # scope so a sibling universe's incarnation of the same entity can
        # answer. Without this, the universe_id filter below silently
        # narrows recall back to the current incarnation and the flag is
        # a no-op (codex P2).
        if universe_id is not None and not include_cross_incarnation:
            search_kwargs["universe_id"] = str(universe_id)
        if include_cross_incarnation:
            search_kwargs["include_cross_incarnation"] = True

        # Wrap params per the data-layer tool contract (MemorySearchRequest).
        # Live e2e (Kvothe) surfaced that flat dicts fail Pydantic validation
        # in production; this restore is required.
        result = await self.call_tool(
            "qdrant_search_memories", {"params": search_kwargs}
        )
        return result if isinstance(result, list) else []

    async def _get_story_context(self, npc_id: UUID) -> str:
        """Summarise recent facts about the NPC for actor mode."""
        facts_result = await self.call_tool(
            "neo4j_list_facts", {"entity_id": str(npc_id), "limit": 15}
        )
        facts = facts_result if isinstance(facts_result, list) else []
        statements = [f.get("statement", "") for f in facts if f.get("statement")]
        if not statements:
            return "No recorded story events yet."
        return "; ".join(statements[:10])

    def _evaluate_triggers(
        self, triggers: List[Dict[str, Any]], player_said: str
    ) -> List[Dict[str, Any]]:
        """Return triggers whose condition appears in player_said (simple substring match)."""
        player_lower = player_said.lower()
        active = []
        for t in triggers:
            condition = t.get("condition", "").lower()
            # Simple heuristic: any key word from condition appears in player input
            if any(word in player_lower for word in condition.split() if len(word) > 3):
                active.append(t)
        return active[:3]  # cap at 3 to avoid prompt bloat

    def _clamp_social_value(self, value: Any) -> float:
        """Clamp social metrics to the normalized -1.0..1.0 range."""
        try:
            return round(max(-1.0, min(1.0, float(value))), 3)
        except (TypeError, ValueError):
            return 0.0

    def _parse_relationship_delta(self, relationship_delta: str) -> tuple[str, float] | None:
        """Parse `trust:+0.1` style deltas into structured data."""
        raw = (relationship_delta or "").strip()
        if not raw or raw.lower() == "none":
            return None
        try:
            axis, delta_str = raw.split(":", 1)
            return axis.strip().lower(), float(delta_str.strip())
        except (ValueError, AttributeError):
            return None

    def _relationship_snapshot(
        self,
        profile: Dict[str, Any],
        player_entity_id: Optional[UUID],
        *,
        universe_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Return the NPC's normalized stance toward the current speaker.

        Resolution order:
          1. relationship_states_by_universe[universe_id][player_id] (preferred)
          2. legacy relationship_states[player_id] (fallback for old data)
        """
        if player_entity_id is None:
            return {}

        snapshot: Dict[str, Any] = {
            "stance": "neutral",
            "trust": 0.0,
            "affinity": 0.0,
            "fear": 0.0,
            "leverage": 0.0,
            "familiarity": 0.0,
            "interest": 0.0,
        }

        # Prefer the per-universe partition when available.
        existing: Dict[str, Any] = {}
        if universe_id is not None:
            by_universe = profile.get("relationship_states_by_universe") or {}
            universe_map = by_universe.get(str(universe_id)) or {}
            candidate = universe_map.get(str(player_entity_id))
            if isinstance(candidate, dict):
                existing = candidate
        # Fallback: legacy single-universe map (key by player).
        if not existing:
            legacy = (profile.get("relationship_states") or {}).get(
                str(player_entity_id)
            )
            if isinstance(legacy, dict):
                existing = legacy

        if existing:
            snapshot.update(existing)
            if "score" in existing and "trust" not in existing:
                snapshot["trust"] = existing.get("score", 0.0)
            if existing.get("sentiment") and not existing.get("stance"):
                snapshot["stance"] = str(existing.get("sentiment"))

        for metric in ("trust", "affinity", "fear", "leverage", "familiarity", "interest"):
            snapshot[metric] = self._clamp_social_value(snapshot.get(metric, 0.0))
        return snapshot

    def _format_emotional_context(
        self,
        profile: Dict[str, Any],
        relationship_snapshot: Optional[Dict[str, Any]] = None,
        *,
        universe_id: Optional[UUID] = None,
    ) -> str:
        """Blend internal emotional state with relationship stance for prompt grounding.

        Reads the per-universe emotional state when available; falls back to
        the legacy single-emotion field for profiles that haven't been
        versioned yet.
        """
        base = "neutral"
        if universe_id is not None:
            by_universe = profile.get("current_emotional_state_by_universe") or {}
            base = str(by_universe.get(str(universe_id)) or base)
        if base == "neutral":
            base = str(profile.get("current_emotional_state") or "neutral")
        if not relationship_snapshot:
            return base
        return (
            f"{base}; stance toward the current speaker is {relationship_snapshot.get('stance', 'neutral')} "
            f"(trust {relationship_snapshot.get('trust', 0.0):+.2f}, fear {relationship_snapshot.get('fear', 0.0):+.2f})"
        )

    def _build_relationship_snapshot(
        self,
        profile: Dict[str, Any],
        player_entity_id: Optional[UUID],
        relationship_delta: str,
        emotional_state_after: str,
        scene_id: Optional[UUID] = None,
        story_id: Optional[UUID] = None,
        reason: str | None = None,
        *,
        universe_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Compute the NPC's updated working social stance after this exchange.

        When universe_id is provided, the snapshot's prior state is read from
        (and the result can be written into) the per-universe partition,
        isolating this NPC's relationship drift across incarnations.
        """
        if player_entity_id is None:
            return {}

        snapshot = dict(
            self._relationship_snapshot(
                profile, player_entity_id, universe_id=universe_id
            )
        )
        parsed = self._parse_relationship_delta(relationship_delta)
        deltas: Dict[str, float] = {}

        snapshot["familiarity"] = self._clamp_social_value(snapshot.get("familiarity", 0.0) + 0.05)

        if parsed:
            axis, delta = parsed
            magnitude = abs(delta)
            if axis in {"trust", "confidence", "respect"}:
                snapshot["trust"] = self._clamp_social_value(snapshot.get("trust", 0.0) + delta)
                deltas["trust"] = round(delta, 3)
            elif axis in {"hostility", "anger", "resentment", "suspicion", "distrust"}:
                snapshot["trust"] = self._clamp_social_value(snapshot.get("trust", 0.0) - magnitude)
                snapshot["affinity"] = self._clamp_social_value(
                    snapshot.get("affinity", 0.0) - (magnitude * 0.5)
                )
                snapshot["fear"] = self._clamp_social_value(
                    snapshot.get("fear", 0.0) + (magnitude * 0.25)
                )
                deltas["trust"] = round(-magnitude, 3)
            elif axis in {"affinity", "friendship", "warmth", "admiration", "loyalty"}:
                snapshot["affinity"] = self._clamp_social_value(
                    snapshot.get("affinity", 0.0) + delta
                )
                deltas["affinity"] = round(delta, 3)
            elif axis in {"fear", "anxiety", "worry"}:
                snapshot["fear"] = self._clamp_social_value(snapshot.get("fear", 0.0) + delta)
                deltas["fear"] = round(delta, 3)
            elif axis in {"leverage", "obligation", "debt"}:
                snapshot["leverage"] = self._clamp_social_value(
                    snapshot.get("leverage", 0.0) + delta
                )
                deltas["leverage"] = round(delta, 3)
            else:
                snapshot["trust"] = self._clamp_social_value(
                    snapshot.get("trust", 0.0) + (delta * 0.5)
                )
                deltas["trust"] = round(delta * 0.5, 3)
        else:
            axis = "none"
            delta = 0.0

        emotion_lower = (emotional_state_after or "").lower()
        if (
            any(token in emotion_lower for token in ("hostile", "angry", "furious"))
            or snapshot.get("trust", 0.0) <= -0.35
        ):
            snapshot["stance"] = "hostile"
        elif (
            any(token in emotion_lower for token in ("warm", "friendly", "grateful", "respectful"))
            or snapshot.get("trust", 0.0) >= 0.45
            or snapshot.get("affinity", 0.0) >= 0.35
        ):
            snapshot["stance"] = "warm"
        elif (
            any(token in emotion_lower for token in ("guarded", "cautious", "wary", "suspicious"))
            or snapshot.get("fear", 0.0) >= 0.35
        ):
            snapshot["stance"] = "guarded"
        else:
            snapshot["stance"] = snapshot.get("stance") or "neutral"

        snapshot["last_shift_reason"] = reason or f"Conversation nudged {axis} by {delta:+.2f}."
        snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()
        if scene_id is not None:
            snapshot["last_scene_id"] = str(scene_id)
        if story_id is not None:
            snapshot["last_story_id"] = str(story_id)
        if deltas:
            snapshot["last_delta"] = deltas

        return snapshot

    def _emotion_to_state_tags(self, emotional_state_after: str) -> tuple[list[str], list[str]]:
        """Map freeform emotional labels to MONITOR's canonical state tags."""
        lowered = (emotional_state_after or "").lower()
        if any(token in lowered for token in ("hostile", "angry", "furious")):
            return ["hostile"], ["friendly", "neutral"]
        if any(
            token in lowered for token in ("warm", "friendly", "respectful", "grateful", "kind")
        ):
            return ["friendly"], ["hostile", "neutral"]
        if any(token in lowered for token in ("fear", "afraid", "terrified", "nervous")):
            return ["frightened"], []
        if any(token in lowered for token in ("guarded", "neutral", "cautious", "wary")):
            return ["neutral"], ["friendly", "hostile"]
        return [], []

    def _format_personality(
        self,
        profile: Dict[str, Any],
        relationship_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compress profile into a compact string for the prompt."""
        parts = []
        if profile.get("speech_style"):
            parts.append(f"Speech: {profile['speech_style']}")
        traits = profile.get("traits", {})
        if traits:
            top_traits = sorted(traits.items(), key=lambda x: abs(x[1]), reverse=True)[:4]
            parts.append("Traits: " + ", ".join(f"{k}({v:+.1f})" for k, v in top_traits))
        if profile.get("values"):
            parts.append("Values: " + ", ".join(profile["values"][:3]))
        if profile.get("fears"):
            parts.append("Fears: " + ", ".join(profile["fears"][:2]))
        if profile.get("desires"):
            parts.append("Desires: " + ", ".join(profile["desires"][:2]))
        if profile.get("catchphrases"):
            parts.append("Catchphrases: " + "; ".join(profile["catchphrases"][:2]))
        if relationship_snapshot:
            parts.append(
                "Speaker stance: "
                f"{relationship_snapshot.get('stance', 'neutral')} "
                f"(trust {relationship_snapshot.get('trust', 0.0):+.2f}, "
                f"fear {relationship_snapshot.get('fear', 0.0):+.2f}, "
                f"leverage {relationship_snapshot.get('leverage', 0.0):+.2f})"
            )
        return " | ".join(parts) if parts else "No personality profile defined."

    def _format_history(self, turns: List[Dict[str, Any]]) -> str:
        """Format last N conversation turns into a compact string."""
        if not turns:
            return "(no prior turns)"
        lines = []
        for t in turns[-8:]:  # last 8 turns max
            role = t.get("speaker_role", "?")
            name = t.get("entity_name") or role
            text = t.get("text", "")
            lines.append(f"{name}: {text}")
        return "\n".join(lines)

    def _build_proposals(
        self,
        npc_id: UUID,
        relationship_delta: str,
        emotional_state_after: str,
        profile: Dict[str, Any],
        player_entity_id: Optional[UUID] = None,
        scene_id: Optional[UUID] = None,
        story_id: Optional[UUID] = None,
        universe_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Build canonical ProposedChange dicts for social state updates.

        When universe_id is provided, the proposal content's profile_updates
        populate the per-universe partition maps (relationship_states_by_universe,
        current_emotional_state_by_universe) so CanonKeeper commits the deltas
        into the right incarnation only. The legacy fields stay populated as
        a fallback for any reader that hasn't migrated.
        """
        proposals: List[Dict[str, Any]] = []
        add_tags, remove_tags = self._emotion_to_state_tags(emotional_state_after)

        # Per-universe emotional state takes precedence when universe_id is set.
        current_emotion_for_diff: Optional[str] = None
        if universe_id is not None:
            by_universe = profile.get("current_emotional_state_by_universe") or {}
            current_emotion_for_diff = by_universe.get(str(universe_id))
        if current_emotion_for_diff is None:
            current_emotion_for_diff = profile.get("current_emotional_state")

        if emotional_state_after and emotional_state_after != current_emotion_for_diff:
            state_content: Dict[str, Any] = {
                "entity_id": str(npc_id),
                "current_emotional_state": emotional_state_after,
                "add_tags": add_tags,
                "remove_tags": remove_tags,
                "profile_updates": {"current_emotional_state": emotional_state_after},
            }
            if scene_id is not None:
                state_content["scene_id"] = str(scene_id)
            if story_id is not None:
                state_content["story_id"] = str(story_id)
            if universe_id is not None:
                state_content["universe_id"] = str(universe_id)
                state_content["profile_updates"][
                    "current_emotional_state_by_universe"
                ] = {str(universe_id): emotional_state_after}
            proposals.append(
                {
                    "change_type": "state_change",
                    "content": state_content,
                    "confidence": 0.9,
                    "proposer": "NPCVoice",
                }
            )

        parsed = self._parse_relationship_delta(relationship_delta)
        if parsed and player_entity_id is not None and player_entity_id != npc_id:
            axis, delta = parsed
            relationship_snapshot = self._build_relationship_snapshot(
                profile=profile,
                player_entity_id=player_entity_id,
                relationship_delta=relationship_delta,
                emotional_state_after=emotional_state_after,
                scene_id=scene_id,
                story_id=story_id,
                universe_id=universe_id,
            )
            trust_after = relationship_snapshot.get("trust", 0.0)
            affinity_after = relationship_snapshot.get("affinity", 0.0)
            if (
                axis in {"hostility", "anger", "resentment", "suspicion", "distrust"}
                or trust_after <= -0.2
            ):
                rel_type = "HOSTILE_TO"
            elif axis in {"trust", "respect", "affinity", "admiration", "loyalty"} and (
                trust_after >= 0.35 or affinity_after >= 0.3
            ):
                rel_type = "ALLIED_WITH"
            else:
                rel_type = "KNOWS"

            relationship_content: Dict[str, Any] = {
                "from_entity_id": str(npc_id),
                "to_entity_id": str(player_entity_id),
                "rel_type": rel_type,
                "properties": {
                    "sentiment": axis,
                    "delta": delta,
                    "new_value": relationship_snapshot.get(
                        axis if axis in relationship_snapshot else "trust"
                    ),
                    "stance_after": relationship_snapshot.get("stance"),
                    "confidence": max(0.6, min(0.95, 0.7 + abs(delta))),
                    "current_emotional_state": emotional_state_after,
                },
                "profile_updates": {
                    "current_emotional_state": emotional_state_after,
                    "relationship_states": {
                        str(player_entity_id): {
                            k: v for k, v in relationship_snapshot.items() if k != "last_delta"
                        }
                    },
                },
            }
            if scene_id is not None:
                relationship_content["scene_id"] = str(scene_id)
            if story_id is not None:
                relationship_content["story_id"] = str(story_id)
            if universe_id is not None:
                relationship_content["universe_id"] = str(universe_id)
                relationship_content["profile_updates"][
                    "relationship_states_by_universe"
                ] = {
                    str(universe_id): {
                        str(player_entity_id): {
                            k: v for k, v in relationship_snapshot.items() if k != "last_delta"
                        }
                    }
                }
            proposals.append(
                {
                    "change_type": "relationship",
                    "content": relationship_content,
                    "confidence": max(0.6, min(0.95, 0.7 + abs(delta))),
                    "proposer": "NPCVoice",
                }
            )

        return proposals

    def _build_insight_proposals(self, npc_id: UUID, canon_insight: str) -> List[Dict[str, Any]]:
        """Build normalized ProposedChange payloads from actor-mode insights."""
        if not canon_insight or canon_insight.strip().lower() == "none":
            return []

        if canon_insight.startswith("update_profile:"):
            remainder = canon_insight[len("update_profile:") :]
            try:
                field, value = remainder.split("=", 1)
                return [
                    {
                        "change_type": "entity",
                        "content": {
                            "entity_id": str(npc_id),
                            "profile_updates": {field.strip(): value.strip()},
                        },
                        "confidence": 0.6,
                        "proposer": "NPCVoice",
                    }
                ]
            except ValueError:
                return []

        if canon_insight.startswith("new_fact:"):
            statement = canon_insight[len("new_fact:") :]
            return [
                {
                    "change_type": "fact",
                    "content": {
                        "statement": statement.strip(),
                        "entity_id": str(npc_id),
                    },
                    "confidence": 0.5,
                    "proposer": "NPCVoice",
                }
            ]

        return []

    async def _update_working_social_state(
        self,
        npc_id: UUID,
        emotional_state_after: str,
        relationship_snapshot: Optional[Dict[str, Any]],
        player_entity_id: Optional[UUID],
        *,
        universe_id: Optional[UUID] = None,
    ) -> None:
        """Best-effort update of the NPC's working social state in MongoDB.

        When universe_id is provided, the emotional state + relationship
        snapshot are written into the per-universe partition maps, isolating
        this NPC's working state from other incarnations. The legacy
        single-universe fields are still updated as a fallback so legacy
        readers see fresh data.
        """
        params: Dict[str, Any] = {"current_emotional_state": emotional_state_after}
        if player_entity_id is not None and relationship_snapshot:
            snapshot_without_delta = {
                key: value
                for key, value in relationship_snapshot.items()
                if key != "last_delta"
            }
            params["relationship_states"] = {
                str(player_entity_id): snapshot_without_delta,
            }
            if universe_id is not None:
                params["relationship_states_by_universe"] = {
                    str(universe_id): {
                        str(player_entity_id): snapshot_without_delta,
                    }
                }
                params["current_emotional_state_by_universe"] = {
                    str(universe_id): emotional_state_after,
                }
        try:
            await self.call_tool(
                "mongodb_update_npc_profile",
                {"entity_id": str(npc_id), "params": params},
            )
        except Exception:
            return

    async def _persist_npc_turn(
        self,
        conversation_id: UUID,
        npc_id: UUID,
        npc_name: str,
        text: str,
        emotional_state: Optional[str],
    ) -> None:
        """Append this NPC turn to the ConversationSession in MongoDB."""
        await self.call_tool(
            "mongodb_append_conversation_turn",
            {
                "conversation_id": str(conversation_id),
                "params": {
                    "speaker_role": "npc",
                    "entity_id": str(npc_id),
                    "entity_name": npc_name,
                    "text": text,
                    "emotional_state": emotional_state,
                },
            },
        )

    async def _write_npc_memory(
        self,
        npc_id: UUID,
        player_said: str,
        npc_said: str,
        conversation_id: UUID,
        emotional_state_after: Optional[str] = None,
        relationship_delta: Optional[str] = None,
        scene_id: Optional[UUID] = None,
        story_id: Optional[UUID] = None,
        universe_id: Optional[UUID] = None,
    ) -> None:
        """Create a CharacterMemory for the NPC about this exchange."""
        memory_bits = [
            f'Player said: "{player_said}".',
            f'I responded: "{npc_said}".',
        ]
        if emotional_state_after:
            memory_bits.append(f"I felt {emotional_state_after} afterward.")
        if relationship_delta and relationship_delta.lower() != "none":
            memory_bits.append(f"Relationship shift: {relationship_delta}.")

        importance = 0.5
        parsed = self._parse_relationship_delta(relationship_delta or "")
        if parsed is not None:
            importance = max(0.5, min(0.9, 0.5 + abs(parsed[1])))

        metadata: Dict[str, Any] = {"conversation_id": str(conversation_id)}
        if scene_id is not None:
            metadata["scene_id"] = str(scene_id)
        if story_id is not None:
            metadata["story_id"] = str(story_id)
        if emotional_state_after:
            metadata["emotional_state"] = emotional_state_after
        if relationship_delta:
            metadata["relationship_delta"] = relationship_delta

        # Universe_id partitions the memory into a specific incarnation.
        # MemoryCreate.universe_id is required, so resolve it: prefer the
        # caller's value, else look up the NPC's home universe from Neo4j
        # (one extra read; legacy callers that don't pass it keep working).
        resolved_universe_id: Optional[str] = (
            str(universe_id) if universe_id is not None else None
        )
        if resolved_universe_id is None:
            try:
                ent = await self.call_tool(
                    "neo4j_get_entity", {"entity_id": str(npc_id)}
                )
                if isinstance(ent, dict):
                    resolved_universe_id = ent.get("universe_id") or ent.get(
                        "properties", {}
                    ).get("universe_id")
            except Exception:  # noqa: BLE001
                resolved_universe_id = None

        # Wrap params per the data-layer tool contract (MemoryCreate).
        # Live e2e surfaced that flat dicts fail Pydantic validation.
        # MemoryCreate.universe_id is REQUIRED — callers must pass a
        # resolved id; if the caller did not, fall back to the
        # character doc via a best-effort Mongo read.
        if not resolved_universe_id:
            try:
                from monitor_data.db.mongodb import get_mongodb_client
                coll = get_mongodb_client().get_collection("characters")
                doc = coll.find_one({"versions.entity_id": str(npc_id)})
                if doc:
                    for v in doc.get("versions", []):
                        if v.get("entity_id") == str(npc_id):
                            resolved_universe_id = v.get("universe_id")
                            break
            except Exception:  # noqa: BLE001
                pass
        if not resolved_universe_id:
            raise RuntimeError(
                "_write_npc_memory: no universe_id resolved for entity "
                f"{npc_id}; ensure ConversationLoop passes state.universe_id "
                "or the character was expanded in the conversatory universe."
            )
        await self.call_tool(
            "mongodb_create_memory",
            {
                "params": {
                    "entity_id": str(npc_id),
                    "text": " ".join(memory_bits),
                    "importance": importance,
                    "metadata": metadata,
                    "universe_id": resolved_universe_id,
                },
            },
        )


import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import anyio

from monitor_agents.loops.scene_support import (
    _award_xp,
    apply_resource_delta,
    canonical_state_tags,
    coerce_uuid,
    derive_state_deltas,
    normalise_resource_value,
    seed_actor_state,
)

logger = logging.getLogger(__name__)


class PersistenceService:
    """Service encapsulating persistence logic for the Scene Loop."""

    @staticmethod
    def build_checkpoint_summary(
        narrative_text: str | None,
        success_level: str,
        resources: dict[str, Any],
        condition_tags: list[str],
    ) -> str:
        """Create a concise scene-summary checkpoint with current resources."""
        excerpt = (narrative_text or "The scene shifts.").strip()
        if len(excerpt) > 220:
            excerpt = excerpt[:217].rstrip() + "..."

        interesting_keys = [
            key
            for key, snap in resources.items()
            if isinstance(snap, dict) and isinstance(snap.get("current"), (int, float))
        ][:5]
        resource_bits: list[str] = []
        for key in interesting_keys:
            snapshot = resources.get(key) or {}
            current = snapshot.get("current")
            maximum = snapshot.get("max")
            if maximum not in (None, ""):
                resource_bits.append(f"{key} {current}/{maximum}")
            else:
                resource_bits.append(f"{key} {current}")

        suffix_parts = [success_level.replace("_", " ")]
        if resource_bits:
            suffix_parts.append(", ".join(resource_bits))
        if condition_tags:
            suffix_parts.append("tags: " + ", ".join(condition_tags))
        return f"{excerpt} [{' | '.join(suffix_parts)}]"

    @staticmethod
    def build_state_change_summary(
        deltas: dict[str, int],
        condition_tags: list[str],
        add_tags: list[str],
    ) -> str:
        """Summarize the staged state drift for CanonKeeper review."""
        changes: list[str] = []
        for key, delta in deltas.items():
            if delta:
                sign = "+" if delta > 0 else ""
                changes.append(f"{key} {sign}{delta}")
        if condition_tags:
            changes.append("conditions: " + ", ".join(condition_tags))
        if add_tags:
            changes.append("canon tags: " + ", ".join(add_tags))
        return "Scene state changed — " + "; ".join(changes) if changes else "Scene state changed."

    @staticmethod
    async def persist_memories(
        *,
        entity_id: UUID,
        scene_id: UUID,
        story_id: UUID,
        universe_id: UUID,
        memories: list[dict[str, Any]],
    ) -> list[UUID]:
        """Task 4: Save extracted memories to MongoDB.

        Each memory is embedded in Qdrant via mongodb_create_memory hook.
        """
        if not memories:
            return []

        from monitor_data.schemas.memories import MemoryCreate
        from monitor_data.tools.mongodb_tools import mongodb_create_memory

        created_ids = []
        for m in memories:
            try:
                raw_importance = m.get("importance", 5)
                importance_float = float(raw_importance) / 10.0 if raw_importance > 1 else float(raw_importance)
                params = MemoryCreate(
                    universe_id=universe_id,
                    entity_id=entity_id,
                    scene_id=scene_id,
                    text=m["text"],
                    importance=min(1.0, max(0.0, importance_float)),
                    emotional_valence=m.get("emotional_valence", 0.0),
                    metadata={"story_id": str(story_id)},
                )
                # mongodb_create_memory is a sync tool from Layer 1
                res = await anyio.to_thread.run_sync(mongodb_create_memory, params)
                created_ids.append(res.memory_id)
            except Exception as e:
                logger.warning("Failed to persist memory for entity %s: %s", entity_id, e)

        return created_ids

    @staticmethod
    async def persist_working_state(
        *,
        scene_id: UUID,
        story_id: UUID,
        actor_id: UUID | None,
        entity_context: list[dict[str, Any]],
        game_context: dict[str, Any],
        resolution: dict[str, Any],
        user_input: str | None,
        narrative_text: str | None,
        turn_id: UUID | None,
        pending_proposals: list[dict[str, Any]],
        resource_deltas: list[dict[str, Any]] | None = None,
        memories_to_persist: list[dict[str, Any]] | None = None,
        actor_context: dict[str, Any] | None = None,
        universe_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Upsert scene-scoped working state and return a UI-friendly snapshot.

        This is a pure data function that accepts explicit parameters rather than
        a SceneState reference, making it testable without the full graph.

        resource_deltas: Optional list of ResourceDelta dicts from ResourceEngine.
        These are merged into deltas before applying to working_state, enabling
        earn-on-failure, session_start, and other game-context-driven resource
        changes that derive_state_deltas alone cannot infer.
        """
        if not resolution:
            return {}
        resource_deltas = resource_deltas or []

        from monitor_data.schemas.base import Authority, ProposalType
        from monitor_data.schemas.proposed_changes import Evidence, ProposedChangeCreate
        from monitor_data.schemas.working_state import (
            AddStatModification,
            WorkingStateCreate,
            WorkingStateUpdate,
        )
        from monitor_data.tools.mongodb_tools import (
            mongodb_add_modification,
            mongodb_create_proposed_change,
            mongodb_create_working_state,
            mongodb_get_working_state,
            mongodb_update_working_state,
        )

        actor_uuid = coerce_uuid(
            actor_id,
            seed=f"monitor://scene/{scene_id}/actor/default",
        )

        # Task 4: Persist extracted memories
        if memories_to_persist:
            await PersistenceService.persist_memories(
                entity_id=actor_uuid,
                scene_id=scene_id,
                story_id=story_id,
                universe_id=universe_id or UUID(int=0),
                memories=memories_to_persist,
            )

        base_stats, seed_resources = seed_actor_state(
            entity_context,
            actor_id,
            game_context,
            actor_context=actor_context,
        )

        existing = await anyio.to_thread.run_sync(lambda: mongodb_get_working_state(actor_uuid, scene_id))
        if existing and getattr(existing, "state", None):
            working_state = existing.state
            merged_resources = {
                str(key): normalise_resource_value(str(key), value)
                for key, value in (working_state.resources or {}).items()
            }
            for key, value in seed_resources.items():
                merged_resources.setdefault(key, value)
            current_stats = dict(working_state.current_stats or base_stats or {})
            state_id = working_state.state_id
        else:
            created = await anyio.to_thread.run_sync(
                lambda: mongodb_create_working_state(
                    WorkingStateCreate(
                        entity_id=actor_uuid,
                        scene_id=scene_id,
                        story_id=story_id,
                        base_stats=base_stats,
                        current_stats=base_stats or None,
                        resources=seed_resources,
                    )
                )
            )
            working_state = created.state
            merged_resources = {
                str(key): normalise_resource_value(str(key), value) for key, value in seed_resources.items()
            }
            for key, value in (working_state.resources or {}).items():
                merged_resources.setdefault(str(key), normalise_resource_value(str(key), value))
            current_stats = dict(working_state.current_stats or base_stats or {})
            state_id = working_state.state_id

        deltas, condition_tags = await derive_state_deltas(
            resolution,
            user_input,
            narrative_text,
            resources=merged_resources,
            game_context=game_context,
        )
        if condition_tags:
            current_stats["conditions"] = condition_tags
        current_stats["narrative_pressure"] = str(resolution.get("narrative_pressure") or "steady")
        current_stats["last_success_level"] = str(resolution.get("success_level") or "success")

        for key, delta in list(deltas.items()):
            if key not in merged_resources:
                default_cap = 0
                for track_def in list(game_context.get("tracks") or []):
                    t_name = str(track_def.get("name") or "")
                    t_abbr = str(track_def.get("abbreviation") or t_name[:6])
                    if key.lower() in {t_name.lower(), t_abbr.lower()} or t_name.lower() in key.lower():
                        default_cap = track_def.get("max_value") or 0
                        break
                merged_resources[key] = normalise_resource_value(key, default_cap, default_cap)
            if delta:
                merged_resources[key] = apply_resource_delta(merged_resources[key], delta)

        # Apply ResourceEngine deltas (earn_on_failure, session_start, etc.)
        engine_modifications: list[Any] = []
        for rd in resource_deltas:
            key = str(rd.get("resource_key", ""))
            delta = int(rd.get("delta", 0))
            if not key or not delta:
                continue
            if key not in merged_resources:
                merged_resources[key] = normalise_resource_value(key, 0, 0)
            if delta:
                merged_resources[key] = apply_resource_delta(merged_resources[key], delta)
                engine_modifications.append((key, delta, f"ResourceEngine: {rd.get('source', 'engine')}"))

        # Award XP based on the turn's resolution outcome (P-21 progression)
        xp_award = _award_xp(resolution, game_context)
        if xp_award > 0:
            current_xp = int(working_state.xp or 0) if working_state else 0
            current_stats["xp"] = current_xp + xp_award
            current_stats["level"] = int(working_state.level or 1) if working_state else 1
            engine_modifications.append(("xp", xp_award, "P-21: XP award"))

        await anyio.to_thread.run_sync(
            lambda: mongodb_update_working_state(
                state_id,
                WorkingStateUpdate(
                    current_stats=current_stats or base_stats,
                    resources=merged_resources,
                ),
            )
        )

        source_text = (user_input or "scene turn")[:200]

        def _add_modification(key: str, delta: int, src: str = source_text) -> Any:
            return mongodb_add_modification(
                AddStatModification(
                    state_id=state_id,
                    stat_or_resource=key,
                    change=delta,
                    source=src,
                )
            )

        modification_tasks = [
            anyio.to_thread.run_sync(_add_modification, key, delta) for key, delta in deltas.items() if delta
        ] + [anyio.to_thread.run_sync(_add_modification, key, delta, src) for key, delta, src in engine_modifications]
        if modification_tasks:
            await asyncio.gather(*modification_tasks)

        checkpoint = {
            "turn_id": str(turn_id) if turn_id else None,
            "resolution_id": None,  # filled by caller
            "success_level": str(resolution.get("success_level") or "success"),
            "narrative_pressure": str(resolution.get("narrative_pressure") or "steady"),
            "xp_awarded": xp_award,
            "summary": PersistenceService.build_checkpoint_summary(
                narrative_text,
                str(resolution.get("success_level") or "success"),
                merged_resources,
                condition_tags,
            ),
            "resources": merged_resources,
            "conditions": condition_tags,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        new_pending_proposals: list[dict[str, Any]] = []
        add_tags = canonical_state_tags(condition_tags, deltas, merged_resources, game_context)
        if any(delta for delta in deltas.values()) or condition_tags or add_tags:
            turn_uuid = coerce_uuid(
                turn_id,
                seed=f"monitor://scene/{scene_id}/turn/{turn_id or uuid4()}",
            )
            proposal_content = {
                "entity_id": str(actor_uuid),
                "scene_id": str(scene_id),
                "story_id": str(story_id),
                "turn_id": str(turn_uuid),
                "add_tags": add_tags,
                "remove_tags": [],
                "resource_changes": {key: delta for key, delta in deltas.items() if delta},
                "resources": merged_resources,
                "condition_tags": condition_tags,
                "checkpoint_summary": checkpoint["summary"],
            }
            proposal_summary = PersistenceService.build_state_change_summary(deltas, condition_tags, add_tags)

            try:
                created_proposal = await anyio.to_thread.run_sync(
                    lambda: mongodb_create_proposed_change(
                        ProposedChangeCreate(
                            scene_id=scene_id,
                            story_id=story_id,
                            turn_id=turn_uuid,
                            change_type=ProposalType.STATE_CHANGE,
                            content=proposal_content,
                            evidence=[Evidence(type="turn", ref_id=turn_uuid)],
                            confidence=0.75,
                            authority=Authority.SYSTEM,
                            proposer="SceneLoop",
                        )
                    )
                )
                proposal_id = str(created_proposal.proposal_id)
                confidence = float(created_proposal.confidence)
            except Exception:
                proposal_id = str(uuid4())
                confidence = 0.75

            new_pending_proposals.append(
                {
                    "proposal_id": proposal_id,
                    "change_type": "state_change",
                    "summary": proposal_summary,
                    "content": proposal_content,
                    "payload": proposal_content,
                    "entity_names": [],
                    "confidence": confidence,
                    "authority": "system",
                    "proposer": "SceneLoop",
                }
            )

        return {
            "working_state_id": str(state_id),
            "working_state": {
                "state_id": str(state_id),
                "entity_id": str(actor_uuid),
                "scene_id": str(scene_id),
                "story_id": str(story_id),
                "current_stats": current_stats or base_stats,
                "resources": merged_resources,
                "conditions": condition_tags,
            },
            "scene_checkpoint": checkpoint,
            "pending_proposals": new_pending_proposals,
        }

    @staticmethod
    def clear_scene_runtime_cache(scene_id: UUID, *, include_entities: bool = False) -> None:
        """Invalidate Redis-backed hot-path keys that become stale after a turn."""
        try:
            from monitor_data.db.redis import get_redis_client

            cache = get_redis_client()
            cache.delete(
                f"solo_play:scene_turns:{scene_id}",
                f"solo_play:scene_summary:{scene_id}",
            )
            cache.delete_prefix(f"solo_play:assemble:{scene_id}")
            cache.delete_prefix(f"solo_play:turn_context:{scene_id}")
            if include_entities:
                cache.delete(f"solo_play:scene_entities:{scene_id}")
        except Exception:
            pass

"""
Scene Loop Support — pure helper functions extracted from scene_loop.py.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), stdlib
CALLED BY: scene_loop.py

These functions handle data transformation, resource management, state
derivation, and working-state persistence.  They are decoupled from the
LangGraph StateGraph wiring so they can be tested and reasoned about
independently of the graph topology.

Grouping:
  - UUID / type coercion
  - Action-type taxonomy mapping
  - Resource normalization & delta application
  - Actor state seeding
  - State delta derivation
  - Checkpoint / canon-summary builders
  - Redis cache invalidation
  - MongoDB working-state persistence
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import anyio


logger = logging.getLogger(__name__)


# =============================================================================
# UUID / TYPE COERCION
# =============================================================================


def coerce_uuid(value: UUID | str | None, *, seed: str) -> UUID:
    """Return a UUID value, deriving a deterministic fallback when needed."""
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid5(NAMESPACE_URL, seed)


def coerce_int(value: Any, default: int = 0) -> int:
    """Best-effort integer coercion for resource snapshots."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# =============================================================================
# ACTION-TYPE TAXONOMY
# =============================================================================


def map_action_type(raw_action_type: str, raw_intent_type: str, user_input: str) -> str:
    """Map live resolver intent/action labels into the DL-24 action taxonomy."""
    lowered = f"{raw_action_type} {raw_intent_type} {user_input}".lower()
    if any(word in lowered for word in ("attack", "fight", "shoot", "strike", "stab", "slash")):
        return "combat"
    if raw_intent_type in {"dialogue", "ooc"} or any(
        word in lowered for word in ("convince", "persuade", "threaten", "ask", "talk", "negotiate")
    ):
        return "social"
    if raw_intent_type == "query" or any(
        word in lowered
        for word in (
            "search",
            "inspect",
            "listen",
            "scan",
            "look",
            "notice",
            "investigate",
            "explore",
            "repair",
            "hotwire",
        )
    ):
        return "exploration"
    return "skill"


# =============================================================================
# RESOURCE NORMALIZATION & DELTA APPLICATION
# =============================================================================


def normalise_resource_value(name: str, value: Any, default: Any = 0) -> Dict[str, Any]:
    """Normalize a resource entry into a stable ``{current, max, label}`` shape."""
    default_int = coerce_int(default, 0)
    if isinstance(value, dict):
        snapshot = dict(value)
        current = snapshot.get(
            "current",
            snapshot.get("value", snapshot.get("amount", snapshot.get("max", default_int))),
        )
        snapshot["current"] = coerce_int(current, default_int)
        if snapshot.get("max") is not None:
            snapshot["max"] = coerce_int(snapshot.get("max"), snapshot["current"])
        elif default_int:
            snapshot["max"] = default_int
        snapshot.setdefault("label", name)
        return snapshot

    current = coerce_int(value, default_int)
    normalized: Dict[str, Any] = {"current": current, "label": name}
    normalized["max"] = default_int or current
    return normalized


def apply_resource_delta(resource: Dict[str, Any], delta: int) -> Dict[str, Any]:
    """Apply a bounded delta to a normalized resource snapshot."""
    updated = dict(resource)
    current = coerce_int(updated.get("current"), 0) + delta
    maximum = updated.get("max")
    if maximum is not None:
        max_int = coerce_int(maximum, current)
        current = max(0, min(max_int, current))
        updated["max"] = max_int
    else:
        current = max(0, current)
    updated["current"] = current
    return updated


# =============================================================================
# ACTOR STATE SEEDING
# =============================================================================


def select_actor_entity(
    entity_context: List[Dict[str, Any]],
    actor_id: UUID | None,
) -> Dict[str, Any]:
    """Pick the matching actor entity from the assembled scene context when possible."""
    actor_str = str(actor_id) if actor_id else None
    for entity in entity_context:
        if not isinstance(entity, dict):
            continue
        for key in ("entity_id", "id"):
            if actor_str and str(entity.get(key) or "") == actor_str:
                return entity
    return entity_context[0] if entity_context else {}


def seed_actor_state(
    entity_context: List[Dict[str, Any]],
    actor_id: UUID | None,
    game_context: Dict[str, Any],
    actor_context: Dict[str, Any] | None = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Build initial base stats and resource snapshots for the active actor.

    Stats are sourced from the actor entity in the scene context when present;
    when the bound PC is not in the scene's entity list (common — the actor is
    resolved from the session, not necessarily linked to the scene), we fall
    back to ``actor_context`` (the resolved CharacterContext, which carries the
    PC's attributes/resources). Without this fallback HP/stats never seed and
    the working-state HUD stays empty (T-092).
    """
    entity = select_actor_entity(entity_context, actor_id)
    props = entity.get("properties", {}) if isinstance(entity, dict) else {}
    base_stats: Dict[str, Any] = {}
    resources: Dict[str, Any] = {}

    # Did scene-context selection actually land on the bound actor?
    actor_str = str(actor_id) if actor_id else None
    matched_actor = bool(
        actor_str
        and isinstance(entity, dict)
        and str(entity.get("entity_id") or entity.get("id") or "") == actor_str
    )

    attr_source = props.get("attributes")
    res_source = props.get("resources")
    # Fall back to the resolved actor_context when the scene entity isn't the
    # actor or carries no stats of its own.
    if actor_context and (
        not matched_actor or not isinstance(attr_source, dict) or not attr_source
    ):
        if isinstance(actor_context.get("attributes"), dict) and actor_context["attributes"]:
            attr_source = actor_context["attributes"]
    if actor_context and (not matched_actor or not isinstance(res_source, dict) or not res_source):
        if isinstance(actor_context.get("resources"), dict) and actor_context["resources"]:
            res_source = actor_context["resources"]

    if isinstance(attr_source, dict):
        base_stats = {
            str(key): coerce_int(value)
            for key, value in attr_source.items()
            if isinstance(value, (int, float))
        }

    if isinstance(res_source, dict):
        resources = {
            str(key): normalise_resource_value(str(key), value, value)
            for key, value in res_source.items()
        }

    for resource_def in list(game_context.get("resources") or []):
        if not isinstance(resource_def, dict):
            continue
        label = str(resource_def.get("name") or resource_def.get("abbreviation") or "resource")
        abbr = str(resource_def.get("abbreviation") or "").strip()
        default_value = (
            resource_def.get("default_value")
            or resource_def.get("starting_value")
            or resource_def.get("max_value")
            or 0
        )
        existing_key = next(
            (
                key
                for key in resources
                if key.lower() in {label.lower(), abbr.lower()} or label.lower() in key.lower()
            ),
            None,
        )
        if existing_key:
            resources[existing_key] = normalise_resource_value(
                existing_key, resources[existing_key], default_value
            )
        else:
            seed_key = abbr or label
            resources[seed_key] = normalise_resource_value(label, default_value, default_value)

    # Seed tracks defined in the game system (e.g. Blood Pool, Humanity, Stress)
    for track_def in list(game_context.get("tracks") or []):
        t_name = str(track_def.get("name") or "")
        if not t_name:
            continue
        t_abbr = str(track_def.get("abbreviation") or t_name[:6])
        existing_key = next(
            (
                key
                for key in resources
                if key.lower() in {t_name.lower(), t_abbr.lower()} or t_name.lower() in key.lower()
            ),
            None,
        )
        if existing_key:
            continue  # Already populated from entity props
        t_min = track_def.get("min_value") or 0
        t_max = track_def.get("max_value") or t_min
        t_default = track_def.get("default_value")
        if t_default is not None:
            current = t_default if isinstance(t_default, int) else t_max
        elif track_def.get("track_type") in ("resource", "stress", "advancement"):
            current = t_max  # Resources start full
        else:
            current = t_min  # Degradation tracks start at min
        seed_key = t_abbr or t_name
        resources[seed_key] = normalise_resource_value(
            t_name, {"current": current, "max": t_max}, t_max
        )

    return base_stats, resources


# =============================================================================
# STATE DELTA DERIVATION
# =============================================================================
# Success-level to delta mappings (shared across extractors)
_STRESS_MAP = {
    "critical_success": -1,
    "success": 0,
    "partial_success": 1,
    "failure": 2,
    "critical_failure": 3,
}
_RESOURCE_LOSS_MAP = {
    "critical_success": 0,
    "success": 0,
    "partial_success": -1,
    "failure": -2,
    "critical_failure": -3,
}
_MOMENTUM_MAP = {
    "critical_success": 2,
    "success": 1,
    "partial_success": 0,
    "failure": -1,
    "critical_failure": -2,
}
_HARM_TOKENS = frozenset(
    (
        "wound",
        "injury",
        "hurt",
        "bleed",
        "strain",
        "vacuum",
        "breath",
        "oxygen",
        "setback",
        "cost",
        "damage",
        "hit",
    )
)


def _compute_stress_deltas(
    success_level: str,
    tracks: list[Dict[str, Any]],
    resources: Dict[str, Any],
) -> Dict[str, int]:
    """Derive stress/degradation deltas from game-system track definitions."""
    deltas: Dict[str, int] = {}
    for track_def in tracks:
        t_name = str(track_def.get("name") or "")
        if not t_name:
            continue
        t_abbr = str(track_def.get("abbreviation") or t_name[:6])
        res_key = next(
            (
                key
                for key in resources
                if key.lower() in {t_name.lower(), t_abbr.lower()} or t_name.lower() in key.lower()
            ),
            None,
        )
        if res_key is None:
            continue
        track_type = track_def.get("track_type", "resource")
        if track_type in ("stress", "degradation"):
            deltas[res_key] = _STRESS_MAP.get(success_level, 0)
    return deltas


def _compute_resource_deltas(
    success_level: str,
    has_harm: bool,
    resources: Dict[str, Any],
    game_context: Dict[str, Any],
) -> Dict[str, int]:
    """Derive resource deltas from game-system definitions."""
    deltas: Dict[str, int] = {}
    system_resources = list(game_context.get("resources") or [])
    if system_resources:
        for res_def in system_resources:
            r_name = str(res_def.get("name") or "")
            r_abbr = str(res_def.get("abbreviation") or "")
            res_key = next(
                (
                    key
                    for key in resources
                    if key.lower() in {r_name.lower(), r_abbr.lower()}
                    or r_name.lower() in key.lower()
                ),
                None,
            )
            if res_key and has_harm:
                deltas[res_key] = _RESOURCE_LOSS_MAP.get(success_level, 0)
    elif has_harm and "pressure" in resources:
        deltas["pressure"] = _STRESS_MAP.get(success_level, 0)
    return deltas


def _analyze_narrative_conditions(
    success_level: str,
    effects: list[str],
    combined_text: str,
    game_context: Dict[str, Any],
    deltas_so_far: Dict[str, int],
    resources: Dict[str, Any],
) -> List[str]:
    """Derive condition tags from success level, effects, and game-system triggers."""
    condition_tags: List[str] = []

    # Check game system condition triggers (e.g. Frenzy at Hunger >= 5)
    if game_context:
        try:
            from monitor_agents.game_system import GameSystemRuntime

            gsr = GameSystemRuntime(game_context)
            triggered = gsr.check_condition_triggers(
                event=f"success_level:{success_level}",
                context={
                    "track_values": {
                        name: snap.get("current", 0) + deltas_so_far.get(name, 0)
                        for name, snap in resources.items()
                        if isinstance(snap, dict)
                    },
                    "active_conditions": [],
                    "success_level": success_level,
                },
            )
            for cond in triggered:
                cond_name = cond.get("name", "")
                if cond_name:
                    condition_tags.append(cond_name.lower().replace(" ", "_"))
        except Exception:  # noqa: BLE001 — game system condition triggers are best-effort
            pass
    return condition_tags


def derive_state_deltas(
    resolution: Dict[str, Any],
    user_input: str | None,
    narrative_text: str | None,
    resources: Dict[str, Any] | None = None,
    game_context: Dict[str, Any] | None = None,
) -> tuple[Dict[str, int], List[str]]:
    """Infer resource drift and condition tags from a turn result.

    Derives deltas generically from the game system's track definitions:
    - stress/degradation tracks: increase on failure, decrease on success
    - resource tracks: decrease on failure with harm tokens in narrative
    - advancement tracks: no auto-delta (managed by advancement model)

    Falls back to generic pressure/momentum only when the game system
    defines no tracks at all (pure narrative mode).
    """
    success_level = str(resolution.get("success_level") or "success")
    effects = [str(effect) for effect in (resolution.get("effects") or [])]
    combined_text = " ".join(
        [
            user_input or "",
            narrative_text or "",
            str(resolution.get("risk_preview") or ""),
            " ".join(effects),
        ]
    ).lower()
    game_context = game_context or {}
    resources = resources or {}

    has_harm = any(token in combined_text for token in _HARM_TOKENS)

    # Collect deltas from each concern
    deltas: Dict[str, int] = {}
    deltas.update(
        _compute_stress_deltas(success_level, game_context.get("tracks") or [], resources)
    )
    deltas.update(_compute_resource_deltas(success_level, has_harm, resources, game_context))

    # Fallback to generic pressure/momentum if no system tracks defined
    if not game_context.get("tracks") and not game_context.get("resources"):
        if "pressure" in resources:
            deltas["pressure"] = _STRESS_MAP.get(success_level, 0)
        if "momentum" in resources:
            deltas["momentum"] = _MOMENTUM_MAP.get(success_level, 0)

    condition_tags = _analyze_narrative_conditions(
        success_level,
        effects,
        combined_text,
        game_context,
        deltas,
        resources,
    )

    deduped_tags = list(dict.fromkeys(condition_tags))
    return deltas, deduped_tags


# XP award mapping by success level (P-21 progression)
_XP_AWARD_MAP = {
    "critical_success": 50,
    "success": 30,
    "partial_success": 15,
    "failure": 10,
    "critical_failure": 5,
}


def _award_xp(
    resolution: Dict[str, Any],
    game_context: Dict[str, Any] | None,
) -> int:
    """Derive XP award from the turn's resolution outcome (P-21).

    Reads the advancement model from the game context. If the system defines
    ``xp_per_session``, uses that as a base. Otherwise falls back to the
    success-level-based ``_XP_AWARD_MAP``. Returns 0 if no advancement model
    is present (pure narrative mode).
    """
    game_context = game_context or {}
    advancement = game_context.get("advancement") or {}
    if not advancement:
        return 0

    success_level = str(resolution.get("success_level") or "success")
    xp_per_session = advancement.get("xp_per_session")

    if xp_per_session:
        # Use the system's per-session XP, scaled by success level
        scale = {
            "critical_success": 1.5,
            "success": 1.0,
            "partial_success": 0.5,
            "failure": 0.25,
            "critical_failure": 0.1,
        }
        return int(xp_per_session * scale.get(success_level, 1.0))

    return _XP_AWARD_MAP.get(success_level, 10)


# =============================================================================
# CHECKPOINT / CANON-SUMMARY BUILDERS
# =============================================================================


def build_checkpoint_summary(
    narrative_text: str | None,
    success_level: str,
    resources: Dict[str, Any],
    condition_tags: List[str],
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
    resource_bits: List[str] = []
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


def _tagify_effect(effect: str) -> str | None:
    """Turn a track threshold/depleted effect into a short state tag, or None.

    Only tag-like effects (a couple of words) become state tags; full-sentence
    effect descriptions are left for the narrator, not the Neo4j tag vocabulary.
    """
    cleaned = "_".join(str(effect).lower().split())
    if not cleaned or len(cleaned) > 30 or cleaned.count("_") > 2:
        return None
    return cleaned


def canonical_state_tags(
    condition_tags: List[str],
    deltas: Dict[str, int],
    resources: Dict[str, Any],
    game_context: Dict[str, Any] | None = None,
) -> List[str]:
    """Derive canonical Neo4j state-tags from the bound game system.

    Tags come from the system's track threshold/depleted effects (evaluated at
    the staged post-turn value) plus the already system-derived ``condition_tags``.
    No tag vocabulary or HP threshold is hardcoded — depletion semantics live in
    the game system's track data (see ``RULES_ENGINE.md``).
    """
    add_tags: List[str] = []

    if game_context:
        try:
            from monitor_agents.game_system import GameSystemRuntime

            gsr = GameSystemRuntime(game_context)
            for track in gsr.get_tracks():
                name = track.get("name")
                abbr = track.get("abbreviation")
                snap = resources.get(name) if name else None
                if snap is None and abbr:
                    snap = resources.get(abbr)
                if not isinstance(snap, dict):
                    continue
                staged = coerce_int(snap.get("current"), 0) + coerce_int(
                    deltas.get(name) if deltas.get(name) is not None else deltas.get(abbr),
                    0,
                )
                result = gsr.evaluate_track_threshold(
                    str(name), staged, coerce_int(snap.get("max"), None)
                )
                for effect in result.get("thresholds_triggered") or []:
                    tag = _tagify_effect(effect)
                    if tag:
                        add_tags.append(tag)
                depleted = result.get("depleted_effect")
                if depleted:
                    tag = _tagify_effect(depleted)
                    if tag:
                        add_tags.append(tag)
        except Exception:  # noqa: BLE001 — track-threshold derivation is best-effort
            pass

    # Condition tags are already system-derived; pass them through directly.
    for tag in condition_tags:
        cleaned = str(tag).lower().strip()
        if cleaned:
            add_tags.append(cleaned)

    return list(dict.fromkeys(add_tags))


def build_state_change_summary(
    deltas: Dict[str, int],
    condition_tags: List[str],
    add_tags: List[str],
) -> str:
    """Summarize the staged state drift for CanonKeeper review."""
    changes: List[str] = []
    for key, delta in deltas.items():
        if delta:
            sign = "+" if delta > 0 else ""
            changes.append(f"{key} {sign}{delta}")
    if condition_tags:
        changes.append("conditions: " + ", ".join(condition_tags))
    if add_tags:
        changes.append("canon tags: " + ", ".join(add_tags))
    return "Scene state changed — " + "; ".join(changes) if changes else "Scene state changed."


# =============================================================================
# REDIS CACHE INVALIDATION
# =============================================================================


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
    except Exception:  # noqa: BLE001
        pass


# =============================================================================
# MONGODB WORKING-STATE PERSISTENCE
# =============================================================================


async def persist_memories(
    *,
    entity_id: UUID,
    scene_id: UUID,
    story_id: UUID,
    universe_id: UUID,
    memories: List[Dict[str, Any]],
) -> List[UUID]:
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


async def persist_working_state(
    *,
    scene_id: UUID,
    story_id: UUID,
    actor_id: UUID | None,
    entity_context: List[Dict[str, Any]],
    game_context: Dict[str, Any],
    resolution: Dict[str, Any],
    user_input: str | None,
    narrative_text: str | None,
    turn_id: UUID | None,
    pending_proposals: List[Dict[str, Any]],
    resource_deltas: List[Dict[str, Any]] | None = None,
    memories_to_persist: List[Dict[str, Any]] | None = None,
    actor_context: Dict[str, Any] | None = None,
    universe_id: UUID | None = None,
) -> Dict[str, Any]:
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
        await persist_memories(
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

    existing = await anyio.to_thread.run_sync(
        lambda: mongodb_get_working_state(actor_uuid, scene_id)
    )
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
            str(key): normalise_resource_value(str(key), value)
            for key, value in seed_resources.items()
        }
        for key, value in (working_state.resources or {}).items():
            merged_resources.setdefault(str(key), normalise_resource_value(str(key), value))
        current_stats = dict(working_state.current_stats or base_stats or {})
        state_id = working_state.state_id

    deltas, condition_tags = derive_state_deltas(
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
    engine_modifications: List[Any] = []
    for rd in resource_deltas:
        key = str(rd.get("resource_key", ""))
        delta = int(rd.get("delta", 0))
        if not key or not delta:
            continue
        if key not in merged_resources:
            merged_resources[key] = normalise_resource_value(key, 0, 0)
        if delta:
            merged_resources[key] = apply_resource_delta(merged_resources[key], delta)
            engine_modifications.append(
                (key, delta, f"ResourceEngine: {rd.get('source', 'engine')}")
            )

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
        anyio.to_thread.run_sync(_add_modification, key, delta)
        for key, delta in deltas.items()
        if delta
    ] + [
        anyio.to_thread.run_sync(_add_modification, key, delta, src)
        for key, delta, src in engine_modifications
    ]
    if modification_tasks:
        await asyncio.gather(*modification_tasks)

    checkpoint = {
        "turn_id": str(turn_id) if turn_id else None,
        "resolution_id": None,  # filled by caller
        "success_level": str(resolution.get("success_level") or "success"),
        "narrative_pressure": str(resolution.get("narrative_pressure") or "steady"),
        "xp_awarded": xp_award,
        "summary": build_checkpoint_summary(
            narrative_text,
            str(resolution.get("success_level") or "success"),
            merged_resources,
            condition_tags,
        ),
        "resources": merged_resources,
        "conditions": condition_tags,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    new_pending_proposals: List[Dict[str, Any]] = []
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
        proposal_summary = build_state_change_summary(deltas, condition_tags, add_tags)

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

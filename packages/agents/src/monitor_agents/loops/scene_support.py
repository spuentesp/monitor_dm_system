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

import logging
import re
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5


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


def normalise_resource_value(name: str, value: Any, default: Any = 0) -> dict[str, Any]:
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
    normalized: dict[str, Any] = {"current": current, "label": name}
    normalized["max"] = default_int or current
    return normalized


def apply_resource_delta(resource: dict[str, Any], delta: int) -> dict[str, Any]:
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
    entity_context: list[dict[str, Any]],
    actor_id: UUID | None,
) -> dict[str, Any]:
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
    entity_context: list[dict[str, Any]],
    actor_id: UUID | None,
    game_context: dict[str, Any],
    actor_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
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
    base_stats: dict[str, Any] = {}
    resources: dict[str, Any] = {}

    # Did scene-context selection actually land on the bound actor?
    actor_str = str(actor_id) if actor_id else None
    matched_actor = bool(
        actor_str and isinstance(entity, dict) and str(entity.get("entity_id") or entity.get("id") or "") == actor_str
    )

    attr_source = props.get("attributes")
    res_source = props.get("resources")
    # Fall back to the resolved actor_context when the scene entity isn't the
    # actor or carries no stats of its own.
    if (
        actor_context
        and (not matched_actor or not isinstance(attr_source, dict) or not attr_source)
        and isinstance(actor_context.get("attributes"), dict)
        and actor_context["attributes"]
    ):
        attr_source = actor_context["attributes"]
    if actor_context and (not matched_actor or not isinstance(res_source, dict) or not res_source):
        if isinstance(actor_context.get("resources"), dict) and actor_context["resources"]:
            res_source = actor_context["resources"]

    if isinstance(attr_source, dict):
        base_stats = {
            str(key): coerce_int(value) for key, value in attr_source.items() if isinstance(value, (int, float))
        }

    if isinstance(res_source, dict):
        resources = {str(key): normalise_resource_value(str(key), value, value) for key, value in res_source.items()}

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
            (key for key in resources if key.lower() in {label.lower(), abbr.lower()} or label.lower() in key.lower()),
            None,
        )
        if existing_key:
            resources[existing_key] = normalise_resource_value(existing_key, resources[existing_key], default_value)
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
        resources[seed_key] = normalise_resource_value(t_name, {"current": current, "max": t_max}, t_max)

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
    tracks: list[dict[str, Any]],
    resources: dict[str, Any],
) -> dict[str, int]:
    """Derive stress/degradation deltas from game-system track definitions."""
    deltas: dict[str, int] = {}
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
    resources: dict[str, Any],
    game_context: dict[str, Any],
) -> dict[str, int]:
    """Derive resource deltas from game-system definitions."""
    deltas: dict[str, int] = {}
    system_resources = list(game_context.get("resources") or [])
    if system_resources:
        for res_def in system_resources:
            r_name = str(res_def.get("name") or "")
            r_abbr = str(res_def.get("abbreviation") or "")
            res_key = next(
                (
                    key
                    for key in resources
                    if key.lower() in {r_name.lower(), r_abbr.lower()} or r_name.lower() in key.lower()
                ),
                None,
            )
            if res_key and has_harm:
                deltas[res_key] = _RESOURCE_LOSS_MAP.get(success_level, 0)
    elif has_harm and "pressure" in resources:
        deltas["pressure"] = _STRESS_MAP.get(success_level, 0)
    return deltas


async def _analyze_narrative_conditions(
    success_level: str,
    effects: list[str],
    combined_text: str,
    game_context: dict[str, Any],
    deltas_so_far: dict[str, int],
    resources: dict[str, Any],
) -> list[str]:
    """Derive condition tags from success level, effects, and game-system triggers."""
    condition_tags: list[str] = []

    # Check game system condition triggers (e.g. Frenzy at Hunger >= 5)
    if game_context:
        try:
            from monitor_agents.game_system import GameSystemRuntime

            gsr = GameSystemRuntime(game_context)
            triggered = await gsr.check_condition_triggers(
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
        except Exception:
            pass
    return condition_tags


async def derive_state_deltas(
    resolution: dict[str, Any],
    user_input: str | None,
    narrative_text: str | None,
    resources: dict[str, Any] | None = None,
    game_context: dict[str, Any] | None = None,
) -> tuple[dict[str, int], list[str]]:
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
    deltas: dict[str, int] = {}
    deltas.update(_compute_stress_deltas(success_level, game_context.get("tracks") or [], resources))
    deltas.update(_compute_resource_deltas(success_level, has_harm, resources, game_context))

    # Fallback to generic pressure/momentum if no system tracks defined
    if not game_context.get("tracks") and not game_context.get("resources"):
        if "pressure" in resources:
            deltas["pressure"] = _STRESS_MAP.get(success_level, 0)
        if "momentum" in resources:
            deltas["momentum"] = _MOMENTUM_MAP.get(success_level, 0)

    condition_tags = await _analyze_narrative_conditions(
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
    resolution: dict[str, Any],
    game_context: dict[str, Any] | None,
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
    condition_tags: list[str],
    deltas: dict[str, int],
    resources: dict[str, Any],
    game_context: dict[str, Any] | None = None,
) -> list[str]:
    """Derive canonical Neo4j state-tags from the bound game system.

    Tags come from the system's track threshold/depleted effects (evaluated at
    the staged post-turn value) plus the already system-derived ``condition_tags``.
    No tag vocabulary or HP threshold is hardcoded — depletion semantics live in
    the game system's track data (see ``RULES_ENGINE.md``).
    """
    add_tags: list[str] = []

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
                    deltas.get(name) if deltas.get(name) is not None else deltas.get(abbr),  # type: ignore[arg-type]
                    0,
                )
                result = gsr.evaluate_track_threshold(
                    str(name),
                    staged,
                    coerce_int(snap.get("max"), None),  # type: ignore[arg-type]
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
        except Exception:
            pass

    # Condition tags are already system-derived; pass them through directly.
    for tag in condition_tags:
        cleaned = str(tag).lower().strip()
        if cleaned:
            add_tags.append(cleaned)

    return list(dict.fromkeys(add_tags))


# =============================================================================
# REDIS CACHE INVALIDATION
# =============================================================================


# =============================================================================
# MONGODB WORKING-STATE PERSISTENCE
# =============================================================================


# =============================================================================
# ENTITY PROMOTION — inline [Name](entity:anchor|flavor) tags + interaction
# tracking. See docs/2_architecture/data_model_workflow.md and
# NarratorSignature's docstring (packages/agents/src/monitor_agents/prompts/narrator.py)
# for the full convention this parses.
# =============================================================================

_ENTITY_TAG_RE = re.compile(r"\[(.+?)\]\(entity:(anchor|flavor)\)")
# Inverse pattern used by ``strip_entity_tags`` to remove the same tags from
# the displayed/persisted text. The name pattern is greedy on non-bracket
# characters so the boundary is unambiguous even when the name contains
# punctuation (e.g. "Kira 'Whisper' Voss"). The intent alternation mirrors
# the parser exactly — if the parser doesn't match, the stripper won't
# either, so the round-trip parse-then-strip is consistent.
_ENTITY_TAG_STRIP_RE = re.compile(r"\[([^\]]+)\]\(entity:(?:anchor|flavor)\)")


def parse_entity_tags(narrative_text: str) -> list[dict[str, str]]:
    """Parse [Name](entity:anchor|flavor) tags from GM narration.

    Pure, deterministic — no LLM call. This is the author-time promotion
    signal: the Narrator itself marks an entity's structural weight at
    generation time, rather than a second-pass classifier inferring it
    from prose alone. Returns one dict per tagged mention:
    ``{"name": str, "promotion_intent": "anchor" | "flavor"}``.
    """
    return [
        {"name": name.strip(), "promotion_intent": intent}
        for name, intent in _ENTITY_TAG_RE.findall(narrative_text or "")
        if name.strip()
    ]


def strip_entity_tags(text: str) -> str:
    """Strip [Name](entity:anchor|flavor) tags from GM narration.

    Inverse of :func:`parse_entity_tags`. Pure, deterministic — no LLM call.
    The parser must still run on the **raw** text first (so the tag metadata
    flows into entity promotion); this strips for display + persistence so
    the player never sees the raw ``[Name](entity:anchor)`` syntax as a
    broken markdown link.

    Strips anchor and flavor in one pass. The regex matches the same shape
    as ``_ENTITY_TAG_RE`` exactly — any variant the parser does not match
    (``[Name](entity:)``, ``[Name](entity:ANCHOR)``, missing intent keyword)
    is also left untouched here, so parser and stripper stay in lockstep.
    Empty/None input returns an empty string.
    """
    return _ENTITY_TAG_STRIP_RE.sub(r"\1", text or "")


def merge_entity_proposals(
    existing_proposals: list[dict[str, Any]],
    new_entity_proposals: list[dict[str, Any]],
    *,
    tags: list[dict[str, str]] | None = None,
    is_mechanically_bound: bool = False,
) -> list[dict[str, Any]]:
    """Merge freshly-detected ENTITY proposals into the scene's running list.

    Deduplicates by entity name (case-insensitive) so an entity mentioned
    across multiple turns accumulates ONE proposal with a growing
    ``interaction_count``, instead of a fresh throwaway proposal per turn.
    This is what feeds CanonKeeper's anchor/flavor promotion gate at scene
    end (see canonkeeper.py's ``evaluate_proposals``).

    Also applies inline ``[Name](entity:anchor|flavor)`` tags (first tag
    wins — an entity already tagged anchor doesn't get downgraded by a
    later untagged or flavor mention) and this turn's mechanical-binding
    signal (OR'd in — once bound, stays bound for the scene).

    Non-ENTITY proposals in ``existing_proposals`` pass through unchanged.
    Returns a new list; does not mutate the inputs.
    """
    tag_by_name = {t["name"].strip().lower(): t["promotion_intent"] for t in (tags or [])}

    result = [dict(p) for p in existing_proposals]
    index_by_name: dict[str, int] = {}
    for i, p in enumerate(result):
        if p.get("proposal_type") == "ENTITY":
            name = str((p.get("content") or {}).get("name", "")).strip().lower()
            if name:
                index_by_name[name] = i

    for new_p in new_entity_proposals:
        name = str((new_p.get("content") or {}).get("name", "")).strip().lower()
        if not name:
            result.append(new_p)
            continue
        if name in index_by_name:
            existing = result[index_by_name[name]]
            existing["interaction_count"] = existing.get("interaction_count", 1) + 1
            if is_mechanically_bound:
                existing["is_mechanically_bound"] = True
            if name in tag_by_name and not existing.get("promotion_intent"):
                existing["promotion_intent"] = tag_by_name[name]
        else:
            new_p = dict(new_p)
            new_p.setdefault("interaction_count", 1)
            if is_mechanically_bound:
                new_p["is_mechanically_bound"] = True
            if name in tag_by_name:
                new_p["promotion_intent"] = tag_by_name[name]
            result.append(new_p)
            index_by_name[name] = len(result) - 1

    return result


def turn_is_mechanically_bound(resolution: dict[str, Any] | None) -> bool:
    """True when this turn's resolution represents a resolved mechanical
    action (combat, contested check, dice roll) rather than a narrative
    beat or a pending/unresolved roll.

    Used as the same-turn co-occurrence signal for ``is_mechanically_bound``:
    an entity tagged/mentioned in a turn whose resolution cleared this gate
    is presumed to have participated in that mechanical action. Real
    entity-ID-level binding isn't possible pre-Neo4j-commit — proposals
    don't have a canonical ID yet at this stage — so this is a same-turn
    proxy, not a durable cross-reference.
    """
    if not resolution:
        return False
    resolution_type = str(resolution.get("resolution_type") or "").lower()
    action_type = str(resolution.get("action_type") or "").lower()
    subsystem_hint = str(resolution.get("subsystem_hint") or "").lower()
    return resolution_type in ("dice", "contested") or action_type == "combat" or subsystem_hint == "combat"

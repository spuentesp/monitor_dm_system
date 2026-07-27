"""
Scene-state tools — structured retrieval over the active scene.

These tools *do not* call the LLM. They answer "what's true right now?" by
reconstructing a ``GameSystemRuntime`` from a JSON game-context arg and
querying the schema/state. The GM uses them to ground narration in canon and
to recall the legal-action set without fabricating actions the world
doesn't support.

Tools:
* ``gm_tool_get_scene_state`` — full scene snapshot (entities, conditions,
  resources, schema summary).
* ``gm_tool_list_playable_actions`` — the "perfect recall of playable actions"
  surface. Returns the legal skill/attribute combinations filtered by
  current character state (e.g. attacks suppressed when ``restrained`` is
  active, or low-HP suppresses risky combat skills via an explicit
  ``disable_under_minimum`` rule).
* ``gm_tool_evaluate_scenery`` — schema-driven scenery-rule modifiers for
  the current location.

These tools are SYNCHRONOUS. The LLM (via dspy.ReAct) calls them with raw
JSON blobs; the tool rebuilds a ``GameSystemRuntime`` and queries the schema.
No DB round-trips during a tool call — the caller (resolver/GMAgent) is
expected to have already loaded the doc.
"""

from __future__ import annotations

import json
from typing import Any

import dspy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_gsr_from_json(game_context_json: str) -> Any:
    """Construct a GameSystemRuntime from a JSON game-context blob.

    Returns ``None`` if the input is empty or unparseable, signaling to the
    tool that the schema-aware legal-action set can't be computed (the
    tool returns a structured ``"status": "no_schema"`` payload).
    """
    if not game_context_json:
        return None
    try:
        doc = json.loads(game_context_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(doc, dict) or not doc:
        return None

    # Lazy import to avoid circularity with agent_factory.
    from monitor_agents.game_system import GameSystemRuntime

    try:
        return GameSystemRuntime(doc)
    except Exception:
        return None


def _active_conditions_from_json(conditions_json: str) -> set[str]:
    """Parse ``["poisoned","blessed"]`` style JSON into a normalized set."""
    if not conditions_json:
        return set()
    try:
        raw = json.loads(conditions_json)
    except (TypeError, ValueError):
        return set()
    if isinstance(raw, list):
        return {str(x).lower().strip() for x in raw if isinstance(x, str) and x.strip()}
    if isinstance(raw, str):
        return {raw.lower().strip()}
    return set()


# Actions whose name suggests you need to be "free to move" — suppressed by
# common restraining conditions. Worlds can override per-skill via the
# ``disable_under_conditions`` schema field on each skill; this is a
# world-agnostic *suggestion* fallback.
_RESTRICTING_CONDITIONS = {
    "restrained",
    "stunned",
    "paralyzed",
    "unconscious",
    "incapacitated",
    "sleeping",
    "knocked_down",
    "prone",
    "staggered",
}

# Conditions that suppress dialogue actions.
_DISTRACTING_CONDITIONS = {
    "frenzied",
    "frenzy",
    "in_ frenzy",
}


# ---------------------------------------------------------------------------
# get_scene_state
# ---------------------------------------------------------------------------


def gm_tool_get_scene_state() -> Any:
    """Return a ``dspy.Tool`` that hands the GM the scene snapshot."""

    def get_scene_state(
        scene_id: str = "",
        game_context_json: str = "",
        active_conditions_json: str = "[]",
        working_resources_json: str = "{}",
    ) -> str:
        """Return the active scene's current state as JSON.

        Args:
            scene_id: The scene identifier (for traceability).
            game_context_json: JSON-encoded game system doc (optional). When
                present, the tool rebuilds a GameSystemRuntime to surface
                schema-derived information (attribute list, skills, conditions).
            active_conditions_json: JSON list of conditions currently on the
                player character.
            working_resources_json: JSON dict of current resource values
                (Blood Pool, HP, Willpower, etc. — schema-defined).

        Returns:
            JSON with entities, conditions, resources, schema summary.
        """
        gsr = _build_gsr_from_json(game_context_json)
        schema_summary: dict[str, Any] = {}
        if gsr is not None:
            schema_summary = {
                "system_name": (gsr._sd.doc.get("name") if hasattr(gsr, "_sd") else None),
                "attributes": [
                    {
                        "name": a.get("name"),
                        "abbreviation": a.get("abbreviation"),
                        "min_value": a.get("min_value"),
                        "max_value": a.get("max_value"),
                    }
                    for a in (gsr._sd.attrs if hasattr(gsr, "_sd") else [])
                ],
                "skills": [
                    {
                        "name": s.get("name"),
                        "linked_attribute": s.get("linked_attribute"),
                        "description": s.get("description", ""),
                    }
                    for s in (gsr._sd.skills if hasattr(gsr, "_sd") else [])
                ],
                "conditions": [
                    {"name": c.get("name"), "tags": c.get("tags", [])}
                    for c in (gsr._sd.conditions if hasattr(gsr, "_sd") else [])
                ],
                "tracks": [
                    {
                        "name": t.get("name"),
                        "min_value": t.get("min_value"),
                        "max_value": t.get("max_value"),
                    }
                    for t in (gsr._sd.tracks if hasattr(gsr, "_sd") else [])
                ],
            }
        try:
            working_resources = json.loads(working_resources_json) if working_resources_json else {}
        except (TypeError, ValueError):
            working_resources = {}
        try:
            active_conditions = json.loads(active_conditions_json) if active_conditions_json else []
        except (TypeError, ValueError):
            active_conditions = []

        payload: dict[str, Any] = {
            "scene_id": scene_id,
            "status": "ok" if gsr is not None else "no_schema",
            "active_conditions": active_conditions,
            "working_resources": working_resources,
            "schema_summary": schema_summary,
        }
        return json.dumps(payload)

    return dspy.Tool(
        get_scene_state,
        name="get_scene_state",
        desc=(
            "Return the current scene's state as JSON: entities in the scene, "
            "active conditions on the player, current resource values (HP / "
            "Blood Pool / etc.), and a schema summary (attributes, skills, "
            "tracks, conditions) for the active game system. ALWAYS call this "
            "BEFORE narrating to ground in canon and avoid inventing things "
            "that aren't there."
        ),
        args={
            "scene_id": {"type": "string", "description": "The active scene's UUID."},
            "game_context_json": {
                "type": "string",
                "description": "JSON-encoded game system doc (loaded by the resolver/GMAgent). Optional.",
                "default": "",
            },
            "active_conditions_json": {
                "type": "string",
                "description": "JSON list of conditions currently on the player character.",
                "default": "[]",
            },
            "working_resources_json": {
                "type": "string",
                "description": "JSON dict of current resource values.",
                "default": "{}",
            },
        },
    )


# ---------------------------------------------------------------------------
# list_playable_actions — the "perfect recall" tool
# ---------------------------------------------------------------------------


def _skill_playable(
    skill: dict[str, Any],
    active_conditions: set[str],
) -> tuple[bool, str | None]:
    """Return ``(playable, reason_if_not)`` for a single skill entry."""
    name = (skill.get("name") or "").lower()

    # 1. Schema-suppressed by specific conditions.
    disable = skill.get("disable_under_conditions") or []
    if isinstance(disable, list):
        for c in disable:
            if isinstance(c, str) and c.lower().strip() in active_conditions:
                return False, f"disabled by condition '{c}'"

    # 2. Schema-suppressed by minimum resource level.
    min_resource = skill.get("disable_under_minimum_resource")
    if isinstance(min_resource, dict):
        resource_name = min_resource.get("name")
        threshold = min_resource.get("min")
        # We can't compute character current resource here — the LLM has it
        # via working_resources. Mark as "review_manually" when a threshold
        # is declared; the GM confirms based on the live numbers.
        if resource_name and threshold is not None:
            return True, f"requires {resource_name} >= {threshold}"

    # 3. World-agnostic fallback: physically-restricting conditions suppress
    # combat/movement actions; dialogue-impairing conditions suppress
    # dialogue. These are *suggestions* — the schema can override.
    # The set of trigger words is lowercased for matching; the conditions
    # themselves are already lowercased, so we keep the reason text
    # canonicalized to the original casing via .title() for display.
    if active_conditions & _RESTRICTING_CONDITIONS:
        # Combat/physical movement suppressed; the GM can override narratively.
        if any(token in name for token in ("attack", "brawl", "shoot", "fire", "dodge", "parry", "athletic", "climb")):
            names = ", ".join(sorted(c.title() for c in (active_conditions & _RESTRICTING_CONDITIONS)))
            return False, f"character is in a restricting state ({names})"
    if active_conditions & _DISTRACTING_CONDITIONS:
        if any(
            token in name
            for token in (
                "persuade",
                "negotiate",
                "bargain",
                "sway",
                "intimidate",
                "charm",
                "perform",
            )
        ):
            names = ", ".join(sorted(c.title() for c in (active_conditions & _DISTRACTING_CONDITIONS)))
            return False, f"character is in a frenzy-like state ({names})"

    return True, None


def _skill_action_type(name: str, attrs: list[str]) -> str:
    """Heuristic mapping of skill name → action_type for the resolver.

    This is the *visual* action_type used to populate the chip UI; the
    resolver's own semantic classifier (or the GM's LLM read) overrides it
    when the player's action doesn't match.
    """
    n = (name or "").lower()
    if any(token in n for token in ("attack", "brawl", "shoot", "fire", "stab")):
        return "combat"
    if any(token in n for token in ("sneak", "stealth", "lockpick", "pick")):
        return "stealth"
    if any(token in n for token in ("intimidate", "persuade", "charm", "sway", "negotiate")):
        return "dialogue"
    if any(token in n for token in ("search", "examine", "investigate", "awareness", "perception")):
        return "exploration"
    if any(token in n for token in ("athletics", "climb", "drive", "ride")):
        return "movement"
    return "action"


def gm_tool_list_playable_actions() -> Any:
    """Return a ``dspy.Tool`` for the playable-actions recall."""

    def list_playable_actions(
        scene_id: str = "",
        system_id: str = "",
        game_context_json: str = "",
        active_conditions_json: str = "[]",
    ) -> str:
        """Return the legal set of actions the player can attempt right now.

        Filters the schema's skill list by active conditions (e.g. suppresses
        attacks when ``restrained`` is active, suppresses dialogue when
        ``frenzied``). Each entry includes the governing attribute and a
        recommended difficulty range derived from the schema.

        Args:
            scene_id: Scene UUID (for traceability).
            system_id: Game system ID (string).
            game_context_json: JSON-encoded game system doc.
            active_conditions_json: JSON list of conditions currently active.

        Returns:
            JSON with ``playable_actions`` (list of skill entries with
            ``playable`` flags) and ``unavailable_actions`` (excluded with
            reasons), plus a schema-anchored ``attrs`` block.
        """
        gsr = _build_gsr_from_json(game_context_json)
        if gsr is None:
            return json.dumps(
                {
                    "scene_id": scene_id,
                    "system_id": system_id,
                    "status": "no_schema",
                    "playable_actions": [],
                    "unavailable_actions": [],
                    "note": "Game system schema not provided; cannot enumerate legal actions.",
                }
            )

        active_conditions = _active_conditions_from_json(active_conditions_json)
        skills = list(gsr._sd.skills or [])
        attrs = list(gsr._sd.attrs or [])

        # Build attribute lookup.
        attr_lookup: dict[str, dict[str, Any]] = {
            a.get("abbreviation", "").upper(): a for a in attrs if a.get("abbreviation")
        }

        playable: list[dict[str, Any]] = []
        unavailable: list[dict[str, Any]] = []
        for skill in skills:
            name = skill.get("name")
            if not name:
                continue
            ok, reason = _skill_playable(skill, active_conditions)
            entry = {
                "name": name,
                "abbreviation": skill.get("abbreviation"),
                "linked_attribute": skill.get("linked_attribute"),
                "description": skill.get("description", ""),
                "action_type": _skill_action_type(name, [a.get("abbreviation", "") for a in attrs]),
            }
            if ok:
                playable.append(entry)
            else:
                entry["reason"] = reason
                unavailable.append(entry)

        # Always include "raw" rolls (unskilled actions) as a fallback when
        # the character's attribute exists.
        for abbr, attr_def in attr_lookup.items():
            entry = {
                "name": f"raw {attr_def.get('name', abbr)} attempt",
                "abbreviation": f"RAW_{abbr}",
                "linked_attribute": abbr,
                "description": "Attribute-only attempt (no specific skill).",
                "action_type": "action",
                "always_playable": True,
            }
            playable.append(entry)

        return json.dumps(
            {
                "scene_id": scene_id,
                "system_id": system_id,
                "status": "ok",
                "active_conditions": sorted(active_conditions),
                "playable_actions": playable,
                "unavailable_actions": unavailable,
            }
        )

    return dspy.Tool(
        list_playable_actions,
        name="list_playable_actions",
        desc=(
            "Return the legal set of actions the player can attempt in the "
            "current scene — what skills and attributes are usable given the "
            "player's current conditions and the game's rules. Use this WHEN "
            "the GM is uncertain whether a player's stated action is "
            "playable, or when the GM wants to recall what success looks like. "
            "Returns ``playable_actions`` (legal now) and ``unavailable_actions`` "
            "(disabled, with reason) lists. The schema may declare additional "
            "suppression rules via disable_under_conditions / "
            "disable_under_minimum_resource on each skill."
        ),
        args={
            "scene_id": {"type": "string", "description": "The active scene's UUID."},
            "system_id": {
                "type": "string",
                "description": "Optional game system ID for traceability.",
                "default": "",
            },
            "game_context_json": {
                "type": "string",
                "description": "JSON-encoded game system doc (loaded by the resolver/GMAgent).",
                "default": "",
            },
            "active_conditions_json": {
                "type": "string",
                "description": "JSON list of conditions currently on the player character.",
                "default": "[]",
            },
        },
    )


# ---------------------------------------------------------------------------
# evaluate_scenery
# ---------------------------------------------------------------------------


def gm_tool_evaluate_scenery() -> Any:
    """Return a ``dspy.Tool`` for schema-driven scenery modifiers."""

    def evaluate_scenery(
        scene_id: str = "",
        game_context_json: str = "",
        location_tags_json: str = "[]",
        location_description: str = "",
    ) -> str:
        """Return scenery rule modifiers (advantage/disadvantage/numeric) for the active location.

        Args:
            scene_id: Scene UUID.
            game_context_json: JSON-encoded game system doc.
            location_tags_json: JSON list of location tags.
            location_description: Lowercased description string (used as a
                fallback for keyword match).

        Returns:
            JSON with ``modifiers`` — list of ``{keyword, modifier, "
            "roll_mode, reason_text, source}`` entries that fire for the
            current location.
        """
        gsr = _build_gsr_from_json(game_context_json)
        if gsr is None:
            return json.dumps(
                {
                    "scene_id": scene_id,
                    "status": "no_schema",
                    "modifiers": [],
                }
            )

        try:
            tags = {t.lower().strip() for t in (json.loads(location_tags_json) or []) if isinstance(t, str)}
        except (TypeError, ValueError):
            tags = set()
        desc_lower = (location_description or "").lower()

        modifiers: list[dict[str, Any]] = []
        for rule in gsr._sd.scenery_rules or []:
            keyword = (rule.get("keyword") or "").lower()
            if not keyword:
                continue
            if keyword not in tags and keyword not in desc_lower:
                continue
            modifiers.append(
                {
                    "keyword": keyword,
                    "modifier": rule.get("roll_modifier"),
                    "roll_mode_override": rule.get("roll_mode_override"),
                    "trigger_verbs": rule.get("trigger_verbs", []),
                    "reason_text": rule.get("reason_text"),
                    "source": "scenery_rule",
                }
            )
        return json.dumps(
            {
                "scene_id": scene_id,
                "status": "ok",
                "location_tags": sorted(tags),
                "modifiers": modifiers,
            }
        )

    return dspy.Tool(
        evaluate_scenery,
        name="evaluate_scenery",
        desc=(
            "Return scenery rule modifiers that apply at the current location — "
            "advantage/disadvantage flags and numeric roll modifiers, plus the "
            "rule's reason text. The trigger_verbs list is informational only; "
            "the semantic action router (via the resolver) decides whether the "
            "player's action fires the rule. Use this when the GM is about to "
            "commit a roll outcome and wants to know if the scenery shifts it."
        ),
        args={
            "scene_id": {"type": "string", "description": "The active scene's UUID."},
            "game_context_json": {
                "type": "string",
                "description": "JSON-encoded game system doc (loaded by the resolver/GMAgent).",
                "default": "",
            },
            "location_tags_json": {
                "type": "string",
                "description": "JSON list of location tags (the resolver extracts these from the location entity).",
                "default": "[]",
            },
            "location_description": {
                "type": "string",
                "description": "Lower-cased description of the active location (fallback for keyword match).",
                "default": "",
            },
        },
    )

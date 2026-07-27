"""
Tests for the scene-state tools (T2).

Covers:
- ``gm_tool_get_scene_state`` returns schema summary + active conditions.
- ``gm_tool_list_playable_actions`` filters by active conditions, exposes
  the per-skill ``disable_under_conditions`` / ``disable_under_minimum_resource``
  schema fields, and falls back to world-agnostic restricting-condition
  suppression (``restrained`` blocks combat).
- ``gm_tool_evaluate_scenery`` surfaces schema-driven scenery-rule modifiers.
- All three tools degrade gracefully when the schema doc isn't available.

The tools are SYNC; we drive them directly, no loop-bridge needed.
"""

from __future__ import annotations

import json
from typing import Any

from monitor_agents.gm_tools.registry import GM_TOOLS, get_tool

# ---------------------------------------------------------------------------
# Schema fixture — the demo-game VtM-ish profile
# ---------------------------------------------------------------------------


_VTM_LIKE = {
    "name": "VtM-test-fixture",
    "attributes": [
        {
            "name": "Strength",
            "abbreviation": "STR",
            "min_value": 1,
            "max_value": 5,
            "default_value": 2,
        },
        {
            "name": "Dexterity",
            "abbreviation": "DEX",
            "min_value": 1,
            "max_value": 5,
            "default_value": 2,
        },
        {
            "name": "Charisma",
            "abbreviation": "CHA",
            "min_value": 1,
            "max_value": 5,
            "default_value": 2,
        },
        {"name": "Wits", "abbreviation": "WIT", "min_value": 1, "max_value": 5, "default_value": 2},
    ],
    "skills": [
        {
            "name": "Brawl",
            "abbreviation": "BRW",
            "linked_attribute": "Strength",
            "description": "Punch, kick, grapple — unarmed combat.",
        },
        {
            "name": "Intimidation",
            "abbreviation": "INT2",
            "linked_attribute": "Charisma",
            "description": "Threaten, menace.",
        },
        {
            "name": "Awareness",
            "abbreviation": "AWA",
            "linked_attribute": "Wits",
            "description": "Notice things.",
        },
        {
            "name": "Investigation",
            "abbreviation": "INV",
            "linked_attribute": "Wits",
            "description": "Search, deduce.",
            # Schema-suppressed by Blood Pool minimum.
            "disable_under_minimum_resource": {"name": "Blood Pool", "min": 1},
            # Schema-suppressed by frenzied condition.
            "disable_under_conditions": ["Frenzy"],
        },
    ],
    "conditions": [
        {"name": "Restrained", "tags": ["physical"]},
        {"name": "Frenzy", "tags": ["mental"]},
        {"name": "Blood Bond", "tags": ["social"]},
    ],
    "tracks": [
        {
            "name": "Blood Pool",
            "min_value": 0,
            "max_value": 10,
            "min_threshold": 1,
            "max_threshold": 10,
        },
        {"name": "Health", "min_value": 0, "max_value": 7},
        {"name": "Willpower", "min_value": 0, "max_value": 5},
    ],
    "scenery_rules": [
        {
            "keyword": "tangled",
            "trigger_verbs": ["dodge", "flee"],
            "roll_modifier": -2,
            "roll_mode_override": "disadvantage",
            "reason_text": "Vines everywhere.",
        },
        {
            "keyword": "high ground",
            "trigger_verbs": ["shoot", "attack"],
            "roll_modifier": 2,
            "roll_mode_override": "advantage",
            "reason_text": "You have the high ground.",
        },
    ],
}


def _tool(name: str) -> Any:
    return get_tool(name)


def _ctx() -> str:
    return json.dumps(_VTM_LIKE)


# ---------------------------------------------------------------------------
# get_scene_state
# ---------------------------------------------------------------------------


def test_get_scene_state_returns_schema_summary() -> None:
    payload = json.loads(_tool("get_scene_state").func("scene-1", _ctx(), "[]", "{}"))
    assert payload["status"] == "ok"
    assert payload["scene_id"] == "scene-1"
    summary = payload["schema_summary"]
    assert summary["system_name"] == "VtM-test-fixture"
    abbrs = {a["abbreviation"] for a in summary["attributes"]}
    assert {"STR", "DEX", "CHA", "WIT"} <= abbrs
    skill_names = {s["name"] for s in summary["skills"]}
    assert "Brawl" in skill_names


def test_get_scene_state_without_schema() -> None:
    payload = json.loads(_tool("get_scene_state").func("scene-1", "", "[]", "{}"))
    assert payload["status"] == "no_schema"
    assert payload["active_conditions"] == []


def test_get_scene_state_includes_active_conditions_and_resources() -> None:
    payload = json.loads(
        _tool("get_scene_state").func(
            "scene-1", _ctx(), '["Restrained"]', '{"Blood Pool": 5, "Health": 5, "Willpower": 3}'
        )
    )
    assert payload["active_conditions"] == ["Restrained"]
    assert payload["working_resources"]["Blood Pool"] == 5


# ---------------------------------------------------------------------------
# list_playable_actions — perfect recall
# ---------------------------------------------------------------------------


def test_list_playable_actions_lists_schema_skills() -> None:
    payload = json.loads(_tool("list_playable_actions").func("scene-1", "sys-1", _ctx(), "[]"))
    assert payload["status"] == "ok"
    names = {a["name"] for a in payload["playable_actions"]}
    assert "Brawl" in names
    assert "Intimidation" in names
    assert "Awareness" in names
    assert "Investigation" in names


def test_list_playable_actions_includes_attribute_raw_actions() -> None:
    payload = json.loads(_tool("list_playable_actions").func("scene-1", "sys-1", _ctx(), "[]"))
    raw = [a for a in payload["playable_actions"] if a["name"].startswith("raw ")]
    # One per attribute in the schema.
    assert len(raw) == 4


def test_list_playable_actions_filters_by_schema_disabling() -> None:
    payload = json.loads(_tool("list_playable_actions").func("scene-1", "sys-1", _ctx(), '["Frenzy"]'))
    # Investigation disables under "Frenzy" — should be unavailable.
    unavailable = {a["name"]: a.get("reason") for a in payload["unavailable_actions"]}
    assert "Investigation" in unavailable
    assert unavailable["Investigation"] and "Frenzy" in unavailable["Investigation"]


def test_list_playable_actions_world_agnostic_restrained_blocks_combat() -> None:
    payload = json.loads(_tool("list_playable_actions").func("scene-1", "sys-1", _ctx(), '["Restrained"]'))
    # Brawl (combat-ish) should be flagged unavailable due to Restrained.
    unavailable = {a["name"]: a.get("reason", "") for a in payload["unavailable_actions"]}
    assert "Brawl" in unavailable
    assert "Restrained" in unavailable["Brawl"]
    # But Awareness (exploration) stays playable.
    playable = {a["name"] for a in payload["playable_actions"]}
    assert "Awareness" in playable


def test_list_playable_actions_no_schema_returns_empty() -> None:
    payload = json.loads(_tool("list_playable_actions").func("scene-1", "sys-1", "", "[]"))
    assert payload["status"] == "no_schema"
    assert payload["playable_actions"] == []


def test_list_playable_actions_with_active_conditions_only_filters_correct_skills() -> None:
    """Conditions that don't disable anything should leave the skill list intact."""
    payload = json.loads(_tool("list_playable_actions").func("scene-1", "sys-1", _ctx(), '["Blood Bond"]'))
    # Blood Bond doesn't restrict any of our skills; everything playable.
    unavailable = {a["name"] for a in payload["unavailable_actions"]}
    assert unavailable == set()


# ---------------------------------------------------------------------------
# evaluate_scenery
# ---------------------------------------------------------------------------


def test_evaluate_scenery_matches_location_tag() -> None:
    payload = json.loads(_tool("evaluate_scenery").func("scene-1", _ctx(), '["tangled"]', ""))
    assert payload["status"] == "ok"
    keys = {m["keyword"] for m in payload["modifiers"]}
    assert "tangled" in keys
    tangled_mod = next(m for m in payload["modifiers"] if m["keyword"] == "tangled")
    assert tangled_mod["modifier"] == -2
    assert tangled_mod["roll_mode_override"] == "disadvantage"


def test_evaluate_scenery_matches_via_description_fallback() -> None:
    payload = json.loads(
        _tool("evaluate_scenery").func(
            "scene-1", _ctx(), "[]", "you stand on the high ground overlooking the courtyard"
        )
    )
    keys = {m["keyword"] for m in payload["modifiers"]}
    assert "high ground" in keys


def test_evaluate_scenery_returns_empty_when_no_match() -> None:
    payload = json.loads(_tool("evaluate_scenery").func("scene-1", _ctx(), '["unrelated"]', "calm road"))
    assert payload["modifiers"] == []


def test_evaluate_scenery_no_schema() -> None:
    payload = json.loads(_tool("evaluate_scenery").func("scene-1", "", "[]", ""))
    assert payload["status"] == "no_schema"
    assert payload["modifiers"] == []


# ---------------------------------------------------------------------------
# Regression — tools still in registry after replacements
# ---------------------------------------------------------------------------


def test_all_three_scene_tools_in_registry() -> None:
    expected = {"get_scene_state", "list_playable_actions", "evaluate_scenery"}
    have = {getattr(t, "name", None) for t in GM_TOOLS()}
    assert expected <= have

"""Tests for GameSystemRuntime character/NPC generation helpers."""

from __future__ import annotations

import asyncio

from monitor_agents.game_system import GameSystemRuntime


def _sample_system_doc() -> dict:
    return {
        "name": "Test Void System",
        "core_mechanic": {
            "type": "dice_pool",
            "formula": "2d6 + stat",
            "success_type": "meet_or_beat",
        },
        "attributes": [
            {
                "name": "Body",
                "abbreviation": "BDY",
                "min_value": 1,
                "max_value": 20,
                "default_value": 10,
            },
            {
                "name": "Dexterity",
                "abbreviation": "DEX",
                "min_value": 1,
                "max_value": 20,
                "default_value": 10,
            },
        ],
        "skills": [],
        "resources": [
            {"name": "Hit Points", "abbreviation": "HP", "calculation": "10"},
        ],
        "npc_stat_blocks": [
            {
                "name": "Dock Guard",
                "tier": "standard",
                "attributes": {"BDY": 11, "DEX": 10},
                "hp": 12,
                "defense": "11",
                "special_abilities": ["Hold the line"],
                "tags": ["guard", "npc"],
            }
        ],
        "npc_creation_rules": {
            "types_available": ["standard", "elite"],
            "simplified_stat_method": "Use the published example stat block closest to the role.",
        },
    }


def test_generate_npc_prefers_embedded_stat_blocks() -> None:
    runtime = GameSystemRuntime(_sample_system_doc())

    npc = runtime.generate_npc(name="Mira Gatekeeper", tier="standard")

    assert npc["name"] == "Mira Gatekeeper"
    assert npc["kind"] == "npc"
    assert npc["attributes"]["BDY"] == 11
    assert npc["resources"]["HP"] == 12
    assert "guard" in npc["tags"]


def test_build_character_candidate_returns_playable_preview() -> None:
    runtime = GameSystemRuntime(_sample_system_doc())

    candidate = runtime.build_character_candidate(name="Tarin Vale", description="scavenger pilot")

    assert candidate["name"] == "Tarin Vale"
    assert candidate["kind"] == "pc"
    assert candidate.get("attributes")
    assert "sheet" in candidate and "starting attributes" in candidate["sheet"].lower()


def test_generate_npc_with_concept() -> None:
    """Test generating NPC with concept."""
    runtime = GameSystemRuntime(_sample_system_doc())

    npc = runtime.generate_npc(name="Guard Captain", tier="standard", concept="veteran guard")

    assert npc["name"] == "Guard Captain"
    assert npc["kind"] == "npc"


def test_primary_attributes_returns_list() -> None:
    """Test that primary_attributes returns a list."""
    runtime = GameSystemRuntime(_sample_system_doc())

    attrs = runtime.primary_attributes

    assert isinstance(attrs, list)
    assert len(attrs) == 2  # Body and Dexterity


def test_ability_method_description_returns_string() -> None:
    """Test that ability_method_description returns a string."""
    runtime = GameSystemRuntime(_sample_system_doc())

    desc = runtime.ability_method_description()

    assert isinstance(desc, str)


def test_get_tracks_returns_list() -> None:
    """Test that get_tracks returns a list."""
    runtime = GameSystemRuntime(_sample_system_doc())

    tracks = runtime.get_tracks()

    assert isinstance(tracks, list)


def test_get_conditions_returns_list() -> None:
    """Test that get_conditions returns a list."""
    runtime = GameSystemRuntime(_sample_system_doc())

    conditions = runtime.get_conditions()

    assert isinstance(conditions, list)


def test_get_damage_types_returns_list() -> None:
    """Test that get_damage_types returns a list."""
    runtime = GameSystemRuntime(_sample_system_doc())

    damage_types = runtime.get_damage_types()

    assert isinstance(damage_types, list)


def test_get_action_types_returns_list() -> None:
    """Test that get_action_types returns a list."""
    runtime = GameSystemRuntime(_sample_system_doc())

    action_types = runtime.get_action_types()

    assert isinstance(action_types, list)


def test_get_resolution_mechanics_returns_list() -> None:
    """Test that get_resolution_mechanics returns a list."""
    runtime = GameSystemRuntime(_sample_system_doc())

    mechanics = runtime.get_resolution_mechanics()

    assert isinstance(mechanics, list)


def test_infer_action_context_returns_dict() -> None:
    """Test that infer_action_context returns a dict (semantic router)."""
    from unittest.mock import patch

    runtime = GameSystemRuntime(_sample_system_doc())

    fake = {
        "action_type": "action",
        "stat_name": "STR",
        "difficulty_class": 12,
        "subsystem_hint": "combat",
    }

    async def _fake_infer(sd, user_input, source_profile=None):
        return fake

    with patch(
        "monitor_agents.game_system._action_routing.infer_action_context",
        side_effect=_fake_infer,
    ):
        context = asyncio.run(runtime.infer_action_context("I swing at the goblin"))

    assert isinstance(context, dict)
    assert context["action_type"] == "action"
    assert context["stat_name"] == "STR"
    assert context["subsystem_hint"] == "combat"

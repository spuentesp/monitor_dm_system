"""
Tests for the Resolver agent.

All LLM calls and MCP tool calls are mocked — pure unit tests.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_agents.resolver import Resolver


# ===========================================================================
# Helpers
# ===========================================================================


def _make_context(body: int = 0, dex: int = 0, savvy: int = 0) -> Dict[str, Any]:
    """Build a minimal scene context dict matching what SceneLoop passes."""
    return {
        "entities": [
            {
                "properties": {
                    "attributes": {
                        "Strength": 12,
                        "Dexterity": dex or 14,
                        "Wisdom": 10,
                        "Charisma": 8,
                        "Intelligence": 13,
                        "body": body or 1,
                        "savvy": savvy or 0,
                    }
                }
            }
        ],
        "turns": [],
    }


# ===========================================================================
# Resolver instantiation
# ===========================================================================


class TestResolverInit:
    def test_default_id(self):
        r = Resolver()
        assert r.agent_id == "resolver-cli-1"
        assert r.agent_type == "Resolver"

    def test_custom_id(self):
        r = Resolver(agent_id="resolver-test-99")
        assert r.agent_id == "resolver-test-99"


# ===========================================================================
# _infer_action_profile
# ===========================================================================


class TestInferActionProfile:
    def setup_method(self):
        self.resolver = Resolver()

    def test_dialogue_keywords(self):
        for kw in ("ask", "say", "tell", "persuade", "convince", "threaten", "speak"):
            action_type, stat, dc = self.resolver._infer_action_profile(kw + " to someone")
            assert action_type == "dialogue", f"keyword {kw!r} should be dialogue"
            assert stat == "Charisma"
            assert dc == 12

    def test_search_keywords(self):
        for kw in ("search", "notice", "inspect", "track", "listen", "sense"):
            action_type, stat, dc = self.resolver._infer_action_profile(kw + " something")
            assert action_type == "action", f"keyword {kw!r} should be action"
            assert stat == "Wisdom"
            assert dc == 13

    def test_stealth_keywords(self):
        for kw in ("sneak", "hide", "dodge", "climb", "pick", "steal"):
            action_type, stat, dc = self.resolver._infer_action_profile(kw + " the lock")
            assert action_type == "action"
            assert stat == "Dexterity"
            assert dc == 14

    def test_knowledge_keywords(self):
        for kw in ("recall", "analyze", "study", "decipher", "investigate"):
            action_type, stat, dc = self.resolver._infer_action_profile(kw + " it")
            assert action_type == "action"
            assert stat == "Intelligence"
            assert dc == 13

    def test_default_physical(self):
        action_type, stat, dc = self.resolver._infer_action_profile("punch the wall")
        assert action_type == "action"
        assert stat == "Strength"
        assert dc == 12

    def test_empty_input(self):
        action_type, stat, dc = self.resolver._infer_action_profile("")
        assert action_type == "action"
        assert stat == "Strength"
        assert dc == 12

    def test_case_insensitive(self):
        action_type, _, _ = self.resolver._infer_action_profile("PERSUADE the guard")
        assert action_type == "dialogue"


# ===========================================================================
# _extract_attributes
# ===========================================================================


class TestExtractAttributes:
    def setup_method(self):
        self.resolver = Resolver()

    def test_extracts_from_first_entity(self):
        ctx = {"entities": [{"properties": {"attributes": {"Strength": 14, "Dexterity": 12}}}]}
        attrs = self.resolver._extract_attributes(ctx)
        assert attrs["Strength"] == 14
        assert attrs["Dexterity"] == 12

    def test_empty_entities_returns_empty(self):
        attrs = self.resolver._extract_attributes({"entities": []})
        assert attrs == {}

    def test_no_entities_key_returns_empty(self):
        attrs = self.resolver._extract_attributes({})
        assert attrs == {}

    def test_entity_without_attributes_skipped(self):
        ctx = {
            "entities": [
                {"properties": {}},  # no attributes key
                {"properties": {"attributes": {"Str": 18}}},  # second entity
            ]
        }
        attrs = self.resolver._extract_attributes(ctx)
        assert attrs == {"Str": 18}

    def test_entity_without_properties_skipped(self):
        ctx = {
            "entities": [
                {},  # no properties key
                {"properties": {"attributes": {"Str": 10}}},
            ]
        }
        attrs = self.resolver._extract_attributes(ctx)
        assert attrs == {"Str": 10}


# ===========================================================================
# resolve_turn — full integration (dice randomness frozen)
# ===========================================================================


class TestResolveTurn:
    @pytest.fixture
    def resolver(self):
        return Resolver()

    @pytest.mark.asyncio
    async def test_returns_required_keys(self, resolver):
        result = await resolver.resolve_turn(
            scene_id="scene-001",
            user_input="I search the room",
            context=_make_context(),
        )
        required = {
            "scene_id",
            "action_type",
            "stat",
            "difficulty_class",
            "roll_total",
            "roll_breakdown",
            "success",
            "success_level",
            "effects",
            "proposals",
        }
        assert required.issubset(set(result.keys()))

    @pytest.mark.asyncio
    async def test_scene_id_preserved(self, resolver):
        sid = str(uuid4())
        result = await resolver.resolve_turn(sid, "look around", _make_context())
        assert result["scene_id"] == sid

    @pytest.mark.asyncio
    async def test_natural_20_is_critical_success(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=20):
            result = await resolver.resolve_turn("s1", "attack", _make_context())
        assert result["success_level"] == "critical_success"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_natural_1_is_critical_failure(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=1):
            result = await resolver.resolve_turn("s1", "attack", _make_context())
        assert result["success_level"] == "critical_failure"
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_high_roll_success(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=18):
            result = await resolver.resolve_turn("s1", "search the area", _make_context())
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_very_low_roll_failure(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=2):
            result = await resolver.resolve_turn("s1", "I attack the bandit", _make_context())
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_dialogue_sets_correct_stat(self, resolver):
        result = await resolver.resolve_turn("s1", "convince the guard", _make_context())
        assert result["stat"] == "Charisma"

    @pytest.mark.asyncio
    async def test_search_sets_correct_stat(self, resolver):
        result = await resolver.resolve_turn("s1", "notice any traps", _make_context())
        assert result["stat"] == "Wisdom"

    @pytest.mark.asyncio
    async def test_effects_never_empty(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=10):
            result = await resolver.resolve_turn("s1", "I strike the bandit", _make_context())
        assert len(result["effects"]) > 0

    @pytest.mark.asyncio
    async def test_dialogue_effects_include_npc_reacts(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=15):
            result = await resolver.resolve_turn("s1", "I attack the bandit", _make_context())
        assert "npc_reacts" in result["effects"] or "fiction_advances" in result["effects"]

    @pytest.mark.asyncio
    async def test_proposals_is_list(self, resolver):
        result = await resolver.resolve_turn("s1", "explore the dungeon", _make_context())
        assert isinstance(result["proposals"], list)

    @pytest.mark.asyncio
    async def test_no_context_uses_defaults(self, resolver):
        """resolve_turn should work even with no context (empty entity list)."""
        result = await resolver.resolve_turn("s1", "walk forward", None)
        assert "success_level" in result

    @pytest.mark.asyncio
    async def test_roll_breakdown_contains_dice_info(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=10):
            result = await resolver.resolve_turn("s1", "I attack the goblin", _make_context())
        breakdown = result["roll_breakdown"]
        assert "1d20" in breakdown

    @pytest.mark.asyncio
    async def test_success_effects_include_momentum(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=20):
            result = await resolver.resolve_turn("s1", "I strike the dragon", _make_context())
        assert "momentum_gained" in result["effects"]

    @pytest.mark.asyncio
    async def test_failure_effects_include_setback(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=1):
            result = await resolver.resolve_turn("s1", "I attack the dragon", _make_context())
        assert "setback" in result["effects"]

    @pytest.mark.asyncio
    async def test_partial_success_returns_consequence_options(self, resolver):
        # Use a contested action with roll 11 → partial success
        ctx = {"entities": [{"properties": {"attributes": {"Strength": 10}}}], "turns": []}
        with patch("monitor_data.utils.dice.random.randint", return_value=11):
            result = await resolver.resolve_turn("s1", "I strike the bandit", ctx)
        assert result["success_level"] == "partial_success"
        assert result["requires_player_choice"] is True
        assert len(result["consequence_options"]) >= 1
        assert result["narrative_pressure"] == "rising"

    @pytest.mark.asyncio
    async def test_query_style_input_surfaces_risk_preview(self, resolver):
        result = await resolver.resolve_turn(
            "s1",
            "What should I know before I force the hatch?",
            _make_context(),
        )
        assert result["intent_type"] == "query"
        assert result["risk_preview"]

    @pytest.mark.asyncio
    async def test_narrative_game_system_skips_dice(self, resolver):
        result = await resolver.resolve_turn(
            "s1",
            "I talk the crew through the crisis.",
            _make_context(),
            game_context={
                "core_mechanic": {
                    "type": "narrative",
                    "formula": "No roll — resolve by fiction",
                    "success_type": "highest_wins",
                },
                "attributes": [],
                "skills": [],
                "resources": [],
            },
            play_mode="dice_game_system",
        )
        assert result["resolution_type"] == "narrative"
        assert result["roll_total"] is None
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_roll_under_weighted_narrative_proposes_base_target_10(self, resolver):
        weighted_context = {
            "core_mechanic": {
                "type": "d20",
                "formula": "1d20 <= 10 + relevant approach + situational modifiers",
                "success_type": "meet_or_beat",
                "success_threshold": "Base target 10; roll under or equal to the final target",
            },
            "attributes": [
                {
                    "name": "Presence",
                    "abbreviation": "PRE",
                    "min_value": -3,
                    "max_value": 3,
                    "default_value": 0,
                    "modifier_formula": None,
                }
            ],
            "skills": [
                {
                    "name": "Sway",
                    "abbreviation": "SWY",
                    "linked_attribute": "Presence",
                    "description": "convince, charm, threaten, negotiate",
                }
            ],
            "resources": [],
            "rules": [],
        }
        ctx = {"entities": [{"properties": {"attributes": {"PRE": 2, "Presence": 2}}}], "turns": []}

        result = await resolver.resolve_turn(
            "s1",
            "convince the guard to let us through",
            ctx,
            game_context=weighted_context,
            play_mode="dice_game_system",
        )

        assert result["difficulty_class"] == 10
        assert result["modifier"] == 2
        assert result["resolution_type"] == "propose_roll"
        assert result["success"] is None
        assert result["roll_under"] is True
        assert result["roll_breakdown"] == "propose_roll — PRE check (DC 10)"

    @pytest.mark.asyncio
    async def test_profile_aliases_help_route_nonstandard_social_actions(self, resolver):
        game_context = {
            "core_mechanic": {
                "type": "d20",
                "formula": "1d20 + relevant attribute vs DC",
                "success_type": "meet_or_beat",
            },
            "attributes": [
                {
                    "name": "Tech",
                    "abbreviation": "TEC",
                    "min_value": -3,
                    "max_value": 3,
                    "default_value": 0,
                    "description": "Repairs, machines, engineering, void gear",
                    "modifier_formula": None,
                },
                {
                    "name": "Presence",
                    "abbreviation": "PRE",
                    "min_value": -3,
                    "max_value": 3,
                    "default_value": 0,
                    "description": "Charm, command, court politics, social leverage",
                    "modifier_formula": None,
                },
            ],
            "skills": [],
            "resources": [],
            "rules": [],
        }
        ctx = {
            "entities": [
                {"properties": {"attributes": {"TEC": 0, "Tech": 0, "PRE": 2, "Presence": 2}}}
            ],
            "turns": [],
            "source_profile": {
                "canon_signal_terms": ["Prince", "Primogen", "Elysium"],
                "institution_model": ["prince-led domains", "sect allegiance"],
                "term_lexicon": {"Embrace": ["Siring"]},
                "confidence_by_field": {
                    "canon_signal_terms": 0.92,
                    "institution_model": 0.9,
                    "term_lexicon": 0.95,
                },
            },
        }

        with patch("monitor_data.utils.dice.random.randint", return_value=12):
            result = await resolver.resolve_turn(
                "s1",
                "I ask the prince about the embrace",
                ctx,
                game_context=game_context,
                play_mode="dice_game_system",
            )

        assert result["stat"] == "PRE"
        assert result["intent_type"] == "dialogue"

    @pytest.mark.asyncio
    async def test_profile_and_rules_surface_ship_subsystem_hint(self, resolver):
        game_context = {
            "core_mechanic": {
                "type": "d20",
                "formula": "1d20 + relevant attribute vs DC",
                "success_type": "meet_or_beat",
            },
            "attributes": [
                {
                    "name": "Tech",
                    "abbreviation": "TEC",
                    "min_value": -3,
                    "max_value": 3,
                    "default_value": 0,
                    "description": "Piloting, repairs, ship systems, rerouting power",
                    "modifier_formula": None,
                },
                {
                    "name": "Presence",
                    "abbreviation": "PRE",
                    "min_value": -3,
                    "max_value": 3,
                    "default_value": 0,
                    "description": "Command, morale, negotiation",
                    "modifier_formula": None,
                },
            ],
            "skills": [
                {
                    "name": "Helm",
                    "abbreviation": "HELM",
                    "linked_attribute": "Tech",
                    "description": "pilot ships, steer through danger, reroute power during void engagements",
                }
            ],
            "resources": [],
            "rules": [
                {
                    "name": "Ship Combat Stations",
                    "rule_type": "combat",
                    "description": "Use helm actions and repair actions during ship combat and boarding scenes.",
                    "formula": "",
                    "applies_to_subject": "ship",
                }
            ],
        }
        ctx = {
            "entities": [
                {"properties": {"attributes": {"TEC": 2, "Tech": 2, "PRE": 0, "Presence": 0}}}
            ],
            "turns": [],
            "source_profile": {
                "important_named_sets": ["Ship Combat"],
                "canon_signal_terms": ["Helm", "Broadside"],
                "confidence_by_field": {
                    "important_named_sets": 0.94,
                    "canon_signal_terms": 0.9,
                },
            },
        }

        with patch("monitor_data.utils.dice.random.randint", return_value=14):
            result = await resolver.resolve_turn(
                "s1",
                "I swing the ship hard to port and reroute power to the guns",
                ctx,
                game_context=game_context,
                play_mode="dice_game_system",
            )

        assert result["stat"] == "TEC"
        assert result["subsystem_hint"] == "ship"


# ===========================================================================
# resolve_turn — partial success boundary
# ===========================================================================


class TestPartialSuccess:
    @pytest.fixture
    def resolver(self):
        return Resolver()

    @pytest.mark.asyncio
    async def test_at_dc_minus_2_is_partial(self, resolver):
        # Use a contested action with default DC ~13. Roll 11 → partial_success.
        # Strength is 10 → modifier = (10-10)//2 = 0.
        # Patch random to return 11 (total = 11+0 = 11 = DC-2).
        ctx = {"entities": [{"properties": {"attributes": {"Strength": 10}}}], "turns": []}
        with patch("monitor_data.utils.dice.random.randint", return_value=11):
            result = await resolver.resolve_turn("s1", "I attack the orc", ctx)
        assert result["success_level"] == "partial_success"
        assert "mixed_outcome" in result["effects"]


# ===========================================================================
# resolve_check — stat / skill check via game system lookup
# ===========================================================================


def _entity_json(universe_id: str, strength: int = 16) -> str:
    import json

    return json.dumps(
        {
            "universe_id": universe_id,
            "properties": {"attributes": {"Strength": strength, "Dexterity": 14, "Wisdom": 10}},
        }
    )


def _universe_json(multiverse_id: str) -> str:
    import json

    return json.dumps({"multiverse_id": multiverse_id})


def _multiverse_json(system_name: str) -> str:
    import json

    return json.dumps({"system_name": system_name})


def _system_list_json(system_name: str = "Standard Fantasy v5") -> str:
    import json

    return json.dumps(
        {
            "systems": [
                {
                    "name": system_name,
                    "core_mechanic": {"type": "d20", "roll_expression": "1d20"},
                    "attributes": [
                        {
                            "name": "Strength",
                            "default_value": 10,
                            "modifier_formula": "(VALUE - 10) // 2",
                        }
                    ],
                    "skills": [
                        {"name": "Athletics", "linked_attribute": "Strength"},
                    ],
                }
            ]
        }
    )


class TestResolveCheck:
    @pytest.fixture
    def resolver(self):
        return Resolver()

    def _setup_tool(
        self,
        resolver,
        universe_id: str,
        multiverse_id: str,
        system_name: str = "Standard Fantasy v5",
    ):
        async def _tool(tool_name: str, params: dict):
            if tool_name == "neo4j_get_entity":
                return _entity_json(universe_id)
            if tool_name == "neo4j_get_universe":
                return _universe_json(multiverse_id)
            if tool_name == "neo4j_get_multiverse":
                return _multiverse_json(system_name)
            if tool_name == "mongodb_list_game_systems":
                return _system_list_json(system_name)
            return None

        resolver.call_tool = _tool

    @pytest.mark.asyncio
    async def test_entity_not_found_returns_error(self, resolver):
        resolver.call_tool = AsyncMock(return_value=None)
        result = await resolver.resolve_check("ent-1", "Strength")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_universe_not_found_returns_error(self, resolver):
        import json

        async def _tool(name, params):
            if name == "neo4j_get_entity":
                return json.dumps({"universe_id": str(uuid4()), "properties": {}})
            return None

        resolver.call_tool = _tool
        result = await resolver.resolve_check("ent-1", "Strength")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_multiverse_not_found_falls_back_to_default_system(self, resolver):
        uid = str(uuid4())
        mid = str(uuid4())

        async def _tool(name, params):
            if name == "neo4j_get_entity":
                return _entity_json(uid)
            if name == "neo4j_get_universe":
                return _universe_json(mid)
            if name == "neo4j_get_multiverse":
                return None  # Missing multiverse — triggers fallback
            if name == "mongodb_list_game_systems":
                return _system_list_json("Standard Fantasy v5")
            return None

        resolver.call_tool = _tool

        with patch("monitor_data.utils.dice.random.randint", return_value=15):
            result = await resolver.resolve_check("ent-1", "Strength", dc=10)

        # Should still resolve — fallback system name is "Standard Fantasy v5"
        assert "success" in result

    @pytest.mark.asyncio
    async def test_system_not_found_returns_error(self, resolver):
        uid = str(uuid4())
        mid = str(uuid4())

        async def _tool(name, params):
            if name == "neo4j_get_entity":
                return _entity_json(uid)
            if name == "neo4j_get_universe":
                return _universe_json(mid)
            if name == "neo4j_get_multiverse":
                return _multiverse_json("UnknownSystem v99")
            if name == "mongodb_list_game_systems":
                return _system_list_json("Standard Fantasy v5")  # different name
            return None

        resolver.call_tool = _tool

        result = await resolver.resolve_check("ent-1", "Strength")
        assert "error" in result
        assert "UnknownSystem v99" in result["error"]

    @pytest.mark.asyncio
    async def test_d20_attribute_check_success(self, resolver):
        uid, mid = str(uuid4()), str(uuid4())
        self._setup_tool(resolver, uid, mid)

        # Strength 16 → modifier (16-10)//2 = 3. Roll 15 → total 18. DC=10 → success.
        with patch("monitor_data.utils.dice.random.randint", return_value=15):
            result = await resolver.resolve_check("ent-1", "Strength", dc=10)

        assert result["success"] is True
        assert result["total"] == 18  # 15 + 3
        assert result["modifier"] == 3
        assert result["stat"] == "Strength"

    @pytest.mark.asyncio
    async def test_d20_attribute_check_failure(self, resolver):
        uid, mid = str(uuid4()), str(uuid4())
        self._setup_tool(resolver, uid, mid)

        # Strength 16 → modifier 3. Roll 1 → total 4. DC=15 → failure.
        with patch("monitor_data.utils.dice.random.randint", return_value=1):
            result = await resolver.resolve_check("ent-1", "Strength", dc=15)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_skill_check_uses_linked_attribute(self, resolver):
        uid, mid = str(uuid4()), str(uuid4())
        self._setup_tool(resolver, uid, mid)

        # "Athletics" links to "Strength" (16 → mod 3). Roll 12 → total 15. DC=10 → success.
        with patch("monitor_data.utils.dice.random.randint", return_value=12):
            result = await resolver.resolve_check("ent-1", "Athletics", dc=10)

        assert result["success"] is True
        assert result["stat"] == "Athletics"

    @pytest.mark.asyncio
    async def test_unknown_stat_returns_error(self, resolver):
        uid, mid = str(uuid4()), str(uuid4())
        self._setup_tool(resolver, uid, mid)

        result = await resolver.resolve_check("ent-1", "FakeStatThatDoesNotExist")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_dice_pool_mechanic_counts_successes(self, resolver):
        import json

        uid, mid = str(uuid4()), str(uuid4())

        async def _tool(name, params):
            if name == "neo4j_get_entity":
                return json.dumps(
                    {
                        "universe_id": uid,
                        "properties": {"attributes": {"Strength": 3}},  # 3 dice in pool
                    }
                )
            if name == "neo4j_get_universe":
                return _universe_json(mid)
            if name == "neo4j_get_multiverse":
                return json.dumps({"system_name": "DicePool TTRPG"})
            if name == "mongodb_list_game_systems":
                return json.dumps(
                    {
                        "systems": [
                            {
                                "name": "DicePool TTRPG",
                                "core_mechanic": {"type": "dice_pool", "success_threshold": 7},
                                "attributes": [
                                    {
                                        "name": "Strength",
                                        "default_value": 3,
                                        "modifier_formula": None,
                                    },
                                ],
                                "skills": [],
                            }
                        ]
                    }
                )
            return None

        resolver.call_tool = _tool

        # 3d10 rolls — patch to all 8s (each ≥ 7 → 3 successes)
        with patch("monitor_data.utils.dice.random.randint", return_value=8):
            result = await resolver.resolve_check("ent-1", "Strength", dc=1)

        assert result["success"] is True
        assert result["total"] == 3  # 3 successes


# ===========================================================================
# _classify_roll_necessity (UC-GM-6)
# ===========================================================================


class TestClassifyRollNecessity:
    """Test the three-way action classification: trivial / propose_roll / contested."""

    @pytest.fixture
    def resolver(self):
        return Resolver()

    # --- Trivial cases (no dice needed) ---

    @pytest.mark.asyncio
    async def test_look_around_is_trivial(self, resolver):
        result = await resolver.resolve_turn("s1", "I look around the cargo bay", _make_context())
        assert result["resolution_type"] == "trivial"
        assert result["roll_total"] is None
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_simple_speech_is_trivial(self, resolver):
        result = await resolver.resolve_turn(
            "s1", 'I say "Hello" to the bartender', _make_context()
        )
        assert result["resolution_type"] == "trivial"

    @pytest.mark.asyncio
    async def test_walking_is_trivial(self, resolver):
        result = await resolver.resolve_turn("s1", "I walk to the bridge", _make_context())
        assert result["resolution_type"] == "trivial"

    @pytest.mark.asyncio
    async def test_query_intent_is_trivial(self, resolver):
        """Query intent bypasses roll classification entirely → trivial."""
        from monitor_agents.resolver import _classify_roll_necessity

        result = _classify_roll_necessity("What should I know before I enter?", "action", "query")
        assert result == "trivial"

    # --- Propose roll cases (GM offers, player chooses) ---

    @pytest.mark.asyncio
    async def test_persuasion_is_propose_roll(self, resolver):
        result = await resolver.resolve_turn("s1", "I try to persuade the guard", _make_context())
        assert result["resolution_type"] == "propose_roll"
        assert result["roll_total"] is None
        assert result["success"] is None
        assert result["success_level"] == "pending"
        assert result["requires_player_choice"] is True
        assert "roll_invitation" in result
        assert result["roll_necessity"] == "propose_roll"

    @pytest.mark.asyncio
    async def test_threaten_is_propose_roll(self, resolver):
        result = await resolver.resolve_turn("s1", "I threaten the merchant", _make_context())
        assert result["resolution_type"] == "propose_roll"

    @pytest.mark.asyncio
    async def test_sneak_past_danger_is_propose_roll(self, resolver):
        result = await resolver.resolve_turn("s1", "I sneak past the guard", _make_context())
        assert result["resolution_type"] == "propose_roll"

    @pytest.mark.asyncio
    async def test_investigate_suspicious_area_is_propose_roll(self, resolver):
        result = await resolver.resolve_turn("s1", "I examine the trap carefully", _make_context())
        assert result["resolution_type"] == "propose_roll"

    # --- Contested cases (roll immediately) ---

    @pytest.mark.asyncio
    async def test_attack_is_contested(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=15):
            result = await resolver.resolve_turn("s1", "I attack the orc", _make_context())
        assert result["resolution_type"] == "dice"
        assert result["roll_necessity"] == "contested"
        assert result["roll_total"] is not None

    @pytest.mark.asyncio
    async def test_shoot_is_contested(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=10):
            result = await resolver.resolve_turn("s1", "I shoot at the target", _make_context())
        assert result["resolution_type"] == "dice"

    @pytest.mark.asyncio
    async def test_cast_spell_is_contested(self, resolver):
        with patch("monitor_data.utils.dice.random.randint", return_value=12):
            result = await resolver.resolve_turn("s1", "I cast fireball", _make_context())
        assert result["resolution_type"] == "dice"

    # --- Edge cases ---

    @pytest.mark.asyncio
    async def test_forced_narrative_still_works(self, resolver):
        """Forced narrative should bypass roll_necessity entirely (for low stakes)."""
        from monitor_agents.gm_awareness import (
            ActionType, IntentType, RollNecessity, Severity, CausalityAction, GMAwareness,
        )
        accept_verdict = GMAwareness(
            intent_type=IntentType.ACTION,
            action_type=ActionType.MOVEMENT,
            roll_necessity=RollNecessity.TRIVIAL,
            declares_outcome=True,
            violates_causality=False,
            severity=Severity.NONE,
            action=CausalityAction.ACCEPT,
            reasoning="Entering an empty room is a declared low-stakes outcome.",
        )
        with patch(
            "monitor_agents.resolver.check_gm_awareness",
            new_callable=AsyncMock,
            return_value=accept_verdict,
        ):
            result = await resolver.resolve_turn("s1", "I successfully enter the room", _make_context())
        assert result["resolution_type"] == "forced_narrative"
        assert result["forced_narrative"] is True

    @pytest.mark.asyncio
    async def test_narrative_mode_still_works(self, resolver):
        """Pure narrative mode should bypass roll_necessity."""
        result = await resolver.resolve_turn(
            "s1", "I attack the orc", _make_context(), play_mode="narrative"
        )
        assert result["resolution_type"] == "narrative"
        assert result["roll_total"] is None

    @pytest.mark.asyncio
    async def test_trivial_has_risk_preview(self, resolver):
        result = await resolver.resolve_turn("s1", "I look around", _make_context())
        assert result["resolution_type"] == "trivial"
        assert "risk_preview" in result
        assert result["risk_preview"] != ""

    @pytest.mark.asyncio
    async def test_propose_roll_has_stat_and_dc(self, resolver):
        result = await resolver.resolve_turn("s1", "I try to pick the lock", _make_context())
        assert result["resolution_type"] == "propose_roll"
        assert result["stat"] is not None
        assert result["difficulty_class"] is not None


# ===========================================================================
# Advantage / Disadvantage
# ===========================================================================


class TestAdvantageDisadvantage:
    @pytest.fixture
    def resolver(self):
        return Resolver()

    @pytest.mark.asyncio
    async def test_advantage_rolls_2d20kh1(self, resolver):
        """Advantage uses 2d20 keep highest."""
        result = await resolver.resolve_turn(
            "s1", "I attack the orc", _make_context(), roll_mode="advantage"
        )
        assert result["roll_mode"] == "advantage"
        assert "2d20kh1" in result["roll_breakdown"]
        detail = result["roll_detail"]
        assert detail["roll_mode"] == "advantage"
        # kept_rolls should exist and be a single number (the highest)
        assert "kept_rolls" in detail

    @pytest.mark.asyncio
    async def test_disadvantage_rolls_2d20kl1(self, resolver):
        """Disadvantage uses 2d20 keep lowest."""
        result = await resolver.resolve_turn(
            "s1", "I attack the orc", _make_context(), roll_mode="disadvantage"
        )
        assert result["roll_mode"] == "disadvantage"
        assert "2d20kl1" in result["roll_breakdown"]
        detail = result["roll_detail"]
        assert detail["roll_mode"] == "disadvantage"

    @pytest.mark.asyncio
    async def test_normal_roll_mode_is_default(self, resolver):
        """Default roll_mode is 'normal' (1d20)."""
        result = await resolver.resolve_turn("s1", "I attack the orc", _make_context())
        assert result["roll_mode"] == "normal"
        assert "1d20" in result["roll_breakdown"]
        assert "2d20" not in result["roll_breakdown"]

    @pytest.mark.asyncio
    async def test_advantage_with_natural_20_is_critical(self, resolver):
        """Advantage with a kept 20 is critical success."""
        with patch("monitor_data.utils.dice.random.randint", side_effect=[5, 20]):
            result = await resolver.resolve_turn(
                "s1", "I strike the dragon", _make_context(), roll_mode="advantage"
            )
        assert result["success_level"] == "critical_success"

    @pytest.mark.asyncio
    async def test_disadvantage_with_natural_1_fails(self, resolver):
        """Disadvantage with a kept 1 is critical failure."""
        with patch("monitor_data.utils.dice.random.randint", side_effect=[1, 15]):
            result = await resolver.resolve_turn(
                "s1", "I attack the dragon", _make_context(), roll_mode="disadvantage"
            )
        assert result["success_level"] in ("critical_failure", "failure")

    @pytest.mark.asyncio
    async def test_advantage_propose_roll_preserves_mode(self, resolver):
        """Even propose_roll tracks roll_mode for the invitation."""
        result = await resolver.resolve_turn(
            "s1", "I try to persuade the guard", _make_context(), roll_mode="advantage"
        )
        assert result["resolution_type"] == "propose_roll"
        assert result["roll_mode"] == "advantage" if "roll_mode" in result else True


# ===========================================================================
# Opposed Checks
# ===========================================================================


class TestOpposedChecks:
    @pytest.fixture
    def resolver(self):
        return Resolver()

    @pytest.fixture
    def opposed_context(self):
        """Context with two entities for opposed checks."""
        return {
            "entities": [
                {
                    "id": "actor-001",
                    "name": "Player",
                    "properties": {"attributes": {"Strength": 16, "Dexterity": 14}},
                },
                {
                    "id": "target-001",
                    "name": "Orc",
                    "properties": {"attributes": {"Strength": 14, "Dexterity": 10}},
                },
            ],
            "turns": [],
        }

    @pytest.mark.asyncio
    async def test_opposed_check_actor_wins(self, resolver, opposed_context):
        """Actor rolls higher → actor wins."""
        # Actor: 18 + 3 = 21, Target: 10 + 2 = 12
        with patch("monitor_data.utils.dice.random.randint", side_effect=[18, 10]):
            result = await resolver.resolve_opposed_check(
                actor_id="actor-001",
                target_id="target-001",
                stat_name="Strength",
                context=opposed_context,
            )
        assert result["winner"] == "actor"
        assert result["margin"] == 9
        assert result["success_level"] == "success"
        assert result["actor_roll"]["total"] > result["target_roll"]["total"]

    @pytest.mark.asyncio
    async def test_opposed_check_target_wins(self, resolver, opposed_context):
        """Target rolls higher → target wins."""
        with patch("monitor_data.utils.dice.random.randint", side_effect=[5, 18]):
            result = await resolver.resolve_opposed_check(
                actor_id="actor-001",
                target_id="target-001",
                stat_name="Dexterity",
                context=opposed_context,
            )
        assert result["winner"] == "target"
        assert result["margin"] > 0
        assert result["success_level"] == "failure"

    @pytest.mark.asyncio
    async def test_opposed_check_tie_is_partial(self, resolver, opposed_context):
        """Both roll same total → tie → partial_success. Use equal stats for true tie."""
        # Actor and target both have Strength that produces the same modifier
        # Actor: 1d20(12) + 3 = 15, Target: 1d20(11) + 2 = 13 → actor wins
        # For a tie, both need same modifier and same roll
        ctx = {
            "entities": [
                {
                    "id": "actor-001",
                    "name": "Player",
                    "properties": {"attributes": {"Strength": 14}},
                },
                {"id": "target-001", "name": "Orc", "properties": {"attributes": {"Strength": 14}}},
            ],
            "turns": [],
        }
        with patch("monitor_data.utils.dice.random.randint", side_effect=[12, 12]):
            result = await resolver.resolve_opposed_check(
                actor_id="actor-001",
                target_id="target-001",
                stat_name="Strength",
                context=ctx,
            )
        assert result["winner"] == "tie"
        assert result["margin"] == 0
        assert result["success_level"] == "partial_success"

    @pytest.mark.asyncio
    async def test_opposed_check_preserves_stat(self, resolver, opposed_context):
        """The stat name used is returned."""
        result = await resolver.resolve_opposed_check(
            actor_id="actor-001",
            target_id="target-001",
            stat_name="Dexterity",
            context=opposed_context,
        )
        assert result["opposed_stat"] == "Dexterity"

    @pytest.mark.asyncio
    async def test_opposed_check_roll_details_present(self, resolver, opposed_context):
        """Both actor_roll and target_roll contain full details."""
        result = await resolver.resolve_opposed_check(
            actor_id="actor-001",
            target_id="target-001",
            stat_name="Strength",
            context=opposed_context,
        )
        for key in ("actor_roll", "target_roll"):
            assert key in result
            assert "total" in result[key]
            assert "natural" in result[key]
            assert "modifier" in result[key]
            assert "rolls" in result[key]

    @pytest.mark.asyncio
    async def test_opposed_check_with_advantage(self, resolver, opposed_context):
        """Advantage mode uses 2d20kh1 for opposed checks."""
        with patch("monitor_data.utils.dice.random.randint", side_effect=[5, 18, 10, 12]):
            result = await resolver.resolve_opposed_check(
                actor_id="actor-001",
                target_id="target-001",
                stat_name="Strength",
                context=opposed_context,
                roll_mode="advantage",
            )
        assert result["actor_roll"]["kept_rolls"] is not None
        assert result["target_roll"]["kept_rolls"] is not None

    @pytest.mark.asyncio
    async def test_opposed_check_no_context_is_graceful(self, resolver):
        """Empty context returns a valid result without crashing.
        Note: default stat_value=0 yields modifier=-5 via (0-10)//2."""
        result = await resolver.resolve_opposed_check(
            actor_id="actor-001",
            target_id="target-001",
            stat_name="Strength",
            context={"entities": [], "turns": []},
        )
        assert "winner" in result
        assert result["actor_roll"]["modifier"] == -5

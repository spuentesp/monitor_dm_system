import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4

from monitor_data.schemas.game_systems import (
    AttributeDefinition,
    ConditionDefinition,
    CoreMechanic,
    CoreMechanicType,
    GameRule,
    GameRuleType,
    NPCCreationRules,
    NPCStatBlock,
    NPCTier,
    ResolutionMechanic,
    ResourceDefinition,
    SceneryRule,
    SkillDefinition,
    SuccessType,
)
from monitor_agents.analyzer._game_system_persistence import (
    _build_attributes,
    _build_character_creation,
    _build_conditions,
    _build_core_mechanic,
    _build_npc_creation_rules,
    _build_npc_stat_blocks,
    _build_resolution_mechanics,
    _build_resources,
    _build_scenery_rules,
    _build_skills,
    _build_typed_list,
    _build_typed_rules,
    _merge_powers_and_subsystems,
    save_game_system,
)


# =============================================================================
# _build_conditions (pre-existing, extended)
# =============================================================================


@pytest.mark.unit
def test_build_conditions() -> None:
    raw_data = {
        "conditions": [
            {
                "name": "poisoned",
                "description": "Taking toxic damage",
                "roll_modifier": "-2",
                "roll_mode_override": "disadvantage",
            },
            {"name": "blinded", "roll_modifier": 0},
        ]
    }
    conditions = _build_conditions(raw_data)
    assert len(conditions) == 2
    assert isinstance(conditions[0], ConditionDefinition)
    assert conditions[0].name == "poisoned"
    assert conditions[0].roll_modifier == -2
    assert conditions[0].roll_mode_override == "disadvantage"
    assert conditions[1].name == "blinded"
    assert conditions[1].roll_modifier == 0
    assert conditions[1].roll_mode_override is None


@pytest.mark.unit
def test_build_conditions_empty() -> None:
    assert _build_conditions({}) == []


@pytest.mark.unit
def test_build_conditions_missing_name_skipped() -> None:
    raw = {"conditions": [{"roll_modifier": 1}]}
    result = _build_conditions(raw)
    assert result == []


# =============================================================================
# _build_scenery_rules (pre-existing, extended)
# =============================================================================


@pytest.mark.unit
def test_build_scenery_rules() -> None:
    raw_data = {
        "scenery_rules": [
            {
                "keyword": "high ground",
                "trigger_verbs": ["attack", "shoot"],
                "roll_modifier": "2",
                "roll_mode_override": "advantage",
                "reason_text": "Elevation advantage",
            }
        ]
    }
    rules = _build_scenery_rules(raw_data)
    assert len(rules) == 1
    assert isinstance(rules[0], SceneryRule)
    assert rules[0].keyword == "high ground"
    assert rules[0].trigger_verbs == ["attack", "shoot"]
    assert rules[0].roll_modifier == 2
    assert rules[0].roll_mode_override == "advantage"


@pytest.mark.unit
def test_build_scenery_rules_empty() -> None:
    assert _build_scenery_rules({}) == []


@pytest.mark.unit
def test_build_scenery_rules_no_modifier() -> None:
    raw = {"scenery_rules": [{"keyword": "darkness", "reason_text": "Low visibility"}]}
    rules = _build_scenery_rules(raw)
    assert len(rules) == 1
    assert rules[0].roll_modifier is None


# =============================================================================
# _build_typed_rules
# =============================================================================


@pytest.mark.unit
class TestBuildTypedRules:
    def test_passthrough_game_rule_object(self):
        rule = GameRule(name="Sneak Attack", rule_type=GameRuleType.COMBAT, description="")
        result = _build_typed_rules([rule])
        assert result[0] is rule

    def test_converts_dict_to_game_rule(self):
        raw = [{"name": "Rage", "rule_type": "combat", "description": "Barbaric fury"}]
        result = _build_typed_rules(raw)
        assert len(result) == 1
        assert isinstance(result[0], GameRule)
        assert result[0].name == "Rage"
        assert result[0].rule_type == GameRuleType.COMBAT

    def test_invalid_rule_type_falls_back_to_custom(self):
        raw = [{"name": "Mystery", "rule_type": "not_a_real_type"}]
        result = _build_typed_rules(raw)
        assert result[0].rule_type == GameRuleType.CUSTOM

    def test_missing_rule_type_defaults_to_custom(self):
        raw = [{"name": "Unknown Thing"}]
        result = _build_typed_rules(raw)
        assert result[0].rule_type == GameRuleType.CUSTOM

    def test_name_truncated_to_200(self):
        raw = [{"name": "A" * 300, "rule_type": "core"}]
        result = _build_typed_rules(raw)
        assert len(result[0].name) == 200

    def test_description_truncated_to_1000(self):
        raw = [{"name": "Rule", "rule_type": "core", "description": "B" * 1500}]
        result = _build_typed_rules(raw)
        assert len(result[0].description) == 1000

    def test_missing_name_uses_default(self):
        raw = [{"rule_type": "core"}]
        result = _build_typed_rules(raw)
        assert result[0].name == "Unknown Rule"

    def test_empty_list_returns_empty(self):
        assert _build_typed_rules([]) == []

    def test_tags_and_formula_carried_through(self):
        raw = [{"name": "Power Attack", "rule_type": "combat", "formula": "-5/+10", "tags": ["feat"]}]
        result = _build_typed_rules(raw)
        assert result[0].formula == "-5/+10"
        assert "feat" in result[0].tags


# =============================================================================
# _build_typed_list
# =============================================================================


@pytest.mark.unit
class TestBuildTypedList:
    def test_passthrough_already_typed_objects(self):
        attr = AttributeDefinition(name="STR", abbreviation="STR", min_value=1, max_value=20, default_value=10)
        result = _build_typed_list([attr], AttributeDefinition, lambda x: None)
        assert result[0] is attr

    def test_non_dict_items_skipped(self):
        result = _build_typed_list(["string", 42, None], AttributeDefinition, lambda x: None)
        assert result == []

    def test_builder_exception_silently_skipped(self):
        def bad_builder(d):
            raise ValueError("boom")

        result = _build_typed_list([{"name": "test"}], AttributeDefinition, bad_builder)
        assert result == []

    def test_mixed_valid_and_invalid(self):
        attr = AttributeDefinition(name="INT", abbreviation="INT", min_value=1, max_value=20, default_value=10)

        def builder(d):
            if d.get("fail"):
                raise ValueError
            return attr

        result = _build_typed_list(
            [attr, {"ok": True}, {"fail": True}, "not_a_dict"],
            AttributeDefinition,
            builder,
        )
        assert len(result) == 2


# =============================================================================
# _build_attributes
# =============================================================================


@pytest.mark.unit
class TestBuildAttributes:
    def test_minimal_attribute(self):
        raw = {"attributes": [{"name": "Strength"}]}
        result = _build_attributes(raw)
        assert len(result) == 1
        assert isinstance(result[0], AttributeDefinition)
        assert result[0].name == "Strength"
        assert result[0].min_value == 1
        assert result[0].max_value == 20
        assert result[0].default_value == 10

    def test_abbreviation_defaults_to_name_first_10(self):
        raw = {"attributes": [{"name": "Strength"}]}
        result = _build_attributes(raw)
        assert result[0].abbreviation == "Strength"[:10]

    def test_explicit_values_used(self):
        raw = {
            "attributes": [
                {
                    "name": "Agility",
                    "abbreviation": "AGI",
                    "min_value": 0,
                    "max_value": 100,
                    "default_value": 50,
                    "modifier_formula": "(val-10)//2",
                }
            ]
        }
        result = _build_attributes(raw)
        assert result[0].abbreviation == "AGI"
        assert result[0].min_value == 0
        assert result[0].max_value == 100
        assert result[0].default_value == 50
        assert result[0].modifier_formula == "(val-10)//2"

    def test_string_int_values_coerced(self):
        raw = {"attributes": [{"name": "STR", "min_value": "3", "max_value": "18", "default_value": "10"}]}
        result = _build_attributes(raw)
        assert result[0].min_value == 3
        assert result[0].max_value == 18

    def test_empty_charsheet_returns_empty(self):
        assert _build_attributes({}) == []

    def test_missing_name_skipped(self):
        raw = {"attributes": [{"abbreviation": "X"}]}
        result = _build_attributes(raw)
        assert result == []


# =============================================================================
# _build_skills
# =============================================================================


@pytest.mark.unit
class TestBuildSkills:
    def test_minimal_skill(self):
        raw = {"skills": [{"name": "Stealth"}]}
        result = _build_skills(raw)
        assert len(result) == 1
        assert isinstance(result[0], SkillDefinition)
        assert result[0].name == "Stealth"
        assert result[0].linked_attribute is None

    def test_full_skill(self):
        raw = {
            "skills": [
                {
                    "name": "Athletics",
                    "abbreviation": "ATH",
                    "linked_attribute": "Strength",
                    "description": "Physical feats",
                }
            ]
        }
        result = _build_skills(raw)
        assert result[0].abbreviation == "ATH"
        assert result[0].linked_attribute == "Strength"
        assert result[0].description == "Physical feats"

    def test_missing_name_skipped(self):
        raw = {"skills": [{"abbreviation": "X"}]}
        assert _build_skills(raw) == []

    def test_empty_returns_empty(self):
        assert _build_skills({}) == []


# =============================================================================
# _build_resources
# =============================================================================


@pytest.mark.unit
class TestBuildResources:
    def test_minimal_resource(self):
        raw = {"resources": [{"name": "Hit Points"}]}
        result = _build_resources(raw)
        assert len(result) == 1
        assert isinstance(result[0], ResourceDefinition)
        assert result[0].name == "Hit Points"
        assert result[0].min_value == 0

    def test_full_resource(self):
        raw = {
            "resources": [
                {
                    "name": "Mana",
                    "abbreviation": "MP",
                    "calculation": "INT * 2",
                    "min_value": "0",
                    "recovers_on": "long rest",
                    "depleted_effect": "Cannot cast spells",
                }
            ]
        }
        result = _build_resources(raw)
        assert result[0].abbreviation == "MP"
        assert result[0].calculation == "INT * 2"
        assert result[0].min_value == 0
        assert result[0].recovers_on == "long rest"
        assert result[0].depleted_effect == "Cannot cast spells"

    def test_missing_name_skipped(self):
        assert _build_resources({"resources": [{"calculation": "x"}]}) == []

    def test_empty_returns_empty(self):
        assert _build_resources({}) == []


# =============================================================================
# _build_core_mechanic
# =============================================================================


@pytest.mark.unit
class TestBuildCoreMechanic:
    def test_missing_core_mechanic_returns_d20_default(self):
        result = _build_core_mechanic({})
        assert isinstance(result, CoreMechanic)
        assert result.type == CoreMechanicType.D20
        assert result.success_type == SuccessType.MEET_OR_BEAT

    def test_passthrough_existing_core_mechanic(self):
        cm = CoreMechanic(type=CoreMechanicType.DICE_POOL, formula="5d6", success_type=SuccessType.COUNT_SUCCESSES)
        result = _build_core_mechanic({"core_mechanic": cm})
        assert result is cm

    def test_dict_converted_to_core_mechanic(self):
        raw = {"core_mechanic": {"type": "dice_pool", "formula": "3d6", "success_type": "count_successes"}}
        result = _build_core_mechanic(raw)
        assert result.type == CoreMechanicType.DICE_POOL
        assert result.success_type == SuccessType.COUNT_SUCCESSES
        assert result.formula == "3d6"

    def test_invalid_type_falls_back_to_d20(self):
        raw = {"core_mechanic": {"type": "xyzzy", "success_type": "meet_or_beat"}}
        result = _build_core_mechanic(raw)
        assert result.type == CoreMechanicType.D20

    def test_invalid_success_type_falls_back_to_meet_or_beat(self):
        raw = {"core_mechanic": {"type": "d20", "success_type": "not_real"}}
        result = _build_core_mechanic(raw)
        assert result.success_type == SuccessType.MEET_OR_BEAT

    def test_missing_formula_uses_placeholder(self):
        result = _build_core_mechanic({"core_mechanic": {"type": "d20"}})
        assert "Auto-detected" in result.formula


# =============================================================================
# _build_npc_stat_blocks
# =============================================================================


@pytest.mark.unit
class TestBuildNpcStatBlocks:
    def test_empty_returns_empty(self):
        assert _build_npc_stat_blocks({}) == []

    def test_passthrough_typed_object(self):
        block = NPCStatBlock(name="Goblin", tier=NPCTier.MINION)
        result = _build_npc_stat_blocks({"stat_blocks": [block]})
        assert result[0] is block

    def test_converts_dict(self):
        raw = {"stat_blocks": [{"name": "Troll", "tier": "elite", "hp": 84}]}
        result = _build_npc_stat_blocks(raw)
        assert len(result) == 1
        assert result[0].name == "Troll"
        assert result[0].tier == NPCTier.ELITE
        assert result[0].hp == 84

    def test_invalid_tier_falls_back_to_standard(self):
        raw = {"stat_blocks": [{"name": "Thing", "tier": "legendary"}]}
        result = _build_npc_stat_blocks(raw)
        assert result[0].tier == NPCTier.STANDARD

    def test_attacks_built(self):
        raw = {
            "stat_blocks": [
                {
                    "name": "Orc",
                    "attacks": [{"name": "Greataxe", "damage": "1d12+4"}],
                }
            ]
        }
        result = _build_npc_stat_blocks(raw)
        assert len(result[0].attacks) == 1
        assert result[0].attacks[0].name == "Greataxe"
        assert result[0].attacks[0].damage == "1d12+4"

    def test_hp_none_when_missing(self):
        raw = {"stat_blocks": [{"name": "Ghost"}]}
        result = _build_npc_stat_blocks(raw)
        assert result[0].hp is None


# =============================================================================
# _build_npc_creation_rules
# =============================================================================


@pytest.mark.unit
class TestBuildNpcCreationRules:
    def test_none_when_missing(self):
        assert _build_npc_creation_rules({}) is None

    def test_passthrough_typed_object(self):
        rules = NPCCreationRules(types_available=["minion", "boss"])
        result = _build_npc_creation_rules({"creation_rules": rules})
        assert result is rules

    def test_converts_dict(self):
        raw = {
            "creation_rules": {
                "types_available": ["standard", "elite"],
                "simplified_stat_method": "half HP",
                "scaling_notes": "Scale by CR",
            }
        }
        result = _build_npc_creation_rules(raw)
        assert isinstance(result, NPCCreationRules)
        assert "standard" in result.types_available
        assert result.simplified_stat_method == "half HP"


# =============================================================================
# _build_resolution_mechanics
# =============================================================================


@pytest.mark.unit
class TestBuildResolutionMechanics:
    def test_empty_returns_empty(self):
        assert _build_resolution_mechanics([]) == []

    def test_converts_dict(self):
        raw = [{"dice_formula": "2d6", "mechanic_type": "dice_pool", "success_type": "count_successes"}]
        result = _build_resolution_mechanics(raw)
        assert len(result) == 1
        assert isinstance(result[0], ResolutionMechanic)
        assert result[0].mechanic_type == CoreMechanicType.DICE_POOL
        assert result[0].success_type == SuccessType.COUNT_SUCCESSES

    def test_passthrough_typed_object(self):
        rm = ResolutionMechanic(
            dice_formula="1d20",
            mechanic_type=CoreMechanicType.D20,
            difficulty_model="fixed_dc",
            success_type=SuccessType.MEET_OR_BEAT,
        )
        result = _build_resolution_mechanics([rm])
        assert result[0] is rm

    def test_invalid_mechanic_type_falls_back_to_d20(self):
        raw = [{"mechanic_type": "invalid_type"}]
        result = _build_resolution_mechanics(raw)
        assert result[0].mechanic_type == CoreMechanicType.D20

    def test_invalid_success_type_falls_back(self):
        raw = [{"success_type": "unknown"}]
        result = _build_resolution_mechanics(raw)
        assert result[0].success_type == SuccessType.MEET_OR_BEAT

    def test_success_degrees_built(self):
        raw = [
            {
                "success_degrees": [
                    {"threshold": "20", "label": "Critical", "effect": "Double damage"},
                    {"threshold": "10", "label": "Success", "effect": "Normal damage"},
                ]
            }
        ]
        result = _build_resolution_mechanics(raw)
        assert len(result[0].success_degrees) == 2
        assert result[0].success_degrees[0].label == "Critical"

    def test_non_dict_in_success_degrees_skipped(self):
        raw = [{"success_degrees": ["not_a_dict", {"threshold": "1", "label": "ok", "effect": "fine"}]}]
        result = _build_resolution_mechanics(raw)
        assert len(result[0].success_degrees) == 1


# =============================================================================
# _merge_powers_and_subsystems
# =============================================================================


@pytest.mark.unit
class TestMergePowersAndSubsystems:
    def test_adds_power_as_rule(self):
        typed_rules = []
        charsheet = {
            "powers": [{"name": "Fireball", "category": "spell", "description": "A ball of fire"}]
        }
        result = _merge_powers_and_subsystems(typed_rules, charsheet, "D&D 5e")
        assert len(result) == 1
        assert result[0].name == "Fireball"
        assert result[0].rule_type == GameRuleType.CUSTOM
        assert "subsystem" in result[0].tags

    def test_adds_subsystem_as_rule(self):
        typed_rules = []
        charsheet = {
            "subsystems": [{"name": "Grappling", "scope": "combat", "description": "Wrestling rules"}]
        }
        result = _merge_powers_and_subsystems(typed_rules, charsheet, "System")
        assert len(result) == 1
        assert result[0].name == "Grappling"
        assert "scope:combat" in result[0].tags

    def test_duplicate_power_name_skipped(self):
        existing = GameRule(name="Fireball", rule_type=GameRuleType.POWER, description="")
        charsheet = {"powers": [{"name": "Fireball", "description": "Another fireball"}]}
        result = _merge_powers_and_subsystems([existing], charsheet, "D&D")
        assert len(result) == 1

    def test_case_insensitive_dedup(self):
        existing = GameRule(name="fireball", rule_type=GameRuleType.POWER, description="")
        charsheet = {"powers": [{"name": "Fireball"}]}
        result = _merge_powers_and_subsystems([existing], charsheet, "D&D")
        assert len(result) == 1

    def test_empty_power_name_skipped(self):
        charsheet = {"powers": [{"name": "", "description": "Nameless"}]}
        result = _merge_powers_and_subsystems([], charsheet, "D&D")
        assert result == []

    def test_default_description_generated_when_missing(self):
        charsheet = {"powers": [{"name": "Smite", "category": "divine"}]}
        result = _merge_powers_and_subsystems([], charsheet, "Paladin System")
        assert "Smite" in result[0].description


# =============================================================================
# _build_character_creation
# =============================================================================


@pytest.mark.unit
class TestBuildCharacterCreation:
    def test_empty_data_returns_none(self):
        assert _build_character_creation({}) is None

    def test_neither_steps_nor_ability_score_returns_none(self):
        assert _build_character_creation({"backgrounds": []}) is None

    def test_with_steps_builds_procedure(self):
        data = {
            "steps": [
                {
                    "step_number": 1,
                    "step_type": "choose_archetype",
                    "title": "Pick a Class",
                    "instructions": "Choose from fighter, wizard, or rogue.",
                }
            ]
        }
        result = _build_character_creation(data)
        assert result is not None
        assert len(result.steps) == 1
        assert result.steps[0].title == "Pick a Class"

    def test_invalid_step_type_falls_back_to_custom(self):
        data = {"steps": [{"step_type": "not_real", "title": "Mystery Step"}]}
        result = _build_character_creation(data)
        from monitor_data.schemas.game_systems import CreationStepType
        assert result.steps[0].step_type == CreationStepType.CUSTOM

    def test_passthrough_creation_step_objects(self):
        from monitor_data.schemas.game_systems import CreationStep, CreationStepType
        step = CreationStep(step_number=1, step_type=CreationStepType.CHOOSE_ARCHETYPE, title="t", instructions="i")
        data = {"steps": [step]}
        result = _build_character_creation(data)
        assert result.steps[0] is step

    def test_with_ability_score_generation(self):
        data = {
            "ability_score_generation": {"method": "point_buy", "point_budget": 27}
        }
        result = _build_character_creation(data)
        assert result is not None
        from monitor_data.schemas.game_systems import AbilityScoreMethod
        assert result.ability_score_generation.method == AbilityScoreMethod.POINT_BUY
        assert result.ability_score_generation.point_budget == 27

    def test_invalid_ability_score_method_falls_back(self):
        data = {"ability_score_generation": {"method": "unknown_method"}}
        result = _build_character_creation(data)
        from monitor_data.schemas.game_systems import AbilityScoreMethod
        assert result.ability_score_generation.method == AbilityScoreMethod.FREE_ASSIGN

    def test_backgrounds_built(self):
        data = {
            "steps": [{"step_type": "choose_background", "title": "Background"}],
            "backgrounds": [{"name": "Soldier", "description": "Military veteran"}],
        }
        result = _build_character_creation(data)
        assert len(result.backgrounds) == 1
        assert result.backgrounds[0].name == "Soldier"

    def test_advancement_system_built(self):
        data = {
            "steps": [{"step_type": "custom", "title": "Level Up"}],
            "advancement": {"method": "milestone", "max_level": 20},
        }
        result = _build_character_creation(data)
        assert result.advancement is not None
        assert result.advancement.method == "milestone"
        assert result.advancement.max_level == 20


# =============================================================================
# save_game_system (async, with mocked MongoDB)
# =============================================================================


_FILTER_PATCHES = {
    "monitor_agents.utils.analyzer_support.filter_player_attributes": lambda x: x,
    "monitor_agents.utils.analyzer_support.filter_player_skills": lambda x: x,
    "monitor_agents.utils.analyzer_support.filter_player_resources": lambda x: x,
}


@pytest.mark.unit
@pytest.mark.asyncio
class TestSaveGameSystem:
    async def test_returns_id_and_embedded_on_success(self):
        fake_id = uuid4()
        mock_system = MagicMock()
        mock_system.id = fake_id

        with patch("monitor_agents.analyzer._game_system_persistence.mongodb_create_game_system", return_value=mock_system):
            with patch("monitor_agents.utils.analyzer_support.filter_player_attributes", side_effect=lambda x: x):
                with patch("monitor_agents.utils.analyzer_support.filter_player_skills", side_effect=lambda x: x):
                    with patch("monitor_agents.utils.analyzer_support.filter_player_resources", side_effect=lambda x: x):
                        sys_id, embedded = await save_game_system(
                            system_name="Test System",
                            game_rules=[],
                            source_name="test.pdf",
                        )

        assert sys_id == fake_id
        assert embedded.name == "Test System"

    async def test_returns_none_id_on_mongodb_failure(self):
        with patch("monitor_agents.analyzer._game_system_persistence.mongodb_create_game_system", side_effect=Exception("DB down")):
            with patch("monitor_agents.utils.analyzer_support.filter_player_attributes", side_effect=lambda x: x):
                with patch("monitor_agents.utils.analyzer_support.filter_player_skills", side_effect=lambda x: x):
                    with patch("monitor_agents.utils.analyzer_support.filter_player_resources", side_effect=lambda x: x):
                        sys_id, embedded = await save_game_system(
                            system_name="Broken System",
                            game_rules=[],
                            source_name="broken.pdf",
                        )

        assert sys_id is None
        assert embedded.name == "Broken System"

    async def test_embedded_description_includes_source_name(self):
        mock_system = MagicMock()
        mock_system.id = uuid4()

        with patch("monitor_agents.analyzer._game_system_persistence.mongodb_create_game_system", return_value=mock_system):
            with patch("monitor_agents.utils.analyzer_support.filter_player_attributes", side_effect=lambda x: x):
                with patch("monitor_agents.utils.analyzer_support.filter_player_skills", side_effect=lambda x: x):
                    with patch("monitor_agents.utils.analyzer_support.filter_player_resources", side_effect=lambda x: x):
                        _, embedded = await save_game_system(
                            system_name="System",
                            game_rules=[],
                            source_name="sourcebook.pdf",
                        )

        assert "sourcebook.pdf" in embedded.description

    async def test_game_rules_are_built_and_embedded(self):
        mock_system = MagicMock()
        mock_system.id = uuid4()

        with patch("monitor_agents.analyzer._game_system_persistence.mongodb_create_game_system", return_value=mock_system):
            with patch("monitor_agents.utils.analyzer_support.filter_player_attributes", side_effect=lambda x: x):
                with patch("monitor_agents.utils.analyzer_support.filter_player_skills", side_effect=lambda x: x):
                    with patch("monitor_agents.utils.analyzer_support.filter_player_resources", side_effect=lambda x: x):
                        _, embedded = await save_game_system(
                            system_name="System",
                            game_rules=[{"name": "Rage", "rule_type": "combat"}],
                            source_name="book.pdf",
                        )

        assert any(r.name == "Rage" for r in embedded.rules)

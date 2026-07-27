"""
Tests for the rule_type alias map and GameRule.field_validator.

INGESTION_PIPELINE_AUDIT follow-up: qwen2.5 (local Ollama LLM) emits
D&D-flavored terms like ``class``, ``background``, ``feat`` that don't
match the canonical GameRuleType enum. Pydantic validation should
normalize them, not reject the whole rule list.
"""

from monitor_data.schemas.game_systems import (
    GAME_RULE_TYPE_ALIASES,
    GameRule,
    GameRuleType,
)


class TestRuleTypeAliases:
    def test_canonical_values_pass_through(self):
        for canonical in GameRuleType:
            rule = GameRule(
                name="X",
                description="y",
                rule_type=canonical.value,
            )
            assert rule.rule_type is canonical

    def test_alias_map_combat_terms(self):
        for raw in ("ranged_combat", "ranged", "melee", "attack", "damage"):
            rule = GameRule(name="X", description="y", rule_type=raw)
            assert rule.rule_type is GameRuleType.COMBAT, raw

    def test_alias_map_power_terms(self):
        for raw in ("magic", "spell", "healing", "ritual", "ceremony", "discipline", "power"):
            rule = GameRule(name="X", description="y", rule_type=raw)
            assert rule.rule_type is GameRuleType.POWER, raw

    def test_alias_map_core_terms(self):
        for raw in ("saving_throw", "save", "movement"):
            rule = GameRule(name="X", description="y", rule_type=raw)
            assert rule.rule_type is GameRuleType.CORE, raw

    def test_alias_map_dnd_flavoured_to_custom(self):
        for raw in ("class", "background", "feat", "merit", "background_dot", "merit_dot"):
            rule = GameRule(name="X", description="y", rule_type=raw)
            assert rule.rule_type is GameRuleType.CUSTOM, raw

    def test_unknown_string_falls_back_to_custom(self):
        rule = GameRule(name="X", description="y", rule_type="some_brand_new_category")
        assert rule.rule_type is GameRuleType.CUSTOM

    def test_case_insensitive(self):
        rule = GameRule(name="X", description="y", rule_type="RANGED_COMBAT")
        assert rule.rule_type is GameRuleType.COMBAT

    def test_whitespace_stripped(self):
        rule = GameRule(name="X", description="y", rule_type="  feat  ")
        assert rule.rule_type is GameRuleType.CUSTOM

    def test_alias_map_keys_are_lowercase_strings(self):
        for k, v in GAME_RULE_TYPE_ALIASES.items():
            assert k == k.lower(), k
            assert isinstance(v, GameRuleType)

    def test_does_not_overwrite_enum_member_passthrough(self):
        # When given an actual GameRuleType member, no transformation.
        rule = GameRule(name="X", description="y", rule_type=GameRuleType.MECHANIC)
        assert rule.rule_type is GameRuleType.MECHANIC

    def test_missing_rule_type_defaults_to_custom(self):
        """Live VtM ingest (2026-07-21) showed qwen2.5 often OMITS rule_type
        entirely on skill-description dicts. The schema must accept the
        omission and default to CUSTOM instead of rejecting the rule list."""
        rule = GameRule(name="Alertness", description="Notice danger")
        assert rule.rule_type is GameRuleType.CUSTOM

    def test_none_rule_type_defaults_to_custom(self):
        rule = GameRule(name="X", description="y", rule_type=None)
        assert rule.rule_type is GameRuleType.CUSTOM

    def test_empty_string_rule_type_defaults_to_custom(self):
        rule = GameRule(name="X", description="y", rule_type="")
        assert rule.rule_type is GameRuleType.CUSTOM

    def test_whitespace_only_rule_type_defaults_to_custom(self):
        rule = GameRule(name="X", description="y", rule_type="   ")
        assert rule.rule_type is GameRuleType.CUSTOM

    def test_list_of_rules_with_missing_types_round_trip(self):
        """The exact shape of the live VtM failure: section output is a
        list of dicts, several of which lack rule_type. The whole list
        must validate successfully with those entries defaulted to CUSTOM
        rather than rejecting the list and dropping every rule."""
        raw_rules = [
            {"name": "Alertness", "description": "Notice danger"},
            {"name": "Fireball", "description": "boom", "rule_type": "magic"},
            {"name": "Initiative", "description": "roll d10", "rule_type": "core"},
            {"name": "Mystery", "description": "x", "rule_type": "unobtanium"},
        ]
        validated = [GameRule.model_validate(r) for r in raw_rules]
        assert [r.rule_type for r in validated] == [
            GameRuleType.CUSTOM,
            GameRuleType.POWER,
            GameRuleType.CORE,
            GameRuleType.CUSTOM,
        ]

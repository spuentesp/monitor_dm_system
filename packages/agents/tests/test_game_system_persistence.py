import pytest
from monitor_data.schemas.game_systems import ConditionDefinition, SceneryRule
from monitor_agents.analyzer._game_system_persistence import _build_conditions, _build_scenery_rules


@pytest.mark.unit
def test_build_conditions() -> None:
    raw_data = {
        "conditions": [
            {
                "name": "poisoned",
                "description": "Taking toxic damage",
                "roll_modifier": "-2",
                "roll_mode_override": "disadvantage"
            },
            {
                "name": "blinded",
                "roll_modifier": 0
            }
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
def test_build_scenery_rules() -> None:
    raw_data = {
        "scenery_rules": [
            {
                "keyword": "high ground",
                "trigger_verbs": ["attack", "shoot"],
                "roll_modifier": "2",
                "roll_mode_override": "advantage",
                "reason_text": "Elevation advantage"
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

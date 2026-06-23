import pytest
from typing import Any, Dict
from monitor_agents.game_system._types import build_system_data
from monitor_agents.game_system._tracks_conditions import evaluate_scenery_and_conditions


@pytest.fixture
def mock_system_doc() -> Dict[str, Any]:
    return {
        "conditions": [
            {
                "name": "poisoned",
                "roll_modifier": -2,
                "roll_mode_override": "disadvantage",
            },
            {
                "name": "blessed",
                "roll_modifier": 1,
                "roll_mode_override": "advantage",
            },
        ],
        "scenery_rules": [
            {
                "keyword": "slippery",
                "trigger_verbs": ["run", "dodge"],
                "roll_modifier": -1,
                "roll_mode_override": "disadvantage",
                "reason_text": "You slip on the wet floor",
            },
            {
                "keyword": "high ground",
                "trigger_verbs": ["shoot", "attack"],
                "roll_modifier": 2,
                "roll_mode_override": "advantage",
                "reason_text": "You have the high ground",
            },
        ],
    }


def test_evaluate_scenery_and_conditions_no_matches(mock_system_doc):
    sd = build_system_data(mock_system_doc)
    context = {"entities": []}
    result = evaluate_scenery_and_conditions(sd, context, "I just stand there")

    assert result["total_modifier"] == 0
    assert result["roll_mode"] == "normal"
    assert result["has_advantage"] is False
    assert result["has_disadvantage"] is False


def test_evaluate_scenery_and_conditions_actor_condition(mock_system_doc):
    sd = build_system_data(mock_system_doc)
    context = {
        "entities": [
            {"entity_type": "character", "properties": {"active_conditions": ["poisoned"]}}
        ]
    }
    result = evaluate_scenery_and_conditions(sd, context, "I attack")

    assert result["cond_modifier"] == -2
    assert result["total_modifier"] == -2
    assert result["roll_mode"] == "disadvantage"
    assert result["has_disadvantage"] is True


def test_evaluate_scenery_and_conditions_location_scenery(mock_system_doc):
    sd = build_system_data(mock_system_doc)
    context = {"entities": [{"entity_type": "location", "properties": {"tags": ["slippery"]}}]}
    result = evaluate_scenery_and_conditions(sd, context, "I try to dodge")

    assert result["scenery_modifier"] == -1
    assert result["total_modifier"] == -1
    assert result["roll_mode"] == "disadvantage"
    assert result["reasons"] == ["You slip on the wet floor"]


def test_evaluate_scenery_and_conditions_combined(mock_system_doc):
    sd = build_system_data(mock_system_doc)
    context = {
        "entities": [
            {"entity_type": "character", "properties": {"active_conditions": ["blessed"]}},
            {"entity_type": "location", "properties": {"tags": ["slippery"]}},
        ]
    }
    result = evaluate_scenery_and_conditions(sd, context, "I run away")

    # Blessed (+1, adv), Slippery (-1, disadv)
    # They should cancel out roll mode to normal.
    assert result["total_modifier"] == 0
    assert result["cond_modifier"] == 1
    assert result["scenery_modifier"] == -1
    assert result["roll_mode"] == "normal"
    assert result["has_advantage"] is True
    assert result["has_disadvantage"] is True

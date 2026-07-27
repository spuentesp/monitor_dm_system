from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

from monitor_agents.game_system._tracks_conditions import evaluate_scenery_and_conditions
from monitor_agents.game_system._types import build_system_data


# Embeddings are unavailable in the hermetic env. The scenery/condition
# matcher now delegates ranking to RetrievalService.nearest. We stub that
# service so the test pins *which rule fires*: a candidate scores 1.0 when
# any of its words is a substring of the user input, 0.0 otherwise — the same
# deterministic signal the legacy keyword behaviour gave these fixtures.
class _StubRetriever:
    def __init__(self, user_input: str) -> None:
        self._text = user_input.lower()

    async def nearest(self, query, candidates, *, top_k=1, candidates_key=None):
        from monitor_data.retrieval import Scored

        out = []
        for i, cand in enumerate(candidates):
            words = str(cand).lower().split()
            score = 1.0 if any(w in self._text for w in words) else 0.0
            out.append(Scored(candidate=cand, index=i, score=score))
        out.sort(key=lambda s: s.score, reverse=True)
        return out[: max(1, top_k)]


@pytest.fixture
def mock_system_doc() -> dict[str, Any]:
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


@contextmanager
def _patch_nearest(text: str):
    """Stub ``default_retrieval_service`` so the matcher's nearest() is scripted.

    The matcher lazy-imports ``default_retrieval_service`` from
    ``monitor_data.retrieval`` inside the function, so patching the source
    binding replaces what it resolves at call time.
    """
    with patch(
        "monitor_data.retrieval.default_retrieval_service",
        return_value=_StubRetriever(text),
    ):
        yield


@pytest.mark.asyncio
async def test_stackable_condition_retriggers_while_active():
    """A stackable condition already active can still re-trigger; a
    non-stackable one already active cannot (regression for the dead
    ``stackable`` filter clause)."""
    from monitor_agents.game_system._tracks_conditions import check_condition_triggers

    sd = build_system_data(
        {
            "conditions": [
                {"name": "bleeding", "stackable": True},
                {"name": "poisoned", "stackable": False},
            ],
            "scenery_rules": [],
        }
    )
    context = {"active_conditions": ["bleeding", "poisoned"]}
    with _patch_nearest("bleeding poisoned everywhere"):
        triggered = await check_condition_triggers(sd, "bleeding poisoned everywhere", context)

    names = {c["name"] for c in triggered}
    assert "bleeding" in names  # stackable → re-fires
    assert "poisoned" not in names  # non-stackable + active → suppressed


@pytest.mark.asyncio
async def test_evaluate_scenery_and_conditions_no_matches(mock_system_doc):
    sd = build_system_data(mock_system_doc)
    context = {"entities": []}
    with _patch_nearest("I just stand there"):
        result = await evaluate_scenery_and_conditions(sd, context, "I just stand there")

    assert result["total_modifier"] == 0
    assert result["roll_mode"] == "normal"
    assert result["has_advantage"] is False
    assert result["has_disadvantage"] is False


@pytest.mark.asyncio
async def test_evaluate_scenery_and_conditions_actor_condition(mock_system_doc):
    sd = build_system_data(mock_system_doc)
    context = {"entities": [{"entity_type": "character", "properties": {"active_conditions": ["poisoned"]}}]}
    with _patch_nearest("I attack"):
        result = await evaluate_scenery_and_conditions(sd, context, "I attack")

    assert result["cond_modifier"] == -2
    assert result["total_modifier"] == -2
    assert result["roll_mode"] == "disadvantage"
    assert result["has_disadvantage"] is True


@pytest.mark.asyncio
async def test_evaluate_scenery_and_conditions_location_scenery(mock_system_doc):
    sd = build_system_data(mock_system_doc)
    context = {"entities": [{"entity_type": "location", "properties": {"tags": ["slippery"]}}]}
    with _patch_nearest("I try to dodge"):
        result = await evaluate_scenery_and_conditions(sd, context, "I try to dodge")

    assert result["scenery_modifier"] == -1
    assert result["total_modifier"] == -1
    assert result["roll_mode"] == "disadvantage"
    assert result["reasons"] == ["You slip on the wet floor"]


@pytest.mark.asyncio
async def test_evaluate_scenery_and_conditions_combined(mock_system_doc):
    sd = build_system_data(mock_system_doc)
    context = {
        "entities": [
            {"entity_type": "character", "properties": {"active_conditions": ["blessed"]}},
            {"entity_type": "location", "properties": {"tags": ["slippery"]}},
        ]
    }
    with _patch_nearest("I run away"):
        result = await evaluate_scenery_and_conditions(sd, context, "I run away")

    # Blessed (+1, adv), Slippery (-1, disadv) — roll mode cancels to normal.
    assert result["total_modifier"] == 0
    assert result["cond_modifier"] == 1
    assert result["scenery_modifier"] == -1
    assert result["roll_mode"] == "normal"
    assert result["has_advantage"] is True
    assert result["has_disadvantage"] is True

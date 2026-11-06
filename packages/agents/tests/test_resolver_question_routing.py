"""The GM decides whether a question is a world truth, a lookup or an action.

Regex routing is only a fallback for when no real GM verdict exists.
"""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents import resolver as rmod
from monitor_agents.gm_awareness import ActionType, CausalityAction, IntentType, RollNecessity
from monitor_agents.gm_tools.contracts import GMVerdict

UNIVERSE = "11111111-1111-4111-8111-111111111111"


def _verdict(intent: IntentType, action: ActionType = ActionType.NONE) -> GMVerdict:
    return GMVerdict(
        intent_type=intent,
        action_type=action,
        roll_necessity=RollNecessity.PROPOSE_ROLL,
        causality_action=CausalityAction.ACCEPT,
        declares_outcome=False,
        narrative_draft="A draft that knows nothing about the answer.",
    )


def _resolver(verdict: GMVerdict | None) -> rmod.Resolver:
    gm = types.SimpleNamespace(decide=AsyncMock(return_value=verdict))
    return rmod.Resolver(gm_agent=gm)


class _Retrieval:
    def __init__(self) -> None:
        self.filters: list[Any] = []

    async def retrieve(self, _collection: str, _query: str, *, filters: Any = None, limit: int = 10) -> list[Any]:
        self.filters.append(filters)
        return [types.SimpleNamespace(payload={"name": "The Beast", "text": "Inner hunger."}, score=0.9)]


@pytest.fixture(autouse=True)
def _generic_stat():
    with patch.object(rmod, "_infer_generic_stat", AsyncMock(return_value="Dexterity")):
        yield


@pytest.fixture
def retrieval():
    fake = _Retrieval()
    with patch("monitor_data.retrieval.service.RetrievalService", lambda: fake):
        yield fake


async def _resolve(resolver: rmod.Resolver, text: str, play_mode: str = "dice_standard", **ctx: Any) -> Any:
    return await resolver.resolve_turn("scene", text, {"entities": [], **ctx}, play_mode=play_mode)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "intent", "action"),
    [
        ("Can I pick the lock?", IntentType.ACTION, ActionType.STEALTH),
        ("Do you know the way, friend?", IntentType.DIALOGUE, ActionType.DIALOGUE),
    ],
)
async def test_gm_keeps_yes_no_shaped_actions_away_from_the_oracle(
    text: str, intent: IntentType, action: ActionType
) -> None:
    result, _ = await _resolve(_resolver(_verdict(intent, action)), text)
    assert result["resolution_type"] == "propose_roll"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    ["Tell me about your brother, I say to the barkeep", "Explain to the guard that I'm a merchant"],
)
async def test_gm_keeps_dialogue_away_from_lookup(text: str, retrieval: _Retrieval) -> None:
    resolver = _resolver(_verdict(IntentType.DIALOGUE, ActionType.DIALOGUE))
    result, _ = await _resolve(resolver, text, universe_id=UNIVERSE)
    assert result["resolution_type"] != "rag_lookup"
    assert retrieval.filters == []


@pytest.mark.asyncio
async def test_gm_query_goes_to_the_oracle_and_drops_the_draft() -> None:
    result, verdict = await _resolve(_resolver(_verdict(IntentType.QUERY)), "Is the door locked?")
    assert result["resolution_type"] == "oracle"
    # The narrator must narrate the oracle's answer, not a draft written without it.
    assert verdict is None


@pytest.mark.asyncio
async def test_gm_lookup_is_scoped_to_the_universe(retrieval: _Retrieval) -> None:
    result, verdict = await _resolve(_resolver(_verdict(IntentType.LOOKUP)), "What is the Beast?", universe_id=UNIVERSE)
    assert result["resolution_type"] == "rag_lookup"
    assert verdict is None
    assert retrieval.filters == [{"universe_id": UNIVERSE}] * 3


@pytest.mark.asyncio
async def test_lookup_never_searches_across_universes(retrieval: _Retrieval) -> None:
    result, _ = await _resolve(_resolver(_verdict(IntentType.LOOKUP)), "What is the Beast?")
    assert result["resolution_type"] != "rag_lookup"
    assert retrieval.filters == []


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", [None, _verdict(IntentType.ACTION)])
async def test_regex_routes_questions_only_without_a_real_verdict(verdict: GMVerdict | None) -> None:
    result, _ = await _resolve(_resolver(verdict), "Is the door locked?")
    assert result["resolution_type"] == "oracle"


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Is the door locked?", "Can I pick the lock?", "Explain the rules to him"])
async def test_narrative_mode_never_rolls_or_looks_up(text: str, retrieval: _Retrieval) -> None:
    resolver = _resolver(_verdict(IntentType.QUERY))
    result, _ = await _resolve(resolver, text, play_mode="narrative", universe_id=UNIVERSE)
    assert result["resolution_type"] == "narrative"
    assert retrieval.filters == []
    resolver._gm_agent.decide.assert_not_awaited()


def test_narrator_receives_the_lookup_answer() -> None:
    from monitor_agents.narrator.agent import Narrator

    narrator = Narrator.__new__(Narrator)
    summary = narrator._format_resolution({"resolution_type": "rag_lookup", "answer": "The Beast is inner hunger."})
    assert "The Beast is inner hunger." in summary

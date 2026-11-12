"""Tests for encounter difficulty estimation (CF-13 / G06).

The estimator is pure arithmetic, so it is tested as arithmetic: a table
of known encounters with the label they must earn, plus the cases where
the honest answer is "we cannot tell you".

Run:
    uv run pytest packages/agents/tests/test_encounter_difficulty.py -q
"""

from __future__ import annotations

import pytest
from monitor_agents.encounter_difficulty import EncounterDifficultyAgent
from monitor_agents.game_system.difficulty import (
    Foe,
    PartyMember,
    estimate_difficulty,
)


def _party(size: int, level: int = 3, hp: int = 24) -> list[PartyMember]:
    return [PartyMember(name=f"PC {i}", level=level, hit_points=hp) for i in range(size)]


class TestEstimateDifficulty:
    def test_a_single_goblin_against_four_heroes_is_trivial(self) -> None:
        estimate = estimate_difficulty([Foe("Goblin", hit_points=7)], _party(4))

        assert estimate.label == "trivial"
        assert estimate.rated is True
        assert estimate.basis == "generic"

    def test_eight_goblins_against_four_heroes_are_hard(self) -> None:
        estimate = estimate_difficulty([Foe("Goblin", count=8, hit_points=7)], _party(4))

        assert estimate.label == "hard"
        # Eight foes carry the size multiplier (3x), not a straight sum.
        assert estimate.details["multiplier"] == 3.0
        assert estimate.threat == 168.0
        assert estimate.ratio == 1.75

    def test_twelve_goblins_against_two_heroes_are_deadly(self) -> None:
        estimate = estimate_difficulty([Foe("Goblin", count=12, hit_points=7)], _party(2))

        assert estimate.label == "deadly"
        assert estimate.details["multiplier"] == 4.0

    def test_the_party_budget_is_the_sum_of_its_members(self) -> None:
        estimate = estimate_difficulty([Foe("Goblin", hit_points=7)], _party(4))

        assert estimate.party_budget == 96.0
        assert estimate.ratio == pytest.approx(7.0 / 96.0, abs=1e-3)

    def test_a_level_without_hit_points_uses_the_level_budget(self) -> None:
        party = [PartyMember(name="Mira", level=3)]
        estimate = estimate_difficulty([Foe("Ogre", hit_points=59)], party)

        assert estimate.party_budget == 75.0

    def test_a_member_with_nothing_known_still_counts(self) -> None:
        party = [PartyMember(name="Mystery"), PartyMember(name="Mystery 2")]
        estimate = estimate_difficulty([Foe("Ogre", hit_points=59)], party)

        assert estimate.party_budget == 60.0

    def test_more_heroes_make_the_same_encounter_easier(self) -> None:
        small = estimate_difficulty([Foe("Ogre", hit_points=59)], _party(2))
        large = estimate_difficulty([Foe("Ogre", hit_points=59)], _party(6))

        assert large.label != "deadly"
        assert large.ratio < small.ratio

    def test_an_empty_party_is_unrated(self) -> None:
        estimate = estimate_difficulty([Foe("Goblin", hit_points=7)], [])

        assert estimate.label == "unrated"
        assert estimate.rated is False

    def test_an_empty_encounter_is_unrated(self) -> None:
        estimate = estimate_difficulty([], _party(4))

        assert estimate.label == "unrated"

    def test_a_party_with_no_resources_is_unrated(self) -> None:
        party = [PartyMember(name="Ghost", level=0, hit_points=0)]
        estimate = estimate_difficulty([Foe("Goblin", hit_points=7)], party)

        assert estimate.label == "unrated"
        assert "resources are unknown" in estimate.rationale

    def test_a_foe_with_no_numbers_still_costs_something(self) -> None:
        estimate = estimate_difficulty([Foe("Mystery")], _party(4))

        assert estimate.threat > 0

    def test_the_estimate_is_deterministic(self) -> None:
        first = estimate_difficulty([Foe("Goblin", count=3, hit_points=7)], _party(4))
        second = estimate_difficulty([Foe("Goblin", count=3, hit_points=7)], _party(4))

        assert first == second

    def test_the_rationale_shows_the_arithmetic(self) -> None:
        estimate = estimate_difficulty([Foe("Goblin", count=8, hit_points=7)], _party(4))

        assert "level-3 party of 4" in estimate.rationale
        assert "168 threat" in estimate.rationale
        assert "96 party resources" in estimate.rationale


class TestSystemRules:
    """A game system may bring its own difficulty rules."""

    def test_a_system_table_wins_over_the_generic_one(self) -> None:
        system = {
            "difficulty": {
                "thresholds": [("trivial", 0.01), ("easy", 0.02), ("moderate", 0.03)],
                "encounter_multipliers": {1: 10.0},
                "threat_weight_per_hp": 2.0,
            }
        }
        estimate = estimate_difficulty([Foe("Goblin", hit_points=7)], _party(4), system)

        assert estimate.basis == "system_table"
        # 7 HP × 2 weight × 10 multiplier = 140 against a budget of 96.
        assert estimate.threat == 140.0
        assert estimate.label == "moderate"

    def test_a_system_without_difficulty_uses_the_generic_convention(self) -> None:
        estimate = estimate_difficulty(
            [Foe("Goblin", hit_points=7)], _party(4), {"resources": []}
        )

        assert estimate.basis == "generic"
        assert estimate.label == "trivial"


class TestAgentResolution:
    """The agent fills in the numbers the caller left out."""

    async def test_numbers_given_by_the_caller_are_used(self) -> None:
        agent = EncounterDifficultyAgent()

        estimate = await agent.estimate(
            universe_id=__import__("uuid").uuid4(),
            foes=[{"name": "Goblin", "count": 12, "hit_points": 7}],
            party=[{"name": "Mira", "level": 3, "hit_points": 24}] * 2,
        )

        assert estimate.label == "deadly"
        assert estimate.party_budget == 48.0

    async def test_a_character_sheet_fills_in_the_hit_points(self, monkeypatch) -> None:
        from monitor_agents.encounter_difficulty import EncounterDifficultyAgent as Agent

        async def _sheets(self, character_id: str) -> dict:
            return {
                "entity_id": character_id,
                "total_level": 3,
                "resources": {"Health": {"current": 18, "max": 24}},
            }

        monkeypatch.setattr(Agent, "_fetch_sheet", _sheets)
        agent = Agent()

        estimate = await agent.estimate(
            universe_id=__import__("uuid").uuid4(),
            foes=[{"name": "Goblin", "count": 8, "hit_points": 7}],
            party=[{"name": "Mira", "character_id": "char-1"}],
        )

        assert estimate.party_budget == 24.0
        assert estimate.details  # the estimate carries its working

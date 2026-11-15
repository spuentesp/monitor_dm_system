"""
Basic workings — the at-the-table combat tracker (CF-9 / G01).

The combat tracker is the surface a GM touches most often mid-session, and
it is the one GM feature with *no* LLM in its state path: HP math, initiative
order and round advance are plain code. That makes it the right place to
pin "the basics work" without any model in the loop.

The flow exercised here is the real one: start → initiative → damage → round
→ end, with the state living in the shipped Mongo tools.

Use Cases: CF-9 (G01)
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from monitor_agents.combat import CombatAgent
from monitor_data.schemas.base import CombatSide, CombatStatus
from monitor_data.schemas.combat import (
    CombatEnd,
    CombatNextRound,
    CombatSetInitiative,
    CombatStart,
    CombatUpdateCombatant,
)
from tests.behavior._hermetic_stack import HermeticStack


def _combatant(name: str, side: CombatSide, hp: int) -> dict[str, object]:
    return {"name": name, "side": side.value, "hp": hp, "max_hp": hp}


@pytest.fixture
def universe_id() -> UUID:
    return uuid4()


@pytest.fixture
def session_id() -> str:
    return "sess-basic-1"


@pytest.fixture
async def encounter(
    hermetic: HermeticStack, universe_id: UUID, session_id: str
) -> tuple[CombatAgent, UUID]:
    """A started encounter with one PC and one enemy."""
    agent = CombatAgent()
    state = await agent.start_encounter(
        CombatStart(
            universe_id=universe_id,
            session_id=session_id,
            combatants=[
                _combatant("Mira", CombatSide.PC, 24),  # type: ignore[arg-type]
                _combatant("Goblin", CombatSide.ENEMY, 7),  # type: ignore[arg-type]
            ],
        )
    )
    return agent, state


class TestStart:
    async def test_encounter_starts_in_initiative(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str
    ) -> None:
        agent = CombatAgent()
        state = await agent.start_encounter(
            CombatStart(
                universe_id=universe_id,
                session_id=session_id,
                combatants=[
                    _combatant("Mira", CombatSide.PC, 24),  # type: ignore[arg-type]
                    _combatant("Goblin", CombatSide.ENEMY, 7),  # type: ignore[arg-type]
                ],
            )
        )

        assert state.status is CombatStatus.INITIATIVE
        assert state.round == 1
        assert [c.name for c in state.combatants] == ["Mira", "Goblin"]
        assert state.combatants[0].hp == 24

    async def test_hp_above_max_is_refused(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str
    ) -> None:
        agent = CombatAgent()
        with pytest.raises(ValueError, match="cannot exceed max_hp"):
            await agent.start_encounter(
                CombatStart(
                    universe_id=universe_id,
                    session_id=session_id,
                    combatants=[{"name": "Mira", "side": "pc", "hp": 30, "max_hp": 20}],
                )
            )

    async def test_state_survives_a_fresh_agent(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        """The encounter is store-backed, not agent-backed."""
        _, state = encounter
        reloaded = await CombatAgent().get_state(universe_id, session_id)

        assert reloaded is not None
        assert [c.name for c in reloaded.combatants] == [c.name for c in state.combatants]

    async def test_missing_encounter_is_none(
        self, hermetic: HermeticStack, universe_id: UUID
    ) -> None:
        assert await CombatAgent().get_state(universe_id, "no-such-session") is None


class TestInitiative:
    async def test_turn_order_follows_the_rolls(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, state = encounter
        mira = state.combatants[0]
        goblin = state.combatants[1]

        updated = await agent.set_initiative(
            CombatSetInitiative(
                universe_id=universe_id,
                session_id=session_id,
                entries=[
                    {"combatant_id": mira.id, "initiative": 12},
                    {"combatant_id": goblin.id, "initiative": 19},
                ],
            )
        )

        assert updated.status is CombatStatus.ACTIVE
        assert updated.turn_order == [goblin.id, mira.id]

    async def test_ties_break_deterministically(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, state = encounter
        mira = state.combatants[0]
        goblin = state.combatants[1]

        updated = await agent.set_initiative(
            CombatSetInitiative(
                universe_id=universe_id,
                session_id=session_id,
                entries=[
                    {"combatant_id": mira.id, "initiative": 15},
                    {"combatant_id": goblin.id, "initiative": 15, "tiebreak": 2},
                ],
            )
        )

        # The tie-break score wins the tie.
        assert updated.turn_order == [goblin.id, mira.id]

    async def test_unknown_combatant_is_refused(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, _ = encounter
        with pytest.raises(ValueError, match="Unknown combatant"):
            await agent.set_initiative(
                CombatSetInitiative(
                    universe_id=universe_id,
                    session_id=session_id,
                    entries=[{"combatant_id": uuid4(), "initiative": 10}],
                )
            )


class TestDamage:
    async def test_damage_reduces_hp(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, state = encounter
        goblin = state.combatants[1]

        updated = await agent.update_combatant(
            CombatUpdateCombatant(
                universe_id=universe_id,
                session_id=session_id,
                combatant_id=goblin.id,
                hp_delta=-3,
            )
        )

        target = next(c for c in updated.combatants if c.id == goblin.id)
        assert target.hp == 4

    async def test_temp_hp_absorbs_damage_first(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, state = encounter
        goblin = state.combatants[1]

        with_temp = await agent.update_combatant(
            CombatUpdateCombatant(
                universe_id=universe_id,
                session_id=session_id,
                combatant_id=goblin.id,
                temp_hp=5,
            )
        )
        assert next(c for c in with_temp.combatants if c.id == goblin.id).temp_hp == 5

        damaged = await agent.update_combatant(
            CombatUpdateCombatant(
                universe_id=universe_id,
                session_id=session_id,
                combatant_id=goblin.id,
                hp_delta=-3,
            )
        )
        target = next(c for c in damaged.combatants if c.id == goblin.id)
        assert target.temp_hp == 2
        assert target.hp == 7  # the goblin's own HP was untouched

    async def test_hp_never_goes_below_zero(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, state = encounter
        goblin = state.combatants[1]

        updated = await agent.update_combatant(
            CombatUpdateCombatant(
                universe_id=universe_id,
                session_id=session_id,
                combatant_id=goblin.id,
                hp_delta=-99,
            )
        )
        target = next(c for c in updated.combatants if c.id == goblin.id)
        assert target.hp == 0

    async def test_conditions_are_added_and_removed(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, state = encounter
        goblin = state.combatants[1]

        poisoned = await agent.update_combatant(
            CombatUpdateCombatant(
                universe_id=universe_id,
                session_id=session_id,
                combatant_id=goblin.id,
                conditions_add=["poisoned"],
            )
        )
        assert "poisoned" in next(c for c in poisoned.combatants if c.id == goblin.id).conditions

        cured = await agent.update_combatant(
            CombatUpdateCombatant(
                universe_id=universe_id,
                session_id=session_id,
                combatant_id=goblin.id,
                conditions_remove=["poisoned"],
            )
        )
        assert "poisoned" not in next(c for c in cured.combatants if c.id == goblin.id).conditions

    async def test_unknown_combatant_is_refused(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, _ = encounter
        with pytest.raises(ValueError, match="not found in encounter"):
            await agent.update_combatant(
                CombatUpdateCombatant(
                    universe_id=universe_id,
                    session_id=session_id,
                    combatant_id=uuid4(),
                    hp_delta=-1,
                )
            )


class TestRoundsAndEnd:
    async def test_round_advances(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, _ = encounter
        updated = await agent.next_round(
            CombatNextRound(universe_id=universe_id, session_id=session_id)
        )
        assert updated.round == 2

    async def test_ending_resolves_the_encounter(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, _ = encounter
        ended = await agent.end_encounter(CombatEnd(universe_id=universe_id, session_id=session_id))
        assert ended.status is CombatStatus.RESOLVED
        assert ended.ended_at is not None

    async def test_a_resolved_encounter_does_not_advance(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        agent, _ = encounter
        await agent.end_encounter(CombatEnd(universe_id=universe_id, session_id=session_id))

        with pytest.raises(ValueError, match="already ended"):
            await agent.next_round(CombatNextRound(universe_id=universe_id, session_id=session_id))

    async def test_the_encounter_writes_nothing_to_canon(
        self, hermetic: HermeticStack, universe_id: UUID, session_id: str, encounter: tuple
    ) -> None:
        """Combat is ephemeral: no proposal, no canon write, ever."""
        agent, state = encounter
        goblin = state.combatants[1]
        await agent.update_combatant(
            CombatUpdateCombatant(
                universe_id=universe_id,
                session_id=session_id,
                combatant_id=goblin.id,
                hp_delta=-7,
                dead=True,
            )
        )
        await agent.end_encounter(CombatEnd(universe_id=universe_id, session_id=session_id))

        assert hermetic.calls_to("mongodb_create_proposed_change") == []
        assert hermetic.collection("proposed_changes").count_documents({}) == 0

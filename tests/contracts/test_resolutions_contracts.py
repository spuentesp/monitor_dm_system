"""Contract tests for the Resolution schemas (DL-24).

Verifies that resolutions Pydantic models:
- instantiate with valid data,
- enforce required fields and length / range constraints,
- enforce enum membership for action / resolution / success / effect types.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.resolutions import (
    ActionType,
    CardDraw,
    ContestedRoll,
    Effect,
    EffectType,
    Mechanics,
    Modifier,
    ResolutionCreate,
    ResolutionFilter,
    ResolutionListResponse,
    ResolutionResponse,
    ResolutionType,
    ResolutionUpdate,
    RollResult,
    SuccessLevel,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# =============================================================================
# Enums
# =============================================================================


class TestActionType:
    def test_values(self):
        expected = {"combat", "skill", "social", "exploration", "magic", "other"}
        actual = {a.value for a in ActionType}
        assert expected.issubset(actual)


class TestResolutionType:
    def test_values(self):
        expected = {
            "dice",
            "card",
            "narrative",
            "deterministic",
            "contested",
            "forced_narrative",
        }
        actual = {r.value for r in ResolutionType}
        assert expected.issubset(actual)


class TestSuccessLevel:
    def test_values(self):
        assert SuccessLevel.CRITICAL_SUCCESS.value == "critical_success"
        assert SuccessLevel.SUCCESS.value == "success"
        assert SuccessLevel.PARTIAL_SUCCESS.value == "partial_success"
        assert SuccessLevel.FAILURE.value == "failure"
        assert SuccessLevel.CRITICAL_FAILURE.value == "critical_failure"


class TestEffectType:
    def test_values(self):
        expected = {
            "damage",
            "healing",
            "condition",
            "buff",
            "debuff",
            "resource_change",
            "stat_change",
            "position_change",
            "other",
        }
        actual = {e.value for e in EffectType}
        assert expected.issubset(actual)


# =============================================================================
# Modifier
# =============================================================================


class TestModifier:
    def test_minimal(self):
        m = Modifier(source="Bless spell", value=2, reason="Bless grants +1d4 ~= +2")
        assert m.source == "Bless spell"
        assert m.value == 2

    def test_source_too_long(self):
        with pytest.raises(ValidationError):
            Modifier(source="x" * 201, value=1, reason="x")

    def test_reason_too_long(self):
        with pytest.raises(ValidationError):
            Modifier(source="x", value=1, reason="y" * 501)

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            Modifier()  # type: ignore[call-arg]


# =============================================================================
# RollResult
# =============================================================================


class TestRollResult:
    def test_minimal(self):
        r = RollResult(raw_rolls=[3, 5], total=8)
        assert r.raw_rolls == [3, 5]
        assert r.kept_rolls == []
        assert r.total == 8
        assert r.natural == 0
        assert r.critical is False
        assert r.fumble is False

    def test_full(self):
        r = RollResult(
            raw_rolls=[20, 14, 5],
            kept_rolls=[20, 14],
            total=39,
            natural=34,
            critical=True,
        )
        assert r.critical is True
        assert r.kept_rolls == [20, 14]

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            RollResult()  # type: ignore[call-arg]


# =============================================================================
# ContestedRoll
# =============================================================================


class TestContestedRoll:
    def test_minimal(self):
        opp_id = uuid4()
        opponent_roll = RollResult(raw_rolls=[10], total=10)
        c = ContestedRoll(
            opponent_id=opp_id, opponent_roll=opponent_roll, margin_of_victory=5
        )
        assert c.opponent_id == opp_id
        assert c.opponent_modifiers == []

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ContestedRoll()  # type: ignore[call-arg]


# =============================================================================
# CardDraw
# =============================================================================


class TestCardDraw:
    def test_minimal(self):
        c = CardDraw(cards_drawn=["Hearts-King"], total_value=13)
        assert c.cards_drawn == ["Hearts-King"]
        assert c.total_value == 13
        assert c.special is None

    def test_with_special(self):
        c = CardDraw(
            cards_drawn=["Joker"],
            total_value=0,
            special="Red Joker - draw again",
        )
        assert c.special == "Red Joker - draw again"

    def test_special_too_long(self):
        with pytest.raises(ValidationError):
            CardDraw(cards_drawn=["x"], total_value=0, special="y" * 201)

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            CardDraw()  # type: ignore[call-arg]


# =============================================================================
# Mechanics
# =============================================================================


class TestMechanics:
    def test_minimal(self):
        m = Mechanics(formula="2d20kh1+5 vs DC 15")
        assert m.formula == "2d20kh1+5 vs DC 15"
        assert m.game_system_id is None
        assert m.modifiers == []
        assert m.target is None
        assert m.roll is None
        assert m.contested is None
        assert m.card_draw is None

    def test_with_roll(self):
        m = Mechanics(
            formula="2d20kh1+5 vs DC 15",
            modifiers=[Modifier(source="Bless", value=2, reason="buff")],
            target=15,
            roll=RollResult(raw_rolls=[15, 8], kept_rolls=[15], total=20),
        )
        assert m.target == 15
        assert m.roll.total == 20

    def test_formula_required(self):
        with pytest.raises(ValidationError):
            Mechanics()  # type: ignore[call-arg]

    def test_formula_too_long(self):
        with pytest.raises(ValidationError):
            Mechanics(formula="x" * 201)


# =============================================================================
# Effect
# =============================================================================


class TestEffect:
    def test_minimal(self):
        e = Effect(
            effect_type=EffectType.DAMAGE,
            target_id=uuid4(),
            description="Slashing damage",
        )
        assert e.magnitude == 0
        assert e.damage_type is None
        assert e.condition is None
        assert e.duration is None
        assert e.metadata == {}

    def test_full(self):
        e = Effect(
            effect_type=EffectType.CONDITION,
            target_id=uuid4(),
            magnitude=0,
            condition="stunned",
            duration=3,
            description="stunned for 3 rounds",
            metadata={"source": "spell"},
        )
        assert e.condition == "stunned"
        assert e.duration == 3

    def test_duration_negative(self):
        with pytest.raises(ValidationError):
            Effect(
                effect_type=EffectType.DAMAGE,
                target_id=uuid4(),
                description="x",
                duration=-1,
            )

    def test_damage_type_too_long(self):
        with pytest.raises(ValidationError):
            Effect(
                effect_type=EffectType.DAMAGE,
                target_id=uuid4(),
                description="x",
                damage_type="y" * 101,
            )

    def test_condition_too_long(self):
        with pytest.raises(ValidationError):
            Effect(
                effect_type=EffectType.CONDITION,
                target_id=uuid4(),
                description="x",
                condition="y" * 101,
            )

    def test_description_too_long(self):
        with pytest.raises(ValidationError):
            Effect(
                effect_type=EffectType.DAMAGE,
                target_id=uuid4(),
                description="x" * 501,
            )

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            Effect()  # type: ignore[call-arg]


# =============================================================================
# ResolutionCreate
# =============================================================================


class TestResolutionCreate:
    def _kwargs(self, **overrides):
        base = {
            "turn_id": uuid4(),
            "scene_id": uuid4(),
            "story_id": uuid4(),
            "actor_id": uuid4(),
            "action": "Strike the orc with sword",
            "action_type": ActionType.COMBAT,
            "resolution_type": ResolutionType.DICE,
            "mechanics": Mechanics(formula="2d20kh1+5 vs AC 15"),
            "success_level": SuccessLevel.SUCCESS,
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        r = ResolutionCreate(**self._kwargs())
        assert r.margin is None
        assert r.effects == []
        assert r.description is None
        assert r.gm_notes is None
        assert r.forced_narrative is False

    def test_full(self):
        effects = [
            Effect(
                effect_type=EffectType.DAMAGE,
                target_id=uuid4(),
                magnitude=12,
                damage_type="slashing",
                description="12 slashing damage",
            )
        ]
        r = ResolutionCreate(
            **self._kwargs(
                margin=5,
                effects=effects,
                description="A solid hit",
                gm_notes="PC rolled well",
                forced_narrative=False,
            )
        )
        assert r.margin == 5
        assert len(r.effects) == 1

    def test_action_too_long(self):
        with pytest.raises(ValidationError):
            ResolutionCreate(**self._kwargs(action="x" * 501))

    def test_description_too_long(self):
        with pytest.raises(ValidationError):
            ResolutionCreate(**self._kwargs(description="x" * 1001))

    def test_gm_notes_too_long(self):
        with pytest.raises(ValidationError):
            ResolutionCreate(**self._kwargs(gm_notes="x" * 1001))

    def test_invalid_action_type(self):
        with pytest.raises(ValidationError):
            ResolutionCreate(**self._kwargs(action_type="bogus"))  # type: ignore[arg-type]

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ResolutionCreate()  # type: ignore[call-arg]


# =============================================================================
# ResolutionUpdate
# =============================================================================


class TestResolutionUpdate:
    def test_empty(self):
        u = ResolutionUpdate()
        assert u.effects is None
        assert u.description is None
        assert u.gm_notes is None

    def test_partial(self):
        u = ResolutionUpdate(description="Updated")
        assert u.description == "Updated"

    def test_description_too_long(self):
        with pytest.raises(ValidationError):
            ResolutionUpdate(description="x" * 1001)

    def test_gm_notes_too_long(self):
        with pytest.raises(ValidationError):
            ResolutionUpdate(gm_notes="x" * 1001)


# =============================================================================
# ResolutionResponse
# =============================================================================


class TestResolutionResponse:
    def _kwargs(self, **overrides):
        base = {
            "id": uuid4(),
            "turn_id": uuid4(),
            "scene_id": uuid4(),
            "story_id": uuid4(),
            "actor_id": uuid4(),
            "action": "x",
            "action_type": ActionType.COMBAT,
            "resolution_type": ResolutionType.DICE,
            "mechanics": Mechanics(formula="x"),
            "success_level": SuccessLevel.SUCCESS,
            "margin": None,
            "effects": [],
            "description": None,
            "gm_notes": None,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        r = ResolutionResponse(**self._kwargs())
        assert r.updated_at is None
        assert r.forced_narrative is False

    def test_with_update(self):
        now = datetime.now(UTC)
        r = ResolutionResponse(**self._kwargs(updated_at=now))
        assert r.updated_at == now

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ResolutionResponse()  # type: ignore[call-arg]


# =============================================================================
# ResolutionFilter
# =============================================================================


class TestResolutionFilter:
    def test_defaults(self):
        f = ResolutionFilter()
        assert f.scene_id is None
        assert f.turn_id is None
        assert f.actor_id is None
        assert f.action_type is None
        assert f.success_level is None
        assert f.limit == 50
        assert f.offset == 0

    def test_with_values(self):
        f = ResolutionFilter(
            scene_id=uuid4(),
            action_type=ActionType.SKILL,
            success_level=SuccessLevel.CRITICAL_SUCCESS,
            limit=10,
        )
        assert f.action_type == ActionType.SKILL

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            ResolutionFilter(limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            ResolutionFilter(limit=101)

    def test_offset_min(self):
        with pytest.raises(ValidationError):
            ResolutionFilter(offset=-1)


# =============================================================================
# ResolutionListResponse
# =============================================================================


class TestResolutionListResponse:
    def test_empty(self):
        r = ResolutionListResponse(resolutions=[], total=0, limit=50, offset=0)
        assert r.resolutions == []
        assert r.total == 0

    def test_with_resolution(self):
        res = ResolutionResponse(
            id=uuid4(),
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="x",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="x"),
            success_level=SuccessLevel.SUCCESS,
            margin=None,
            effects=[],
            description=None,
            gm_notes=None,
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        r = ResolutionListResponse(resolutions=[res], total=1, limit=50, offset=0)
        assert len(r.resolutions) == 1

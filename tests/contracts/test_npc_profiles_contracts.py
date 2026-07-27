"""Contract tests for the NPCProfile schemas.

Verifies that npc_profiles Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce numeric / length constraints,
- reject invalid enum values where applicable.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.npc_profiles import (
    BehavioralTrigger,
    CharacterPreference,
    EmotionalTendency,
    NPCProfileCreate,
    NPCProfileResponse,
    NPCProfileUpdate,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# =============================================================================
# EmotionalTendency
# =============================================================================


class TestEmotionalTendency:
    def test_minimal(self):
        e = EmotionalTendency(emotion="anger", baseline=0.3)
        assert e.emotion == "anger"
        assert e.baseline == 0.3
        assert e.volatility == 0.5  # default

    def test_with_volatility(self):
        e = EmotionalTendency(emotion="joy", baseline=0.8, volatility=0.2)
        assert e.volatility == 0.2

    def test_baseline_min(self):
        with pytest.raises(ValidationError):
            EmotionalTendency(emotion="anger", baseline=-1.1)

    def test_baseline_max(self):
        with pytest.raises(ValidationError):
            EmotionalTendency(emotion="anger", baseline=1.1)

    def test_baseline_bounds(self):
        e_min = EmotionalTendency(emotion="anger", baseline=-1.0)
        e_max = EmotionalTendency(emotion="anger", baseline=1.0)
        assert e_min.baseline == -1.0
        assert e_max.baseline == 1.0

    def test_volatility_min(self):
        with pytest.raises(ValidationError):
            EmotionalTendency(emotion="anger", baseline=0.0, volatility=-0.1)

    def test_volatility_max(self):
        with pytest.raises(ValidationError):
            EmotionalTendency(emotion="anger", baseline=0.0, volatility=1.1)

    def test_emotion_too_long(self):
        with pytest.raises(ValidationError):
            EmotionalTendency(emotion="x" * 51, baseline=0.0)

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            EmotionalTendency()  # type: ignore[call-arg]


# =============================================================================
# CharacterPreference
# =============================================================================


class TestCharacterPreference:
    def test_minimal(self):
        p = CharacterPreference(category="food", item="apples", valence=0.7)
        assert p.category == "food"
        assert p.item == "apples"
        assert p.valence == 0.7
        assert p.reason is None

    def test_with_reason(self):
        p = CharacterPreference(
            category="people",
            item="soldiers",
            valence=-0.5,
            reason="lost brother in war",
        )
        assert p.reason == "lost brother in war"

    def test_valence_min(self):
        with pytest.raises(ValidationError):
            CharacterPreference(category="x", item="y", valence=-1.1)

    def test_valence_max(self):
        with pytest.raises(ValidationError):
            CharacterPreference(category="x", item="y", valence=1.1)

    def test_valence_bounds(self):
        p_min = CharacterPreference(category="x", item="y", valence=-1.0)
        p_max = CharacterPreference(category="x", item="y", valence=1.0)
        assert p_min.valence == -1.0
        assert p_max.valence == 1.0

    def test_category_too_long(self):
        with pytest.raises(ValidationError):
            CharacterPreference(category="x" * 51, item="y", valence=0.0)

    def test_item_too_long(self):
        with pytest.raises(ValidationError):
            CharacterPreference(category="x", item="y" * 201, valence=0.0)

    def test_reason_too_long(self):
        with pytest.raises(ValidationError):
            CharacterPreference(category="x", item="y", valence=0.0, reason="z" * 501)

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            CharacterPreference()  # type: ignore[call-arg]


# =============================================================================
# BehavioralTrigger
# =============================================================================


class TestBehavioralTrigger:
    def test_minimal(self):
        t = BehavioralTrigger(
            condition="asked about the thieves guild",
            reaction="becomes evasive",
        )
        assert t.condition == "asked about the thieves guild"
        assert t.reaction == "becomes evasive"
        assert t.intensity == 0.7  # default
        assert t.is_hidden is True  # default

    def test_with_intensity(self):
        t = BehavioralTrigger(
            condition="sees a sword",
            reaction="freezes",
            intensity=0.9,
            is_hidden=False,
        )
        assert t.intensity == 0.9
        assert t.is_hidden is False

    def test_intensity_min(self):
        with pytest.raises(ValidationError):
            BehavioralTrigger(condition="x", reaction="y", intensity=-0.1)

    def test_intensity_max(self):
        with pytest.raises(ValidationError):
            BehavioralTrigger(condition="x", reaction="y", intensity=1.1)

    def test_condition_too_long(self):
        with pytest.raises(ValidationError):
            BehavioralTrigger(condition="x" * 501, reaction="y")

    def test_reaction_too_long(self):
        with pytest.raises(ValidationError):
            BehavioralTrigger(condition="x", reaction="y" * 501)

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            BehavioralTrigger()  # type: ignore[call-arg]


# =============================================================================
# NPCProfileCreate
# =============================================================================


class TestNPCProfileCreate:
    def test_minimal(self):
        eid = uuid4()
        p = NPCProfileCreate(entity_id=eid)
        assert p.entity_id == eid
        assert p.traits == {}
        assert p.values == []
        assert p.fears == []
        assert p.desires == []
        assert p.speech_style is None
        assert p.catchphrases == []
        assert p.mannerisms == []
        assert p.emotional_tendencies == []
        assert p.preferences == []
        assert p.triggers == []
        assert p.secrets == []
        assert p.gm_notes is None
        assert p.current_emotional_state is None
        assert p.relationship_states == {}

    def test_full(self):
        eid = uuid4()
        p = NPCProfileCreate(
            entity_id=eid,
            traits={"openness": 0.8, "conscientiousness": 0.3},
            values=["honor", "family"],
            fears=["betrayal"],
            desires=["recognition"],
            speech_style="formal and verbose",
            catchphrases=["By the Seven!"],
            mannerisms=["tugs ear when lying"],
            emotional_tendencies=[
                EmotionalTendency(emotion="anger", baseline=0.2, volatility=0.7)
            ],
            preferences=[
                CharacterPreference(category="food", item="apples", valence=0.7)
            ],
            triggers=[BehavioralTrigger(condition="sees a sword", reaction="freezes")],
            secrets=["is actually the king's bastard"],
            gm_notes="Motivated by revenge",
            current_emotional_state="suspicious",
            relationship_states={str(uuid4()): {"trust": 0.2, "hostility": 0.5}},
        )
        assert p.traits["openness"] == 0.8
        assert "honor" in p.values
        assert len(p.triggers) == 1

    def test_speech_style_too_long(self):
        with pytest.raises(ValidationError):
            NPCProfileCreate(entity_id=uuid4(), speech_style="x" * 201)

    def test_current_emotion_too_long(self):
        with pytest.raises(ValidationError):
            NPCProfileCreate(entity_id=uuid4(), current_emotional_state="x" * 201)

    def test_gm_notes_too_long(self):
        with pytest.raises(ValidationError):
            NPCProfileCreate(entity_id=uuid4(), gm_notes="x" * 5001)

    def test_required_entity_id(self):
        with pytest.raises(ValidationError):
            NPCProfileCreate()  # type: ignore[call-arg]


# =============================================================================
# NPCProfileUpdate
# =============================================================================


class TestNPCProfileUpdate:
    def test_empty(self):
        u = NPCProfileUpdate()
        assert u.traits is None
        assert u.values is None
        assert u.add_preference is None
        assert u.add_trigger is None
        assert u.add_secret is None

    def test_partial(self):
        u = NPCProfileUpdate(values=["honor"], fears=["death"])
        assert u.values == ["honor"]
        assert u.fears == ["death"]

    def test_speech_style_too_long(self):
        with pytest.raises(ValidationError):
            NPCProfileUpdate(speech_style="x" * 201)

    def test_gm_notes_too_long(self):
        with pytest.raises(ValidationError):
            NPCProfileUpdate(gm_notes="x" * 5001)

    def test_add_secret_too_long(self):
        with pytest.raises(ValidationError):
            NPCProfileUpdate(add_secret="x" * 501)

    def test_append_helpers(self):
        u = NPCProfileUpdate(
            add_preference=CharacterPreference(
                category="food", item="apples", valence=0.7
            ),
            add_trigger=BehavioralTrigger(condition="sees a sword", reaction="freezes"),
            add_secret="is a spy",
        )
        assert u.add_preference is not None
        assert u.add_trigger is not None
        assert u.add_secret == "is a spy"


# =============================================================================
# NPCProfileResponse
# =============================================================================


class TestNPCProfileResponse:
    def _kwargs(self, **overrides):
        base = {
            "profile_id": uuid4(),
            "entity_id": uuid4(),
            "traits": {"openness": 0.8},
            "values": ["honor"],
            "fears": ["betrayal"],
            "desires": ["recognition"],
            "catchphrases": ["By the Seven!"],
            "mannerisms": ["tugs ear"],
            "emotional_tendencies": [],
            "preferences": [],
            "triggers": [],
            "secrets": [],
            "created_at": datetime.now(UTC),
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        r = NPCProfileResponse(**self._kwargs())
        assert r.speech_style is None
        assert r.gm_notes is None
        assert r.current_emotional_state is None
        assert r.relationship_states == {}
        assert r.updated_at is None

    def test_with_relationship_states(self):
        states = {str(uuid4()): {"trust": 0.5, "hostility": 0.0}}
        r = NPCProfileResponse(**self._kwargs(relationship_states=states))
        assert r.relationship_states == states

    def test_with_emotional_tendencies(self):
        e = EmotionalTendency(emotion="anger", baseline=0.3, volatility=0.5)
        r = NPCProfileResponse(**self._kwargs(emotional_tendencies=[e]))
        assert len(r.emotional_tendencies) == 1

    def test_required_profile_id(self):
        with pytest.raises(ValidationError):
            NPCProfileResponse(
                entity_id=uuid4(),
                traits={},
                values=[],
                fears=[],
                desires=[],
                catchphrases=[],
                mannerisms=[],
                emotional_tendencies=[],
                preferences=[],
                triggers=[],
                secrets=[],
                created_at=datetime.now(UTC),
            )

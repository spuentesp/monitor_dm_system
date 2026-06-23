"""Contract tests for the NPCSceneGenerator output schemas.

Verifies that npc_scene_generator Pydantic models:
- instantiate with valid data,
- enforce numeric / length constraints.
"""
from __future__ import annotations

import pytest
from monitor_data.schemas.npc_scene_generator import (
    SceneBehavioralTrigger,
    GeneratedNPCProfile,
    NPCSceneGeneratorOutput,
    ScenePrompt,
)
from pydantic import ValidationError


pytestmark = pytest.mark.unit


# =============================================================================
# SceneBehavioralTrigger
# =============================================================================


class TestBehavioralTrigger:
    def test_minimal(self):
        t = SceneBehavioralTrigger(
            trigger_topic="asked about family",
            reaction="looks away",
        )
        assert t.trigger_topic == "asked about family"
        assert t.reaction == "looks away"
        assert t.gm_note is None

    def test_with_gm_note(self):
        t = SceneBehavioralTrigger(
            trigger_topic="sees a sword",
            reaction="freezes",
            gm_note="Lost her brother in the war",
        )
        assert t.gm_note == "Lost her brother in the war"

    def test_topic_too_long(self):
        with pytest.raises(ValidationError):
            SceneBehavioralTrigger(
                trigger_topic="x" * 201, reaction="y"
            )

    def test_reaction_too_long(self):
        with pytest.raises(ValidationError):
            SceneBehavioralTrigger(
                trigger_topic="x", reaction="y" * 501
            )

    def test_gm_note_too_long(self):
        with pytest.raises(ValidationError):
            SceneBehavioralTrigger(
                trigger_topic="x", reaction="y", gm_note="z" * 301
            )

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            SceneBehavioralTrigger()  # type: ignore[call-arg]


# =============================================================================
# GeneratedNPCProfile
# =============================================================================


class TestGeneratedNPCProfile:
    def test_minimal(self):
        p = GeneratedNPCProfile(
            name="Bartholomew",
            role="innkeeper",
            personality_summary="gruff but kind",
            current_goal="pay off his mortgage",
        )
        assert p.name == "Bartholomew"
        assert p.role == "innkeeper"
        assert p.agenda_title is None
        assert p.behavior_triggers == []
        assert p.suggested_dialogue_hooks == []
        assert p.suggested_scene_invitations == []
        assert p.tags == []

    def test_full(self):
        p = GeneratedNPCProfile(
            name="Bartholomew",
            role="innkeeper",
            personality_summary="gruff but kind",
            current_goal="pay off his mortgage",
            agenda_title="The Inn's Debt",
            behavior_triggers=[
                SceneBehavioralTrigger(
                    trigger_topic="sees a sword",
                    reaction="freezes",
                )
            ],
            suggested_dialogue_hooks=["What can I get you?", "We don't serve your kind here."],
            suggested_scene_invitations=["A traveler arrives at midnight"],
            tags=["innkeeper", "neutral"],
        )
        assert p.agenda_title == "The Inn's Debt"
        assert len(p.behavior_triggers) == 1
        assert "innkeeper" in p.tags

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            GeneratedNPCProfile(
                name="x" * 201, role="x", personality_summary="x", current_goal="x"
            )

    def test_role_too_long(self):
        with pytest.raises(ValidationError):
            GeneratedNPCProfile(
                name="x", role="x" * 201, personality_summary="x", current_goal="x"
            )

    def test_personality_too_long(self):
        with pytest.raises(ValidationError):
            GeneratedNPCProfile(
                name="x",
                role="x",
                personality_summary="x" * 501,
                current_goal="x",
            )

    def test_goal_too_long(self):
        with pytest.raises(ValidationError):
            GeneratedNPCProfile(
                name="x", role="x", personality_summary="x", current_goal="x" * 501
            )

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            GeneratedNPCProfile()  # type: ignore[call-arg]


# =============================================================================
# ScenePrompt
# =============================================================================


class TestScenePrompt:
    def test_minimal(self):
        s = ScenePrompt(title="The Midnight Arrival", setup="A traveler arrives at midnight.")
        assert s.title == "The Midnight Arrival"
        assert s.npcs_involved == []
        assert s.random_table_rolls == []
        assert s.agenda_clocks_active == []
        assert s.suggested_conflict is None
        assert s.tags == []

    def test_full(self):
        s = ScenePrompt(
            title="The Midnight Arrival",
            setup="A traveler arrives at midnight, covered in blood.",
            npcs_involved=["Bartholomew", "Captain Vex"],
            random_table_rolls=[{"table": "weather", "roll": 17, "result": "storm"}],
            agenda_clocks_active=["The Inn's Debt"],
            suggested_conflict="The traveler is being pursued",
            tags=["night", "rain"],
        )
        assert "Bartholomew" in s.npcs_involved
        assert s.suggested_conflict == "The traveler is being pursued"

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            ScenePrompt(title="x" * 201, setup="x")

    def test_setup_too_long(self):
        with pytest.raises(ValidationError):
            ScenePrompt(title="x", setup="x" * 1001)

    def test_conflict_too_long(self):
        with pytest.raises(ValidationError):
            ScenePrompt(title="x", setup="x", suggested_conflict="x" * 501)

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ScenePrompt()  # type: ignore[call-arg]


# =============================================================================
# NPCSceneGeneratorOutput
# =============================================================================


class TestNPCSceneGeneratorOutput:
    def test_minimal(self):
        o = NPCSceneGeneratorOutput()
        assert o.npcs == []
        assert o.scenes == []
        assert o.generated_from_pack_id is None

    def test_with_content(self):
        o = NPCSceneGeneratorOutput(
            npcs=[
                GeneratedNPCProfile(
                    name="Bart",
                    role="innkeeper",
                    personality_summary="x",
                    current_goal="x",
                )
            ],
            scenes=[
                ScenePrompt(title="A Storm", setup="Dark clouds gather.")
            ],
            generated_from_pack_id="pack-123",
        )
        assert len(o.npcs) == 1
        assert len(o.scenes) == 1
        assert o.generated_from_pack_id == "pack-123"

    def test_generated_from_pack_id_too_long(self):
        with pytest.raises(ValidationError):
            NPCSceneGeneratorOutput(generated_from_pack_id="x" * 201)

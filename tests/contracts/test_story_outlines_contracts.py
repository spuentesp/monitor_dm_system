"""
Contract tests for Story Outline schemas (M-29, DL-6).

Covers:
- StoryBeat: individual story beat with progression
- BranchingPoint: branching narrative decisions
- MysteryClue: clue in a mystery
- MysterySuspect: suspect in a mystery
- MysteryStructure: full mystery structure
- PacingMetrics: pacing tracking
- StoryOutlineCreate: create outline
- StoryOutlineUpdate: partial update with beat ops
- StoryOutlineResponse: full response
- ThreadDeadline: time pressure
- BeatStatus enum
- StoryStructureType enum
- ArcTemplate enum
- ClueVisibility enum

Use Cases: M-29, DL-6
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Dict

import pytest

from monitor_data.schemas.story_outlines import (
    StoryBeat,
    BranchingPoint,
    MysteryClue,
    MysterySuspect,
    MysteryStructure,
    PacingMetrics,
    StoryOutlineCreate,
    StoryOutlineUpdate,
    StoryOutlineResponse,
    ThreadDeadline,
    PlotThreadCreate,
)
from monitor_data.schemas.base import (
    BeatStatus,
    StoryStructureType,
    ArcTemplate,
    ClueVisibility,
)


# =============================================================================
# StoryBeat
# =============================================================================


class TestStoryBeat:
    def test_minimal(self):
        b = StoryBeat(
            title="Meet the mentor",
            order=0,
        )
        assert b.title == "Meet the mentor"
        assert b.order == 0
        assert b.status == BeatStatus.PENDING
        assert b.optional is False

    def test_with_status(self):
        b = StoryBeat(
            title="Battle the dragon",
            order=5,
            status=BeatStatus.IN_PROGRESS,
        )
        assert b.status == BeatStatus.IN_PROGRESS

    def test_optional_beat(self):
        b = StoryBeat(
            title="Side quest: lost cat",
            order=10,
            optional=True,
        )
        assert b.optional is True

    def test_beat_id_is_set(self):
        b = StoryBeat(title="x", order=0)
        assert b.beat_id is not None

    def test_order_bounds(self):
        with pytest.raises(Exception):
            StoryBeat(title="x", order=-1)


# =============================================================================
# BranchingPoint
# =============================================================================


class TestBranchingPoint:
    def test_minimal(self):
        bp = BranchingPoint(
            beat_id=uuid4(),
            decision="Help the villagers or rob them",
        )
        assert "villagers" in bp.decision
        assert bp.branches == []

    def test_with_branches(self):
        bp = BranchingPoint(
            beat_id=uuid4(),
            decision="Choose your path",
            branches=[
                {"label": "Right path", "next_beat_id": str(uuid4())},
                {"label": "Left path", "next_beat_id": str(uuid4())},
            ],
        )
        assert len(bp.branches) == 2


# =============================================================================
# MysteryClue
# =============================================================================


class TestMysteryClue:
    def test_minimal(self):
        c = MysteryClue(content="A bloody knife under the bed")
        assert c.content == "A bloody knife under the bed"
        assert c.is_discovered is False
        assert c.visibility == ClueVisibility.HIDDEN

    def test_with_discovery(self):
        c = MysteryClue(
            content="A torn letter with a half-legible signature",
            discovery_methods=["search", "investigate"],
            is_discovered=True,
            discovered_in_scene_id=uuid4(),
        )
        assert c.is_discovered is True
        assert "search" in c.discovery_methods

    def test_visibility_states(self):
        c = MysteryClue(content="x", visibility=ClueVisibility.REVEALED)
        assert c.visibility == ClueVisibility.REVEALED


# =============================================================================
# MysterySuspect
# =============================================================================


class TestMysterySuspect:
    def test_minimal(self):
        s = MysterySuspect(
            entity_id=uuid4(),
            theory="The butler did it",
        )
        assert "butler" in s.theory
        assert s.evidence_for == []
        assert s.evidence_against == []

    def test_with_evidence(self):
        s = MysterySuspect(
            entity_id=uuid4(),
            theory="The butler did it",
            evidence_for=[uuid4(), uuid4()],
            evidence_against=[uuid4()],
        )
        assert len(s.evidence_for) == 2
        assert len(s.evidence_against) == 1


# =============================================================================
# MysteryStructure
# =============================================================================


class TestMysteryStructure:
    def test_minimal(self):
        m = MysteryStructure(truth="The butler did it", question="Who killed the lord?")
        assert m.truth == "The butler did it"
        assert m.core_clues == []
        assert m.suspects == []

    def test_with_clues_and_suspects(self):
        m = MysteryStructure(
            truth="The queen did it",
            question="Who stole the crown?",
            core_clues=[
                MysteryClue(content="Crown in garden"),
                MysteryClue(content="Royal footprints"),
            ],
            suspects=[
                MysterySuspect(entity_id=uuid4(), theory="The queen"),
                MysterySuspect(entity_id=uuid4(), theory="The advisor"),
            ],
        )
        assert len(m.core_clues) == 2
        assert len(m.suspects) == 2


# =============================================================================
# PacingMetrics
# =============================================================================


class TestPacingMetrics:
    def test_defaults(self):
        m = PacingMetrics()
        assert m.current_act == 1
        assert m.tension_level == 0.0
        assert m.scenes_since_major_event == 0
        assert m.estimated_completion == 0.0

    def test_tension_bounds(self):
        with pytest.raises(Exception):
            PacingMetrics(tension_level=1.5)
        with pytest.raises(Exception):
            PacingMetrics(tension_level=-0.1)

    def test_act_bounds(self):
        with pytest.raises(Exception):
            PacingMetrics(current_act=0)  # < 1
        with pytest.raises(Exception):
            PacingMetrics(current_act=6)  # > 5


# =============================================================================
# StoryOutlineCreate
# =============================================================================


class TestStoryOutlineCreate:
    def test_minimal(self):
        req = StoryOutlineCreate(story_id=uuid4())
        assert req.story_id
        assert req.theme == ""
        assert req.premise == ""
        assert req.beats == []
        assert req.structure_type == StoryStructureType.LINEAR
        assert req.template == ArcTemplate.CUSTOM

    def test_with_beats(self):
        req = StoryOutlineCreate(
            story_id=uuid4(),
            theme="Redemption",
            premise="A fallen hero seeks forgiveness",
            beats=[
                StoryBeat(title="Setup", order=0),
                StoryBeat(title="Rising action", order=1),
            ],
            structure_type=StoryStructureType.LINEAR,
            template=ArcTemplate.THREE_ACT,
        )
        assert req.theme == "Redemption"
        assert len(req.beats) == 2
        assert req.template == ArcTemplate.THREE_ACT

    def test_with_mystery(self):
        req = StoryOutlineCreate(
            story_id=uuid4(),
            structure_type=StoryStructureType.MYSTERY,
            template=ArcTemplate.MYSTERY,
            mystery_structure=MysteryStructure(
                truth="X did it",
                question="Who did X?",
                core_clues=[MysteryClue(content="x")],
            ),
        )
        assert req.mystery_structure is not None
        assert len(req.mystery_structure.core_clues) == 1


# =============================================================================
# StoryOutlineUpdate
# =============================================================================


class TestStoryOutlineUpdate:
    def test_empty(self):
        upd = StoryOutlineUpdate()
        assert upd.theme is None
        assert upd.add_beats is None
        assert upd.remove_beat_ids is None

    def test_beat_operations(self):
        new_beat = StoryBeat(title="New", order=99)
        upd = StoryOutlineUpdate(
            add_beats=[new_beat],
            remove_beat_ids=[uuid4()],
            reorder_beats=[uuid4(), uuid4()],
        )
        assert len(upd.add_beats) == 1
        assert len(upd.remove_beat_ids) == 1
        assert len(upd.reorder_beats) == 2

    def test_mark_clue_discovered(self):
        clue_id = uuid4()
        upd = StoryOutlineUpdate(mark_clue_discovered=clue_id)
        assert upd.mark_clue_discovered == clue_id


# =============================================================================
# StoryOutlineResponse
# =============================================================================


class TestStoryOutlineResponse:
    def test_minimal(self):
        resp = StoryOutlineResponse(
            story_id=uuid4(),
            theme="",
            premise="",
            constraints=[],
            beats=[],
            structure_type=StoryStructureType.LINEAR,
            template=ArcTemplate.CUSTOM,
            branching_points=[],
            pacing_metrics=PacingMetrics(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert resp.story_id
        assert resp.open_threads == []  # default


# =============================================================================
# ThreadDeadline
# =============================================================================


class TestThreadDeadline:
    def test_basic(self):
        t = ThreadDeadline(
            world_time=datetime(2024, 12, 31, tzinfo=timezone.utc),
            description="The ancient seal weakens",
        )
        assert t.description == "The ancient seal weakens"

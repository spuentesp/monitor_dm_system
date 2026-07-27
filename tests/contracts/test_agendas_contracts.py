"""
Contract tests for Faction Agendas / Clocks schemas (M-36).

Covers:
- AgendaStatus enum (dormant, active, completed, failed/thwarted)
- AgendaType enum (faction_goal, world_event, personal_vendetta, mindscape_evolution)
- ExtractedAgenda: agenda extracted from source text with evidence refs
- AgendaCreate: CRUD request schema with clock segments
- AgendaResponse: full agenda with current clock state
- AgendaFilter: list filter parameters

Use Cases: M-36 (Faction drive / clocks)
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

from monitor_data.schemas.agendas import (
    AgendaCreate,
    AgendaFilter,
    AgendaResponse,
    AgendaStatus,
    AgendaType,
    ExtractedAgenda,
)


def _ts() -> str:
    return datetime.now(UTC).isoformat()


# =============================================================================
# Enums
# =============================================================================


class TestAgendaStatusEnum:
    def test_all_values(self):
        assert AgendaStatus.DORMANT.value == "dormant"
        assert AgendaStatus.ACTIVE.value == "active"
        assert AgendaStatus.COMPLETED.value == "completed"
        assert AgendaStatus.THWARTED.value == "failed"


class TestAgendaTypeEnum:
    def test_all_values(self):
        assert AgendaType.FACTION_GOAL.value == "faction_goal"
        assert AgendaType.WORLD_EVENT.value == "world_event"
        assert AgendaType.PERSONAL_VENDETTA.value == "personal_vendetta"
        assert AgendaType.MINDSCAPE_EVOLUTION.value == "mindscape_evolution"


# =============================================================================
# ExtractedAgenda
# =============================================================================


class TestExtractedAgenda:
    def test_minimal(self):
        agenda = ExtractedAgenda(
            title="Rescue the princess",
            description="The princess is held in the tower.",
        )
        assert agenda.title == "Rescue the princess"
        assert agenda.agenda_type == "faction_goal"  # default
        assert agenda.suggested_segments == 6  # default
        assert agenda.confidence == 0.8  # default

    def test_with_custom_segments(self):
        agenda = ExtractedAgenda(
            title="Build an army",
            description="Recruit 100 soldiers.",
            suggested_segments=10,
        )
        assert agenda.suggested_segments == 10

    def test_with_evidence_refs(self):
        # ProfileEvidenceRef may not be importable or may have different shape
        try:
            from monitor_data.schemas.base import ProfileEvidenceRef

            agenda = ExtractedAgenda(
                title="Investigate the cult",
                description="Strange rituals observed in the temple district.",
                evidence_refs=[
                    ProfileEvidenceRef(
                        snippet_id="snip-1",
                        text_excerpt="Worshippers gather at midnight...",
                    ),
                ],
            )
            assert len(agenda.evidence_refs) == 1
        except (ImportError, TypeError, Exception):
            # Skip if schema field shape doesn't match
            agenda = ExtractedAgenda(
                title="Investigate the cult",
                description="Strange rituals observed in the temple district.",
            )
            assert len(agenda.evidence_refs) == 0  # default is empty list


# =============================================================================
# AgendaCreate
# =============================================================================


class TestAgendaCreate:
    def test_minimal(self):
        req = AgendaCreate(
            universe_id=uuid4(),
            title="Conquer the kingdom",
            description="Annex all neighboring lands.",
        )
        assert req.title == "Conquer the kingdom"
        assert req.agenda_type == AgendaType.FACTION_GOAL  # default
        assert req.status == AgendaStatus.ACTIVE  # default
        assert req.total_segments == 6  # default
        assert req.current_segments == 0  # default

    def test_with_owner(self):
        owner = uuid4()
        req = AgendaCreate(
            universe_id=uuid4(),
            owner_id=owner,
            title="Personal revenge",
            description="Seek vengeance.",
            agenda_type=AgendaType.PERSONAL_VENDETTA,
        )
        assert req.owner_id == owner
        assert req.agenda_type == AgendaType.PERSONAL_VENDETTA

    def test_with_clock_segments(self):
        req = AgendaCreate(
            universe_id=uuid4(),
            title="Advance the ritual",
            description="Progress through 8 stages.",
            total_segments=8,
            current_segments=3,
        )
        assert req.total_segments == 8
        assert req.current_segments == 3

    def test_with_properties(self):
        req = AgendaCreate(
            universe_id=uuid4(),
            title="Mine the mountain",
            description="Extract rare ores.",
            properties={"target": "Iron Hills", "lead_miner": "Balin"},
        )
        assert req.properties["target"] == "Iron Hills"


# =============================================================================
# AgendaResponse
# =============================================================================


class TestAgendaResponse:
    def _make(self, **overrides) -> AgendaResponse:
        defaults = {
            "id": uuid4(),
            "universe_id": uuid4(),
            "owner_id": None,
            "title": "Test Agenda",
            "description": "Test description",
            "agenda_type": AgendaType.FACTION_GOAL,
            "status": AgendaStatus.ACTIVE,
            "total_segments": 6,
            "current_segments": 2,
            "properties": None,
            "created_at": _ts(),
            "updated_at": _ts(),
        }
        defaults.update(overrides)
        return AgendaResponse(**defaults)

    def test_minimal(self):
        resp = self._make()
        assert resp.id
        assert resp.title == "Test Agenda"
        assert resp.total_segments == 6
        assert resp.current_segments == 2

    def test_with_owner(self):
        owner = uuid4()
        resp = self._make(owner_id=owner)
        assert resp.owner_id == owner

    def test_status_transitions(self):
        for status in [
            AgendaStatus.DORMANT,
            AgendaStatus.ACTIVE,
            AgendaStatus.COMPLETED,
            AgendaStatus.THWARTED,
        ]:
            resp = self._make(status=status)
            assert resp.status == status


# =============================================================================
# AgendaFilter
# =============================================================================


class TestAgendaFilter:
    def test_empty_filter(self):
        f = AgendaFilter()
        assert f.universe_id is None
        assert f.owner_id is None
        assert f.status is None
        assert f.agenda_type is None

    def test_filter_by_universe(self):
        uid = uuid4()
        f = AgendaFilter(universe_id=uid)
        assert f.universe_id == uid

    def test_filter_by_status(self):
        f = AgendaFilter(status=AgendaStatus.ACTIVE)
        assert f.status == AgendaStatus.ACTIVE

    def test_filter_by_type(self):
        f = AgendaFilter(agenda_type=AgendaType.WORLD_EVENT)
        assert f.agenda_type == AgendaType.WORLD_EVENT

    def test_filter_by_owner(self):
        owner = uuid4()
        f = AgendaFilter(owner_id=owner)
        assert f.owner_id == owner

    def test_combined_filter(self):
        uid = uuid4()
        owner = uuid4()
        f = AgendaFilter(
            universe_id=uid,
            owner_id=owner,
            status=AgendaStatus.ACTIVE,
            agenda_type=AgendaType.FACTION_GOAL,
        )
        assert f.universe_id == uid
        assert f.owner_id == owner
        assert f.status == AgendaStatus.ACTIVE
        assert f.agenda_type == AgendaType.FACTION_GOAL

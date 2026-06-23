"""
Contract tests for Party schemas (DL-15 part 2).

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)

pytest --test-run-type=unit tests/contracts/test_DL_28_contracts.py
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4, UUID

from pydantic import ValidationError

from monitor_data.schemas.base import PartyStatus
from monitor_data.schemas.parties import (
    PartyMemberInfo,
    PartyCreate,
    PartyUpdate,
    PartyResponse,
    AddPartyMember,
    RemovePartyMember,
    SetActivePC,
)


# =============================================================================
# PARTY MEMBER INFO
# =============================================================================


class TestPartyMemberInfo:
    def test_minimal(self):
        now = datetime.now(timezone.utc)
        m = PartyMemberInfo(entity_id=uuid4(), joined_at=now)
        assert m.role is None
        assert m.position is None

    def test_full(self):
        now = datetime.now(timezone.utc)
        eid = uuid4()
        m = PartyMemberInfo(entity_id=eid, role="leader", position=0, joined_at=now)
        assert m.role == "leader"
        assert m.position == 0


# =============================================================================
# PARTY CREATE
# =============================================================================


class TestPartyCreate:
    def test_minimal(self):
        sid = uuid4()
        p = PartyCreate(story_id=sid, name="The Fellowship")
        assert p.name == "The Fellowship"
        assert p.status == PartyStatus.TRAVELING
        assert p.initial_member_ids == []
        assert p.formation == []

    def test_with_members(self):
        sid = uuid4()
        eids = [uuid4(), uuid4()]
        p = PartyCreate(story_id=sid, name="Heroes", initial_member_ids=eids)
        assert len(p.initial_member_ids) == 2

    def test_name_min_length_1(self):
        with pytest.raises(ValidationError):
            PartyCreate(story_id=uuid4(), name="")

    def test_name_max_length_200(self):
        with pytest.raises(ValidationError):
            PartyCreate(story_id=uuid4(), name="A" * 201)

    def test_all_statuses(self):
        for status in PartyStatus:
            p = PartyCreate(story_id=uuid4(), name=f"Party {status.value}", status=status)
            assert p.status == status


class TestPartyUpdate:
    def test_empty_update(self):
        u = PartyUpdate()
        assert u.name is None
        assert u.status is None

    def test_partial(self):
        u = PartyUpdate(name="New Name", status=PartyStatus.RESTING)
        assert u.name == "New Name"
        assert u.status == PartyStatus.RESTING


class TestPartyResponse:
    def test_minimal(self):
        now = datetime.now(timezone.utc)
        r = PartyResponse(
            id=uuid4(),
            story_id=uuid4(),
            name="Fellowship",
            status=PartyStatus.TRAVELING,
            formation=[],
            created_at=now,
        )
        assert r.name == "Fellowship"
        assert r.members == []

    def test_with_members(self):
        now = datetime.now(timezone.utc)
        m = PartyMemberInfo(entity_id=uuid4(), joined_at=now)
        r = PartyResponse(
            id=uuid4(),
            story_id=uuid4(),
            name="Fellowship",
            status=PartyStatus.TRAVELING,
            formation=[],
            members=[m],
            created_at=now,
        )
        assert len(r.members) == 1


# =============================================================================
# ADD/REMOVE MEMBER, ACTIVE PC
# =============================================================================


class TestAddPartyMember:
    def test_valid(self):
        a = AddPartyMember(party_id=uuid4(), entity_id=uuid4(), role="scout", position=1)
        assert a.role == "scout"
        assert a.position == 1


class TestRemovePartyMember:
    def test_valid(self):
        r = RemovePartyMember(party_id=uuid4(), entity_id=uuid4())
        assert isinstance(r.party_id, UUID)


class TestSetActivePC:
    def test_valid(self):
        s = SetActivePC(party_id=uuid4(), entity_id=uuid4())
        assert isinstance(s.entity_id, UUID)


# =============================================================================
# PARTY STATUS ENUM
# =============================================================================


class TestPartyStatusEnum:
    def test_values(self):
        assert PartyStatus.TRAVELING.value == "traveling"
        assert PartyStatus.CAMPING.value == "camping"
        assert PartyStatus.IN_SCENE.value == "in_scene"
        assert PartyStatus.COMBAT.value == "combat"
        assert PartyStatus.SPLIT.value == "split"
        assert PartyStatus.RESTING.value == "resting"

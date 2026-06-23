"""
Contract tests for Party schemas.

Covers:
- PartyMemberInfo: party member info
- PartyCreate / Update / Response
- AddPartyMember / RemovePartyMember / SetActivePC
- PartyStatus enum

Use Cases: Phase 1 Party system
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

import pytest

from monitor_data.schemas.parties import (
    PartyMemberInfo,
    PartyCreate,
    PartyUpdate,
    PartyResponse,
    AddPartyMember,
    RemovePartyMember,
    SetActivePC,
)
from monitor_data.schemas.base import PartyStatus


# =============================================================================
# Enum
# =============================================================================


class TestPartyStatusEnum:
    def test_all_values(self):
        assert PartyStatus.TRAVELING.value == "traveling"
        assert PartyStatus.CAMPING.value == "camping"
        assert PartyStatus.IN_SCENE.value == "in_scene"
        assert PartyStatus.COMBAT.value == "combat"
        assert PartyStatus.SPLIT.value == "split"
        assert PartyStatus.RESTING.value == "resting"


# =============================================================================
# PartyMemberInfo
# =============================================================================


class TestPartyMemberInfo:
    def test_minimal(self):
        m = PartyMemberInfo(
            entity_id=uuid4(),
            joined_at=datetime.utcnow(),
        )
        assert m.role is None
        assert m.position is None

    def test_with_role(self):
        m = PartyMemberInfo(
            entity_id=uuid4(),
            role="scout",
            position=0,
            joined_at=datetime.utcnow(),
        )
        assert m.role == "scout"
        assert m.position == 0

    def test_negative_position_fails(self):
        with pytest.raises(Exception):
            PartyMemberInfo(
                entity_id=uuid4(),
                position=-1,
                joined_at=datetime.utcnow(),
            )


# =============================================================================
# PartyCreate
# =============================================================================


class TestPartyCreate:
    def test_minimal(self):
        p = PartyCreate(
            story_id=uuid4(),
            name="The Fellowship",
        )
        assert p.status == PartyStatus.TRAVELING  # default
        assert p.initial_member_ids == []  # default
        assert p.formation == []  # default
        assert p.active_pc_id is None

    def test_with_members(self):
        p = PartyCreate(
            story_id=uuid4(),
            name="Party",
            initial_member_ids=[uuid4(), uuid4(), uuid4()],
            active_pc_id=uuid4(),
            status=PartyStatus.COMBAT,
        )
        assert len(p.initial_member_ids) == 3
        assert p.status == PartyStatus.COMBAT

    def test_with_location(self):
        p = PartyCreate(
            story_id=uuid4(),
            name="Party",
            location_id=uuid4(),
        )
        assert p.location_id is not None

    def test_with_formation(self):
        eids = [uuid4(), uuid4(), uuid4()]
        p = PartyCreate(
            story_id=uuid4(),
            name="Party",
            formation=eids,
        )
        assert p.formation == eids


# =============================================================================
# PartyUpdate
# =============================================================================


class TestPartyUpdate:
    def test_empty(self):
        u = PartyUpdate()
        assert u.name is None
        assert u.status is None

    def test_status_change(self):
        u = PartyUpdate(status=PartyStatus.CAMPING, location_id=uuid4())
        assert u.status == PartyStatus.CAMPING


# =============================================================================
# PartyResponse
# =============================================================================


class TestPartyResponse:
    def test_minimal(self):
        p = PartyResponse(
            id=uuid4(),
            story_id=uuid4(),
            name="x",
            status=PartyStatus.TRAVELING,
            formation=[],
            created_at=datetime.utcnow(),
        )
        assert p.members == []  # default
        assert p.updated_at is None

    def test_with_members(self):
        member = PartyMemberInfo(
            entity_id=uuid4(),
            role="leader",
            joined_at=datetime.utcnow(),
        )
        p = PartyResponse(
            id=uuid4(),
            story_id=uuid4(),
            name="x",
            status=PartyStatus.IN_SCENE,
            formation=[member.entity_id],
            members=[member],
            created_at=datetime.utcnow(),
        )
        assert len(p.members) == 1


# =============================================================================
# AddPartyMember
# =============================================================================


class TestAddPartyMember:
    def test_minimal(self):
        req = AddPartyMember(
            party_id=uuid4(),
            entity_id=uuid4(),
        )
        assert req.role is None
        assert req.position is None

    def test_with_role(self):
        req = AddPartyMember(
            party_id=uuid4(),
            entity_id=uuid4(),
            role="scout",
            position=1,
        )
        assert req.role == "scout"
        assert req.position == 1

    def test_negative_position_fails(self):
        with pytest.raises(Exception):
            AddPartyMember(
                party_id=uuid4(),
                entity_id=uuid4(),
                position=-1,
            )


# =============================================================================
# RemovePartyMember
# =============================================================================


class TestRemovePartyMember:
    def test_basic(self):
        req = RemovePartyMember(
            party_id=uuid4(),
            entity_id=uuid4(),
        )
        assert req.party_id is not None
        assert req.entity_id is not None


# =============================================================================
# SetActivePC
# =============================================================================


class TestSetActivePC:
    def test_basic(self):
        req = SetActivePC(
            party_id=uuid4(),
            entity_id=uuid4(),
        )
        assert req.party_id is not None
        assert req.entity_id is not None

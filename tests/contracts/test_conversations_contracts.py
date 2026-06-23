"""
Contract tests for Conversation schemas.

Covers:
- ConversationMode enum: direct, actor, scene
- ConversationStatus enum: active, completed, abandoned
- ConversationTurn: single turn in conversation
- ConversationSessionCreate / Response / Update / Filter / ListResponse
- AppendConversationTurn: append a turn

Use Cases: Phase 1 NPC conversations
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

import pytest

from monitor_data.schemas.conversations import (
    ConversationMode,
    ConversationStatus,
    ConversationTurn,
    ConversationSessionCreate,
    ConversationSessionResponse,
    ConversationSessionUpdate,
    ConversationSessionFilter,
    ConversationSessionListResponse,
    AppendConversationTurn,
)


# =============================================================================
# Enums
# =============================================================================


class TestConversationModeEnum:
    def test_all_values(self):
        assert ConversationMode.DIRECT.value == "direct"
        assert ConversationMode.ACTOR.value == "actor"
        assert ConversationMode.SCENE.value == "scene"


class TestConversationStatusEnum:
    def test_all_values(self):
        assert ConversationStatus.ACTIVE.value == "active"
        assert ConversationStatus.COMPLETED.value == "completed"
        assert ConversationStatus.ABANDONED.value == "abandoned"


# =============================================================================
# ConversationTurn
# =============================================================================


class TestConversationTurn:
    def test_player_turn(self):
        t = ConversationTurn(
            turn_index=0,
            speaker_role="player",
            text="Hello, who are you?",
        )
        assert t.turn_index == 0
        assert t.entity_id is None  # default
        assert t.emotional_state is None  # default

    def test_npc_turn(self):
        t = ConversationTurn(
            turn_index=1,
            speaker_role="npc",
            entity_id=uuid4(),
            entity_name="Gandalf",
            text="I am a wizard.",
            emotional_state="calm",
        )
        assert t.entity_name == "Gandalf"
        assert t.emotional_state == "calm"

    def test_negative_turn_index_fails(self):
        with pytest.raises(Exception):
            ConversationTurn(
                turn_index=-1,
                speaker_role="player",
                text="x",
            )

    def test_empty_text_fails(self):
        with pytest.raises(Exception):
            ConversationTurn(
                turn_index=0,
                speaker_role="player",
                text="",
            )


# =============================================================================
# ConversationSessionCreate
# =============================================================================


class TestConversationSessionCreate:
    def test_minimal(self):
        req = ConversationSessionCreate(
            universe_id=uuid4(),
            mode=ConversationMode.DIRECT,
            npc_ids=[uuid4()],
        )
        assert req.scene_id is None
        assert req.metadata == {}

    def test_full(self):
        req = ConversationSessionCreate(
            universe_id=uuid4(),
            mode=ConversationMode.ACTOR,
            npc_ids=[uuid4(), uuid4()],
            scene_id=uuid4(),
            story_id=uuid4(),
            player_entity_id=uuid4(),
            metadata={"goal": "explore NPC motivations"},
        )
        assert len(req.npc_ids) == 2
        assert req.metadata["goal"] == "explore NPC motivations"

    def test_npc_ids_min_length(self):
        with pytest.raises(Exception):
            ConversationSessionCreate(
                universe_id=uuid4(),
                mode=ConversationMode.DIRECT,
                npc_ids=[],  # min_length=1
            )


# =============================================================================
# ConversationSessionResponse
# =============================================================================


class TestConversationSessionResponse:
    def test_minimal(self):
        resp = ConversationSessionResponse(
            conversation_id=uuid4(),
            universe_id=uuid4(),
            mode=ConversationMode.DIRECT,
            status=ConversationStatus.ACTIVE,
            npc_ids=[uuid4()],
            scene_id=None,
            story_id=None,
            player_entity_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert resp.turns == []  # default
        assert resp.completed_at is None  # default

    def test_with_turns(self):
        t = ConversationTurn(
            turn_index=0,
            speaker_role="player",
            text="Hi",
        )
        resp = ConversationSessionResponse(
            conversation_id=uuid4(),
            universe_id=uuid4(),
            mode=ConversationMode.ACTOR,
            status=ConversationStatus.COMPLETED,
            npc_ids=[uuid4()],
            scene_id=uuid4(),
            story_id=uuid4(),
            player_entity_id=uuid4(),
            turns=[t],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        assert len(resp.turns) == 1
        assert resp.completed_at is not None


# =============================================================================
# ConversationSessionUpdate
# =============================================================================


class TestConversationSessionUpdate:
    def test_empty(self):
        u = ConversationSessionUpdate()
        assert u.status is None
        assert u.metadata is None

    def test_complete(self):
        u = ConversationSessionUpdate(
            status=ConversationStatus.COMPLETED,
            metadata={"summary": "Good conversation"},
        )
        assert u.status == ConversationStatus.COMPLETED


# =============================================================================
# ConversationSessionFilter
# =============================================================================


class TestConversationSessionFilter:
    def test_defaults(self):
        f = ConversationSessionFilter()
        assert f.limit == 50
        assert f.offset == 0

    def test_with_filters(self):
        f = ConversationSessionFilter(
            universe_id=uuid4(),
            mode=ConversationMode.ACTOR,
            status=ConversationStatus.ACTIVE,
        )
        assert f.mode == ConversationMode.ACTOR

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            ConversationSessionFilter(limit=600)  # > 500


# =============================================================================
# ConversationSessionListResponse
# =============================================================================


class TestConversationSessionListResponse:
    def test_empty(self):
        r = ConversationSessionListResponse(
            sessions=[], total=0, limit=50, offset=0,
        )
        assert r.sessions == []


# =============================================================================
# AppendConversationTurn
# =============================================================================


class TestAppendConversationTurn:
    def test_player(self):
        req = AppendConversationTurn(
            speaker_role="player",
            text="Hello there",
        )
        assert req.entity_id is None

    def test_npc(self):
        req = AppendConversationTurn(
            speaker_role="npc",
            entity_id=uuid4(),
            entity_name="Aria",
            text="Greetings traveler",
            emotional_state="curious",
        )
        assert req.entity_name == "Aria"

    def test_invalid_role_fails(self):
        with pytest.raises(Exception):
            AppendConversationTurn(
                speaker_role="invalid",
                text="x",
            )

    def test_empty_text_fails(self):
        with pytest.raises(Exception):
            AppendConversationTurn(
                speaker_role="player",
                text="",
            )

"""Contract tests for the NPCDialogue schemas.

Verifies that npc_dialogues Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce numeric / length constraints,
- reject invalid enum values where applicable.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.base import DialogueStatus
from monitor_data.schemas.npc_dialogues import (
    AppendDialogueMessage,
    DialogueMessage,
    NPCDialogueCreate,
    NPCDialogueFilter,
    NPCDialogueListResponse,
    NPCDialogueResponse,
    NPCDialogueUpdate,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# =============================================================================
# DialogueMessage
# =============================================================================


class TestDialogueMessage:
    def test_minimal(self):
        msg = DialogueMessage(
            message_id=uuid4(),
            role="player",
            text="Hello!",
            timestamp=datetime.now(UTC),
        )
        assert msg.role == "player"
        assert msg.text == "Hello!"
        assert msg.memory_refs_read == []
        assert msg.npc_emotional_state is None
        assert msg.proposed_change_ids == []

    def test_full(self):
        msg = DialogueMessage(
            message_id=uuid4(),
            role="npc",
            text="Welcome, traveler.",
            timestamp=datetime.now(UTC),
            memory_refs_read=[uuid4(), uuid4()],
            npc_emotional_state="curious",
            proposed_change_ids=[uuid4()],
        )
        assert len(msg.memory_refs_read) == 2
        assert msg.npc_emotional_state == "curious"

    def test_text_required(self):
        with pytest.raises(ValidationError):
            DialogueMessage(
                message_id=uuid4(),
                role="player",
                timestamp=datetime.now(UTC),
            )

    def test_text_empty_rejected(self):
        with pytest.raises(ValidationError):
            DialogueMessage(
                message_id=uuid4(),
                role="player",
                text="",
                timestamp=datetime.now(UTC),
            )

    def test_text_too_long(self):
        with pytest.raises(ValidationError):
            DialogueMessage(
                message_id=uuid4(),
                role="player",
                text="x" * 10001,
                timestamp=datetime.now(UTC),
            )

    def test_role_too_long(self):
        with pytest.raises(ValidationError):
            DialogueMessage(
                message_id=uuid4(),
                role="x" * 21,
                text="hi",
                timestamp=datetime.now(UTC),
            )

    def test_emotional_state_too_long(self):
        with pytest.raises(ValidationError):
            DialogueMessage(
                message_id=uuid4(),
                role="npc",
                text="x",
                timestamp=datetime.now(UTC),
                npc_emotional_state="x" * 201,
            )


# =============================================================================
# NPCDialogueCreate
# =============================================================================


class TestNPCDialogueCreate:
    def test_minimal(self):
        d = NPCDialogueCreate(entity_id=uuid4(), universe_id=uuid4())
        assert d.embedded_in_scene is False
        assert d.persona_snapshot == {}
        assert d.opening_context is None
        assert d.player_entity_id is None
        assert d.scene_id is None
        assert d.story_id is None

    def test_with_persona(self):
        d = NPCDialogueCreate(
            entity_id=uuid4(),
            universe_id=uuid4(),
            persona_snapshot={"name": "Bartholomew", "role": "innkeeper"},
            opening_context="Bart is wiping down the bar.",
        )
        assert d.persona_snapshot["name"] == "Bartholomew"
        assert d.opening_context is not None

    def test_embedded_in_scene(self):
        d = NPCDialogueCreate(
            entity_id=uuid4(),
            universe_id=uuid4(),
            scene_id=uuid4(),
            embedded_in_scene=True,
        )
        assert d.embedded_in_scene is True
        assert d.scene_id is not None

    def test_opening_context_too_long(self):
        with pytest.raises(ValidationError):
            NPCDialogueCreate(
                entity_id=uuid4(),
                universe_id=uuid4(),
                opening_context="x" * 1001,
            )

    def test_required_entity_id(self):
        with pytest.raises(ValidationError):
            NPCDialogueCreate(universe_id=uuid4())  # type: ignore[call-arg]

    def test_required_universe_id(self):
        with pytest.raises(ValidationError):
            NPCDialogueCreate(entity_id=uuid4())  # type: ignore[call-arg]


# =============================================================================
# AppendDialogueMessage
# =============================================================================


class TestAppendDialogueMessage:
    def test_minimal(self):
        msg = AppendDialogueMessage(dialogue_id=uuid4(), role="player", text="Hi")
        assert msg.role == "player"
        assert msg.text == "Hi"
        assert msg.memory_refs_read == []
        assert msg.npc_emotional_state is None
        assert msg.proposed_change_ids == []

    def test_full(self):
        msg = AppendDialogueMessage(
            dialogue_id=uuid4(),
            role="npc",
            text="Greetings",
            memory_refs_read=[uuid4()],
            npc_emotional_state="happy",
            proposed_change_ids=[uuid4()],
        )
        assert msg.npc_emotional_state == "happy"

    def test_text_empty_rejected(self):
        with pytest.raises(ValidationError):
            AppendDialogueMessage(dialogue_id=uuid4(), role="player", text="")

    def test_text_too_long(self):
        with pytest.raises(ValidationError):
            AppendDialogueMessage(dialogue_id=uuid4(), role="player", text="x" * 10001)

    def test_role_too_long(self):
        with pytest.raises(ValidationError):
            AppendDialogueMessage(dialogue_id=uuid4(), role="x" * 21, text="x")

    def test_emotional_state_too_long(self):
        with pytest.raises(ValidationError):
            AppendDialogueMessage(
                dialogue_id=uuid4(),
                role="npc",
                text="x",
                npc_emotional_state="x" * 201,
            )

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            AppendDialogueMessage()  # type: ignore[call-arg]


# =============================================================================
# NPCDialogueUpdate
# =============================================================================


class TestNPCDialogueUpdate:
    def test_empty(self):
        u = NPCDialogueUpdate()
        assert u.status is None
        assert u.summary is None

    def test_with_status(self):
        u = NPCDialogueUpdate(status=DialogueStatus.ACTIVE)
        assert u.status == DialogueStatus.ACTIVE

    def test_with_summary(self):
        u = NPCDialogueUpdate(summary="Discussed the missing shipment")
        assert u.summary == "Discussed the missing shipment"

    def test_summary_too_long(self):
        with pytest.raises(ValidationError):
            NPCDialogueUpdate(summary="x" * 2001)

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            NPCDialogueUpdate(status="bogus")  # type: ignore[arg-type]


# =============================================================================
# NPCDialogueResponse
# =============================================================================


class TestNPCDialogueResponse:
    def _kwargs(self, **overrides):
        base = {
            "dialogue_id": uuid4(),
            "entity_id": uuid4(),
            "universe_id": uuid4(),
            "status": DialogueStatus.ACTIVE,
            "embedded_in_scene": False,
            "persona_snapshot": {},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        r = NPCDialogueResponse(**self._kwargs())
        assert r.player_entity_id is None
        assert r.scene_id is None
        assert r.story_id is None
        assert r.opening_context is None
        assert r.messages == []
        assert r.summary is None
        assert r.ended_at is None

    def test_with_messages(self):
        msg = DialogueMessage(
            message_id=uuid4(),
            role="player",
            text="hi",
            timestamp=datetime.now(UTC),
        )
        r = NPCDialogueResponse(**self._kwargs(messages=[msg]))
        assert len(r.messages) == 1

    def test_ended(self):
        ts = datetime.now(UTC)
        r = NPCDialogueResponse(
            **self._kwargs(
                status=DialogueStatus.ENDED,
                ended_at=ts,
                summary="Said goodbye",
            )
        )
        assert r.status == DialogueStatus.ENDED
        assert r.ended_at == ts

    def test_required_dialogue_id(self):
        with pytest.raises(ValidationError):
            NPCDialogueResponse(
                entity_id=uuid4(),
                universe_id=uuid4(),
                status=DialogueStatus.ACTIVE,
                embedded_in_scene=False,
                persona_snapshot={},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )


# =============================================================================
# NPCDialogueFilter
# =============================================================================


class TestNPCDialogueFilter:
    def test_defaults(self):
        f = NPCDialogueFilter()
        assert f.entity_id is None
        assert f.player_entity_id is None
        assert f.scene_id is None
        assert f.story_id is None
        assert f.status is None
        assert f.limit == 50
        assert f.offset == 0

    def test_with_filters(self):
        f = NPCDialogueFilter(
            entity_id=uuid4(),
            status=DialogueStatus.ENDED,
            limit=10,
        )
        assert f.status == DialogueStatus.ENDED
        assert f.limit == 10

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            NPCDialogueFilter(limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            NPCDialogueFilter(limit=201)

    def test_offset_min(self):
        with pytest.raises(ValidationError):
            NPCDialogueFilter(offset=-1)


# =============================================================================
# NPCDialogueListResponse
# =============================================================================


class TestNPCDialogueListResponse:
    def test_empty(self):
        r = NPCDialogueListResponse(dialogues=[], total=0, limit=50, offset=0)
        assert r.dialogues == []
        assert r.total == 0

    def test_with_dialogue(self):
        d = NPCDialogueResponse(
            dialogue_id=uuid4(),
            entity_id=uuid4(),
            universe_id=uuid4(),
            status=DialogueStatus.ACTIVE,
            embedded_in_scene=False,
            persona_snapshot={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        r = NPCDialogueListResponse(dialogues=[d], total=1, limit=50, offset=0)
        assert len(r.dialogues) == 1
        assert r.total == 1

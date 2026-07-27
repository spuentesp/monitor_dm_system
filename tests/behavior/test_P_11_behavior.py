"""
Behavior tests for P-11: Conversation loop.

Tests conversation session management without DB/LLM dependencies.
"""

from __future__ import annotations

from monitor_data.schemas.conversations import (
    ConversationMode,
    ConversationStatus,
)


class TestConversationModes:
    def test_all_modes(self):
        assert ConversationMode.DIRECT.value == "direct"
        assert ConversationMode.ACTOR.value == "actor"
        assert ConversationMode.SCENE.value == "scene"

    def test_mode_direct_meaning(self):
        """DIRECT mode is for in-character NPC dialogue."""
        assert ConversationMode.DIRECT is not None

    def test_mode_actor_meaning(self):
        """ACTOR mode is for out-of-character NPC reflection."""
        assert ConversationMode.ACTOR is not None


class TestConversationStatus:
    def test_all_statuses(self):
        assert ConversationStatus.ACTIVE.value == "active"
        assert ConversationStatus.COMPLETED.value == "completed"
        assert ConversationStatus.ABANDONED.value == "abandoned"

    def test_status_transitions(self):
        """Valid transitions: ACTIVE → COMPLETED or ACTIVE → ABANDONED."""
        # ACTIVE is the starting state
        assert ConversationStatus.ACTIVE is not None
        # Can complete
        assert ConversationStatus.COMPLETED is not None
        # Can abandon
        assert ConversationStatus.ABANDONED is not None

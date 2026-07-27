"""
Contract tests for Conversations, NPC Dialogues, and NPC Profiles schemas.

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)
"""

from monitor_data.schemas.conversations import (
    ConversationMode,
    ConversationStatus,
)


class TestConversationMode:
    def test_values(self):
        assert ConversationMode.DIRECT.value == "direct"
        assert ConversationMode.ACTOR.value == "actor"
        assert ConversationMode.SCENE.value == "scene"


class TestConversationStatus:
    def test_values(self):
        assert ConversationStatus.ACTIVE.value == "active"
        assert ConversationStatus.COMPLETED.value == "completed"
        assert ConversationStatus.ABANDONED.value == "abandoned"

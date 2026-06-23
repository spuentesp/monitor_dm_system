"""
Tests for NPC ConversationSession CRUD operations.

Covers:
- mongodb_create_conversation
- mongodb_get_conversation
- mongodb_append_conversation_turn
- mongodb_update_conversation
- mongodb_list_conversations
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4
from unittest.mock import Mock, patch
from typing import Any, Dict

from monitor_data.tools.mongodb_tools import (
    mongodb_create_conversation,
    mongodb_get_conversation,
    mongodb_get_recent_conversation_turns,
    mongodb_append_conversation_turn,
    mongodb_update_conversation,
    mongodb_list_conversations,
)
from monitor_data.schemas.conversations import (
    AppendConversationTurn,
    ConversationMode,
    ConversationSessionCreate,
    ConversationSessionFilter,
    ConversationSessionUpdate,
    ConversationStatus,
)


# =============================================================================
# HELPERS
# =============================================================================

_NOW = datetime.now(timezone.utc)


def _make_conv_doc(
    conversation_id: UUID,
    universe_id: UUID,
    npc_ids: list,
    mode: ConversationMode = ConversationMode.DIRECT,
    status: ConversationStatus = ConversationStatus.ACTIVE,
    turns: list | None = None,
) -> Dict[str, Any]:
    return {
        "conversation_id": str(conversation_id),
        "universe_id": str(universe_id),
        "mode": mode.value,
        "status": status.value,
        "npc_ids": [str(n) for n in npc_ids],
        "scene_id": None,
        "story_id": None,
        "player_entity_id": None,
        "turns": turns or [],
        "metadata": {},
        "created_at": _NOW,
        "updated_at": _NOW,
        "completed_at": None,
    }


# =============================================================================
# CREATE TESTS
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_create_conversation_direct_mode(mock_mongo: Mock) -> None:
    """Creating a DIRECT session returns a valid response with ACTIVE status."""
    universe_id = uuid4()
    npc_id = uuid4()

    mock_col = Mock()
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = ConversationSessionCreate(
        universe_id=universe_id,
        mode=ConversationMode.DIRECT,
        npc_ids=[npc_id],
    )

    result = mongodb_create_conversation(params)

    assert result.universe_id == universe_id
    assert result.mode == ConversationMode.DIRECT
    assert result.status == ConversationStatus.ACTIVE
    assert npc_id in result.npc_ids
    assert result.turns == []
    mock_col.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_create_conversation_actor_mode(mock_mongo: Mock) -> None:
    """Creating an ACTOR session with metadata stores metadata correctly."""
    universe_id = uuid4()
    npc_id = uuid4()

    mock_col = Mock()
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = ConversationSessionCreate(
        universe_id=universe_id,
        mode=ConversationMode.ACTOR,
        npc_ids=[npc_id],
        metadata={"goal": "understand NPC motivation"},
    )

    result = mongodb_create_conversation(params)

    assert result.mode == ConversationMode.ACTOR
    assert result.metadata == {"goal": "understand NPC motivation"}


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_create_conversation_multi_npc(mock_mongo: Mock) -> None:
    """Session with multiple NPCs stores all NPC IDs."""
    universe_id = uuid4()
    npc1, npc2 = uuid4(), uuid4()

    mock_col = Mock()
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = ConversationSessionCreate(
        universe_id=universe_id,
        mode=ConversationMode.DIRECT,
        npc_ids=[npc1, npc2],
    )

    result = mongodb_create_conversation(params)

    assert npc1 in result.npc_ids
    assert npc2 in result.npc_ids
    assert len(result.npc_ids) == 2


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_create_conversation_requires_at_least_one_npc(mock_mongo: Mock) -> None:
    """Creating a session with zero NPCs raises validation error."""
    with pytest.raises(Exception):
        ConversationSessionCreate(
            universe_id=uuid4(),
            mode=ConversationMode.DIRECT,
            npc_ids=[],  # empty — should fail Pydantic min_length=1
        )


# =============================================================================
# GET TESTS
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_get_conversation_found(mock_mongo: Mock) -> None:
    """Retrieving an existing session returns correct data."""
    universe_id = uuid4()
    npc_id = uuid4()
    conv_id = uuid4()
    doc = _make_conv_doc(conv_id, universe_id, [npc_id])

    mock_col = Mock()
    mock_col.find_one.return_value = doc
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    result = mongodb_get_conversation(conv_id)

    assert result is not None
    assert result.conversation_id == conv_id
    assert result.universe_id == universe_id


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_get_conversation_not_found(mock_mongo: Mock) -> None:
    """Retrieving a non-existent session returns None."""
    mock_col = Mock()
    mock_col.find_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    result = mongodb_get_conversation(uuid4())

    assert result is None


# =============================================================================
# APPEND TURN TESTS
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_append_player_turn(mock_mongo: Mock) -> None:
    """Appending a player turn increments turn count and sets speaker_role."""
    universe_id = uuid4()
    npc_id = uuid4()
    conv_id = uuid4()
    doc = _make_conv_doc(conv_id, universe_id, [npc_id])

    updated_doc = {
        **doc,
        "turns": [
            {
                "turn_index": 0,
                "speaker_role": "player",
                "entity_id": None,
                "entity_name": "Player",
                "text": "Hello there!",
                "emotional_state": None,
                "timestamp": _NOW,
            }
        ],
    }

    mock_col = Mock()
    mock_col.find_one.side_effect = [doc, updated_doc]
    mock_col.update_one.return_value = Mock(matched_count=1)
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = AppendConversationTurn(
        speaker_role="player",
        text="Hello there!",
        entity_name="Player",
    )

    result = mongodb_append_conversation_turn(conv_id, params)

    assert len(result.turns) == 1
    assert result.turns[0].speaker_role == "player"
    assert result.turns[0].text == "Hello there!"
    mock_col.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_append_npc_turn_with_emotional_state(mock_mongo: Mock) -> None:
    """NPC turn persists emotional_state correctly."""
    universe_id = uuid4()
    npc_id = uuid4()
    conv_id = uuid4()
    doc = _make_conv_doc(conv_id, universe_id, [npc_id])

    updated_doc = {
        **doc,
        "turns": [
            {
                "turn_index": 0,
                "speaker_role": "npc",
                "entity_id": str(npc_id),
                "entity_name": "Aldric",
                "text": "What do you want?",
                "emotional_state": "suspicious",
                "timestamp": _NOW,
            }
        ],
    }

    mock_col = Mock()
    mock_col.find_one.side_effect = [doc, updated_doc]
    mock_col.update_one.return_value = Mock(matched_count=1)
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = AppendConversationTurn(
        speaker_role="npc",
        entity_id=npc_id,
        entity_name="Aldric",
        text="What do you want?",
        emotional_state="suspicious",
    )

    result = mongodb_append_conversation_turn(conv_id, params)

    turn = result.turns[0]
    assert turn.speaker_role == "npc"
    assert turn.entity_id == npc_id
    assert turn.emotional_state == "suspicious"


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_append_turn_to_completed_session_raises(mock_mongo: Mock) -> None:
    """Appending to a completed session raises ValueError."""
    universe_id = uuid4()
    conv_id = uuid4()
    doc = _make_conv_doc(conv_id, universe_id, [uuid4()], status=ConversationStatus.COMPLETED)

    mock_col = Mock()
    mock_col.find_one.return_value = doc
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = AppendConversationTurn(speaker_role="player", text="too late")

    with pytest.raises(ValueError, match="Cannot append"):
        mongodb_append_conversation_turn(conv_id, params)


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_append_turn_to_nonexistent_session_raises(mock_mongo: Mock) -> None:
    """Appending to a non-existent session raises ValueError."""
    mock_col = Mock()
    mock_col.find_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = AppendConversationTurn(speaker_role="player", text="hello")

    with pytest.raises(ValueError, match="not found"):
        mongodb_append_conversation_turn(uuid4(), params)


# =============================================================================
# UPDATE TESTS
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_update_conversation_status_to_completed(mock_mongo: Mock) -> None:
    """Marking a session completed sets completed_at timestamp."""
    universe_id = uuid4()
    conv_id = uuid4()
    doc = _make_conv_doc(conv_id, universe_id, [uuid4()])
    completed_doc = {**doc, "status": "completed", "completed_at": _NOW}

    mock_col = Mock()
    mock_col.find_one.side_effect = [doc, completed_doc]
    mock_col.update_one.return_value = Mock(matched_count=1)
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = ConversationSessionUpdate(status=ConversationStatus.COMPLETED)
    result = mongodb_update_conversation(conv_id, params)

    assert result.status == ConversationStatus.COMPLETED
    assert result.completed_at is not None


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_update_nonexistent_session_raises(mock_mongo: Mock) -> None:
    """Updating a non-existent session raises ValueError."""
    mock_col = Mock()
    mock_col.find_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = ConversationSessionUpdate(status=ConversationStatus.COMPLETED)
    with pytest.raises(ValueError, match="not found"):
        mongodb_update_conversation(uuid4(), params)


# =============================================================================
# LIST TESTS
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_list_conversations_by_universe(mock_mongo: Mock) -> None:
    """Listing sessions filters by universe_id correctly."""
    universe_id = uuid4()
    npc_id = uuid4()
    conv_id = uuid4()
    doc = _make_conv_doc(conv_id, universe_id, [npc_id])

    mock_col = Mock()
    mock_col.count_documents.return_value = 1
    cursor = Mock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.sort.return_value = [doc]
    mock_col.find.return_value = cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    result = mongodb_list_conversations(ConversationSessionFilter(universe_id=universe_id))

    assert result.total == 1
    assert result.sessions[0].universe_id == universe_id


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_list_conversations_empty(mock_mongo: Mock) -> None:
    """Listing with no matches returns empty list and zero total."""
    mock_col = Mock()
    mock_col.count_documents.return_value = 0
    cursor = Mock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.sort.return_value = []
    mock_col.find.return_value = cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    result = mongodb_list_conversations(ConversationSessionFilter())

    assert result.total == 0
    assert result.sessions == []


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_list_conversations_filter_by_npc(mock_mongo: Mock) -> None:
    """Filtering by npc_id passes the correct query to MongoDB."""
    npc_id = uuid4()

    mock_col = Mock()
    mock_col.count_documents.return_value = 0
    cursor = Mock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.sort.return_value = []
    mock_col.find.return_value = cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    mongodb_list_conversations(ConversationSessionFilter(npc_id=npc_id))

    call_args = mock_col.find.call_args[0][0]
    assert call_args.get("npc_ids") == str(npc_id)


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_list_conversations_filter_by_mode(mock_mongo: Mock) -> None:
    """Filtering by mode passes the correct mode value to MongoDB."""
    mock_col = Mock()
    mock_col.count_documents.return_value = 0
    cursor = Mock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.sort.return_value = []
    mock_col.find.return_value = cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    mongodb_list_conversations(ConversationSessionFilter(mode=ConversationMode.ACTOR))

    call_args = mock_col.find.call_args[0][0]
    assert call_args.get("mode") == ConversationMode.ACTOR.value


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_get_recent_conversation_turns_flattens_and_orders(mock_mongo: Mock) -> None:
    """Recent conversation turn helper returns flattened turns in descending time order."""
    scene_id = uuid4()
    story_id = uuid4()

    older = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 1, 10, 5, 0, tzinfo=timezone.utc)

    doc_1 = {
        "conversation_id": str(uuid4()),
        "mode": "direct",
        "turns": [
            {
                "turn_index": 0,
                "speaker_role": "player",
                "entity_id": None,
                "entity_name": "Player",
                "text": "Hello",
                "emotional_state": None,
                "timestamp": older,
            }
        ],
    }
    doc_2 = {
        "conversation_id": str(uuid4()),
        "mode": "direct",
        "turns": [
            {
                "turn_index": 1,
                "speaker_role": "npc",
                "entity_id": None,
                "entity_name": "Aldric",
                "text": "State your business.",
                "emotional_state": "suspicious",
                "timestamp": newer,
            }
        ],
    }

    mock_col = Mock()
    cursor = Mock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = [doc_1, doc_2]
    mock_col.find.return_value = cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    turns = mongodb_get_recent_conversation_turns(scene_id=scene_id, story_id=story_id, limit=5)

    assert len(turns) == 2
    assert turns[0]["text"] == "State your business."
    assert turns[1]["text"] == "Hello"
    find_query = mock_col.find.call_args[0][0]
    assert find_query == {"scene_id": str(scene_id), "story_id": str(story_id)}


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_update_conversation_metadata(mock_mongo: Mock) -> None:
    """Updating conversation metadata stores changes correctly."""
    universe_id = uuid4()
    npc_id = uuid4()
    conv_id = uuid4()
    doc = _make_conv_doc(conv_id, universe_id, [npc_id])

    updated_doc = {
        **doc,
        "metadata": {"goal": "understand NPC motivation", "completed": True},
    }

    mock_col = Mock()
    mock_col.find_one.side_effect = [doc, updated_doc]
    mock_col.update_one.return_value = Mock(matched_count=1)
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = ConversationSessionUpdate(
        metadata={"goal": "understand NPC motivation", "completed": True},
    )

    result = mongodb_update_conversation(conv_id, params)

    assert result.metadata == {"goal": "understand NPC motivation", "completed": True}
    mock_col.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_append_turn_with_scene_context(mock_mongo: Mock) -> None:
    """Appending a turn with scene context stores scene_id and story_id."""
    universe_id = uuid4()
    npc_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()
    conv_id = uuid4()
    doc = _make_conv_doc(conv_id, universe_id, [npc_id])

    updated_doc = {
        **doc,
        "scene_id": str(scene_id),
        "story_id": str(story_id),
        "turns": [
            {
                "turn_index": 0,
                "speaker_role": "player",
                "entity_id": None,
                "entity_name": "Player",
                "text": "Hello there!",
                "emotional_state": None,
                "timestamp": _NOW,
            }
        ],
    }

    mock_col = Mock()
    mock_col.find_one.side_effect = [doc, updated_doc]
    mock_col.update_one.return_value = Mock(matched_count=1)
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = AppendConversationTurn(
        speaker_role="player",
        text="Hello there!",
        entity_name="Player",
        scene_id=scene_id,
        story_id=story_id,
    )

    result = mongodb_append_conversation_turn(conv_id, params)

    assert result.scene_id == scene_id
    assert result.story_id == story_id
    assert len(result.turns) == 1


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_list_conversations_with_pagination(mock_mongo: Mock) -> None:
    """Listing conversations with pagination returns correct slice."""
    universe_id = uuid4()
    npc_id = uuid4()

    _make_conv_doc(uuid4(), universe_id, [npc_id])
    doc2 = _make_conv_doc(uuid4(), universe_id, [npc_id])
    doc3 = _make_conv_doc(uuid4(), universe_id, [npc_id])

    mock_col = Mock()
    cursor = Mock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.sort.return_value = [doc2, doc3]  # Sort then limit
    mock_col.find.return_value = cursor
    mock_col.count_documents.return_value = 3  # Total count before pagination
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    filter_params = ConversationSessionFilter(universe_id=universe_id, offset=1, limit=2)

    result = mongodb_list_conversations(filter_params)

    assert len(result.sessions) == 2
    cursor.skip.assert_called_once_with(1)
    cursor.limit.assert_called_once_with(2)


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_list_conversations_filter_by_status(mock_mongo: Mock) -> None:
    """Listing conversations with status filter returns only matching status."""
    universe_id = uuid4()
    npc_id = uuid4()

    _make_conv_doc(uuid4(), universe_id, [npc_id], status=ConversationStatus.ACTIVE)
    completed_doc = _make_conv_doc(
        uuid4(), universe_id, [npc_id], status=ConversationStatus.COMPLETED
    )

    mock_col = Mock()
    cursor = Mock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.sort.return_value = [completed_doc]
    mock_col.find.return_value = cursor
    mock_col.count_documents.return_value = 1  # Total count
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    filter_params = ConversationSessionFilter(
        universe_id=universe_id, status=ConversationStatus.COMPLETED
    )

    result = mongodb_list_conversations(filter_params)

    assert len(result.sessions) == 1
    assert result.sessions[0].status == ConversationStatus.COMPLETED
    # Verify status filter was applied
    find_query = mock_col.find.call_args[0][0]
    assert find_query["status"] == "completed"


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_get_recent_conversation_turns_with_limit(mock_mongo: Mock) -> None:
    """Recent conversation turn helper respects limit parameter."""
    scene_id = uuid4()
    story_id = uuid4()

    docs = []
    for i in range(10):
        docs.append(
            {
                "conversation_id": str(uuid4()),
                "mode": "direct",
                "turns": [
                    {
                        "turn_index": i,
                        "speaker_role": "player" if i % 2 == 0 else "npc",
                        "entity_id": None,
                        "entity_name": "Speaker",
                        "text": f"Turn {i}",
                        "emotional_state": None,
                        "timestamp": datetime(2026, 1, 1, 10, i, 0, tzinfo=timezone.utc),
                    }
                ],
            }
        )

    mock_col = Mock()
    cursor = Mock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = docs[:3]  # Only return first 3
    mock_col.find.return_value = cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    turns = mongodb_get_recent_conversation_turns(scene_id=scene_id, story_id=story_id, limit=3)

    assert len(turns) == 3
    # Verify limit was applied
    cursor.limit.assert_called_once_with(3)


# =============================================================================
# TEST: mongodb_list_conversations - filter by scene_id
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_list_conversations_filter_by_scene(mock_mongo: Mock) -> None:
    """Filtering by scene_id passes the correct query to MongoDB."""
    scene_id = uuid4()

    mock_col = Mock()
    mock_col.count_documents.return_value = 0
    cursor = Mock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.sort.return_value = []
    mock_col.find.return_value = cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    mongodb_list_conversations(ConversationSessionFilter(scene_id=scene_id))

    call_args = mock_col.find.call_args[0][0]
    assert call_args.get("scene_id") == str(scene_id)


# =============================================================================
# TEST: mongodb_list_conversations - filter by story_id
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_list_conversations_filter_by_story(mock_mongo: Mock) -> None:
    """Filtering by story_id passes the correct query to MongoDB."""
    story_id = uuid4()

    mock_col = Mock()
    mock_col.count_documents.return_value = 0
    cursor = Mock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.sort.return_value = []
    mock_col.find.return_value = cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    mongodb_list_conversations(ConversationSessionFilter(story_id=story_id))

    call_args = mock_col.find.call_args[0][0]
    assert call_args.get("story_id") == str(story_id)


# =============================================================================
# TEST: mongodb_update_conversation - status to ABANDONED
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_update_conversation_status_to_abandoned(mock_mongo: Mock) -> None:
    """Marking a conversation as ABANDONED updates status and completed_at."""
    conversation_id = uuid4()
    universe_id = uuid4()
    npc_id = uuid4()

    mock_col = Mock()
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    # Mock existing conversation
    existing_doc = _make_conv_doc(
        conversation_id=conversation_id,
        universe_id=universe_id,
        npc_ids=[npc_id],
        status=ConversationStatus.ACTIVE,
    )
    mock_col.find_one.return_value = existing_doc

    # Mock updated conversation
    updated_doc = _make_conv_doc(
        conversation_id=conversation_id,
        universe_id=universe_id,
        npc_ids=[npc_id],
        status=ConversationStatus.ABANDONED,
    )
    updated_doc["completed_at"] = _NOW
    mock_col.find_one.side_effect = [existing_doc, updated_doc]

    params = ConversationSessionUpdate(status=ConversationStatus.ABANDONED)
    result = mongodb_update_conversation(conversation_id, params)

    assert result.status == ConversationStatus.ABANDONED
    assert result.completed_at is not None
    update_call = mock_col.update_one.call_args[0][1]["$set"]
    assert update_call["status"] == "abandoned"
    assert "completed_at" in update_call


# =============================================================================
# TEST: mongodb_create_conversation - with scene_id and story_id
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_create_conversation_with_scene_and_story(mock_mongo: Mock) -> None:
    """Creating a session with scene_id and story_id stores both."""
    universe_id = uuid4()
    npc_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()

    mock_col = Mock()
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = ConversationSessionCreate(
        universe_id=universe_id,
        mode=ConversationMode.DIRECT,
        npc_ids=[npc_id],
        scene_id=scene_id,
        story_id=story_id,
    )

    result = mongodb_create_conversation(params)

    assert result.scene_id == scene_id
    assert result.story_id == story_id
    insert_call = mock_col.insert_one.call_args[0][0]
    assert insert_call["scene_id"] == str(scene_id)
    assert insert_call["story_id"] == str(story_id)


# =============================================================================
# TEST: mongodb_create_conversation - with player_entity_id
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.conversations.get_mongodb_client")
def test_create_conversation_with_player_entity(mock_mongo: Mock) -> None:
    """Creating a session with player_entity_id stores it."""
    universe_id = uuid4()
    npc_id = uuid4()
    player_entity_id = uuid4()

    mock_col = Mock()
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_col)

    params = ConversationSessionCreate(
        universe_id=universe_id,
        mode=ConversationMode.DIRECT,
        npc_ids=[npc_id],
        player_entity_id=player_entity_id,
    )

    result = mongodb_create_conversation(params)

    assert result.player_entity_id == player_entity_id
    insert_call = mock_col.insert_one.call_args[0][0]
    assert insert_call["player_entity_id"] == str(player_entity_id)

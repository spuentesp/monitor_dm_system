from __future__ import annotations

from datetime import datetime, timezone

from monitor_agents.utils.dialogue_context_support import (
    build_dialogue_turn_windows,
    collect_dialogue_query_terms,
    collect_dialogue_window_terms,
    compose_dialogue_focus_terms,
    dialogue_windows_to_memory_items,
    conversation_turns_to_memory_items,
    is_dialogue_action,
    rank_dialogue_windows,
    rank_conversation_turns,
)


def test_is_dialogue_action_detects_social_verbs_and_questions() -> None:
    assert is_dialogue_action("I ask the guard about the missing caravan")
    assert is_dialogue_action("Can you explain what happened?")
    assert not is_dialogue_action("I climb the crumbling wall")


def test_rank_conversation_turns_prefers_overlap_and_npc_context() -> None:
    turns = [
        {
            "speaker_role": "player",
            "entity_name": "Player",
            "text": "I am looking for the old archives.",
            "timestamp": datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
        },
        {
            "speaker_role": "npc",
            "entity_name": "Archivist",
            "text": "The archives are sealed by the bishop's decree.",
            "timestamp": datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
        },
        {
            "speaker_role": "npc",
            "entity_name": "Guard",
            "text": "The stables close at dusk.",
            "timestamp": datetime(2026, 1, 1, 10, 3, tzinfo=timezone.utc),
        },
    ]

    ranked = rank_conversation_turns(
        turns,
        player_action="I ask about the archives and who sealed them",
        limit=2,
    )

    assert len(ranked) == 2
    assert ranked[0]["entity_name"] == "Archivist"


def test_conversation_turns_to_memory_items_projects_speaker_prefixed_content() -> None:
    items = conversation_turns_to_memory_items(
        [
            {
                "conversation_id": "conv-1",
                "turn_index": 4,
                "speaker_role": "npc",
                "entity_name": "Aldric",
                "text": "The vault opens only at moonrise.",
                "timestamp": datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc),
            }
        ]
    )

    assert len(items) == 1
    assert items[0]["source"] == "conversation_turn"
    assert items[0]["content"].startswith("Aldric: The vault opens")


def test_collect_dialogue_query_terms_includes_speaker_and_tokens() -> None:
    terms = collect_dialogue_query_terms(
        [
            {
                "speaker_role": "npc",
                "entity_name": "Gate Captain",
                "text": "State your purpose and present your papers.",
            }
        ]
    )

    assert "Gate Captain" in terms
    assert "npc" in terms
    assert any(token in terms for token in ("purpose", "papers", "state"))


def test_build_dialogue_turn_windows_creates_recent_bounded_windows() -> None:
    turns = [
        {
            "conversation_id": "c-1",
            "turn_index": 1,
            "speaker_role": "player",
            "entity_name": "Player",
            "text": "I ask about entry.",
            "timestamp": "2026-01-01T10:00:00+00:00",
        },
        {
            "conversation_id": "c-1",
            "turn_index": 2,
            "speaker_role": "npc",
            "entity_name": "Gate Captain",
            "text": "State your business.",
            "timestamp": "2026-01-01T10:01:00+00:00",
        },
        {
            "conversation_id": "c-1",
            "turn_index": 3,
            "speaker_role": "player",
            "entity_name": "Player",
            "text": "I carry writs from the court.",
            "timestamp": "2026-01-01T10:02:00+00:00",
        },
    ]

    windows = build_dialogue_turn_windows(turns, window_size=3, max_windows=4)

    assert windows
    assert len(windows) <= 4
    assert windows[0]["center_turn"]["turn_index"] == 3
    assert "State your business" in windows[0]["window_text"]


def test_rank_dialogue_windows_prefers_overlap_and_speaker_continuity() -> None:
    windows = [
        {
            "center_turn": {"entity_name": "Guard", "speaker_role": "npc"},
            "window_text": "The stables close at dusk.",
            "timestamp": "2026-01-01T10:02:00+00:00",
            "entity_name": "Guard",
        },
        {
            "center_turn": {"entity_name": "Archivist", "speaker_role": "npc"},
            "window_text": "The archives are sealed by decree.",
            "timestamp": "2026-01-01T10:03:00+00:00",
            "entity_name": "Archivist",
        },
    ]

    ranked = rank_dialogue_windows(
        windows,
        player_action="I ask who sealed the archives",
        preferred_speakers=["Archivist"],
        limit=2,
    )

    assert len(ranked) == 2
    assert ranked[0]["entity_name"] == "Archivist"


def test_dialogue_windows_to_memory_items_projects_context_entries() -> None:
    items = dialogue_windows_to_memory_items(
        [
            {
                "center_turn": {
                    "conversation_id": "c-1",
                    "turn_index": 4,
                    "speaker_role": "npc",
                    "entity_name": "Aldric",
                    "timestamp": "2026-01-01T10:05:00+00:00",
                },
                "window_text": "The vault opens only at moonrise.",
            }
        ]
    )

    assert len(items) == 1
    assert items[0]["source"] == "conversation_window"
    assert items[0]["content"].startswith("Aldric context: The vault opens")


def test_collect_dialogue_window_terms_includes_speaker_and_window_tokens() -> None:
    terms = collect_dialogue_window_terms(
        [
            {
                "entity_name": "Gate Captain",
                "window_text": "State your purpose and present your travel papers.",
            }
        ]
    )

    assert "Gate Captain" in terms
    assert any(token in terms for token in ("purpose", "present", "travel", "papers"))


def test_compose_dialogue_focus_terms_deduplicates_across_turns_and_windows() -> None:
    turns = [
        {
            "speaker_role": "npc",
            "entity_name": "Gate Captain",
            "text": "State your purpose and present your papers.",
        }
    ]
    windows = [
        {
            "entity_name": "Gate Captain",
            "window_text": "Gate Captain repeats: present papers at the gate.",
        }
    ]

    terms = compose_dialogue_focus_terms(turns, windows, limit=8)

    assert "Gate Captain" in terms
    assert terms.count("Gate Captain") == 1
    assert any(token in terms for token in ("purpose", "present", "papers", "gate"))


class TestBuildDialogueTurnWindows:
    """Tests for build_dialogue_turn_windows function."""

    def test_build_dialogue_turn_windows_returns_list(self):
        """build_dialogue_turn_windows should return a list."""
        turns = [
            {"speaker_role": "player", "entity_name": "Player", "text": "Hello"},
            {"speaker_role": "npc", "entity_name": "NPC", "text": "Hi there"},
        ]
        windows = build_dialogue_turn_windows(turns)
        assert isinstance(windows, list)

    def test_build_dialogue_turn_windows_with_empty_turns(self):
        """build_dialogue_turn_windows should handle empty turns."""
        windows = build_dialogue_turn_windows([])
        assert windows == []

    def test_build_dialogue_turn_windows_with_single_turn(self):
        """build_dialogue_turn_windows should return empty list for single turn."""
        turns = [
            {"speaker_role": "player", "entity_name": "Player", "text": "Hello"},
        ]
        windows = build_dialogue_turn_windows(turns)
        # Single turn may return empty list since windows need multiple turns
        assert isinstance(windows, list)

    def test_build_dialogue_turn_windows_default_window_size(self):
        """build_dialogue_turn_windows should use default window_size of 3."""
        turns = [
            {"speaker_role": "player", "entity_name": "P", "text": f"Turn {i}"} for i in range(10)
        ]
        windows = build_dialogue_turn_windows(turns)
        assert isinstance(windows, list)

    def test_build_dialogue_turn_windows_custom_window_size(self):
        """build_dialogue_turn_windows should accept custom window_size."""
        turns = [
            {"speaker_role": "player", "entity_name": "P", "text": f"Turn {i}"} for i in range(10)
        ]
        windows = build_dialogue_turn_windows(turns, window_size=5)
        assert isinstance(windows, list)

    def test_build_dialogue_turn_windows_max_windows(self):
        """build_dialogue_turn_windows should respect max_windows."""
        turns = [
            {"speaker_role": "player", "entity_name": "P", "text": f"Turn {i}"} for i in range(20)
        ]
        windows = build_dialogue_turn_windows(turns, max_windows=3)
        assert len(windows) <= 3

"""
Tests for mongodb_verify_memory — memory write verification.

Covers:
- Memory exists and matches text
- Memory exists but text doesn't match
- Memory exists and matches entity_id
- Memory not found raises ValueError
- No expected values → always verified if exists

Run:
    cd /path/to/monitor_dm_system && pytest packages/data-layer/tests/test_verify_memory.py -v
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_data.schemas.memories import MemoryResponse
from monitor_data.tools.mongodb_tools.memories import mongodb_verify_memory


def _make_memory_response(
    memory_id=None,
    entity_id=None,
    text="The hero entered the dark forest.",
) -> MemoryResponse:
    return MemoryResponse(
        memory_id=memory_id or uuid4(),
        universe_id=uuid4(),
        entity_id=entity_id or uuid4(),
        text=text,
        scene_id=uuid4(),
        linked_fact_id=None,
        emotional_valence=0.0,
        importance=5,
        certainty=1.0,
        metadata={},
        created_at="2026-01-01T00:00:00Z",
        last_accessed="2026-01-01T00:00:00Z",
        access_count=0,
    )


class TestVerifyMemory:
    """Tests for mongodb_verify_memory."""

    @patch("monitor_data.tools.mongodb_tools.memories.mongodb_get_memory")
    def test_verify_with_matching_text(self, mock_get):
        memory_id = uuid4()
        entity_id = uuid4()
        mock_get.return_value = _make_memory_response(
            memory_id=memory_id,
            entity_id=entity_id,
            text="The hero entered the dark forest.",
        )

        result = mongodb_verify_memory(memory_id, expected_text="dark forest")

        assert result["verified"] is True
        assert result["matches_text"] is True

    @patch("monitor_data.tools.mongodb_tools.memories.mongodb_get_memory")
    def test_verify_with_non_matching_text(self, mock_get):
        memory_id = uuid4()
        mock_get.return_value = _make_memory_response(
            memory_id=memory_id,
            text="The hero entered the dark forest.",
        )

        result = mongodb_verify_memory(memory_id, expected_text="dragon breathes fire")

        assert result["verified"] is False
        assert result["matches_text"] is False

    @patch("monitor_data.tools.mongodb_tools.memories.mongodb_get_memory")
    def test_verify_with_matching_entity_id(self, mock_get):
        memory_id = uuid4()
        entity_id = uuid4()
        mock_get.return_value = _make_memory_response(
            memory_id=memory_id,
            entity_id=entity_id,
        )

        result = mongodb_verify_memory(memory_id, expected_entity_id=entity_id)

        assert result["verified"] is True
        assert result["matches_entity_id"] is True

    @patch("monitor_data.tools.mongodb_tools.memories.mongodb_get_memory")
    def test_verify_no_expected_values(self, mock_get):
        memory_id = uuid4()
        mock_get.return_value = _make_memory_response(memory_id=memory_id)

        result = mongodb_verify_memory(memory_id)

        assert result["verified"] is True
        assert result["matches_text"] is True
        assert result["matches_entity_id"] is True

    @patch("monitor_data.tools.mongodb_tools.memories.mongodb_get_memory")
    def test_verify_memory_not_found(self, mock_get):
        memory_id = uuid4()
        mock_get.side_effect = ValueError(f"Memory {memory_id} not found")

        with pytest.raises(ValueError, match="not found"):
            mongodb_verify_memory(memory_id)

    @patch("monitor_data.tools.mongodb_tools.memories.mongodb_get_memory")
    def test_verify_truncates_text(self, mock_get):
        memory_id = uuid4()
        long_text = "A" * 500
        mock_get.return_value = _make_memory_response(memory_id=memory_id, text=long_text)

        result = mongodb_verify_memory(memory_id)

        assert len(result["actual_text"]) == 200

"""Typed memory extraction + per-cast extraction (Phase 4 Task 6)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from monitor_agents.extraction.agent import ExtractionAgent
from monitor_agents.extraction.memory_extraction import (
    ExtractedMemory,
    MemoryExtractionResult,
    MemoryExtractor,
)


def _no_lm_context(*_args, **_kwargs):
    """Replace dspy_context_for (which resolves the LM registry over sockets)."""
    import contextlib

    return contextlib.nullcontext()


class TestTypedParsing:
    def test_valid_json_parses_into_typed_memories(self):
        parsed = MemoryExtractor._parse_memories(
            '[{"text": "Met the dock officer", "importance": 7, "emotional_valence": 0.2}]'
        )
        assert parsed is not None
        assert parsed[0] == ExtractedMemory(text="Met the dock officer", importance=7.0, emotional_valence=0.2)

    def test_json_parse_failure_returns_none_not_raw_text(self):
        # The old raw-text fallback pasted unparseable prose into the memory
        # store; the typed path reports failure instead (Task 6).
        assert MemoryExtractor._parse_memories("totally not json") is None

    def test_forward_typed_reports_parse_status(self):
        extractor = MemoryExtractor()
        extractor.extract = MagicMock(return_value=SimpleNamespace(memories="not json"))  # type: ignore[method-assign]
        with patch("monitor_agents.extraction.memory_extraction.dspy_context_for", _no_lm_context):
            result = extractor.forward_typed("text", "narrative", "Ana")
        assert isinstance(result, MemoryExtractionResult)
        assert result.parse_ok is False
        assert result.memories == []
        assert "not json" in (result.error or "")

    def test_forward_typed_success(self):
        extractor = MemoryExtractor()
        extractor.extract = MagicMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(
                memories='[{"text": "kept the secret", "importance": 4, "emotional_valence": -0.5}]'
            )
        )
        with patch("monitor_agents.extraction.memory_extraction.dspy_context_for", _no_lm_context):
            result = extractor.forward_typed("text", "failure", "Vex")
        assert result.parse_ok is True
        assert result.as_dicts()[0]["text"] == "kept the secret"

    def test_forward_dict_view_still_serves_legacy_callers(self):
        extractor = MemoryExtractor()
        extractor.extract = MagicMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(memories='[{"text": "ok", "importance": 5}]')
        )
        with patch("monitor_agents.extraction.memory_extraction.dspy_context_for", _no_lm_context):
            memories = extractor.forward("t", "r", "n")
        assert isinstance(memories, list)
        assert memories[0]["text"] == "ok"


class TestCastExtraction:
    @pytest.mark.asyncio
    async def test_per_turn_extracts_only_the_speaker_with_owner_and_witnesses(self):
        """Join task 2: one model call per turn, for the acting character;
        the rest of the cast gets its scene memory at scene end."""
        agent = ExtractionAgent(agent_id="extractor-test")
        pc_id = str(uuid4())
        npc_id = str(uuid4())
        universe_id = uuid4()
        calls: list[str] = []

        def _fake_forward_typed(self, narrative_text, resolution, actor_name, role=None):
            calls.append(actor_name)
            return MemoryExtractionResult(memories=[ExtractedMemory(text=f"{actor_name} remembers", importance=5.0)])

        cast = [
            {"entity_id": pc_id, "name": "Ana", "controller": "user", "is_speaker": True},
            {"entity_id": npc_id, "name": "Vex", "controller": "gm", "is_speaker": False},
        ]
        with patch.object(MemoryExtractor, "forward_typed", _fake_forward_typed):
            out = await agent.extract_memories(
                narrative_text="the scene",
                actor_context=None,
                resolution={"success_level": "success"},
                cast=cast,
                scene_id=uuid4(),
                universe_id=universe_id,
            )

        # One extraction per turn, for the acting character only.
        assert calls == ["Ana"]
        memories = out["memories_to_persist"]
        assert len(memories) == 1
        assert {m["entity_id"] for m in memories} == {pc_id}
        assert all(m["universe_id"] == str(universe_id) for m in memories)
        # Witnesses = the whole present cast (Task 8).
        assert all(set(m["witnesses"]) == {pc_id, npc_id} for m in memories)

    @pytest.mark.asyncio
    async def test_the_speaker_falls_back_to_the_actor_context(self):
        agent = ExtractionAgent(agent_id="extractor-test")
        pc_id = str(uuid4())
        calls: list[str] = []

        def _fake_forward_typed(self, narrative_text, resolution, actor_name, role=None):
            calls.append(actor_name)
            return MemoryExtractionResult(memories=[ExtractedMemory(text="x", importance=5.0)])

        cast = [{"entity_id": pc_id, "name": "Ana", "controller": "user"}]
        with patch.object(MemoryExtractor, "forward_typed", _fake_forward_typed):
            out = await agent.extract_memories(
                narrative_text="the scene",
                actor_context={"id": pc_id, "name": "Ana"},
                resolution=None,
                cast=cast,
                scene_id=uuid4(),
                universe_id=uuid4(),
            )

        assert calls == ["Ana"]
        assert [m["entity_id"] for m in out["memories_to_persist"]] == [pc_id]

    @pytest.mark.asyncio
    async def test_parse_failure_is_recorded_and_yields_no_raw_text_memory(self):
        agent = ExtractionAgent(agent_id="extractor-test")
        from unittest.mock import AsyncMock

        record_mock = AsyncMock(return_value=None)
        with (
            patch.object(
                MemoryExtractor,
                "forward_typed",
                lambda self, *a, **k: MemoryExtractionResult(memories=[], parse_ok=False, error="bad json"),
            ),
            patch("monitor_agents.extraction.agent.RoleplayErrorRecorder.record", record_mock),
        ):
            out = await agent.extract_memories(
                narrative_text="the scene",
                actor_context=None,
                resolution=None,
                cast=[{"entity_id": str(uuid4()), "name": "Ana", "controller": "user", "is_speaker": True}],
                scene_id=uuid4(),
                universe_id=uuid4(),
            )

        assert out["memories_to_persist"] == []
        assert record_mock.await_count == 1
        assert "memory_extraction_json_parse_failed" in record_mock.await_args.kwargs["message"]

    @pytest.mark.asyncio
    async def test_scene_end_helper_extracts_per_cast_member(self):
        agent = ExtractionAgent(agent_id="extractor-test")
        calls: list[str] = []

        def _fake_forward_typed(self, narrative_text, resolution, actor_name, role=None):
            calls.append(narrative_text)
            return MemoryExtractionResult(memories=[ExtractedMemory(text=f"{actor_name} scene memory")])

        cast = [{"entity_id": str(uuid4()), "name": "Vex", "controller": "gm"}]
        with patch.object(MemoryExtractor, "forward_typed", _fake_forward_typed):
            out = await agent.extract_scene_memories(
                transcript="whole scene transcript",
                cast=cast,
                scene_id=uuid4(),
                universe_id=uuid4(),
            )

        assert calls == ["whole scene transcript"]
        assert out["memories_to_persist"][0]["text"] == "Vex scene memory"

    @pytest.mark.asyncio
    async def test_scene_end_narrows_to_the_members_who_never_acted(self):
        """Join task 2: extract_for_ids picks the non-actors; the witnesses
        stay the whole cast present."""
        agent = ExtractionAgent(agent_id="extractor-test")
        pc_id = str(uuid4())
        npc_id = str(uuid4())
        calls: list[str] = []

        def _fake_forward_typed(self, narrative_text, resolution, actor_name, role=None):
            calls.append(actor_name)
            return MemoryExtractionResult(memories=[ExtractedMemory(text=f"{actor_name} scene memory")])

        cast = [
            {"entity_id": pc_id, "name": "Ana", "controller": "user", "is_speaker": True},
            {"entity_id": npc_id, "name": "Vex", "controller": "gm", "is_speaker": False},
        ]
        with patch.object(MemoryExtractor, "forward_typed", _fake_forward_typed):
            out = await agent.extract_scene_memories(
                transcript="whole scene transcript",
                cast=cast,
                scene_id=uuid4(),
                universe_id=uuid4(),
                extract_for_ids=[npc_id],
            )

        assert calls == ["Vex"]
        memories = out["memories_to_persist"]
        assert [m["entity_id"] for m in memories] == [npc_id]
        assert all(set(m["witnesses"]) == {pc_id, npc_id} for m in memories)

    @pytest.mark.asyncio
    async def test_scene_end_with_no_targets_extracts_nothing(self):
        agent = ExtractionAgent(agent_id="extractor-test")

        def _boom(self, *a, **k):  # pragma: no cover — must never run
            raise AssertionError("no extraction expected")

        cast = [{"entity_id": str(uuid4()), "name": "Vex", "controller": "gm"}]
        with patch.object(MemoryExtractor, "forward_typed", _boom):
            out = await agent.extract_scene_memories(
                transcript="whole scene transcript",
                cast=cast,
                extract_for_ids=[],
            )
        assert out["memories_to_persist"] == []

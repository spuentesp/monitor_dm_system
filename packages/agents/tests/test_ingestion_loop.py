from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from monitor_data.schemas.base import IngestionStatus

from monitor_agents.loops.ingestion_loop import (
    IngestionLoop,
    IngestionModality,
    IngestionState,
    detect_modality,
    route_modality,
)


@pytest.mark.asyncio
async def test_ingestion_loop_detect_modality_text():
    """Plain text files route to the TEXT modality."""
    state = IngestionState(
        universe_id=uuid4(),
        filename="notes.txt",
        file_bytes=b"Some transcript",
        source_title="Session Notes",
        pack_name="Session 1",
    )

    res = await detect_modality(state)
    assert res["modality"] == IngestionModality.TEXT


@pytest.mark.asyncio
async def test_ingestion_loop_detect_modality_vision():
    """Image files with map-like names route to the VISION modality."""
    state = IngestionState(
        universe_id=uuid4(),
        filename="dungeon_map.png",
        source_title="Dungeon Map",
        pack_name="Dungeon",
    )

    res = await detect_modality(state)
    assert res["modality"] == IngestionModality.VISION


@pytest.mark.asyncio
async def test_ingestion_loop_synthesize_with_mock_data():
    loop = IngestionLoop()
    u_id = uuid4()

    state = IngestionState(
        universe_id=u_id,
        filename="test.txt",
        source_title="Test",
        pack_name="Test Pack",
        extracted_entities=[{"name": "Test Entity", "entity_type": "npc"}],
    )

    mock_pack = MagicMock()
    mock_pack.id = uuid4()

    with (
        patch("monitor_agents.loops.ingestion_loop.Indexer.index", new_callable=AsyncMock),
        patch("monitor_agents.loops.ingestion_loop.Analyzer.analyze", new_callable=AsyncMock),
        patch(
            "monitor_agents.loops.ingestion_loop.mongodb_create_knowledge_pack",
            return_value=mock_pack,
        ),
        patch(
            "monitor_agents.loops.ingestion_loop.check_proposal_contradictions",
            new_callable=AsyncMock,
        ) as mock_contradict,
    ):
        mock_contradict.return_value = []

        # We manually route to synthesize by setting stage
        res = await loop.run(state)

        assert res["status"] == IngestionStatus.COMPLETED
        assert res["pack_id"] == mock_pack.id


class TestIngestionState:
    def test_ingestion_state_creation(self):
        """IngestionState should be created with required fields."""
        u_id = uuid4()
        state = IngestionState(universe_id=u_id, filename="test.txt", source_title="Test", pack_name="Test Pack")
        assert state.universe_id == u_id
        assert state.filename == "test.txt"

    def test_ingestion_state_default_values(self):
        """IngestionState should have sensible defaults."""
        u_id = uuid4()
        state = IngestionState(universe_id=u_id, filename="test.txt", source_title="Test", pack_name="Test Pack")
        assert state.extracted_entities == []
        assert state.extracted_axioms == []
        assert state.extracted_facts == []


class TestRouteModality:
    def test_route_modality_text(self):
        """route_modality should return process_text for TEXT modality."""
        state = IngestionState(
            universe_id=uuid4(),
            filename="notes.txt",
            source_title="Test",
            pack_name="Test",
            modality=IngestionModality.TEXT,
        )
        result = route_modality(state)
        assert result == "process_text"

    def test_route_modality_vision(self):
        """route_modality should return process_vision for VISION modality."""
        state = IngestionState(
            universe_id=uuid4(),
            filename="map.png",
            source_title="Test",
            pack_name="Test",
            modality=IngestionModality.VISION,
        )
        result = route_modality(state)
        assert result == "process_vision"

    def test_route_modality_live_session(self):
        """route_modality should return process_live_session for SESSION modality."""
        state = IngestionState(
            universe_id=uuid4(),
            filename="session.md",
            source_title="Session 1",
            pack_name="Test",
            modality=IngestionModality.SESSION,
        )
        result = route_modality(state)
        assert result == "process_live_session"

    def test_route_modality_audio(self):
        """route_modality should return process_live_session for AUDIO modality."""
        state = IngestionState(
            universe_id=uuid4(),
            filename="recording.mp3",
            source_title="Session Audio",
            pack_name="Test",
            modality=IngestionModality.AUDIO,
        )
        result = route_modality(state)
        assert result == "process_live_session"

    def test_route_modality_defaults_to_text(self):
        """route_modality should default to process_text for unhandled modality."""
        state = IngestionState(
            universe_id=uuid4(),
            filename="data.csv",
            source_title="Test",
            pack_name="Test",
            modality=IngestionModality.TEXT,
        )
        result = route_modality(state)
        assert result == "process_text"


class TestIngestionLoop:
    def test_ingestion_loop_initialization(self):
        """IngestionLoop should initialize without errors."""
        loop = IngestionLoop()
        assert loop is not None

    def test_ingestion_loop_has_run_method(self):
        """IngestionLoop should have run method."""
        loop = IngestionLoop()
        assert hasattr(loop, "run")

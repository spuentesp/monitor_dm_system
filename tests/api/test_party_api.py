"""
Unit tests for the party router — group character management (P-13, DL-15).

Verifies that the party API endpoints correctly delegate to the Neo4j tools
and return proper responses.

Use Cases: P-13 (Party Management), DL-15 (Manage Parties)
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _setup_path() -> None:
    import sys
    from pathlib import Path

    backend_src = (
        Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
    )
    if str(backend_src) not in sys.path:
        sys.path.insert(0, str(backend_src))


class TestPartyAPI:
    """Tests for the party router endpoints."""

    @pytest.mark.asyncio
    async def test_create_party(self, monkeypatch):
        """POST /api/parties creates a party via Neo4j."""
        from monitor_ui.routers import parties

        party_id = uuid4()
        story_id = uuid4()
        member_id = uuid4()

        mock_response = MagicMock()
        mock_response.id = party_id
        mock_response.story_id = story_id
        mock_response.name = "The Brave Companions"
        mock_response.members = []

        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.parties.neo4j_create_party",
            lambda params: mock_response,
        )

        result = await parties.create_party(
            parties.PartyCreateRequest(
                story_id=str(story_id),
                name="The Brave Companions",
                initial_member_ids=[str(member_id)],
            )
        )

        assert result.name == "The Brave Companions"

    @pytest.mark.asyncio
    async def test_list_parties(self, monkeypatch):
        """GET /api/parties lists parties filtered by story_id."""
        from monitor_ui.routers import parties

        mock_party = MagicMock()
        mock_party.name = "Test Party"
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.parties.neo4j_list_parties",
            lambda params: [mock_party],
        )

        result = await parties.list_parties(story_id=str(uuid4()))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_parties_empty(self, monkeypatch):
        """GET /api/parties returns empty list on error."""
        from monitor_ui.routers import parties

        def failing_list(params):
            raise RuntimeError("DB down")

        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.parties.neo4j_list_parties",
            failing_list,
        )

        result = await parties.list_parties()
        assert result == []

    @pytest.mark.asyncio
    async def test_add_member(self, monkeypatch):
        """POST /api/parties/{id}/members adds a character to a party."""
        from monitor_ui.routers import parties

        party_id = uuid4()
        entity_id = uuid4()

        mock_response = MagicMock()
        mock_response.id = party_id
        mock_response.name = "Test Party"

        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.parties.neo4j_add_party_member",
            lambda params: mock_response,
        )

        result = await parties.add_member(
            str(party_id),
            parties.AddMemberRequest(entity_id=str(entity_id), role="scout"),
        )
        assert result.id == party_id

    @pytest.mark.asyncio
    async def test_remove_member(self, monkeypatch):
        """DELETE /api/parties/{id}/members/{entity_id} removes a character."""
        from monitor_ui.routers import parties

        party_id = uuid4()
        entity_id = uuid4()

        mock_response = MagicMock()
        mock_response.id = party_id

        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.parties.neo4j_remove_party_member",
            lambda params: mock_response,
        )

        result = await parties.remove_member(str(party_id), str(entity_id))
        assert result.id == party_id

    @pytest.mark.asyncio
    async def test_set_active_pc(self, monkeypatch):
        """POST /api/parties/{id}/active-pc sets the active PC."""
        from monitor_ui.routers import parties

        party_id = uuid4()
        entity_id = uuid4()

        mock_response = MagicMock()
        mock_response.id = party_id
        mock_response.active_pc_id = entity_id

        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.parties.neo4j_set_active_pc",
            lambda params: mock_response,
        )

        result = await parties.set_active_pc(
            str(party_id),
            parties.AddMemberRequest(entity_id=str(entity_id)),
        )
        assert result.active_pc_id == entity_id

    @pytest.mark.asyncio
    async def test_create_party_invalid_uuid(self, monkeypatch):
        """POST /api/parties rejects invalid UUIDs with 422."""
        from monitor_ui.routers import parties
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await parties.create_party(
                parties.PartyCreateRequest(
                    story_id="not-a-uuid",
                    name="Test",
                )
            )
        assert exc_info.value.status_code == 422
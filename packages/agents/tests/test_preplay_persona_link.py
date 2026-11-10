"""Persona-to-incarnation link written at pre-play (join Task 3).

Phase 2's pre-play writes the incarnation; it must pass ``source_persona_id``
so Phase 4's cast shows which persona stands behind each user character.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from monitor_agents.loops.preplay_finalize import _ensure_persona_link
from monitor_agents.loops.preplay_orchestrator import _persist_narrative_character


class TestEnsurePersonaLink:
    @pytest.mark.asyncio
    async def test_stamps_the_link_on_an_unlinked_incarnation_sheet(self):
        persona_id = str(uuid4())
        entity_id = str(uuid4())
        sheet = SimpleNamespace(sheet_id=uuid4(), source_persona_id=None)
        listing = SimpleNamespace(sheets=[sheet])
        update = MagicMock(return_value=None)

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_list_character_sheets",
                MagicMock(return_value=listing),
            ),
            patch("monitor_data.tools.mongodb_tools.mongodb_update_character_sheet", update),
        ):
            await _ensure_persona_link({"persona_id": persona_id, "character_id": entity_id})

        assert update.call_count == 1
        sheet_id, params = update.call_args.args
        assert sheet_id == sheet.sheet_id
        assert params.source_persona_id == persona_id

    @pytest.mark.asyncio
    async def test_an_existing_link_is_never_overwritten(self):
        persona_id = str(uuid4())
        entity_id = str(uuid4())
        sheet = SimpleNamespace(sheet_id=uuid4(), source_persona_id=str(uuid4()))
        listing = SimpleNamespace(sheets=[sheet])
        update = MagicMock(return_value=None)

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_list_character_sheets",
                MagicMock(return_value=listing),
            ),
            patch("monitor_data.tools.mongodb_tools.mongodb_update_character_sheet", update),
        ):
            await _ensure_persona_link({"persona_id": persona_id, "character_id": entity_id})

        assert update.call_count == 0

    @pytest.mark.asyncio
    async def test_no_persona_or_no_character_is_a_no_op(self):
        update = MagicMock(return_value=None)
        listing = MagicMock(return_value=SimpleNamespace(sheets=[]))

        with (
            patch("monitor_data.tools.mongodb_tools.mongodb_list_character_sheets", listing),
            patch("monitor_data.tools.mongodb_tools.mongodb_update_character_sheet", update),
        ):
            await _ensure_persona_link({"persona_id": str(uuid4())})
            await _ensure_persona_link({"character_id": str(uuid4())})
            await _ensure_persona_link({})

        assert listing.call_count == 0
        assert update.call_count == 0

    @pytest.mark.asyncio
    async def test_a_failed_write_never_blocks_the_opening(self):
        persona_id = str(uuid4())
        entity_id = str(uuid4())

        with patch(
            "monitor_data.tools.mongodb_tools.mongodb_list_character_sheets",
            MagicMock(side_effect=RuntimeError("mongo down")),
        ):
            # No exception escapes — the opening proceeds without the link.
            await _ensure_persona_link({"persona_id": persona_id, "character_id": entity_id})


class TestIncarnationWriteCarriesThePersona:
    def test_the_narrative_character_preview_passes_source_persona_id(self):
        captured: dict = {}

        def _fake_persist(session, preview, source_meta):
            captured.update(preview)
            return None

        session = {"persona_id": str(uuid4()), "speaker_label": "Ana"}
        with patch(
            "monitor_agents.loops.preplay_orchestrator.persist_session_character",
            _fake_persist,
        ):
            _persist_narrative_character(session, {"character_name": "Ana", "concept": "sailor"})

        assert captured["source_persona_id"] == session["persona_id"]

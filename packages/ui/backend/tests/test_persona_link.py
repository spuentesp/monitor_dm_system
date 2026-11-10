"""Persona-to-incarnation link on the character record (Phase 4 Task 4)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from monitor_ui.routers import character_resolution as cr
from monitor_ui.routers import character_storage as cs


class TestCharacterStorage:
    def test_create_character_persists_source_persona_id(self):
        coll = MagicMock()
        persona_id = str(uuid4())
        with patch.object(cs, "_coll", lambda: coll):
            doc = cs.create_character(
                {
                    "name": "Ana",
                    "source_persona_id": persona_id,
                    "owner_id": "owner-1",
                }
            )
        assert doc["source_persona_id"] == persona_id
        inserted = coll.insert_one.call_args.args[0]
        assert inserted["source_persona_id"] == persona_id


class TestResolvePersonaLink:
    def test_standalone_character_resolves_persona_name_via_real_callee(self):
        persona_id = str(uuid4())
        char_id = str(uuid4())
        calls: list[Any] = []

        def _get_character(raw_id, *args, **kwargs):
            calls.append(str(raw_id))
            if str(raw_id) == char_id:
                return {"id": char_id, "name": "Ana", "source_persona_id": persona_id}
            return {"id": persona_id, "name": "Ana Persona"}

        with patch.object(cr, "mongodb_get_character", _get_character):
            link = cr.resolve_persona_link(char_id)

        # The real callee was invoked with the persona id (Task 4 read side).
        assert link == {"persona_id": persona_id, "persona_name": "Ana Persona"}
        assert persona_id in calls

    def test_character_without_persona_returns_none(self):
        with patch.object(cr, "mongodb_get_character", lambda raw_id, *a, **k: {"id": raw_id, "name": "X"}):
            assert cr.resolve_persona_link(str(uuid4())) is None

    def test_entity_incarnation_resolves_via_character_sheet(self):
        entity_id = str(uuid4())
        persona_id = str(uuid4())
        sheet = MagicMock()
        sheet.source_persona_id = persona_id
        listing = MagicMock()
        listing.sheets = [sheet]

        def _get_character(raw_id, *args, **kwargs):
            return {"id": persona_id, "name": "Ana Persona"} if str(raw_id) == persona_id else None

        with (
            patch.object(cr, "mongodb_get_character", _get_character),
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_list_character_sheets",
                MagicMock(return_value=listing),
            ) as list_sheets,
        ):
            link = cr.resolve_persona_link(entity_id, source="entity")

        assert link == {"persona_id": persona_id, "persona_name": "Ana Persona"}
        assert list_sheets.call_count == 1

    def test_resolve_controlled_personas_maps_roster(self):
        char_id = str(uuid4())
        persona_id = str(uuid4())

        def _get_character(raw_id, *args, **kwargs):
            if str(raw_id) == char_id:
                return {"id": char_id, "name": "Ana", "source_persona_id": persona_id}
            return {"id": persona_id, "name": "Ana Persona"}

        with patch.object(cr, "mongodb_get_character", _get_character):
            out = cr.resolve_controlled_personas([char_id, "  ", str(uuid4())])

        assert out == {char_id: {"persona_id": persona_id, "persona_name": "Ana Persona"}}


class TestResolveActorCharacter:
    def test_actor_context_carries_the_persona(self):
        persona_id = str(uuid4())
        char_id = str(uuid4())

        def _get_character(raw_id, *args, **kwargs):
            if str(raw_id) == char_id:
                return {
                    "id": char_id,
                    "name": "Ana",
                    "personality": "",
                    "description": "",
                    "is_ooc_persona": False,
                    "source_persona_id": persona_id,
                }
            return {"id": persona_id, "name": "Ana Persona"}

        session = {"speaker_character_id": char_id}
        with patch.object(cr, "mongodb_get_character", _get_character):
            ctx = cr.resolve_actor_character(session)

        assert ctx is not None
        assert ctx.persona_id == persona_id
        assert ctx.persona_name == "Ana Persona"
        assert ctx.name == "Ana"

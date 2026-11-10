"""Tests for the persona-template bridge (character templates plan, Q2):
a saved standalone-character persona pre-seeds Session Zero instead of a
blank interview, and the resulting CharacterSheet keeps a back-reference to
the source persona id.

Covers:
- _seed_answers_from_persona: maps a persona doc into Session Zero
  prior_answers, excluding gm_notes (author-facing, not player-stated).
- persist_session_character: injects source_persona_id into the preview
  dict from session["persona_id"] before persisting, without clobbering an
  already-present value.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_agents.loops.preplay_support import _seed_answers_from_persona
from monitor_agents.loops.preplay_support import persist_session_character
from monitor_agents.loops.preplay_support import _persist_generated_entity

# =============================================================================
# _seed_answers_from_persona
# =============================================================================


class TestSeedAnswersFromPersona:
    def test_maps_all_player_facing_fields(self):
        persona = {
            "name": "Rook",
            "description": "A wary scavenger from the ash flats.",
            "personality": "Guarded, dry humor, loyal once trust is earned.",
            "first_message": "*eyes you warily* You're not from around here.",
            "gm_notes": "Secretly working for the syndicate.",
        }
        seed = _seed_answers_from_persona(persona)

        answers_by_category = {a["category"]: a["answer"] for a in seed}
        assert answers_by_category["name"] == "Rook"
        assert answers_by_category["origin"] == "A wary scavenger from the ash flats."
        assert "Guarded" in answers_by_category["custom"] or any("Guarded" in a["answer"] for a in seed)
        assert any("not from around here" in a["answer"] for a in seed)

    def test_excludes_gm_notes(self):
        """gm_notes is author-facing guidance for the AI, not player-stated
        characterization -- it must never appear in the seeded answers."""
        persona = {
            "name": "Rook",
            "description": "A scavenger.",
            "personality": "",
            "first_message": "",
            "gm_notes": "Secretly working for the syndicate.",
        }
        seed = _seed_answers_from_persona(persona)

        assert not any("syndicate" in a["answer"] for a in seed)
        assert not any("gm_notes" in a["category"] for a in seed)

    def test_skips_empty_fields(self):
        persona = {
            "name": "Rook",
            "description": "",
            "personality": "",
            "first_message": "",
        }
        seed = _seed_answers_from_persona(persona)

        assert len(seed) == 1
        assert seed[0]["answer"] == "Rook"

    def test_empty_persona_produces_no_seed(self):
        assert _seed_answers_from_persona({}) == []

    def test_every_seed_entry_has_question_answer_category(self):
        persona = {
            "name": "Rook",
            "description": "A scavenger.",
            "personality": "Guarded.",
            "first_message": "Hello.",
        }
        seed = _seed_answers_from_persona(persona)

        assert len(seed) == 4
        for entry in seed:
            assert set(entry.keys()) == {"question", "answer", "category"}
            assert entry["question"]
            assert entry["answer"]
            assert entry["category"]

    def test_seeds_voice_and_backstory_beats(self):
        """G-6 Phase 2: the portable-template fields seed Session Zero too."""
        persona = {
            "name": "Rook",
            "description": "A scavenger.",
            "personality": "Guarded.",
            "voice": "Speaks in clipped, wary sentences.",
            "backstory_beats": ["Lost a city to a bargain", "Never pays his debts"],
        }
        seed = _seed_answers_from_persona(persona)

        answers = [a["answer"] for a in seed]
        assert any("clipped, wary sentences" in answer for answer in answers)
        # The beats are seeded as one ordered answer.
        beats = next((a for a in seed if a["category"] == "background"), None)
        assert beats is not None
        assert "Lost a city to a bargain" in beats["answer"]
        assert "Never pays his debts" in beats["answer"]

    def test_template_concept_seeds_the_origin_answer(self):
        """A template carries its summary in `concept`, not `description`."""
        template = {
            "name": "Varys",
            "concept": "A spymaster who is never where you expect",
            "personality": "Charming.",
            "voice": "Speaks in parables.",
        }
        seed = _seed_answers_from_persona(template)

        answers_by_category = {a["category"]: a["answer"] for a in seed}
        assert answers_by_category["origin"] == "A spymaster who is never where you expect"
        assert any("parables" in a["answer"] for a in seed)

    def test_description_wins_over_concept(self):
        persona = {
            "name": "Rook",
            "description": "A scavenger from the ash flats.",
            "concept": "A template concept",
        }
        seed = _seed_answers_from_persona(persona)

        answers_by_category = {a["category"]: a["answer"] for a in seed}
        assert answers_by_category["origin"] == "A scavenger from the ash flats."


# =============================================================================
# persist_session_character — source_persona_id back-reference
# =============================================================================


def test_generated_character_persists_template_prose():
    world_id, entity_id, sheet_id = uuid4(), uuid4(), uuid4()
    preview = {
        "name": "Varys",
        "concept": "Spy",
        "backstory": "Lost a city",
        "personality": "Patient",
        "voice": "Quiet",
    }
    with (
        patch(
            "monitor_data.tools.neo4j_tools.entities.neo4j_create_entity",
            return_value=SimpleNamespace(id=entity_id, universe_id=world_id),
        ) as create_entity,
        patch(
            "monitor_data.tools.mongodb_tools.mongodb_create_character_sheet",
            return_value=SimpleNamespace(sheet_id=sheet_id),
        ),
    ):
        _persist_generated_entity(universe_id=str(world_id), preview=preview, source_meta={})
    properties = create_entity.call_args.args[0].properties
    assert {key: properties[key] for key in ("concept", "backstory", "personality", "voice")} == {
        key: preview[key] for key in ("concept", "backstory", "personality", "voice")
    }


class TestPersistSessionCharacterPersonaBackref:
    @pytest.fixture(autouse=True)
    def _usage_counter(self):
        with patch(
            "monitor_data.tools.mongodb_tools.character_templates.mongodb_increment_character_template_usage"
        ) as counter:
            yield counter

    def test_injects_source_persona_id_from_session(self, _usage_counter):
        session = {"universe_id": "u-1", "persona_id": "persona-42"}
        preview = {"kind": "pc", "name": "Rook"}

        with patch(
            "monitor_agents.loops.preplay_support._persist_generated_entity",
            return_value={"entity_id": "e-1", "sheet_id": "s-1"},
        ) as mock_persist:
            persist_session_character(session, preview, {})

        called_preview = mock_persist.call_args.kwargs["preview"]
        assert called_preview["source_persona_id"] == "persona-42"
        _usage_counter.assert_called_once_with("persona-42")

    def test_does_not_increment_usage_when_no_character_was_saved(self, _usage_counter):
        with patch(
            "monitor_agents.loops.preplay_support._persist_generated_entity",
            return_value={},
        ):
            persist_session_character({"universe_id": "u-1", "persona_id": "p-1"}, {}, {})
        _usage_counter.assert_not_called()

    def test_no_persona_id_on_session_leaves_preview_untouched(self):
        session = {"universe_id": "u-1"}
        preview = {"kind": "pc", "name": "Rook"}

        with patch(
            "monitor_agents.loops.preplay_support._persist_generated_entity",
            return_value={"entity_id": "e-1", "sheet_id": "s-1"},
        ) as mock_persist:
            persist_session_character(session, preview, {})

        called_preview = mock_persist.call_args.kwargs["preview"]
        assert "source_persona_id" not in called_preview

    def test_does_not_clobber_an_already_present_source_persona_id(self):
        session = {"universe_id": "u-1", "persona_id": "persona-42"}
        preview = {
            "kind": "pc",
            "name": "Rook",
            "source_persona_id": "persona-explicit",
        }

        with patch(
            "monitor_agents.loops.preplay_support._persist_generated_entity",
            return_value={"entity_id": "e-1", "sheet_id": "s-1"},
        ) as mock_persist:
            persist_session_character(session, preview, {})

        called_preview = mock_persist.call_args.kwargs["preview"]
        assert called_preview["source_persona_id"] == "persona-explicit"

    def test_original_preview_dict_is_not_mutated(self):
        """persist_session_character must not mutate the caller's preview
        dict in place -- other code may still hold a reference to it."""
        session = {"universe_id": "u-1", "persona_id": "persona-42"}
        preview = {"kind": "pc", "name": "Rook"}

        with patch(
            "monitor_agents.loops.preplay_support._persist_generated_entity",
            return_value={"entity_id": "e-1", "sheet_id": "s-1"},
        ):
            persist_session_character(session, preview, {})

        assert "source_persona_id" not in preview

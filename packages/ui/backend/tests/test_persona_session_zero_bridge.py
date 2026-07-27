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

from unittest.mock import patch

from monitor_agents.loops.preplay_support import _seed_answers_from_persona
from monitor_agents.loops.preplay_support import persist_session_character

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


# =============================================================================
# persist_session_character — source_persona_id back-reference
# =============================================================================


class TestPersistSessionCharacterPersonaBackref:
    def test_injects_source_persona_id_from_session(self):
        session = {"universe_id": "u-1", "persona_id": "persona-42"}
        preview = {"kind": "pc", "name": "Rook"}

        with patch(
            "monitor_agents.loops.preplay_support._persist_generated_entity",
            return_value={"entity_id": "e-1", "sheet_id": "s-1"},
        ) as mock_persist:
            persist_session_character(session, preview, {})

        called_preview = mock_persist.call_args.kwargs["preview"]
        assert called_preview["source_persona_id"] == "persona-42"

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

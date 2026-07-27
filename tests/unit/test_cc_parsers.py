"""Hermetic tests for character-creation structural field extraction.

`_extract_field`/`_FIELD_KEYS_BY_STEP` split a multi-line LLM dump into
the line relevant to the current step by fixed field-name keys (e.g.
"Dot Assignments: ..." for the attributes step). This is structural
parsing of a known key-prefix format, not interpretation of ambiguous
free text -- the actual meaning of the player's answer (attribute
values, skill picks) is now extracted by DSPy modules
(`_extract_attribute_and_resource_assignments`, `_parse_skill_choices`
in `character_creation_loop.py`), covered by
`tests/behavior/test_character_creation_loop_choreography_behavior.py`.
"""

from __future__ import annotations


def _import_field_helpers():
    from monitor_agents.loops.character_creation_loop import (
        _FIELD_KEYS_BY_STEP,
        _extract_field,
    )

    return _extract_field, _FIELD_KEYS_BY_STEP


def test_field_keys_by_step_isolates_dot_assignments_line() -> None:
    """A multi-field LLM dump must be sliced to just the current step's
    line before any further parsing happens."""
    extract_field, field_keys = _import_field_helpers()
    full_dump = (
        "Name: Kael Thorne\n"
        "Clan: Torene\n"
        "Class: Bruiser\n"
        "Dot Assignments: 5 Willpower, 3 Stamina, 2 Strength\n"
        "Skill Picks: Melee Combat (Excellence), Close Quarter Combat (Great)\n"
        "Discipline Names: Iron Will, Brutal Impact"
    )
    assert "generate_attributes" in field_keys
    assert "assign_attributes" in field_keys
    assert "choose_skills" in field_keys

    dot_line = extract_field(full_dump, *field_keys["generate_attributes"])
    assert dot_line == "5 Willpower, 3 Stamina, 2 Strength"

    skill_line = extract_field(full_dump, *field_keys["choose_skills"])
    assert skill_line == "Melee Combat (Excellence), Close Quarter Combat (Great)"


def test_extract_field_returns_none_when_key_absent() -> None:
    extract_field, field_keys = _import_field_helpers()
    out = extract_field(
        "Name: Kael Thorne\nClass: Bruiser", *field_keys["choose_skills"]
    )
    assert out is None

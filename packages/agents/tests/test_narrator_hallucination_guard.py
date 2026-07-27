"""[G-4] Narrator hallucination guard.

Empty-sheet characters used to be silently omitted from the actor block,
which let the narrator invent clan / class / faction / items that the
player never picked. See ``docs/architecture/GAP_REMEDIATION_PLAN.md``
G-4 and ``docs/STATUS.md`` ([G-4] shipped 2026-07-23).

The fix lives in ``monitor_agents.narrator.agent.Narrator._build_actor_block``:
- when every identity-bearing field on the actor is empty/None, prepend
  a ``[CHARACTER SHEET IS EMPTY]`` sentinel so the prompt-level rule
  against inventing character facts actually fires.
- otherwise return the standard ACTOR PROFILE block (no sentinel).

These tests pin the *behaviour* of the helper across the relevant cases.
Per ``feedback_no_brittle_patches``, we avoid reintroducing regex/keyword
parsing — the actor block is a plain Python builder.
"""

from __future__ import annotations

import pytest

from monitor_agents.narrator.agent import Narrator

SENTINEL = "[CHARACTER SHEET IS EMPTY"


# --------------------------------------------------------------------------- #
# None / falsy actors
# --------------------------------------------------------------------------- #


def test_build_actor_block_returns_empty_string_when_actor_is_none() -> None:
    """``None`` actor must return ``""`` — no block, no sentinel."""
    assert Narrator._build_actor_block(None) == ""


def test_build_actor_block_returns_empty_string_when_actor_is_empty_dict() -> None:
    """``{}`` actor has no name/role/content — still no sentinel, but no block either.

    The empty-dict shape carries no information worth surfacing; the
    narrator already has the player's own description.
    """
    assert Narrator._build_actor_block({}) == ""


# --------------------------------------------------------------------------- #
# Empty-sheet detection — the G-4 fix
# --------------------------------------------------------------------------- #


def test_empty_sheet_triggers_sentinel() -> None:
    """Every identity-bearing field empty → sentinel prepended."""
    block = Narrator._build_actor_block(
        {
            "name": "Kael",
            "role": "pc",
            "personality": "",
            "state_tags": [],
            "stats": {},
            "inventory": [],
            "conditions": [],
        }
    )
    assert block.startswith("\n\n[CHARACTER SHEET IS EMPTY")
    assert "do not invent identity facts" in block
    # Still surfaces what little we know (role)
    assert "ACTOR PROFILE (Kael)" in block
    assert "- Role: pc" in block


def test_empty_sheet_triggers_sentinel_with_none_values() -> None:
    """Some players leave fields as None — those count as empty too."""
    block = Narrator._build_actor_block(
        {
            "name": "Kael",
            "role": "pc",
            "personality": None,
            "state_tags": None,
            "stats": None,
            "inventory": None,
            "conditions": None,
        }
    )
    assert SENTINEL in block


def test_populated_sheet_does_not_trigger_sentinel() -> None:
    """A real actor with at least one fact populated must NOT carry the sentinel."""
    block = Narrator._build_actor_block(
        {
            "name": "Kael",
            "role": "pc",
            "personality": "sardonic salvage engineer",
            "stats": {"STR": 12, "INT": 16},
            "inventory": ["laser cutter", "combat knife"],
            "conditions": ["hungry"],
            "state_tags": [],
        }
    )
    assert SENTINEL not in block
    assert "ACTOR PROFILE (Kael)" in block
    assert "- Personality: sardonic salvage engineer" in block
    assert "- Stats: STR: 12, INT: 16" in block or "INT: 16" in block
    assert "- Inventory: laser cutter, combat knife" in block
    assert "- Conditions: hungry" in block


@pytest.mark.parametrize(
    "actor",
    [
        # only stats present
        {
            "name": "K",
            "role": "pc",
            "stats": {"STR": 10},
            "inventory": [],
            "conditions": [],
            "personality": "",
            "state_tags": [],
        },
        # only inventory present
        {
            "name": "K",
            "role": "pc",
            "stats": {},
            "inventory": ["knife"],
            "conditions": [],
            "personality": "",
            "state_tags": [],
        },
        # only conditions present
        {
            "name": "K",
            "role": "pc",
            "stats": {},
            "inventory": [],
            "conditions": ["wounded"],
            "personality": "",
            "state_tags": [],
        },
        # only personality present
        {
            "name": "K",
            "role": "pc",
            "stats": {},
            "inventory": [],
            "conditions": [],
            "personality": "grim",
            "state_tags": [],
        },
        # only state_tags present
        {
            "name": "K",
            "role": "pc",
            "stats": {},
            "inventory": [],
            "conditions": [],
            "personality": "",
            "state_tags": ["stealthy"],
        },
    ],
    ids=["stats-only", "inventory-only", "conditions-only", "personality-only", "state-tags-only"],
)
def test_partial_sheet_does_not_trigger_sentinel(actor: dict) -> None:
    """One identity-bearing field present is enough to skip the sentinel.

    The empty-sheet rule is a last resort: any concrete fact on the sheet
    (one stat, one inventory item, one tag) makes the actor legible, and
    the prompt-level rule stops being necessary.
    """
    block = Narrator._build_actor_block(actor)
    assert SENTINEL not in block, f"unexpected sentinel for partial sheet: {actor}"
    assert "ACTOR PROFILE" in block


# --------------------------------------------------------------------------- #
# Structural guards — the helper must always be safe to call
# --------------------------------------------------------------------------- #


def test_helper_does_not_raise_on_unexpected_shapes() -> None:
    """Defensive: weird input shapes should not raise — they fall back to empty/block.

    We don't promise perfect rendering for malformed actors, but a
    ``KeyError`` mid-turn would crash the scene loop.
    """
    # missing keys, wrong types, etc.
    weird = {
        "name": 42,  # not a string
        "role": object(),  # not a string
        "stats": "not a dict",
        "inventory": "not a list",
        "conditions": {"not": "a list"},
    }
    block = Narrator._build_actor_block(weird)  # type: ignore[arg-type]
    assert isinstance(block, str)
    assert "ACTOR PROFILE" in block


# --------------------------------------------------------------------------- #
# Prompt-level guard coverage (new GAP_REMEDIATION_PLAN.md rev. 2)
# --------------------------------------------------------------------------- #
#
# The new G-4 spec puts the do-not-invent rule in three prompt-level places:
#   1. ``NarratorSignature.__doc__`` "Core GM craft rules" list
#   2. ``profile_context`` InputField desc
#   3. ``narrative_text`` OutputField desc
#
# These tests are a regression guard against the rule being lost on a future
# prompt edit. They DO NOT call an LLM — they inspect the static prompt text.


def test_narrator_signature_docstring_contains_identity_facts_rule() -> None:
    """NarratorSignature docstring must carry the do-not-invent rule."""
    from monitor_agents.narrator.narrator import NarratorSignature

    doc = NarratorSignature.__doc__ or ""
    assert "identity facts" in doc, (
        f"NarratorSignature docstring should forbid inventing identity facts. Got docstring:\n{doc[:500]}"
    )
    # The text is word-wrapped across multiple lines, so normalize whitespace
    # before substring-matching ("sheet is empty" may appear across a break).
    doc_flat = " ".join(doc.split())
    assert "sheet is empty" in doc_flat, (
        "NarratorSignature docstring should reference the empty-sheet case. "
        f"Got docstring (normalized):\n{doc_flat[:500]}"
    )


def test_profile_context_desc_contains_empty_sheet_rule() -> None:
    """``profile_context`` InputField desc gets the empty-sheet prohibition."""
    from monitor_agents.narrator.narrator import NarratorSignature

    field = NarratorSignature.model_fields["profile_context"]
    desc = field.json_schema_extra.get("desc", "") if field.json_schema_extra else ""
    # dspy.InputField stores the desc on the field metadata; fall back to str()
    desc_text = desc or str(field)
    assert "character sheet is empty" in desc_text, (
        f"profile_context desc should forbid inventing on empty sheet. Got desc:\n{desc_text[:500]}"
    )
    assert "do not invent" in desc_text.lower(), (
        f"profile_context desc should include 'do not invent' phrasing. Got desc:\n{desc_text[:500]}"
    )


def test_narrative_text_desc_contains_identity_facts_rule() -> None:
    """``narrative_text`` OutputField desc leads with the no-invent rule."""
    from monitor_agents.narrator.narrator import NarratorSignature

    field = NarratorSignature.model_fields["narrative_text"]
    desc = field.json_schema_extra.get("desc", "") if field.json_schema_extra else ""
    desc_text = desc or str(field)
    assert "identity facts" in desc_text, (
        f"narrative_text desc must lead with the no-invent identity-facts rule. Got desc:\n{desc_text[:500]}"
    )
    # Identity rule should appear BEFORE the length guidance (leading prefix)
    assert desc_text.lower().index("identity facts") < desc_text.lower().index("voice set by tone_context"), (
        "narrative_text desc should lead with the no-invent rule, not bury it"
    )

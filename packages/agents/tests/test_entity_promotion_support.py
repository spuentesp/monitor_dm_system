"""Tests for the entity-promotion pure helpers in scene_support.py.

Covers:
- parse_entity_tags: [Name](entity:anchor|flavor) extraction from prose
- merge_entity_proposals: dedup-by-name + interaction_count accumulation
- turn_is_mechanically_bound: same-turn mechanical-outcome detection

See docs/2_architecture/data_model_workflow.md for the full promotion
lifecycle these feed into (CanonKeeper.evaluate_proposals).
"""

from __future__ import annotations

from monitor_agents.loops.scene_support import (
    merge_entity_proposals,
    parse_entity_tags,
    strip_entity_tags,
    turn_is_mechanically_bound,
)

# ============================================================================
# parse_entity_tags
# ============================================================================


def test_parse_single_anchor_tag() -> None:
    text = "*[Kira Shadowdancer](entity:anchor) rises from her seat.*"
    tags = parse_entity_tags(text)
    assert tags == [{"name": "Kira Shadowdancer", "promotion_intent": "anchor"}]


def test_parse_single_flavor_tag() -> None:
    text = "[a bored bartender](entity:flavor) wipes the bar."
    tags = parse_entity_tags(text)
    assert tags == [{"name": "a bored bartender", "promotion_intent": "flavor"}]


def test_parse_multiple_tags_in_one_turn() -> None:
    text = (
        "[Kira Shadowdancer](entity:anchor) nods to [a bored bartender](entity:flavor) "
        "as [General Puentes](entity:anchor) enters."
    )
    tags = parse_entity_tags(text)
    assert len(tags) == 3
    names = {t["name"] for t in tags}
    assert names == {"Kira Shadowdancer", "a bored bartender", "General Puentes"}


def test_parse_no_tags_returns_empty_list() -> None:
    assert parse_entity_tags("The chamber falls silent.") == []


def test_parse_empty_string() -> None:
    assert parse_entity_tags("") == []


def test_parse_none_safe() -> None:
    assert parse_entity_tags(None) == []  # type: ignore[arg-type]


def test_parse_ignores_malformed_tag_missing_type() -> None:
    """[Name](entity:) with no anchor/flavor keyword doesn't match — the
    regex only accepts the two literal values."""
    text = "[Somebody](entity:) walks past."
    assert parse_entity_tags(text) == []


def test_parse_ignores_asterisk_action_markup() -> None:
    """The existing *action* markup convention must not be confused with
    entity tags — they're independent conventions."""
    text = "*The door creaks open.* [Kira](entity:anchor) steps through."
    tags = parse_entity_tags(text)
    assert tags == [{"name": "Kira", "promotion_intent": "anchor"}]


# ============================================================================
# strip_entity_tags — inverse of parse_entity_tags, no LLM call.
# Must stay in lockstep with the parser: any variant the parser rejects
# the stripper must also leave alone (so we never silently drop a tag
# the KG expects to see).
# ============================================================================


def test_strip_single_anchor_tag() -> None:
    text = "*[Kira Shadowdancer](entity:anchor) rises from her seat.*"
    assert strip_entity_tags(text) == "*Kira Shadowdancer rises from her seat.*"


def test_strip_single_flavor_tag() -> None:
    text = "[a bored bartender](entity:flavor) wipes the bar."
    assert strip_entity_tags(text) == "a bored bartender wipes the bar."


def test_strip_multiple_tags_in_one_turn() -> None:
    text = (
        "[Kira Shadowdancer](entity:anchor) nods to [a bored bartender](entity:flavor) "
        "as [General Puentes](entity:anchor) enters."
    )
    assert (
        strip_entity_tags(text)
        == "Kira Shadowdancer nods to a bored bartender as General Puentes enters."
    )


def test_strip_no_tags_returns_text_unchanged() -> None:
    text = "The chamber falls silent."
    assert strip_entity_tags(text) == text


def test_strip_empty_string() -> None:
    assert strip_entity_tags("") == ""


def test_strip_none_safe() -> None:
    assert strip_entity_tags(None) == ""  # type: ignore[arg-type]


def test_strip_ignores_malformed_tag_missing_type() -> None:
    """[Name](entity:) with no anchor/flavor keyword must NOT be stripped —
    the parser rejects it too, so the stripper leaves it alone for
    round-trip consistency."""
    text = "[Somebody](entity:) walks past."
    assert strip_entity_tags(text) == text


def test_strip_ignores_uppercase_intent() -> None:
    """[Name](entity:ANCHOR) is not what the parser matches; the stripper
    must also leave it alone. Same lockstep rule."""
    text = "[Kira](entity:ANCHOR) sits."
    assert strip_entity_tags(text) == text


def test_strip_preserves_asterisk_action_markup() -> None:
    """The *action* markup convention must survive stripping — only the
    entity-tag brackets are removed."""
    text = "*The door creaks open.* [Kira](entity:anchor) steps through."
    assert (
        strip_entity_tags(text)
        == "*The door creaks open.* Kira steps through."
    )


def test_strip_preserves_ooc_double_paren_markup() -> None:
    """The ((ooc)) convention is independent of entity tags and must not
    be touched by the stripper."""
    text = "*[Kira](entity:anchor) smiles.* ((this is meta))"
    assert strip_entity_tags(text) == "*Kira smiles.* ((this is meta))"


def test_strip_handles_name_with_punctuation() -> None:
    """Names with quotes, apostrophes, or hyphens must not break the regex
    boundary."""
    text = "[Kira 'Whisper' Voss-Vane](entity:anchor) speaks."
    assert strip_entity_tags(text) == "Kira 'Whisper' Voss-Vane speaks."


def test_strip_round_trip_with_parse() -> None:
    """The canonical use-case: parse_entity_tags sees every tag (so the KG
    gets full metadata); strip_entity_tags removes every tag (so the player
    sees clean text). The names from parse match the names that survive
    the strip."""
    text = (
        "[Kira Shadowdancer](entity:anchor) greets "
        "[the bartender](entity:flavor)."
    )
    parsed = parse_entity_tags(text)
    stripped = strip_entity_tags(text)

    # All parsed names still appear in the stripped text (proves the
    # stripper didn't drop the entity-promotion signal).
    for tag in parsed:
        assert tag["name"] in stripped

    # And no raw tag syntax survives the strip.
    assert "[Kira Shadowdancer]" not in stripped
    assert "entity:anchor" not in stripped
    assert "entity:flavor" not in stripped
    assert "](" not in stripped, "no dangling markdown link syntax"


def test_strip_entity_tags_lockstep_with_narrator_duplicate() -> None:
    """The Narrator's _persist_turn path duplicates the strip regex inline
    (see comment in narrator.py — load-time circular import). The two
    implementations MUST agree on every input, otherwise the canonical
    turn record diverges from the live display. This test locks the
    behavior in lockstep.

    If a future refactor moves the duplicate back to a real import, this
    test still passes; it just guards the behavior, not the structure.
    """
    from monitor_agents.narrator.agent import _strip_entity_tags as narrator_strip

    cases = [
        "[Kira](entity:anchor) rises.",
        "[a bartender](entity:flavor) nods.",
        "[A](entity:anchor) and [B](entity:flavor) and [C](entity:anchor).",
        "No tags here at all.",
        "",
        "[malformed](entity:) leaves a hole.",
        "[Kira 'Whisper' Vane](entity:anchor) speaks.",
        "*[Kira](entity:anchor) acts.* ((ooc aside))",
        "Multiple\nlines\n[with one](entity:flavor) tag.",
    ]

    for text in cases:
        assert strip_entity_tags(text) == narrator_strip(text), (
            f"strip_entity_tags vs narrator._strip_entity_tags diverged on:\n"
            f"  input:    {text!r}\n"
            f"  scene:    {strip_entity_tags(text)!r}\n"
            f"  narrator: {narrator_strip(text)!r}"
        )


# ============================================================================
# merge_entity_proposals
# ============================================================================


# ============================================================================
# merge_entity_proposals
# ============================================================================


def _entity_proposal(name: str, **overrides) -> dict:
    base = {
        "proposal_type": "ENTITY",
        "content": {"name": name, "entity_type": "CHARACTER", "description": ""},
        "confidence": 0.8,
        "authority": "SYSTEM",
        "proposer": "narrator",
    }
    base.update(overrides)
    return base


def test_merge_new_entity_gets_interaction_count_one() -> None:
    result = merge_entity_proposals([], [_entity_proposal("Kira Shadowdancer")])
    assert len(result) == 1
    assert result[0]["interaction_count"] == 1


def test_merge_repeat_entity_bumps_existing_instead_of_duplicating() -> None:
    """The core bug this function fixes: without dedup, the same entity
    detected on turn 2 would become a SECOND proposal instead of bumping
    the first one's interaction_count."""
    existing = [_entity_proposal("Kira Shadowdancer", interaction_count=1)]
    new = [_entity_proposal("Kira Shadowdancer")]  # detected again on turn 2

    result = merge_entity_proposals(existing, new)

    assert len(result) == 1, "must not create a duplicate proposal for the same name"
    assert result[0]["interaction_count"] == 2


def test_merge_is_case_insensitive() -> None:
    existing = [_entity_proposal("Kira Shadowdancer")]
    new = [_entity_proposal("KIRA SHADOWDANCER")]

    result = merge_entity_proposals(existing, new)

    assert len(result) == 1
    assert result[0]["interaction_count"] == 2


def test_merge_non_entity_proposals_pass_through_unchanged() -> None:
    fact_proposal = {"proposal_type": "FACT", "content": {"statement": "The war ended."}}
    result = merge_entity_proposals([fact_proposal], [])
    assert result == [fact_proposal]


def test_merge_applies_tag_to_new_entity() -> None:
    tags = [{"name": "Kira Shadowdancer", "promotion_intent": "anchor"}]
    result = merge_entity_proposals([], [_entity_proposal("Kira Shadowdancer")], tags=tags)
    assert result[0]["promotion_intent"] == "anchor"


def test_merge_applies_tag_to_existing_entity_on_repeat_mention() -> None:
    """An entity untagged on turn 1 can still get promotion_intent set on
    turn 2 if THIS turn's narration finally tags it."""
    existing = [_entity_proposal("Kira Shadowdancer")]  # no promotion_intent yet
    tags = [{"name": "Kira Shadowdancer", "promotion_intent": "anchor"}]

    result = merge_entity_proposals(existing, [_entity_proposal("Kira Shadowdancer")], tags=tags)

    assert result[0]["promotion_intent"] == "anchor"
    assert result[0]["interaction_count"] == 2


def test_merge_does_not_downgrade_existing_anchor_tag() -> None:
    """An entity already tagged anchor keeps that status even if a later
    turn's tag (or absence of one) would suggest flavor — first tag wins."""
    existing = [_entity_proposal("Kira Shadowdancer", promotion_intent="anchor")]
    tags = [{"name": "Kira Shadowdancer", "promotion_intent": "flavor"}]

    result = merge_entity_proposals(existing, [_entity_proposal("Kira Shadowdancer")], tags=tags)

    assert result[0]["promotion_intent"] == "anchor"


def test_merge_mechanically_bound_ors_in_and_stays_true() -> None:
    existing = [_entity_proposal("Guard", is_mechanically_bound=False)]

    result = merge_entity_proposals(existing, [_entity_proposal("Guard")], is_mechanically_bound=True)
    assert result[0]["is_mechanically_bound"] is True

    # A later turn with no mechanical action must NOT clear the flag.
    result2 = merge_entity_proposals(result, [_entity_proposal("Guard")], is_mechanically_bound=False)
    assert result2[0]["is_mechanically_bound"] is True


def test_merge_does_not_mutate_input_lists() -> None:
    existing = [_entity_proposal("Kira Shadowdancer")]
    existing_copy_marker = dict(existing[0])

    merge_entity_proposals(existing, [_entity_proposal("Kira Shadowdancer")])

    assert existing[0] == existing_copy_marker, "must not mutate the caller's list/dicts"


def test_merge_entity_missing_name_is_appended_without_dedup() -> None:
    """Malformed proposals without a content.name still get appended (no
    crash), just can't participate in dedup."""
    malformed = {"proposal_type": "ENTITY", "content": {}}
    result = merge_entity_proposals([], [malformed])
    assert len(result) == 1


# ============================================================================
# turn_is_mechanically_bound
# ============================================================================


def test_mechanically_bound_dice_resolution() -> None:
    assert turn_is_mechanically_bound({"resolution_type": "dice"}) is True


def test_mechanically_bound_contested_resolution() -> None:
    assert turn_is_mechanically_bound({"resolution_type": "contested"}) is True


def test_mechanically_bound_combat_action_type() -> None:
    assert turn_is_mechanically_bound({"action_type": "combat"}) is True


def test_mechanically_bound_combat_subsystem_hint() -> None:
    assert turn_is_mechanically_bound({"subsystem_hint": "combat"}) is True


def test_not_mechanically_bound_narrative_resolution() -> None:
    assert turn_is_mechanically_bound({"resolution_type": "narrative"}) is False


def test_not_mechanically_bound_none_resolution() -> None:
    assert turn_is_mechanically_bound(None) is False


def test_not_mechanically_bound_empty_dict() -> None:
    assert turn_is_mechanically_bound({}) is False

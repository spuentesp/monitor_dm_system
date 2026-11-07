"""
Deterministic state-transition rules for CanonKeeper (G-9 Phase 2).

Pure Python, no LLM. These rules catch the mechanical impossibilities that a
reasoning model is both slow and unreliable at noticing: a dead character who
acts, an entity that is somehow both alive and dead. They only ever *flag* —
the verdict stays the model's call. (Phase 3 turns the deterministic subset
into hard rejections, once the flag rate is measured.)

Deliberately small and explicit. The complement pairs are a hand-written list,
never inferred — an inferred taxonomy is a heuristic in disguise, and the
de-heuristic principle (`docs/architecture/DE_HEURISTIC_PRINCIPLE.md`) asks for
explicit tables over inferred ones.

Location/teleport checks are deliberately absent: mapping an event sequence
needs temporal reasoning, which belongs to the implication-level check, not to
a tag table.
"""

from __future__ import annotations

from dataclasses import dataclass

# Tags that end an entity's agency. Removing one of these, or adding an
# agency-implying tag on top of it, is the classic impossible transition.
# "dead" is the canonical StateTag; the rest are free-form synonyms that
# proposals sometimes use.
TERMINAL_TAGS: frozenset[str] = frozenset({"dead", "destroyed", "deceased"})

# Tags that imply the entity is doing something.
AGENCY_TAGS: frozenset[str] = frozenset({"alive", "conscious", "active", "mobile", "speaking", "acting"})

# Mutually exclusive tag pairs. Kept short and explicit on purpose — only
# pairs that cannot both be true. Dispositions (hostile/friendly/neutral) are
# deliberately absent: they are not strictly exclusive.
MUTUALLY_EXCLUSIVE: tuple[tuple[str, str], ...] = (
    ("dead", "alive"),
    ("conscious", "unconscious"),
)


@dataclass(frozen=True)
class TransitionViolation:
    """One deterministic rule violation, ready to be flagged for review."""

    rule: str
    reason: str


def check_state_transition(
    current_tags: list[str],
    add_tags: list[str],
    remove_tags: list[str],
    override_reason: str | None = None,
) -> TransitionViolation | None:
    """
    Check a proposed state-tag change against the deterministic rules.

    Args:
        current_tags: The entity's current state tags.
        add_tags: Tags the proposal would add.
        remove_tags: Tags the proposal would remove.
        override_reason: If set, the proposal explicitly states why the
            transition is legal (resurrection is legal fiction — but it has to
            be said out loud, not inferred).

    Returns:
        The first violation found, or None when the transition is fine.
    """
    current = {str(t).lower() for t in current_tags}
    add = {str(t).lower() for t in add_tags}
    remove = {str(t).lower() for t in remove_tags}

    if not override_reason:
        terminal = current & TERMINAL_TAGS
        if terminal and (remove & TERMINAL_TAGS):
            return TransitionViolation(
                rule="terminal_tag_removal",
                reason=(
                    f"Entity is tagged {sorted(terminal)} and the proposal removes "
                    f"{sorted(remove & TERMINAL_TAGS)}. A terminal state is final "
                    "unless the proposal states an explicit override_reason."
                ),
            )
        if terminal and (add & AGENCY_TAGS):
            return TransitionViolation(
                rule="terminal_tag_agency",
                reason=(
                    f"Entity is tagged {sorted(terminal)} and the proposal adds the "
                    f"agency-implying tag(s) {sorted(add & AGENCY_TAGS)}. A dead "
                    "entity cannot act unless the proposal states an explicit "
                    "override_reason."
                ),
            )

    resulting = (current | add) - remove
    for left, right in MUTUALLY_EXCLUSIVE:
        if left in resulting and right in resulting:
            return TransitionViolation(
                rule="mutual_exclusion",
                reason=(
                    f"The resulting state would carry both '{left}' and '{right}'. These tags are mutually exclusive."
                ),
            )

    return None

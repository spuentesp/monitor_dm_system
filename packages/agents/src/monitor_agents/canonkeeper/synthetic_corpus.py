"""
A small hermetic corpus for measuring the contradiction checks (G-9).

The seeded universes are mechanical, and the product boundary (2026-11-07) keeps
it that way — so the false-positive measurement must not depend on them. This
module holds a hand-written narrative world: a handful of canon facts, a set
of candidate statements that are all *consistent* with them, and a set that
genuinely *contradicts* them.

Every flag raised on the consistent set is a false positive by construction;
every flag raised on the contradicting set is a true positive. So one run
yields both the false-positive rate and the detection rate — with no database,
no seeded content and (for the deterministic rules) no model at all.

The corpus lives here rather than in the script so the measurement can be
pinned by a test.
"""

from __future__ import annotations

from typing import Any

# ─── The world ───────────────────────────────────────────────────────────────

SYNTHETIC_CANON: tuple[str, ...] = (
    "Mira Vale is a courier for the Grey Line, running messages between the harbour districts.",
    "Mira Vale has never crossed into the Burnside district.",
    "The Grey Line pays in silver marks, not in favours.",
    "Old Tam is the only lamplighter still working the harbour terraces.",
    "The harbour council meets at dusk in the Customs House.",
    "Mira Vale carries a brass key that opens the seawall gate.",
    "The seawall gate is sealed each night at the seventh bell.",
    "Captain Rell commands the dredger Kittiwake.",
    "Captain Rell lost the Kittiwake's sister boat to shoals two winters ago.",
    "Sable is a courier who works for the Harbour Trust.",
    "Sable and Mira Vale have never spoken.",
    "The Brass Market closes when the fog comes off the water.",
)

# Consistent with the canon: restatements and compatible elaborations.
SYNTHETIC_CONSISTENT: tuple[str, ...] = (
    "Mira Vale is a courier for the Grey Line.",
    "By all accounts, Mira Vale still runs messages for the Grey Line.",
    "Mira Vale has never crossed into the Burnside district, not once.",
    "The Grey Line still pays its couriers in silver marks.",
    "Old Tam goes up the harbour terraces every night with his long pole.",
    "The harbour council gathers at dusk in the Customs House.",
    "Mira Vale carries a brass key for the seawall gate.",
    "The seawall gate is sealed at the seventh bell every night.",
    "Captain Rell still commands the dredger Kittiwake.",
    "Captain Rell lost the Kittiwake's sister boat to the shoals two winters back.",
    "Sable works as a courier for the Harbour Trust.",
    "Sable and Mira Vale have still never spoken to each other.",
    "The Brass Market shuts when the fog lifts off the water.",
    "Mira Vale prefers the harbour route to the cliff path.",
    "The Grey Line still runs its harbour route twice a day.",
    "Captain Rell keeps the Kittiwake moored below the Customs House.",
)

# Contradicts the canon: these SHOULD be flagged.
SYNTHETIC_CONTRADICTING: tuple[str, ...] = (
    "Mira Vale has crossed into the Burnside district a dozen times.",
    "The Grey Line pays its couriers in favours now, not silver marks.",
    "Old Tam retired from the lamplighters' trade years ago.",
    "The brass key Mira Vale carries opens the Customs House.",
    "Captain Rell no longer commands the Kittiwake.",
    "Sable and Mira Vale are close friends who speak every day.",
    "The Brass Market stays open all night, even in fog.",
    "Mira Vale no longer works for the Grey Line.",
)

# ─── The deterministic transition corpus ─────────────────────────────────────
#
# Each case is (entity_id, add_tags, remove_tags, current_tags). "Good" cases
# must not raise a violation; "bad" cases must. Every case carries its own
# current state, so a mutual-exclusion probe is not masked by a terminal-tag
# probe (the terminal rule is checked first).

SYNTHETIC_GOOD_TRANSITIONS: tuple[tuple[str, list[str], list[str], list[str]], ...] = (
    ("e-1", ["wounded"], [], ["alive", "friendly", "hidden"]),
    ("e-2", [], ["friendly"], ["alive", "friendly", "hidden"]),
    ("e-3", ["prone"], [], ["alive", "friendly", "hidden"]),
    ("e-4", [], ["hostile", "neutral"], ["alive", "friendly", "hidden"]),
    ("e-5", ["revealed"], [], ["alive", "friendly", "hidden"]),
    ("e-6", ["frightened"], ["friendly"], ["alive", "friendly", "hidden"]),
    ("e-7", ["stunned"], [], ["alive", "friendly", "hidden"]),
    ("e-8", ["incapacitated"], [], ["alive", "friendly", "hidden"]),
    ("e-9", [], ["hidden"], ["alive", "friendly", "hidden"]),
    ("e-10", ["charmed"], ["hostile"], ["alive", "friendly", "hidden"]),
    ("e-11", ["grappled"], [], ["alive", "friendly", "hidden"]),
    ("e-12", ["confused"], [], ["alive", "friendly", "hidden"]),
)

SYNTHETIC_BAD_TRANSITIONS: tuple[tuple[str, list[str], list[str], list[str]], ...] = (
    ("e-13", ["alive"], [], ["dead"]),  # agency added to a dead entity
    ("e-14", [], ["dead"], ["dead"]),  # a terminal tag removed
    ("e-15", ["dead", "alive"], [], ["neutral"]),  # mutually exclusive tags
)


def synthetic_context() -> str:
    """The canon rendered as the context lines the checks consume."""
    return "\n".join(f"Fact: {fact}" for fact in SYNTHETIC_CANON)


def replay_transitions(
    cases: tuple[tuple[str, list[str], list[str], list[str]], ...],
) -> list[dict[str, Any]]:
    """Run the deterministic transition rules over synthetic state changes."""
    from monitor_agents.canonkeeper.transition_rules import check_state_transition

    violations: list[dict[str, Any]] = []
    for entity_id, add_tags, remove_tags, current_tags in cases:
        violation = check_state_transition(
            current_tags=current_tags,
            add_tags=add_tags,
            remove_tags=remove_tags,
        )
        if violation is not None:
            violations.append(
                {
                    "entity_id": entity_id,
                    "current_tags": current_tags,
                    "add_tags": add_tags,
                    "remove_tags": remove_tags,
                    "rule": violation.rule,
                    "reason": violation.reason,
                }
            )
    return violations

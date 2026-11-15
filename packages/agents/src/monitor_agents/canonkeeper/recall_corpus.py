"""
A labeled recall corpus for the contradiction checks (G08, gap G-9).

The 2026-11-07 measurement (`docs/testing/canonkeeper_depth_measurement_2026-11-07.md`)
found the implication check at **25% recall** on eight hand-written
contradictions. That number was too small to act on: eight cases cannot
tell "the check is weak" from "the sample was unlucky", and a single
percentage hides *which* kind of contradiction the check misses.

This module is the corpus that fixes both problems:

- **More cases**, spread over the kinds of contradiction a GM actually
  produces — an outright negation, a flipped status word, an event placed
  in the wrong part of the timeline, a conflict that only shows up after a
  chain of reasoning.
- **A label per case**, so the measurement reports recall *per class*
  instead of one number. A check that catches negations and misses
  timelines is a different product from one that catches both.

The canon is a small fictional world with explicit entities and in-fiction
timestamps, so the retrieval layer can be measured too: a candidate about
Mira Vale should not have to reason past the whole world to find the facts
that bear on it.

Everything here is data — no model, no database — so the corpus can be
pinned by a test and replayed by `scripts/eval_canonkeeper_recall.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ─── Case classes ───────────────────────────────────────────────────────────
#
# The classes are the unit the measurement reports on. ``DIRECT_CLASSES`` and
# ``TIMELINE_CLASSES`` are the two families the G08 plan gates hard rejection
# on; ``IMPLICATION_CLASSES`` is the reasoning-chain family, which is held to
# a lower bar because a chain is, by nature, the hardest case.

DIRECT_CLASSES: tuple[str, ...] = ("direct_negation", "status_antonym")
TIMELINE_CLASSES: tuple[str, ...] = ("timeline_violation",)
IMPLICATION_CLASSES: tuple[str, ...] = ("implication_chain",)
CONSISTENT_CLASSES: tuple[str, ...] = ("consistent_restatement", "consistent_elaboration")

VIOLATION_CLASSES: tuple[str, ...] = (
    *DIRECT_CLASSES,
    *TIMELINE_CLASSES,
    *IMPLICATION_CLASSES,
)

# Per-class recall floors. Direct and timeline violations must be caught
# almost always before hard rejection is safe; the reasoning chains are
# held to 80% because a chain is allowed to be missed now and then.
CLASS_TARGETS: dict[str, float] = {
    "direct_negation": 0.90,
    "status_antonym": 0.90,
    "timeline_violation": 0.90,
    "implication_chain": 0.80,
}

# A false positive on known-good material is worse than a miss: it trains
# the GM to ignore the warning. The whole corpus is only worth measuring if
# this stays low.
FALSE_POSITIVE_CEILING: float = 0.05


@dataclass(frozen=True)
class CanonFact:
    """One piece of canon, with the entities and the time it belongs to."""

    statement: str
    entities: tuple[str, ...] = ()
    time_ref: str | None = None
    kind: str = "fact"  # "fact" or "axiom"


@dataclass(frozen=True)
class RecallCase:
    """One probe: a statement to check, and what checking it should find."""

    statement: str
    case_class: str
    expects_violation: bool
    note: str = ""


@dataclass
class ClassReport:
    """The measured outcome for one case class."""

    case_class: str
    total: int = 0
    detected: int = 0
    detected_direct: int = 0
    detected_implication: int = 0
    false_positives: int = 0
    target: float | None = None

    @property
    def recall(self) -> float:
        return self.detected / self.total if self.total else 0.0

    @property
    def direct_recall(self) -> float:
        return self.detected_direct / self.total if self.total else 0.0

    @property
    def implication_recall(self) -> float:
        return self.detected_implication / self.total if self.total else 0.0

    @property
    def meets_target(self) -> bool:
        if self.target is None:
            return True
        return self.recall >= self.target


# ─── The world ──────────────────────────────────────────────────────────────
#
# A courier guild on a fog-bound harbour. The canon carries three things the
# checks need: *who* (entities), *when* (in-fiction day/time), and *what*
# (the statement itself). Axioms are the world's rules; facts are what
# happened inside them.

RECALL_CANON: tuple[CanonFact, ...] = (
    CanonFact(
        statement=("The Grey Line is a courier guild that runs only between the harbour districts."),
        entities=("Grey Line",),
        kind="axiom",
    ),
    CanonFact(
        statement=("Silver marks are the only currency the harbour council accepts."),
        entities=("harbour council", "silver marks"),
        kind="axiom",
    ),
    CanonFact(
        statement=("Mira Vale is a courier for the Grey Line, running messages between the harbour districts."),
        entities=("Mira Vale", "Grey Line"),
    ),
    CanonFact(
        statement=("Mira Vale has never crossed into the Burnside district."),
        entities=("Mira Vale", "Burnside district"),
    ),
    CanonFact(
        statement=("The Grey Line pays in silver marks, not in favours."),
        entities=("Grey Line", "silver marks"),
    ),
    CanonFact(
        statement=("Old Tam is the only lamplighter still working the harbour terraces."),
        entities=("Old Tam", "harbour terraces"),
    ),
    CanonFact(
        statement=("Old Tam lights the harbour terraces every night at the sixth bell."),
        entities=("Old Tam", "harbour terraces"),
        time_ref="day 1, 18:00",
    ),
    CanonFact(
        statement=("The harbour council meets at dusk in the Customs House."),
        entities=("harbour council", "Customs House"),
        time_ref="day 1, 19:00",
    ),
    CanonFact(
        statement=("Mira Vale carries a brass key that opens the seawall gate."),
        entities=("Mira Vale", "brass key", "seawall gate"),
    ),
    CanonFact(
        statement=("The seawall gate is sealed each night at the seventh bell."),
        entities=("seawall gate",),
        time_ref="day 1, 19:00",
    ),
    CanonFact(
        statement=("Captain Rell commands the dredger Kittiwake."),
        entities=("Captain Rell", "Kittiwake"),
    ),
    CanonFact(
        statement=("Captain Rell lost the Kittiwake's sister boat to shoals two winters ago."),
        entities=("Captain Rell", "Kittiwake"),
        time_ref="two winters ago",
    ),
    CanonFact(
        statement=("Sable is a courier who works for the Harbour Trust."),
        entities=("Sable", "Harbour Trust"),
    ),
    CanonFact(
        statement=("Sable and Mira Vale have never spoken."),
        entities=("Sable", "Mira Vale"),
    ),
    CanonFact(
        statement=("The Brass Market closes when the fog comes off the water."),
        entities=("Brass Market",),
    ),
    CanonFact(
        statement=("On the third day, Mira Vale delivered a sealed letter to the Customs House."),
        entities=("Mira Vale", "Customs House"),
        time_ref="day 3, 10:00",
    ),
    CanonFact(
        statement=("On the fourth day, the harbour council voted to close the Brass Market."),
        entities=("harbour council", "Brass Market"),
        time_ref="day 4, 19:00",
    ),
    CanonFact(
        statement=("Mira Vale was barred from the Customs House after the third day's delivery."),
        entities=("Mira Vale", "Customs House"),
        time_ref="day 4, 12:00",
    ),
)


# ─── The cases ──────────────────────────────────────────────────────────────

RECALL_CASES: tuple[RecallCase, ...] = (
    # -- direct negation: the candidate denies a canon fact outright -------
    RecallCase(
        "Mira Vale works for the Harbour Trust, not the Grey Line.",
        "direct_negation",
        True,
        "denies that Mira Vale is a Grey Line courier",
    ),
    RecallCase(
        "The Grey Line pays its couriers in favours, not silver marks.",
        "direct_negation",
        True,
        "negates the payment axiom",
    ),
    RecallCase(
        "Old Tam retired from the lamplighters' trade years ago.",
        "direct_negation",
        True,
        "denies that Old Tam still works",
    ),
    RecallCase(
        "The brass key Mira Vale carries opens the Customs House.",
        "direct_negation",
        True,
        "the key opens the seawall gate, not the Customs House",
    ),
    RecallCase(
        "Captain Rell no longer commands the Kittiwake.",
        "direct_negation",
        True,
        "denies a standing fact",
    ),
    RecallCase(
        "Sable and Mira Vale are close friends who speak every day.",
        "direct_negation",
        True,
        "denies that they never spoke",
    ),
    RecallCase(
        "Mira Vale has crossed into the Burnside district a dozen times.",
        "direct_negation",
        True,
        "denies 'never crossed'",
    ),
    RecallCase(
        "Mira Vale no longer works for the Grey Line.",
        "direct_negation",
        True,
        "denies the employment fact",
    ),
    # -- status antonym: a status word flipped ------------------------------
    RecallCase(
        "Mira Vale is a former courier for the Grey Line.",
        "status_antonym",
        True,
        "'former' vs 'is'",
    ),
    RecallCase(
        "The Brass Market stays open all night, even in fog.",
        "status_antonym",
        True,
        "'open' vs 'closes'",
    ),
    RecallCase(
        "The seawall gate is unsealed every night at the seventh bell.",
        "status_antonym",
        True,
        "'unsealed' vs 'sealed'",
    ),
    RecallCase(
        "Sable is a courier who no longer works for the Harbour Trust.",
        "status_antonym",
        True,
        "'no longer' vs 'works for'",
    ),
    RecallCase(
        "The harbour council meets at dawn in the Customs House.",
        "status_antonym",
        True,
        "'dawn' vs 'dusk'",
    ),
    RecallCase(
        "Old Tam is no longer the only lamplighter working the harbour terraces.",
        "status_antonym",
        True,
        "'no longer the only' vs 'the only'",
    ),
    # -- timeline violation: an event in the wrong part of the timeline ------
    RecallCase(
        "On the first day, Mira Vale was already barred from the Customs House.",
        "timeline_violation",
        True,
        "barred on day 4, not day 1",
    ),
    RecallCase(
        "On the sixth day, Mira Vale delivered the sealed letter to the Customs House.",
        "timeline_violation",
        True,
        "the delivery was on day 3",
    ),
    RecallCase(
        "Before Mira Vale's delivery on the third day, the harbour council had already "
        "voted to close the Brass Market.",
        "timeline_violation",
        True,
        "the vote was on day 4",
    ),
    RecallCase(
        "On the second day, Mira Vale was barred from the Customs House.",
        "timeline_violation",
        True,
        "barred on day 4, not day 2",
    ),
    RecallCase(
        "On the fifth day, Old Tam lit the harbour terraces at the sixth bell for the last time.",
        "timeline_violation",
        True,
        "the sixth bell happened on day 1",
    ),
    RecallCase(
        "On the fourth day at dawn, the harbour council met in the Customs House.",
        "timeline_violation",
        True,
        "the council meets at dusk",
    ),
    # -- implication chain: the conflict only shows up after reasoning ------
    RecallCase(
        "Mira Vale's errand took her through the Burnside district.",
        "implication_chain",
        True,
        "an errand through Burnside means she crossed into it",
    ),
    RecallCase(
        "Sable delivered a message for Mira Vale.",
        "implication_chain",
        True,
        "delivering a message means they spoke",
    ),
    RecallCase(
        "Mira Vale was seen inside the Customs House on the fourth day.",
        "implication_chain",
        True,
        "she was barred from it on the fourth day",
    ),
    RecallCase(
        "The Kittiwake's sister boat was raised from the shoals two winters later.",
        "implication_chain",
        True,
        "it was lost to the shoals",
    ),
    RecallCase(
        "Mira Vale lit the harbour terraces with Old Tam's lamp.",
        "implication_chain",
        True,
        "Old Tam is the only lamplighter still working them",
    ),
    RecallCase(
        "The Harbour Trust roster lists Mira Vale as its courier.",
        "implication_chain",
        True,
        "she is a Grey Line courier",
    ),
    # -- consistent restatement: the same thing said again ------------------
    RecallCase(
        "Mira Vale is a courier for the Grey Line.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "By all accounts, Mira Vale still runs messages for the Grey Line.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "Mira Vale has never crossed into the Burnside district, not once.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "The Grey Line still pays its couriers in silver marks.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "Old Tam goes up the harbour terraces every night with his long pole.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "The harbour council gathers at dusk in the Customs House.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "Mira Vale carries a brass key for the seawall gate.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "The seawall gate is sealed at the seventh bell every night.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "Captain Rell still commands the dredger Kittiwake.",
        "consistent_restatement",
        False,
    ),
    RecallCase(
        "Sable works as a courier for the Harbour Trust.",
        "consistent_restatement",
        False,
    ),
    # -- consistent elaboration: compatible new detail -----------------------
    RecallCase(
        "Mira Vale prefers the harbour route to the cliff path.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "The Grey Line still runs its harbour route twice a day.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "Captain Rell keeps the Kittiwake moored below the Customs House.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "Old Tam's long pole has a waxed cord at the tip.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "Sable wears a Harbour Trust armband.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "The harbour council's meeting room smells of lamp oil.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "Mira Vale counts the seventh bell by the Customs House clock.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "Sable and Mira Vale have still never spoken to each other.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "Mira Vale checks the brass key every morning.",
        "consistent_elaboration",
        False,
    ),
    RecallCase(
        "The Brass Market shutters shut when the fog lifts off the water.",
        "consistent_elaboration",
        False,
    ),
)


# ─── Rendering and evaluation ──────────────────────────────────────────────


def render_context(facts: tuple[CanonFact, ...] = RECALL_CANON) -> str:
    """Render the canon the way the checks consume it.

    Axioms come first (they are the world's rules), then facts. A fact with
    an in-fiction timestamp carries it in the line, because a check that
    cannot see *when* cannot see a timeline violation.
    """
    axioms = [f for f in facts if f.kind == "axiom"]
    rest = [f for f in facts if f.kind != "axiom"]
    lines: list[str] = []
    for fact in axioms:
        lines.append(f"Axiom: {fact.statement}")
    for fact in rest:
        if fact.time_ref:
            lines.append(f"Fact ({fact.time_ref}): {fact.statement}")
        else:
            lines.append(f"Fact: {fact.statement}")
    return "\n".join(lines)


def entity_names(text: str) -> set[str]:
    """The canon entity names that appear in a piece of text.

    Matching is case-insensitive and substring-based, which is enough for a
    hand-written corpus and keeps the retrieval layer free of a model.
    """
    lowered = text.lower()
    names: set[str] = set()
    for fact in RECALL_CANON:
        for entity in fact.entities:
            if entity.lower() in lowered:
                names.add(entity)
    return names


def focused_context(statement: str, facts: tuple[CanonFact, ...] = RECALL_CANON) -> str:
    """The canon lines that bear on one candidate statement.

    A candidate about Mira Vale is checked against the facts that mention
    Mira Vale (and the facts those facts share an entity with), plus the
    world's axioms. Everything else is noise for that candidate — and noise
    is what a long context is made of.
    """
    mentioned = entity_names(statement)
    axioms = [f for f in facts if f.kind == "axiom"]
    related = [f for f in facts if f.kind != "axiom" and mentioned.intersection(f.entities)]
    # One hop out: facts sharing an entity with a directly related fact.
    neighbours: set[str] = set(mentioned)
    for fact in related:
        neighbours.update(fact.entities)
    one_hop = [f for f in facts if f.kind != "axiom" and f not in related and neighbours.intersection(f.entities)]
    lines: list[str] = []
    for fact in axioms:
        lines.append(f"Axiom: {fact.statement}")
    for fact in (*related, *one_hop):
        if fact.time_ref:
            lines.append(f"Fact ({fact.time_ref}): {fact.statement}")
        else:
            lines.append(f"Fact: {fact.statement}")
    return "\n".join(lines)


@dataclass
class RecallReport:
    """The measured outcome over the whole corpus."""

    classes: dict[str, ClassReport] = field(default_factory=dict)

    @property
    def false_positive_rate(self) -> float:
        """False positives over all known-good cases."""
        consistent = [c for c in self.classes.values() if c.target is None]
        total = sum(c.total for c in consistent)
        if not total:
            return 0.0
        return sum(c.false_positives for c in consistent) / total

    @property
    def meets_targets(self) -> bool:
        return all(c.meets_target for c in self.classes.values() if c.target is not None)

    def to_dict(self) -> dict[str, object]:
        return {
            "false_positive_rate": self.false_positive_rate,
            "meets_targets": self.meets_targets,
            "classes": {
                name: {
                    "total": c.total,
                    "detected": c.detected,
                    "recall": c.recall,
                    "direct_recall": c.direct_recall,
                    "implication_recall": c.implication_recall,
                    "false_positives": c.false_positives,
                    "target": c.target,
                    "meets_target": c.meets_target,
                }
                for name, c in self.classes.items()
            },
        }


def evaluate(
    cases: tuple[RecallCase, ...],
    direct_flags: set[str],
    implication_flags: set[str],
) -> RecallReport:
    """Score a run of the checks against the corpus.

    Args:
        cases: The corpus.
        direct_flags: Statements the direct check flagged.
        implication_flags: Statements the implication check flagged.

    Returns:
        The per-class report. A case counts as detected when *either* check
        flagged it — the product's job is to catch the contradiction, not
        to catch it with one particular module.
    """
    report = RecallReport()
    for case in cases:
        entry = report.classes.get(case.case_class)
        if entry is None:
            entry = ClassReport(
                case_class=case.case_class,
                target=CLASS_TARGETS.get(case.case_class),
            )
            report.classes[case.case_class] = entry
        entry.total += 1
        hit_direct = case.statement in direct_flags
        hit_implication = case.statement in implication_flags
        if case.expects_violation:
            if hit_direct:
                entry.detected_direct += 1
            if hit_implication:
                entry.detected_implication += 1
            if hit_direct or hit_implication:
                entry.detected += 1
        else:
            if hit_direct or hit_implication:
                entry.false_positives += 1
    return report


__all__ = [
    "CLASS_TARGETS",
    "CONSISTENT_CLASSES",
    "CanonFact",
    "ClassReport",
    "DIRECT_CLASSES",
    "FALSE_POSITIVE_CEILING",
    "IMPLICATION_CLASSES",
    "RECALL_CANON",
    "RECALL_CASES",
    "RecallCase",
    "RecallReport",
    "TIMELINE_CLASSES",
    "VIOLATION_CLASSES",
    "entity_names",
    "evaluate",
    "focused_context",
    "render_context",
]

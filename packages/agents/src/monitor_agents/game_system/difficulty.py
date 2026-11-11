"""
Encounter difficulty estimation (CF-13 / G06).

CF-7 suggests encounters and CF-4 improvises NPCs, but nothing checks a
suggested fight against the party that would actually fight it. The GM
gets "three goblins" with no idea whether that is a warm-up or a funeral.

This module is the math behind the answer. It is **pure and deterministic**:
no model, no database, no hidden state. The labels and the numbers are
derived from the bound game system's own data where it provides any, and
from an explicit generic convention where it does not.

Two rules keep it honest:

- **No game-system names are hardcoded.** The thresholds, the encounter
  multipliers and the threat weights come from the system document's
  ``difficulty`` section when it has one; the built-in defaults are the
  generic convention, not a system's rules.
- **No guessing.** A universe whose game system says nothing about
  difficulty gets ``unrated`` — an explicit "we cannot tell you", which is
  more useful than a confident wrong number.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1 schemas), external libraries
CALLED BY: GmTableAgent (Layer 2), UI backend routers (Layer 3)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from monitor_data.schemas.game_systems import EncounterDifficulty

# The labels, worst last. The order is the contract: a system's own table
# may rename them but not reorder them.
DIFFICULTY_LABELS: tuple[str, ...] = (
    "trivial",
    "easy",
    "moderate",
    "hard",
    "deadly",
    "unrated",
)

# The generic encounter multipliers: how much worse a fight gets because
# more people are in it. This is the classic table (1, 1.5, 2, 3, 4, 5)
# expressed as data — a system's own table replaces it when it has one.
DEFAULT_ENCOUNTER_MULTIPLIERS: dict[int, float] = {
    0: 1.0,
    1: 1.0,
    2: 1.5,
    3: 2.0,
    4: 2.0,
    5: 2.0,
    6: 2.0,
    7: 3.0,
    8: 3.0,
    9: 3.0,
    10: 3.0,
    11: 4.0,
    12: 4.0,
    13: 4.0,
    14: 4.0,
}

# The generic threshold table: the ratio of threat to the party's budget
# that earns each label. The last entry is the ceiling — anything above it
# is "deadly" too, because there is no worse word.
DEFAULT_THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("trivial", 0.25),
    ("easy", 0.5),
    ("moderate", 1.0),
    ("hard", 1.5),
    ("deadly", 2.5),
)

# What a foe's hit points are worth against the party's budget, and what a
# foe's damage output adds. Both are generic weights: a system with its own
# difficulty section supplies its own.
DEFAULT_THREAT_WEIGHT_PER_HP: float = 1.0
DEFAULT_ATTACK_THREAT: float = 5.0

# The generic party budget per character level, used when the party members
# have a level but no hit points.
DEFAULT_BUDGET_PER_LEVEL: float = 25.0

# The budget used for a party member with neither hit points nor a level.
DEFAULT_BUDGET_PER_MEMBER: float = 30.0


@dataclass(frozen=True)
class Foe:
    """One opponent in the proposed encounter."""

    name: str
    count: int = 1
    hit_points: int | None = None
    armor_class: int | None = None
    attack_bonus: int | None = None


@dataclass(frozen=True)
class PartyMember:
    """One member of the party that would face the encounter."""

    name: str
    level: int | None = None
    hit_points: int | None = None


@dataclass
class DifficultyEstimate:
    """The verdict, and the arithmetic behind it.

    ``rationale`` is the deterministic explanation ("deadly for a level-3
    party of 4"); a model may rephrase it for the GM, but the numbers come
    from here.
    """

    label: str = "unrated"
    threat: float = 0.0
    party_budget: float = 0.0
    ratio: float | None = None
    basis: str = "unrated"
    rationale: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def rated(self) -> bool:
        """Whether an estimate was produced at all."""
        return self.label != "unrated"

    def to_report(self) -> "EncounterDifficulty":
        """The estimate as the response model the API speaks."""
        from monitor_data.schemas.game_systems import EncounterDifficulty

        return EncounterDifficulty(
            label=self.label,
            rationale=self.rationale,
            threat=self.threat,
            party_budget=self.party_budget,
            ratio=self.ratio,
            basis=self.basis,
            details=dict(self.details),
        )


def _multiplier_for(count: int, table: dict[int, float]) -> float:
    """The encounter multiplier for a number of foes."""
    if count <= 0:
        return 1.0
    if count in table:
        return table[count]
    highest = max(table)
    return table[highest]


def _rules_from_system(system: dict[str, Any] | None) -> dict[str, Any]:
    """The difficulty rules a game system document provides, if any."""
    if not system:
        return {}
    rules = system.get("difficulty")
    return rules if isinstance(rules, dict) else {}


def _foe_threat(foe: Foe, weight_per_hp: float, attack_threat: float) -> float:
    """What one foe is worth against the party's budget."""
    threat = 0.0
    if foe.hit_points is not None:
        threat += max(0, foe.hit_points) * weight_per_hp
    if foe.attack_bonus is not None:
        threat += max(0, foe.attack_bonus) * 2
    if threat == 0.0:
        # A foe with no numbers at all still costs the party attention.
        threat = attack_threat
    return threat * max(1, foe.count)


def _member_budget(member: PartyMember, budget_per_level: float, budget_per_member: float) -> float:
    """What one party member brings to the fight."""
    if member.hit_points is not None:
        return float(max(0, member.hit_points))
    if member.level is not None:
        return float(max(1, member.level)) * budget_per_level
    return budget_per_member


def _label_for(ratio: float, thresholds: tuple[tuple[str, float], ...]) -> str:
    """The label a threat/budget ratio earns."""
    label = thresholds[0][0]
    for name, ceiling in thresholds:
        if ratio >= ceiling:
            label = name
    return label


def estimate_difficulty(
    foes: list[Foe],
    party: list[PartyMember],
    system: dict[str, Any] | None = None,
) -> DifficultyEstimate:
    """Estimate how fair an encounter is for a party.

    Args:
        foes: The opponents in the proposed encounter.
        party: The party that would face them.
        system: The bound game system's document (may be empty).

    Returns:
        The estimate. ``unrated`` when there is nothing to compare — an
        empty party, an empty encounter, or a system that says nothing about
        difficulty and no numbers on either side.
    """
    rules = _rules_from_system(system)
    multipliers = rules.get("encounter_multipliers") or DEFAULT_ENCOUNTER_MULTIPLIERS
    multipliers = {int(k): float(v) for k, v in multipliers.items()}
    thresholds = rules.get("thresholds") or DEFAULT_THRESHOLDS
    weight_per_hp = float(rules.get("threat_weight_per_hp", DEFAULT_THREAT_WEIGHT_PER_HP))
    attack_threat = float(rules.get("attack_threat", DEFAULT_ATTACK_THREAT))
    budget_per_level = float(rules.get("budget_per_level", DEFAULT_BUDGET_PER_LEVEL))
    budget_per_member = float(rules.get("budget_per_member", DEFAULT_BUDGET_PER_MEMBER))
    basis = "system_table" if rules else "generic"

    if not foes or not party:
        return DifficultyEstimate(
            label="unrated",
            basis="unrated",
            rationale="Not enough information to estimate this encounter.",
        )

    total_foes = sum(max(1, foe.count) for foe in foes)
    threat = sum(_foe_threat(foe, weight_per_hp, attack_threat) for foe in foes)
    multiplier = _multiplier_for(total_foes, multipliers)
    adjusted_threat = threat * multiplier

    party_budget = sum(
        _member_budget(member, budget_per_level, budget_per_member) for member in party
    )
    if party_budget <= 0:
        return DifficultyEstimate(
            label="unrated",
            threat=adjusted_threat,
            party_budget=0.0,
            basis="unrated",
            rationale="The party's resources are unknown, so no estimate was made.",
        )

    ratio = adjusted_threat / party_budget
    label = _label_for(ratio, thresholds)

    party_description = _party_description(party)
    rationale = (
        f"{label.capitalize()} for {party_description}: "
        f"{_number(adjusted_threat)} threat against {_number(party_budget)} party resources "
        f"({_number(ratio)}x), {_number(total_foes)} opponent(s)."
    )

    return DifficultyEstimate(
        label=label,
        threat=round(adjusted_threat, 2),
        party_budget=round(party_budget, 2),
        ratio=round(ratio, 3),
        basis=basis,
        rationale=rationale,
        details={
            "foe_count": total_foes,
            "multiplier": multiplier,
            "raw_threat": round(threat, 2),
        },
    )


def _party_description(party: list[PartyMember]) -> str:
    """How the party is described in the rationale."""
    size = len(party)
    levels = sorted({m.level for m in party if m.level is not None})
    if len(levels) == 1:
        return f"a level-{levels[0]} party of {size}"
    if levels:
        return f"a party of {size} (levels {levels[0]}-{levels[-1]})"
    return f"a party of {size}"


def _number(value: float) -> str:
    """A number the way a GM would say it out loud."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


__all__ = [
    "DEFAULT_BUDGET_PER_LEVEL",
    "DEFAULT_BUDGET_PER_MEMBER",
    "DEFAULT_ENCOUNTER_MULTIPLIERS",
    "DEFAULT_THRESHOLDS",
    "DIFFICULTY_LABELS",
    "DifficultyEstimate",
    "Foe",
    "PartyMember",
    "estimate_difficulty",
]

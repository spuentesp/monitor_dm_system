"""
Pydantic schemas for canon contradiction detection (EPIC 2).

LAYER: 1 (data-layer)

When a KnowledgePack is applied to a multiverse, we check its extracted items
against the existing canon (facts, axioms already committed to Neo4j). If the
new source says something that contradicts existing canon, we flag it as a
contradiction for manual review.

Contradiction types:
    SEMANTIC_OPPOSITE  — The new statement directly negates an existing fact.
                         E.g. new: "Elves are mortal" vs canon: "Elves are immortal"
    TEMPORAL_OVERRIDE  — A newer source overrides an older one (time-based authority).
    SCOPE_CONFLICT     — Fact A is canon in Universe X but contradicted in Universe Y.
    PARTIAL_OVERLAP    — Two facts cover overlapping but not identical domains.

Resolution strategies:
    NEW_WINS   — The new source is more authoritative; override existing canon.
    OLD_WINS   — Existing canon stands; mark new item as rejected.
    MERGE      — Attempt LLM-assisted merge (produces a suggestion).
    REVIEW     — Escalate to human (default for non-trivial contradictions).
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class ContradictionType(StrEnum):
    """Classification of how two facts conflict."""

    SEMANTIC_OPPOSITE = "semantic_opposite"
    TEMPORAL_OVERRIDE = "temporal_override"
    SCOPE_CONFLICT = "scope_conflict"
    PARTIAL_OVERLAP = "partial_overlap"


class ContradictionSeverity(StrEnum):
    """How serious the contradiction is."""

    LOW = "low"  # Minor detail; can auto-resolve
    MEDIUM = "medium"  # Significant but doesn't break world coherence
    HIGH = "high"  # World-breaking contradiction; must resolve before apply
    CRITICAL = "critical"  # Axiom-level conflict; world integrity at risk


class ContradictionResolution(StrEnum):
    """How to resolve the contradiction."""

    NEW_WINS = "new_wins"
    OLD_WINS = "old_wins"
    MERGE = "merge"
    REVIEW = "review"


class ContradictionFact(BaseModel):
    """One side of a contradiction (either the new item or existing canon)."""

    statement: str = Field(max_length=2000, description="The fact/axiom statement")
    source_name: str | None = Field(None, max_length=300, description="Where this fact came from")
    source_id: UUID | None = Field(None, description="Source UUID")
    canon_level: str = Field(default="proposed", max_length=50)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    fact_type: str = Field(default="fact", max_length=50, description="fact | axiom | lore")


class ContradictionMatch(BaseModel):
    """A single detected contradiction between a new extracted item and existing canon."""

    contradiction_id: str = Field(
        max_length=100,
        description="Stable identifier: 'contra:{category}:{index}:{canon_index}'",
    )
    contradiction_type: ContradictionType
    severity: ContradictionSeverity
    new_fact: ContradictionFact = Field(description="The newly extracted fact/axiom")
    existing_fact: ContradictionFact = Field(description="The existing canon fact/axiom")
    similarity_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="How semantically similar the two statements are (higher = more likely a real contradiction)",
    )
    explanation: str = Field(
        default="",
        max_length=2000,
        description="Human-readable explanation of why this is a contradiction",
    )
    recommended_resolution: ContradictionResolution = Field(
        default=ContradictionResolution.REVIEW,
    )
    category: str = Field(
        default="lore_facts",
        max_length=50,
        description="Which extraction category: axioms, lore_facts, entity_archetypes",
    )
    item_index: int = Field(
        default=0,
        ge=0,
        description="Index of the new item in its extraction array",
    )


class ContradictionResult(BaseModel):
    """Complete result of checking a KnowledgePack against existing canon."""

    checked_against_multiverse: UUID | None = Field(
        None,
        description="Multiverse ID checked against",
    )
    checked_against_universe: UUID | None = Field(
        None,
        description="Universe ID checked against",
    )

    # Per-category matches
    axiom_contradictions: list[ContradictionMatch] = Field(default_factory=list)
    lore_contradictions: list[ContradictionMatch] = Field(default_factory=list)
    entity_contradictions: list[ContradictionMatch] = Field(default_factory=list)

    # Summary stats
    total_contradictions: int = Field(default=0)
    high_severity_count: int = Field(default=0)
    critical_severity_count: int = Field(default=0)

    # All items flattened for easy iteration
    all_matches: list[ContradictionMatch] = Field(default_factory=list)

    def compute_totals(self) -> None:
        """Recompute summary stats from the match lists."""
        self.all_matches = self.axiom_contradictions + self.lore_contradictions + self.entity_contradictions
        self.total_contradictions = len(self.all_matches)
        self.high_severity_count = sum(
            1 for m in self.all_matches if m.severity in (ContradictionSeverity.HIGH, ContradictionSeverity.CRITICAL)
        )
        self.critical_severity_count = sum(1 for m in self.all_matches if m.severity == ContradictionSeverity.CRITICAL)

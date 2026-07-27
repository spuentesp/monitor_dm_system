"""
Pydantic schemas for agent LLM response models.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, uuid, datetime, enum)
CALLED BY: agents layer — Narrator, Resolver, CanonKeeper agents

These schemas are the *return types* that each agent's LLM call must produce.
They live in data-layer so that:
  1. The data-layer can validate them (DRY — single definition)
  2. The agents layer imports them without circular deps

Per LIBRARY_PLAN §AG-A3:
  - NarratorResponse    : narrative text + optional proposals
  - ResolverOutcome     : mechanical resolution record + proposals
  - CanonKeeperVerdict  : accept/reject decision with reasoning
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# =============================================================================
# SHARED
# =============================================================================


class ProposedChangeRef(BaseModel):
    """Lightweight reference to a ProposedChange from an agent response."""

    proposal_id: UUID = Field(
        default_factory=uuid4,
        description="ID of the ProposedChange document (auto-generated if omitted)",
    )
    change_type: str = Field(description="Type of change being proposed")
    summary: str = Field(
        description="One-line human-readable summary of the proposal",
        max_length=500,
    )
    content: dict[str, Any] = Field(
        default_factory=dict,
        description="Payload for the proposed change (matches ProposedChangeCreate.content)",
    )


# =============================================================================
# NARRATOR RESPONSE
# =============================================================================


class NarratorResponse(BaseModel):
    """
    Structured output from the Narrator agent's LLM call.

    Used with ``instructor`` for strict Pydantic enforcement, or with DSPy
    ChainOfThought for creative generation with optional proposals extraction.
    """

    narrative_text: str = Field(
        description="The narrative prose produced for this turn",
        min_length=1,
    )
    proposals: list[ProposedChangeRef] = Field(
        default_factory=list,
        description="Proposed canon changes implicit in the narrative (may be empty)",
    )
    mood: str | None = Field(
        default=None,
        description="Narrative mood/tone for UI hints (e.g. 'tense', 'whimsical')",
        max_length=50,
    )


# =============================================================================
# RESOLVER OUTCOME
# =============================================================================


class ResolverSuccessLevel(StrEnum):
    CRITICAL_SUCCESS = "critical_success"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CRITICAL_FAILURE = "critical_failure"


class ResolverOutcome(BaseModel):
    """
    Structured output from the Resolver agent's LLM call.

    Used with ``instructor`` (strict schema — no partial results accepted).
    """

    success_level: ResolverSuccessLevel = Field(description="Final outcome level of the mechanical resolution")
    roll_total: int | None = Field(
        default=None,
        description="Total value of the dice roll (None for narrative resolutions)",
    )
    roll_breakdown: str | None = Field(
        default=None,
        description="Human-readable breakdown of the roll (e.g. '2d6+3 = 4+3+3 = 10')",
        max_length=200,
    )
    effects: list[str] = Field(
        default_factory=list,
        description="Mechanical effects applied by this resolution (damage, conditions, etc.)",
    )
    narration_hint: str = Field(
        description="Short hint for the Narrator describing how to incorporate this resolution",
        max_length=500,
    )
    proposals: list[ProposedChangeRef] = Field(
        default_factory=list,
        description="State changes implied by this resolution that need canonisation",
    )


# =============================================================================
# CANONKEEPER VERDICT
# =============================================================================


class CanonKeeperDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class CanonKeeperVerdict(BaseModel):
    """
    Structured output from CanonKeeper's evaluation of a ProposedChange.

    Used with ``instructor`` (strict schema — CanonKeeper must give a definitive
    accept/reject/defer; no free-text ambiguity accepted).
    """

    proposal_id: UUID = Field(description="ID of the evaluated ProposedChange")
    decision: CanonKeeperDecision = Field(description="CanonKeeper's ruling on this proposal")
    reasoning: str = Field(
        description="Rationale for the decision (stored in DecisionMetadata)",
        min_length=10,
        max_length=2000,
    )
    canon_node_type: str | None = Field(
        default=None,
        description="Neo4j node label to create if accepted (e.g. 'EntityInstance')",
    )
    canon_properties: dict[str, Any] | None = Field(
        default=None,
        description="Properties for the new canonical node (used only when accepted)",
    )
    decided_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of the verdict",
    )

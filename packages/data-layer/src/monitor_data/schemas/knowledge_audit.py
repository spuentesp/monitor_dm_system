"""
Schemas for the per-character knowledge audit (CF-15 / G09).

The GM can ask what the party knows ("what do they know about the
harbour?"), but cannot *audit* it: there was no view of the facts and
memories the system attributes to a character, with their provenance.

These schemas are that view. Every item says where it came from, so a
doubtful attribution can be challenged rather than merely doubted.

LAYER: 1 (data-layer)
IMPORTS FROM: external libraries (pydantic, uuid)
CALLED BY: mongodb_tools/knowledge_audit.py, UI backend routers
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Where a piece of knowledge came from.
KnowledgeSource = Literal["scene", "witnessed", "common", "proposal", "memory"]

# What kind of record a piece of knowledge is.
KnowledgeKind = Literal["fact", "memory", "proposal"]


class KnowledgeItem(BaseModel):
    """One thing the system believes a character knows."""

    id: str = Field(description="The id of the underlying record")
    kind: KnowledgeKind
    statement: str = Field(description="What the character is believed to know")
    source: KnowledgeSource = Field(
        description=(
            "scene — formed in a scene; witnessed — the character was present "
            "when it happened; common — no witness record, so everyone knows "
            "it; proposal — a pending change about it; memory — the "
            "character's own recollection"
        )
    )
    scene_id: UUID | None = None
    importance: float = Field(default=0.0, ge=0.0, le=1.0)
    certainty: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    canon_level: str = Field(default="", max_length=32)
    suspicious: bool = Field(
        default=False,
        description="Whether the attribution looks doubtful (heuristic, v1)",
    )
    suspicion_reason: str = Field(default="", max_length=500)


class KnowledgeAuditFilter(BaseModel):
    """Which character's knowledge to audit."""

    entity_id: UUID
    universe_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class KnowledgeAudit(BaseModel):
    """Everything the system attributes to one character."""

    entity_id: UUID
    universe_id: UUID | None = None
    items: list[KnowledgeItem] = Field(default_factory=list)
    fact_count: int = 0
    memory_count: int = 0
    proposal_count: int = 0
    suspicious_count: int = 0
    offset: int = 0
    next_offset: int | None = None


class KnowledgeChallenge(BaseModel):
    """A GM challenging one attribution."""

    item_id: str = Field(min_length=1, max_length=200)
    kind: KnowledgeKind = Field(default="memory")
    statement: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    action: Literal["retract", "correct"] = Field(
        default="retract",
        description=(
            "retract — the character does not know this; correct — the statement is wrong and carries the right one"
        ),
    )


__all__ = [
    "KnowledgeAudit",
    "KnowledgeAuditFilter",
    "KnowledgeChallenge",
    "KnowledgeItem",
    "KnowledgeKind",
    "KnowledgeSource",
]

"""
Pydantic schemas for ChangeLog operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

The change_log collection is an APPEND-ONLY audit trail of every
canonical change made to Neo4j nodes and edges. It is written
automatically by the middleware layer whenever CanonKeeper commits
a change to Neo4j.

Records are NEVER updated or deleted.

This enables:
- Full history reconstruction ("what did the world look like at scene 15?")
- Undo/revert operations (compute reverse diff)
- Conflict detection (two changes to the same entity in same transaction)
- GM review of what canonized facts were written this session
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import Authority

# =============================================================================
# ENUMS
# =============================================================================


class ChangeSubjectType(StrEnum):
    """Type of Neo4j node/edge being changed."""

    ENTITY = "entity"
    FACT = "fact"
    EVENT = "event"
    LORE_EVENT = "lore_event"
    STORY = "story"
    SCENE = "scene"
    RELATIONSHIP = "relationship"
    AXIOM = "axiom"
    PARTY = "party"
    SOURCE = "source"


class ChangeType(StrEnum):
    """Type of change operation."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STATE_TAG_ADDED = "state_tag_added"
    STATE_TAG_REMOVED = "state_tag_removed"
    RELATIONSHIP_ADDED = "relationship_added"
    RELATIONSHIP_REMOVED = "relationship_removed"
    CANON_LEVEL_CHANGED = "canon_level_changed"
    RETCONNED = "retconned"


# =============================================================================
# CHANGE LOG SCHEMAS
# =============================================================================


class ChangeLogEntry(BaseModel):
    """A single entry in the append-only change log.

    Created automatically by middleware; never created manually.
    """

    change_id: UUID
    subject_type: ChangeSubjectType
    subject_id: UUID = Field(description="Neo4j node/edge UUID")
    change_type: ChangeType
    timestamp: datetime
    # Field-level change tracking
    field_path: str | None = Field(
        None,
        max_length=200,
        description="Dot-path to changed field (e.g., 'state_tags', 'properties.hp')",
    )
    old_value: Any | None = None
    new_value: Any | None = None
    # Author
    author: str = Field(
        max_length=200,
        description="Who made the change (e.g., 'CanonKeeper', 'User:admin', 'System')",
    )
    authority: Authority
    # Evidence
    evidence_type: str | None = Field(
        None,
        max_length=50,
        description="Evidence kind: scene, turn, proposal, manual",
    )
    evidence_id: UUID | None = None
    reason: str | None = Field(None, max_length=1000, description="Why this change was made")
    # Transaction grouping
    transaction_id: UUID | None = Field(
        None,
        description="Groups related changes that were committed atomically",
    )

    model_config = {"from_attributes": True}


class ChangeLogFilter(BaseModel):
    """Filter for querying the change log (read-only)."""

    subject_type: ChangeSubjectType | None = None
    subject_id: UUID | None = Field(None, description="Get full history of a specific entity")
    change_type: ChangeType | None = None
    author: str | None = Field(None, max_length=200)
    transaction_id: UUID | None = None
    since: datetime | None = Field(None, description="Only return changes after this timestamp")
    until: datetime | None = Field(None, description="Only return changes before this timestamp")
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_order: str = Field(
        default="desc",
        description="Sort by timestamp: desc=newest first",
        pattern="^(asc|desc)$",
    )


class ChangeLogListResponse(BaseModel):
    """Response for change log queries."""

    entries: list[ChangeLogEntry]
    total: int
    limit: int
    offset: int

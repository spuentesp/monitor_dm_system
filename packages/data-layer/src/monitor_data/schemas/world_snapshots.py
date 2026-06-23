"""
Pydantic schemas for WorldSnapshot operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

WorldSnapshots are point-in-time captures of a Universe's state in Neo4j.
They allow the GM to:
  - Create "restore points" before major experimental world changes.
  - Compare the world state between two points in time.
  - Fork a universe into a new alternate timeline.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# SNAPSHOT CONTENT SCHEMAS
# =============================================================================


class WorldSnapshot(BaseModel):
    """The complete content of a world snapshot."""

    universe_id: UUID
    name: str = Field(min_length=1, max_length=200, description="Snapshot name")
    description: str = Field(default="", max_length=1000)

    # State snapshots (JSON blobs)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    facts: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    axioms: List[Dict[str, Any]] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    snapshot_id: UUID = Field(default_factory=lambda: None)  # Set at creation

    model_config = {"from_attributes": True}


# =============================================================================
# SNAPSHOT CRUD SCHEMAS
# =============================================================================


class WorldSnapshotCreate(BaseModel):
    """Request to create a WorldSnapshot."""

    universe_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class WorldSnapshotResponse(BaseModel):
    """Metadata-only response for a WorldSnapshot."""

    snapshot_id: UUID
    universe_id: UUID
    name: str
    description: str
    entity_count: int
    fact_count: int
    relationship_count: int
    axiom_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WorldSnapshotFilter(BaseModel):
    """Filter for listing snapshots."""

    universe_id: Optional[UUID] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class WorldSnapshotListResponse(BaseModel):
    """Response for list operations."""

    snapshots: List[WorldSnapshotResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# SNAPSHOT COMPARE SCHEMAS (M-34)
# =============================================================================


class SnapshotEntityDiff(BaseModel):
    """Diff for a single entity between two snapshots."""

    entity_id: str
    name: str
    diff_type: str = Field(description="Type of diff: 'added', 'removed', 'modified'")
    snapshot_a_state: Optional[Dict[str, Any]] = Field(
        default=None, description="Entity state in the earlier snapshot"
    )
    snapshot_b_state: Optional[Dict[str, Any]] = Field(
        default=None, description="Entity state in the later snapshot"
    )
    changed_fields: Optional[List[str]] = Field(
        default=None, description="Fields that changed (for 'modified' type)"
    )


class SnapshotFactDiff(BaseModel):
    """Diff for a single fact between two snapshots."""

    fact_id: str
    statement: str
    diff_type: str = Field(description="Type of diff: 'added', 'removed', 'modified'")
    snapshot_a_state: Optional[Dict[str, Any]] = Field(default=None)
    snapshot_b_state: Optional[Dict[str, Any]] = Field(default=None)
    changed_fields: Optional[List[str]] = Field(default=None)


class SnapshotRelationshipDiff(BaseModel):
    """Diff for a single relationship between two snapshots."""

    relationship_id: str
    from_entity_id: str
    to_entity_id: str
    relationship_type: str
    diff_type: str = Field(description="Type of diff: 'added', 'removed'")
    snapshot_a_state: Optional[Dict[str, Any]] = Field(default=None)
    snapshot_b_state: Optional[Dict[str, Any]] = Field(default=None)


class SnapshotCompareResponse(BaseModel):
    """Response comparing two world snapshots."""

    snapshot_a_id: UUID
    snapshot_b_id: UUID
    universe_id: UUID
    # Diff summaries
    entities_added: int = 0
    entities_removed: int = 0
    entities_modified: int = 0
    facts_added: int = 0
    facts_removed: int = 0
    facts_modified: int = 0
    relationships_added: int = 0
    relationships_removed: int = 0
    # Detailed diffs (capped for response size)
    entity_diffs: List[SnapshotEntityDiff] = Field(default_factory=list)
    fact_diffs: List[SnapshotFactDiff] = Field(default_factory=list)
    relationship_diffs: List[SnapshotRelationshipDiff] = Field(default_factory=list)
    # Metadata
    snapshot_a_name: str = ""
    snapshot_b_name: str = ""
    snapshot_a_created_at: datetime = Field(default_factory=datetime.utcnow)
    snapshot_b_created_at: datetime = Field(default_factory=datetime.utcnow)
    compared_at: datetime = Field(default_factory=datetime.utcnow)

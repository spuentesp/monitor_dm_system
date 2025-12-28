"""
Base Pydantic models and enums for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, datetime, uuid, enum)
CALLED BY: All other schema modules

These are the foundation models used across all schemas in the data layer.
"""

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class CanonLevel(str, Enum):
    """Canonization status for most canonical nodes (Universe, Entity, Fact, etc)."""

    PROPOSED = "proposed"
    CANON = "canon"
    RETCONNED = "retconned"


class SourceCanonLevel(str, Enum):
    """Canonization status for Source nodes only.

    Sources use 'authoritative' instead of 'retconned' because
    source documents themselves aren't revised—only facts derived
    from them can be retconned.
    """

    PROPOSED = "proposed"
    CANON = "canon"
    AUTHORITATIVE = "authoritative"


class Authority(str, Enum):
    """Who asserted this data (for Facts, Events, Entities)."""

    SOURCE = "source"
    GM = "gm"
    PLAYER = "player"
    SYSTEM = "system"


class AxiomAuthority(str, Enum):
    """Authority for Axiom nodes only (excludes 'player').

    World rules (physics, magic systems) cannot be created by player
    actions—only by GM declaration or authoritative sources.
    """

    SOURCE = "source"
    GM = "gm"
    SYSTEM = "system"


class EntityType(str, Enum):
    """Entity classification."""

    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"
    ORGANIZATION = "organization"


class EntityClass(str, Enum):
    """Axiomatic vs Concrete entity classification."""

    AXIOMATICA = "EntityArchetype"
    CONCRETA = "EntityInstance"


class StoryType(str, Enum):
    """Story type classification."""

    CAMPAIGN = "campaign"
    ARC = "arc"
    EPISODE = "episode"
    ONE_SHOT = "one_shot"


class StoryStatus(str, Enum):
    """Story status."""

    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SceneStatus(str, Enum):
    """Scene workflow status."""

    ACTIVE = "active"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


class ProposalStatus(str, Enum):
    """Proposed change status."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProposalType(str, Enum):
    """Type of proposed change."""

    FACT = "fact"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    STATE_CHANGE = "state_change"
    EVENT = "event"


class Speaker(str, Enum):
    """Who is speaking in a turn."""

    USER = "user"
    GM = "gm"
    ENTITY = "entity"


class SourceType(str, Enum):
    """Type of source material."""

    BOOK = "book"
    RULEBOOK = "rulebook"
    WIKI = "wiki"
    HOMEBREW = "homebrew"
    CUSTOM = "custom"


class DocumentStatus(str, Enum):
    """Status of document extraction."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestProposalType(str, Enum):
    """Type of ingested knowledge proposal."""

    ENTITY = "entity"
    FACT = "fact"
    AXIOM = "axiom"
    RELATIONSHIP = "relationship"


class IngestProposalStatus(str, Enum):
    """Status of ingest proposal."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


# =============================================================================
# BASE MODELS
# =============================================================================


class CanonicalMetadata(BaseModel):
    """Base metadata for all canonical nodes."""

    canon_level: CanonLevel
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    authority: Authority
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BaseResponse(BaseModel):
    """Base response model with common fields."""

    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}

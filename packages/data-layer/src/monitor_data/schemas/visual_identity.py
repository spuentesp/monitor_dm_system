"""
Pydantic schemas for VisualIdentity (Layer 1, Task 1).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools/visual_identities.py (Task 2) and the UI backend.

A VisualIdentity is a structured, canon-aware description of a subject's
appearance. It supports three anchor shapes:

  - card default:       character_id only (no universe context)
  - incarnation:        character_id + universe_id, optional entity_id
  - canonical entity:   entity_id + universe_id

Exactly one anchor must be present. ``entity_id`` is not allowed without
``universe_id``. Approval lifecycle: draft -> approved -> superseded.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

# =============================================================================
# ENUMS
# =============================================================================


class VisualIdentitySource(StrEnum):
    """Origin of the visual identity record."""

    MANUAL = "manual"  # User-authored
    CARD_IMPORT = "card_import"  # Imported from a character card
    CANON = "canon"  # Mirrors a canonical entity's compact identity
    AI_EXTRACTED = "ai_extracted"  # Assembled by an LLM from canon facts


class VisualIdentityStatus(StrEnum):
    """Lifecycle status of a visual identity.

    Draft -> Approved -> Superseded. A superseded identity is no longer the
    current one for its anchor subject, but is kept for history.
    """

    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


# =============================================================================
# STATUS TRANSITIONS
# =============================================================================


def transition_visual_identity_status(
    current: VisualIdentityStatus, target: VisualIdentityStatus
) -> bool:
    """Return True if ``current`` may legally transition to ``target``.

    Allowed transitions:
        DRAFT      -> APPROVED
        APPROVED   -> SUPERSEDED
    """
    if not isinstance(current, VisualIdentityStatus) or not isinstance(
        target, VisualIdentityStatus
    ):
        return False
    if current == target:
        return False
    allowed = {
        VisualIdentityStatus.DRAFT: {VisualIdentityStatus.APPROVED},
        VisualIdentityStatus.APPROVED: {VisualIdentityStatus.SUPERSEDED},
    }
    return target in allowed.get(current, set())


# =============================================================================
# VISUAL IDENTITY SCHEMAS
# =============================================================================


class VisualIdentity(BaseModel):
    """A persisted VisualIdentity record (response shape).

    Anchors:
      - card default:     character_id only
      - incarnation:      character_id + universe_id [optional entity_id]
      - canonical entity: entity_id + universe_id
    """

    identity_id: UUID = Field(default_factory=uuid4)
    character_id: str | None = Field(
        default=None,
        max_length=200,
        description="Card-level character this identity belongs to",
    )
    entity_id: UUID | None = Field(
        default=None,
        description="Canonical entity (Neo4j) this identity is anchored to",
    )
    universe_id: UUID | None = Field(
        default=None,
        description="Universe scope; required when entity_id is set",
    )
    version: int = Field(default=1, ge=1, description="Monotonic version per anchor")
    description: str = Field(default="", max_length=4000)
    species_or_type: str | None = Field(default=None, max_length=200)
    apparent_age: str | None = Field(default=None, max_length=200)
    build: str | None = Field(default=None, max_length=200)
    hair: str | None = Field(default=None, max_length=500)
    eyes: str | None = Field(default=None, max_length=500)
    skin_or_surface: str | None = Field(default=None, max_length=500)
    signature_attire: str | None = Field(default=None, max_length=1000)
    distinguishing_features: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Trait markers; capped at 20 to keep prompts focused",
    )
    palette: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Color cues for the image prompt",
    )
    style_hint: str | None = Field(default=None, max_length=500)
    source: VisualIdentitySource = VisualIdentitySource.MANUAL
    approved_reference_asset_ids: list[UUID] = Field(default_factory=list)
    status: VisualIdentityStatus = VisualIdentityStatus.DRAFT
    decision_proposal_id: UUID | None = Field(
        default=None,
        description="ProposedChange that canonized (approved) or rejected this version",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _validate_anchor(self) -> VisualIdentity:
        if self.character_id is None and self.entity_id is None:
            raise ValueError(
                "VisualIdentity requires an anchor: character_id (card/incarnation) "
                "or entity_id (canonical entity)."
            )
        if self.entity_id is not None and self.universe_id is None:
            raise ValueError(
                "VisualIdentity.entity_id requires universe_id as its canonical anchor."
            )
        return self


class VisualIdentityCreate(BaseModel):
    """Request to create a VisualIdentity.

    Validation mirrors ``VisualIdentity``. ``created_at`` / ``updated_at`` are
    set by the persistence layer, not the caller.
    """

    character_id: str | None = Field(default=None, max_length=200)
    entity_id: UUID | None = None
    universe_id: UUID | None = None
    description: str = Field(default="", max_length=4000)
    species_or_type: str | None = Field(default=None, max_length=200)
    apparent_age: str | None = Field(default=None, max_length=200)
    build: str | None = Field(default=None, max_length=200)
    hair: str | None = Field(default=None, max_length=500)
    eyes: str | None = Field(default=None, max_length=500)
    skin_or_surface: str | None = Field(default=None, max_length=500)
    signature_attire: str | None = Field(default=None, max_length=1000)
    distinguishing_features: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Trait markers; capped at 20 to keep prompts focused",
    )
    palette: list[str] = Field(default_factory=list, max_length=12)
    style_hint: str | None = Field(default=None, max_length=500)
    source: VisualIdentitySource = VisualIdentitySource.MANUAL
    approved_reference_asset_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_anchor(self) -> VisualIdentityCreate:
        if self.character_id is None and self.entity_id is None:
            raise ValueError(
                "VisualIdentity requires an anchor: character_id (card/incarnation) "
                "or entity_id (canonical entity)."
            )
        if self.entity_id is not None and self.universe_id is None:
            raise ValueError(
                "VisualIdentity.entity_id requires universe_id as its canonical anchor."
            )
        return self


class VisualIdentityUpdate(BaseModel):
    """Mutable subset of a VisualIdentity.

    ``identity_id`` and ``expected_version`` identify the version being
    replaced; they are optimistic-lock metadata, not mutable identity fields.
    Anchor fields (``character_id``, ``entity_id``, ``universe_id``) and
    ``version`` are not mutable here; the persistence layer carries them into
    the next immutable version.
    """

    identity_id: UUID | None = Field(
        default=None,
        description="Identity version to replace; required by persistence updates",
    )
    expected_version: int | None = Field(
        default=None,
        ge=1,
        description="Optimistic-lock version; required by persistence updates",
    )
    description: str | None = Field(default=None, max_length=4000)
    species_or_type: str | None = Field(default=None, max_length=200)
    apparent_age: str | None = Field(default=None, max_length=200)
    build: str | None = Field(default=None, max_length=200)
    hair: str | None = Field(default=None, max_length=500)
    eyes: str | None = Field(default=None, max_length=500)
    skin_or_surface: str | None = Field(default=None, max_length=500)
    signature_attire: str | None = Field(default=None, max_length=1000)
    distinguishing_features: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Trait markers; capped at 20",
    )
    palette: list[str] | None = Field(default=None, max_length=12)
    style_hint: str | None = Field(default=None, max_length=500)
    source: VisualIdentitySource | None = None
    approved_reference_asset_ids: list[UUID] | None = None
    status: VisualIdentityStatus | None = None


class VisualIdentityFilter(BaseModel):
    """Filter for listing visual identities (gallery/editor views).

    All filters are exact matches; ``status=None`` lists every lifecycle
    state (draft, approved, superseded history).
    """

    character_id: str | None = Field(default=None, max_length=200)
    entity_id: UUID | None = None
    universe_id: UUID | None = None
    status: VisualIdentityStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

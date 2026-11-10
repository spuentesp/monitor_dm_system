"""
Pydantic schemas for the GM prep bundle (prep-to-table, CF-7).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools/gm_prep.py, routers/gm_tools.py

A prep bundle is "tonight's" session preparation: the NPCs, locations and
plot threads the GM reviewed from their notes before the session. It is
user-owned scratch state — no canon, no Neo4j writes, no CanonKeeper gate
(accepted threads are committed as plot threads by the router, and new
NPCs/locations are staged as ProposedChange items for the CF-8 queue).
One document per (universe, story); a story-less bundle is keyed on an
empty story key.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# PREP BUNDLE ITEM SCHEMAS
# =============================================================================


class GmPrepNpc(BaseModel):
    """One NPC the GM reviewed for tonight's session."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    want: str = Field(default="", max_length=500, description="What this NPC wants tonight")
    existing_entity_id: UUID | None = Field(
        default=None,
        description="Canon entity this NPC was matched against, when one exists",
    )


class GmPrepLocation(BaseModel):
    """One location the GM reviewed for tonight's session."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    existing_entity_id: UUID | None = Field(
        default=None,
        description="Canon entity this location was matched against, when one exists",
    )


class GmPrepThread(BaseModel):
    """One plot thread the GM reviewed for tonight's session."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    urgency: str = Field(default="medium", max_length=20)
    thread_id: str | None = Field(
        default=None,
        description="Neo4j plot thread id, set when the bundle was committed",
    )


# =============================================================================
# PREP BUNDLE CRUD SCHEMAS
# =============================================================================


class GmPrepBundleUpsert(BaseModel):
    """Request to upsert the prep bundle for a (universe, story)."""

    universe_id: UUID
    story_id: UUID | None = None
    npcs: list[GmPrepNpc] = Field(default_factory=list)
    locations: list[GmPrepLocation] = Field(default_factory=list)
    threads: list[GmPrepThread] = Field(default_factory=list)
    source: str = Field(default="prep_flow", max_length=100)


class GmPrepBundleResponse(BaseModel):
    """Response: the current prep bundle for a (universe, story)."""

    universe_id: UUID
    story_id: UUID | None = None
    npcs: list[GmPrepNpc] = Field(default_factory=list)
    locations: list[GmPrepLocation] = Field(default_factory=list)
    threads: list[GmPrepThread] = Field(default_factory=list)
    source: str = "prep_flow"
    updated_at: datetime

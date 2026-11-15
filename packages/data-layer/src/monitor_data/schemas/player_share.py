"""
Schemas for player-facing share links and shared artifacts (CF-14 / G07).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools/player_share.py, ShareAgent (Layer 2), UI routers (Layer 3)

A share link is a single unguessable token per story (v1). The token is the
credential for the public ``/share/{token}`` routes — no player accounts.
Shared artifacts are the recaps and handouts a GM explicitly publishes;
they live in Mongo only and never touch Neo4j (canon untouched).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ShareArtifactType(str, Enum):
    """What kind of player-facing artifact was published."""

    RECAP = "recap"
    HANDOUT = "handout"


class ShareSpoilerLevel(str, Enum):
    """Who a shared artifact is visible to (resolved server-side)."""

    PARTY = "party"
    CHARACTER = "character"


class PlayerShare(BaseModel):
    """A story-scoped share token (CF-14)."""

    id: UUID
    story_id: UUID
    universe_id: UUID
    owner_id: str = Field(description="Principal user_id that created the link")
    token: str = Field(description="Unguessable credential for /share/{token}")
    revoked: bool = False
    created_at: datetime
    expires_at: datetime | None = Field(None, description="Optional expiry; None = never")


class PlayerShareCreate(BaseModel):
    """Create a fresh share token for a story."""

    story_id: UUID
    universe_id: UUID
    owner_id: str
    expires_at: datetime | None = None


class SharedArtifact(BaseModel):
    """A recap or handout the GM can publish to a share link (CF-14)."""

    id: UUID
    story_id: UUID
    universe_id: UUID
    owner_id: str
    artifact_type: ShareArtifactType
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(description="Markdown body shown to players")
    spoiler_level: ShareSpoilerLevel = ShareSpoilerLevel.PARTY
    scope_character_id: UUID | None = Field(
        None, description="PC this handout is written for (spoiler_level=character)"
    )
    source_fact_ids: list[UUID] = Field(
        default_factory=list,
        description=(
            "Canon facts this artifact draws on; other party members see a "
            "character-scoped artifact only when they witnessed all of them"
        ),
    )
    session_id: UUID | None = None
    published: bool = False
    created_at: datetime
    updated_at: datetime


class SharedArtifactCreate(BaseModel):
    """Create a shared artifact (publish on create, or draft)."""

    story_id: UUID
    universe_id: UUID
    owner_id: str
    artifact_type: ShareArtifactType
    title: str = Field(min_length=1, max_length=300)
    content: str
    spoiler_level: ShareSpoilerLevel = ShareSpoilerLevel.PARTY
    scope_character_id: UUID | None = None
    source_fact_ids: list[UUID] = Field(default_factory=list)
    session_id: UUID | None = None
    published: bool = False


class PlayerArtifactSummary(BaseModel):
    """List entry on the public player view — never carries drafts."""

    id: UUID
    artifact_type: ShareArtifactType
    title: str
    spoiler_level: ShareSpoilerLevel
    updated_at: datetime


class PlayerShareCharacter(BaseModel):
    """Roster entry so the share page can offer a character selector."""

    id: UUID
    name: str


class PlayerView(BaseModel):
    """What a token holder may see for a story (CF-14)."""

    story_id: UUID
    character_id: UUID | None = None
    artifacts: list[PlayerArtifactSummary] = Field(default_factory=list)
    characters: list[PlayerShareCharacter] = Field(default_factory=list)

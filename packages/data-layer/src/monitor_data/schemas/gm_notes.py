"""
Pydantic schemas for GM notebook (per-universe scratchpad) operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools/gm_notes.py, routers/gm_notes.py

GM notebooks are user-owned scratchpads — one doc per universe.
They are NOT canon (no Neo4j writes, no CanonKeeper gate). Per-user
identity is the responsibility of the caller (router layer); the data-layer
is keyed solely on ``universe_id``.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# GM NOTE CRUD SCHEMAS
# =============================================================================


class GmNoteUpsert(BaseModel):
    """Request to upsert the GM notebook for a universe.

    The note is addressed by ``universe_id`` (URL path); ``content`` is the
    payload stored as a single text blob. A single upsert per universe
    replaces the previous content.
    """

    content: str = Field(
        ...,
        max_length=50000,
        description="Free-form GM notes (markdown/plain); ≤50,000 chars",
    )


class GmNoteResponse(BaseModel):
    """Response: the current notebook content for a universe."""

    universe_id: UUID
    content: str
    updated_at: datetime

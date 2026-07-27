"""GM notebook router — P2.3 (GM Assistant scratchpad persistence).

Per-universe notebook: one note per universe, addressed by ``universe_id``.
GET returns 200 with empty content if no note exists yet (the row is
created on the first PUT). This is a user-owned scratchpad — no canon,
no Neo4j, no CanonKeeper gate.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

from fastapi import APIRouter
from monitor_data.schemas.gm_notes import GmNoteResponse, GmNoteUpsert
from monitor_data.tools.mongodb_tools import (
    mongodb_get_gm_note,
    mongodb_upsert_gm_note,
)

from .ingest_shared import db_op, validate_uuid

router = APIRouter()


@router.get("/gm/notes/{universe_id}", response_model=GmNoteResponse)
async def get_gm_note(universe_id: str) -> GmNoteResponse:
    """Return the GM notebook for a universe, or 200 with empty content if absent.

    The frontend treats an empty ``content`` as "no notes yet" and binds
    the textarea to an empty string. We deliberately return 200 (not 404)
    so the frontend does not need a special-case for the first load.
    """
    universe_uuid = validate_uuid(universe_id, "universe_id")
    with db_op():
        note = mongodb_get_gm_note(universe_uuid)
    if note is None:
        # Empty note: round-trip UTC epoch so the response is always well-formed.
        from datetime import UTC, datetime

        return GmNoteResponse(
            universe_id=universe_uuid,
            content="",
            updated_at=datetime.now(UTC),
        )
    return note


@router.put("/gm/notes/{universe_id}", response_model=GmNoteResponse)
async def upsert_gm_note(universe_id: str, body: GmNoteUpsert) -> GmNoteResponse:
    """Upsert the GM notebook for a universe.

    Replaces the prior content with the new payload. The response contains
    the post-write state (with refreshed ``updated_at``) so the frontend can
    reflect the save timestamp without a follow-up GET.
    """
    universe_uuid = validate_uuid(universe_id, "universe_id")
    with db_op():
        return mongodb_upsert_gm_note(universe_uuid, body)

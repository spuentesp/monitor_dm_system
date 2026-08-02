"""Character → canon promotion.

Routes the light-RP conversation history for a character through
``SessionListenerModule`` and emits a batch of ``ProposedChange`` documents
the user can then commit via the existing CanonKeeper flow. v1 deliberately
skips entity resolution and contradiction arbitration; the proposals are
written, the user reviews them, and CanonKeeper evaluates.

This is the *plumbing* of the promotion machinery. The "is imported Elara
the same entity as the ranger of the eastern woods?" question is item 4's
next layer (Qdrant semantic dedup + a user-facing diff view) and is left
for a focused follow-up.

LAYER: 3 (UI backend)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from monitor_agents.ingestion import session_ingest as _session_ingest
from monitor_data.db import mongodb as _mongodb
from monitor_data.schemas.base import Authority, ProposalType, ProposalStatus

from . import character_storage as _character_storage

logger = structlog.get_logger()

router = APIRouter()


class PromotionRequest(BaseModel):
    conversation_id: str | None = Field(
        default=None,
        description=(
            "Conversation to promote. If omitted, the most recent active "
            "conversation for this character is used."
        ),
    )
    context: str | None = Field(
        default=None,
        description="Optional extra context threaded into the listener prompt.",
    )


class PromotionPreview(BaseModel):
    character_id: str
    conversation_id: str
    events_proposed: int
    lore_proposed: int
    threads_proposed: int
    proposal_ids: list[str]
    skipped: list[str] = Field(
        default_factory=list,
        description="Why a piece of extraction was dropped (e.g. empty statement).",
    )


def _turns_to_text(turns: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for turn in turns:
        speaker = turn.get("speaker_role") or turn.get("entity_name") or "Player"
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        parts.append(f"{speaker}: {text}")
    return "\n\n".join(parts)


def _find_target_conversation(character_id: str, conversation_id: str | None) -> dict[str, Any]:
    """Resolve the conversation to promote. Raises HTTPException on miss."""
    coll = _mongodb.get_mongodb_client().get_collection("conversations")
    if conversation_id:
        doc = coll.find_one({"conversation_id": conversation_id})
        if not doc:
            raise HTTPException(
                status_code=404, detail=f"Conversation {conversation_id} not found."
            )
        return doc  # type: ignore[no-any-return]
    active = coll.find_one(
        {"status": "active", "lorebook_character_ids": character_id},
        sort=[("updated_at", -1)],
    )
    if not active:
        raise HTTPException(
            status_code=409,
            detail="No active conversation to promote. Start a conversation first, "
            "or pass a conversation_id explicitly.",
        )
    return active  # type: ignore[no-any-return]


@router.post(
    "/characters/{character_id}/promote",
    response_model=PromotionPreview,
)
async def promote_character(
    character_id: str, body: PromotionRequest | None = None
) -> PromotionPreview:
    """Promote a light-RP character's conversation history to ProposedChanges.

    The conversation is found, its turns are formatted, ``SessionListenerModule``
    extracts events / new_lore / active_threads, and each item becomes a
    ``ProposedChange`` document. Evidence is intentionally omitted in v1 — the
    Evidence schema demands a UUID anchor that the light-RP transcript doesn't
    provide precisely; the conversation_id is carried inside the proposal's
    ``content`` for the diff view to look up.
    """
    body = body or PromotionRequest()
    char = _character_storage.get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found.")

    conv = _find_target_conversation(character_id, body.conversation_id)
    turns = conv.get("turns") or []
    turns_text = _turns_to_text(turns)
    if not turns_text:
        raise HTTPException(
            status_code=422,
            detail=f"Conversation {conv.get('conversation_id')} has no speech turns to promote.",
        )

    context = body.context or (
        f"Promoting light-RP conversation history for character '{char.get('name', character_id)}'."
    )

    extraction = _session_ingest.SessionListenerModule().forward(turns=turns_text, context=context)

    conv_anchor = str(conv.get("conversation_id"))
    proposal_ids: list[str] = []
    skipped: list[str] = []
    events_count = lore_count = threads_count = 0

    def _emit(content: dict[str, Any], confidence: float) -> None:
        nonlocal events_count, lore_count, threads_count
        # Write directly to the collection: entity-bound promotion has no
        # scene / story to anchor against, and ``ProposedChangeCreate`` enforces
        # the scene-or-story rule at the model level. We mirror the document
        # shape the tool emits so CanonKeeper's evaluator works unchanged.
        try:
            proposal_id = uuid.uuid4()
            now = datetime.now(UTC)
            doc: dict[str, Any] = {
                "proposal_id": str(proposal_id),
                "scene_id": None,
                "story_id": None,
                "turn_id": None,
                "change_type": ProposalType.FACT.value,
                "content": content,
                "evidence": [],
                "confidence": confidence,
                "authority": Authority.SYSTEM.value,
                "proposer": f"character_promotion:{character_id}",
                "status": ProposalStatus.PENDING.value,
                "decision_metadata": None,
                "promotion_intent": None,
                "interaction_count": 1,
                "is_mechanically_bound": False,
                "created_at": now,
                "updated_at": now,
            }
            _mongodb.get_mongodb_client().get_collection("proposed_changes").insert_one(doc)
        except Exception as exc:
            logger.warning("promotion_proposal_create_failed", exc_info=True)
            skipped.append(str(exc))
            return
        proposal_ids.append(str(proposal_id))
        # Type tag so the counts land in the right bucket after persistence.
        if content.get("source") == "session_listener":
            if "description" in content:
                threads_count += 1
            else:
                lore_count += 1
        else:
            events_count += 1

    for event in extraction.events or []:
        statement = (event.statement or "").strip()
        if not statement:
            skipped.append("event: empty statement")
            continue
        _emit(
            {
                "statement": statement,
                "involved_entities": list(event.involved_entities or []),
                "consequence": event.consequence,
                "is_lore": event.is_lore,
                "conversation_id": conv_anchor,
            },
            confidence=0.7,
        )

    for lore in extraction.new_lore or []:
        statement = (lore or "").strip()
        if not statement:
            skipped.append("lore: empty statement")
            continue
        _emit(
            {
                "statement": statement,
                "conversation_id": conv_anchor,
                "source": "session_listener",
            },
            confidence=0.6,
        )

    for thread in extraction.active_threads or []:
        description = (thread or "").strip()
        if not description:
            skipped.append("thread: empty description")
            continue
        _emit(
            {
                "description": description,
                "conversation_id": conv_anchor,
                "source": "session_listener",
            },
            confidence=0.5,
        )

    return PromotionPreview(
        character_id=character_id,
        conversation_id=conv_anchor,
        events_proposed=events_count,
        lore_proposed=lore_count,
        threads_proposed=threads_count,
        proposal_ids=proposal_ids,
        skipped=skipped,
    )

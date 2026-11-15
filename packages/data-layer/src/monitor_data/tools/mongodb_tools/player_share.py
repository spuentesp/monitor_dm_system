"""
MongoDB tools for player share tokens and shared artifacts (CF-14 / G07).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: ShareAgent (Layer 2) via MCP tools

Two user-owned collections — no canon, no Neo4j, no CanonKeeper gate:

- ``player_share_tokens`` — one unguessable token per story (v1), revocable.
- ``shared_artifacts``   — recaps/handouts with a ``published`` toggle; only
  published artifacts are ever surfaced on ``/share/*``.

Ownership is predicated in every read/update that leaves the creating
principal: foreign IDs behave exactly like missing ones (generic miss).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.player_share import (
    PlayerShare,
    PlayerShareCreate,
    SharedArtifact,
    SharedArtifactCreate,
    ShareArtifactType,
    ShareSpoilerLevel,
)

log = structlog.get_logger()

_SHARE_COLLECTION = "player_share_tokens"
_ARTIFACT_COLLECTION = "shared_artifacts"
# 32 url-safe bytes ≈ 256 bits of entropy — unguessable as a bearer credential.
_TOKEN_BYTES = 32


def _share_collection() -> Any:
    return get_mongodb_client().get_collection(_SHARE_COLLECTION)


def _artifact_collection() -> Any:
    return get_mongodb_client().get_collection(_ARTIFACT_COLLECTION)


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _share_to_model(doc: dict[str, Any]) -> PlayerShare:
    return PlayerShare(
        id=UUID(str(doc["id"])),
        story_id=UUID(str(doc["story_id"])),
        universe_id=UUID(str(doc["universe_id"])),
        owner_id=str(doc.get("owner_id", "")),
        token=str(doc["token"]),
        revoked=bool(doc.get("revoked", False)),
        created_at=_parse_dt(doc.get("created_at")) or _now(),
        expires_at=_parse_dt(doc.get("expires_at")),
    )


def _artifact_to_model(doc: dict[str, Any]) -> SharedArtifact:
    return SharedArtifact(
        id=UUID(str(doc["id"])),
        story_id=UUID(str(doc["story_id"])),
        universe_id=UUID(str(doc["universe_id"])),
        owner_id=str(doc.get("owner_id", "")),
        artifact_type=ShareArtifactType(str(doc["artifact_type"])),
        title=str(doc["title"]),
        content=str(doc.get("content", "")),
        spoiler_level=ShareSpoilerLevel(str(doc.get("spoiler_level", ShareSpoilerLevel.PARTY.value))),
        scope_character_id=UUID(str(doc["scope_character_id"])) if doc.get("scope_character_id") else None,
        source_fact_ids=[UUID(str(f)) for f in doc.get("source_fact_ids") or []],
        session_id=UUID(str(doc["session_id"])) if doc.get("session_id") else None,
        published=bool(doc.get("published", False)),
        created_at=_parse_dt(doc.get("created_at")) or _now(),
        updated_at=_parse_dt(doc.get("updated_at")) or _now(),
    )


# =============================================================================
# SHARE TOKEN OPERATIONS (CF-14)
# =============================================================================


def mongodb_create_player_share(params: PlayerShareCreate) -> PlayerShare:
    """Mint a new share token for a story. Always creates a fresh token."""
    share = PlayerShare(
        id=uuid4(),
        story_id=params.story_id,
        universe_id=params.universe_id,
        owner_id=params.owner_id,
        token=secrets.token_urlsafe(_TOKEN_BYTES),
        revoked=False,
        created_at=_now(),
        expires_at=params.expires_at,
    )
    _share_collection().insert_one(
        {
            "id": str(share.id),
            "story_id": str(share.story_id),
            "universe_id": str(share.universe_id),
            "owner_id": share.owner_id,
            "token": share.token,
            "revoked": False,
            "created_at": share.created_at.isoformat(),
            "expires_at": share.expires_at.isoformat() if share.expires_at else None,
        }
    )
    log.info("player_share_created", share_id=str(share.id), story_id=str(share.story_id))
    return share


def mongodb_get_player_share_by_token(token: str) -> PlayerShare | None:
    """Look up a share doc by its bearer token (revoked/expired included)."""
    if not token:
        return None
    doc = _share_collection().find_one({"token": token})
    return _share_to_model(doc) if doc else None


def mongodb_get_player_share_for_story(story_id: UUID) -> PlayerShare | None:
    """The story's latest active (non-revoked, non-expired) share token."""
    now = _now()
    candidates: list[PlayerShare] = []
    for doc in _share_collection().find({"story_id": str(story_id), "revoked": False}):
        share = _share_to_model(doc)
        if share.expires_at is not None and share.expires_at <= now:
            continue
        candidates.append(share)
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.created_at)


def mongodb_revoke_player_share(story_id: UUID, owner_id: str, universe_id: UUID) -> bool:
    """Revoke the story's active share token.

    Predicated on owner + universe so a foreign caller can never revoke
    someone else's link. Returns True when a live token was revoked.
    """
    result = _share_collection().update_many(
        {
            "story_id": str(story_id),
            "owner_id": owner_id,
            "universe_id": str(universe_id),
            "revoked": False,
        },
        {"$set": {"revoked": True}},
    )
    modified = int(getattr(result, "modified_count", 0) or 0)
    if modified:
        log.info("player_share_revoked", story_id=str(story_id))
    return modified > 0


# =============================================================================
# SHARED ARTIFACT OPERATIONS (CF-14)
# =============================================================================


def mongodb_create_shared_artifact(params: SharedArtifactCreate) -> SharedArtifact:
    """Persist a recap/handout draft or published artifact (Mongo only)."""
    now = _now()
    artifact = SharedArtifact(
        id=uuid4(),
        story_id=params.story_id,
        universe_id=params.universe_id,
        owner_id=params.owner_id,
        artifact_type=params.artifact_type,
        title=params.title,
        content=params.content,
        spoiler_level=params.spoiler_level,
        scope_character_id=params.scope_character_id,
        source_fact_ids=params.source_fact_ids,
        session_id=params.session_id,
        published=params.published,
        created_at=now,
        updated_at=now,
    )
    _artifact_collection().insert_one(
        {
            "id": str(artifact.id),
            "story_id": str(artifact.story_id),
            "universe_id": str(artifact.universe_id),
            "owner_id": artifact.owner_id,
            "artifact_type": artifact.artifact_type.value,
            "title": artifact.title,
            "content": artifact.content,
            "spoiler_level": artifact.spoiler_level.value,
            "scope_character_id": str(artifact.scope_character_id) if artifact.scope_character_id else None,
            "source_fact_ids": [str(f) for f in artifact.source_fact_ids],
            "session_id": str(artifact.session_id) if artifact.session_id else None,
            "published": artifact.published,
            "created_at": artifact.created_at.isoformat(),
            "updated_at": artifact.updated_at.isoformat(),
        }
    )
    return artifact


def mongodb_get_shared_artifact(artifact_id: UUID) -> SharedArtifact | None:
    doc = _artifact_collection().find_one({"id": str(artifact_id)})
    return _artifact_to_model(doc) if doc else None


def mongodb_list_shared_artifacts(story_id: UUID, published_only: bool = False) -> list[SharedArtifact]:
    """Artifacts for a story; ``published_only`` is the /share/* read path."""
    query: dict[str, Any] = {"story_id": str(story_id)}
    if published_only:
        query["published"] = True
    artifacts = [_artifact_to_model(d) for d in _artifact_collection().find(query)]
    artifacts.sort(key=lambda a: a.created_at)
    return artifacts


def mongodb_set_shared_artifact_published(artifact_id: UUID, universe_id: UUID, owner_id: str, published: bool) -> bool:
    """Toggle the published flag, predicated on universe + owner.

    A foreign or missing artifact behaves like a miss (returns False) so
    cross-tenant unpublish probes reveal nothing.
    """
    result = _artifact_collection().update_one(
        {
            "id": str(artifact_id),
            "universe_id": str(universe_id),
            "owner_id": owner_id,
        },
        {"$set": {"published": bool(published), "updated_at": _now().isoformat()}},
    )
    return int(getattr(result, "modified_count", 0) or 0) > 0

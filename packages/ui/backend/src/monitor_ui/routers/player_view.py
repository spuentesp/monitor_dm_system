"""
Public player view — share-link routes (CF-14 / G07).

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: monitor_agents (Layer 2)

UNAUTHENTICATED BY DESIGN: the unguessable token in the path is the
credential (v1 — no player accounts). Every handler:

1. rate-limits per (client IP, token) before touching storage,
2. delegates to ShareAgent — the only reader of these collections — and
3. maps every share failure to the same generic 404 so revoked, expired,
   unknown, draft, and foreign resources are indistinguishable.

No ``get_current_user``, no ``resource_route_guard``: adding either would
lock players out of their own recap.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from monitor_agents.player_share import (
    ShareAgent,
    ShareError,
)
from monitor_data.schemas.player_share import (
    PlayerView,
    ShareArtifactType,
    SharedArtifact,
)
from monitor_ui.auth import RateLimiter, client_ip
from monitor_ui.config import UISettings, get_settings

log = structlog.get_logger()

# The router deliberately has NO auth dependency: token-in-path is auth.
router = APIRouter()

_share_limiter: RateLimiter | None = None


def get_share_limiter(settings: UISettings) -> RateLimiter:
    """Process-wide limiter for /share/* (per client IP + token).

    Recreated when settings change so tests can tighten the limit via env.
    """
    global _share_limiter
    if (
        _share_limiter is None
        or _share_limiter._limit != settings.share_rate_limit
        or _share_limiter._window != settings.auth_rate_window_seconds
    ):
        _share_limiter = RateLimiter(settings.share_rate_limit, settings.auth_rate_window_seconds)
    return _share_limiter


async def _rate_limit(request: Request, settings: UISettings, token: str) -> None:
    key = f"{client_ip(request, settings)}:{token}"
    if not await get_share_limiter(settings).hit(key):
        log.warning("share_rate_limited", path=request.url.path)
        raise HTTPException(status_code=429, detail="Too many requests")


def _parse_viewer_character(viewer_character: str | None) -> UUID | None:
    """Parse the optional ``viewer_character`` query hint (not an ownership id).

    Deliberately not named ``character_id``: that name is in ownership's
    resolver table, and this value is a selection hint resolved against the
    share roster server-side — never a credential.
    """
    if viewer_character is None or viewer_character == "":
        return None
    try:
        return UUID(viewer_character)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid viewer_character format") from exc


def _share_agent() -> ShareAgent:
    return ShareAgent()


def _not_found(exc: ShareError) -> HTTPException:
    # One status for unknown/revoked/expired/draft/foreign — never leak which.
    log.debug("share_access_refused", reason=type(exc).__name__)
    return HTTPException(status_code=404, detail="Not found")


@router.get("/share/{token}", response_model=PlayerView)
async def share_index(
    token: str,
    request: Request,
    viewer_character: str | None = Query(None, description="Viewer's selected party member"),
    settings: UISettings = Depends(get_settings),
    agent: ShareAgent = Depends(_share_agent),
) -> PlayerView:
    """Published recaps + handouts for the token's story (party-level v1)."""
    await _rate_limit(request, settings, token)
    try:
        share = await agent.resolve_share(token)
        return await agent.build_player_view(
            share.story_id, token, character_id=_parse_viewer_character(viewer_character)
        )
    except ShareError as exc:
        raise _not_found(exc) from exc


async def _load_visible(
    token: str,
    artifact_id: UUID,
    *,
    expected_type: ShareArtifactType | None,
    viewer_character: str | None,
    request: Request,
    settings: UISettings,
    agent: ShareAgent,
) -> SharedArtifact:
    await _rate_limit(request, settings, token)
    try:
        share = await agent.resolve_share(token)
        return await agent.get_visible_artifact(
            share.story_id,
            token,
            artifact_id,
            character_id=_parse_viewer_character(viewer_character),
            expected_type=expected_type,
        )
    except ShareError as exc:
        raise _not_found(exc) from exc


@router.get("/share/{token}/recap/{artifact_id}", response_model=SharedArtifact)
async def share_recap(
    token: str,
    artifact_id: UUID,
    request: Request,
    viewer_character: str | None = Query(None),
    settings: UISettings = Depends(get_settings),
    agent: ShareAgent = Depends(_share_agent),
) -> SharedArtifact:
    """One published recap. Handout ids on this route are 404 (type-checked)."""
    return await _load_visible(
        token,
        artifact_id,
        expected_type=ShareArtifactType.RECAP,
        viewer_character=viewer_character,
        request=request,
        settings=settings,
        agent=agent,
    )


@router.get("/share/{token}/handout/{artifact_id}", response_model=SharedArtifact)
async def share_handout(
    token: str,
    artifact_id: UUID,
    request: Request,
    viewer_character: str | None = Query(None),
    settings: UISettings = Depends(get_settings),
    agent: ShareAgent = Depends(_share_agent),
) -> SharedArtifact:
    """One published handout (character-scoped ones run the spoiler check)."""
    return await _load_visible(
        token,
        artifact_id,
        expected_type=ShareArtifactType.HANDOUT,
        viewer_character=viewer_character,
        request=request,
        settings=settings,
        agent=agent,
    )


@router.get("/share/{token}/export/{artifact_id}.md")
async def share_export_markdown(
    token: str,
    artifact_id: UUID,
    request: Request,
    viewer_character: str | None = Query(None),
    settings: UISettings = Depends(get_settings),
    agent: ShareAgent = Depends(_share_agent),
) -> Response:
    """Markdown (.md) download of any artifact this viewer may see (CF-14)."""
    artifact = await _load_visible(
        token,
        artifact_id,
        expected_type=None,  # export works for recaps and handouts alike
        viewer_character=viewer_character,
        request=request,
        settings=settings,
        agent=agent,
    )
    markdown = agent.export_markdown(artifact)
    filename = f"{artifact.title.strip().lower().replace(' ', '-')[:60] or 'artifact'}.md"
    return PlainTextResponse(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

"""
Image generation router — portraits and scene illustrations.

Principle (spec §6): no standalone image tool; generate where content lives.
Provider config lives in the LLM registry (a ``llm_providers`` row with
``role='image'``); generated images are stored in MinIO and served through
short-lived presigned URLs. Character ``avatar_url`` stores the MinIO object
*key* — ``GET /avatar/{id}` issues a fresh presigned redirect for ``<img>``
tags, so expiring URLs never get persisted.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from monitor_data.db.minio import get_minio_client
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.postgres import get_postgres_client
from monitor_data.llm.image_providers import ImageProviderAdapter, resolve_image_adapter
from pydantic import BaseModel, Field

from .character_storage import get_character, update_character
from .chat_persistence import db_load_messages

router = APIRouter()

_NO_PROVIDER_DETAIL = (
    "No image provider configured. Add a MiniMax (image-01) or Google "
    "(gemini-2.5-flash-image) provider and assign it the 'image' role under "
    "/config → LLM Providers."
)

# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class PortraitRequest(BaseModel):
    character_id: str


class PortraitResponse(BaseModel):
    avatar_url: str
    key: str


class SceneRequest(BaseModel):
    conversation_id: str | None = None
    session_id: str | None = None
    last_n: int = Field(default=12, ge=1, le=50)


class SceneResponse(BaseModel):
    image_url: str
    key: str


# ---------------------------------------------------------------------------
# Prompt builders (pure — unit-testable without any I/O)
# ---------------------------------------------------------------------------


def build_portrait_prompt(character: dict[str, Any]) -> str:
    """Portrait prompt from card fields: name + description + personality."""
    parts = [f"Character portrait of {character.get('name') or 'a fictional character'}."]
    description = (character.get("description") or "").strip()
    if description:
        parts.append(description)
    personality = (character.get("personality") or "").strip()
    if personality:
        parts.append(f"Personality: {personality}.")
    parts.append(
        "Head-and-shoulders fantasy character portrait, expressive, painterly, high detail, no text, no watermark."
    )
    return " ".join(parts)


def build_scene_prompt(messages: list[dict[str, Any]], character: dict[str, Any] | None = None) -> str:
    """Scene-illustration prompt summarising the last N chat messages."""
    lines: list[str] = []
    for m in messages:
        text = (m.get("text") or m.get("content") or "").strip()
        if not text:
            continue
        speaker = m.get("entity_name") or m.get("speaker_role") or m.get("role") or "narrator"
        lines.append(f"{speaker}: {text}")
    excerpt = "\n".join(lines)[-3000:]
    featuring = f" featuring {character['name']}" if character and character.get("name") else ""
    return (
        f"Cinematic scene illustration{featuring}, 16:9 composition, based on "
        f"this roleplay excerpt:\n{excerpt}\n"
        "Atmospheric, painterly, dramatic lighting, no text, no watermark."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _adapter() -> ImageProviderAdapter:
    postgres = get_postgres_client()
    adapter = await resolve_image_adapter(postgres)
    if adapter is None:
        raise HTTPException(status_code=400, detail=_NO_PROVIDER_DETAIL)
    return adapter


async def _generate(adapter: ImageProviderAdapter, prompt: str, aspect_ratio: str) -> bytes:
    try:
        return await adapter.generate_image(prompt, aspect_ratio=aspect_ratio)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image provider failed (retryable): {exc}")


def _load_scene_messages(body: SceneRequest) -> tuple[list[dict[str, Any]], str]:
    """Return (messages, storage-prefix) for either a play session or a
    light-RP conversation. Raises 404 when the source doesn't exist or is empty."""
    if body.session_id:
        rows = db_load_messages(body.session_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Session has no messages")
        messages = [
            {"speaker_role": r.get("role"), "entity_name": None, "text": r.get("content") or ""}
            for r in rows[-body.last_n :]
        ]
        return messages, f"session-{body.session_id}"

    doc = get_mongodb_client().get_collection("conversations").find_one({"conversation_id": body.conversation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found")
    turns = list(doc.get("turns") or [])[-body.last_n :]
    if not turns:
        raise HTTPException(status_code=404, detail="Conversation has no turns")
    return turns, f"conversation-{body.conversation_id}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/portrait", response_model=PortraitResponse)
async def generate_portrait(body: PortraitRequest) -> PortraitResponse:
    """Generate a portrait for a standalone character and set its avatar."""
    char = get_character(body.character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    adapter = await _adapter()
    png = await _generate(adapter, build_portrait_prompt(char), "1:1")

    key = f"portraits/{body.character_id}/{uuid4().hex}.png"
    minio = get_minio_client()
    await minio.upload(key, png, content_type="image/png")
    update_character(body.character_id, {"avatar_url": key})
    url = await minio.presigned_url(key, expires_in=3600)
    return PortraitResponse(avatar_url=url, key=key)


@router.post("/scene", response_model=SceneResponse)
async def generate_scene_image(body: SceneRequest) -> SceneResponse:
    """Generate a scene illustration from the last N messages of a chat."""
    if not body.conversation_id and not body.session_id:
        raise HTTPException(
            status_code=400,
            detail="Provide conversation_id (light RP) or session_id (play chat).",
        )

    messages, source = _load_scene_messages(body)
    adapter = await _adapter()
    png = await _generate(adapter, build_scene_prompt(messages), "16:9")

    key = f"scenes/{source}/{uuid4().hex}.png"
    minio = get_minio_client()
    await minio.upload(key, png, content_type="image/png")
    url = await minio.presigned_url(key, expires_in=3600)
    return SceneResponse(image_url=url, key=key)


@router.get("/avatar/{character_id}")
async def character_avatar(character_id: str) -> RedirectResponse:
    """Redirect to a fresh presigned URL for the character's avatar image."""
    char = get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    avatar = char.get("avatar_url") or ""
    if not avatar:
        raise HTTPException(status_code=404, detail="Character has no avatar")
    if avatar.startswith(("http://", "https://", "data:")):
        return RedirectResponse(avatar)
    url = await get_minio_client().presigned_url(avatar, expires_in=3600)
    return RedirectResponse(url)

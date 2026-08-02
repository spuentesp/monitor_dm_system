"""
Image generation router — portraits and scene illustrations.

Principle (spec §6): no standalone image tool; generate where content lives.
Provider config lives in the LLM registry (a ``llm_providers`` row with
``role='image'``); generated images are stored in MinIO and served through
short-lived presigned URLs. Character ``avatar_url`` stores the MinIO object
*key* — ``GET /avatar/{id}`` issues a fresh presigned redirect for ``<img>``
tags, so expiring URLs never get persisted.

Durability (Task 5): every successful generation persists exactly one
``GeneratedAsset`` record — after the MinIO upload succeeds — carrying the
final prompt, provider/model, and provenance (conversation/session scope,
source messages, canon fact IDs, identity version, reference IDs, MinIO key).
Provider or upload failures persist nothing; if metadata persistence fails
after upload, the stored object is deleted best-effort and the request fails
with HTTP 500 rather than returning an untracked success.

Prompts are assembled by ``monitor_data.llm.image_prompts`` from a canonical
visual context resolved through ``monitor_agents.image_context`` (read-only —
this router never writes Neo4j). Context assembly is best-effort: a read
failure falls back to card-based prompting instead of failing the request.

Approval workflow (Task 8): every generated asset is persisted with
``approval_status="pending"``. Generation never mutates the character avatar
— approving the asset via ``POST /api/image/assets/{id}/approve`` with
``use_as_avatar=true`` (image_assets.py) is the only avatar-mutation path.
The pre-approval-workflow ``auto_approve_legacy`` flag was removed here once
the frontend preview/approval flow landed.

New uploads use object keys ``assets/{asset_type}/{scope}/{uuid}.png``; older
``portraits/`` and ``scenes/`` keys remain valid (the avatar redirect serves
any stored key).

Trigger provenance (Task 9): both endpoints accept an optional ``trigger``
(``TriggerSource``, default ``user``) and ``source_turn_id`` so loop-suggestion
chips record what prompted the generation on the asset's provenance. Suggestions
themselves never auto-generate — they only reach this router via an explicit
user click.

Policy + budget (Task 10): before invoking the provider the router runs
``monitor_data.llm.image_policy.check_image_policy`` (provider_default or
lines_and_veils) and reserves a slot in the three configured budgets
(per-scene, per-conversation, per-actor-hour). A policy block surfaces as
HTTP 400 with the violated agreement; a budget block surfaces as HTTP 429
with ``scope``, ``used``, ``limit``, and retry guidance. Failed provider or
upload calls release their reserved slot so the budget reflects only
successful generations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from monitor_agents.image_context import CanonicalVisualContext, assemble_image_context
from monitor_data.db.minio import MinIOClient, get_minio_client
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.postgres import get_postgres_client
from monitor_data.llm.image_policy import (
    ImagePolicyDecision,
    check_image_policy,
)
from monitor_data.llm.image_prompts import (
    ImagePrompt,
    build_portrait_prompt,
    build_scene_prompt,
)
from monitor_data.llm.image_providers import (
    ImageGenerationInput,
    ImageProviderAdapter,
    ImageProviderError,
    dispatch_image_generation,
    load_reference_images,
    resolve_image_adapter,
    select_references,
)
from monitor_data.schemas.generated_assets import (
    ApprovalStatus,
    AssetType,
    GeneratedAsset,
    GeneratedAssetCreate,
    TriggerSource,
)
from monitor_data.tools.mongodb_tools.generated_assets import mongodb_create_generated_asset
from monitor_data.tools.mongodb_tools.image_settings import (
    mongodb_get_image_generation_settings,
)
from pydantic import BaseModel, Field

from monitor_ui.image_budget import (
    BudgetScope,
    release_budget,
    reserve_budget,
)

from .character_storage import get_character
from .chat_persistence import db_load_messages

log = structlog.get_logger()

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
    # Task 9: what triggered the generation (loop suggestion chips pass
    # "loop_suggestion"); recorded on the asset's provenance.
    trigger: TriggerSource = TriggerSource.USER
    # Provenance pointer back to the loop turn that suggested the image.
    source_turn_id: str | None = None


class PortraitResponse(BaseModel):
    avatar_url: str
    key: str
    asset_id: UUID
    approval_status: ApprovalStatus
    prompt_warnings: list[str] = Field(default_factory=list)


class SceneRequest(BaseModel):
    conversation_id: str | None = None
    session_id: str | None = None
    last_n: int = Field(default=12, ge=1, le=50)
    # Task 10: the character the player is "speaking as" in the scene. When
    # present, the actor-hour budget is reserved against this character in
    # addition to the scene + conversation budgets. Without it, only the
    # per-scene and per-conversation scopes are enforced.
    character_id: str | None = None
    # Task 9: trigger provenance — see PortraitRequest.
    trigger: TriggerSource = TriggerSource.USER
    source_turn_id: str | None = None


class SceneResponse(BaseModel):
    image_url: str
    key: str
    asset_id: UUID
    approval_status: ApprovalStatus
    prompt_warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scene source loading
# ---------------------------------------------------------------------------


@dataclass
class _SceneSource:
    """Messages plus provenance scope for a scene illustration request."""

    messages: list[dict[str, Any]]
    scope: str  # storage-prefix segment, e.g. "conversation-<id>" / "session-<id>"
    conversation_id: UUID | None = None
    universe_id: UUID | None = None
    story_id: UUID | None = None
    scene_id: UUID | None = None
    source_message_ids: list[str] = field(default_factory=list)
    # Active campaign agreements (lines = "must never appear", veils =
    # "fade-to-black"). Empty tuples mean "no agreements declared"; the
    # policy module then never invents restrictions. Populated from the
    # session's ``story_agreements`` for the session path; conversations
    # in the current schema do not store story_agreements so the tuple
    # stays empty there.
    agreements_lines: tuple[str, ...] = ()
    agreements_veils: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_uuid(value: Any) -> UUID | None:
    """Parse a UUID-ish value; None when absent or not a valid UUID."""
    if value is None or value == "":
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


async def _adapter() -> ImageProviderAdapter:
    postgres = get_postgres_client()
    try:
        adapter = await resolve_image_adapter(postgres)
    except ImageProviderError as exc:
        # A role='image' row exists but is unusable (e.g. saved without an
        # API key and no env fallback) — same actionable 400 as "no provider".
        raise HTTPException(
            status_code=400,
            detail=f"Image provider is misconfigured: {exc} Fix it under /config → LLM Providers.",
        )
    if adapter is None:
        raise HTTPException(status_code=400, detail=_NO_PROVIDER_DETAIL)
    return adapter


async def _resolve_context(
    *,
    universe_id: UUID | None,
    character_id: str | None = None,
    entity_id: UUID | None = None,
    conversation_id: UUID | None = None,
    scene_id: UUID | None = None,
) -> CanonicalVisualContext | None:
    """Best-effort canonical visual context.

    Returns None when no universe scope is known or when the read-only
    assembly fails — generation then falls back to card-based prompting
    rather than failing the whole request.
    """
    if universe_id is None:
        return None
    try:
        return await assemble_image_context(
            universe_id=universe_id,
            character_id=character_id,
            entity_ids=(entity_id,) if entity_id is not None else (),
            conversation_id=conversation_id,
            scene_id=scene_id,
        )
    except Exception as exc:
        log.warning(
            "image_gen.context_assembly_failed",
            error=str(exc),
            universe_id=str(universe_id),
        )
        return None


async def _generate(
    adapter: ImageProviderAdapter,
    prompt: ImagePrompt,
    aspect_ratio: str,
    reference_images: Sequence[Any] = (),
) -> bytes:
    try:
        return await dispatch_image_generation(
            adapter,
            ImageGenerationInput(
                prompt=prompt.positive,
                aspect_ratio=aspect_ratio,
                reference_images=tuple(reference_images),
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image provider failed (retryable): {exc}")


# Constants used by ``_select_and_load_references`` to size the per-request
# reference set. The total cap is intentionally small (4) because today's
# provider contracts don't yet consume references — see Task 3 — and the
# real-world image models under consideration accept at most a handful of
# inline images per request. Bumping these values later only requires a
# new test in ``test_image_gen.py``; nothing in the orchestrator hard-codes
# the numbers.
_MAX_REFERENCE_IMAGES = 4
_MAX_REFERENCE_IMAGES_PER_SUBJECT = 2
_MAX_REFERENCE_IMAGES_PER_PROVIDER = 4


async def _select_and_load_references(
    adapter: ImageProviderAdapter,
    context: CanonicalVisualContext | None,
    minio: MinIOClient,
    *,
    log_extras: dict[str, Any] | None = None,
) -> tuple[list[Any], list[str]]:
    """Build the per-request reference set + warnings.

    Returns ``(references, warnings)``. Today every shipped adapter reports
    ``supports_reference_images=False`` — references never load and the
    router records a clear "text-only fallback" warning so the preview UI
    can surface the active mode. When a future adapter flips the flag, the
    loader pulls bytes from MinIO in selection order and the router records
    a "reference conditioning active" warning instead. Either way the
    asset's ``reference_asset_ids`` provenance still records the IDs of
    every approved reference the orchestrator considered, regardless of
    whether the provider consumed the bytes.
    """
    log_extras = log_extras or {}
    if context is None or not context.reference_assets:
        return [], []
    eligible_count = len(context.reference_assets)
    if not adapter.capabilities().supports_reference_images:
        return [], [
            "text-only fallback: provider does not consume reference images; "
            f"dropped {eligible_count} approved reference(s) at the orchestrator."
        ]
    selected = select_references(
        context.reference_assets,
        max_total=_MAX_REFERENCE_IMAGES,
        max_per_subject=_MAX_REFERENCE_IMAGES_PER_SUBJECT,
        max_per_provider=_MAX_REFERENCE_IMAGES_PER_PROVIDER,
    )
    if not selected:
        return [], []
    references = await load_reference_images(minio, selected)
    dropped = eligible_count - len(selected)
    suffix = f"; dropped {dropped} beyond the per-request cap" if dropped else ""
    log.info(
        "image_gen.reference_conditioning_active",
        selected=len(selected),
        eligible=eligible_count,
        provider_id=adapter.capabilities().provider_id,
        **log_extras,
    )
    return references, [
        f"reference conditioning active: sent {len(selected)} of {eligible_count} approved "
        f"reference(s) to {adapter.capabilities().provider_id}{suffix}."
    ]


def _session_agreements_from_doc(session: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the lines/veils stored on a chat_sessions doc.

    Mirrors the contract of :func:`monitor_ui.routers.chat_loops._session_agreements`
    so the image router never has to import across router boundaries just
    to read the same field. Empty / malformed ``story_agreements`` yields
    empty tuples, which the policy module treats as "no rules declared".
    """
    raw = session.get("story_agreements")
    if not isinstance(raw, dict):
        return (), ()
    lines = tuple(
        str(item).strip() for item in (raw.get("lines") or []) if str(item).strip()
    )
    veils = tuple(
        str(item).strip() for item in (raw.get("veils") or []) if str(item).strip()
    )
    return lines, veils


def _load_scene_source(body: SceneRequest) -> _SceneSource:
    """Return messages + provenance scope for a play session or light-RP
    conversation. Raises 404 when the source doesn't exist or is empty."""
    if body.session_id:
        rows = db_load_messages(body.session_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Session has no messages")
        window = rows[-body.last_n :]
        messages = [
            {
                "id": r.get("id"),
                "speaker_role": r.get("role"),
                "entity_name": None,
                "text": r.get("content") or "",
            }
            for r in window
        ]
        session = get_mongodb_client().get_collection("chat_sessions").find_one({"id": body.session_id}) or {}
        agreements_lines, agreements_veils = _session_agreements_from_doc(session)
        return _SceneSource(
            messages=messages,
            scope=f"session-{body.session_id}",
            universe_id=_as_uuid(session.get("universe_id") or session.get("world_id")),
            story_id=_as_uuid(session.get("story_id")),
            scene_id=_as_uuid(session.get("scene_id")),
            source_message_ids=[str(r["id"]) for r in window if r.get("id")],
            agreements_lines=agreements_lines,
            agreements_veils=agreements_veils,
        )

    doc = get_mongodb_client().get_collection("conversations").find_one({"conversation_id": body.conversation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found")
    turns = list(doc.get("turns") or [])[-body.last_n :]
    if not turns:
        raise HTTPException(status_code=404, detail="Conversation has no turns")
    # Light-RP conversations in the current schema do not carry
    # story_agreements; we treat them as "no agreements declared" and the
    # policy module returns lines_and_veils_no_agreements (no inventions).
    return _SceneSource(
        messages=turns,
        scope=f"conversation-{body.conversation_id}",
        conversation_id=_as_uuid(body.conversation_id),
        universe_id=_as_uuid(doc.get("universe_id")),
        source_message_ids=[
            f"{body.conversation_id}:{t['turn_index']}" for t in turns if t.get("turn_index") is not None
        ],
    )


def _reference_uuids(prompt: ImagePrompt) -> list[UUID]:
    """Reference asset IDs from the prompt, parsed to UUIDs (unparseable dropped)."""
    return [uid for raw in prompt.reference_asset_ids if (uid := _as_uuid(raw)) is not None]


def _combined_warnings(prompt: ImagePrompt, context: CanonicalVisualContext | None) -> list[str]:
    warnings = [*prompt.warnings, *(context.warnings if context is not None else ())]
    return list(dict.fromkeys(warnings))


def _identity_provenance(context: CanonicalVisualContext | None) -> tuple[UUID | None, int | None]:
    """First identity version pointer (deterministic order), if any."""
    if context is None or not context.identity_versions:
        return None, None
    first = context.identity_versions[0]
    return first.identity_id, first.version


async def _upload(minio: MinIOClient, key: str, png: bytes) -> None:
    try:
        await minio.upload(key, png, content_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image storage failed (retryable): {exc}")


async def _persist_asset(minio: MinIOClient, params: GeneratedAssetCreate) -> GeneratedAsset:
    """Persist the asset record after upload.

    On failure the uploaded object is deleted best-effort and the request
    fails with HTTP 500 — an untracked image is never reported as success.
    """
    try:
        return mongodb_create_generated_asset(params)
    except Exception as exc:
        log.error(
            "image_gen.asset_persistence_failed",
            minio_key=params.minio_key,
            error=str(exc),
        )
        try:
            await minio.delete(params.minio_key)
        except Exception as cleanup_exc:
            log.warning(
                "image_gen.asset_cleanup_failed",
                minio_key=params.minio_key,
                error=str(cleanup_exc),
            )
        raise HTTPException(
            status_code=500,
            detail="Image was generated but its metadata could not be persisted; the stored object was cleaned up.",
        )


def _enforce_policy(
    *,
    prompt: str,
    settings: Any,
    agreements_lines: tuple[str, ...] | list[str],
    agreements_veils: tuple[str, ...] | list[str],
) -> ImagePolicyDecision:
    """Run the policy check and surface a 400 if the prompt is blocked.

    The :class:`ImageGenerationSettings` model uses
    ``Literal["provider_default", "lines_and_veils"]``; we map straight to
    :class:`ImageModerationMode` here so the data-layer module stays
    router-agnostic.
    """
    from monitor_data.llm.image_policy import ImageModerationMode

    mode = ImageModerationMode(settings.image_moderation_mode)
    decision = check_image_policy(
        prompt=prompt,
        mode=mode,
        agreements_lines=agreements_lines,
        agreements_veils=agreements_veils,
    )
    if not decision.allowed:
        log.info(
            "image_gen.policy_blocked",
            reason=decision.reason,
            violated=decision.violated_agreement,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "policy_blocked",
                "reason": decision.reason,
                "violated_agreement": decision.violated_agreement,
                "message": (
                    "Prompt violates an active campaign agreement. "
                    "Adjust the prompt or disable lines_and_veils under /config."
                ),
            },
        )
    return decision


def _enforce_budget(
    *,
    settings: Any,
    scope: BudgetScope,
    scope_key: str,
    actor_id: str | None,
) -> None:
    """Reserve a slot in the named budget; raise 429 if the cap is reached."""
    decision = reserve_budget(
        settings,
        scope=scope,
        scope_key=scope_key,
        actor_id=actor_id,
    )
    if not decision.allowed:
        log.info(
            "image_gen.budget_blocked",
            scope=decision.scope,
            used=decision.used,
            limit=decision.limit,
        )
        raise HTTPException(
            status_code=429,
            detail={
                "error": "budget_exceeded",
                "scope": decision.scope,
                "used": decision.used,
                "limit": decision.limit,
                "retry": decision.retry,
            },
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


async def _portrait_agreements(char: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve the active campaign agreements for a portrait.

    Portraits are anchored to a character card; the active campaign is
    the character's default universe. We look for a play session that
    references the character — if one is active and has
    ``story_agreements`` set, we honor those. When the character is not
    bound to a session (typical for character-sheet portrait work in
    light-RP / forge flows), there are no campaign agreements to apply
    and we fall back to the empty tuple. The policy module treats empty
    agreements in ``lines_and_veils`` mode as "no rules declared" rather
    than inventing restrictions, so this is safe.
    """
    char_id = char.get("id")
    if not char_id:
        return (), ()
    try:
        session = (
            get_mongodb_client()
            .get_collection("chat_sessions")
            .find_one(
                {"character_id": str(char_id)},
                sort=[("updated_at", -1)],
            )
        )
    except Exception as exc:
        log.warning("image_gen.portrait_session_lookup_failed", character_id=str(char_id), error=str(exc))
        return (), ()
    if not session:
        return (), ()
    return _session_agreements_from_doc(session)


@router.post("/portrait", response_model=PortraitResponse)
async def generate_portrait(body: PortraitRequest) -> PortraitResponse:
    """Generate a portrait and record it as a PENDING asset.

    The avatar is never mutated here — approving the asset with
    ``use_as_avatar=true`` (image_assets router) is the only avatar path.
    """
    char = get_character(body.character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    settings = mongodb_get_image_generation_settings()

    # Portrait has no scene/conversation scope on the request side itself —
    # the character is the actor, so the relevant budget is actor_hour.
    # The card-level policy has no agreements (provider policy only).
    settings_lines, settings_veils = await _portrait_agreements(char)

    adapter = await _adapter()
    capabilities = adapter.capabilities()

    universe_id = _as_uuid(char.get("default_universe_id") or char.get("source_universe_id"))
    entity_id = _as_uuid(char.get("entity_id"))
    context = await _resolve_context(
        universe_id=universe_id,
        character_id=body.character_id,
        entity_id=entity_id,
    )
    prompt = build_portrait_prompt(char, context)

    # Policy before any expensive work.
    _enforce_policy(
        prompt=prompt.positive,
        settings=settings,
        agreements_lines=settings_lines,
        agreements_veils=settings_veils,
    )

    _enforce_budget(
        settings=settings,
        scope="actor_hour",
        scope_key=body.character_id,
        actor_id=body.character_id,
    )

    minio = get_minio_client()
    references, reference_warnings = await _select_and_load_references(
        adapter,
        context,
        minio,
        log_extras={"endpoint": "portrait", "character_id": body.character_id},
    )

    try:
        png = await _generate(adapter, prompt, "1:1", reference_images=references)
    except Exception:
        release_budget(scope="actor_hour", scope_key=body.character_id, actor_id=body.character_id)
        raise

    key = f"assets/portrait/character-{body.character_id}/{uuid4().hex}.png"
    try:
        await _upload(minio, key, png)
    except Exception:
        release_budget(scope="actor_hour", scope_key=body.character_id, actor_id=body.character_id)
        raise

    warnings = _combined_warnings(prompt, context)
    warnings.extend(reference_warnings)
    identity_id, identity_version = _identity_provenance(context)
    try:
        asset = await _persist_asset(
            minio,
            GeneratedAssetCreate(
                asset_type=AssetType.PORTRAIT,
                minio_key=key,
                byte_size=len(png),
                character_id=body.character_id,
                entity_id=entity_id,
                universe_id=universe_id,
                canon_fact_ids=list(context.source_fact_ids) if context is not None else [],
                visual_identity_id=identity_id,
                visual_identity_version=identity_version,
                prompt=prompt.positive,
                negative_prompt=prompt.negative or None,
                prompt_warnings=warnings,
                reference_asset_ids=_reference_uuids(prompt),
                provider_id=capabilities.provider_id,
                provider_model=capabilities.model,
                provider_capabilities=capabilities.to_dict(),
                trigger=body.trigger,
                source_message_ids=[body.source_turn_id] if body.source_turn_id else [],
                approval_status=ApprovalStatus.PENDING,
            ),
        )
    except Exception:
        release_budget(scope="actor_hour", scope_key=body.character_id, actor_id=body.character_id)
        raise

    url = await minio.presigned_url(key, expires_in=3600)
    return PortraitResponse(
        avatar_url=url,
        key=key,
        asset_id=asset.asset_id,
        approval_status=asset.approval_status,
        prompt_warnings=warnings,
    )


@router.post("/scene", response_model=SceneResponse)
async def generate_scene_image(body: SceneRequest) -> SceneResponse:
    """Generate a scene illustration from the last N messages of a chat."""
    if not body.conversation_id and not body.session_id:
        raise HTTPException(
            status_code=400,
            detail="Provide conversation_id (light RP) or session_id (play chat).",
        )
    if body.conversation_id and body.session_id:
        raise HTTPException(
            status_code=400,
            detail="Provide either conversation_id or session_id, not both.",
        )

    source = _load_scene_source(body)
    settings = mongodb_get_image_generation_settings()

    # Scene budgets cover scene + conversation + actor-hour. Each scope
    # reserves its own slot; on any failure we release them all.
    actor_id = body.character_id
    # Scene budget: only reserve when we have a real scene id. Without
    # one we don't know the scene scope, so we skip the reserve rather
    # than risk a fallback key that collides with the conversation
    # counter (Finding 4 — was: scene_scope_key = source.scope, which
    # was the same string the conversation budget used).
    if source.scene_id is not None:
        scene_scope_key = str(source.scene_id)
    else:
        scene_scope_key = None
    conversation_scope_key = (
        str(source.conversation_id) if source.conversation_id else source.scope
    )
    actor_hour_scope_key = body.character_id

    reserved: list[tuple[BudgetScope, str, str | None]] = []
    scopes_to_reserve: list[tuple[BudgetScope, str, str | None]] = []
    if scene_scope_key is not None:
        scopes_to_reserve.append(("scene", scene_scope_key, actor_id))
    scopes_to_reserve.append(("conversation", conversation_scope_key, actor_id))
    if actor_hour_scope_key:
        scopes_to_reserve.append(("actor_hour", actor_hour_scope_key, actor_id))

    for scope, scope_key, aid in scopes_to_reserve:
        if scope == "actor_hour" and not aid:
            continue
        decision = reserve_budget(
            settings,
            scope=scope,
            scope_key=scope_key,
            actor_id=aid,
        )
        if not decision.allowed:
            for r_scope, r_key, r_aid in reserved:
                release_budget(scope=r_scope, scope_key=r_key, actor_id=r_aid)
            log.info(
                "image_gen.budget_blocked",
                scope=decision.scope,
                used=decision.used,
                limit=decision.limit,
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "budget_exceeded",
                    "scope": decision.scope,
                    "used": decision.used,
                    "limit": decision.limit,
                    "retry": decision.retry,
                },
            )
        reserved.append((scope, scope_key, aid))

    def _release_all() -> None:
        for r_scope, r_key, r_aid in reserved:
            release_budget(scope=r_scope, scope_key=r_key, actor_id=r_aid)

    adapter = await _adapter()
    capabilities = adapter.capabilities()

    context = await _resolve_context(
        universe_id=source.universe_id,
        conversation_id=source.conversation_id,
        scene_id=source.scene_id,
    )
    prompt = build_scene_prompt(source.messages, context)

    # Policy check before the provider call. The active session's
    # story_agreements (lines/veils) are the source of truth here —
    # without them the lines_and_veils mode silently never matches
    # anything (Finding 1 — was hardcoded to ()/()).
    _enforce_policy(
        prompt=prompt.positive,
        settings=settings,
        agreements_lines=source.agreements_lines,
        agreements_veils=source.agreements_veils,
    )

    minio = get_minio_client()
    references, reference_warnings = await _select_and_load_references(
        adapter,
        context,
        minio,
        log_extras={"endpoint": "scene", "scope": source.scope},
    )

    try:
        png = await _generate(adapter, prompt, "16:9", reference_images=references)
    except Exception:
        _release_all()
        raise

    key = f"assets/scene/{source.scope}/{uuid4().hex}.png"
    try:
        await _upload(minio, key, png)
    except Exception:
        _release_all()
        raise

    warnings = _combined_warnings(prompt, context)
    warnings.extend(reference_warnings)
    identity_id, identity_version = _identity_provenance(context)
    try:
        asset = await _persist_asset(
            minio,
            GeneratedAssetCreate(
                asset_type=AssetType.SCENE,
                minio_key=key,
                byte_size=len(png),
                universe_id=source.universe_id,
                story_id=source.story_id,
                scene_id=source.scene_id,
                conversation_id=source.conversation_id,
                source_message_ids=[
                    *source.source_message_ids,
                    *([body.source_turn_id] if body.source_turn_id else []),
                ],
                canon_fact_ids=list(context.source_fact_ids) if context is not None else [],
                visual_identity_id=identity_id,
                visual_identity_version=identity_version,
                prompt=prompt.positive,
                negative_prompt=prompt.negative or None,
                prompt_warnings=warnings,
                reference_asset_ids=_reference_uuids(prompt),
                provider_id=capabilities.provider_id,
                provider_model=capabilities.model,
                provider_capabilities=capabilities.to_dict(),
                trigger=body.trigger,
                approval_status=ApprovalStatus.PENDING,
            ),
        )
    except Exception:
        _release_all()
        raise

    url = await minio.presigned_url(key, expires_in=3600)
    return SceneResponse(
        image_url=url,
        key=key,
        asset_id=asset.asset_id,
        approval_status=asset.approval_status,
        prompt_warnings=warnings,
    )


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

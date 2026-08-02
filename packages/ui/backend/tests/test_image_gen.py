"""Tests for the image generation router (provider + storage fully mocked).

Task 5: every successful portrait/scene generation persists exactly one
GeneratedAsset record with durable provenance; failures persist nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from monitor_agents.image_context import (
    CanonicalVisualContext,
    IdentityVersion,
    ReferenceAsset,
    VisualFact,
)
from monitor_data.llm.image_providers import ImageCapabilities, ImageProviderError
from monitor_data.schemas.generated_assets import (
    AssetType,
    GeneratedAsset,
    GeneratedAssetCreate,
    ReferenceStatus,
    TriggerSource,
)

import monitor_ui.routers.image_gen as image_gen
from monitor_ui.routers.image_gen import router

app = FastAPI()
app.include_router(router, prefix="/api/image")
client = TestClient(app)

CHAR = {
    "id": "c-1",
    "name": "Wisp",
    "description": "A fox-spirit guide with ember eyes.",
    "personality": "playful, evasive",
    "gm_notes": "",
    "avatar_url": None,
    "entity_id": None,
    "default_universe_id": None,
    "source_universe_id": None,
}

PNG = b"\x89PNG-fake"

UNIVERSE_ID = uuid4()
ENTITY_ID = uuid4()
FACT_ID = uuid4()
IDENTITY_ID = uuid4()
REFERENCE_ID = uuid4()
CONVERSATION_ID = uuid4()
STORY_ID = uuid4()
SCENE_ID = uuid4()


class _FakeAdapter:
    """Minimal ImageProviderAdapter: capabilities + structured generation."""

    def __init__(self, *, fail: bool = False):
        self.calls: list[dict] = []
        self.fail = fail

    def capabilities(self) -> ImageCapabilities:
        return ImageCapabilities(
            provider_id="fake-provider",
            model="fake-image-1",
            supports_reference_images=False,
            supported_aspect_ratios=frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"}),
        )

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        if self.fail:
            raise RuntimeError("rate limited")
        self.calls.append({"prompt": prompt, "aspect_ratio": aspect_ratio})
        return PNG

    async def generate_image_structured(self, input) -> bytes:
        if self.fail:
            raise RuntimeError("rate limited")
        self.calls.append(
            {
                "prompt": input.prompt,
                "aspect_ratio": input.aspect_ratio,
                "reference_images": list(input.reference_images),
            }
        )
        return PNG


def _fake_create_asset(params: GeneratedAssetCreate) -> GeneratedAsset:
    """Stand-in for mongodb_create_generated_asset (no Mongo needed)."""
    now = datetime.now(UTC)
    return GeneratedAsset(
        asset_id=uuid4(),
        approved_by=None,
        approved_at=None,
        created_at=now,
        updated_at=now,
        **params.model_dump(),
    )


@pytest.fixture
def fake_adapter():
    return _FakeAdapter()


@pytest.fixture
def mock_storage():
    minio = AsyncMock()
    minio.presigned_url.return_value = "https://minio.example.com/presigned/abc"
    with (
        patch.object(image_gen, "get_minio_client", return_value=minio),
        patch.object(image_gen, "get_postgres_client", return_value=AsyncMock()),
    ):
        yield minio


@pytest.fixture
def mock_create_asset():
    with patch.object(image_gen, "mongodb_create_generated_asset") as create:
        create.side_effect = _fake_create_asset
        yield create


@pytest.fixture
def mock_context():
    """Default: no canonical context available (card-fallback prompting)."""
    with patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)) as asm:
        yield asm


@pytest.fixture
def mock_settings():
    """Default: permissive settings — no budget enforcement, provider policy only.

    The Task 10 router calls ``mongodb_get_image_generation_settings``
    every request to know the budget caps and policy mode. Existing
    tests in this file were written before that hook existed; we mock
    it here so the behavioral assertions (provider mock, persistence,
    provenance) keep working without env/Mongo setup.
    """
    from monitor_data.schemas.image_settings import ImageGenerationSettings

    settings = ImageGenerationSettings(
        image_moderation_mode="provider_default",
        image_max_per_scene=0,
        image_max_per_conversation=0,
        image_max_per_actor_hour=0,
        image_suggestions_enabled=True,
    )
    with patch.object(image_gen, "mongodb_get_image_generation_settings", return_value=settings):
        yield settings


@pytest.fixture
def lines_and_veils_settings():
    """Strict settings — lines_and_veils mode. Used by the policy integration
    tests in this file to assert that the router actually consults the
    active session's story_agreements before generating."""
    from monitor_data.schemas.image_settings import ImageGenerationSettings

    settings = ImageGenerationSettings(
        image_moderation_mode="lines_and_veils",
        image_max_per_scene=0,
        image_max_per_conversation=0,
        image_max_per_actor_hour=0,
        image_suggestions_enabled=True,
    )
    with patch.object(image_gen, "mongodb_get_image_generation_settings", return_value=settings):
        yield settings


def _canon_context() -> CanonicalVisualContext:
    return CanonicalVisualContext(
        universe_id=UNIVERSE_ID,
        facts=(VisualFact(fact_id=FACT_ID, statement="Wisp has ember eyes.", entity_id=ENTITY_ID),),
        reference_assets=(
            ReferenceAsset(
                asset_id=REFERENCE_ID,
                reference_status=ReferenceStatus.PRIMARY,
                minio_key="assets/portrait/character-c-1/old.png",
            ),
        ),
        identity_versions=(IdentityVersion(identity_id=IDENTITY_ID, version=3),),
        warnings=("No approved visual identity found for character c-1; card defaults will be used.",),
    )


def _created_params(create_mock) -> GeneratedAssetCreate:
    create_mock.assert_called_once()
    params = create_mock.call_args[0][0]
    assert isinstance(params, GeneratedAssetCreate)
    return params


# ---------------------------------------------------------------------------
# Portrait endpoint
# ---------------------------------------------------------------------------


def test_portrait_happy_path_persists_one_pending_asset(fake_adapter, mock_storage, mock_create_asset, mock_context, mock_settings):
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    body = res.json()
    # Existing fields unchanged
    assert body["avatar_url"] == "https://minio.example.com/presigned/abc"
    assert body["key"].startswith("assets/portrait/character-c-1/")
    # Task 8: generation always produces a PENDING asset; the avatar is only
    # changed by approving the asset with use_as_avatar (image_assets router).
    assert UUID(body["asset_id"])  # parses as a UUID
    assert body["approval_status"] == "pending"
    assert body["prompt_warnings"] == []

    mock_storage.upload.assert_awaited_once()
    assert mock_storage.upload.call_args[0][0] == body["key"]
    assert mock_storage.upload.call_args[0][1] == PNG
    # delete only runs for cleanup on metadata failure
    mock_storage.delete.assert_not_awaited()

    # Exactly one durable asset, persisted with provenance
    params = _created_params(mock_create_asset)
    assert params.asset_type == AssetType.PORTRAIT
    assert params.approval_status == "pending"
    assert params.minio_key == body["key"]
    assert params.byte_size == len(PNG)
    assert params.content_type == "image/png"
    assert params.character_id == "c-1"
    assert params.prompt == fake_adapter.calls[0]["prompt"]
    assert "fox-spirit guide" in params.prompt  # card fallback still drives the prompt
    assert params.negative_prompt
    assert params.provider_id == "fake-provider"
    assert params.provider_model == "fake-image-1"
    assert params.provider_capabilities["provider_id"] == "fake-provider"


def test_portrait_endpoint_has_no_avatar_mutation_path():
    """Task 8 removed the legacy auto-approve/avatar-mutation path: the router
    no longer imports update_character. Approving with use_as_avatar (covered
    in test_image_assets.py) is the only avatar-mutation path."""
    assert not hasattr(image_gen, "update_character")


def test_portrait_records_canon_provenance(fake_adapter, mock_storage, mock_create_asset, mock_settings):
    """Fact IDs, identity version, reference IDs and scope come from the context."""
    char = {
        **CHAR,
        "entity_id": str(ENTITY_ID),
        "default_universe_id": str(UNIVERSE_ID),
    }
    with (
        patch.object(image_gen, "get_character", return_value=char),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=_canon_context())) as asm,
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    asm.assert_awaited_once()
    kwargs = asm.call_args.kwargs
    assert kwargs["universe_id"] == UNIVERSE_ID
    assert kwargs["character_id"] == "c-1"
    assert kwargs["entity_ids"] == (ENTITY_ID,)

    params = _created_params(mock_create_asset)
    assert params.universe_id == UNIVERSE_ID
    assert params.entity_id == ENTITY_ID
    assert params.canon_fact_ids == [FACT_ID]
    assert params.visual_identity_id == IDENTITY_ID
    assert params.visual_identity_version == 3
    assert params.reference_asset_ids == [REFERENCE_ID]
    assert "ember eyes" in params.prompt  # canon fact reached the provider prompt

    body = res.json()
    assert body["prompt_warnings"] == [
        "No approved visual identity found for character c-1; card defaults will be used.",
        "text-only fallback: provider does not consume reference images; dropped 1 approved reference(s) at the orchestrator.",
    ]


def test_portrait_succeeds_when_context_assembly_fails(fake_adapter, mock_storage, mock_create_asset, mock_settings):
    """Canonical context is best-effort: a read failure must not block generation."""
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(
            image_gen,
            "assemble_image_context",
            new=AsyncMock(side_effect=RuntimeError("neo4j down")),
        ),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    params = _created_params(mock_create_asset)
    assert params.canon_fact_ids == []
    assert params.visual_identity_id is None
    assert params.reference_asset_ids == []


def test_portrait_400_when_no_image_provider(mock_storage, mock_create_asset, mock_context, mock_settings):
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 400
    assert "/config" in res.json()["detail"]
    mock_create_asset.assert_not_called()


def test_portrait_400_when_image_row_is_keyless(mock_storage, mock_create_asset, mock_context, mock_settings):
    """A role='image' row without an API key (and no env fallback) makes
    resolve_image_adapter raise ImageProviderError — must surface as 400,
    not an unhandled 500."""
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(
            image_gen,
            "resolve_image_adapter",
            new=AsyncMock(side_effect=ImageProviderError("No API key configured for image provider 'img-a'")),
        ),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 400
    assert "/config" in res.json()["detail"]
    mock_create_asset.assert_not_called()


def test_portrait_404_for_unknown_character(mock_storage, mock_create_asset, mock_context, mock_settings):
    with patch.object(image_gen, "get_character", return_value=None):
        res = client.post("/api/image/portrait", json={"character_id": "nope"})
    assert res.status_code == 404
    mock_create_asset.assert_not_called()


def test_portrait_502_on_provider_failure_persists_nothing(mock_storage, mock_create_asset, mock_context, mock_settings):
    failing = _FakeAdapter(fail=True)
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=failing)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 502
    mock_create_asset.assert_not_called()
    mock_storage.upload.assert_not_awaited()


def test_portrait_502_on_upload_failure_leaves_no_dangling_asset(
    fake_adapter, mock_storage, mock_create_asset, mock_context, mock_settings
):
    mock_storage.upload.side_effect = RuntimeError("storage backend down")
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 502
    mock_create_asset.assert_not_called()


def test_portrait_500_and_minio_cleanup_when_metadata_persistence_fails(
    fake_adapter, mock_storage, mock_create_asset, mock_context, mock_settings
):
    """Mongo failure after upload: best-effort MinIO cleanup + HTTP 500."""
    mock_create_asset.side_effect = RuntimeError("mongo unavailable")
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 500
    uploaded_key = mock_storage.upload.call_args[0][0]
    mock_storage.delete.assert_awaited_once_with(uploaded_key)


# ---------------------------------------------------------------------------
# Scene endpoint
# ---------------------------------------------------------------------------


def _mongo_with_conversation(doc):
    mongo = MagicMock()  # pymongo calls are synchronous
    mongo.get_collection.return_value.find_one.return_value = doc
    return mongo


def test_scene_from_conversation_turns(fake_adapter, mock_storage, mock_create_asset, mock_settings):
    turns = [
        {"turn_index": 0, "speaker_role": "player", "entity_name": None, "text": "I light the lantern."},
        {"turn_index": 1, "speaker_role": "npc", "entity_name": "Wisp", "text": "The dark notices."},
    ]
    doc = {
        "conversation_id": str(CONVERSATION_ID),
        "universe_id": str(UNIVERSE_ID),
        "turns": turns,
    }
    with (
        patch.object(image_gen, "get_mongodb_client", return_value=_mongo_with_conversation(doc)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)) as asm,
    ):
        res = client.post("/api/image/scene", json={"conversation_id": str(CONVERSATION_ID), "last_n": 12})

    assert res.status_code == 200
    body = res.json()
    assert body["key"].startswith(f"assets/scene/conversation-{CONVERSATION_ID}/")
    assert UUID(body["asset_id"])
    assert body["approval_status"] == "pending"  # Task 8: no more auto-approve
    assert body["prompt_warnings"] == []
    assert fake_adapter.calls[0]["aspect_ratio"] == "16:9"
    assert "I light the lantern." in fake_adapter.calls[0]["prompt"]

    # Canonical context resolved with conversation scope
    asm.assert_awaited_once()
    kwargs = asm.call_args.kwargs
    assert kwargs["universe_id"] == UNIVERSE_ID
    assert kwargs["conversation_id"] == CONVERSATION_ID

    params = _created_params(mock_create_asset)
    assert params.asset_type == AssetType.SCENE
    assert params.conversation_id == CONVERSATION_ID
    assert params.universe_id == UNIVERSE_ID
    assert params.source_message_ids == [
        f"{CONVERSATION_ID}:0",
        f"{CONVERSATION_ID}:1",
    ]
    assert params.minio_key == body["key"]


def test_scene_from_play_session(fake_adapter, mock_storage, mock_create_asset, mock_settings):
    rows = [
        {"id": "m-1", "role": "player", "content": "I open the gate.", "timestamp": "t1"},
        {"id": "m-2", "role": "gm", "content": "The courtyard is flooded.", "timestamp": "t2"},
    ]
    session_doc = {
        "id": "s-1",
        "universe_id": str(UNIVERSE_ID),
        "story_id": str(STORY_ID),
        "scene_id": str(SCENE_ID),
    }
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = session_doc
    with (
        patch.object(image_gen, "db_load_messages", return_value=rows),
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)) as asm,
    ):
        res = client.post("/api/image/scene", json={"session_id": "s-1", "last_n": 12})

    assert res.status_code == 200
    body = res.json()
    assert body["key"].startswith("assets/scene/session-s-1/")
    assert "courtyard is flooded" in fake_adapter.calls[0]["prompt"]

    kwargs = asm.call_args.kwargs
    assert kwargs["universe_id"] == UNIVERSE_ID
    assert kwargs["scene_id"] == SCENE_ID

    params = _created_params(mock_create_asset)
    assert params.asset_type == AssetType.SCENE
    assert params.universe_id == UNIVERSE_ID
    assert params.story_id == STORY_ID
    assert params.scene_id == SCENE_ID
    assert params.source_message_ids == ["m-1", "m-2"]


def test_scene_400_without_any_source(mock_storage, mock_create_asset, mock_context, mock_settings):
    res = client.post("/api/image/scene", json={"last_n": 12})
    assert res.status_code == 400
    mock_create_asset.assert_not_called()


def test_scene_400_with_both_sources(mock_storage, mock_create_asset, mock_context, mock_settings):
    res = client.post("/api/image/scene", json={"conversation_id": "c-1", "session_id": "s-1"})
    assert res.status_code == 400
    assert "not both" in res.json()["detail"]
    mock_create_asset.assert_not_called()


def test_scene_404_for_unknown_conversation(fake_adapter, mock_storage, mock_create_asset, mock_context, mock_settings):
    mongo = _mongo_with_conversation(None)
    with (
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/scene", json={"conversation_id": "ghost", "last_n": 12})
    assert res.status_code == 404
    mock_create_asset.assert_not_called()


def test_scene_502_on_provider_failure_persists_nothing(mock_storage, mock_create_asset, mock_context, mock_settings):
    doc = {
        "conversation_id": str(CONVERSATION_ID),
        "turns": [{"turn_index": 0, "speaker_role": "player", "text": "Hello."}],
    }
    failing = _FakeAdapter(fail=True)
    with (
        patch.object(image_gen, "get_mongodb_client", return_value=_mongo_with_conversation(doc)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=failing)),
    ):
        res = client.post("/api/image/scene", json={"conversation_id": str(CONVERSATION_ID)})
    assert res.status_code == 502
    mock_create_asset.assert_not_called()
    mock_storage.upload.assert_not_awaited()


# ---------------------------------------------------------------------------
# Avatar redirect — old `portraits/` keys must keep working
# ---------------------------------------------------------------------------


def test_avatar_redirects_to_presigned_url_for_legacy_key(mock_storage):
    with patch.object(image_gen, "get_character", return_value={**CHAR, "avatar_url": "portraits/c-1/x.png"}):
        res = client.get("/api/image/avatar/c-1", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"] == "https://minio.example.com/presigned/abc"
    mock_storage.presigned_url.assert_awaited_with("portraits/c-1/x.png", expires_in=3600)


def test_avatar_redirects_to_presigned_url_for_new_key(mock_storage):
    key = "assets/portrait/character-c-1/abc.png"
    with patch.object(image_gen, "get_character", return_value={**CHAR, "avatar_url": key}):
        res = client.get("/api/image/avatar/c-1", follow_redirects=False)
    assert res.status_code in (302, 307)
    mock_storage.presigned_url.assert_awaited_with(key, expires_in=3600)


def test_avatar_404_without_avatar(mock_storage):
    with patch.object(image_gen, "get_character", return_value=dict(CHAR)):
        res = client.get("/api/image/avatar/c-1")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Task 9: trigger + source_turn_id provenance (loop suggestions)
# ---------------------------------------------------------------------------
# Loop-suggestion chips call the same endpoints with trigger="loop_suggestion"
# and the suggestion's source_turn_id; both are recorded on the asset's
# provenance. Existing callers omit them and default to trigger="user".


def _run_play_session_scene(fake_adapter, mock_storage, mock_create_asset, payload: dict):
    rows = [
        {"id": "m-1", "role": "player", "content": "I open the gate.", "timestamp": "t1"},
        {"id": "m-2", "role": "gm", "content": "The courtyard is flooded.", "timestamp": "t2"},
    ]
    session_doc = {
        "id": "s-1",
        "universe_id": str(UNIVERSE_ID),
        "story_id": str(STORY_ID),
        "scene_id": str(SCENE_ID),
    }
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = session_doc
    with (
        patch.object(image_gen, "db_load_messages", return_value=rows),
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        return client.post("/api/image/scene", json=payload)


def test_portrait_trigger_defaults_to_user(fake_adapter, mock_storage, mock_create_asset, mock_context, mock_settings):
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    params = _created_params(mock_create_asset)
    assert params.trigger == TriggerSource.USER
    assert params.source_message_ids == []


def test_portrait_records_loop_suggestion_trigger_and_turn_provenance(
    fake_adapter, mock_storage, mock_create_asset, mock_context, mock_settings
):
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post(
            "/api/image/portrait",
            json={"character_id": "c-1", "trigger": "loop_suggestion", "source_turn_id": "turn-xyz"},
        )

    assert res.status_code == 200
    params = _created_params(mock_create_asset)
    assert params.trigger == TriggerSource.LOOP_SUGGESTION
    assert params.source_message_ids == ["turn-xyz"]


def test_portrait_422_on_unknown_trigger(mock_storage, mock_create_asset, mock_context, mock_settings):
    res = client.post("/api/image/portrait", json={"character_id": "c-1", "trigger": "ghost"})
    assert res.status_code == 422
    mock_create_asset.assert_not_called()


def test_scene_trigger_defaults_to_user(fake_adapter, mock_storage, mock_create_asset, mock_settings):
    res = _run_play_session_scene(fake_adapter, mock_storage, mock_create_asset, {"session_id": "s-1"})

    assert res.status_code == 200
    params = _created_params(mock_create_asset)
    assert params.trigger == TriggerSource.USER
    assert params.source_message_ids == ["m-1", "m-2"]


def test_scene_records_loop_suggestion_trigger_and_turn_provenance(fake_adapter, mock_storage, mock_create_asset, mock_settings):
    res = _run_play_session_scene(
        fake_adapter,
        mock_storage,
        mock_create_asset,
        {"session_id": "s-1", "trigger": "loop_suggestion", "source_turn_id": "turn-xyz"},
    )

    assert res.status_code == 200
    params = _created_params(mock_create_asset)
    assert params.trigger == TriggerSource.LOOP_SUGGESTION
    # The suggestion's source turn rides alongside the window's message ids.
    assert params.source_message_ids == ["m-1", "m-2", "turn-xyz"]


# ---------------------------------------------------------------------------
# Review fix round 1: scene policy must consult session story_agreements.
# The Task 10 router previously hardcoded ()/() for agreements, so
# lines_and_veils mode silently never matched anything. These tests pin
# the corrected behaviour: an active veil blocks a matching prompt;
# a clean prompt passes; mode=provider_default still passes through.
# ---------------------------------------------------------------------------


def _play_session_with_agreements(agreements: dict | None) -> tuple[list[dict], dict]:
    """Build a session doc + messages with the given story_agreements payload."""
    rows = [
        {
            "id": "m-1",
            "role": "player",
            "content": "I open the gate and witness a quiet dismemberment in the courtyard.",
            "timestamp": "t1",
        },
        {"id": "m-2", "role": "gm", "content": "The courtyard goes still.", "timestamp": "t2"},
    ]
    session_doc = {
        "id": "s-agree",
        "universe_id": str(UNIVERSE_ID),
        "story_id": str(STORY_ID),
        "scene_id": str(SCENE_ID),
    }
    if agreements is not None:
        session_doc["story_agreements"] = agreements
    return rows, session_doc


def test_scene_blocks_on_active_veil_from_session(
    fake_adapter, mock_storage, mock_create_asset, lines_and_veils_settings
) -> None:
    """An active veil stored on the session must block a matching prompt.

    Without the fix, the router hardcoded empty agreements and the
    policy check returned 'allowed=True' regardless of the session's
    story_agreements. With the fix, the veils stored on the session are
    read by the router and passed into the policy module.
    """
    rows, session_doc = _play_session_with_agreements(
        {"lines": [], "veils": ["dismemberment"], "confirmed": True}
    )
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = session_doc
    with (
        patch.object(image_gen, "db_load_messages", return_value=rows),
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/scene", json={"session_id": "s-agree", "last_n": 12})

    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["error"] == "policy_blocked"
    assert detail["violated_agreement"] == "dismemberment"
    # The provider was never reached.
    fake_adapter.calls == []
    mock_create_asset.assert_not_called()


def test_scene_blocks_on_active_line_from_session(
    fake_adapter, mock_storage, mock_create_asset, lines_and_veils_settings
) -> None:
    """An active line stored on the session blocks a matching prompt."""
    rows, session_doc = _play_session_with_agreements(
        {"lines": ["dismemberment"], "veils": [], "confirmed": True}
    )
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = session_doc
    with (
        patch.object(image_gen, "db_load_messages", return_value=rows),
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/scene", json={"session_id": "s-agree", "last_n": 12})

    assert res.status_code == 400
    assert res.json()["detail"]["violated_agreement"] == "dismemberment"
    mock_create_asset.assert_not_called()


def test_scene_passes_clean_prompt_with_active_veils(
    fake_adapter, mock_storage, mock_create_asset, lines_and_veils_settings
) -> None:
    """lines_and_veils mode with active veils must not block a clean prompt."""
    rows, session_doc = _play_session_with_agreements(
        {"lines": [], "veils": ["torture"], "confirmed": True}
    )
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = session_doc
    with (
        patch.object(image_gen, "db_load_messages", return_value=rows),
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/scene", json={"session_id": "s-agree", "last_n": 12})

    assert res.status_code == 200
    mock_create_asset.assert_called_once()


def test_scene_with_no_session_agreements_in_lines_and_veils_mode_does_not_invent_rules(
    fake_adapter, mock_storage, mock_create_asset, lines_and_veils_settings
) -> None:
    """lines_and_veils + no declared agreements = pass-through (no inventions)."""
    rows, session_doc = _play_session_with_agreements(None)
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = session_doc
    with (
        patch.object(image_gen, "db_load_messages", return_value=rows),
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/scene", json={"session_id": "s-agree", "last_n": 12})

    assert res.status_code == 200
    mock_create_asset.assert_called_once()


# ---------------------------------------------------------------------------
# Task 11: canon-anchored scene composition — provenance + reference wiring
# ---------------------------------------------------------------------------


REFERENCE_2_ID = uuid4()


def _canon_scene_context() -> CanonicalVisualContext:
    """A context with one canonical identity, two reference assets, and the
    three provenance fields Task 11 wants pinned on the asset record
    (``reference_asset_ids``, ``visual_identity_id``/``version``,
    ``canon_fact_ids``)."""
    return CanonicalVisualContext(
        universe_id=UNIVERSE_ID,
        facts=(VisualFact(fact_id=FACT_ID, statement="Wisp has ember eyes.", entity_id=ENTITY_ID),),
        reference_assets=(
            ReferenceAsset(
                asset_id=REFERENCE_ID,
                reference_status=ReferenceStatus.PRIMARY,
                minio_key="assets/portrait/character-c-1/primary.png",
            ),
            ReferenceAsset(
                asset_id=REFERENCE_2_ID,
                reference_status=ReferenceStatus.SUPPORTING,
                minio_key="assets/scene/conversation-conv-1/supporting.png",
            ),
        ),
        identity_versions=(
            IdentityVersion(identity_id=IDENTITY_ID, version=4),
        ),
        warnings=("No approved visual identity found for character c-1; card defaults will be used.",),
    )


def test_portrait_records_full_provenance_with_text_only_fallback(
    fake_adapter, mock_storage, mock_create_asset, mock_settings
):
    """Pin every provenance field the brief asks for: ``reference_asset_ids``
    (in selection order), ``visual_identity_id`` + ``visual_identity_version``
    (single-valued provenance pointer), and ``canon_fact_ids`` (sorted by
    fact_id). The current adapter reports ``supports_reference_images=False``,
    so the response includes the "text-only fallback" warning.
    """
    char = {**CHAR, "entity_id": str(ENTITY_ID), "default_universe_id": str(UNIVERSE_ID)}
    with (
        patch.object(image_gen, "get_character", return_value=char),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=_canon_scene_context())),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    params = _created_params(mock_create_asset)

    # Exact provenance pointers (Task 11 brief).
    assert params.reference_asset_ids == [REFERENCE_ID, REFERENCE_2_ID]
    assert params.visual_identity_id == IDENTITY_ID
    assert params.visual_identity_version == 4
    assert params.canon_fact_ids == [FACT_ID]

    # Text-only fallback warning surfaces because the current adapter
    # advertises no support for reference bytes; reference provenance is
    # still recorded so the UI can show what *would* have been sent.
    body = res.json()
    fallback_warnings = [w for w in body["prompt_warnings"] if "text-only fallback" in w]
    assert fallback_warnings, "text-only fallback warning should be surfaced"


def test_portrait_warns_no_fallback_when_no_eligible_references(
    fake_adapter, mock_storage, mock_create_asset, mock_settings
):
    """When the context has zero approved references, no fallback warning is
    added — there's nothing to drop, so the warning would be misleading."""
    ctx = CanonicalVisualContext(
        universe_id=UNIVERSE_ID,
        facts=(VisualFact(fact_id=FACT_ID, statement="Wisp has ember eyes.", entity_id=ENTITY_ID),),
        identity_versions=(IdentityVersion(identity_id=IDENTITY_ID, version=3),),
        warnings=(),
    )
    char = {**CHAR, "entity_id": str(ENTITY_ID), "default_universe_id": str(UNIVERSE_ID)}
    with (
        patch.object(image_gen, "get_character", return_value=char),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=ctx)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    body = res.json()
    assert all("text-only fallback" not in w for w in body["prompt_warnings"])
    params = _created_params(mock_create_asset)
    assert params.reference_asset_ids == []


def test_scene_records_full_provenance_with_text_only_fallback(
    fake_adapter, mock_storage, mock_create_asset, mock_settings
):
    """Scene endpoint mirrors the portrait provenance pins and surfaces the
    fallback warning when the context has approved references but the
    adapter cannot consume them."""
    ctx = _canon_scene_context()
    doc = {
        "conversation_id": str(CONVERSATION_ID),
        "universe_id": str(UNIVERSE_ID),
        "turns": [{"turn_index": 0, "speaker_role": "player", "text": "I light the lantern."}],
    }
    with (
        patch.object(image_gen, "get_mongodb_client", return_value=_mongo_with_conversation(doc)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=ctx)),
    ):
        res = client.post("/api/image/scene", json={"conversation_id": str(CONVERSATION_ID), "last_n": 12})

    assert res.status_code == 200
    params = _created_params(mock_create_asset)
    assert params.reference_asset_ids == [REFERENCE_ID, REFERENCE_2_ID]
    assert params.visual_identity_id == IDENTITY_ID
    assert params.visual_identity_version == 4
    assert params.canon_fact_ids == [FACT_ID]
    body = res.json()
    assert any("text-only fallback" in w for w in body["prompt_warnings"])


def test_reference_capable_adapter_loads_bytes_and_emits_active_warning(
    fake_adapter, mock_storage, mock_create_asset, mock_settings
):
    """For a hypothetical reference-capable adapter the router loads the
    reference bytes from MinIO, forwards them through the dispatch helper,
    and emits the "reference conditioning active" warning. The asset's
    provenance still pins the same ``reference_asset_ids``.
    """
    from monitor_data.llm.image_providers import ImageCapabilities

    fake_adapter.capabilities = lambda: ImageCapabilities(  # type: ignore[method-assign]
        provider_id="ref-capable-test",
        model="ref-capable-1",
        supports_reference_images=True,
        supported_aspect_ratios=frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"}),
    )

    primary_bytes = b"\x89PNG-PRI"
    supporting_bytes = b"\x89PNG-SUP"

    async def fake_download(key: str, bucket: str | None = None) -> bytes:
        return primary_bytes if "primary" in key else supporting_bytes

    mock_storage.download.side_effect = fake_download

    captured: list = []

    async def capturing_structured(input):
        captured.append(list(input.reference_images))
        return PNG

    fake_adapter.generate_image_structured = capturing_structured  # type: ignore[method-assign]

    char = {**CHAR, "entity_id": str(ENTITY_ID), "default_universe_id": str(UNIVERSE_ID)}
    with (
        patch.object(image_gen, "get_character", return_value=char),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=_canon_scene_context())),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    body = res.json()

    # The router loaded both references and forwarded them in selection order.
    assert len(captured) == 1
    refs = captured[0]
    assert [ref.content for ref in refs] == [primary_bytes, supporting_bytes]
    assert {ref.content_type for ref in refs} == {"image/png"}
    assert mock_storage.download.await_count == 2

    # Asset provenance still pins the same IDs (capability changes don't
    # affect provenance recording).
    params = _created_params(mock_create_asset)
    assert params.reference_asset_ids == [REFERENCE_ID, REFERENCE_2_ID]
    assert params.visual_identity_id == IDENTITY_ID
    assert params.visual_identity_version == 4
    assert params.canon_fact_ids == [FACT_ID]

    # The "reference conditioning active" warning surfaces; no fallback warning.
    active = [w for w in body["prompt_warnings"] if "reference conditioning active" in w]
    assert active, "reference conditioning active warning should be surfaced"
    assert all("text-only fallback" not in w for w in body["prompt_warnings"])

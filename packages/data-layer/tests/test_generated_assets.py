"""
Tests for GeneratedAsset schemas (Layer 1, Task 1).

GeneratedAsset is a MongoDB-side record that pairs a MinIO object with
provenance metadata: provider info, prompt, identity version, fact IDs,
reference IDs, and source message/turn IDs.

It is NOT a Neo4j node — only CanonKeeper commits canonical changes to
Neo4j. GeneratedAsset simply records *that* an image was generated, what
prompt was used, and what produced it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from monitor_data.schemas.generated_assets import (
    ApprovalStatus,
    AssetType,
    GeneratedAsset,
    GeneratedAssetCreate,
    GeneratedAssetFilter,
    GeneratedAssetUpdate,
    ModerationStatus,
    ReferenceStatus,
    TriggerSource,
)


# =============================================================================
# HELPERS
# =============================================================================


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_payload(**overrides):
    payload = {
        "asset_type": AssetType.PORTRAIT,
        "minio_key": "assets/portraits/char-1/abc.png",
        "byte_size": 1024,
        "character_id": "char-1",
        "prompt": "Head-and-shoulders fantasy portrait.",
        "provider_id": "minimax",
        "provider_model": "image-01",
    }
    payload.update(overrides)
    return payload


# =============================================================================
# ENUM VALUES
# =============================================================================


class TestGeneratedAssetEnums:
    def test_asset_type_values(self) -> None:
        assert AssetType.PORTRAIT == "portrait"
        assert AssetType.SCENE == "scene"
        assert AssetType.LOCATION == "location"
        assert AssetType.OBJECT == "object"

    def test_approval_status_values(self) -> None:
        assert ApprovalStatus.PENDING == "pending"
        assert ApprovalStatus.APPROVED == "approved"
        assert ApprovalStatus.REJECTED == "rejected"

    def test_reference_status_values(self) -> None:
        assert ReferenceStatus.NONE == "none"
        assert ReferenceStatus.PRIMARY == "primary"
        assert ReferenceStatus.SUPPORTING == "supporting"

    def test_moderation_status_values(self) -> None:
        assert ModerationStatus.PROVIDER_DEFAULT == "provider_default"
        assert ModerationStatus.ALLOWED == "allowed"
        assert ModerationStatus.BLOCKED == "blocked"

    def test_trigger_source_values(self) -> None:
        assert TriggerSource.USER == "user"
        assert TriggerSource.LOOP_SUGGESTION == "loop_suggestion"


# =============================================================================
# GENERATED ASSET CREATE
# =============================================================================


class TestGeneratedAssetCreate:
    def test_portrait_round_trip(self) -> None:
        universe = uuid4()
        entity = uuid4()
        identity_id = uuid4()
        scene_id = uuid4()
        story_id = uuid4()
        conv_id = uuid4()
        canon_fact_id = uuid4()
        reference_id = uuid4()

        asset = GeneratedAssetCreate(
            **_base_payload(
                universe_id=universe,
                entity_id=entity,
                story_id=story_id,
                scene_id=scene_id,
                conversation_id=conv_id,
                source_message_ids=["msg-1", "msg-2"],
                visual_identity_id=identity_id,
                visual_identity_version=2,
                canon_fact_ids=[canon_fact_id],
                reference_asset_ids=[reference_id],
                negative_prompt="no text, no watermark",
                prompt_warnings=["reference fallback: text-only provider"],
                provider_capabilities={"supports_reference_images": False},
                trigger=TriggerSource.USER,
            )
        )
        assert asset.asset_type == AssetType.PORTRAIT
        assert asset.universe_id == universe
        assert asset.entity_id == entity
        assert asset.story_id == story_id
        assert asset.scene_id == scene_id
        assert asset.conversation_id == conv_id
        assert asset.source_message_ids == ["msg-1", "msg-2"]
        assert asset.visual_identity_id == identity_id
        assert asset.visual_identity_version == 2
        assert asset.canon_fact_ids == [canon_fact_id]
        assert asset.reference_asset_ids == [reference_id]
        assert asset.negative_prompt == "no text, no watermark"
        assert asset.prompt_warnings == ["reference fallback: text-only provider"]
        assert asset.provider_capabilities == {"supports_reference_images": False}
        assert asset.trigger == TriggerSource.USER

    def test_scene_round_trip(self) -> None:
        asset = GeneratedAssetCreate(
            **_base_payload(
                asset_type=AssetType.SCENE,
                minio_key="assets/scenes/session-x/xyz.png",
                conversation_id=uuid4(),
            )
        )
        assert asset.asset_type == AssetType.SCENE
        assert asset.conversation_id is not None

    def test_positive_byte_size_required(self) -> None:
        with pytest.raises(ValidationError):
            GeneratedAssetCreate(**_base_payload(byte_size=0))
        with pytest.raises(ValidationError):
            GeneratedAssetCreate(**_base_payload(byte_size=-1))

    def test_default_content_type(self) -> None:
        asset = GeneratedAssetCreate(**_base_payload())
        assert asset.content_type == "image/png"

    def test_explicit_content_type_honored(self) -> None:
        asset = GeneratedAssetCreate(**_base_payload(content_type="image/webp"))
        assert asset.content_type == "image/webp"


# =============================================================================
# GENERATED ASSET (RESPONSE)
# =============================================================================


class TestGeneratedAssetResponse:
    def test_pending_approval_default(self) -> None:
        """New assets start as PENDING and not yet approved."""
        asset = GeneratedAsset(
            asset_id=uuid4(),
            asset_type=AssetType.PORTRAIT,
            minio_key="assets/portraits/char-1/abc.png",
            byte_size=512,
            character_id="char-1",
            prompt="Portrait prompt",
            provider_id="minimax",
            provider_model="image-01",
            created_at=_now(),
            updated_at=_now(),
        )
        assert asset.approval_status == ApprovalStatus.PENDING
        assert asset.reference_status == ReferenceStatus.NONE
        assert asset.moderation_status == ModerationStatus.PROVIDER_DEFAULT
        assert asset.trigger == TriggerSource.USER
        assert asset.approved_by is None
        assert asset.approved_at is None
        assert asset.estimated_cost_usd is None

    def test_default_collection_lists(self) -> None:
        asset = GeneratedAsset(
            asset_id=uuid4(),
            asset_type=AssetType.SCENE,
            minio_key="assets/scenes/x/x.png",
            byte_size=512,
            prompt="p",
            provider_id="p",
            provider_model="m",
            created_at=_now(),
            updated_at=_now(),
        )
        assert asset.source_message_ids == []
        assert asset.canon_fact_ids == []
        assert asset.reference_asset_ids == []
        assert asset.prompt_warnings == []
        assert asset.provider_capabilities == {}


# =============================================================================
# GENERATED ASSET UPDATE
# =============================================================================


class TestGeneratedAssetUpdate:
    def test_update_only_mutates_allowed_fields(self) -> None:
        payload = GeneratedAssetUpdate(
            approval_status=ApprovalStatus.APPROVED,
            reference_status=ReferenceStatus.PRIMARY,
            approved_by="local",
            approved_at=_now(),
        )
        dumped = payload.model_dump(exclude_none=True)
        assert dumped["approval_status"] == ApprovalStatus.APPROVED
        assert dumped["reference_status"] == ReferenceStatus.PRIMARY
        assert dumped["approved_by"] == "local"
        assert "approved_at" in dumped


# =============================================================================
# GENERATED ASSET FILTER
# =============================================================================


class TestGeneratedAssetFilter:
    def test_defaults(self) -> None:
        f = GeneratedAssetFilter()
        assert f.limit == 50
        assert f.offset == 0
        assert f.character_id is None
        assert f.entity_id is None
        assert f.universe_id is None
        assert f.scene_id is None
        assert f.conversation_id is None
        assert f.asset_type is None
        assert f.approval_status is None
        assert f.reference_status is None

    def test_field_assignment(self) -> None:
        f = GeneratedAssetFilter(
            character_id="char-1",
            universe_id=uuid4(),
            asset_type=AssetType.PORTRAIT,
            approval_status=ApprovalStatus.APPROVED,
            reference_status=ReferenceStatus.PRIMARY,
            limit=10,
            offset=5,
        )
        assert f.character_id == "char-1"
        assert f.universe_id is not None
        assert f.asset_type == AssetType.PORTRAIT
        assert f.approval_status == ApprovalStatus.APPROVED
        assert f.reference_status == ReferenceStatus.PRIMARY
        assert f.limit == 10
        assert f.offset == 5

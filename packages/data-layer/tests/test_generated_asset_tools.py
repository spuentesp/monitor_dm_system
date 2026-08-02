"""Tests for GeneratedAsset MongoDB persistence tools (Task 2)."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

import monitor_data.tools.mongodb_tools.generated_assets as asset_tools
from monitor_data.db.mongodb import MongoDBClient
from monitor_data.middleware.auth import AUTHORITY_MATRIX
from monitor_data.schemas.generated_assets import (
    ApprovalStatus,
    AssetType,
    GeneratedAssetCreate,
    GeneratedAssetFilter,
    GeneratedAssetUpdate,
    ModerationStatus,
    ReferenceStatus,
    TriggerSource,
)


class _FakeCursor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = list(rows)

    def sort(self, key: str, direction: int) -> _FakeCursor:
        self.rows.sort(
            key=lambda row: (row.get(key) is None, row.get(key)),
            reverse=direction == -1,
        )
        return self

    def skip(self, amount: int) -> _FakeCursor:
        self.rows = self.rows[amount:]
        return self

    def limit(self, amount: int) -> _FakeCursor:
        self.rows = self.rows[:amount]
        return self

    def __iter__(self):
        return iter(self.rows)


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.index_calls: list[tuple[object, dict]] = []

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif isinstance(expected, dict) and "$ne" in expected:
                if actual == expected["$ne"]:
                    return False
            elif actual != expected:
                return False
        return True

    def find_one(self, query: dict) -> dict | None:
        return next((doc for doc in self.docs if self._matches(doc, query)), None)

    def find(self, query: dict) -> _FakeCursor:
        return _FakeCursor([doc for doc in self.docs if self._matches(doc, query)])

    def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        doc = self.find_one(query)
        if doc is None:
            if not upsert:
                return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
            doc = dict(query)
            self.docs.append(doc)
        for key, value in update.get("$set", {}).items():
            doc[key] = value
        for key in update.get("$unset", {}):
            doc.pop(key, None)
        return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()

    def count_documents(self, query: dict) -> int:
        return sum(1 for doc in self.docs if self._matches(doc, query))

    def create_index(self, keys: object, **kwargs: object) -> None:
        self.index_calls.append((keys, kwargs))


class _FakeMongoClient:
    def __init__(self) -> None:
        self.assets = _FakeCollection()

    def get_collection(self, name: str) -> _FakeCollection:
        if name != "generated_assets":
            raise AssertionError(f"unexpected collection {name}")
        return self.assets

    def __getitem__(self, name: str) -> _FakeCollection:
        return self.get_collection(name)


@pytest.fixture
def fake_mongo(monkeypatch: pytest.MonkeyPatch) -> _FakeMongoClient:
    client = _FakeMongoClient()
    monkeypatch.setattr(asset_tools, "get_mongodb_client", lambda: client)
    return client


def _sample_asset(**overrides: object) -> GeneratedAssetCreate:
    payload: dict[str, object] = {
        "asset_type": AssetType.PORTRAIT,
        "minio_key": "generated/asset-1.png",
        "byte_size": 2048,
        "character_id": "riri-williams",
        "entity_id": uuid4(),
        "universe_id": uuid4(),
        "story_id": uuid4(),
        "scene_id": uuid4(),
        "conversation_id": uuid4(),
        "source_message_ids": ["msg-1"],
        "visual_identity_id": uuid4(),
        "visual_identity_version": 1,
        "canon_fact_ids": [uuid4()],
        "prompt": "A cinematic portrait with copper highlights.",
        "negative_prompt": "blurry",
        "prompt_warnings": ["provider truncation avoided"],
        "reference_asset_ids": [uuid4()],
        "provider_id": "openai",
        "provider_model": "gpt-image-1",
        "provider_capabilities": {"supports_reference_images": True},
        "trigger": TriggerSource.USER,
        "moderation_status": ModerationStatus.ALLOWED,
    }
    payload.update(overrides)
    return GeneratedAssetCreate(**payload)


def test_create_and_get_roundtrip_uses_string_uuids(fake_mongo: _FakeMongoClient) -> None:
    created = asset_tools.mongodb_create_generated_asset(_sample_asset())

    assert isinstance(created.asset_id, UUID)
    assert created.approval_status == ApprovalStatus.PENDING
    assert created.reference_status == ReferenceStatus.NONE
    raw = fake_mongo.assets.docs[0]
    assert raw["asset_id"] == str(created.asset_id)
    assert raw["entity_id"] == str(created.entity_id)
    assert raw["canon_fact_ids"] == [str(created.canon_fact_ids[0])]

    loaded = asset_tools.mongodb_get_generated_asset(created.asset_id)
    assert loaded is not None
    assert loaded.asset_id == created.asset_id
    assert loaded.visual_identity_id == created.visual_identity_id
    assert loaded.provider_capabilities == {"supports_reference_images": True}
    assert loaded.created_at.tzinfo is not None


def test_get_missing_generated_asset_returns_none(fake_mongo: _FakeMongoClient) -> None:
    assert asset_tools.mongodb_get_generated_asset(uuid4()) is None


def test_update_generated_asset_changes_only_supplied_mutable_fields(
    fake_mongo: _FakeMongoClient,
) -> None:
    created = asset_tools.mongodb_create_generated_asset(_sample_asset())

    updated = asset_tools.mongodb_update_generated_asset(
        created.asset_id,
        GeneratedAssetUpdate(
            moderation_status=ModerationStatus.BLOCKED,
            prompt_warnings=["blocked by provider"],
        ),
    )

    assert updated.moderation_status == ModerationStatus.BLOCKED
    assert updated.prompt_warnings == ["blocked by provider"]
    assert updated.minio_key == created.minio_key
    assert updated.updated_at >= created.updated_at


def test_update_ignores_explicit_none_for_optional_patch_fields(
    fake_mongo: _FakeMongoClient,
) -> None:
    created = asset_tools.mongodb_create_generated_asset(_sample_asset())

    updated = asset_tools.mongodb_update_generated_asset(
        created.asset_id,
        GeneratedAssetUpdate(approval_status=None),
    )

    assert updated.approval_status == ApprovalStatus.PENDING
    assert fake_mongo.assets.docs[0]["approval_status"] == ApprovalStatus.PENDING.value


def test_update_rejects_primary_reference_when_asset_is_not_approved(
    fake_mongo: _FakeMongoClient,
) -> None:
    created = asset_tools.mongodb_create_generated_asset(_sample_asset())

    with pytest.raises(ValueError, match="approved"):
        asset_tools.mongodb_update_generated_asset(
            created.asset_id,
            GeneratedAssetUpdate(reference_status=ReferenceStatus.PRIMARY),
        )


def test_approve_allows_primary_reference_and_records_reviewer(
    fake_mongo: _FakeMongoClient,
) -> None:
    created = asset_tools.mongodb_create_generated_asset(_sample_asset())

    approved = asset_tools.mongodb_approve_generated_asset(
        created.asset_id,
        approved_by="operator-7",
        reference_status=ReferenceStatus.PRIMARY,
    )

    assert approved.approval_status == ApprovalStatus.APPROVED
    assert approved.reference_status == ReferenceStatus.PRIMARY
    assert approved.approved_by == "operator-7"
    assert approved.approved_at is not None


def test_approve_primary_demotes_previous_primary_to_supporting(
    fake_mongo: _FakeMongoClient,
) -> None:
    """A new primary reference demotes the previous one in the same scope —
    never deletes it."""
    first = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/first.png"))
    asset_tools.mongodb_approve_generated_asset(
        first.asset_id, approved_by="op", reference_status=ReferenceStatus.PRIMARY
    )
    second = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/second.png"))

    approved = asset_tools.mongodb_approve_generated_asset(
        second.asset_id, approved_by="op", reference_status=ReferenceStatus.PRIMARY
    )

    assert approved.reference_status == ReferenceStatus.PRIMARY
    demoted = asset_tools.mongodb_get_generated_asset(first.asset_id)
    assert demoted is not None  # still present — demoted, not deleted
    assert demoted.reference_status == ReferenceStatus.SUPPORTING
    assert demoted.approval_status == ApprovalStatus.APPROVED


def test_approve_primary_leaves_other_scopes_untouched(fake_mongo: _FakeMongoClient) -> None:
    """Primaries anchored to a different character/entity keep their role."""
    other = asset_tools.mongodb_create_generated_asset(
        _sample_asset(
            minio_key="generated/other.png",
            character_id="oliver-queen",
            entity_id=uuid4(),
        )
    )
    asset_tools.mongodb_approve_generated_asset(
        other.asset_id, approved_by="op", reference_status=ReferenceStatus.PRIMARY
    )
    mine = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/mine.png"))

    asset_tools.mongodb_approve_generated_asset(
        mine.asset_id, approved_by="op", reference_status=ReferenceStatus.PRIMARY
    )

    untouched = asset_tools.mongodb_get_generated_asset(other.asset_id)
    assert untouched is not None
    assert untouched.reference_status == ReferenceStatus.PRIMARY


def test_update_to_primary_demotes_previous_primary(fake_mongo: _FakeMongoClient) -> None:
    """The update path holds the same single-primary-per-scope invariant."""
    first = asset_tools.mongodb_create_generated_asset(
        _sample_asset(minio_key="generated/first.png", approval_status=ApprovalStatus.APPROVED)
    )
    asset_tools.mongodb_update_generated_asset(
        first.asset_id, GeneratedAssetUpdate(reference_status=ReferenceStatus.PRIMARY)
    )
    second = asset_tools.mongodb_create_generated_asset(
        _sample_asset(minio_key="generated/second.png", approval_status=ApprovalStatus.APPROVED)
    )

    asset_tools.mongodb_update_generated_asset(
        second.asset_id, GeneratedAssetUpdate(reference_status=ReferenceStatus.PRIMARY)
    )

    demoted = asset_tools.mongodb_get_generated_asset(first.asset_id)
    assert demoted is not None
    assert demoted.reference_status == ReferenceStatus.SUPPORTING


def test_approve_non_primary_does_not_demote_existing_primary(
    fake_mongo: _FakeMongoClient,
) -> None:
    first = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/first.png"))
    asset_tools.mongodb_approve_generated_asset(
        first.asset_id, approved_by="op", reference_status=ReferenceStatus.PRIMARY
    )
    second = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/second.png"))

    asset_tools.mongodb_approve_generated_asset(
        second.asset_id, approved_by="op", reference_status=ReferenceStatus.SUPPORTING
    )

    untouched = asset_tools.mongodb_get_generated_asset(first.asset_id)
    assert untouched is not None
    assert untouched.reference_status == ReferenceStatus.PRIMARY


def test_reject_clears_reference_and_records_rejector(fake_mongo: _FakeMongoClient) -> None:
    created = asset_tools.mongodb_create_generated_asset(_sample_asset())
    asset_tools.mongodb_approve_generated_asset(
        created.asset_id,
        approved_by="operator-7",
        reference_status=ReferenceStatus.SUPPORTING,
    )

    rejected = asset_tools.mongodb_reject_generated_asset(
        created.asset_id,
        rejected_by="operator-8",
    )

    assert rejected.approval_status == ApprovalStatus.REJECTED
    assert rejected.reference_status == ReferenceStatus.NONE
    assert rejected.approved_by is None
    assert fake_mongo.assets.docs[0]["rejected_by"] == "operator-8"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("character_id", "riri-williams"),
        ("entity_id", "00000000-0000-0000-0000-000000000001"),
        ("universe_id", "00000000-0000-0000-0000-000000000002"),
        ("scene_id", "00000000-0000-0000-0000-000000000003"),
        ("conversation_id", "00000000-0000-0000-0000-000000000004"),
        ("asset_type", AssetType.SCENE),
        ("approval_status", ApprovalStatus.APPROVED),
        ("reference_status", ReferenceStatus.PRIMARY),
        ("trigger", TriggerSource.LOOP_SUGGESTION),
    ],
)
def test_list_generated_assets_filters_each_supported_field(
    fake_mongo: _FakeMongoClient,
    field: str,
    value: object,
) -> None:
    matching: dict[str, object] = {
        "character_id": "riri-williams",
        "entity_id": UUID("00000000-0000-0000-0000-000000000001"),
        "universe_id": UUID("00000000-0000-0000-0000-000000000002"),
        "scene_id": UUID("00000000-0000-0000-0000-000000000003"),
        "conversation_id": UUID("00000000-0000-0000-0000-000000000004"),
        "asset_type": AssetType.SCENE,
        "approval_status": ApprovalStatus.APPROVED,
        "reference_status": ReferenceStatus.PRIMARY,
        "trigger": TriggerSource.LOOP_SUGGESTION,
    }
    matching["minio_key"] = f"generated/{field}-match.png"
    asset_tools.mongodb_create_generated_asset(_sample_asset(**matching))
    asset_tools.mongodb_create_generated_asset(
        _sample_asset(
            minio_key=f"generated/{field}-other.png",
            character_id="someone-else",
            entity_id=uuid4(),
            universe_id=uuid4(),
            scene_id=uuid4(),
            conversation_id=uuid4(),
            asset_type=AssetType.OBJECT,
            approval_status=ApprovalStatus.PENDING,
            reference_status=ReferenceStatus.NONE,
            trigger=TriggerSource.USER,
        )
    )

    result = asset_tools.mongodb_list_generated_assets(GeneratedAssetFilter(**{field: value}))

    assert len(result) == 1
    assert result[0].minio_key == f"generated/{field}-match.png"


def test_list_generated_assets_supports_offset_and_limit(fake_mongo: _FakeMongoClient) -> None:
    for index in range(3):
        asset_tools.mongodb_create_generated_asset(
            _sample_asset(minio_key=f"generated/{index}.png", character_id=f"char-{index}")
        )

    result = asset_tools.mongodb_list_generated_assets(
        GeneratedAssetFilter(limit=1, offset=1)
    )

    assert len(result) == 1
    assert result[0].minio_key in {"generated/0.png", "generated/1.png", "generated/2.png"}


def test_list_excludes_rejected_assets_by_default(fake_mongo: _FakeMongoClient) -> None:
    kept = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/kept.png"))
    dropped = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/dropped.png"))
    asset_tools.mongodb_reject_generated_asset(dropped.asset_id, rejected_by="operator")

    result = asset_tools.mongodb_list_generated_assets(GeneratedAssetFilter())

    assert [asset.minio_key for asset in result] == ["generated/kept.png"]
    assert kept.asset_id == result[0].asset_id


def test_list_include_rejected_flag_returns_rejected_assets(fake_mongo: _FakeMongoClient) -> None:
    asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/kept.png"))
    dropped = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/dropped.png"))
    asset_tools.mongodb_reject_generated_asset(dropped.asset_id, rejected_by="operator")

    result = asset_tools.mongodb_list_generated_assets(GeneratedAssetFilter(include_rejected=True))

    assert {asset.minio_key for asset in result} == {"generated/kept.png", "generated/dropped.png"}


def test_list_explicit_rejected_filter_still_matches_rejected(fake_mongo: _FakeMongoClient) -> None:
    asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/kept.png"))
    dropped = asset_tools.mongodb_create_generated_asset(_sample_asset(minio_key="generated/dropped.png"))
    asset_tools.mongodb_reject_generated_asset(dropped.asset_id, rejected_by="operator")

    result = asset_tools.mongodb_list_generated_assets(
        GeneratedAssetFilter(approval_status=ApprovalStatus.REJECTED)
    )

    assert [asset.minio_key for asset in result] == ["generated/dropped.png"]


def test_missing_asset_mutations_raise_value_error(fake_mongo: _FakeMongoClient) -> None:
    asset_id = uuid4()
    with pytest.raises(ValueError, match="not found"):
        asset_tools.mongodb_update_generated_asset(asset_id, GeneratedAssetUpdate())
    with pytest.raises(ValueError, match="not found"):
        asset_tools.mongodb_approve_generated_asset(
            asset_id, approved_by="operator", reference_status=ReferenceStatus.NONE
        )
    with pytest.raises(ValueError, match="not found"):
        asset_tools.mongodb_reject_generated_asset(asset_id, rejected_by="operator")


def test_authority_matrix_keeps_asset_writes_restricted() -> None:
    assert AUTHORITY_MATRIX["mongodb_create_generated_asset"] == ["ImageRouter"]
    assert AUTHORITY_MATRIX["mongodb_update_generated_asset"] == ["ImageRouter"]
    assert AUTHORITY_MATRIX["mongodb_approve_generated_asset"] == ["ImageRouter", "CanonKeeper"]
    assert AUTHORITY_MATRIX["mongodb_reject_generated_asset"] == ["ImageRouter", "CanonKeeper"]
    assert AUTHORITY_MATRIX["mongodb_get_generated_asset"] == ["*"]
    assert AUTHORITY_MATRIX["mongodb_list_generated_assets"] == ["*"]
    assert "neo4j_create_generated_asset" not in AUTHORITY_MATRIX


def test_new_asset_tools_are_exported_from_facade() -> None:
    import monitor_data.tools.mongodb_tools as facade

    for name in (
        "mongodb_create_generated_asset",
        "mongodb_get_generated_asset",
        "mongodb_list_generated_assets",
        "mongodb_update_generated_asset",
        "mongodb_approve_generated_asset",
        "mongodb_reject_generated_asset",
    ):
        assert name in facade.__all__
        assert callable(getattr(facade, name))


@pytest.mark.asyncio
async def test_create_indexes_provisions_asset_indexes() -> None:
    client = MongoDBClient.__new__(MongoDBClient)
    columns: dict[str, MagicMock] = {}
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: columns.setdefault(name, MagicMock())
    client._db = db

    await client._create_indexes()

    calls = columns["generated_assets"].create_index.call_args_list
    keys = [call.args[0] for call in calls]
    assert [("asset_id", 1)] in keys
    unique = next(call for call in calls if call.args[0] == [("asset_id", 1)])
    assert unique.kwargs["unique"] is True
    assert [("entity_id", 1), ("universe_id", 1), ("created_at", -1)] in keys
    assert [("character_id", 1), ("created_at", -1)] in keys
    assert [("scene_id", 1), ("created_at", -1)] in keys
    assert [("conversation_id", 1), ("created_at", -1)] in keys

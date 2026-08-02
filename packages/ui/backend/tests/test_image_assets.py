"""Tests for the image asset gallery/approval router (Task 6).

The router is exercised end-to-end against the real Task 2 data-layer tool
functions with an in-memory Mongo fake — only MinIO presigning is mocked.
This keeps the router thin (validation/serialization) while the behavioral
guarantees (default gallery exclusion, primary demotion, optimistic locking)
are verified through the API surface.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from monitor_data.schemas.generated_assets import (
    AssetType,
    GeneratedAssetCreate,
)
from monitor_data.schemas.visual_identity import VisualIdentityCreate, VisualIdentityStatus

import monitor_data.tools.mongodb_tools.generated_assets as asset_tools
import monitor_data.tools.mongodb_tools.proposals as proposal_tools
import monitor_data.tools.mongodb_tools.visual_identities as identity_tools
import monitor_ui.routers.image_assets as image_assets
from monitor_ui.routers import character_storage
from monitor_ui.routers.image_assets import router

app = FastAPI()
app.include_router(router, prefix="/api/image")
client = TestClient(app)

CHAR_ID = "c-1"
OTHER_CHAR_ID = "c-2"


# ---------------------------------------------------------------------------
# In-memory Mongo fake (shared by assets, identities, and characters)
# ---------------------------------------------------------------------------


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

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict) and "$ne" in expected:
                if actual == expected["$ne"]:
                    return False
            elif isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
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

    def _apply_set(self, doc: dict, update: dict) -> None:
        for key, value in update.get("$set", {}).items():
            doc[key] = value

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        doc = self.find_one(query)
        if doc is None:
            return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
        self._apply_set(doc, update)
        return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()

    def find_one_and_update(self, query: dict, update: dict, return_document: bool = False):
        doc = self.find_one(query)
        if doc is None:
            return None
        self._apply_set(doc, update)
        return doc


class _FakeMongoClient:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeCollection] = {}

    def get_collection(self, name: str) -> _FakeCollection:
        if name not in self.collections:
            self.collections[name] = _FakeCollection()
        return self.collections[name]


@pytest.fixture
def fake_mongo(monkeypatch: pytest.MonkeyPatch) -> _FakeMongoClient:
    client = _FakeMongoClient()
    monkeypatch.setattr(asset_tools, "get_mongodb_client", lambda: client)
    monkeypatch.setattr(identity_tools, "get_mongodb_client", lambda: client)
    monkeypatch.setattr(proposal_tools, "get_mongodb_client", lambda: client)
    # Proposals verify story anchors via Neo4j when story_id is set; the
    # visual-identity flow never sets one, so a mock client is sufficient.
    monkeypatch.setattr(proposal_tools, "get_neo4j_client", lambda: AsyncMock())
    # character_storage resolves the client lazily from the db module.
    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: client)
    return client


@pytest.fixture
def mock_minio():
    minio = AsyncMock()
    minio.presigned_url.return_value = "https://minio.example.com/presigned/asset"
    with patch.object(image_assets, "get_minio_client", return_value=minio):
        yield minio


# ---------------------------------------------------------------------------
# Seed helpers (real tool functions against the fake)
# ---------------------------------------------------------------------------


def _seed_asset(fake_mongo: _FakeMongoClient, **overrides: Any) -> dict:
    payload: dict[str, Any] = {
        "asset_type": AssetType.PORTRAIT,
        "minio_key": f"assets/portrait/character-{CHAR_ID}/{uuid4().hex}.png",
        "byte_size": 2048,
        "character_id": CHAR_ID,
        "prompt": "A cinematic portrait.",
        "provider_id": "fake-provider",
        "provider_model": "fake-image-1",
    }
    payload.update(overrides)
    asset = asset_tools.mongodb_create_generated_asset(GeneratedAssetCreate(**payload))
    return asset.model_dump(mode="json")


def _seed_identity(**overrides: Any):
    payload: dict[str, Any] = {
        "character_id": CHAR_ID,
        "description": "A fox-spirit guide with ember eyes.",
        "source": "manual",
    }
    payload.update(overrides)
    return identity_tools.mongodb_upsert_visual_identity(VisualIdentityCreate(**payload))


# ---------------------------------------------------------------------------
# GET /assets — gallery listing
# ---------------------------------------------------------------------------


def test_list_assets_returns_seeded_assets(fake_mongo: _FakeMongoClient) -> None:
    seeded = _seed_asset(fake_mongo)

    res = client.get("/api/image/assets")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["asset_id"] == seeded["asset_id"]
    assert body[0]["prompt"] == "A cinematic portrait."
    assert body[0]["approval_status"] == "pending"


def test_list_assets_filters_by_character_and_type(fake_mongo: _FakeMongoClient) -> None:
    mine = _seed_asset(fake_mongo)
    _seed_asset(fake_mongo, character_id=OTHER_CHAR_ID)
    _seed_asset(fake_mongo, asset_type=AssetType.SCENE, conversation_id=uuid4())

    res = client.get(f"/api/image/assets?character_id={CHAR_ID}&asset_type=portrait")

    assert res.status_code == 200
    assert [a["asset_id"] for a in res.json()] == [mine["asset_id"]]


def test_list_assets_filters_by_scope_ids(fake_mongo: _FakeMongoClient) -> None:
    universe_id, scene_id, conversation_id = uuid4(), uuid4(), uuid4()
    mine = _seed_asset(
        fake_mongo,
        asset_type=AssetType.SCENE,
        character_id=None,
        universe_id=universe_id,
        scene_id=scene_id,
        conversation_id=conversation_id,
    )
    _seed_asset(fake_mongo)

    res = client.get(
        f"/api/image/assets?universe_id={universe_id}&scene_id={scene_id}&conversation_id={conversation_id}"
    )

    assert res.status_code == 200
    assert [a["asset_id"] for a in res.json()] == [mine["asset_id"]]


def test_list_assets_invalid_scope_uuid_is_422(fake_mongo: _FakeMongoClient) -> None:
    res = client.get("/api/image/assets?universe_id=not-a-uuid")
    assert res.status_code == 422


def test_list_assets_excludes_rejected_by_default(fake_mongo: _FakeMongoClient) -> None:
    kept = _seed_asset(fake_mongo)
    dropped = _seed_asset(fake_mongo)
    client.post(f"/api/image/assets/{dropped['asset_id']}/reject", json={})

    res = client.get("/api/image/assets")

    assert res.status_code == 200
    assert [a["asset_id"] for a in res.json()] == [kept["asset_id"]]


def test_list_assets_include_rejected_flag(fake_mongo: _FakeMongoClient) -> None:
    kept = _seed_asset(fake_mongo)
    dropped = _seed_asset(fake_mongo)
    client.post(f"/api/image/assets/{dropped['asset_id']}/reject", json={})

    res = client.get("/api/image/assets?include_rejected=true")

    assert res.status_code == 200
    assert {a["asset_id"] for a in res.json()} == {kept["asset_id"], dropped["asset_id"]}


def test_list_assets_explicit_rejected_status_filter(fake_mongo: _FakeMongoClient) -> None:
    _seed_asset(fake_mongo)
    dropped = _seed_asset(fake_mongo)
    client.post(f"/api/image/assets/{dropped['asset_id']}/reject", json={})

    res = client.get("/api/image/assets?approval_status=rejected")

    assert res.status_code == 200
    assert [a["asset_id"] for a in res.json()] == [dropped["asset_id"]]


def test_list_assets_filters_by_reference_status(fake_mongo: _FakeMongoClient) -> None:
    primary = _seed_asset(fake_mongo)
    _seed_asset(fake_mongo)
    client.post(
        f"/api/image/assets/{primary['asset_id']}/approve",
        json={"reference_status": "primary"},
    )

    res = client.get("/api/image/assets?reference_status=primary")

    assert res.status_code == 200
    assert [a["asset_id"] for a in res.json()] == [primary["asset_id"]]


# ---------------------------------------------------------------------------
# GET /assets/{asset_id} + /file
# ---------------------------------------------------------------------------


def test_get_asset_returns_metadata(fake_mongo: _FakeMongoClient) -> None:
    seeded = _seed_asset(fake_mongo)

    res = client.get(f"/api/image/assets/{seeded['asset_id']}")

    assert res.status_code == 200
    body = res.json()
    assert body["asset_id"] == seeded["asset_id"]
    assert body["minio_key"] == seeded["minio_key"]
    assert body["provider_id"] == "fake-provider"


def test_get_asset_404_for_unknown_id(fake_mongo: _FakeMongoClient) -> None:
    res = client.get(f"/api/image/assets/{uuid4()}")
    assert res.status_code == 404


def test_asset_file_redirects_to_presigned_url(fake_mongo: _FakeMongoClient, mock_minio) -> None:
    seeded = _seed_asset(fake_mongo)

    res = client.get(f"/api/image/assets/{seeded['asset_id']}/file", follow_redirects=False)

    assert res.status_code in (302, 307)
    assert res.headers["location"] == "https://minio.example.com/presigned/asset"
    mock_minio.presigned_url.assert_awaited_with(seeded["minio_key"], expires_in=3600)


def test_asset_file_404_for_unknown_id(fake_mongo: _FakeMongoClient, mock_minio) -> None:
    res = client.get(f"/api/image/assets/{uuid4()}/file")
    assert res.status_code == 404
    mock_minio.presigned_url.assert_not_awaited()


# ---------------------------------------------------------------------------
# POST /assets/{asset_id}/approve
# ---------------------------------------------------------------------------


def test_approve_asset_default_body(fake_mongo: _FakeMongoClient) -> None:
    seeded = _seed_asset(fake_mongo)

    res = client.post(f"/api/image/assets/{seeded['asset_id']}/approve", json={})

    assert res.status_code == 200
    body = res.json()
    assert body["approval_status"] == "approved"
    assert body["reference_status"] == "none"
    assert body["approved_by"] == "local"
    assert body["approved_at"] is not None


def test_approve_asset_as_primary_reference(fake_mongo: _FakeMongoClient) -> None:
    seeded = _seed_asset(fake_mongo)

    res = client.post(
        f"/api/image/assets/{seeded['asset_id']}/approve",
        json={"approved_by": "gm", "reference_status": "primary"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["approval_status"] == "approved"
    assert body["reference_status"] == "primary"
    assert body["approved_by"] == "gm"


def test_approve_primary_demotes_previous_primary_without_deleting(
    fake_mongo: _FakeMongoClient,
) -> None:
    first = _seed_asset(fake_mongo)
    second = _seed_asset(fake_mongo)
    client.post(f"/api/image/assets/{first['asset_id']}/approve", json={"reference_status": "primary"})

    res = client.post(
        f"/api/image/assets/{second['asset_id']}/approve",
        json={"reference_status": "primary"},
    )

    assert res.status_code == 200
    assert res.json()["reference_status"] == "primary"
    demoted = client.get(f"/api/image/assets/{first['asset_id']}")
    assert demoted.status_code == 200  # still exists — demoted, never deleted
    assert demoted.json()["reference_status"] == "supporting"
    assert demoted.json()["approval_status"] == "approved"


def test_approve_404_for_unknown_asset(fake_mongo: _FakeMongoClient) -> None:
    res = client.post(f"/api/image/assets/{uuid4()}/approve", json={})
    assert res.status_code == 404


def test_approve_use_as_avatar_updates_only_the_matching_character(
    fake_mongo: _FakeMongoClient,
) -> None:
    characters = fake_mongo.get_collection("characters")
    characters.insert_one({"id": CHAR_ID, "name": "Wisp", "avatar_url": None})
    characters.insert_one({"id": OTHER_CHAR_ID, "name": "Ollie", "avatar_url": None})
    seeded = _seed_asset(fake_mongo)

    res = client.post(
        f"/api/image/assets/{seeded['asset_id']}/approve",
        json={"use_as_avatar": True},
    )

    assert res.status_code == 200
    assert res.json()["approval_status"] == "approved"
    char = character_storage.get_character(CHAR_ID)
    other = character_storage.get_character(OTHER_CHAR_ID)
    assert char is not None and char["avatar_url"] == seeded["minio_key"]
    assert other is not None and other["avatar_url"] is None


def test_approve_use_as_avatar_400_for_scene_asset(fake_mongo: _FakeMongoClient) -> None:
    seeded = _seed_asset(fake_mongo, asset_type=AssetType.SCENE, character_id=None)

    res = client.post(
        f"/api/image/assets/{seeded['asset_id']}/approve",
        json={"use_as_avatar": True},
    )

    assert res.status_code == 400
    # The asset must not be approved as a side effect of the failed request.
    assert client.get(f"/api/image/assets/{seeded['asset_id']}").json()["approval_status"] == "pending"


def test_approve_use_as_avatar_400_for_portrait_without_character(
    fake_mongo: _FakeMongoClient,
) -> None:
    seeded = _seed_asset(fake_mongo, character_id=None)

    res = client.post(
        f"/api/image/assets/{seeded['asset_id']}/approve",
        json={"use_as_avatar": True},
    )

    assert res.status_code == 400


def test_approve_use_as_avatar_404_for_unknown_character(fake_mongo: _FakeMongoClient) -> None:
    seeded = _seed_asset(fake_mongo)

    res = client.post(
        f"/api/image/assets/{seeded['asset_id']}/approve",
        json={"use_as_avatar": True},
    )

    assert res.status_code == 404
    assert client.get(f"/api/image/assets/{seeded['asset_id']}").json()["approval_status"] == "pending"


# ---------------------------------------------------------------------------
# POST /assets/{asset_id}/reject
# ---------------------------------------------------------------------------


def test_reject_asset_clears_reference_and_hides_from_default_gallery(
    fake_mongo: _FakeMongoClient,
) -> None:
    seeded = _seed_asset(fake_mongo)
    client.post(
        f"/api/image/assets/{seeded['asset_id']}/approve",
        json={"reference_status": "supporting"},
    )

    res = client.post(
        f"/api/image/assets/{seeded['asset_id']}/reject",
        json={"rejected_by": "gm"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["approval_status"] == "rejected"
    # A rejected asset can no longer act as a reference.
    assert body["reference_status"] == "none"
    assert body["approved_by"] is None
    # ... and no longer appears in default galleries.
    assert client.get("/api/image/assets").json() == []
    assert client.get("/api/image/assets?reference_status=supporting").json() == []
    rejected = client.get("/api/image/assets?approval_status=rejected").json()
    assert [a["asset_id"] for a in rejected] == [seeded["asset_id"]]


def test_reject_404_for_unknown_asset(fake_mongo: _FakeMongoClient) -> None:
    res = client.post(f"/api/image/assets/{uuid4()}/reject", json={})
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET /visual-identities
# ---------------------------------------------------------------------------


def test_list_visual_identities_returns_all_statuses_by_default(
    fake_mongo: _FakeMongoClient,
) -> None:
    draft = _seed_identity()
    other = _seed_identity(character_id=OTHER_CHAR_ID)

    res = client.get("/api/image/visual-identities")

    assert res.status_code == 200
    ids = {i["identity_id"] for i in res.json()}
    assert ids == {str(draft.identity_id), str(other.identity_id)}


def test_list_visual_identities_filters_by_anchor_and_status(
    fake_mongo: _FakeMongoClient,
) -> None:
    mine = _seed_identity()
    _seed_identity(character_id=OTHER_CHAR_ID)

    res = client.get(f"/api/image/visual-identities?character_id={CHAR_ID}&status=draft")

    assert res.status_code == 200
    assert [i["identity_id"] for i in res.json()] == [str(mine.identity_id)]


def test_get_current_identity_returns_latest_approved(fake_mongo: _FakeMongoClient) -> None:
    draft = _seed_identity()
    approved = identity_tools.mongodb_upsert_visual_identity(
        identity_tools.VisualIdentityUpdate(
            identity_id=draft.identity_id,
            expected_version=1,
            status=VisualIdentityStatus.APPROVED,
        )
    )

    res = client.get(f"/api/image/visual-identities/current?character_id={CHAR_ID}")

    assert res.status_code == 200
    body = res.json()
    assert body["identity_id"] == str(approved.identity_id)
    assert body["version"] == 2
    assert body["status"] == "approved"


def test_get_current_identity_404_when_none_matches(fake_mongo: _FakeMongoClient) -> None:
    _seed_identity()  # draft only — the default lookup wants approved

    res = client.get(f"/api/image/visual-identities/current?character_id={CHAR_ID}")

    assert res.status_code == 404


def test_get_current_identity_status_and_card_default_only_params(
    fake_mongo: _FakeMongoClient,
) -> None:
    card = _seed_identity()
    _seed_identity(universe_id=uuid4(), description="Incarnation identity.")

    res = client.get(
        f"/api/image/visual-identities/current?character_id={CHAR_ID}"
        "&status=draft&card_default_only=true"
    )

    assert res.status_code == 200
    assert res.json()["identity_id"] == str(card.identity_id)


def test_get_current_identity_400_without_anchor(fake_mongo: _FakeMongoClient) -> None:
    res = client.get("/api/image/visual-identities/current")
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# PUT /visual-identities/current — optimistic locking
# ---------------------------------------------------------------------------


def test_put_identity_creates_next_version(fake_mongo: _FakeMongoClient) -> None:
    original = _seed_identity()

    res = client.put(
        "/api/image/visual-identities/current",
        json={
            "identity_id": str(original.identity_id),
            "expected_version": 1,
            "description": "Updated after the canon costume reveal.",
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 2
    assert body["identity_id"] != str(original.identity_id)
    assert body["description"] == "Updated after the canon costume reveal."


def test_put_identity_409_on_version_conflict(fake_mongo: _FakeMongoClient) -> None:
    original = _seed_identity()
    payload = {
        "identity_id": str(original.identity_id),
        "expected_version": 1,
        "description": "First writer wins.",
    }
    assert client.put("/api/image/visual-identities/current", json=payload).status_code == 200

    res = client.put(
        "/api/image/visual-identities/current",
        json={**payload, "description": "Stale writer loses."},
    )

    assert res.status_code == 409


def test_put_identity_404_for_unknown_identity(fake_mongo: _FakeMongoClient) -> None:
    res = client.put(
        "/api/image/visual-identities/current",
        json={"identity_id": str(uuid4()), "expected_version": 1, "description": "ghost"},
    )
    assert res.status_code == 404


def test_put_identity_400_without_lock_metadata(fake_mongo: _FakeMongoClient) -> None:
    res = client.put(
        "/api/image/visual-identities/current",
        json={"description": "no lock fields at all"},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# PUT /visual-identities/current — canon proposal staging (Task 7)
# ---------------------------------------------------------------------------


def _staged_proposals(fake_mongo: _FakeMongoClient) -> list[dict]:
    return fake_mongo.get_collection("proposed_changes").docs


def test_put_identity_with_entity_anchor_stages_pending_proposal(
    fake_mongo: _FakeMongoClient,
) -> None:
    entity_id, universe_id = uuid4(), uuid4()
    original = _seed_identity(entity_id=entity_id, universe_id=universe_id)

    res = client.put(
        "/api/image/visual-identities/current",
        json={
            "identity_id": str(original.identity_id),
            "expected_version": 1,
            "description": "Canonized after the costume reveal.",
        },
    )

    assert res.status_code == 200
    edited = res.json()
    proposals = _staged_proposals(fake_mongo)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["change_type"] == "entity"
    assert proposal["proposer"] == "UI"
    assert proposal["status"] == "pending"
    content = proposal["content"]
    assert content["operation"] == "set_visual_identity"
    assert content["entity_id"] == str(entity_id)
    assert content["universe_id"] == str(universe_id)
    # Provenance back to the staged identity version.
    assert content["visual_identity"]["identity_id"] == edited["identity_id"]
    assert content["visual_identity_version"] == edited["version"] == 2


def test_put_card_default_identity_stages_no_proposal(fake_mongo: _FakeMongoClient) -> None:
    original = _seed_identity()  # card default: character_id only, no entity

    res = client.put(
        "/api/image/visual-identities/current",
        json={
            "identity_id": str(original.identity_id),
            "expected_version": 1,
            "description": "Card-level tweak; no canon target.",
        },
    )

    assert res.status_code == 200
    assert res.json()["version"] == 2
    assert _staged_proposals(fake_mongo) == []


def test_put_incarnation_identity_without_entity_stages_no_proposal(
    fake_mongo: _FakeMongoClient,
) -> None:
    # Incarnation anchor (character + universe) but no canonical entity target.
    original = _seed_identity(universe_id=uuid4())

    res = client.put(
        "/api/image/visual-identities/current",
        json={
            "identity_id": str(original.identity_id),
            "expected_version": 1,
            "description": "Incarnation tweak without a canonical entity.",
        },
    )

    assert res.status_code == 200
    assert _staged_proposals(fake_mongo) == []

"""Tests for the /api/prompt-collections router (Forge Prompts CRUD)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from monitor_data.schemas.prompt_collections import (
    PromptCollectionListResponse,
    PromptCollectionResponse,
    PromptEntry,
)

from monitor_ui.main import app

client = TestClient(app)
_MODULE = "monitor_ui.routers.prompt_collections"


def _response(**overrides) -> PromptCollectionResponse:
    base = {
        "collection_id": uuid4(),
        "name": "V5 Session Zero",
        "category": "session_zero",
        "tags": ["gothic"],
        "entries": [PromptEntry(order=0, category="name", question_text="What are you called?")],
        "is_builtin": False,
        "hand_authored": True,
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return PromptCollectionResponse(**base)


def test_create_prompt_collection():
    created = _response()
    with patch(f"{_MODULE}.mongodb_create_prompt_collection", return_value=created) as m:
        resp = client.post(
            "/api/prompt-collections",
            json={
                "name": "V5 Session Zero",
                "category": "session_zero",
                "entries": [{"order": 0, "category": "name", "question_text": "What are you called?"}],
            },
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "V5 Session Zero"
    m.assert_called_once()


def test_get_prompt_collection_404():
    with patch(f"{_MODULE}.mongodb_get_prompt_collection", return_value=None):
        resp = client.get(f"/api/prompt-collections/{uuid4()}")
    assert resp.status_code == 404


def test_list_prompt_collections_passes_filters():
    listing = PromptCollectionListResponse(collections=[_response()], total=1, limit=50, offset=0)
    with patch(f"{_MODULE}.mongodb_list_prompt_collections", return_value=listing) as m:
        resp = client.get("/api/prompt-collections", params={"category": "session_zero"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert m.call_args.args[0].category == "session_zero"


def test_update_prompt_collection_404_maps_valueerror():
    with patch(f"{_MODULE}.mongodb_update_prompt_collection", side_effect=ValueError("not found")):
        resp = client.patch(f"/api/prompt-collections/{uuid4()}", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_prompt_collection():
    with patch(f"{_MODULE}.mongodb_delete_prompt_collection", return_value=True):
        resp = client.delete(f"/api/prompt-collections/{uuid4()}")
    assert resp.status_code == 204

    with patch(f"{_MODULE}.mongodb_delete_prompt_collection", return_value=False):
        resp = client.delete(f"/api/prompt-collections/{uuid4()}")
    assert resp.status_code == 404


def _version(**overrides):
    from monitor_data.schemas.prompt_collections import PromptCollectionVersionResponse

    base = {
        "version_id": uuid4(),
        "collection_id": uuid4(),
        "version": "v1",
        "name": "V5 Session Zero",
        "category": "session_zero",
        "tags": [],
        "entries": [PromptEntry(order=0, category="name", question_text="What are you called?")],
        "published_at": datetime.now(UTC),
    }
    base.update(overrides)
    return PromptCollectionVersionResponse(**base)


def test_publish_prompt_collection():
    version = _version()
    with patch(f"{_MODULE}.mongodb_publish_prompt_collection", return_value=version) as m:
        resp = client.post(f"/api/prompt-collections/{version.collection_id}/publish", json={"note": "first"})
    assert resp.status_code == 201
    assert resp.json()["version"] == "v1"
    m.assert_called_once()


def test_publish_missing_collection_404():
    with patch(f"{_MODULE}.mongodb_publish_prompt_collection", side_effect=ValueError("not found")):
        resp = client.post(f"/api/prompt-collections/{uuid4()}/publish", json={})
    assert resp.status_code == 404


def test_list_versions():
    from monitor_data.schemas.prompt_collections import PromptCollectionVersionListResponse

    listing = PromptCollectionVersionListResponse(versions=[_version(), _version(version="v2")], total=2)
    with patch(f"{_MODULE}.mongodb_list_prompt_collection_versions", return_value=listing):
        resp = client.get(f"/api/prompt-collections/{uuid4()}/versions")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_restore_version():
    restored = _response()
    with patch(f"{_MODULE}.mongodb_restore_prompt_collection_version", return_value=restored):
        resp = client.post(f"/api/prompt-collections/versions/{uuid4()}/restore")
    assert resp.status_code == 200
    assert resp.json()["name"] == "V5 Session Zero"

    with patch(f"{_MODULE}.mongodb_restore_prompt_collection_version", side_effect=ValueError("gone")):
        resp = client.post(f"/api/prompt-collections/versions/{uuid4()}/restore")
    assert resp.status_code == 404

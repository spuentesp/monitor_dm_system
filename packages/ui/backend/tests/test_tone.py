"""Tests for the Tone router (UI Layer 3)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch, Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_data.schemas.tone_profiles import (
    ToneProfileResponse,
    ToneProfileListResponse,
)
from monitor_data.schemas.tone_libraries import (
    ToneLibraryResponse,
    ToneLibraryListResponse,
)
from monitor_data.schemas.tag_registry import (
    TagDefinitionResponse,
    TagDefinitionListResponse,
    TagSuggestionResponse,
    TagCategory,
)

from monitor_ui.main import app

client = TestClient(app)
BASE = "/api/tone"


class TestListToneProfiles:
    @patch("monitor_ui.routers.tone.mongodb_list_tone_profiles")
    def test_list_profiles_default_pagination(self, mock_list: Mock) -> None:
        mock_list.return_value = ToneProfileListResponse(
            profiles=[], total=0, page=1, page_size=50
        )
        resp = client.get(f"{BASE}/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["total"] == 0

    @patch("monitor_ui.routers.tone.mongodb_list_tone_profiles")
    def test_list_profiles_with_builtin_filter(self, mock_list: Mock) -> None:
        mock_list.return_value = ToneProfileListResponse(
            profiles=[], total=0, page=1, page_size=20
        )
        resp = client.get(f"{BASE}/profiles?is_builtin=true&page_size=20")
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs["is_builtin"] is True


class TestListBuiltinProfiles:
    @patch("monitor_ui.routers.tone.mongodb_list_tone_profiles")
    def test_list_builtin_profiles(self, mock_list: Mock) -> None:
        mock_list.return_value = ToneProfileListResponse(
            profiles=[], total=0, page=1, page_size=50
        )
        resp = client.get(f"{BASE}/profiles/builtin")
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs["is_builtin"] is True


class TestGetToneProfile:
    @patch("monitor_ui.routers.tone.mongodb_get_tone_profile")
    def test_get_profile_found(self, mock_get: Mock) -> None:
        pid = uuid4()
        mock_get.return_value = ToneProfileResponse(
            profile_id=pid,
            name="Dramatic",
            description="Baroque.",
            instruction="Baroque, weighty.",
            trigger_tags=["dramatic"],
            category="narrative",
            language="en",
            pack_id=None,
            is_builtin=True,
            example_output=None,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.get(f"{BASE}/profiles/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Dramatic"

    @patch("monitor_ui.routers.tone.mongodb_get_tone_profile")
    def test_get_profile_not_found(self, mock_get: Mock) -> None:
        mock_get.return_value = None
        resp = client.get(f"{BASE}/profiles/{uuid4()}")
        assert resp.status_code == 404


class TestCreateToneProfile:
    @patch("monitor_ui.routers.tone.mongodb_create_tone_profile")
    def test_create_profile(self, mock_create: Mock) -> None:
        pid = uuid4()
        mock_create.return_value = ToneProfileResponse(
            profile_id=pid,
            name="grim_noir",
            description="Grim noir.",
            instruction="Terse.",
            trigger_tags=["grim"],
            category="narrative",
            language="en",
            pack_id=None,
            is_builtin=False,
            example_output=None,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.post(
            f"{BASE}/profiles",
            json={
                "name": "grim_noir",
                "description": "Grim noir.",
                "instruction": "Terse.",
                "trigger_tags": ["grim"],
                "category": "narrative",
                "language": "en",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "grim_noir"


class TestUpdateToneProfile:
    @patch("monitor_ui.routers.tone.mongodb_update_tone_profile")
    def test_update_profile_success(self, mock_update: Mock) -> None:
        pid = uuid4()
        mock_update.return_value = ToneProfileResponse(
            profile_id=pid,
            name="updated",
            description="Desc",
            instruction="Instr",
            trigger_tags=["tag"],
            category="narrative",
            language="en",
            pack_id=None,
            is_builtin=False,
            example_output=None,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.put(f"{BASE}/profiles/{pid}", json={"name": "updated"})
        assert resp.status_code == 200

    @patch("monitor_ui.routers.tone.mongodb_update_tone_profile")
    def test_update_profile_not_found(self, mock_update: Mock) -> None:
        mock_update.return_value = None
        resp = client.put(f"{BASE}/profiles/{uuid4()}", json={"name": "x"})
        assert resp.status_code == 404

    @patch("monitor_ui.routers.tone.mongodb_update_tone_profile")
    def test_update_builtin_forbidden(self, mock_update: Mock) -> None:
        mock_update.side_effect = ValueError("Cannot update built-in")
        resp = client.put(f"{BASE}/profiles/{uuid4()}", json={"name": "x"})
        assert resp.status_code == 403


class TestDeleteToneProfile:
    @patch("monitor_ui.routers.tone.mongodb_delete_tone_profile")
    def test_delete_profile_success(self, mock_delete: Mock) -> None:
        mock_delete.return_value = True
        resp = client.delete(f"{BASE}/profiles/{uuid4()}")
        assert resp.status_code == 204

    @patch("monitor_ui.routers.tone.mongodb_delete_tone_profile")
    def test_delete_profile_not_found(self, mock_delete: Mock) -> None:
        mock_delete.return_value = False
        resp = client.delete(f"{BASE}/profiles/{uuid4()}")
        assert resp.status_code == 404

    @patch("monitor_ui.routers.tone.mongodb_delete_tone_profile")
    def test_delete_builtin_forbidden(self, mock_delete: Mock) -> None:
        mock_delete.side_effect = ValueError("Cannot delete built-in")
        resp = client.delete(f"{BASE}/profiles/{uuid4()}")
        assert resp.status_code == 403


class TestListToneLibraries:
    @patch("monitor_ui.routers.tone.mongodb_list_tone_libraries")
    def test_list_libraries(self, mock_list: Mock) -> None:
        mock_list.return_value = ToneLibraryListResponse(
            libraries=[], total=0, page=1, page_size=50
        )
        resp = client.get(f"{BASE}/libraries")
        assert resp.status_code == 200


class TestGetDefaultToneLibrary:
    @patch("monitor_ui.routers.tone.mongodb_get_default_tone_library")
    def test_get_default_library(self, mock_get: Mock) -> None:
        lid = uuid4()
        mock_get.return_value = ToneLibraryResponse(
            library_id=lid,
            name="Default",
            description="",
            tone_profile_ids=[],
            pack_id=None,
            universe_id=None,
            priority=100,
            is_default=True,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.get(f"{BASE}/libraries/default")
        assert resp.status_code == 200
        assert resp.json()["is_default"] is True

    @patch("monitor_ui.routers.tone.mongodb_get_default_tone_library")
    def test_get_default_library_not_found(self, mock_get: Mock) -> None:
        mock_get.return_value = None
        resp = client.get(f"{BASE}/libraries/default")
        assert resp.status_code == 404


class TestGetToneLibrary:
    @patch("monitor_ui.routers.tone.mongodb_get_tone_library")
    def test_get_library_found(self, mock_get: Mock) -> None:
        lid = uuid4()
        mock_get.return_value = ToneLibraryResponse(
            library_id=lid,
            name="Cyberpunk",
            description="",
            tone_profile_ids=[],
            pack_id=None,
            universe_id=None,
            priority=100,
            is_default=False,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.get(f"{BASE}/libraries/{lid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Cyberpunk"

    @patch("monitor_ui.routers.tone.mongodb_get_tone_library")
    def test_get_library_not_found(self, mock_get: Mock) -> None:
        mock_get.return_value = None
        resp = client.get(f"{BASE}/libraries/{uuid4()}")
        assert resp.status_code == 404


class TestCreateToneLibrary:
    @patch("monitor_ui.routers.tone.mongodb_create_tone_library")
    def test_create_library(self, mock_create: Mock) -> None:
        lid = uuid4()
        mock_create.return_value = ToneLibraryResponse(
            library_id=lid,
            name="Cyberpunk",
            description="",
            tone_profile_ids=[uuid4()],
            pack_id=None,
            universe_id=None,
            priority=150,
            is_default=False,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.post(
            f"{BASE}/libraries",
            json={
                "name": "Cyberpunk",
                "tone_profile_ids": [str(uuid4())],
                "priority": 150,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Cyberpunk"


class TestUpdateToneLibrary:
    @patch("monitor_ui.routers.tone.mongodb_update_tone_library")
    def test_update_library_success(self, mock_update: Mock) -> None:
        lid = uuid4()
        mock_update.return_value = ToneLibraryResponse(
            library_id=lid,
            name="Updated",
            description="",
            tone_profile_ids=[],
            pack_id=None,
            universe_id=None,
            priority=100,
            is_default=False,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.put(f"{BASE}/libraries/{lid}", json={"name": "Updated"})
        assert resp.status_code == 200

    @patch("monitor_ui.routers.tone.mongodb_update_tone_library")
    def test_update_library_not_found(self, mock_update: Mock) -> None:
        mock_update.return_value = None
        resp = client.put(f"{BASE}/libraries/{uuid4()}", json={"name": "x"})
        assert resp.status_code == 404


class TestDeleteToneLibrary:
    @patch("monitor_ui.routers.tone.mongodb_delete_tone_library")
    def test_delete_library_success(self, mock_delete: Mock) -> None:
        mock_delete.return_value = True
        resp = client.delete(f"{BASE}/libraries/{uuid4()}")
        assert resp.status_code == 204

    @patch("monitor_ui.routers.tone.mongodb_delete_tone_library")
    def test_delete_default_forbidden(self, mock_delete: Mock) -> None:
        mock_delete.side_effect = ValueError("Cannot delete default")
        resp = client.delete(f"{BASE}/libraries/{uuid4()}")
        assert resp.status_code == 403


class TestListTagDefinitions:
    @patch("monitor_ui.routers.tone.mongodb_list_tag_definitions")
    def test_list_tags(self, mock_list: Mock) -> None:
        mock_list.return_value = TagDefinitionListResponse(
            tags=[], total=0, page=1, page_size=50
        )
        resp = client.get(f"{BASE}/tags")
        assert resp.status_code == 200


class TestSuggestTags:
    @patch("monitor_ui.routers.tone.mongodb_suggest_tags")
    def test_suggest_tags(self, mock_suggest: Mock) -> None:
        mock_suggest.return_value = TagSuggestionResponse(
            suggestions=[
                TagDefinitionResponse(
                    tag="grim",
                    category=TagCategory.TONE,
                    synonyms=["dark"],
                    description="Dark tone",
                    example_tones=[],
                    pack_id=None,
                    is_builtin=True,
                    created_at=datetime.now(timezone.utc),
                ),
                TagDefinitionResponse(
                    tag="gritty",
                    category=TagCategory.TONE,
                    synonyms=[],
                    description="Gritty tone",
                    example_tones=[],
                    pack_id=None,
                    is_builtin=True,
                    created_at=datetime.now(timezone.utc),
                ),
            ],
            partial="grim",
            total_found=2,
        )
        resp = client.get(f"{BASE}/tags/suggest?partial=grim")
        assert resp.status_code == 200
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) == 2
        assert suggestions[0]["tag"] == "grim"

    def test_suggest_tags_requires_min_length(self) -> None:
        resp = client.get(f"{BASE}/tags/suggest?partial=")
        assert resp.status_code == 422


class TestGetTagDefinition:
    @patch("monitor_ui.routers.tone.mongodb_get_tag_definition")
    def test_get_tag_found(self, mock_get: Mock) -> None:
        mock_get.return_value = TagDefinitionResponse(
            tag="grim",
            category=TagCategory.TONE,
            synonyms=["dark"],
            description="Dark tone",
            example_tones=[],
            pack_id=None,
            is_builtin=True,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.get(f"{BASE}/tags/grim")
        assert resp.status_code == 200
        assert resp.json()["tag"] == "grim"

    @patch("monitor_ui.routers.tone.mongodb_get_tag_definition")
    def test_get_tag_not_found(self, mock_get: Mock) -> None:
        mock_get.return_value = None
        resp = client.get(f"{BASE}/tags/nonexistent")
        assert resp.status_code == 404


class TestCreateTagDefinition:
    @patch("monitor_ui.routers.tone.mongodb_create_tag_definition")
    def test_create_tag(self, mock_create: Mock) -> None:
        mock_create.return_value = TagDefinitionResponse(
            tag="cyberpunk",
            category=TagCategory.STYLE,
            synonyms=["futuristic"],
            description="Futuristic",
            example_tones=[],
            pack_id=None,
            is_builtin=False,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.post(
            f"{BASE}/tags",
            json={
                "tag": "cyberpunk",
                "category": "style",
                "synonyms": ["futuristic"],
                "description": "Futuristic",
                "example_tones": [],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["tag"] == "cyberpunk"


class TestUpdateTagDefinition:
    @patch("monitor_ui.routers.tone.mongodb_update_tag_definition")
    def test_update_tag_success(self, mock_update: Mock) -> None:
        mock_update.return_value = TagDefinitionResponse(
            tag="grim",
            category=TagCategory.TONE,
            synonyms=["dark", "somber"],
            description="Dark tone",
            example_tones=[],
            pack_id=None,
            is_builtin=True,
            created_at=datetime.now(timezone.utc),
        )
        resp = client.put(f"{BASE}/tags/grim", json={"synonyms": ["dark", "somber"]})
        assert resp.status_code == 200
        assert "somber" in resp.json()["synonyms"]

    @patch("monitor_ui.routers.tone.mongodb_update_tag_definition")
    def test_update_tag_not_found(self, mock_update: Mock) -> None:
        mock_update.return_value = None
        resp = client.put(f"{BASE}/tags/nonexistent", json={"synonyms": ["x"]})
        assert resp.status_code == 404


class TestDeleteTagDefinition:
    @patch("monitor_ui.routers.tone.mongodb_delete_tag_definition")
    def test_delete_tag_success(self, mock_delete: Mock) -> None:
        mock_delete.return_value = True
        resp = client.delete(f"{BASE}/tags/custom_tag")
        assert resp.status_code == 204

    @patch("monitor_ui.routers.tone.mongodb_delete_tag_definition")
    def test_delete_builtin_forbidden(self, mock_delete: Mock) -> None:
        mock_delete.side_effect = ValueError("Cannot delete built-in")
        resp = client.delete(f"{BASE}/tags/grim")
        assert resp.status_code == 403

    @patch("monitor_ui.routers.tone.mongodb_delete_tag_definition")
    def test_delete_tag_not_found(self, mock_delete: Mock) -> None:
        mock_delete.return_value = False
        resp = client.delete(f"{BASE}/tags/nonexistent")
        assert resp.status_code == 404

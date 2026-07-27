"""Tests for ToneProfile CRUD operations in MongoDB tools."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.tone_profiles import (
    ToneProfileCreate,
    ToneProfileListResponse,
    ToneProfileUpdate,
)
from monitor_data.tools.mongodb_tools.tone_profiles import (
    mongodb_create_tone_profile,
    mongodb_delete_tone_profile,
    mongodb_get_tone_profile,
    mongodb_get_tone_profiles_batch,
    mongodb_list_tone_profiles,
    mongodb_update_tone_profile,
)


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_create_tone_profile_returns_response(mock_mongo: Mock) -> None:
    """Test that creating a ToneProfile returns a ToneProfileResponse."""
    pack_id = uuid4()

    mock_collection = Mock()
    mock_collection.insert_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_create_tone_profile(
        ToneProfileCreate(
            name="grim_noir",
            description="Grim, noir detective style",
            instruction="Terse, industrial, cosmic-dread. Short declarative sentences.",
            trigger_tags=["grim", "noir"],
            category="narrative",
            language="en",
            pack_id=pack_id,
            is_builtin=False,
            example_output="Rain slicked the pavement like oil...",
        )
    )

    assert result.name == "grim_noir"
    assert result.instruction == "Terse, industrial, cosmic-dread. Short declarative sentences."
    assert result.trigger_tags == ["grim", "noir"]
    assert result.pack_id == pack_id
    assert not result.is_builtin
    assert result.profile_id is not None  # Should be auto-generated
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_get_tone_profile_found(mock_mongo: Mock) -> None:
    """Test retrieving a ToneProfile that exists."""
    profile_id = uuid4()
    pack_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = {
        "profile_id": str(profile_id),
        "name": "grim_noir",
        "description": "Grim, noir detective style",
        "instruction": "Terse, industrial, cosmic-dread.",
        "trigger_tags": ["grim", "noir"],
        "category": "narrative",
        "language": "en",
        "pack_id": str(pack_id),
        "is_builtin": False,
        "example_output": "Rain slicked the pavement...",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": None,
    }
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_tone_profile(profile_id)

    assert result is not None
    assert result.profile_id == profile_id
    assert result.name == "grim_noir"
    assert result.trigger_tags == ["grim", "noir"]


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_get_tone_profile_not_found(mock_mongo: Mock) -> None:
    """Test retrieving a ToneProfile that doesn't exist."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_tone_profile(profile_id)

    assert result is None


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_list_tone_profiles_filters_by_pack(mock_mongo: Mock) -> None:
    """Test listing ToneProfiles with pack filter."""
    pack_id = uuid4()
    profile_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [  # Mock cursor iteration
        {
            "profile_id": str(profile_id),
            "name": "cyberpunk_gritty",
            "description": "Cyberpunk style",
            "instruction": "Gritty, street-level...",
            "trigger_tags": ["cyberpunk", "gritty"],
            "category": "genre",
            "language": "en",
            "pack_id": str(pack_id),
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_profiles(pack_id=pack_id, limit=10, offset=0)

    assert isinstance(result, ToneProfileListResponse)
    assert result.total == 1
    assert len(result.profiles) == 1
    assert result.profiles[0].pack_id == pack_id


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_list_tone_profiles_empty_results(mock_mongo: Mock) -> None:
    """Test listing ToneProfiles with no matching results."""
    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = []  # Empty results

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 0
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_profiles(category="nonexistent", limit=10, offset=0)

    assert isinstance(result, ToneProfileListResponse)
    assert result.total == 0
    assert len(result.profiles) == 0


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_list_tone_profiles_filters_by_category(mock_mongo: Mock) -> None:
    """Test listing ToneProfiles with category filter."""
    profile_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "profile_id": str(profile_id),
            "name": "cyberpunk_gritty",
            "description": "Cyberpunk style",
            "instruction": "Gritty, street-level...",
            "trigger_tags": ["cyberpunk", "gritty"],
            "category": "genre",  # Filtered by category
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_profiles(category="genre", limit=10, offset=0)

    assert isinstance(result, ToneProfileListResponse)
    assert result.total == 1
    assert len(result.profiles) == 1
    assert result.profiles[0].category == "genre"


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_list_tone_profiles_with_pagination(mock_mongo: Mock) -> None:
    """Test listing ToneProfiles with pagination."""
    profile_id_1 = uuid4()
    profile_id_2 = uuid4()

    docs = [
        {
            "profile_id": str(profile_id_1),
            "name": "profile_1",
            "description": "First profile",
            "instruction": "Instruction 1",
            "trigger_tags": ["tag1"],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": None,
        },
        {
            "profile_id": str(profile_id_2),
            "name": "profile_2",
            "description": "Second profile",
            "instruction": "Instruction 2",
            "trigger_tags": ["tag2"],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": None,
        },
    ]

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = docs

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 5  # Total 5 profiles
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_profiles(limit=2, offset=2)

    assert isinstance(result, ToneProfileListResponse)
    assert result.total == 5
    assert len(result.profiles) == 2
    assert result.page == 2  # offset 2, limit 2 => page 2
    assert result.page_size == 2


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_success(mock_mongo: Mock) -> None:
    """Test updating a ToneProfile."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": False},
        {
            "profile_id": str(profile_id),
            "name": "grim_noir_updated",
            "description": "Updated description",
            "instruction": "Updated instruction",
            "trigger_tags": ["grim"],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(
        profile_id,
        ToneProfileUpdate(description="Updated description", instruction="Updated instruction"),
    )

    assert result is not None
    assert result.description == "Updated description"
    assert result.instruction == "Updated instruction"


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_builtin_profile_protects_name(mock_mongo: Mock) -> None:
    """Test that updating a built-in profile protects the name field."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": True},
        {
            "profile_id": str(profile_id),
            "name": "original_name",  # Name should NOT change
            "description": "Updated description",
            "instruction": "Original instruction",
            "trigger_tags": [],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": True,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(
        profile_id,
        ToneProfileUpdate(name="new_name", description="Updated description"),
    )

    assert result is not None
    # Name should NOT be updated for built-in profiles
    assert result.name == "original_name"


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_not_found_returns_none(mock_mongo: Mock) -> None:
    """Test updating a ToneProfile that doesn't exist returns None."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = None  # Profile not found

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(profile_id, ToneProfileUpdate(description="New description"))

    assert result is None
    mock_collection.find_one.assert_called_once_with({"profile_id": str(profile_id)})
    mock_collection.update_one.assert_not_called()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_partial_fields(mock_mongo: Mock) -> None:
    """Test updating only some fields of a ToneProfile."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": False},
        {
            "profile_id": str(profile_id),
            "name": "original_name",
            "description": "Updated description",
            "instruction": "Original instruction",
            "trigger_tags": ["original_tag"],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(profile_id, ToneProfileUpdate(description="Updated description"))

    assert result is not None
    assert result.description == "Updated description"
    assert result.instruction == "Original instruction"
    assert result.trigger_tags == ["original_tag"]  # Should not change


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_delete_tone_profile_success(mock_mongo: Mock) -> None:
    """Test deleting a ToneProfile."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = {"profile_id": str(profile_id), "is_builtin": False}
    mock_collection.delete_one.return_value = Mock(deleted_count=1)
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_delete_tone_profile(profile_id)

    assert result is True
    mock_collection.delete_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_delete_builtin_profile_raises_error(mock_mongo: Mock) -> None:
    """Test that deleting a built-in profile raises ValueError."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = {"profile_id": str(profile_id), "is_builtin": True}
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    with pytest.raises(ValueError, match="Cannot delete built-in ToneProfile"):
        mongodb_delete_tone_profile(profile_id)


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_get_tone_profiles_batch_empty(mock_mongo: Mock) -> None:
    """Test batch retrieval with empty list."""
    result = mongodb_get_tone_profiles_batch([])

    assert result == []


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_get_tone_profiles_batch_multiple(mock_mongo: Mock) -> None:
    """Test batch retrieval of multiple ToneProfiles."""
    profile_id_1 = uuid4()
    profile_id_2 = uuid4()

    mock_cursor = Mock()
    mock_cursor.__iter__ = Mock(
        return_value=iter(
            [
                {
                    "profile_id": str(profile_id_1),
                    "name": "profile_1",
                    "description": "First profile",
                    "instruction": "Instruction 1",
                    "trigger_tags": ["tag1"],
                    "category": "narrative",
                    "language": "en",
                    "pack_id": None,
                    "is_builtin": False,
                    "example_output": None,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": None,
                },
                {
                    "profile_id": str(profile_id_2),
                    "name": "profile_2",
                    "description": "Second profile",
                    "instruction": "Instruction 2",
                    "trigger_tags": ["tag2"],
                    "category": "narrative",
                    "language": "en",
                    "pack_id": None,
                    "is_builtin": False,
                    "example_output": None,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": None,
                },
            ]
        )
    )

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_tone_profiles_batch([profile_id_1, profile_id_2])

    assert len(result) == 2
    assert result[0].profile_id == profile_id_1
    assert result[1].profile_id == profile_id_2


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_trigger_tags(mock_mongo: Mock) -> None:
    """Test updating tone_profile trigger_tags."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": False},
        {
            "profile_id": str(profile_id),
            "name": "original_name",
            "description": "Original description",
            "instruction": "Original instruction",
            "trigger_tags": ["new_tag_1", "new_tag_2", "new_tag_3"],  # Updated tags
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(
        profile_id,
        ToneProfileUpdate(trigger_tags=["new_tag_1", "new_tag_2", "new_tag_3"]),
    )

    assert result is not None
    assert result.trigger_tags == ["new_tag_1", "new_tag_2", "new_tag_3"]
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_category(mock_mongo: Mock) -> None:
    """Test updating tone_profile category."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": False},
        {
            "profile_id": str(profile_id),
            "name": "original_name",
            "description": "Original description",
            "instruction": "Original instruction",
            "trigger_tags": [],
            "category": "dialogue",  # Changed from narrative to dialogue
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(
        profile_id,
        ToneProfileUpdate(category="dialogue"),
    )

    assert result is not None
    assert result.category == "dialogue"
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_language(mock_mongo: Mock) -> None:
    """Test updating tone_profile language."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": False},
        {
            "profile_id": str(profile_id),
            "name": "original_name",
            "description": "Original description",
            "instruction": "Original instruction",
            "trigger_tags": [],
            "category": "narrative",
            "language": "es",  # Changed from en to es
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(
        profile_id,
        ToneProfileUpdate(language="es"),
    )

    assert result is not None
    assert result.language == "es"
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_list_tone_profiles_filters_by_language(mock_mongo: Mock) -> None:
    """Test listing ToneProfiles filtered by language."""
    profile_id = uuid4()

    docs = [
        {
            "profile_id": str(profile_id),
            "name": "profile_1",
            "description": "Spanish profile",
            "instruction": "Instruction 1",
            "trigger_tags": [],
            "category": "narrative",
            "language": "es",  # Spanish
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": None,
        },
    ]

    mock_cursor = Mock()
    mock_cursor.__iter__ = Mock(return_value=iter(docs))
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_profiles(language="es")

    assert result.total == 1
    assert len(result.profiles) == 1
    assert result.profiles[0].language == "es"
    mock_collection.find.assert_called_once_with({"language": "es"})


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_list_tone_profiles_filters_by_is_builtin(mock_mongo: Mock) -> None:
    """Test listing ToneProfiles filtered by is_builtin flag."""
    profile_id_1 = uuid4()
    profile_id_2 = uuid4()

    docs = [
        {
            "profile_id": str(profile_id_1),
            "name": "builtin_profile",
            "description": "Built-in profile",
            "instruction": "Instruction 1",
            "trigger_tags": [],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": True,  # Built-in
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": None,
        },
        {
            "profile_id": str(profile_id_2),
            "name": "custom_profile",
            "description": "Custom profile",
            "instruction": "Instruction 2",
            "trigger_tags": [],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,  # Custom
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": None,
        },
    ]

    mock_cursor = Mock()
    mock_cursor.__iter__ = Mock(return_value=iter(docs))
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 2
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_profiles(is_builtin=True)

    assert result.total == 2
    assert len(result.profiles) == 2
    mock_collection.find.assert_called_once_with({"is_builtin": True})


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_create_tone_profile_with_minimal_fields(mock_mongo: Mock) -> None:
    """Test creating a ToneProfile with only required fields."""
    pack_id = uuid4()

    mock_collection = Mock()
    mock_collection.insert_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_create_tone_profile(
        ToneProfileCreate(
            name="minimal_tone",
            description="Minimal description",
            instruction="Minimal instruction",
            pack_id=pack_id,
        )
    )

    assert result.name == "minimal_tone"
    assert result.description == "Minimal description"
    assert result.instruction == "Minimal instruction"
    # Check default values
    assert result.trigger_tags == []
    assert result.category == "narrative"
    assert result.language == "en"
    assert result.is_builtin is False
    assert result.example_output is None
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_name_only(mock_mongo: Mock) -> None:
    """Test updating only the name field of a ToneProfile."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": False},
        {
            "profile_id": str(profile_id),
            "name": "new_name",
            "description": "Original description",
            "instruction": "Original instruction",
            "trigger_tags": [],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(
        profile_id,
        ToneProfileUpdate(name="new_name"),
    )

    assert result is not None
    assert result.name == "new_name"
    assert result.description == "Original description"
    assert result.instruction == "Original instruction"
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_description_only(mock_mongo: Mock) -> None:
    """Test updating only the description field of a ToneProfile."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": False},
        {
            "profile_id": str(profile_id),
            "name": "original_name",
            "description": "Updated description",
            "instruction": "Original instruction",
            "trigger_tags": [],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(
        profile_id,
        ToneProfileUpdate(description="Updated description"),
    )

    assert result is not None
    assert result.name == "original_name"
    assert result.description == "Updated description"
    assert result.instruction == "Original instruction"
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_update_tone_profile_example_output(mock_mongo: Mock) -> None:
    """Test updating the example_output field of a ToneProfile."""
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        {"profile_id": str(profile_id), "is_builtin": False},
        {
            "profile_id": str(profile_id),
            "name": "original_name",
            "description": "Original description",
            "instruction": "Original instruction",
            "trigger_tags": [],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": False,
            "example_output": "New example output for LLM training",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_profile(
        profile_id,
        ToneProfileUpdate(example_output="New example output for LLM training"),
    )

    assert result is not None
    assert result.example_output == "New example output for LLM training"
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_profiles.get_mongodb_client")
def test_list_tone_profiles_with_multiple_filters(mock_mongo: Mock) -> None:
    """Test listing ToneProfiles with multiple filters (category + language + is_builtin)."""
    profile_id = uuid4()
    pack_id = uuid4()

    docs = [
        {
            "profile_id": str(profile_id),
            "name": "spanish_narrative_builtin",
            "description": "Spanish built-in narrative tone",
            "instruction": "Instruction in Spanish",
            "trigger_tags": [],
            "category": "narrative",
            "language": "es",
            "pack_id": str(pack_id),
            "is_builtin": True,
            "example_output": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": None,
        },
    ]

    mock_cursor = Mock()
    mock_cursor.__iter__ = Mock(return_value=iter(docs))
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_profiles(
        category="narrative",
        language="es",
        is_builtin=True,
    )

    assert result.total == 1
    assert len(result.profiles) == 1
    assert result.profiles[0].category == "narrative"
    assert result.profiles[0].language == "es"
    assert result.profiles[0].is_builtin is True
    mock_collection.find.assert_called_once_with({"category": "narrative", "language": "es", "is_builtin": True})

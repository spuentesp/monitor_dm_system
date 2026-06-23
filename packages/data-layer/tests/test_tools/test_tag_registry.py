"""Tests for TagRegistry CRUD operations in MongoDB tools."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.tag_registry import (
    TagDefinitionCreate,
    TagDefinitionUpdate,
    TagCategory,
    TagDefinitionListResponse,
    TagSuggestionRequest,
    TagSuggestionResponse,
)
from monitor_data.tools.mongodb_tools.tag_registry import (
    mongodb_create_tag_definition,
    mongodb_get_tag_definition,
    mongodb_normalize_tag,
    mongodb_list_tag_definitions,
    mongodb_update_tag_definition,
    mongodb_delete_tag_definition,
    mongodb_suggest_tags,
)


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_create_tag_definition_returns_response(mock_mongo: Mock) -> None:
    """Test that creating a TagDefinition returns a TagDefinitionResponse."""
    pack_id = uuid4()
    tone_id = uuid4()

    mock_collection = Mock()
    mock_collection.insert_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_create_tag_definition(
        TagDefinitionCreate(
            tag="grim",
            category=TagCategory.TONE,
            synonyms=["dark", "bleak", "gritty"],
            description="Dark, serious tone",
            example_tones=[tone_id],
            pack_id=pack_id,
            is_builtin=False,
        )
    )

    assert result.tag == "grim"
    assert result.category == TagCategory.TONE
    assert result.synonyms == ["dark", "bleak", "gritty"]
    assert result.description == "Dark, serious tone"
    assert result.pack_id == pack_id
    assert not result.is_builtin
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_create_tag_definition_normalizes_tag(mock_mongo: Mock) -> None:
    """Test that tag names are normalized to lowercase."""
    mock_collection = Mock()
    mock_collection.insert_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    mongodb_create_tag_definition(
        TagDefinitionCreate(
            tag="GRIM_NOIR",  # Mixed case
            category=TagCategory.TONE,
        )
    )

    # Should be normalized to lowercase
    mock_collection.insert_one.assert_called_once()
    call_args = mock_collection.insert_one.call_args[0][0]
    assert call_args["tag"] == "grim_noir"


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_get_tag_definition_found(mock_mongo: Mock) -> None:
    """Test retrieving a TagDefinition that exists."""
    tone_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = {
        "tag": "grim",
        "category": "tone",
        "synonyms": ["dark", "bleak"],
        "description": "Dark tone",
        "example_tones": [str(tone_id)],
        "pack_id": None,
        "is_builtin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
    }
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_tag_definition("grim")

    assert result is not None
    assert result.tag == "grim"
    assert result.category == TagCategory.TONE
    assert "dark" in result.synonyms


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_get_tag_definition_not_found(mock_mongo: Mock) -> None:
    """Test retrieving a TagDefinition that doesn't exist."""
    mock_collection = Mock()
    mock_collection.find_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_tag_definition("nonexistent")

    assert result is None


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_normalize_tag_canonical(mock_mongo: Mock) -> None:
    """Test normalizing a tag that is already canonical."""
    mock_collection = Mock()
    mock_collection.find_one.return_value = {"tag": "grim"}  # Tag exists as canonical
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_normalize_tag("grim")

    assert result == "grim"


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_normalize_tag_synonym(mock_mongo: Mock) -> None:
    """Test normalizing a tag that is a synonym."""
    mock_collection = Mock()
    # First call: not a canonical tag
    # Second call: found as a synonym
    mock_collection.find_one.side_effect = [
        None,
        {"tag": "grim", "synonyms": ["dark", "bleak"]},
    ]
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_normalize_tag("dark")

    assert result == "grim"


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_normalize_tag_no_match(mock_mongo: Mock) -> None:
    """Test normalizing a tag with no canonical or synonym match."""
    mock_collection = Mock()
    mock_collection.find_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_normalize_tag("custom_tag")

    assert result == "custom_tag"


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_list_tag_definitions_filters_by_category(mock_mongo: Mock) -> None:
    """Test listing TagDefinitions with category filter."""
    tone_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "tag": "grim",
            "category": "tone",
            "synonyms": ["dark"],
            "description": "Dark tone",
            "example_tones": [str(tone_id)],
            "pack_id": None,
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tag_definitions(category=TagCategory.TONE, limit=10, offset=0)

    assert isinstance(result, TagDefinitionListResponse)
    assert result.total == 1
    assert len(result.tags) == 1
    assert result.tags[0].category == TagCategory.TONE


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_list_tag_definitions_filters_by_pack_id(mock_mongo: Mock) -> None:
    """Test listing TagDefinitions with pack_id filter."""
    pack_id = uuid4()
    tone_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "tag": "grim",
            "category": "tone",
            "synonyms": ["dark"],
            "description": "Dark tone",
            "example_tones": [str(tone_id)],
            "pack_id": str(pack_id),
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tag_definitions(pack_id=pack_id, limit=10, offset=0)

    assert isinstance(result, TagDefinitionListResponse)
    assert result.total == 1
    assert len(result.tags) == 1
    assert result.tags[0].pack_id == pack_id


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_list_tag_definitions_empty_results(mock_mongo: Mock) -> None:
    """Test listing TagDefinitions with no matches."""
    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = []

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 0
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tag_definitions(category=TagCategory.CONCEPT, limit=10, offset=0)

    assert isinstance(result, TagDefinitionListResponse)
    assert result.total == 0
    assert len(result.tags) == 0


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_list_tag_definitions_with_pagination(mock_mongo: Mock) -> None:
    """Test listing TagDefinitions with pagination."""
    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "tag": "dark",
            "category": "tone",
            "synonyms": [],
            "description": "Dark",
            "example_tones": [],
            "pack_id": None,
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
        {
            "tag": "gritty",
            "category": "tone",
            "synonyms": [],
            "description": "Gritty",
            "example_tones": [],
            "pack_id": None,
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 5  # Total of 5 tags
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tag_definitions(limit=2, offset=2)  # Page 2 (skip 2, limit 2)

    assert isinstance(result, TagDefinitionListResponse)
    assert result.total == 5
    assert len(result.tags) == 2
    assert result.page == 2
    assert result.page_size == 2


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_update_tag_definition_success(mock_mongo: Mock) -> None:
    """Test updating a TagDefinition."""
    tone_id = uuid4()

    updated_doc = {
        "tag": "grim",
        "category": "tone",
        "synonyms": ["dark", "bleak", "gritty"],  # Updated
        "description": "Updated description",
        "example_tones": [str(tone_id)],
        "pack_id": None,
        "is_builtin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = updated_doc  # Always return the updated doc

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tag_definition(
        "grim",
        TagDefinitionUpdate(
            synonyms=["dark", "bleak", "gritty"], description="Updated description"
        ),
    )

    assert result is not None
    assert result.description == "Updated description"
    assert "gritty" in result.synonyms
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_update_tag_definition_partial_fields(mock_mongo: Mock) -> None:
    """Test updating only some fields of a TagDefinition (partial update)."""
    tone_id = uuid4()

    updated_doc = {
        "tag": "grim",
        "category": "tone",
        "synonyms": ["dark", "bleak"],  # Unchanged
        "description": "Only description updated",  # Updated
        "example_tones": [str(tone_id)],
        "pack_id": None,
        "is_builtin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = updated_doc

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tag_definition(
        "grim",
        TagDefinitionUpdate(description="Only description updated"),  # Only update description
    )

    assert result is not None
    assert result.description == "Only description updated"
    assert result.synonyms == ["dark", "bleak"]  # Should remain unchanged
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_delete_tag_definition_success(mock_mongo: Mock) -> None:
    """Test deleting a TagDefinition."""
    mock_collection = Mock()
    mock_collection.find_one.return_value = {"tag": "grim", "is_builtin": False}
    mock_collection.delete_one.return_value = Mock(deleted_count=1)
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_delete_tag_definition("grim")

    assert result is True
    mock_collection.delete_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_delete_tag_definition_not_found(mock_mongo: Mock) -> None:
    """Test deleting a TagDefinition that doesn't exist returns False."""
    mock_collection = Mock()
    mock_collection.find_one.return_value = None  # Tag not found
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_delete_tag_definition("nonexistent")

    assert result is False
    mock_collection.delete_one.assert_not_called()


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_delete_builtin_tag_raises_error(mock_mongo: Mock) -> None:
    """Test that deleting a built-in tag raises ValueError."""
    mock_collection = Mock()
    mock_collection.find_one.return_value = {"tag": "grim", "is_builtin": True}
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    with pytest.raises(ValueError, match="Cannot delete built-in TagDefinition"):
        mongodb_delete_tag_definition("grim")


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_suggest_tags_case_insensitive(mock_mongo: Mock) -> None:
    """Test tag suggestions with case-insensitive prefix match."""
    tone_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "tag": "grim",
            "category": "tone",
            "synonyms": ["dark"],
            "description": "Dark tone",
            "example_tones": [str(tone_id)],
            "pack_id": None,
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
        {
            "tag": "grim_noir",
            "category": "tone",
            "synonyms": [],
            "description": "Grim noir style",
            "example_tones": [],
            "pack_id": None,
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 2
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_suggest_tags(
        TagSuggestionRequest(partial="GRIM", category=TagCategory.TONE, limit=10)
    )

    assert isinstance(result, TagSuggestionResponse)
    assert result.partial == "GRIM"
    assert result.total_found == 2
    assert len(result.suggestions) == 2
    assert result.suggestions[0].tag == "grim"
    assert result.suggestions[1].tag == "grim_noir"


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_suggest_tags_empty_result(mock_mongo: Mock) -> None:
    """Test tag suggestions with no matches."""
    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = []

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 0
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_suggest_tags(TagSuggestionRequest(partial="nonexistent", limit=10))

    assert isinstance(result, TagSuggestionResponse)
    assert result.total_found == 0
    assert len(result.suggestions) == 0


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_normalize_tags_batch(mock_mongo: Mock) -> None:
    """Test normalizing multiple tags at once."""
    mock_collection = Mock()

    # Mock behavior for multiple calls:
    # 1. "dark" (synonym of "grim")
    # 2. "grim" (canonical)
    # 3. "custom" (no match)
    mock_collection.find_one.side_effect = [
        None,
        {"tag": "grim"},  # call for "dark" -> None then find by synonym
        {"tag": "grim"},  # call for "grim" -> find by canonical
        None,
        None,  # call for "custom" -> None then None
    ]

    # Actually mongodb_normalize_tag does 1 or 2 queries.
    # Let's refine the side_effect to match the implementation:
    # tag 1 ("dark"): canonical? (None) -> synonym? ({"tag": "grim"})
    # tag 2 ("grim"): canonical? ({"tag": "grim"})
    # tag 3 ("custom"): canonical? (None) -> synonym? (None)

    mock_collection.find_one.side_effect = [
        None,
        {"tag": "grim"},  # "dark"
        {"tag": "grim"},  # "grim"
        None,
        None,  # "custom"
    ]

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    from monitor_data.tools.mongodb_tools.tag_registry import mongodb_normalize_tags

    result = mongodb_normalize_tags(["dark", "grim", "custom"])

    # Result should be sorted and deduplicated: ["custom", "grim"]
    assert result == ["custom", "grim"]


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_list_tag_definitions_filters_by_is_builtin(mock_mongo: Mock) -> None:
    """Test listing TagDefinitions with is_builtin filter."""
    tone_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "tag": "dark",
            "category": "tone",
            "synonyms": [],
            "description": "Built-in dark tone",
            "example_tones": [str(tone_id)],
            "pack_id": None,
            "is_builtin": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tag_definitions(is_builtin=True, limit=10, offset=0)

    assert isinstance(result, TagDefinitionListResponse)
    assert result.total == 1
    assert len(result.tags) == 1
    assert result.tags[0].is_builtin is True


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_list_tag_definitions_with_multiple_filters(mock_mongo: Mock) -> None:
    """Test listing TagDefinitions with multiple filters (category + pack_id + is_builtin)."""
    pack_id = uuid4()
    tone_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "tag": "custom_grim",
            "category": "tone",
            "synonyms": ["dark"],
            "description": "Custom grim tone",
            "example_tones": [str(tone_id)],
            "pack_id": str(pack_id),
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tag_definitions(
        category=TagCategory.TONE, pack_id=pack_id, is_builtin=False, limit=10, offset=0
    )

    assert isinstance(result, TagDefinitionListResponse)
    assert result.total == 1
    assert len(result.tags) == 1
    assert result.tags[0].category == TagCategory.TONE
    assert result.tags[0].pack_id == pack_id
    assert result.tags[0].is_builtin is False


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_update_tag_definition_example_tones_only(mock_mongo: Mock) -> None:
    """Test updating only example_tones field of a TagDefinition."""
    tone_id1 = uuid4()
    tone_id2 = uuid4()

    updated_doc = {
        "tag": "grim",
        "category": "tone",
        "synonyms": ["dark", "bleak"],  # Unchanged
        "description": "Dark tone",  # Unchanged
        "example_tones": [str(tone_id1), str(tone_id2)],  # Updated
        "pack_id": None,
        "is_builtin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = updated_doc

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tag_definition(
        "grim",
        TagDefinitionUpdate(example_tones=[tone_id1, tone_id2]),  # Only update example_tones
    )

    assert result is not None
    assert len(result.example_tones) == 2
    assert tone_id1 in result.example_tones
    assert tone_id2 in result.example_tones
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_suggest_tags_with_category_filter(mock_mongo: Mock) -> None:
    """Test tag suggestions filtered by category."""

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "tag": "dark_theme",
            "category": "theme",
            "synonyms": [],
            "description": "Dark theme",
            "example_tones": [],
            "pack_id": None,
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_suggest_tags(
        TagSuggestionRequest(partial="dark", category=TagCategory.THEME, limit=10)
    )

    assert isinstance(result, TagSuggestionResponse)
    assert result.partial == "dark"
    assert result.total_found == 1
    assert len(result.suggestions) == 1
    assert result.suggestions[0].tag == "dark_theme"
    assert result.suggestions[0].category == TagCategory.THEME


@patch("monitor_data.tools.mongodb_tools.tag_registry.get_mongodb_client")
def test_suggest_tags_with_limit(mock_mongo: Mock) -> None:
    """Test tag suggestions with limit parameter."""
    tone_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor

    # Create mock for limit that returns only 2 items despite more matching
    mock_cursor.limit.return_value = [
        {
            "tag": "dark",
            "category": "tone",
            "synonyms": [],
            "description": "Dark tone",
            "example_tones": [str(tone_id)],
            "pack_id": None,
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
        {
            "tag": "dark_theme",
            "category": "theme",
            "synonyms": [],
            "description": "Dark theme",
            "example_tones": [],
            "pack_id": None,
            "is_builtin": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 5  # 5 total matches, but limit=2
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_suggest_tags(TagSuggestionRequest(partial="dark", limit=2))

    assert isinstance(result, TagSuggestionResponse)
    assert result.partial == "dark"
    assert result.total_found == 5  # Total matches
    assert len(result.suggestions) == 2  # But only 2 returned due to limit
    # Verify that limit was actually applied
    mock_cursor.limit.assert_called_once_with(2)

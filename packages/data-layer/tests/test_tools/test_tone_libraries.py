"""Tests for ToneLibrary CRUD operations in MongoDB tools."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.tone_libraries import (
    ToneLibraryCreate,
    ToneLibraryUpdate,
    ToneLibraryListResponse,
)
from monitor_data.tools.mongodb_tools.tone_libraries import (
    mongodb_create_tone_library,
    mongodb_get_tone_library,
    mongodb_get_default_tone_library,
    mongodb_list_tone_libraries,
    mongodb_update_tone_library,
    mongodb_delete_tone_library,
)


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_create_tone_library_returns_response(mock_mongo: Mock) -> None:
    """Test that creating a ToneLibrary returns a ToneLibraryResponse."""
    pack_id = uuid4()
    profile_id_1 = uuid4()
    profile_id_2 = uuid4()

    mock_collection = Mock()
    mock_collection.insert_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_create_tone_library(
        ToneLibraryCreate(
            name="Cyberpunk 2020",
            description="Tones for Cyberpunk 2020",
            tone_profile_ids=[profile_id_1, profile_id_2],
            pack_id=pack_id,
            universe_id=None,
            priority=150,
            is_default=False,
        )
    )

    assert result.name == "Cyberpunk 2020"
    assert len(result.tone_profile_ids) == 2
    assert profile_id_1 in result.tone_profile_ids
    assert result.pack_id == pack_id
    assert result.priority == 150
    assert not result.is_default
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_create_tone_library_with_optional_fields(mock_mongo: Mock) -> None:
    """Test creating a ToneLibrary with optional pack_id and universe_id."""
    pack_id = uuid4()
    universe_id = uuid4()
    profile_id_1 = uuid4()
    profile_id_2 = uuid4()

    mock_collection = Mock()
    mock_collection.insert_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_create_tone_library(
        ToneLibraryCreate(
            name="Library with Pack and Universe",
            description="Test library with all optional fields",
            tone_profile_ids=[profile_id_1, profile_id_2],
            pack_id=pack_id,
            universe_id=universe_id,
            priority=150,
            is_default=False,
        )
    )

    assert result is not None
    assert result.name == "Library with Pack and Universe"
    assert result.pack_id == pack_id
    assert result.universe_id == universe_id
    assert result.priority == 150
    assert not result.is_default
    mock_collection.insert_one.assert_called_once()
    inserted_doc = mock_collection.insert_one.call_args[0][0]
    assert inserted_doc["pack_id"] == str(pack_id)
    assert inserted_doc["universe_id"] == str(universe_id)


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_get_tone_library_found(mock_mongo: Mock) -> None:
    """Test retrieving a ToneLibrary that exists."""
    library_id = uuid4()
    pack_id = uuid4()
    profile_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = {
        "library_id": str(library_id),
        "name": "Default Library",
        "description": "Built-in tones",
        "tone_profile_ids": [str(profile_id)],
        "pack_id": str(pack_id),
        "universe_id": None,
        "priority": 100,
        "is_default": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
    }
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_tone_library(library_id)

    assert result is not None
    assert result.library_id == library_id
    assert result.name == "Default Library"
    assert result.is_default is True


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_get_tone_library_not_found(mock_mongo: Mock) -> None:
    """Test retrieving a ToneLibrary that doesn't exist."""
    library_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_tone_library(library_id)

    assert result is None


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_get_default_tone_library_found(mock_mongo: Mock) -> None:
    """Test retrieving the default ToneLibrary."""
    library_id = uuid4()
    profile_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.next.side_effect = [
        {
            "library_id": str(library_id),
            "name": "Default Library",
            "description": "Built-in tones",
            "tone_profile_ids": [str(profile_id)],
            "pack_id": None,
            "universe_id": None,
            "priority": 100,
            "is_default": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
        StopIteration,
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_default_tone_library()

    assert result is not None
    assert result.is_default is True
    assert result.priority == 100


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_get_default_tone_library_not_found(mock_mongo: Mock) -> None:
    """Test when no default ToneLibrary exists."""
    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.next.side_effect = StopIteration

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_get_default_tone_library()

    assert result is None


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_list_tone_libraries_filters_by_universe(mock_mongo: Mock) -> None:
    """Test listing ToneLibraries with universe filter."""
    universe_id = uuid4()
    library_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "library_id": str(library_id),
            "name": "Universe Library",
            "description": "Tones for this universe",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": str(universe_id),
            "priority": 100,
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_libraries(universe_id=universe_id, limit=10, offset=0)

    assert isinstance(result, ToneLibraryListResponse)
    assert result.total == 1
    assert len(result.libraries) == 1
    assert result.libraries[0].universe_id == universe_id


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_list_tone_libraries_empty_results(mock_mongo: Mock) -> None:
    """Test listing ToneLibraries with no matching results."""
    mock_cursor = Mock()
    mock_cursor.__iter__ = Mock(return_value=iter([]))
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 0
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_libraries(universe_id=uuid4(), limit=10, offset=0)

    assert isinstance(result, ToneLibraryListResponse)
    assert result.total == 0
    assert len(result.libraries) == 0
    mock_collection.find.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_list_tone_libraries_with_pagination(mock_mongo: Mock) -> None:
    """Test listing ToneLibraries with pagination."""
    library_id_1 = uuid4()
    library_id_2 = uuid4()

    docs = [
        {
            "library_id": str(library_id_1),
            "name": "Library 1",
            "description": "First library",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": None,
            "priority": 100,
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
        {
            "library_id": str(library_id_2),
            "name": "Library 2",
            "description": "Second library",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": None,
            "priority": 90,
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
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
    mock_collection.count_documents.return_value = 5  # Total 5 libraries
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_libraries(limit=2, offset=2)

    assert isinstance(result, ToneLibraryListResponse)
    assert result.total == 5
    assert len(result.libraries) == 2
    assert result.page == 2  # offset 2, limit 2 => page 2
    assert result.page_size == 2
    mock_collection.find.assert_called_once()
    mock_collection.count_documents.assert_called_once_with({})


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_update_tone_library_success(mock_mongo: Mock) -> None:
    """Test updating a ToneLibrary."""
    library_id = uuid4()
    profile_id = uuid4()

    updated_doc = {
        "library_id": str(library_id),
        "name": "Updated Library",
        "description": "Updated description",
        "tone_profile_ids": [str(profile_id)],
        "pack_id": None,
        "universe_id": None,
        "priority": 200,
        "is_default": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = updated_doc  # Always return the updated doc

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_library(
        library_id,
        ToneLibraryUpdate(name="Updated Library", description="Updated description", priority=200),
    )

    assert result is not None
    assert result.name == "Updated Library"
    assert result.description == "Updated description"
    assert result.priority == 200
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_update_tone_library_not_found_raises_error(mock_mongo: Mock) -> None:
    """Test updating a ToneLibrary that doesn't exist raises ValueError."""
    library_id = uuid4()

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = None  # Library not found after update

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    with pytest.raises(ValueError, match="not found after update"):
        mongodb_update_tone_library(library_id, ToneLibraryUpdate(name="New Name"))

    mock_collection.update_one.assert_called_once()
    mock_collection.find_one.assert_called_once_with({"library_id": str(library_id)})


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_delete_tone_library_success(mock_mongo: Mock) -> None:
    """Test deleting a ToneLibrary."""
    library_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = {"library_id": str(library_id), "is_default": False}
    mock_collection.delete_one.return_value = Mock(deleted_count=1)
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_delete_tone_library(library_id)

    assert result is True
    mock_collection.delete_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_delete_default_library_raises_error(mock_mongo: Mock) -> None:
    """Test that deleting the default library raises ValueError."""
    library_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = {"library_id": str(library_id), "is_default": True}
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    with pytest.raises(ValueError, match="Cannot delete default ToneLibrary"):
        mongodb_delete_tone_library(library_id)


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_delete_tone_library_not_found_returns_false(mock_mongo: Mock) -> None:
    """Test deleting a ToneLibrary that doesn't exist returns False."""
    library_id = uuid4()

    mock_collection = Mock()
    mock_collection.find_one.return_value = None  # Library not found
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_delete_tone_library(library_id)

    assert result is False
    mock_collection.find_one.assert_called_once_with({"library_id": str(library_id)})
    mock_collection.delete_one.assert_not_called()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_update_tone_library_tone_profile_ids(mock_mongo: Mock) -> None:
    """Test updating tone_library tone_profile_ids."""
    library_id = uuid4()
    profile_id_1 = uuid4()
    profile_id_2 = uuid4()

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = {
        "library_id": str(library_id),
        "name": "Updated Library",
        "description": "Updated description",
        "tone_profile_ids": [str(profile_id_1), str(profile_id_2)],
        "pack_id": None,
        "universe_id": None,
        "priority": 50,
        "is_default": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    params = ToneLibraryUpdate(tone_profile_ids=[profile_id_1, profile_id_2])
    result = mongodb_update_tone_library(library_id, params)

    assert result is not None
    assert result.library_id == library_id
    assert len(result.tone_profile_ids) == 2
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_update_tone_library_partial_update(mock_mongo: Mock) -> None:
    """Test updating only specific fields of a tone_library (partial update)."""
    library_id = uuid4()

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = {
        "library_id": str(library_id),
        "name": "Test Library",  # Name NOT changed
        "description": "Updated description only",  # Only description changed
        "tone_profile_ids": [],
        "pack_id": None,
        "universe_id": None,
        "priority": 100,  # Priority NOT changed
        "is_default": False,  # is_default NOT changed
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    params = ToneLibraryUpdate(description="Updated description only")
    result = mongodb_update_tone_library(library_id, params)

    assert result is not None
    assert result.library_id == library_id
    assert result.description == "Updated description only"
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_update_tone_library_set_is_default(mock_mongo: Mock) -> None:
    """Test setting is_default to True for a tone_library."""
    library_id = uuid4()

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = {
        "library_id": str(library_id),
        "name": "Default Library",
        "description": "Now a default library",
        "tone_profile_ids": [],
        "pack_id": None,
        "universe_id": None,
        "priority": 100,
        "is_default": True,  # Changed from False to True
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    params = ToneLibraryUpdate(is_default=True)
    result = mongodb_update_tone_library(library_id, params)

    assert result is not None
    assert result.library_id == library_id
    assert result.is_default is True
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_list_tone_libraries_without_universe_filter(mock_mongo: Mock) -> None:
    """Test listing all tone_libraries when universe filter is not provided."""
    universe_id_1 = uuid4()
    universe_id_2 = uuid4()

    docs = [
        {
            "library_id": str(uuid4()),
            "name": "Library 1",
            "description": "Description 1",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": str(universe_id_1),  # Different universe
            "priority": 200,
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
        {
            "library_id": str(uuid4()),
            "name": "Library 2",
            "description": "Description 2",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": str(universe_id_2),  # Different universe
            "priority": 100,
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
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

    result = mongodb_list_tone_libraries(universe_id=None)

    assert result.total == 2
    assert len(result.libraries) == 2
    mock_collection.find.assert_called_once_with({})


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_list_tone_libraries_sorts_by_priority(mock_mongo: Mock) -> None:
    """Test that tone_libraries are sorted by priority descending."""
    docs = [
        {
            "library_id": str(uuid4()),
            "name": "High Priority",
            "description": "Description",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": None,
            "priority": 200,  # High (first in descending order)
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
        {
            "library_id": str(uuid4()),
            "name": "Medium Priority",
            "description": "Description",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": None,
            "priority": 150,  # Medium
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        },
        {
            "library_id": str(uuid4()),
            "name": "Low Priority",
            "description": "Description",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": None,
            "priority": 50,  # Low (last in descending order)
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
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
    mock_collection.count_documents.return_value = 3
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_libraries()

    assert len(result.libraries) == 3
    # Verify sort is called with priority descending
    mock_cursor.sort.assert_called_once_with("priority", -1)
    # Results should be in sorted order (as we pre-sorted the docs)
    assert result.libraries[0].priority == 200
    assert result.libraries[1].priority == 150
    assert result.libraries[2].priority == 50


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_create_tone_library_with_minimal_fields(mock_mongo: Mock) -> None:
    """Test creating a ToneLibrary with only required fields."""
    mock_collection = Mock()
    mock_collection.insert_one.return_value = None
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_create_tone_library(
        ToneLibraryCreate(
            name="Minimal Library",
            description="",  # Default
            tone_profile_ids=[],  # Default
            pack_id=None,  # Default
            universe_id=None,  # Default
            priority=100,  # Default
            is_default=False,  # Default
        )
    )

    assert result is not None
    assert result.name == "Minimal Library"
    assert result.description == ""
    assert len(result.tone_profile_ids) == 0
    assert result.pack_id is None
    assert result.universe_id is None
    assert result.priority == 100
    assert result.is_default is False
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_update_tone_library_name_only(mock_mongo: Mock) -> None:
    """Test updating only name field of a ToneLibrary."""
    library_id = uuid4()

    updated_doc = {
        "library_id": str(library_id),
        "name": "Renamed Library",  # Updated
        "description": "Original description",  # Unchanged
        "tone_profile_ids": [],
        "pack_id": None,
        "universe_id": None,
        "priority": 100,  # Unchanged
        "is_default": False,  # Unchanged
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = updated_doc

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_library(
        library_id,
        ToneLibraryUpdate(name="Renamed Library"),  # Only update name
    )

    assert result is not None
    assert result.name == "Renamed Library"
    assert result.description == "Original description"  # Should remain unchanged
    assert result.priority == 100  # Should remain unchanged
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_update_tone_library_priority_only(mock_mongo: Mock) -> None:
    """Test updating only priority field of a ToneLibrary."""
    library_id = uuid4()

    updated_doc = {
        "library_id": str(library_id),
        "name": "Test Library",  # Unchanged
        "description": "Description",  # Unchanged
        "tone_profile_ids": [],
        "pack_id": None,
        "universe_id": None,
        "priority": 250,  # Updated
        "is_default": False,  # Unchanged
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    mock_collection = Mock()
    mock_collection.update_one.return_value = None
    mock_collection.find_one.return_value = updated_doc

    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_update_tone_library(
        library_id,
        ToneLibraryUpdate(priority=250),  # Only update priority
    )

    assert result is not None
    assert result.priority == 250
    assert result.name == "Test Library"  # Should remain unchanged
    assert result.description == "Description"  # Should remain unchanged
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_list_tone_libraries_filters_by_pack_id(mock_mongo: Mock) -> None:
    """Test listing ToneLibraries with pack_id filter."""
    pack_id = uuid4()
    library_id = uuid4()

    mock_cursor = Mock()
    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "library_id": str(library_id),
            "name": "Pack Library",
            "description": "Tones for this pack",
            "tone_profile_ids": [],
            "pack_id": str(pack_id),
            "universe_id": None,
            "priority": 150,
            "is_default": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_libraries(pack_id=pack_id, limit=10, offset=0)

    assert isinstance(result, ToneLibraryListResponse)
    assert result.total == 1
    assert len(result.libraries) == 1
    assert result.libraries[0].pack_id == pack_id


@patch("monitor_data.tools.mongodb_tools.tone_libraries.get_mongodb_client")
def test_list_tone_libraries_filters_by_is_default(mock_mongo: Mock) -> None:
    """Test listing ToneLibraries with is_default filter."""
    library_id = uuid4()

    mock_cursor = Mock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "library_id": str(library_id),
            "name": "Default Library",
            "description": "Built-in tones",
            "tone_profile_ids": [],
            "pack_id": None,
            "universe_id": None,
            "priority": 100,
            "is_default": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        }
    ]

    mock_collection = Mock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongo.return_value.__getitem__ = Mock(return_value=mock_collection)
    mock_mongo.return_value.get_collection = Mock(return_value=mock_collection)

    result = mongodb_list_tone_libraries(is_default=True, limit=10, offset=0)

    assert isinstance(result, ToneLibraryListResponse)
    assert result.total == 1
    assert len(result.libraries) == 1
    assert result.libraries[0].is_default is True

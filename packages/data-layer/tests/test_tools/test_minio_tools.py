"""
Unit tests for MinIO tools.

Tests cover:
- minio_upload (with auto-key generation)
- minio_get_object
- minio_delete_object
- minio_list_objects (with pagination)
- minio_get_presigned_url
"""

from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

import pytest
from minio.error import S3Error

from monitor_data.schemas.assets import (
    MinioUpload,
    MinioGetObject,
    MinioDeleteObject,
    MinioListObjects,
    MinioGetPresignedUrl,
)
from monitor_data.tools.minio_tools import (
    minio_upload,
    minio_get_object,
    minio_delete_object,
    minio_list_objects,
    minio_get_presigned_url,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_minio_client() -> Mock:
    """Provide a mock MinIO client for testing."""
    mock_client = Mock()
    mock_client.upload_object = Mock()
    mock_client.get_object = Mock()
    mock_client.delete_object = Mock()
    mock_client.list_objects = Mock()
    mock_client.get_presigned_url = Mock()
    return mock_client


@pytest.fixture
def sample_binary_content() -> bytes:
    """Provide sample binary content."""
    return b"Test binary content for MinIO upload"


@pytest.fixture
def sample_metadata() -> Dict[str, str]:
    """Provide sample metadata."""
    return {
        "source_id": str(uuid4()),
        "universe_id": str(uuid4()),
        "uploader": "test_user",
    }


# =============================================================================
# TESTS: minio_upload
# =============================================================================


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_upload_success(
    mock_get_client: Mock,
    mock_minio_client: Mock,
    sample_binary_content: bytes,
    sample_metadata: Dict[str, str],
):
    """Test successful object upload with explicit key."""
    mock_get_client.return_value = mock_minio_client

    # Mock upload response
    mock_minio_client.upload_object.return_value = {
        "bucket": "documents",
        "key": "test-file.pdf",
        "etag": "test-etag-123",
        "version_id": "v1",
    }

    params = MinioUpload(
        bucket="documents",
        key="test-file.pdf",
        content=sample_binary_content,
        content_type="application/pdf",
        metadata=sample_metadata,
    )

    result = minio_upload(params)

    assert result.bucket == "documents"
    assert result.key == "test-file.pdf"
    assert result.etag == "test-etag-123"
    assert result.version_id == "v1"
    assert result.size == len(sample_binary_content)
    assert result.minio_ref.bucket == "documents"
    assert result.minio_ref.key == "test-file.pdf"
    mock_minio_client.upload_object.assert_called_once()


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_upload_auto_key(
    mock_get_client: Mock, mock_minio_client: Mock, sample_binary_content: bytes
):
    """Test upload with auto-generated UUID key."""
    mock_get_client.return_value = mock_minio_client

    # Mock upload response - key will be auto-generated
    def upload_side_effect(bucket_name, object_key, content, content_type, metadata):
        return {
            "bucket": bucket_name,
            "key": object_key,
            "etag": "auto-etag-456",
            "version_id": None,
        }

    mock_minio_client.upload_object.side_effect = upload_side_effect

    params = MinioUpload(
        bucket="documents",
        key=None,  # Auto-generate key
        content=sample_binary_content,
        content_type="application/octet-stream",
    )

    result = minio_upload(params)

    assert result.bucket == "documents"
    # Key should be a valid UUID
    assert len(result.key) == 36  # UUID string length
    assert result.etag == "auto-etag-456"
    assert result.size == len(sample_binary_content)
    mock_minio_client.upload_object.assert_called_once()


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_upload_default_content_type(
    mock_get_client: Mock, mock_minio_client: Mock, sample_binary_content: bytes
):
    """Test upload uses default content type when not specified."""
    mock_get_client.return_value = mock_minio_client

    mock_minio_client.upload_object.return_value = {
        "bucket": "documents",
        "key": "test-file",
        "etag": "test-etag",
        "version_id": None,
    }

    params = MinioUpload(
        bucket="documents",
        key="test-file",
        content=sample_binary_content,
        # content_type defaults to "application/octet-stream"
    )

    result = minio_upload(params)

    # Verify default content type was used
    call_args = mock_minio_client.upload_object.call_args
    assert call_args[1]["content_type"] == "application/octet-stream"


# =============================================================================
# TESTS: minio_get_object
# =============================================================================


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_get_object_success(
    mock_get_client: Mock, mock_minio_client: Mock, sample_binary_content: bytes
):
    """Test successful object retrieval."""
    mock_get_client.return_value = mock_minio_client

    # Mock get response
    mock_minio_client.get_object.return_value = {
        "bucket": "documents",
        "key": "test-file.pdf",
        "content": sample_binary_content,
        "content_type": "application/pdf",
        "size": len(sample_binary_content),
        "metadata": {"source_id": "test-source"},
        "etag": "test-etag-123",
        "last_modified": datetime.now(timezone.utc),
    }

    params = MinioGetObject(bucket="documents", key="test-file.pdf")

    result = minio_get_object(params)

    assert result.bucket == "documents"
    assert result.key == "test-file.pdf"
    assert result.content == sample_binary_content
    assert result.content_type == "application/pdf"
    assert result.size == len(sample_binary_content)
    assert result.metadata["source_id"] == "test-source"
    assert result.minio_ref.bucket == "documents"
    assert result.minio_ref.key == "test-file.pdf"
    mock_minio_client.get_object.assert_called_once()


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_get_object_not_found(mock_get_client: Mock, mock_minio_client: Mock):
    """Test getting a non-existent object raises error."""
    mock_get_client.return_value = mock_minio_client

    # Mock S3Error for not found
    mock_minio_client.get_object.side_effect = S3Error(
        code="NoSuchKey",
        message="Object not found",
        resource="/documents/nonexistent.pdf",
        request_id="test-req-id",
        host_id="test-host-id",
        response=MagicMock(),
    )

    params = MinioGetObject(bucket="documents", key="nonexistent.pdf")

    with pytest.raises(S3Error):
        minio_get_object(params)


# =============================================================================
# TESTS: minio_delete_object
# =============================================================================


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_delete_object_success(mock_get_client: Mock, mock_minio_client: Mock):
    """Test successful object deletion."""
    mock_get_client.return_value = mock_minio_client

    # Mock delete response
    mock_minio_client.delete_object.return_value = True

    params = MinioDeleteObject(bucket="documents", key="test-file.pdf")

    result = minio_delete_object(params)

    assert result.bucket == "documents"
    assert result.key == "test-file.pdf"
    assert result.deleted is True
    mock_minio_client.delete_object.assert_called_once_with(
        bucket_name="documents", object_key="test-file.pdf"
    )


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_delete_object_nonexistent(mock_get_client: Mock, mock_minio_client: Mock):
    """Test deleting a non-existent object (MinIO silently succeeds)."""
    mock_get_client.return_value = mock_minio_client

    # MinIO doesn't raise error for deleting non-existent objects
    mock_minio_client.delete_object.return_value = True

    params = MinioDeleteObject(bucket="documents", key="nonexistent.pdf")

    result = minio_delete_object(params)

    assert result.deleted is True


# =============================================================================
# TESTS: minio_list_objects
# =============================================================================


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_list_objects_success(mock_get_client: Mock, mock_minio_client: Mock):
    """Test successful object listing."""
    mock_get_client.return_value = mock_minio_client

    # Mock list response
    now = datetime.now(timezone.utc)
    mock_minio_client.list_objects.return_value = [
        {
            "bucket": "documents",
            "key": "file1.pdf",
            "size": 1024,
            "etag": "etag1",
            "last_modified": now,
            "is_dir": False,
        },
        {
            "bucket": "documents",
            "key": "file2.pdf",
            "size": 2048,
            "etag": "etag2",
            "last_modified": now,
            "is_dir": False,
        },
    ]

    params = MinioListObjects(bucket="documents", limit=10, offset=0)

    result = minio_list_objects(params)

    assert result.bucket == "documents"
    assert result.count == 2
    assert len(result.objects) == 2
    assert result.objects[0].key == "file1.pdf"
    assert result.objects[1].key == "file2.pdf"
    assert result.offset == 0
    assert result.limit == 10
    assert result.has_more is False


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_list_objects_with_prefix(mock_get_client: Mock, mock_minio_client: Mock):
    """Test listing with prefix filter."""
    mock_get_client.return_value = mock_minio_client

    now = datetime.now(timezone.utc)
    mock_minio_client.list_objects.return_value = [
        {
            "bucket": "documents",
            "key": "pdfs/file1.pdf",
            "size": 1024,
            "etag": "etag1",
            "last_modified": now,
            "is_dir": False,
        },
    ]

    params = MinioListObjects(bucket="documents", prefix="pdfs/", limit=10, offset=0)

    result = minio_list_objects(params)

    assert result.prefix == "pdfs/"
    assert result.count == 1
    assert result.objects[0].key == "pdfs/file1.pdf"
    mock_minio_client.list_objects.assert_called_once_with(
        bucket_name="documents", prefix="pdfs/", recursive=True
    )


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_list_objects_pagination(mock_get_client: Mock, mock_minio_client: Mock):
    """Test pagination works correctly."""
    mock_get_client.return_value = mock_minio_client

    # Mock 5 objects
    now = datetime.now(timezone.utc)
    all_objects = [
        {
            "bucket": "documents",
            "key": f"file{i}.pdf",
            "size": 1024,
            "etag": f"etag{i}",
            "last_modified": now,
            "is_dir": False,
        }
        for i in range(5)
    ]
    mock_minio_client.list_objects.return_value = all_objects

    # Request first 2 objects
    params = MinioListObjects(bucket="documents", limit=2, offset=0)
    result = minio_list_objects(params)

    assert result.count == 2
    assert result.objects[0].key == "file0.pdf"
    assert result.objects[1].key == "file1.pdf"
    assert result.has_more is True  # More objects exist

    # Request next 2 objects
    params = MinioListObjects(bucket="documents", limit=2, offset=2)
    result = minio_list_objects(params)

    assert result.count == 2
    assert result.objects[0].key == "file2.pdf"
    assert result.objects[1].key == "file3.pdf"
    assert result.has_more is True

    # Request last object
    params = MinioListObjects(bucket="documents", limit=2, offset=4)
    result = minio_list_objects(params)

    assert result.count == 1
    assert result.objects[0].key == "file4.pdf"
    assert result.has_more is False  # No more objects


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_list_objects_empty_bucket(mock_get_client: Mock, mock_minio_client: Mock):
    """Test listing an empty bucket."""
    mock_get_client.return_value = mock_minio_client

    mock_minio_client.list_objects.return_value = []

    params = MinioListObjects(bucket="documents", limit=10, offset=0)

    result = minio_list_objects(params)

    assert result.count == 0
    assert len(result.objects) == 0
    assert result.has_more is False


# =============================================================================
# TESTS: minio_get_presigned_url
# =============================================================================


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_get_presigned_url_success(mock_get_client: Mock, mock_minio_client: Mock):
    """Test successful presigned URL generation."""
    mock_get_client.return_value = mock_minio_client

    # Mock presigned URL
    mock_url = "https://minio.example.com/documents/test-file.pdf?X-Amz-Signature=..."
    mock_minio_client.get_presigned_url.return_value = mock_url

    params = MinioGetPresignedUrl(
        bucket="documents", key="test-file.pdf", expires_in=3600
    )

    result = minio_get_presigned_url(params)

    assert result.bucket == "documents"
    assert result.key == "test-file.pdf"
    assert result.url == mock_url
    assert result.expires_in == 3600
    assert result.minio_ref.bucket == "documents"
    assert result.minio_ref.key == "test-file.pdf"
    mock_minio_client.get_presigned_url.assert_called_once_with(
        bucket_name="documents", object_key="test-file.pdf", expires_in=3600
    )


@patch("monitor_data.tools.minio_tools.get_minio_client")
def test_get_presigned_url_custom_expiry(
    mock_get_client: Mock, mock_minio_client: Mock
):
    """Test presigned URL with custom expiration time."""
    mock_get_client.return_value = mock_minio_client

    mock_url = "https://minio.example.com/documents/test-file.pdf?expires=7200"
    mock_minio_client.get_presigned_url.return_value = mock_url

    params = MinioGetPresignedUrl(
        bucket="documents", key="test-file.pdf", expires_in=7200  # 2 hours
    )

    result = minio_get_presigned_url(params)

    assert result.expires_in == 7200
    mock_minio_client.get_presigned_url.assert_called_once_with(
        bucket_name="documents", object_key="test-file.pdf", expires_in=7200
    )


# =============================================================================
# TESTS: Validation
# =============================================================================


def test_upload_missing_required_fields():
    """Test upload validation with missing required fields."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        MinioUpload(
            bucket="documents",
            # Missing content
        )  # type: ignore

    assert "content" in str(exc_info.value).lower()


def test_list_objects_invalid_limit():
    """Test list validation with invalid limit."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MinioListObjects(bucket="documents", limit=5000)  # Exceeds max of 1000


def test_get_presigned_url_invalid_expiry():
    """Test presigned URL validation with invalid expiry."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MinioGetPresignedUrl(
            bucket="documents",
            key="test-file.pdf",
            expires_in=700000,  # Exceeds max of 604800 (7 days)
        )

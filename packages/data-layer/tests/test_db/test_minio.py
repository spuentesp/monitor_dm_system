"""
Unit tests for MinIO client.

Tests cover:
- MinIOClient initialization
- Secret key requirement enforcement
- Connection management
- Basic operations (with mocked minio client)
- Upload, get, delete, list operations
- Presigned URL generation
"""

import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import pytest
from io import BytesIO

from monitor_data.db.minio import MinIOClient, get_minio_client
from minio.error import S3Error


def test_minio_client_requires_secret_key():
    """Test that MinIOClient raises error when secret_key is not provided."""
    # Clear secret key env var if it exists
    original_secret = os.environ.get("MINIO_SECRET_KEY")
    if "MINIO_SECRET_KEY" in os.environ:
        del os.environ["MINIO_SECRET_KEY"]

    try:
        with pytest.raises(ValueError, match="MinIO secret key is required"):
            MinIOClient()
    finally:
        # Restore original secret key
        if original_secret:
            os.environ["MINIO_SECRET_KEY"] = original_secret


def test_minio_client_accepts_explicit_secret():
    """Test that MinIOClient works with explicit secret_key parameter."""
    # Clear secret key env var
    original_secret = os.environ.get("MINIO_SECRET_KEY")
    if "MINIO_SECRET_KEY" in os.environ:
        del os.environ["MINIO_SECRET_KEY"]

    try:
        client = MinIOClient(secret_key="explicit_secret")
        assert client.secret_key == "explicit_secret"
    finally:
        # Restore original secret key
        if original_secret:
            os.environ["MINIO_SECRET_KEY"] = original_secret


def test_minio_client_uses_env_secret():
    """Test that MinIOClient uses secret_key from environment variable."""
    os.environ["MINIO_SECRET_KEY"] = "env_secret"

    client = MinIOClient()
    assert client.secret_key == "env_secret"


def test_minio_client_explicit_overrides_env():
    """Test that explicit secret_key parameter overrides environment variable."""
    os.environ["MINIO_SECRET_KEY"] = "env_secret"

    client = MinIOClient(secret_key="explicit_secret")
    assert client.secret_key == "explicit_secret"


def test_minio_client_default_endpoint():
    """Test that MinIOClient uses default endpoint."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    assert client.endpoint == "localhost:9000"


def test_minio_client_custom_endpoint():
    """Test that MinIOClient accepts custom endpoint."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient(endpoint="minio.example.com:9000")
    assert client.endpoint == "minio.example.com:9000"


def test_minio_client_default_secure_false():
    """Test that MinIOClient defaults secure to False."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    assert client.secure is False


def test_minio_client_secure_from_env():
    """Test that MinIOClient reads secure from environment."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    os.environ["MINIO_SECURE"] = "true"
    
    try:
        client = MinIOClient()
        assert client.secure is True
    finally:
        os.environ["MINIO_SECURE"] = "false"


@patch("monitor_data.db.minio.Minio")
def test_minio_client_connect(mock_minio_class):
    """Test that connect() creates a Minio client."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    
    assert client._client == mock_minio_instance
    mock_minio_class.assert_called_once_with(
        "localhost:9000",
        access_key="monitor",
        secret_key="test_secret",
        secure=False,
    )


def test_minio_client_close():
    """Test that close() clears the client."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    client._client = Mock()
    client.close()
    
    assert client._client is None


@patch("monitor_data.db.minio.Minio")
def test_minio_client_context_manager(mock_minio_class):
    """Test that MinIOClient works as context manager."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_minio_class.return_value = mock_minio_instance
    
    with MinIOClient() as client:
        assert client._client == mock_minio_instance
    
    # After context, client should be closed
    assert client._client is None


@patch("monitor_data.db.minio.Minio")
def test_ensure_bucket_creates_if_not_exists(mock_minio_class):
    """Test ensure_bucket creates bucket if it doesn't exist."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_minio_instance.bucket_exists.return_value = False
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    client.ensure_bucket("test-bucket")
    
    mock_minio_instance.bucket_exists.assert_called_once_with("test-bucket")
    mock_minio_instance.make_bucket.assert_called_once_with("test-bucket")


@patch("monitor_data.db.minio.Minio")
def test_ensure_bucket_skips_if_exists(mock_minio_class):
    """Test ensure_bucket skips creation if bucket exists."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_minio_instance.bucket_exists.return_value = True
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    client.ensure_bucket("test-bucket")
    
    mock_minio_instance.bucket_exists.assert_called_once_with("test-bucket")
    mock_minio_instance.make_bucket.assert_not_called()


def test_ensure_bucket_requires_connection():
    """Test ensure_bucket raises error if not connected."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    # Don't call connect()
    
    with pytest.raises(RuntimeError, match="MinIO client not connected"):
        client.ensure_bucket("test-bucket")


def test_upload_object_requires_connection():
    """Test upload_object raises error if not connected."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    # Don't call connect()
    
    with pytest.raises(RuntimeError, match="MinIO client not connected"):
        client.upload_object("bucket", "key", b"content")


def test_get_object_requires_connection():
    """Test get_object raises error if not connected."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    # Don't call connect()
    
    with pytest.raises(RuntimeError, match="MinIO client not connected"):
        client.get_object("bucket", "key")


def test_delete_object_requires_connection():
    """Test delete_object raises error if not connected."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    # Don't call connect()
    
    with pytest.raises(RuntimeError, match="MinIO client not connected"):
        client.delete_object("bucket", "key")


def test_list_objects_requires_connection():
    """Test list_objects raises error if not connected."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    # Don't call connect()
    
    with pytest.raises(RuntimeError, match="MinIO client not connected"):
        client.list_objects("bucket")


def test_get_presigned_url_requires_connection():
    """Test get_presigned_url raises error if not connected."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    # Don't call connect()
    
    with pytest.raises(RuntimeError, match="MinIO client not connected"):
        client.get_presigned_url("bucket", "key")


@patch("monitor_data.db.minio.Minio")
def test_verify_connectivity_success(mock_minio_class):
    """Test verify_connectivity returns True when connected."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_minio_instance.list_buckets.return_value = []
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    
    assert client.verify_connectivity() is True


def test_verify_connectivity_not_connected():
    """Test verify_connectivity returns False when not connected."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    client = MinIOClient()
    # Don't call connect()
    
    assert client.verify_connectivity() is False


@patch("monitor_data.db.minio.Minio")
def test_verify_connectivity_failure(mock_minio_class):
    """Test verify_connectivity returns False on exception."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_minio_instance.list_buckets.side_effect = Exception("Connection failed")
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    
    assert client.verify_connectivity() is False


@patch("monitor_data.db.minio.Minio")
def test_upload_object_success(mock_minio_class):
    """Test upload_object successfully uploads content."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_minio_instance.bucket_exists.return_value = True
    mock_result = Mock()
    mock_result.etag = "test-etag"
    mock_result.version_id = "v1"
    mock_minio_instance.put_object.return_value = mock_result
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    
    content = b"test content"
    result = client.upload_object("test-bucket", "test-key", content, "text/plain", {"meta": "data"})
    
    assert result["bucket"] == "test-bucket"
    assert result["key"] == "test-key"
    assert result["etag"] == "test-etag"
    assert result["version_id"] == "v1"
    mock_minio_instance.put_object.assert_called_once()


@patch("monitor_data.db.minio.Minio")
def test_get_object_success(mock_minio_class):
    """Test get_object successfully retrieves content."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_response = Mock()
    mock_response.read.return_value = b"test content"
    mock_response.close = Mock()
    mock_response.release_conn = Mock()
    mock_minio_instance.get_object.return_value = mock_response
    
    mock_stat = Mock()
    mock_stat.content_type = "text/plain"
    mock_stat.size = 12
    mock_stat.metadata = {"meta": "data"}
    mock_stat.etag = "test-etag"
    mock_stat.last_modified = datetime.now(timezone.utc)
    mock_minio_instance.stat_object.return_value = mock_stat
    
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    
    result = client.get_object("test-bucket", "test-key")
    
    assert result["bucket"] == "test-bucket"
    assert result["key"] == "test-key"
    assert result["content"] == b"test content"
    assert result["content_type"] == "text/plain"
    assert result["size"] == 12
    mock_response.close.assert_called_once()
    mock_response.release_conn.assert_called_once()


@patch("monitor_data.db.minio.Minio")
def test_delete_object_success(mock_minio_class):
    """Test delete_object successfully removes object."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_minio_instance.remove_object.return_value = None
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    
    result = client.delete_object("test-bucket", "test-key")
    
    assert result is True
    mock_minio_instance.remove_object.assert_called_once_with("test-bucket", "test-key")


@patch("monitor_data.db.minio.Minio")
def test_list_objects_success(mock_minio_class):
    """Test list_objects returns object list."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_obj1 = Mock()
    mock_obj1.object_name = "file1.txt"
    mock_obj1.size = 100
    mock_obj1.etag = "etag1"
    mock_obj1.last_modified = datetime.now(timezone.utc)
    mock_obj1.is_dir = False
    
    mock_obj2 = Mock()
    mock_obj2.object_name = "file2.txt"
    mock_obj2.size = 200
    mock_obj2.etag = "etag2"
    mock_obj2.last_modified = datetime.now(timezone.utc)
    mock_obj2.is_dir = False
    
    mock_minio_instance.list_objects.return_value = [mock_obj1, mock_obj2]
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    
    result = client.list_objects("test-bucket", prefix="test/")
    
    assert len(result) == 2
    assert result[0]["key"] == "file1.txt"
    assert result[1]["key"] == "file2.txt"
    mock_minio_instance.list_objects.assert_called_once_with("test-bucket", prefix="test/", recursive=True)


@patch("monitor_data.db.minio.Minio")
def test_get_presigned_url_success(mock_minio_class):
    """Test get_presigned_url generates URL."""
    os.environ["MINIO_SECRET_KEY"] = "test_secret"
    
    mock_minio_instance = Mock()
    mock_url = "https://minio.example.com/bucket/key?signature=..."
    mock_minio_instance.presigned_get_object.return_value = mock_url
    mock_minio_class.return_value = mock_minio_instance
    
    client = MinIOClient()
    client.connect()
    
    result = client.get_presigned_url("test-bucket", "test-key", expires_in=7200)
    
    assert result == mock_url
    mock_minio_instance.presigned_get_object.assert_called_once()

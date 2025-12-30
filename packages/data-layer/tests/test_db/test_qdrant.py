"""
Unit tests for Qdrant client.

Tests cover:
- QdrantClient initialization
- Connection management
- Collection operations
"""

import os
import pytest
from unittest.mock import Mock, patch

from monitor_data.db.qdrant import QdrantClient, get_qdrant_client, reset_qdrant_client


def test_qdrant_client_uses_env_url():
    """Test that QdrantClient uses URL from environment variable."""
    os.environ["QDRANT_URL"] = "http://test-qdrant:6333"

    client = QdrantClient()
    assert client.url == "http://test-qdrant:6333"


def test_qdrant_client_uses_env_api_key():
    """Test that QdrantClient uses API key from environment variable."""
    os.environ["QDRANT_API_KEY"] = "test_api_key"

    client = QdrantClient()
    assert client.api_key == "test_api_key"


def test_qdrant_client_explicit_overrides_env():
    """Test that explicit parameters override environment variables."""
    os.environ["QDRANT_URL"] = "http://env-qdrant:6333"
    os.environ["QDRANT_API_KEY"] = "env_key"

    client = QdrantClient(url="http://explicit-qdrant:6333", api_key="explicit_key")
    assert client.url == "http://explicit-qdrant:6333"
    assert client.api_key == "explicit_key"


def test_qdrant_client_default_values():
    """Test that QdrantClient uses default values when env vars not set."""
    # Clear env vars
    if "QDRANT_URL" in os.environ:
        del os.environ["QDRANT_URL"]
    if "QDRANT_API_KEY" in os.environ:
        del os.environ["QDRANT_API_KEY"]

    client = QdrantClient()
    assert client.url == "http://localhost:6333"
    assert client.api_key is None


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_qdrant_client_connect_without_api_key(mock_qdrant_sdk: Mock):
    """Test connecting without API key."""
    client = QdrantClient(url="http://localhost:6333")
    client.connect()

    mock_qdrant_sdk.assert_called_once_with(url="http://localhost:6333")
    assert client._client is not None


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_qdrant_client_connect_with_api_key(mock_qdrant_sdk: Mock):
    """Test connecting with API key."""
    client = QdrantClient(url="http://localhost:6333", api_key="test_key")
    client.connect()

    mock_qdrant_sdk.assert_called_once_with(
        url="http://localhost:6333", api_key="test_key"
    )
    assert client._client is not None


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_qdrant_client_close(mock_qdrant_sdk: Mock):
    """Test closing connection."""
    mock_client = Mock()
    mock_qdrant_sdk.return_value = mock_client

    client = QdrantClient()
    client.connect()
    client.close()

    mock_client.close.assert_called_once()
    assert client._client is None


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_qdrant_client_context_manager(mock_qdrant_sdk: Mock):
    """Test context manager usage."""
    mock_client = Mock()
    mock_qdrant_sdk.return_value = mock_client

    with QdrantClient() as client:
        assert client._client is not None

    mock_client.close.assert_called_once()


def test_qdrant_client_get_client_without_connection():
    """Test that get_client raises RuntimeError when not connected."""
    client = QdrantClient()
    # Don't call connect()

    with pytest.raises(
        RuntimeError, match="Qdrant client not connected. Call connect\\(\\) first."
    ):
        client.get_client()


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_qdrant_client_verify_connectivity_success(mock_qdrant_sdk: Mock):
    """Test successful connectivity verification."""
    mock_client = Mock()
    mock_client.get_collections.return_value = Mock()
    mock_qdrant_sdk.return_value = mock_client

    client = QdrantClient()
    result = client.verify_connectivity()

    assert result is True
    mock_client.get_collections.assert_called_once()


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_qdrant_client_verify_connectivity_failure(mock_qdrant_sdk: Mock):
    """Test connectivity verification failure."""
    mock_client = Mock()
    mock_client.get_collections.side_effect = Exception("Connection failed")
    mock_qdrant_sdk.return_value = mock_client

    client = QdrantClient()
    result = client.verify_connectivity()

    assert result is False


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_qdrant_client_ensure_collection_creates_new(mock_qdrant_sdk: Mock):
    """Test ensure_collection creates collection if not exists."""
    mock_client = Mock()
    mock_collections = Mock()
    mock_collections.collections = []
    mock_client.get_collections.return_value = mock_collections
    mock_qdrant_sdk.return_value = mock_client

    client = QdrantClient()
    client.connect()
    client.ensure_collection("test_collection", vector_size=1536)

    mock_client.create_collection.assert_called_once()


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_qdrant_client_ensure_collection_exists(mock_qdrant_sdk: Mock):
    """Test ensure_collection doesn't create if exists."""
    mock_client = Mock()
    mock_collection = Mock()
    mock_collection.name = "test_collection"
    mock_collections = Mock()
    mock_collections.collections = [mock_collection]
    mock_client.get_collections.return_value = mock_collections
    mock_qdrant_sdk.return_value = mock_client

    client = QdrantClient()
    client.connect()
    client.ensure_collection("test_collection", vector_size=1536)

    mock_client.create_collection.assert_not_called()


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_get_qdrant_client_singleton(mock_qdrant_sdk: Mock):
    """Test that get_qdrant_client returns singleton."""
    reset_qdrant_client()  # Clear any existing instance

    client1 = get_qdrant_client()
    client2 = get_qdrant_client()

    assert client1 is client2


@patch("monitor_data.db.qdrant.QdrantSDK")
def test_reset_qdrant_client(mock_qdrant_sdk: Mock):
    """Test that reset_qdrant_client clears singleton."""
    # First, clear any existing instance
    reset_qdrant_client()

    mock_client_instance = Mock()
    mock_qdrant_sdk.return_value = mock_client_instance

    client1 = get_qdrant_client()

    # The mock_client_instance should be returned as the _client attribute
    # We need to check that close was called on the QdrantClient's _client
    assert client1._client is not None

    reset_qdrant_client()

    # After reset, getting a new client should be a different QdrantClient instance
    client2 = get_qdrant_client()

    assert client1 is not client2
    # Verify close was called on the SDK client
    mock_client_instance.close.assert_called_once()

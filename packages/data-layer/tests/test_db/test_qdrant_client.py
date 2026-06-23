"""
Unit tests for Qdrant client.

Covers QdrantClient lifecycle, connectivity, and collection management
with mocked QdrantAsyncClientLib.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from monitor_data.db.qdrant import QdrantClient, get_qdrant_client, reset_qdrant_client


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def clean_singleton():
    """Reset module singleton before each test."""
    reset_qdrant_client()


# =============================================================================
# INITIALISATION
# =============================================================================


def test_init_with_url():
    c = QdrantClient(url="http://qdrant:6333", api_key="secret")
    assert c._url == "http://qdrant:6333"
    assert c._api_key == "secret"
    assert c._client is None


def test_init_defaults_to_localhost():
    with patch("monitor_data.db.qdrant.settings") as mock_settings:
        mock_settings.qdrant_url = None
        mock_settings.qdrant_path = None
        mock_settings.qdrant_api_key = None
        c = QdrantClient()
        assert c._url == "http://localhost:6333"


# =============================================================================
# CONNECTION LIFECYCLE
# =============================================================================


@pytest.mark.asyncio
async def test_connect_with_url():
    c = QdrantClient(url="http://qdrant:6333")
    with patch("monitor_data.db.qdrant.QdrantAsyncClientLib") as MockClient:
        instance = AsyncMock()
        MockClient.return_value = instance
        await c.connect()
    MockClient.assert_called_once_with(url="http://qdrant:6333", api_key=None, prefer_grpc=True)
    assert c._client is instance


@pytest.mark.asyncio
async def test_connect_with_path():
    c = QdrantClient(path="/tmp/qdrant")
    with patch("monitor_data.db.qdrant.QdrantAsyncClientLib") as MockClient:
        instance = AsyncMock()
        MockClient.return_value = instance
        await c.connect()
    MockClient.assert_called_once_with(path="/tmp/qdrant")
    assert c._client is instance


@pytest.mark.asyncio
async def test_connect_is_idempotent():
    c = QdrantClient(url="http://qdrant:6333")
    with patch("monitor_data.db.qdrant.QdrantAsyncClientLib") as MockClient:
        instance = AsyncMock()
        MockClient.return_value = instance
        await c.connect()
        await c.connect()
    MockClient.assert_called_once()


@pytest.mark.asyncio
async def test_close():
    c = QdrantClient(url="http://qdrant:6333")
    with patch("monitor_data.db.qdrant.QdrantAsyncClientLib") as MockClient:
        instance = AsyncMock()
        MockClient.return_value = instance
        await c.connect()
        c._collections_initialized.add("scenes")
        await c.close()
    instance.close.assert_awaited_once()
    assert c._client is None
    assert c._collections_initialized == set()


# =============================================================================
# HEALTH CHECK
# =============================================================================


def test_verify_connectivity_success():
    c = QdrantClient(url="http://qdrant:6333")
    c._client = AsyncMock()
    with patch("monitor_data.db.qdrant.run_sync") as mock_run_sync:
        mock_run_sync.side_effect = lambda coro: asyncio.new_event_loop().run_until_complete(coro)
        result = c.verify_connectivity()
        assert result is True


def test_get_client_auto_connects():
    c = QdrantClient(url="http://qdrant:6333")
    assert c._client is None
    with patch("monitor_data.db.qdrant.QdrantAsyncClientLib") as MockClient:
        instance = AsyncMock()
        MockClient.return_value = instance
        with patch("monitor_data.db.qdrant.run_sync") as mock_run_sync:
            mock_run_sync.side_effect = lambda coro: asyncio.new_event_loop().run_until_complete(
                coro
            )
            result = c.get_client()
    assert result is instance


# =============================================================================
# GET CLIENT
# =============================================================================


def test_get_client_returns_existing():
    c = QdrantClient(url="http://qdrant:6333")
    mock_client = Mock()
    c._client = mock_client
    result = c.get_client()
    assert result is mock_client


# =============================================================================
# ENSURE COLLECTION
# =============================================================================


@pytest.mark.asyncio
async def test_ensure_collection_already_initialized():
    c = QdrantClient(url="http://qdrant:6333")
    c._client = AsyncMock()
    c._collections_initialized.add("scenes")
    with patch("monitor_data.db.qdrant.QdrantAsyncClientLib"):
        await c.ensure_collection("scenes")
    c._client.get_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_collection_unknown_raises():
    c = QdrantClient(url="http://qdrant:6333")
    c._client = AsyncMock()
    with pytest.raises(ValueError, match="Unknown collection"):
        await c.ensure_collection("unknown_collection")


@pytest.mark.asyncio
async def test_ensure_collection_creates_when_missing():
    c = QdrantClient(url="http://qdrant:6333")
    mock_client = AsyncMock()
    mock_client.get_collection.side_effect = Exception("Collection not found")
    mock_client.create_collection = AsyncMock()
    mock_client.create_payload_index = AsyncMock()
    c._client = mock_client

    with patch("monitor_data.db.qdrant.VectorParams"):
        await c.ensure_collection("scenes")

    mock_client.create_collection.assert_awaited_once()
    assert "scenes" in c._collections_initialized


@pytest.mark.asyncio
async def test_ensure_collection_uses_existing():
    c = QdrantClient(url="http://qdrant:6333")
    mock_client = AsyncMock()
    mock_client.get_collection = AsyncMock()  # no exception = exists
    mock_client.create_payload_index = AsyncMock()
    c._client = mock_client

    await c.ensure_collection("scenes")
    mock_client.create_collection.assert_not_awaited()
    mock_client.create_payload_index.assert_awaited()
    assert "scenes" in c._collections_initialized


# =============================================================================
# PAYLOAD INDEXES
# =============================================================================


@pytest.mark.asyncio
async def test_ensure_payload_indexes_for_snippets():
    c = QdrantClient(url="http://qdrant:6333")
    mock_client = AsyncMock()
    mock_client.create_payload_index = AsyncMock()
    c._client = mock_client

    with patch("monitor_data.db.qdrant.TextIndexParams"):
        await c._ensure_payload_indexes("snippets")
    # Should call for text field + all snippet payload indexes
    assert mock_client.create_payload_index.await_count >= 1


@pytest.mark.asyncio
async def test_ensure_payload_indexes_skips_on_error():
    c = QdrantClient(url="http://qdrant:6333")
    mock_client = AsyncMock()
    mock_client.create_payload_index.side_effect = Exception("index exists")
    c._client = mock_client

    # Should not raise despite errors
    await c._ensure_payload_indexes("scenes")


# =============================================================================
# SINGLETON
# =============================================================================


def test_get_qdrant_client_singleton():
    c1 = get_qdrant_client()
    c2 = get_qdrant_client()
    assert c1 is c2


def test_reset_qdrant_client():
    c = get_qdrant_client()
    with patch("monitor_data.db.qdrant.run_sync") as mock_run_sync:
        mock_run_sync.return_value = None
        reset_qdrant_client()
    assert c._client is None


# =============================================================================
# reset_client (T-098/R9 — self-healing upsert retry support)
# =============================================================================


def test_reset_client_drops_cached_client():
    c = QdrantClient(url="http://qdrant:6333")
    c._client = Mock()
    c._client_loop = asyncio.new_event_loop()
    c._collections_initialized.add("memories")

    c.reset_client()

    assert c._client is None
    assert c._client_loop is None
    assert c._collections_initialized == set()


def test_reset_client_keeps_externally_set_client():
    # When _client_loop is None the client was set externally (e.g. a test mock)
    # — reset_client must not clobber it.
    c = QdrantClient(url="http://qdrant:6333")
    external = Mock()
    c._client = external
    c._client_loop = None

    c.reset_client()

    assert c._client is external

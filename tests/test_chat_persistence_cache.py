from __future__ import annotations

from types import SimpleNamespace

from monitor_ui.routers import chat_persistence


def test_db_load_messages_prefers_redis_cache(monkeypatch):
    cached_messages = [
        {
            "id": "msg-1",
            "session_id": "session-1",
            "role": "gm",
            "content": "Cached hello",
            "timestamp": "2026-04-08T00:00:00+00:00",
        }
    ]

    monkeypatch.setattr(
        chat_persistence,
        "_redis_get_json",
        lambda key: cached_messages if key == "chat_messages:session-1" else None,
    )

    def _fail_get_mongo():
        raise AssertionError("MongoDB should not be hit when Redis chat cache is warm")

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", _fail_get_mongo)

    result = chat_persistence.db_load_messages("session-1")

    assert result == cached_messages


def test_db_save_session_updates_shared_redis_cache(monkeypatch):
    replace_calls: list[tuple[dict, dict, bool]] = []
    redis_writes: dict[str, object] = {}
    published: list[tuple[str, str, dict]] = []

    class _FakeCollection:
        def replace_one(self, query, document, upsert=False):
            replace_calls.append((query, document, upsert))

    fake_mongo = SimpleNamespace(get_collection=lambda _name: _FakeCollection())

    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client", lambda: fake_mongo
    )
    monkeypatch.setattr(
        chat_persistence,
        "_redis_get_json",
        lambda key: [] if key == chat_persistence._SESSION_INDEX_KEY else None,
    )
    monkeypatch.setattr(
        chat_persistence,
        "_redis_set_json",
        lambda key, value: redis_writes.__setitem__(key, value),
    )
    monkeypatch.setattr(
        chat_persistence,
        "_publish_chat_event",
        lambda session_id, event_type, payload: published.append(
            (session_id, event_type, payload)
        ),
    )

    session = {
        "id": "session-42",
        "title": "Redis-backed session",
        "updated_at": "2026-04-08T12:00:00+00:00",
    }

    chat_persistence.db_save_session(session)

    assert replace_calls == [({"id": "session-42"}, session, True)]
    assert redis_writes[chat_persistence._session_cache_key("session-42")] == session
    index_rows = redis_writes[chat_persistence._SESSION_INDEX_KEY]
    assert isinstance(index_rows, list)
    assert index_rows[0]["id"] == "session-42"
    assert published == [
        ("session-42", "session_saved", {"updated_at": "2026-04-08T12:00:00+00:00"})
    ]


def test_purge_chat_runtime_cache_removes_deleted_session(monkeypatch):
    writes: dict[str, object] = {}
    deleted: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        chat_persistence,
        "_redis_get_json",
        lambda key: (
            [{"id": "keep"}, {"id": "gone"}]
            if key == chat_persistence._SESSION_INDEX_KEY
            else None
        ),
    )
    monkeypatch.setattr(
        chat_persistence,
        "_redis_set_json",
        lambda key, value: writes.__setitem__(key, value),
    )
    monkeypatch.setattr(
        chat_persistence,
        "_redis_delete",
        lambda *keys: deleted.append(keys) or len(keys),
    )

    chat_persistence.purge_chat_runtime_cache("gone")

    assert deleted == [
        (
            chat_persistence._session_cache_key("gone"),
            chat_persistence._messages_cache_key("gone"),
        )
    ]
    assert writes[chat_persistence._SESSION_INDEX_KEY] == [{"id": "keep"}]


# =============================================================================
# Additional chat persistence cache tests
# =============================================================================


def test_db_load_sessions_prefers_redis_cache(monkeypatch):
    """Test db_load_sessions returns cached sessions from Redis."""
    cached_sessions = [
        {"id": "session-1", "title": "Session 1", "updated_at": "2026-04-08T12:00:00+00:00"},
        {"id": "session-2", "title": "Session 2", "updated_at": "2026-04-08T11:00:00+00:00"},
    ]

    monkeypatch.setattr(
        chat_persistence,
        "_redis_get_json",
        lambda key: cached_sessions if key == chat_persistence._SESSION_INDEX_KEY else None,
    )

    def _fail_get_mongo():
        raise AssertionError("MongoDB should not be hit when Redis cache is warm")

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", _fail_get_mongo)

    result = chat_persistence.db_load_sessions()

    assert result == cached_sessions


def test_db_load_sessions_falls_back_to_mongodb(monkeypatch):
    """Test db_load_sessions falls back to MongoDB when Redis cache is cold."""
    mongo_sessions = [
        {"id": "session-1", "title": "Session 1", "updated_at": "2026-04-08T12:00:00+00:00"},
        {"id": "session-2", "title": "Session 2", "updated_at": "2026-04-08T11:00:00+00:00"},
    ]

    class _FakeCollection:
        def find(self, query, projection=None, sort=None):
            return iter(mongo_sessions)

    fake_mongo = SimpleNamespace(get_collection=lambda _name: _FakeCollection())

    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(chat_persistence, "_redis_get_json", lambda key: None)
    monkeypatch.setattr(chat_persistence, "_redis_set_json", lambda key, value: None)

    result = chat_persistence.db_load_sessions()

    assert len(result) == 2
    assert result[0]["id"] == "session-1"
    assert result[1]["id"] == "session-2"


def test_db_save_message_updates_mongodb(monkeypatch):
    """Test db_save_message upserts message to MongoDB."""
    replace_calls: list[tuple] = []

    class _FakeCollection:
        def replace_one(self, query, document, upsert=False):
            replace_calls.append((query, document, upsert))

        def find(self, query, projection=None, sort=None):
            return iter([])

    fake_mongo = SimpleNamespace(get_collection=lambda _name: _FakeCollection())

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: fake_mongo)
    monkeypatch.setattr(chat_persistence, "_redis_get_json", lambda key: None)
    monkeypatch.setattr(chat_persistence, "_redis_set_json", lambda key, value: None)
    monkeypatch.setattr(chat_persistence, "_publish_chat_event", lambda *args: None)

    msg = {
        "id": "msg-1",
        "session_id": "session-1",
        "role": "gm",
        "content": "Hello",
        "timestamp": "2026-04-08T12:00:00+00:00",
    }

    chat_persistence.db_save_message(msg)

    assert len(replace_calls) == 1
    assert replace_calls[0][0] == {"id": "msg-1"}
    assert replace_calls[0][1] == msg
    assert replace_calls[0][2] is True  # upsert=True


def test_db_save_message_upserts_existing_message(monkeypatch):
    """Test db_save_message replaces existing message in MongoDB."""
    replace_calls: list[tuple] = []

    class _FakeCollection:
        def replace_one(self, query, document, upsert=False):
            replace_calls.append((query, document, upsert))

        def find(self, query, projection=None, sort=None):
            return iter([])

    fake_mongo = SimpleNamespace(get_collection=lambda _name: _FakeCollection())

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: fake_mongo)
    monkeypatch.setattr(chat_persistence, "_redis_get_json", lambda key: None)
    monkeypatch.setattr(chat_persistence, "_redis_set_json", lambda key, value: None)
    monkeypatch.setattr(chat_persistence, "_publish_chat_event", lambda *args: None)

    updated_msg = {
        "id": "msg-1",
        "session_id": "session-1",
        "role": "gm",
        "content": "New content",
        "timestamp": "2026-04-08T11:00:00+00:00",
    }

    chat_persistence.db_save_message(updated_msg)

    assert len(replace_calls) == 1
    assert replace_calls[0][0] == {"id": "msg-1"}
    assert replace_calls[0][1] == updated_msg
    assert replace_calls[0][2] is True  # upsert=True


def test_db_save_message_handles_missing_session_id(monkeypatch):
    """Test db_save_message handles messages without session_id gracefully."""
    redis_writes: dict[str, object] = []

    class _FakeCollection:
        def replace_one(self, query, document, upsert=False):
            pass

    fake_mongo = SimpleNamespace(get_collection=lambda _name: _FakeCollection())

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: fake_mongo)
    monkeypatch.setattr(
        chat_persistence,
        "_redis_get_json",
        lambda key: [] if "messages" in key else None,
    )
    monkeypatch.setattr(
        chat_persistence,
        "_redis_set_json",
        lambda key, value: redis_writes.__setitem__(key, value),
    )
    monkeypatch.setattr(chat_persistence, "_publish_chat_event", lambda *args: None)

    msg = {
        "id": "msg-1",
        "session_id": None,
        "role": "gm",
        "content": "Orphan message",
        "timestamp": "2026-04-08T12:00:00+00:00",
    }

    chat_persistence.db_save_message(msg)

    # Should not write to Redis cache for messages without session_id
    cache_key = chat_persistence._messages_cache_key("")
    assert cache_key not in redis_writes


class TestChatPersistenceHelperFunctions:
    """Tests for chat persistence helper functions."""

    def test_session_cache_key_format(self):
        """_session_cache_key should generate correct key format."""
        key = chat_persistence._session_cache_key("session-123")
        assert key == "chat_session:session-123"

    def test_messages_cache_key_format(self):
        """_messages_cache_key should generate correct key format."""
        key = chat_persistence._messages_cache_key("session-456")
        assert key == "chat_messages:session-456"

    def test_session_index_key(self):
        """_SESSION_INDEX_KEY should be defined."""
        assert chat_persistence._SESSION_INDEX_KEY == "chat_sessions:index"

    def test_cache_key_with_special_characters(self):
        """_session_cache_key should handle special characters in session_id."""
        key = chat_persistence._session_cache_key("session-with-dashes")
        assert "session-with-dashes" in key

    def test_cache_key_with_uuid_format(self):
        """_session_cache_key should handle UUID-style session IDs."""
        uuid_session = "550e8400-e29b-41d4-a716-446655440000"
        key = chat_persistence._session_cache_key(uuid_session)
        assert uuid_session in key


class TestChatPersistenceEventPublishing:
    """Tests for chat event publishing functionality."""

    def test_publish_chat_event_signature(self):
        """_publish_chat_event should accept session_id, event_type, and payload."""
        # Just verify the function exists and has correct signature
        import inspect
        sig = inspect.signature(chat_persistence._publish_chat_event)
        params = list(sig.parameters.keys())
        assert "session_id" in params
        assert "event_type" in params
        assert "payload" in params

    def test_publish_chat_event_is_callable(self):
        """_publish_chat_event should be callable."""
        assert callable(chat_persistence._publish_chat_event)

from __future__ import annotations

from monitor_data.db.redis import RedisClient, clear_runtime_cache


class _FakePubSub:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._channels: list[str] = []

    def subscribe(self, *channels: str) -> None:
        self._channels.extend(channels)

    def get_message(self, timeout: float = 0.0):  # noqa: ARG002
        for channel in self._channels:
            key = f"pub:{channel}"
            if key in self._redis.store:
                return {"type": "message", "data": self._redis.store.pop(key)}
        return None

    def close(self) -> None:
        return None


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    @classmethod
    def from_url(cls, *args, **kwargs):  # noqa: ANN002, ANN003
        return cls()

    def ping(self) -> bool:
        return True

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> bool:  # noqa: ARG002
        self.store[key] = value
        return True

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                deleted += 1
        return deleted

    def publish(self, channel: str, value: str) -> int:
        self.store[f"pub:{channel}"] = value
        return 1

    def pubsub(self, ignore_subscribe_messages: bool = True):  # noqa: ARG002
        return _FakePubSub(self)

    def scan_iter(self, match: str):
        prefix = match[:-1] if match.endswith("*") else match
        for key in list(self.store):
            if key.startswith(prefix):
                yield key

    def close(self) -> None:
        return None


def test_redis_client_round_trips_json(monkeypatch):
    monkeypatch.setattr("monitor_data.db.redis.Redis", _FakeRedis)

    client = RedisClient(
        url="redis://example", enabled=True, key_prefix="monitor-test", default_ttl=10
    )

    assert client.set_json("solo_play:scene_summary:abc", {"summary": "Fast cache"}) is True
    assert client.get_json("solo_play:scene_summary:abc") == {"summary": "Fast cache"}


def test_redis_client_degrades_gracefully_without_backend(monkeypatch):
    monkeypatch.setattr("monitor_data.db.redis.Redis", None)

    client = RedisClient(url="redis://example", enabled=True)

    assert client.is_available() is False
    assert client.get_json("missing") is None
    assert client.set_json("missing", {"ok": True}) is False
    assert client.delete_prefix("solo_play:") == 0


def test_clear_runtime_cache_accepts_multiple_prefixes(monkeypatch):
    monkeypatch.setattr("monitor_data.db.redis.Redis", _FakeRedis)
    client = RedisClient(
        url="redis://example", enabled=True, key_prefix="monitor-test", default_ttl=10
    )
    monkeypatch.setattr("monitor_data.db.redis.get_redis_client", lambda: client)

    client.set_json("solo_play:scene_summary:1", {"ok": True})
    client.set_json("chat_messages:session-1", [{"id": "m1"}])

    cleared = clear_runtime_cache(("solo_play:", "chat_messages:"))

    assert cleared == 2


def test_redis_client_pubsub_round_trips_json(monkeypatch):
    monkeypatch.setattr("monitor_data.db.redis.Redis", _FakeRedis)

    client = RedisClient(
        url="redis://example", enabled=True, key_prefix="monitor-test", default_ttl=10
    )
    pubsub = client.create_pubsub("chat_events:session-1")

    assert pubsub is not None
    assert (
        client.publish_json(
            "chat_events:session-1", {"event_type": "ws_fanout", "payload": {"type": "done"}}
        )
        == 1
    )
    assert client.get_pubsub_message_json(pubsub) == {
        "event_type": "ws_fanout",
        "payload": {"type": "done"},
    }

    client.close_pubsub(pubsub)

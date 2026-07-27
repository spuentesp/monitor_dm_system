"""
Fake Redis client for unit tests.

Mirrors the interface of the Redis client used by MONITOR.
Supports get, set, delete, exists, expire, ttl, pub/sub.

Usage::

    from tests.mocks.db.redis import FakeRedisClient

    client = FakeRedisClient()
    await client.set("key", "value", ex=30)
    value = await client.get("key")
"""

from __future__ import annotations

import time
from typing import Any


class FakePubSub:
    """Fake Redis pub/sub channel."""

    def __init__(self) -> None:
        self._messages: list[dict[str, Any]] = []
        self._subscribed: set[str] = set()

    async def subscribe(self, *channels: str) -> None:
        self._subscribed.update(channels)

    async def unsubscribe(self, *channels: str) -> None:
        for ch in channels:
            self._subscribed.discard(ch)

    async def publish(self, channel: str, message: str) -> int:
        self._messages.append({"channel": channel, "data": message})
        return 1

    async def get_message(self, timeout: float = 1.0) -> dict[str, Any] | None:
        if self._messages:
            return self._messages.pop(0)
        return None

    async def close(self) -> None:
        self._messages.clear()
        self._subscribed.clear()


class FakeRedisClient:
    """In-memory Redis client for unit tests.

    Supports strings, expiry, and pub/sub.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[str | bytes, float | None]] = {}
        self._pubsub = FakePubSub()

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        if key not in self._data:
            return None
        value, expires_at = self._data[key]
        if expires_at is not None and time.time() > expires_at:
            del self._data[key]
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    async def set(
        self, key: str, value: str | bytes, ex: int | None = None, **kwargs: Any
    ) -> bool:
        """Set a key-value pair with optional expiry (seconds)."""
        expires_at = time.time() + ex if ex else None
        if isinstance(value, str):
            value = value.encode("utf-8")
        self._data[key] = (value, expires_at)
        return True

    async def delete(self, *keys: str) -> int:
        """Delete keys. Returns count deleted."""
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
        return count

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        if key not in self._data:
            return False
        _, expires_at = self._data[key]
        if expires_at is not None and time.time() > expires_at:
            del self._data[key]
            return False
        return True

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiry on a key."""
        if key not in self._data:
            return False
        value, _ = self._data[key]
        self._data[key] = (value, time.time() + seconds)
        return True

    async def ttl(self, key: str) -> int:
        """Get TTL in seconds (-1 if no expiry, -2 if not exists)."""
        if key not in self._data:
            return -2
        _, expires_at = self._data[key]
        if expires_at is None:
            return -1
        remaining = int(expires_at - time.time())
        if remaining <= 0:
            del self._data[key]
            return -2
        return remaining

    async def incr(self, key: str) -> int:
        """Increment a key."""
        value = await self.get(key)
        new_value = int(value) + 1 if value else 1
        await self.set(key, str(new_value))
        return new_value

    async def flushdb(self) -> None:
        """Clear all keys."""
        self._data.clear()

    def pubsub(self) -> FakePubSub:
        """Return a pub/sub handle."""
        return self._pubsub

    def reset(self) -> None:
        """Clear all data."""
        self._data.clear()
        self._pubsub = FakePubSub()


def make_mock_redis_client() -> FakeRedisClient:
    """Return a FakeRedisClient."""
    return FakeRedisClient()

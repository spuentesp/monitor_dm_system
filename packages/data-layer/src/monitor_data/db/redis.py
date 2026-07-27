"""
Redis runtime cache client for MONITOR.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (redis-py)
CALLED BY: agents and UI surfaces that need hot-path caching, locks, or pub/sub

Redis is **optional** and is never the source of truth. If `REDIS_URL` is not
configured, the package is not installed, or the server is unavailable, every
operation degrades to a no-op so the system keeps using MongoDB/Neo4j/Qdrant
normally.
"""

from __future__ import annotations

import importlib
import json
import logging
import threading
from contextlib import suppress
from typing import Any

from monitor_data.config import settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised via monkeypatch in tests when redis is absent
    Redis = importlib.import_module("redis").Redis
except Exception:
    Redis = None


class RedisClient:
    """Thin synchronous wrapper for ephemeral runtime caching."""

    def __init__(
        self,
        url: str | None = None,
        *,
        enabled: bool | None = None,
        key_prefix: str | None = None,
        default_ttl: int | None = None,
    ) -> None:
        self._url = url or settings.redis_url
        self._enabled = settings.redis_enabled if enabled is None else enabled
        prefix = (key_prefix or settings.redis_key_prefix or "monitor").strip() or "monitor"
        self._prefix = prefix if prefix.endswith(":") else f"{prefix}:"
        self._default_ttl = max(1, int(default_ttl or settings.redis_cache_ttl_seconds or 30))
        self._client: Any = None
        self._connect_lock = threading.Lock()
        self._logged_unavailable = False
        self._connection_attempted = False

    def _qualified_key(self, key: str) -> str:
        cleaned = (key or "").strip().lstrip(":")
        if cleaned.startswith(self._prefix):
            return cleaned
        return f"{self._prefix}{cleaned}"

    def _get_client(self) -> Any:
        if not self._enabled or not self._url:
            return None
        if Redis is None:
            if not self._logged_unavailable:
                logger.info("Redis cache disabled: redis-py is not installed")
                self._logged_unavailable = True
            return None
        if self._client is not None:
            return self._client
        if self._connection_attempted and self._logged_unavailable:
            return None

        with self._connect_lock:
            if self._client is not None:
                return self._client
            if self._connection_attempted and self._logged_unavailable:
                return None
            try:
                client = Redis.from_url(
                    self._url,
                    decode_responses=True,
                    socket_timeout=settings.redis_socket_timeout,
                    socket_connect_timeout=settings.redis_connect_timeout,
                    health_check_interval=30,
                )
                client.ping()
                self._client = client
                self._connection_attempted = True
            except Exception as exc:
                self._connection_attempted = True
                if not self._logged_unavailable:
                    logger.info("Redis cache unavailable, falling back to direct DB reads: %s", exc)
                    self._logged_unavailable = True
                self._client = None
        return self._client

    def is_available(self) -> bool:
        """Return True when Redis is configured and reachable."""
        return self._get_client() is not None

    def get_json(self, key: str) -> Any | None:
        """Load a JSON payload from Redis, returning None on miss/failure."""
        client = self._get_client()
        if client is None:
            return None
        try:
            raw = client.get(self._qualified_key(key))
            if raw in (None, ""):
                return None
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Redis JSON decode failed for %s: %s", key, exc)
            return None
        except Exception as exc:
            logger.debug("Redis get_json failed for %s: %s", key, exc)
            return None

    def set_json(self, key: str, value: Any, *, ttl: int | None = None) -> bool:
        """Store a JSON-serialisable payload with TTL. Returns True on success."""
        client = self._get_client()
        if client is None:
            return False
        try:
            client.setex(
                self._qualified_key(key),
                max(1, int(ttl or self._default_ttl)),
                json.dumps(value, default=str),
            )
            return True
        except (TypeError, ValueError) as exc:
            logger.warning("Redis set_json serialisation failed for %s: %s", key, exc)
            return False
        except Exception as exc:
            logger.debug("Redis set_json failed for %s: %s", key, exc)
            return False

    def delete(self, *keys: str) -> int:
        """Delete a fixed set of keys and return the number removed."""
        client = self._get_client()
        if client is None or not keys:
            return 0
        qualified = [self._qualified_key(key) for key in keys if key]
        if not qualified:
            return 0
        try:
            return int(client.delete(*qualified))
        except Exception as exc:
            logger.debug("Redis delete failed for %s: %s", qualified, exc)
            return 0

    def publish_json(self, channel: str, value: Any) -> int:
        """Publish a JSON payload to a Redis channel. Returns subscriber count."""
        client = self._get_client()
        if client is None:
            return 0
        try:
            return int(client.publish(self._qualified_key(channel), json.dumps(value, default=str)))
        except Exception as exc:
            logger.debug("Redis publish_json failed for %s: %s", channel, exc)
            return 0

    def create_pubsub(self, *channels: str) -> Any | None:
        """Open a pub/sub subscription for one or more JSON channels."""
        client = self._get_client()
        if client is None or not channels:
            return None
        try:
            qualified = [self._qualified_key(channel) for channel in channels if channel]
            if not qualified:
                return None
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(*qualified)
            return pubsub
        except Exception as exc:
            logger.debug("Redis create_pubsub failed for %s: %s", channels, exc)
            return None

    def get_pubsub_message_json(self, pubsub: Any, *, timeout: float = 1.0) -> Any | None:
        """Read and decode a single JSON pub/sub message."""
        if pubsub is None:
            return None
        try:
            message = pubsub.get_message(timeout=timeout)
            if not message or message.get("type") != "message":
                return None
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if data in (None, ""):
                return None
            return json.loads(data)
        except Exception as exc:
            logger.debug("Redis get_pubsub_message_json failed: %s", exc)
            return None

    def close_pubsub(self, pubsub: Any) -> None:
        """Close a pub/sub handle if one exists."""
        if pubsub is None:
            return
        with suppress(Exception):
            pubsub.close()

    def delete_prefix(self, prefix: str) -> int:
        """Delete every key under a prefix, e.g. `solo_play:`."""
        client = self._get_client()
        if client is None:
            return 0
        match = f"{self._qualified_key(prefix)}*"
        deleted = 0
        try:
            keys = list(client.scan_iter(match=match))
            if keys:
                deleted = int(client.delete(*keys))
            return deleted
        except Exception as exc:
            logger.debug("Redis delete_prefix failed for %s: %s", prefix, exc)
            return 0

    def close(self) -> None:
        """Close the underlying client if one exists."""
        client = self._client
        self._client = None
        self._connection_attempted = False
        self._logged_unavailable = False
        if client is None:
            return
        with suppress(Exception):
            client.close()


_redis_client_instance: RedisClient | None = None
_client_lock = threading.Lock()


def get_redis_client() -> RedisClient:
    """Return the module-level RedisClient singleton."""
    global _redis_client_instance
    with _client_lock:
        if _redis_client_instance is None:
            _redis_client_instance = RedisClient()
    return _redis_client_instance


def clear_runtime_cache(
    prefix: str | tuple[str, ...] = (
        "solo_play:",
        "chat_session:",
        "chat_messages:",
        "chat_sessions:",
    ),
) -> int:
    """Best-effort purge of the hot-path runtime cache namespaces."""
    client = get_redis_client()
    if isinstance(prefix, str):
        return client.delete_prefix(prefix)
    return sum(client.delete_prefix(item) for item in prefix)


def reset_redis_client() -> None:
    """Discard the singleton; useful in tests or after config changes."""
    global _redis_client_instance
    with _client_lock:
        if _redis_client_instance is not None:
            _redis_client_instance.close()
            _redis_client_instance = None

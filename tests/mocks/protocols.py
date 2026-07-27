"""
Protocol definitions for 1:1 contract enforcement.

Each Protocol mirrors the public interface of a real class. Fakes that
claim to implement these interfaces must match every method signature.

These are checked at type-check time by mypy and at test time by
contract_check.py.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, Type, TypeVar

T = TypeVar("T")


# =============================================================================
# Database Protocols
# =============================================================================


class MongoDBClientProtocol(Protocol):
    """Interface that any MongoDB client (real or fake) must implement."""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def verify_connectivity(self) -> bool: ...
    def get_database(self) -> Any: ...


class Neo4jClientProtocol(Protocol):
    """Interface that any Neo4j client must implement."""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def verify_connectivity(self) -> bool: ...
    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]: ...
    async def run_read(self, query: str, **params: Any) -> list[dict[str, Any]]: ...
    async def run_write(self, query: str, **params: Any) -> list[dict[str, Any]]: ...


class PostgresClientProtocol(Protocol):
    """Interface that any Postgres client must implement."""

    async def providers_list(self) -> list[dict[str, Any]]: ...
    async def effective_llm_for_node(self, node_name: str) -> dict[str, Any]: ...
    async def node_assignment_get(self, node_name: str) -> dict[str, Any] | None: ...
    async def provider_get(self, provider_id: str) -> dict[str, Any] | None: ...
    async def provider_upsert(self, provider: dict[str, Any]) -> dict[str, Any]: ...
    async def node_assignment_upsert(
        self, assignment: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def setting_get(self, key: str) -> str | None: ...
    async def setting_set(self, key: str, value: str) -> None: ...


class QdrantClientProtocol(Protocol):
    """Interface that any Qdrant client must implement."""

    async def create_collection(self, collection_name: str, **kwargs: Any) -> None: ...
    async def delete_collection(self, collection_name: str) -> None: ...
    async def upsert(
        self, collection_name: str, points: list[dict[str, Any]], **kwargs: Any
    ) -> None: ...
    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]: ...
    async def delete(
        self, collection_name: str, points_selector: list[str], **kwargs: Any
    ) -> None: ...


class MinIOClientProtocol(Protocol):
    """Interface that any MinIO/S3 client must implement."""

    async def upload(
        self,
        object_name: str,
        data: bytes,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str: ...
    async def download(self, object_name: str) -> bytes: ...
    async def delete(self, object_name: str) -> None: ...
    async def exists(self, object_name: str) -> bool: ...
    async def list_objects(self, prefix: str = "") -> list[str]: ...


class RedisClientProtocol(Protocol):
    """Interface that any Redis client must implement."""

    async def get(self, key: str) -> str | None: ...
    async def set(
        self, key: str, value: str | bytes, ex: int | None = None, **kwargs: Any
    ) -> bool: ...
    async def delete(self, *keys: str) -> int: ...
    async def exists(self, key: str) -> bool: ...
    async def expire(self, key: str, seconds: int) -> bool: ...
    async def ttl(self, key: str) -> int: ...


# =============================================================================
# Agent Protocols
# =============================================================================


class LLMClientProtocol(Protocol):
    """Interface that any LLM client must implement."""

    model: str
    provider: Any
    params: dict[str, Any]
    api_key: str
    base_url: str | None
    prompt_version: str | None

    async def create(
        self,
        response_model: type[T],
        messages: list[dict[str, Any]],
        **override_params: Any,
    ) -> T: ...
    async def complete_text(
        self, messages: list[dict[str, Any]], **override_params: Any
    ) -> str: ...


class LLMRegistryProtocol(Protocol):
    """Interface that any LLM registry must implement."""

    async def for_node(self, node_name: str) -> Any: ...
    async def for_role(self, role: Any) -> Any: ...
    async def for_node_or_role(self, node_name: str, role: Any) -> Any: ...
    async def default_client(self) -> Any: ...
    def clear_cache(self) -> None: ...


class MCPClientProtocol(Protocol):
    """Interface that any MCP client must implement."""

    async def call(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any: ...

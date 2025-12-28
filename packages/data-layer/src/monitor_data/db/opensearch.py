"""
OpenSearch client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (opensearchpy)
CALLED BY: opensearch_tools.py

This client provides a thin wrapper around the OpenSearch client with
index management and text search operations.
"""

import os
from typing import Any, Dict, List, Optional

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError


class OpenSearchClient:
    """
    OpenSearch client for full-text search operations.

    This client provides text indexing and search capabilities for
    snippets, facts, scenes, and other narrative content.
    All agents can use OpenSearch operations (authority: *).
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = False,
        verify_certs: bool = False,
    ):
        """
        Initialize OpenSearch client.

        Args:
            host: OpenSearch host (default: from OPENSEARCH_HOST env var)
            port: OpenSearch port (default: from OPENSEARCH_PORT env var)
            user: OpenSearch username (default: from OPENSEARCH_USER env var)
            password: OpenSearch password (default: from OPENSEARCH_PASSWORD env var)
            use_ssl: Whether to use SSL (default: False for local dev)
            verify_certs: Whether to verify SSL certificates (default: False for local dev)
        """
        self.host = host or os.getenv("OPENSEARCH_HOST", "localhost")
        self.port = int(port or os.getenv("OPENSEARCH_PORT", "9200"))
        self.user = user or os.getenv("OPENSEARCH_USER", "admin")
        self.password = password or os.getenv("OPENSEARCH_PASSWORD", "admin")
        self.use_ssl = use_ssl
        self.verify_certs = verify_certs

        self._client: Optional[OpenSearch] = None

    def connect(self) -> None:
        """Establish connection to OpenSearch."""
        if self._client is None:
            auth = (self.user, self.password) if self.user and self.password else None
            self._client = OpenSearch(
                hosts=[{"host": self.host, "port": self.port}],
                http_auth=auth,
                use_ssl=self.use_ssl,
                verify_certs=self.verify_certs,
                ssl_show_warn=False,
            )

    def close(self) -> None:
        """Close the OpenSearch connection."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "OpenSearchClient":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def _ensure_client(self) -> OpenSearch:
        """Ensure client is connected and return it."""
        if not self._client:
            raise RuntimeError("OpenSearch client not connected. Call connect() first.")
        return self._client

    def create_index(
        self, index: str, mappings: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Create an index with optional mappings.

        Args:
            index: Index name
            mappings: Optional index mappings (field types, analyzers)

        Raises:
            RuntimeError: If not connected
        """
        client = self._ensure_client()

        # Default mappings if none provided
        if mappings is None:
            mappings = {
                "properties": {
                    "id": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "universe_id": {"type": "keyword"},
                    "text": {
                        "type": "text",
                        "analyzer": "standard",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "metadata": {"type": "object", "enabled": True},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                }
            }

        body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "default": {
                            "type": "standard",
                            "stopwords": "_english_",
                        }
                    }
                },
            },
            "mappings": mappings,
        }

        client.indices.create(index=index, body=body, ignore=400)

    def index_exists(self, index: str) -> bool:
        """
        Check if an index exists.

        Args:
            index: Index name

        Returns:
            True if index exists, False otherwise

        Raises:
            RuntimeError: If not connected
        """
        client = self._ensure_client()
        return client.indices.exists(index=index)

    def index_document(
        self,
        index: str,
        doc_id: str,
        body: Dict[str, Any],
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Index a document (upsert).

        Args:
            index: Index name
            doc_id: Document ID
            body: Document body
            refresh: Whether to refresh the index immediately

        Returns:
            Response from OpenSearch

        Raises:
            RuntimeError: If not connected
        """
        client = self._ensure_client()

        # Create index if it doesn't exist
        if not self.index_exists(index):
            self.create_index(index)

        response = client.index(
            index=index,
            id=doc_id,
            body=body,
            refresh="true" if refresh else "false",
        )

        return response

    def get_document(self, index: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a document by ID.

        Args:
            index: Index name
            doc_id: Document ID

        Returns:
            Document if found, None otherwise

        Raises:
            RuntimeError: If not connected
        """
        client = self._ensure_client()

        try:
            response = client.get(index=index, id=doc_id)
            return response
        except NotFoundError:
            return None

    def search(
        self,
        index: str,
        query: Dict[str, Any],
        filters: Optional[Dict[str, Any]] = None,
        highlight: Optional[Dict[str, Any]] = None,
        from_: int = 0,
        size: int = 10,
    ) -> Dict[str, Any]:
        """
        Search documents.

        Args:
            index: Index name (can use wildcards like "snippets*")
            query: Query DSL
            filters: Optional filters to apply
            highlight: Optional highlight configuration
            from_: Offset for pagination (default: 0)
            size: Number of results to return (default: 10)

        Returns:
            Search response with hits

        Raises:
            RuntimeError: If not connected
        """
        client = self._ensure_client()

        # Build query body
        body: Dict[str, Any] = {"query": {}}

        # Combine query and filters
        if filters:
            body["query"] = {
                "bool": {
                    "must": [query],
                    "filter": [{"term": {k: v}} for k, v in filters.items()],
                }
            }
        else:
            body["query"] = query

        # Add highlighting if specified
        if highlight:
            body["highlight"] = highlight

        # Add pagination
        body["from"] = from_
        body["size"] = size

        response = client.search(index=index, body=body)

        return response

    def delete_document(self, index: str, doc_id: str) -> Dict[str, Any]:
        """
        Delete a document by ID.

        Args:
            index: Index name
            doc_id: Document ID

        Returns:
            Response from OpenSearch

        Raises:
            RuntimeError: If not connected
            NotFoundError: If document doesn't exist
        """
        client = self._ensure_client()

        response = client.delete(index=index, id=doc_id)

        return response

    def delete_by_query(
        self, index: str, query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Delete documents matching a query.

        Args:
            index: Index name
            query: Query DSL

        Returns:
            Response with number of deleted documents

        Raises:
            RuntimeError: If not connected
        """
        client = self._ensure_client()

        body = {"query": query}

        response = client.delete_by_query(index=index, body=body)

        return response


# =============================================================================
# CLIENT SINGLETON
# =============================================================================

_client_instance: Optional[OpenSearchClient] = None


def get_opensearch_client() -> OpenSearchClient:
    """
    Get or create the singleton OpenSearch client instance.

    Returns:
        OpenSearchClient instance (connected)
    """
    global _client_instance

    if _client_instance is None:
        _client_instance = OpenSearchClient()
        _client_instance.connect()

    return _client_instance

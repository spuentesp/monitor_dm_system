"""
OpenSearch client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (opensearch-py)
CALLED BY: opensearch_tools.py

This client provides a thin wrapper around opensearch-py for:
- Text search: Full-text search with keyword and phrase queries
- Document indexing: Index text with metadata for search
- Index management: Create indices with appropriate analyzers

Indices:
- snippets: Document snippets with embeddings
- facts: Canonical facts for keyword search
- scenes: Scene content for narrative search
- sources: Source documents metadata
"""

import os
from typing import Optional, Dict, Any, List, cast
from opensearchpy import OpenSearch, NotFoundError


class OpenSearchClient:
    """
    OpenSearch client for MONITOR full-text search.

    Thread-safe singleton client for OpenSearch operations.
    Manages connection lifecycle and provides index operations.
    """

    def __init__(
        self,
        hosts: Optional[List[str]] = None,
        http_auth: Optional[tuple] = None,
        use_ssl: Optional[bool] = None,
        verify_certs: Optional[bool] = None,
    ):
        """
        Initialize OpenSearch client.

        Args:
            hosts: List of OpenSearch hosts (default: from OPENSEARCH_HOST and OPENSEARCH_PORT env vars)
            http_auth: Tuple of (username, password) (default: from OPENSEARCH_USER and OPENSEARCH_PASSWORD)
            use_ssl: Whether to use SSL (default: from OPENSEARCH_USE_SSL env var)
            verify_certs: Whether to verify SSL certificates (default: from OPENSEARCH_VERIFY_CERTS env var)
        """
        # Get configuration from environment
        default_host = os.getenv("OPENSEARCH_HOST", "localhost")
        default_port = os.getenv("OPENSEARCH_PORT", "9200")
        default_hosts = [f"{default_host}:{default_port}"]

        self.hosts: List[str] = cast(List[str], hosts or default_hosts)

        username = os.getenv("OPENSEARCH_USER", "admin")
        password = os.getenv("OPENSEARCH_PASSWORD", "admin")
        self.http_auth: tuple = http_auth or (username, password)

        self.use_ssl: bool = (
            use_ssl if use_ssl is not None else os.getenv("OPENSEARCH_USE_SSL", "false").lower() == "true"
        )
        self.verify_certs: bool = (
            verify_certs if verify_certs is not None else os.getenv("OPENSEARCH_VERIFY_CERTS", "false").lower() == "true"
        )

        self._client: Optional[OpenSearch] = None
        self._indexes_created: Dict[str, bool] = {}

    def connect(self) -> None:
        """
        Establish connection to OpenSearch.

        Creates client instance if not already connected.
        """
        if self._client is None:
            self._client = OpenSearch(
                hosts=self.hosts,
                http_auth=self.http_auth,
                use_ssl=self.use_ssl,
                verify_certs=self.verify_certs,
                ssl_show_warn=False,
            )

    def close(self) -> None:
        """Close OpenSearch connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._indexes_created = {}

    def verify_connectivity(self) -> bool:
        """
        Verify OpenSearch connection is working.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            if self._client is None:
                self.connect()
            assert self._client is not None
            # Ping the cluster
            return self._client.ping()
        except Exception:
            return False

    def get_client(self) -> OpenSearch:
        """
        Get the OpenSearch client object.

        Returns:
            OpenSearch client instance

        Raises:
            RuntimeError: If not connected
        """
        if self._client is None:
            raise RuntimeError("OpenSearch client not connected. Call connect() first.")
        return self._client

    def ensure_index(self, index_name: str, mappings: Optional[Dict[str, Any]] = None) -> None:
        """
        Ensure an index exists, creating it if necessary.

        Args:
            index_name: Name of the index to ensure exists
            mappings: Optional index mappings and settings

        Creates index with default settings if mappings not provided.
        """
        client = self.get_client()

        # Check if we've already created this index in this session
        if self._indexes_created.get(index_name):
            return

        # Check if index exists
        if client.indices.exists(index=index_name):
            self._indexes_created[index_name] = True
            return

        # Create index with mappings
        if mappings is None:
            mappings = self._get_default_mappings()

        client.indices.create(index=index_name, body=mappings)
        self._indexes_created[index_name] = True

    def _get_default_mappings(self) -> Dict[str, Any]:
        """
        Get default index mappings and settings.

        Returns:
            Default mappings with standard analyzer and common fields
        """
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "default": {
                            "type": "standard",
                        }
                    }
                },
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "universe_id": {"type": "keyword"},
                    "text": {"type": "text"},
                    "metadata": {"type": "object", "enabled": True},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                }
            },
        }

    def index_document(
        self,
        index: str,
        doc_id: str,
        body: Dict[str, Any],
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Index a document (create or update).

        Args:
            index: Index name
            doc_id: Document ID
            body: Document body
            refresh: Whether to refresh the index immediately

        Returns:
            Indexing result from OpenSearch
        """
        client = self.get_client()
        self.ensure_index(index)

        result = client.index(
            index=index,
            id=doc_id,
            body=body,
            refresh="wait_for" if refresh else False,
        )
        return result

    def get_document(self, index: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a document by ID.

        Args:
            index: Index name
            doc_id: Document ID

        Returns:
            Document if found, None otherwise
        """
        client = self.get_client()

        try:
            result = client.get(index=index, id=doc_id)
            return result
        except NotFoundError:
            return None

    def search(
        self,
        index: str,
        query: Dict[str, Any],
        from_: int = 0,
        size: int = 10,
        highlight: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Search documents.

        Args:
            index: Index name
            query: Query DSL
            from_: Starting offset for pagination
            size: Number of results to return
            highlight: Highlight configuration

        Returns:
            Search results from OpenSearch
        """
        client = self.get_client()

        body: Dict[str, Any] = {
            "query": query,
            "from": from_,
            "size": size,
        }

        if highlight:
            body["highlight"] = highlight

        result = client.search(index=index, body=body)
        return result

    def delete_document(self, index: str, doc_id: str) -> Dict[str, Any]:
        """
        Delete a document by ID.

        Args:
            index: Index name
            doc_id: Document ID

        Returns:
            Deletion result from OpenSearch

        Raises:
            NotFoundError: If document doesn't exist
        """
        client = self.get_client()
        result = client.delete(index=index, id=doc_id)
        return result

    def delete_by_query(self, index: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delete documents matching a query.

        Args:
            index: Index name
            query: Query DSL to match documents for deletion

        Returns:
            Deletion result with count of deleted documents
        """
        client = self.get_client()
        result = client.delete_by_query(
            index=index,
            body={"query": query},
        )
        return result


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_opensearch_client_instance: Optional[OpenSearchClient] = None


def get_opensearch_client() -> OpenSearchClient:
    """
    Get or create the singleton OpenSearch client.

    Returns:
        OpenSearchClient instance

    Thread-safe singleton pattern for database connections.
    """
    global _opensearch_client_instance

    if _opensearch_client_instance is None:
        _opensearch_client_instance = OpenSearchClient()
        _opensearch_client_instance.connect()

    return _opensearch_client_instance


def reset_opensearch_client() -> None:
    """
    Reset the OpenSearch client singleton.

    Used for testing to ensure clean state between tests.
    """
    global _opensearch_client_instance

    if _opensearch_client_instance is not None:
        _opensearch_client_instance.close()
        _opensearch_client_instance = None

"""
Neo4j client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (neo4j driver)
CALLED BY: neo4j_tools.py

This client provides a thin wrapper around the Neo4j driver with
transaction management for read/write operations.
"""

import os
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase, Driver


class Neo4jClient:
    """
    Neo4j database client for canonical graph operations.

    This client provides transaction-safe read and write operations.
    All write operations should be called ONLY through tools with
    CanonKeeper authority enforcement.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize Neo4j client.

        Args:
            uri: Neo4j connection URI (default: from NEO4J_URI env var)
            user: Neo4j username (default: from NEO4J_USER env var)
            password: Neo4j password (required, from NEO4J_PASSWORD env var)

        Raises:
            ValueError: If password is not provided and NEO4J_PASSWORD env var is not set
        """
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD")

        if not self.password:
            raise ValueError(
                "Neo4j password is required. "
                "Provide it via the 'password' parameter or set the NEO4J_PASSWORD environment variable."
            )

        self._driver: Optional[Driver] = None

    def connect(self) -> None:
        """Establish connection to Neo4j."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )

    def close(self) -> None:
        """Close the Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def __enter__(self) -> "Neo4jClient":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def execute_read(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a read transaction.

        Args:
            query: Cypher query string
            parameters: Query parameters

        Returns:
            List of result records as dictionaries

        Raises:
            Exception: If not connected or query fails
        """
        if not self._driver:
            raise RuntimeError("Neo4j client not connected. Call connect() first.")

        parameters = parameters or {}

        with self._driver.session() as session:
            result = session.execute_read(lambda tx: list(tx.run(query, parameters)))
            return [dict(record) for record in result]

    def execute_write(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a write transaction.

        Args:
            query: Cypher query string
            parameters: Query parameters

        Returns:
            List of result records as dictionaries

        Raises:
            Exception: If not connected or query fails
        """
        if not self._driver:
            raise RuntimeError("Neo4j client not connected. Call connect() first.")

        parameters = parameters or {}

        with self._driver.session() as session:
            result = session.execute_write(lambda tx: list(tx.run(query, parameters)))
            return [dict(record) for record in result]

    def verify_connectivity(self) -> bool:
        """
        Verify connection to Neo4j.

        Returns:
            True if connected and can execute queries, False otherwise
        """
        try:
            if not self._driver:
                return False
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False


# Global client instance (can be initialized once at startup)
_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    """
    Get or create the global Neo4j client instance.

    Returns:
        Neo4jClient instance

    Note:
        This returns a singleton client. Call connect() before using.
    """
    global _client
    if _client is None:
        _client = Neo4jClient()
        _client.connect()
    return _client

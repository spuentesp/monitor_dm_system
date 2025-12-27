"""
Neo4j client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only

Provides connection and query execution for Neo4j canonical graph database.
"""

import os
from typing import Any, Optional

from neo4j import GraphDatabase, Driver, Session


class Neo4jClient:
    """
    Client for interacting with Neo4j graph database.
    
    This client provides connection management and query execution
    for the canonical truth layer.
    
    WRITE AUTHORITY: CanonKeeper agent only (enforced at tool level)
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
            uri: Neo4j connection URI (defaults to NEO4J_URI env var)
            user: Neo4j username (defaults to NEO4J_USER env var)
            password: Neo4j password (defaults to NEO4J_PASSWORD env var)
        """
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "neo4j")
        
        self._driver: Optional[Driver] = None
    
    def connect(self) -> None:
        """Establish connection to Neo4j."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
    
    def close(self) -> None:
        """Close connection to Neo4j."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def execute_read(self, query: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        """
        Execute a read query.
        
        Args:
            query: Cypher query string
            params: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        if self._driver is None:
            self.connect()
        
        with self._driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]
    
    def execute_write(self, query: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        """
        Execute a write query.
        
        Args:
            query: Cypher query string
            params: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        if self._driver is None:
            self.connect()
        
        with self._driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]
    
    def verify_connection(self) -> bool:
        """
        Verify connection to Neo4j.
        
        Returns:
            True if connection is successful
        """
        try:
            if self._driver is None:
                self.connect()
            
            with self._driver.session() as session:
                result = session.run("RETURN 1 as num")
                record = result.single()
                return record["num"] == 1
        except Exception:
            return False

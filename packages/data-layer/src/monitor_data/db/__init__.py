"""
Database clients for MONITOR Data Layer.

This module provides thin client wrappers around database drivers:
- Neo4jClient:      Canonical graph (truth layer)
- MongoDBClient:    Narrative documents (scenes, turns, proposals)
- QdrantClient:     Vector embeddings (semantic search)
- MinIOClient:      Binary storage (PDFs, images)
- OpenSearchClient: Full-text search (keyword/phrase queries)

WRITE AUTHORITY (enforced at tool level, not here):
- Neo4j:      CanonKeeper only
- MongoDB:    Orchestrator, Narrator, Resolver, MemoryManager
- Qdrant:     Indexer only
- MinIO:      Ingest pipeline only
- OpenSearch: All agents (*)
"""

from monitor_data.db.neo4j import Neo4jClient, get_neo4j_client
from monitor_data.db.opensearch import OpenSearchClient, get_opensearch_client

# from monitor_data.db.mongodb import MongoDBClient
# from monitor_data.db.qdrant import QdrantClient
# from monitor_data.db.minio import MinIOClient

__all__ = [
    "Neo4jClient",
    "get_neo4j_client",
    "OpenSearchClient",
    "get_opensearch_client",
    # "MongoDBClient",
    # "QdrantClient",
    # "MinIOClient",
]

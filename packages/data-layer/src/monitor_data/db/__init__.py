"""
Database clients for MONITOR Data Layer.

This module provides thin client wrappers around database drivers:
- Neo4jClient:   Canonical graph (truth layer)
- MongoDBClient: Narrative documents (scenes, turns, proposals)
- QdrantClient:  Vector embeddings (semantic search)
- MinIOClient:   Binary storage (PDFs, images)

WRITE AUTHORITY (enforced at tool level, not here):
- Neo4j:  CanonKeeper only
- MongoDB: Orchestrator, Narrator, Resolver, MemoryManager
- Qdrant: Indexer only
- MinIO:  Ingest pipeline only
"""

from monitor_data.db.neo4j import Neo4jClient

__all__ = [
    "Neo4jClient",
    # "MongoDBClient",
    # "QdrantClient",
    # "MinIOClient",
]

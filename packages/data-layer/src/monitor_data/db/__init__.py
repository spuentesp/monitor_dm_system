"""
Database clients for MONITOR Data Layer.

This module provides thin client wrappers around database drivers:
- Neo4jClient:   Canonical graph (truth layer)
- MongoDBClient: Narrative documents (scenes, turns, proposals)
- QdrantClient:  Vector embeddings (semantic search)
- MinIOClient:   Binary storage (PDFs, images)
- embed_text / embed_batch: Provider-agnostic text embeddings (LiteLLM)

WRITE AUTHORITY (enforced at tool level, not here):
- Neo4j:  CanonKeeper only
- MongoDB: Orchestrator, Narrator, Resolver, MemoryManager
- Qdrant: Indexer only
- MinIO:  Ingest pipeline only
"""

# Embedding access is gated by monitor_data.retrieval.RetrievalService
# (the only path that calls litellm.aembedding). The db.embeddings
# module no longer exists — see retrieval/embedder.py for the single
# Embedder implementation.

from monitor_data.db.gliner import (
    Entity,
    GLiNERClient,
    extract_entities,
    extract_entities_batch,
    get_gliner_client,
)
from monitor_data.db.minio import MinIOClient, get_minio_client, reset_minio_client
from monitor_data.db.mongodb import (
    MongoDBClient,
    get_mongodb_client,
    reset_mongodb_client,
)
from monitor_data.db.neo4j import Neo4jClient, get_neo4j_client, reset_neo4j_client
from monitor_data.db.qdrant import QdrantClient, get_qdrant_client, reset_qdrant_client
from monitor_data.db.redis import (
    RedisClient,
    clear_runtime_cache,
    get_redis_client,
    reset_redis_client,
)

__all__ = [
    # Neo4j
    "Neo4jClient",
    "get_neo4j_client",
    "reset_neo4j_client",
    # MongoDB
    "MongoDBClient",
    "get_mongodb_client",
    "reset_mongodb_client",
    # Qdrant
    "QdrantClient",
    "get_qdrant_client",
    "reset_qdrant_client",
    # MinIO / S3
    "MinIOClient",
    "get_minio_client",
    "reset_minio_client",
    # Redis runtime cache
    "RedisClient",
    "get_redis_client",
    "reset_redis_client",
    "clear_runtime_cache",
    # Embeddings
    "embed_text",
    "embed_batch",
    # NLP / GLiNER
    "GLiNERClient",
    "Entity",
    "extract_entities",
    "extract_entities_batch",
    "get_gliner_client",
]

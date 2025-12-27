"""
================================================================================
MONITOR Data Layer (Layer 1 of 3)
================================================================================

This is the BOTTOM layer of the MONITOR stack. It provides:
- Database clients for Neo4j, MongoDB, Qdrant, MinIO
- MCP server exposing tools for agents to interact with data
- Pydantic schemas for data validation
- Authority enforcement middleware

ARCHITECTURE RULES:
==================
1. This package has NO dependencies on other MONITOR packages
2. Only Layer 2 (agents) imports from this package
3. Layer 3 (cli) does NOT import directly from this package

IMPORT HIERARCHY:
================
    cli (Layer 3)
         ↓ imports
    agents (Layer 2)
         ↓ imports
    data-layer (Layer 1)  ← YOU ARE HERE
         ↓ imports
    external libraries + databases

WHO WRITES TO WHAT:
==================
- Neo4j:   CanonKeeper agent ONLY (via neo4j_tools)
- MongoDB: Multiple agents (via mongodb_tools)
- Qdrant:  Indexer agent ONLY (via qdrant_tools)
- MinIO:   Ingest pipeline ONLY (via minio_tools)

SUBMODULES:
==========
- monitor_data.db        - Database client implementations
- monitor_data.tools     - MCP tool definitions
- monitor_data.schemas   - Pydantic models for validation
- monitor_data.middleware - Authority enforcement, validation

================================================================================
"""

__version__ = "0.1.0"
__layer__ = 1
__layer_name__ = "data-layer"

# Re-export key components (to be implemented)
# from monitor_data.server import MCPServer
# from monitor_data.db import Neo4jClient, MongoDBClient, QdrantClient, MinIOClient

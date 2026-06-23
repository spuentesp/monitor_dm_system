"""
MCP Tools for MONITOR Data Layer.

These tools are exposed via the MCP server for agents to call.
Each tool enforces authority checks before executing.

TOOL CATEGORIES:
- neo4j_tools:     41 operations (entities, facts, events, queries)
- mongodb_tools:   18 operations (scenes, turns, proposals, memories)
- qdrant_tools:    3 operations (embed, search, delete)
- nlp_tools:       4 operations (entity extraction, batch extraction, health check, config)
- composite_tools: 2 operations (context assembly, canonization)

AUTHORITY ENFORCEMENT:
Tools check the calling agent's type before executing.
Example: neo4j_create_fact() only allows agent_type="CanonKeeper"

See: docs/architecture/MCP_TRANSPORT.md for full tool specifications
See: docs/architecture/AGENT_ORCHESTRATION.md for authority matrix
"""

from monitor_data.tools.ingest_tools import (
    IngestedChunk,
    chunk_text,
    detect_format,
    extract_pdf_text,
    ingest_docx,
    ingest_epub,
    ingest_file,
    ingest_html,
    ingest_markdown,
    ingest_pdf,
    ingest_text,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_document,
    mongodb_get_document,
    mongodb_record_verdict,
    mongodb_update_document,
)
from monitor_data.tools.neo4j_tools import (
    neo4j_create_axiom,
    neo4j_create_multiverse,
    neo4j_create_source,
    neo4j_create_universe,
    neo4j_delete_universe,
    neo4j_ensure_omniverse,
    neo4j_get_axiom,
    neo4j_get_entities_by_names,
    neo4j_get_multiverse,
    neo4j_get_source,
    neo4j_get_universe,
    neo4j_list_axioms,
    neo4j_list_universes,
    neo4j_update_universe,
)
from monitor_data.tools.nlp_tools import (
    BatchEntityExtractionRequest,
    BatchEntityExtractionResponse,
    EntityExtractionRequest,
    EntityExtractionResponse,
    NLPHealthCheckResponse,
    nlp_extract_entities,
    nlp_extract_entities_batch,
    nlp_get_supported_entity_types,
    nlp_health_check,
)
from monitor_data.tools.qdrant_tools import (
    qdrant_delete,
    qdrant_delete_by_filter,
    qdrant_get_collection_info,
    qdrant_search,
    qdrant_upsert,
    qdrant_upsert_batch,
)

# from monitor_data.tools.composite_tools import *

__all__ = [
    # Neo4j Universe/Multiverse tools
    "neo4j_create_multiverse",
    "neo4j_get_multiverse",
    "neo4j_create_universe",
    "neo4j_get_universe",
    "neo4j_list_universes",
    "neo4j_update_universe",
    "neo4j_delete_universe",
    "neo4j_ensure_omniverse",
    # Neo4j Source tools
    "neo4j_create_source",
    "neo4j_get_source",
    # Neo4j Axiom tools
    "neo4j_create_axiom",
    "neo4j_get_axiom",
    "neo4j_list_axioms",
    "neo4j_get_entities_by_names",
    # Qdrant Vector tools
    "qdrant_upsert",
    "qdrant_upsert_batch",
    "qdrant_search",
    "qdrant_delete",
    "qdrant_delete_by_filter",
    "qdrant_get_collection_info",
    # Ingest tools (DL-B2/DL-B3 + multi-format)
    "IngestedChunk",
    "ingest_pdf",
    "ingest_text",
    "ingest_markdown",
    "ingest_html",
    "ingest_docx",
    "ingest_epub",
    "ingest_file",
    "detect_format",
    "extract_pdf_text",
    "chunk_text",
    # MongoDB Document tools
    "mongodb_create_document",
    "mongodb_get_document",
    "mongodb_update_document",
    "mongodb_record_verdict",
    # NLP / GLiNER tools
    "nlp_extract_entities",
    "nlp_extract_entities_batch",
    "nlp_health_check",
    "nlp_get_supported_entity_types",
    "EntityExtractionRequest",
    "EntityExtractionResponse",
    "BatchEntityExtractionRequest",
    "BatchEntityExtractionResponse",
    "NLPHealthCheckResponse",
]

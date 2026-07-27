"""
Data Topology — complete map of all 6 storage backends.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only + monitor_data.schemas.rpg_ontology.meta

What this module provides
--------------------------
A machine-queryable ``DataTopology`` object that documents:
- What every storage backend holds (``StorageNode`` per backend)
- Every cross-store reference (``DataEdgeSpec`` from meta.py)
- Gap analysis: backends that are deployed but have zero MCP tooling

It is intentionally pure data (no I/O) so it can be used for:
- Generating system documentation
- Agent prompts ("what storage does this data live in?")
- Health checks ("are all required collections/indexes present?")

Usage
-----
::

    from monitor_data.schemas.rpg_ontology.topology import MONITOR_TOPOLOGY, gap_report

    for node in MONITOR_TOPOLOGY.storage_nodes:
        print(node.backend, "—", node.description)

    gaps = gap_report(MONITOR_TOPOLOGY)
    for g in gaps:
        print("GAP:", g)
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from monitor_data.schemas.rpg_ontology.meta import DataEdgeSpec, StorageBackend

# ---------------------------------------------------------------------------
# Collection / table descriptor
# ---------------------------------------------------------------------------


class IndexedBy(StrEnum):
    """Indexing strategy for a collection or table."""

    FORMAL_INDEX = "formal_index"  # DB-level index exists
    PRIMARY_KEY = "primary_key"  # PK / unique key
    NO_INDEX = "no_index"  # no index — sequential scan only
    VECTOR = "vector"  # vector ANN index (Qdrant / OpenSearch)


class CollectionSpec(BaseModel):
    """
    Documents one collection, table, or bucket prefix within a storage node.
    """

    name: str
    description: str
    schema_module: str | None = Field(
        None,
        description="Python module path to the Pydantic schema(s) for this collection",
    )
    indexed_by: IndexedBy = IndexedBy.NO_INDEX
    index_fields: list[str] = Field(
        default_factory=list,
        description="Fields that have an index",
    )
    key_fields: list[str] = Field(
        default_factory=list,
        description="Primary or unique key fields",
    )
    notes: str | None = None
    has_mcp_tools: bool = Field(
        default=True,
        description="Whether MCP tools exist to read/write this collection",
    )


# ---------------------------------------------------------------------------
# Storage node — one per backend
# ---------------------------------------------------------------------------


class StorageNode(BaseModel):
    """
    Documents one storage backend used by MONITOR.
    """

    backend: StorageBackend
    technology: str  # e.g. "Neo4j 5.15", "MongoDB 7.0"
    description: str
    docker_service: str  # docker-compose service name
    default_port: int
    collections: list[CollectionSpec] = Field(default_factory=list)
    notes: str | None = None
    is_deployed: bool = True
    is_active: bool = Field(
        description="True if the backend has active MCP tools and real usage",
    )


# ---------------------------------------------------------------------------
# Topology — the full picture
# ---------------------------------------------------------------------------


class DataTopology(BaseModel):
    """
    Complete data topology for one MONITOR instance.

    Contains all storage nodes and the cross-store data edges between them.
    """

    storage_nodes: list[StorageNode]
    data_edges: list[DataEdgeSpec] = Field(default_factory=list)

    def get_node(self, backend: StorageBackend) -> StorageNode | None:
        return next((n for n in self.storage_nodes if n.backend == backend), None)

    def edges_from(self, backend: StorageBackend) -> list[DataEdgeSpec]:
        return [e for e in self.data_edges if e.from_backend == backend]

    def edges_to(self, backend: StorageBackend) -> list[DataEdgeSpec]:
        return [e for e in self.data_edges if e.to_backend == backend]


# ---------------------------------------------------------------------------
# The topology definition
# ---------------------------------------------------------------------------

MONITOR_TOPOLOGY = DataTopology(
    storage_nodes=[
        # ── Neo4j ────────────────────────────────────────────────────────
        StorageNode(
            backend=StorageBackend.NEO4J,
            technology="Neo4j 5.15",
            docker_service="neo4j",
            default_port=7687,
            is_active=True,
            description=(
                "Canonical knowledge graph — the single source of truth for "
                "world structure and ontological facts. ONLY CanonKeeper writes here."
            ),
            collections=[
                CollectionSpec(
                    name="Omniverse",
                    description="Root node — one per MONITOR instance",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    schema_module="monitor_data.schemas.universe",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="Multiverse",
                    description="Groups related universes (e.g. a campaign setting)",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="Universe",
                    description="A single world / setting (links to PostgreSQL worlds table)",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                    notes="id mirrors PostgreSQL worlds.id",
                ),
                CollectionSpec(
                    name="EntityInstance",
                    description="A named character, location, faction, or object",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    index_fields=["universe_id", "name", "type"],
                    key_fields=["id"],
                    has_mcp_tools=True,
                    notes="Links to character_sheet_index (PostgreSQL) via entity_id",
                ),
                CollectionSpec(
                    name="EntityArchetype",
                    description="Template / class for EntityInstances (e.g. 'Space Pirate')",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="Fact",
                    description="A canonical world fact (e.g. 'Ypsilon 14 is dying')",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    index_fields=["universe_id", "type"],
                    key_fields=["id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="Axiom",
                    description="A fundamental law of the world (e.g. 'FTL travel exists')",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                    notes="Embedded in Qdrant 'knowledge' collection for semantic search",
                ),
                CollectionSpec(
                    name="Source",
                    description="A source document node (links to MongoDB documents + MinIO)",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="Story",
                    description="A narrative arc or campaign",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="Scene",
                    description=("A scene node in the canon graph (lightweight — full scene data lives in MongoDB)"),
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="KnowledgeTree",
                    description="Hierarchical knowledge structure rooted at a Universe",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=False,
                    notes="Graph traversal only — no dedicated MCP tool yet",
                ),
            ],
            notes=(
                "Write access: CanonKeeper ONLY. All other agents submit ProposedChange to MongoDB and await verdict."
            ),
        ),
        # ── MongoDB ──────────────────────────────────────────────────────
        StorageNode(
            backend=StorageBackend.MONGODB,
            technology="MongoDB 7.0 (PyMongo sync)",
            docker_service="mongodb",
            default_port=27017,
            is_active=True,
            description=(
                "Primary narrative store — all mutable, evolving, in-play data. 18 collections; 7 have formal indexes."
            ),
            collections=[
                CollectionSpec(
                    name="scenes",
                    description="Narrative episodes and their embedded turns",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["scene_id"],
                    index_fields=["story_id", "order", "status", "created_at"],
                    schema_module="monitor_data.schemas.scenes",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="proposed_changes",
                    description=(
                        "CanonKeeper staging area — changes proposed during play awaiting canonisation into Neo4j"
                    ),
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["proposal_id"],
                    index_fields=["scene_id", "status"],
                    schema_module="monitor_data.schemas.proposed_changes",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="canon_verdicts",
                    description="CanonKeeper decision log after evaluating proposed_changes",
                    indexed_by=IndexedBy.NO_INDEX,
                    has_mcp_tools=False,
                    notes="GAP: no formal index; verdict history not queryable by MCP tools",
                ),
                CollectionSpec(
                    name="story_outlines",
                    description="High-level story structure (beats, branches, mystery arcs)",
                    indexed_by=IndexedBy.NO_INDEX,
                    key_fields=["story_id"],
                    schema_module="monitor_data.schemas.story_outlines",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="combat_encounters",
                    description="Active and resolved combat encounters with participants",
                    indexed_by=IndexedBy.NO_INDEX,
                    key_fields=["encounter_id"],
                    schema_module="monitor_data.schemas.combat",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="resolutions",
                    description="Individual action resolution records (dice outcome + narrative)",
                    indexed_by=IndexedBy.NO_INDEX,
                    key_fields=["resolution_id"],
                    schema_module="monitor_data.schemas.resolutions",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="memories",
                    description="Agent and character episodic memories; mirrored in Qdrant",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["memory_id"],
                    index_fields=["entity_id", "created_at"],
                    schema_module="monitor_data.schemas.memories",
                    has_mcp_tools=True,
                    notes="Embedded in Qdrant 'memories' collection for semantic search",
                ),
                CollectionSpec(
                    name="character_memories",
                    description="Alias/subset of memories scoped to character entities",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["memory_id"],
                    index_fields=["entity_id"],
                    schema_module="monitor_data.schemas.memories",
                    has_mcp_tools=True,
                    notes="Backed by same Pydantic schema as memories collection",
                ),
                CollectionSpec(
                    name="game_systems",
                    description=(
                        "RPG system definitions (rules, dice, attributes). "
                        "Full GameSystemSpec JSONB stored here; "
                        "also mirrored in PostgreSQL game_system_schemas.spec"
                    ),
                    indexed_by=IndexedBy.NO_INDEX,
                    key_fields=["system_id"],
                    schema_module="monitor_data.schemas.game_systems",
                    has_mcp_tools=True,
                    notes="Links to MinIO PDF via source_document_id",
                ),
                CollectionSpec(
                    name="rule_overrides",
                    description="Per-session/story overrides to game rules",
                    indexed_by=IndexedBy.NO_INDEX,
                    key_fields=["override_id"],
                    schema_module="monitor_data.schemas.game_systems",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="party_inventories",
                    description="Shared party gold + item lists",
                    indexed_by=IndexedBy.NO_INDEX,
                    key_fields=["party_id"],
                    schema_module="monitor_data.schemas.party_inventory",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="party_splits",
                    description="Audit trail of party inventory split events",
                    indexed_by=IndexedBy.NO_INDEX,
                    has_mcp_tools=True,
                    notes="References party_inventories.party_id",
                ),
                CollectionSpec(
                    name="character_working_state",
                    description=(
                        "In-scene live stat modifications (HP changes, temp buffs). "
                        "EPHEMERAL — not canonical. Cleared/archived at scene end."
                    ),
                    indexed_by=IndexedBy.NO_INDEX,
                    key_fields=["entity_id", "scene_id"],
                    schema_module="monitor_data.schemas.working_state",
                    has_mcp_tools=True,
                    notes=(
                        "GAP: not formally indexed; entity_id is a soft reference to PostgreSQL character_sheet_index"
                    ),
                ),
                CollectionSpec(
                    name="documents",
                    description="Ingested source document metadata (PDF, DOCX, etc.)",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["doc_id"],
                    index_fields=["universe_id", "status"],
                    schema_module="monitor_data.schemas.documents",
                    has_mcp_tools=True,
                    notes="minio_ref → MinIO object path",
                ),
                CollectionSpec(
                    name="snippets",
                    description="Text chunks extracted from documents with Qdrant refs",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["snippet_id"],
                    index_fields=["doc_id"],
                    schema_module="monitor_data.schemas.documents",
                    has_mcp_tools=True,
                    notes="Each snippet has a mirrored vector in Qdrant 'snippets' collection",
                ),
                CollectionSpec(
                    name="ingestion_jobs",
                    description="Pipeline tracking for PDF/document ingest",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["job_id"],
                    index_fields=["source_id", "universe_id", "status", "created_at"],
                    schema_module="monitor_data.schemas.ingestion_jobs",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="knowledge_packs",
                    description=(
                        "Assembled world-knowledge packages (axioms, archetypes, lore) "
                        "ready for agent injection into LLM context"
                    ),
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["pack_id"],
                    index_fields=["status", "pack_type", "system_name", "created_at"],
                    schema_module="monitor_data.schemas.knowledge_packs",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="conversations",
                    description="NPC dialogue sessions",
                    indexed_by=IndexedBy.NO_INDEX,
                    key_fields=["session_id"],
                    schema_module="monitor_data.schemas.conversations",
                    has_mcp_tools=True,
                ),
            ],
        ),
        # ── Qdrant ───────────────────────────────────────────────────────
        StorageNode(
            backend=StorageBackend.QDRANT,
            technology="Qdrant 1.7.4",
            docker_service="qdrant",
            default_port=6333,
            is_active=True,
            description=(
                "Vector store for semantic search across all narrative content. "
                "All collections use 1536-dim cosine similarity (text-embedding-3-small)."
            ),
            collections=[
                CollectionSpec(
                    name="scenes",
                    description="Scene embeddings for semantic search (summaries + turn text)",
                    indexed_by=IndexedBy.VECTOR,
                    schema_module="monitor_data.schemas.vectors",
                    has_mcp_tools=True,
                    notes="Payload: scene_id, story_id, universe_id, status",
                ),
                CollectionSpec(
                    name="memories",
                    description="Character and agent episodic memory embeddings",
                    indexed_by=IndexedBy.VECTOR,
                    schema_module="monitor_data.schemas.vectors",
                    has_mcp_tools=True,
                    notes="Payload: memory_id, entity_id, importance, emotional_valence",
                ),
                CollectionSpec(
                    name="snippets",
                    description="Ingested document chunk embeddings",
                    indexed_by=IndexedBy.VECTOR,
                    schema_module="monitor_data.schemas.vectors",
                    has_mcp_tools=True,
                    notes="Payload: snippet_id, doc_id, universe_id",
                ),
                CollectionSpec(
                    name="entities",
                    description="Entity descriptions for semantic NPC/location discovery",
                    indexed_by=IndexedBy.VECTOR,
                    schema_module="monitor_data.schemas.vectors",
                    has_mcp_tools=True,
                    notes="Payload: entity_id, universe_id, name, entity_type, state_tags",
                ),
                CollectionSpec(
                    name="knowledge",
                    description="Rules, axioms, lore events — structured world knowledge",
                    indexed_by=IndexedBy.VECTOR,
                    schema_module="monitor_data.schemas.vectors",
                    has_mcp_tools=True,
                    notes="Payload: source_id, universe_id, type (axiom|lore|term), ref_id, title",
                ),
            ],
        ),
        # ── MinIO ────────────────────────────────────────────────────────
        StorageNode(
            backend=StorageBackend.MINIO,
            technology="MinIO (S3-compatible)",
            docker_service="minio",
            default_port=9000,
            is_active=True,
            description=("Object storage for raw binary files. Supports minio, s3, and local-folder backends."),
            collections=[
                CollectionSpec(
                    name="monitor/uploads/",
                    description=("Uploaded source documents. Path pattern: uploads/{doc_id}/{timestamp}_{filename}"),
                    indexed_by=IndexedBy.NO_INDEX,
                    has_mcp_tools=True,
                    notes=(
                        "Death in Space PDF confirmed present at "
                        "monitor/uploads/<doc_id>/. "
                        "Metadata lives in MongoDB 'documents' collection."
                    ),
                ),
            ],
            notes=(
                "Single bucket 'monitor' by default. "
                "Per-world isolation via minio_prefix in world_db_bindings (PostgreSQL)."
            ),
        ),
        # ── PostgreSQL ───────────────────────────────────────────────────
        StorageNode(
            backend=StorageBackend.POSTGRES,
            technology="PostgreSQL 15+ (asyncpg)",
            docker_service="postgres",
            default_port=5432,
            is_active=True,
            description=(
                "Relational store for structured app config, routing, and formally typed game-mechanical data."
            ),
            collections=[
                CollectionSpec(
                    name="system_config",
                    description="App-wide key/value configuration",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["key"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="llm_providers",
                    description="LLM provider credentials and model parameters",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    schema_module="monitor_data.schemas.llm_config",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="llm_node_assignments",
                    description="Maps agent nodes to specific LLM providers",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["node_name"],
                    schema_module="monitor_data.schemas.llm_config",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="worlds",
                    description=("World/universe registry — id mirrors Neo4j Universe.id"),
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="world_db_bindings",
                    description="Per-world DB namespace pointers for all 6 backends",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["world_id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="active_world",
                    description="Singleton — which world is the current session",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["singleton"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="connection_settings",
                    description="Named/saved DB connection profiles",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["id"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="active_mode",
                    description="Singleton — current system operation mode",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["singleton"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="user_preferences",
                    description="Per-key JSON user preferences",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["key"],
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="game_system_schemas",
                    description=(
                        "RPG system registry — stores full GameSystemSpec as JSONB "
                        "in the 'spec' column (meta.py format). "
                        "Legacy columns (attributes, resources, schema_class) retained "
                        "for backward compatibility."
                    ),
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["system_id"],
                    schema_module="monitor_data.schemas.rpg_ontology.meta",
                    has_mcp_tools=True,
                    notes="spec JSONB replaces schema_class Python import path approach",
                ),
                CollectionSpec(
                    name="character_sheet_index",
                    description=(
                        "Validated character sheets — one row per character per world. "
                        "sheet_data is validated JSONB per the system's GameSystemSpec."
                    ),
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["id"],
                    index_fields=["world_id", "system_id"],
                    schema_module="monitor_data.schemas.rpg_ontology.meta",
                    has_mcp_tools=True,
                    notes=(
                        "entity_id → Neo4j EntityInstance (soft reference). "
                        "Also referenced by MongoDB character_working_state."
                    ),
                ),
                CollectionSpec(
                    name="equipment_catalog",
                    description="Typed equipment items indexed by system and item type",
                    indexed_by=IndexedBy.FORMAL_INDEX,
                    key_fields=["id"],
                    index_fields=["world_id", "system_id", "item_type"],
                    schema_module="monitor_data.schemas.rpg_ontology.meta",
                    has_mcp_tools=True,
                ),
                CollectionSpec(
                    name="character_equipment",
                    description="Character ↔ equipment join table (equipped items)",
                    indexed_by=IndexedBy.PRIMARY_KEY,
                    key_fields=["character_sheet_id", "item_id"],
                    has_mcp_tools=True,
                ),
            ],
        ),
        # ── OpenSearch ───────────────────────────────────────────────────
        StorageNode(
            backend=StorageBackend.OPENSEARCH,
            technology="OpenSearch 2.11.1",
            docker_service="opensearch",
            default_port=9200,
            is_active=False,
            is_deployed=True,
            description=(
                "Full-text search engine. DEPLOYED but NOT ACTIVE — "
                "zero MCP tools, zero index creation, zero query usage."
            ),
            collections=[],
            notes=(
                "GAP: OpenSearch is running in docker-compose but the codebase "
                "has no MCP tools targeting it. world_db_bindings tracks an "
                "opensearch_index_prefix column but it is never used. "
                "Potential uses: full-text search over scenes/turns, "
                "faceted entity search, log analytics."
            ),
        ),
    ],
    # ── Cross-store data edges ────────────────────────────────────────────
    data_edges=[
        DataEdgeSpec(
            edge_id="scene_mongodb_to_neo4j_universe",
            description="MongoDB scene references its Neo4j Universe",
            from_backend=StorageBackend.MONGODB,
            from_collection="scenes",
            from_field="universe_id",
            to_backend=StorageBackend.NEO4J,
            to_collection="Universe",
            to_field="id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="scene_mongodb_to_qdrant",
            description="MongoDB scene is embedded into Qdrant for semantic search",
            from_backend=StorageBackend.MONGODB,
            from_collection="scenes",
            from_field="scene_id",
            to_backend=StorageBackend.QDRANT,
            to_collection="scenes",
            to_field="scene_id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="memory_mongodb_to_qdrant",
            description="MongoDB memory is mirrored in Qdrant vectors",
            from_backend=StorageBackend.MONGODB,
            from_collection="memories",
            from_field="memory_id",
            to_backend=StorageBackend.QDRANT,
            to_collection="memories",
            to_field="memory_id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="memory_mongodb_to_neo4j_entity",
            description="MongoDB memory references a Neo4j EntityInstance",
            from_backend=StorageBackend.MONGODB,
            from_collection="memories",
            from_field="entity_id",
            to_backend=StorageBackend.NEO4J,
            to_collection="EntityInstance",
            to_field="id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="proposed_change_to_scene",
            description="ProposedChange in MongoDB references its parent scene",
            from_backend=StorageBackend.MONGODB,
            from_collection="proposed_changes",
            from_field="scene_id",
            to_backend=StorageBackend.MONGODB,
            to_collection="scenes",
            to_field="scene_id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="document_mongodb_to_minio",
            description="MongoDB document record references the raw file in MinIO",
            from_backend=StorageBackend.MONGODB,
            from_collection="documents",
            from_field="minio_ref",
            to_backend=StorageBackend.MINIO,
            to_collection="monitor/uploads/",
            to_field="object_path",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="snippet_mongodb_to_qdrant",
            description="MongoDB snippet chunk has a vector in Qdrant",
            from_backend=StorageBackend.MONGODB,
            from_collection="snippets",
            from_field="snippet_id",
            to_backend=StorageBackend.QDRANT,
            to_collection="snippets",
            to_field="snippet_id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="snippet_mongodb_to_document",
            description="MongoDB snippet belongs to a document",
            from_backend=StorageBackend.MONGODB,
            from_collection="snippets",
            from_field="doc_id",
            to_backend=StorageBackend.MONGODB,
            to_collection="documents",
            to_field="doc_id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="character_sheet_to_neo4j",
            description="PostgreSQL character sheet references canonical Neo4j entity",
            from_backend=StorageBackend.POSTGRES,
            from_collection="character_sheet_index",
            from_field="entity_id",
            to_backend=StorageBackend.NEO4J,
            to_collection="EntityInstance",
            to_field="id",
            is_enforced=False,
            notes="Soft reference — no FK across backends",
        ),
        DataEdgeSpec(
            edge_id="character_sheet_to_world",
            description="PostgreSQL character sheet belongs to a world",
            from_backend=StorageBackend.POSTGRES,
            from_collection="character_sheet_index",
            from_field="world_id",
            to_backend=StorageBackend.POSTGRES,
            to_collection="worlds",
            to_field="id",
            is_enforced=True,
            notes="PostgreSQL FK — enforced",
        ),
        DataEdgeSpec(
            edge_id="working_state_to_character_sheet",
            description=("MongoDB in-scene working state references PostgreSQL character sheet"),
            from_backend=StorageBackend.MONGODB,
            from_collection="character_working_state",
            from_field="entity_id",
            to_backend=StorageBackend.POSTGRES,
            to_collection="character_sheet_index",
            to_field="entity_id",
            is_enforced=False,
            notes=(
                "GAP: ephemeral state is not guaranteed to match canonical sheet. No cleanup on scene end is enforced."
            ),
        ),
        DataEdgeSpec(
            edge_id="worlds_to_neo4j_universe",
            description="PostgreSQL worlds table mirrors Neo4j Universe nodes",
            from_backend=StorageBackend.POSTGRES,
            from_collection="worlds",
            from_field="id",
            to_backend=StorageBackend.NEO4J,
            to_collection="Universe",
            to_field="id",
            is_enforced=False,
            notes="Denormalised cache — must be kept in sync manually",
        ),
        DataEdgeSpec(
            edge_id="game_system_mongodb_to_minio_pdf",
            description="MongoDB game_systems.source_document_id → raw PDF in MinIO",
            from_backend=StorageBackend.MONGODB,
            from_collection="game_systems",
            from_field="source_document_id",
            to_backend=StorageBackend.MINIO,
            to_collection="monitor/uploads/",
            to_field="doc_id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="game_system_mongodb_to_postgres",
            description=("MongoDB game_systems record mirrors spec to PostgreSQL game_system_schemas"),
            from_backend=StorageBackend.MONGODB,
            from_collection="game_systems",
            from_field="system_id",
            to_backend=StorageBackend.POSTGRES,
            to_collection="game_system_schemas",
            to_field="system_id",
            is_enforced=False,
            notes=(
                "GAP: two stores of truth for game system spec. "
                "MongoDB stores the full flexible doc; "
                "PostgreSQL stores the formal GameSystemSpec JSONB. "
                "Keep in sync on write."
            ),
        ),
        DataEdgeSpec(
            edge_id="neo4j_source_to_minio",
            description="Neo4j Source node references raw file in MinIO",
            from_backend=StorageBackend.NEO4J,
            from_collection="Source",
            from_field="minio_ref",
            to_backend=StorageBackend.MINIO,
            to_collection="monitor/uploads/",
            to_field="object_path",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="entity_neo4j_to_qdrant",
            description="Neo4j EntityInstance description is embedded in Qdrant",
            from_backend=StorageBackend.NEO4J,
            from_collection="EntityInstance",
            from_field="id",
            to_backend=StorageBackend.QDRANT,
            to_collection="entities",
            to_field="entity_id",
            is_enforced=False,
        ),
        DataEdgeSpec(
            edge_id="axiom_neo4j_to_qdrant",
            description="Neo4j Axiom is embedded in Qdrant for semantic retrieval",
            from_backend=StorageBackend.NEO4J,
            from_collection="Axiom",
            from_field="id",
            to_backend=StorageBackend.QDRANT,
            to_collection="knowledge",
            to_field="ref_id",
            is_enforced=False,
        ),
    ],
)


# ---------------------------------------------------------------------------
# Gap analysis helper
# ---------------------------------------------------------------------------


def gap_report(topology: DataTopology) -> list[str]:
    """
    Return a list of gap descriptions for the given topology.

    Gaps are:
    1. Backends that are deployed but not active (no MCP tools).
    2. Collections that are deployed but have no MCP tools.
    3. Cross-store edges that are unenforced (soft references) — informational.
    4. Specific known issues documented in collection notes.
    """
    gaps: list[str] = []

    for node in topology.storage_nodes:
        if node.is_deployed and not node.is_active:
            gaps.append(
                f"[BACKEND_INACTIVE] {node.backend.value} ({node.technology}) "
                f"is deployed but has no active MCP tools. "
                f"{node.notes or ''}"
            )
        for coll in node.collections:
            if not coll.has_mcp_tools:
                gaps.append(f"[NO_MCP_TOOLS] {node.backend.value}/{coll.name}: {coll.description}. {coll.notes or ''}")
            if coll.notes and "GAP" in coll.notes:
                gaps.append(f"[COLLECTION_GAP] {node.backend.value}/{coll.name}: {coll.notes}")

    unenforced = [e for e in topology.data_edges if not e.is_enforced]
    if unenforced:
        gaps.append(
            f"[REFERENTIAL_INTEGRITY] {len(unenforced)} cross-store references "
            f"are soft (not enforced by the DB). "
            f"Orphaned data is possible if writes are not coordinated. "
            f"Edges: {[e.edge_id for e in unenforced]}"
        )

    return gaps

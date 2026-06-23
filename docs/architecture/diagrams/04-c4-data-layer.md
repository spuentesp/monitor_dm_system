# 04 — C4 Componentes: Data Layer (Nivel 3)

> Componentes internos del Data Layer (`monitor-data-layer`).
> MCP Tools, DB Clients, Pydantic Schemas, y Authority Middleware.

## Descripción

El Data Layer expone todas las operaciones de base de datos como **MCP Tools**,
que son consumidas por los agentes de la Capa 2 vía el protocolo MCP.

### Estructura

| Grupo | Archivo(s) | Operaciones |
|-------|-----------|-------------|
| Neo4j Tools | `neo4j_tools/` | create_entity, create_fact, create_relationship, query_graph, get_entity, get_facts, traverse_graph, create_source |
| MongoDB Tools | `mongodb_tools/` | scenes, turns, resolutions, proposals, knowledge_packs, ingestion_jobs, game_systems, character_sheets, npc_profiles, memories, tone_profiles, random_tables, conversations, party, tag_registry, profiles, webhook_tools |
| Qdrant Tools | `qdrant_tools.py` | search_similar, index_snippets, delete_collection |
| Ingest Tools | `ingest_tools/` | chunking, tokenization, deduplication (identity maps, conflict detection) |
| RPG Tools | `rpg_tools.py` | roll_dice, resolve_check, calc_modifier, resource_engine |
| Perception Tools | `perception_tools.py` | npc_perception_check, sensory_range_query |
| Lain Tools | `lain_tools.py` | blast radius, dependency traces, dead code, semantic search |

### Authority Middleware

El middleware `middleware/auth.py` intercepta todas las llamadas a herramientas de escritura
de Neo4j. Solo el agente **CanonKeeper** tiene permiso de escritura en Neo4j.
Todos los demás agentes pueden escribir en MongoDB y Qdrant.

## Diagrama

```mermaid
graph TB
    subgraph L1["📦 monitor-data-layer"]
        subgraph TOOLS["MCP Tools (server.py auto-registro)"]
            N4J_TOOLS["neo4j_tools/\ncreate_entity, create_fact\ncreate_relationship\nquery_graph, get_entity\nget_facts, traverse_graph\ncreate_source"]
            MONGO_TOOLS["mongodb_tools/\nscenes, turns, resolutions\nproposals, knowledge_packs\ningestion_jobs, game_systems\ncharacter_sheets, npc_profiles\nmemories, tone_profiles\nrandom_tables, conversations\nparty, tag_registry, profiles\nwebhook_tools"]
            QDR_TOOLS["qdrant_tools.py\nsearch_similar\nindex_snippets\ndelete_collection"]
            INGEST_TOOLS["ingest_tools/\n_models (IngestedChunk, SectionBlock)\ndeduplication (identity maps, conflict detection)\nchunking + tokenization"]
            RPG_TOOLS["rpg_tools.py\nroll_dice, resolve_check\ncalc_modifier, resource_engine"]
            PERC_TOOLS["perception_tools.py\nnpc_perception_check\nsensory_range_query"]
            LAIN_TOOLS["lain_tools.py\nget_blast_radius\ntrace_dependency\nfind_dead_code\nsemantic_search"]
        end

        subgraph CLIENTS["DB Clients"]
            N4J_CLIENT["Neo4jClient\nCypher query builder\nTransaction management\nGraph traversal utils"]
            MONGO_CLIENT["MongoDBClient\nCollection accessors\nChange stream watcher\nAggregation pipeline"]
            QDR_CLIENT["QdrantClient\nVector CRUD\nCollection management\nPayload filtering"]
            PG_CLIENT["PostgreSQLClient\nSQLAlchemy ORM\nMigration runner\nConnection pooling"]
            MINIO_CLIENT["MinioClient\nS3-compatible upload/download\nPresigned URLs\nBucket management"]
        end

        subgraph SCHEMAS["Pydantic v2 Schemas"]
            BASE["base.py\nEntityArchetype, EntityInstance\nCanonLevel, ExtractionStatus\nSourceType, KnowledgeTreeType"]
            ENTITY["entities.py\nEntityCreate, EntityUpdate\nEntityResponse"]
            FACT["facts.py\nFactCreate, FactUpdate\nFactResponse, CanonLevel"]
            SCENE["scenes.py\nSceneCreate, SceneResponse\nSceneStatus"]
            TURN["turns.py\nTurnCreate, TurnResponse\nActionType"]
            PROPOSAL["proposals.py\nProposedChange, ChangeType\nProposalStatus"]
            PACK["knowledge_packs.py\nKnowledgePack, PackType\nApplyKnowledgePackRequest"]
            JOB["ingestion_jobs.py\nIngestionJob, IngestionStage\nJobStatus tracking"]
            GS["game_systems.py\nGameSystemSchema\nCharacterSheetSchema"]
        end

        MIDDLEWARE["🛡️ Authority Middleware\nmiddleware/auth.py\nIdentifica agente → verifica AUTHORITY_MATRIX\nCanonKeeper = único escritor Neo4j\nLectura: todos los agentes"]
    end

    TOOLS --> CLIENTS
    TOOLS --> SCHEMAS
    N4J_TOOLS --> MIDDLEWARE
    MIDDLEWARE --> N4J_CLIENT
    MONGO_TOOLS --> MONGO_CLIENT
    QDR_TOOLS --> QDR_CLIENT
    RPG_TOOLS --> PG_CLIENT
    LAIN_TOOLS --> LAIN_CLIENT["Lain MCP Client\n(stdio transport)"]

    classDef tools fill:#fff3e0,stroke:#f57c00
    classDef client fill:#e8eaf6,stroke:#3f51b5
    classDef schema fill:#e0f2f1,stroke:#00796b
    classDef mw fill:#ffebee,stroke:#c62828

    class N4J_TOOLS,MONGO_TOOLS,QDR_TOOLS,INGEST_TOOLS,RPG_TOOLS,PERC_TOOLS,LAIN_TOOLS tools
    class N4J_CLIENT,MONGO_CLIENT,QDR_CLIENT,PG_CLIENT,MINIO_CLIENT,LAIN_CLIENT client
    class BASE,ENTITY,FACT,SCENE,TURN,PROPOSAL,PACK,JOB,GS schema
    class MIDDLEWARE mw
```

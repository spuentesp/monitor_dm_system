# 08 — Pipeline de Ingestión

> Flujo completo de ingesta de documentos: desde el archivo crudo hasta
> la canonización en Neo4j, pasando por indexación, análisis, y revisión.

## Descripción

El pipeline de ingesta convierte documentos fuente (PDFs, EPUBs, etc.) en
conocimiento canónico estructurado en el Knowledge Graph de Neo4j.

### Fases

| Fase | Responsable | Entrada | Salida |
|------|-------------|---------|--------|
| 1. Registro | IngestionPipeline | File bytes | MinIO key + Neo4j Source + MongoDB Document + IngestionJob |
| 2. Indexación | Indexer | Source bytes | Qdrant snippets (chunks + embeddings) |
| 3. Análisis | Analyzer | Qdrant snippets | KnowledgePack en MongoDB (status=ready) |
| 4. Revisión y Dedup | Usuario + Sistema | KnowledgePack | KnowledgePack revisado + deduplicado |
| 5. Aplicación | Usuario | KnowledgePack aprobado | ProposedChanges en MongoDB |
| 6. Canonización | CanonKeeper | ProposedChanges | Entidades y hechos en Neo4j |

### Notas importantes

- La **deduplicación** (`ingest_tools/deduplication.py`) ocurre durante la fase de
  aplicación del KnowledgePack, no como paso independiente del pipeline.
- El **IngestionJob** se marca como `stage=complete` después de la fase 3 (Analyzer).
  La canonización (fase 6) es un proceso separado disparado por el usuario.
- **CanonKeeper** es el único que escribe en Neo4j. Los ProposedChanges se
  crean en MongoDB y CanonKeeper los evalúa uno por uno.

## Diagrama

```mermaid
sequenceDiagram
    actor U as Usuario (World Architect)
    participant CLI as CLI / Web UI
    participant IP as IngestionPipeline
    participant MINIO as MinIO
    participant N4J as Neo4j
    participant MONGO as MongoDB
    participant IDX as Indexer
    participant QDR as Qdrant
    participant ANL as Analyzer
    participant LLM as LLM Provider
    participant CK as CanonKeeper

    U->>CLI: upload "phb.pdf"
    CLI->>IP: ingest_file(bytes, filename, universe_id)

    rect rgb(240, 248, 255)
        Note over IP: Fase 1: Registro
        IP->>MINIO: upload file bytes
        MINIO-->>IP: minio_key + bucket
        IP->>N4J: neo4j_create_source(title, type, universe_id)
        N4J-->>IP: source_id
        IP->>MONGO: mongodb_create_document(filename, source_id)
        MONGO-->>IP: doc_id
        IP->>MONGO: mongodb_create_ingestion_job()
        MONGO-->>IP: job_id
        IP->>MONGO: mongodb_update_ingestion_job(stage=ingesting)
    end

    rect rgb(255, 243, 224)
        Note over IP: Fase 2: Indexacion (Indexer)
        IP->>IDX: index(source_bytes, source_id, universe_id)
        IDX->>IDX: chunk + tokenize
        IDX->>LLM: embed chunks
        LLM-->>IDX: embeddings
        IDX->>QDR: upsert snippets + vectors
        QDR-->>IDX: snippet_count
        IDX-->>IP: snippet_count
        IP->>MONGO: mongodb_update_ingestion_job(stage=indexed)
    end

    rect rgb(232, 245, 233)
        Note over IP: Fase 3: Analisis (Analyzer)
        IP->>ANL: analyze(source_id, universe_id, pack_type, layers)
        loop Por cada capa (axioms, entities, lore, game_system, rules)
            ANL->>QDR: search_similar(query)
            QDR-->>ANL: top-K snippets
            ANL->>LLM: DSPy extraction (instructor)
            LLM-->>ANL: structured knowledge
        end
        ANL->>MONGO: create KnowledgePack(status=ready)
        MONGO-->>ANL: pack_id
        ANL-->>IP: pack_id + extracted_count
        IP->>MONGO: mongodb_update_ingestion_job(stage=analyzed)
        Note over IP: IngestionPipeline termina aquí.<br/>IngestionJob → stage=complete
    end

    rect rgb(243, 229, 245)
        Note over IP: Fase 4: Revision y Deduplicacion (Usuario)
        U->>CLI: review KnowledgePack
        CLI->>MONGO: get pack details
        MONGO-->>CLI: entities, facts, conflicts
        Note over MONGO: Identity maps + conflict detection<br/>Exact match → Semantic match → Negation conflict
        U->>CLI: approve / reject / merge items
    end

    rect rgb(255, 235, 238)
        Note over IP: Fase 5: Aplicacion → ProposedChanges
        CLI->>MONGO: apply KnowledgePack → ProposedChanges
        MONGO-->>CLI: proposal_count
    end

    rect rgb(255, 253, 231)
        Note over IP: Fase 6: Canonizacion (CanonKeeper)
        U->>CLI: canonize proposals
        CLI->>CK: evaluate_and_commit(proposal_ids)
        CK->>MONGO: get pending proposals
        MONGO-->>CK: ProposedChange[]
        loop Por cada propuesta
            CK->>N4J: check existing facts/entities
            N4J-->>CK: existing data
            CK->>LLM: DSPy evaluation
            LLM-->>CK: accept/reject + reasoning
            alt Aceptada
                CK->>N4J: create_entity / create_fact
                N4J-->>CK: entity_id / fact_id
                CK->>MONGO: mark proposal accepted
            else Rechazada
                CK->>MONGO: mark proposal rejected + reason
            end
        end
        CK-->>CLI: accepted + rejected counts
    end

    CLI-->>U: ✅ "phb.pdf" ingesta completa
```

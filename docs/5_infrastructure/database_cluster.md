---
description: "Details the docker-compose environment."
tags: [infrastructure, docker, databases]
layer: 0
---

# Database Cluster

MONITOR relies heavily on containerized infrastructure for local development and eventual cloud deployment.

## The Docker Compose Stack
Running `./dev.sh` spins up `infra/docker-compose.yml`, which includes:
- **Neo4j** (Port 7687) — canonical graph. APOC core is bundled; the **GDS
  plugin is vendored** via `./scripts/fetch_neo4j_plugins.sh` (GDS 2.6.8,
  sha256-pinned, into the gitignored `infra/neo4j/plugins/`). GDS powers the
  graph-analytics tools in `neo4j_tools/graph_algos.py` (orphan detection,
  node similarity, centrality, shortest path). Note: GDS 2.5.x does NOT load
  on Neo4j 5.15 — use the 2.6.x line.
- **MongoDB** (Port 27017) — narrative documents. Indexes are spec-driven in
  `db/mongodb.py::_INDEX_SPECS`, including **text indexes** on scenes,
  snippets, knowledge_packs, chat_messages, lorebook_entries, gm_notes (the
  full-text role formerly provisioned for OpenSearch, which has been
  **removed**). Multi-world isolation uses collection prefixes
  (`world_db_bindings.mongodb_collection_prefix`); `ensure_indexes_for_prefix`
  replays the full index set for a prefixed world.
- **Qdrant** (Port 6333) — vector store. Dense vectors only (no hybrid/BM25);
  per-world collections via bindings (`world_<id>`), cloned on fork by
  `qdrant_clone_collection`.
- **PostgreSQL** (Port 5432) — accounts, config, LLM providers, worlds +
  `world_db_bindings` + `active_world`.
- **MinIO** (Port 9000, 9001) — object storage; `STORAGE_BACKEND=folder`
  stores on local disk instead. Per-world key prefixes (`minio_prefix`),
  copied on fork by `MinIOClient.copy_prefix`.
- **Redis** (Port 6379) — optional cache/coordination; `REDIS_ENABLED=false`
  disables it.
- **GLiNER** (Port 8082) — opt-in NER service (`--profile gliner`), self-built
  from `infra/gliner/Dockerfile` with the model baked in. `NLP_BACKEND=gliner`
  with automatic spaCy fallback when the service is down; labels come from
  `ENTITY_TYPES` (use domain labels for RPG ingestion).

## Reusable base worlds
A base world = a published knowledge pack (`POST /api/packs/{id}/publish`,
gated by `mongodb_pack_quality_report` + `neo4j_universe_quality_report`) plus
a Universe marked `is_template`. Users fork it (`POST /api/universes/{id}/fork`):
the graph is deep-cloned (`neo4j_fork_universe`, CanonKeeper/WorldArchitect
only), and Mongo/Qdrant/MinIO data is copied into the fork's prefixed
collections/collections/prefix per its `world_db_bindings` row. The active
world's bindings are loaded by `BaseAgent.load_world_context()`, which applies
the Mongo collection prefix and exposes the Qdrant collection / MinIO prefix.
Neo4j isolation is by `Universe` node (Community edition has a single user
database — `neo4j_database` in bindings is informational).

## Environment Variables
The `.env` file (copied from `env.example`) dictates credentials for these databases. The Data Layer dynamically loads these upon initialization.

## See Also
- [Infrastructure Index](./_index.md)
- [Layer 1: Data](../2_architecture/layer1_data.md)

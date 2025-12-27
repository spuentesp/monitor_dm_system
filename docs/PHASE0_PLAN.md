# Phase 0 Plan — Data Layer Foundation

This phase defines the prep and basic tooling needed before agents implement any higher-layer logic. It aligns with DL-1 to DL-14 in `docs/USE_CASES.md`.

## Goals
- Establish schemas for all data objects.
- Stand up DB clients and health checks.
- Implement MCP tool stubs wired through auth/validation middleware.
- Provide templates so agents can copy/extend patterns quickly.
- Ensure Docker/dev env is runnable.

## Scope (DL-1..DL-14)
- Neo4j: universes, entities (archetype/instance), axioms, facts/events, relationships/state-tags, stories (canonical), plot threads.
- MongoDB: scenes/turns (narrative), proposed changes, story_outlines, memories, sources/documents/snippets/ingest proposals.
- Qdrant: embeddings for scenes/memories/snippets.
- MinIO: binary assets for sources/documents.
- OpenSearch: keyword index/search for text content.
- MCP server: tool registry, auth, validation, health.

## File/Template Checklist
- Schemas (`packages/data-layer/src/monitor_data/schemas/`):
  - universe.py, entity.py (archetype/instance), axiom.py, fact_event.py, relationship.py, story.py (canonical), scene_turn.py (narrative), proposed_change.py, story_outline.py, plot_thread.py, memory.py, source.py, document.py, snippet.py, ingest_proposal.py, binary.py (metadata), embedding.py (vector payload), search_document.py (OpenSearch doc).
  - base.py with common config, UUID type, pagination helpers.
- DB clients (`db/`): neo4j.py, mongodb.py, qdrant.py, minio.py, opensearch.py with health checks.
- Tools (`tools/`): neo4j_tools.py, mongodb_tools.py, qdrant_tools.py, minio_tools.py, opensearch_tools.py, composite_tools.py. Each tool mirrors a DL use case and uses schemas + auth/validation.
- Middleware: `middleware/auth.py` (authority matrix) and `middleware/validation.py` (schema enforcement).
- Server: `server.py` registers all tools, applies middleware, exposes health.

## Patterns (copy/extend)
- Schema pattern: Pydantic model trio (Create, Update, Read) per object with `extra="forbid"` and type hints; IDs as strings (UUID).
- Tool pattern: validate input schema → authority check → call DB client → return schema response; use a shared error/response shape.
- Client pattern: thin wrappers around drivers with connection management and health probe method.

## Docker/Env
- Ensure `infra/docker-compose.yml` and `.env.example` are present and runnable for Neo4j, MongoDB, Qdrant, MinIO, OpenSearch.
- Add sample service URLs/credentials to `.env.example` for data-layer use.

## Testing
- Unit tests for schemas (validation) and tools (using fakes/mocks).
- Integration tests gated by env flags to hit real services spun up via docker-compose (optional to run by default).
- Health check tests per client.

## Deliverables
- Schema files stubbed out with fields from ontology.
- DB client stubs with health methods.
- MCP tool stubs registered in server.py with auth/validation middleware wired.
- Basic tests to validate schemas and tool wiring (even if DB calls are mocked initially).

## How to use
- Agents pick a DL use case, copy the relevant schema/tool template, fill in fields/operations per `ONTOLOGY.md` and `DATABASE_INTEGRATION.md`, and add tests.

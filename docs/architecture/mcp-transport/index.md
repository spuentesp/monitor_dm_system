# MONITOR MCP Transport Layer

*MCP tool specifications for the Data Layer API.*

---

## Overview

This document defines how agents interact with the Data Layer API via **Model Context Protocol (MCP)**.

**Key principle:** Each Data Layer API operation is exposed as an MCP tool with proper schema validation and authority enforcement.

> **Note:** This is the transport/spec reference. For the live tool registry and middleware behavior, verify the current implementation in `packages/data-layer/src/monitor_data/`.
>
> **Implementation reality (April 2026):** `monitor_data.server` currently auto-discovers `neo4j_*`, `mongodb_*`, `qdrant_*`, and `ingest_*` functions. MinIO operations are wrapped by the ingest flow today; OpenSearch and standalone `rpg_*` exposure are still specification-level targets.

### Redis adoption plan for solo-play speed ✅

Redis is now adopted as an **optional runtime acceleration layer**, not as canonical storage.

**Source of truth remains unchanged:**
- `Neo4j` → canon graph
- `MongoDB` → scenes, turns, packs, jobs, proposals
- `Qdrant` → semantic recall
- `Redis` → ephemeral hot-path cache only

**Phase 1 (implemented):**
- `packages/data-layer/src/monitor_data/db/redis.py` provides an optional Redis client with graceful fallback.
- `ContextAssembly` caches the main solo-play hot path:
  - scene entities
  - scene summary
  - recent turns
  - active game-system doc
  - source profile
  - short-lived memory/snippet retrieval results
- TTLs stay short (`~5–60s`) so canon stays fresh while repeated turn lookups avoid redundant reads.
- `/api/ingest/cache/clear` now also clears the Redis runtime cache namespace.

**Phase 2 (implemented):**
- `packages/ui/backend/src/monitor_ui/routers/chat_persistence.py` now uses Redis as a shared warm cache for `chat_sessions` and `chat_messages`.
- New play requests can rehydrate session/message state from Redis before falling back to MongoDB, reducing warm-start latency and improving cross-process consistency.
- Session/message saves emit lightweight Redis coordination events (`chat_events:<session_id>`).

**Phase 3 (implemented):**
- `packages/ui/backend/src/monitor_ui/routers/chat.py` now maintains session-scoped websocket listeners and rebroadcasts streamed `start` / `token` / `done` events to every connected client on that session.
- When Redis is available, those stream events are also published on `chat_events:<session_id>` and replayed to sockets attached to other backend processes, enabling live multi-backend fan-out without changing canonical persistence.

**Next phases (not required for correctness):**
1. durable queue coordination for ingestion workers
2. transient locks for World Forge collaborative editing

---

## MCP Architecture

```
┌────────────────────────────────────────────┐
│         AGENT (Claude/LLM)                 │
│  - ContextAssembly                         │
│  - Narrator                                │
│  - CanonKeeper                             │
│  - Resolver                                │
│  - Indexer / Analyzer / IngestionPipeline  │
│  - WorldArchitect / NPCVoice              │
└────────────────┬───────────────────────────┘
                 │
                 ▼ (MCP Protocol)
┌────────────────────────────────────────────┐
│       MCP SERVER (Data Layer Gateway)      │
│  - Tool registration                       │
│  - Schema validation                       │
│  - Authority enforcement                   │
│  - Request routing                         │
└─┬───────┬────────┬────────┬────────┬───────┘
  │       │        │        │        │
  ▼       ▼        ▼        ▼        ▼
┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
│Neo4│ │Mongo│ │Qdrant│ │OpenS│ │MinIO│
└────┘ └────┘ └────┘ └────┘ └────┘
```

---

## 1. MCP Server Configuration

### 1.1 Server Metadata

```json
{
  "name": "monitor-data-layer",
  "version": "1.0.0",
  "description": "MONITOR Data Layer API via MCP",
  "protocol_version": "2024-11-05",
  "capabilities": {
    "tools": {},
    "resources": {},
    "prompts": {}
  }
}
```

### 1.2 Authority Context

Every MCP request must include agent identity:

```json
{
  "agent_id": "uuid",
  "agent_type": "CanonKeeper | Narrator | ContextAssembly | Resolver | Indexer | Analyzer | IngestionPipeline | WorldArchitect | NPCVoice"
}
```

This is passed via MCP context and validated against the authority matrix.

---

## 2. Tool Naming Convention

```
<domain>_<operation>_<entity>

Examples:
- neo4j_create_entity
- neo4j_get_entity
- neo4j_query_entities
- mongodb_create_scene
- mongodb_append_turn
- qdrant_semantic_search
- composite_assemble_scene_context
- composite_canonize_scene
```

---


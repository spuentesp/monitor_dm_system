# MONITOR Data Layer API

*Complete API contract for interacting with MONITOR's multi-database data layer.*

---

## Overview

The Data Layer is a **service interface** between agents and the five storage systems. Agents interact with data exclusively through these APIs, never directly with databases.

**Key principle:** Data layer is stateless and agent-agnostic. It validates, enforces authority, and ensures consistency.

> **Note:** This file is the API/specification reference. For the currently implemented tool surface and auth rules, cross-check `packages/data-layer/src/monitor_data/` and `packages/data-layer/src/monitor_data/middleware/auth.py`.
>
> **Implementation reality (April 2026):** the live MCP server in `monitor_data.server` auto-registers `neo4j_*`, `mongodb_*`, `qdrant_*`, and `ingest_*` tool families. MinIO access is currently surfaced through the ingest flow; standalone OpenSearch and `rpg_*` registration remain planned/spec-level concerns.

---

## API Architecture

```
┌─────────────────────────────────────────────┐
│           AGENT LAYER                       │
│  (Narrator, CanonKeeper, ContextAssembly...)│
└────────────────┬────────────────────────────┘
                 │
                 ▼ (MCP or gRPC)
┌─────────────────────────────────────────────┐
│        DATA LAYER API                       │
│  - Validation                               │
│  - Authority enforcement                    │
│  - Cross-DB coordination                    │
└─┬───────┬────────┬────────┬────────┬────────┘
  │       │        │        │        │
  ▼       ▼        ▼        ▼        ▼
┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
│Neo4│ │Mongo│ │Qdrant│ │OpenS│ │MinIO│
└────┘ └────┘ └────┘ └────┘ └────┘
```

---


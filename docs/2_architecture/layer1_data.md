---
description: "Details Layer 1: Data, Databases, and Schemas."
tags: [architecture, data, layer-1, databases]
layer: 1
---

# Layer 1: Data Layer (`monitor-data-layer`)

The foundation of the system. It owns all database connections, data schemas (Pydantic), and the "Canonical Truth".

## Responsibilities
- **Database CRUD**: Direct interactions with underlying databases.
- **Authority Enforcement**: Gating operations based on user/agent permissions.
- **Schema Validation**: Defining and enforcing Pydantic v2 data models.
- **MCP Server**: Exposing data operations as Model Context Protocol tools.

## Databases & Usage
- **Neo4j (Canon)**: Stores the canonical knowledge graph (Entities, Facts, Relationships).
- **MongoDB (State)**: Stores mutable state, turn history, and `ProposedChange` documents.
- **Qdrant (Vectors)**: Stores embeddings for semantic search.
- **PostgreSQL**: Stores configuration and management metadata.
- **MinIO**: Object storage for uploaded files and documents.

## Strict Rules
- **Rule:** Never imports from Layer 2 or 3.
- **Rule:** All tools must be exposed via MCP. Agents should not bypass MCP to access databases.

## See Also
- [The Three Layers](./the_three_layers.md)
- [MCP Transport](./mcp_transport.md)

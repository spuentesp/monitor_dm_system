---
description: "Index for Architecture documentation."
tags: [architecture, index]
layer: 0
---

# 2. Architecture

This directory details the technical architecture of MONITOR, primarily organized around the 3-Layer Cake dependency pattern.

## Documents

- **[The Three Layers](./the_three_layers.md)**: Defines the boundaries and rules of the 3-Layer architecture.
- **[Layer 1: Data](./layer1_data.md)**: Database clients, Pydantic schemas, and MCP tools.
- **[Layer 2: Agents](./layer2_agents.md)**: LangGraph loops, BaseAgent, and DSPy modules.
- **[Layer 3: Interface](./layer3_interface.md)**: CLI and Web interfaces.
- **[Data Model & Workflow](./data_model_workflow.md)**: Explains the 5 databases (Neo4j, MongoDB, Qdrant, MinIO, Postgres) and how they interact.
- **[MCP Transport](./mcp_transport.md)**: How agents interact with Layer 1 via Model Context Protocol.

## The Proposed Change Pattern
To preserve the integrity of the Neo4j Knowledge Graph, **no agent (except CanonKeeper) can write to Neo4j**. Instead, agents create `ProposedChange` documents in MongoDB. The CanonKeeper reviews these against established policies and commits accepted proposals to Neo4j.

## See Also
- [Root Index](../_index.md)

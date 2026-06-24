---
description: "The root index for all MONITOR agent documentation."
tags: [index, root, map]
layer: 0
---

# MONITOR Documentation Map

Welcome to the MONITOR Agent Documentation. This structure is designed to be highly modular and dense to maximize context efficiency.

## 1. Product (What are we building?)
- [Vision & Modes](./1_product/vision_and_modes.md): The core pitch, modes of operation, and non-goals.
- [Epics](./1_product/epics.md): The 9 core development epics and their coverage.
- [Ideal State & Use Cases](./1_product/ideal_state.md): Examples of how the three modes should ideally operate.

## 2. Architecture (How is it built?)
- [The Three Layers](./2_architecture/the_three_layers.md): The strict `3-Layer Cake` dependency rules.
- [Layer 1: Data](./2_architecture/layer1_data.md): Databases and tools.
- [Layer 2: Agents](./2_architecture/layer2_agents.md): Specialized workers and DSPy.
- [Layer 3: Interface](./2_architecture/layer3_interface.md): CLI and UI.
- [MCP Transport](./2_architecture/mcp_transport.md): How agents communicate with data.

## 3. Loops & Systems (Dynamic Behaviors)
- [Scene Loop](./3_loops_and_systems/scene_loop.md): Turn-by-turn resolution.
- [Story Loop](./3_loops_and_systems/story_loop.md): Campaign progression.
- [Conversation Loop](./3_loops_and_systems/conversation_loop.md): NPC dialogue logic.
- [World Building Loop](./3_loops_and_systems/world_building_loop.md): Collaborative creation.

## 4. Ontology (Data Models)
- [Fact Canon Levels](./4_ontology/fact_canon_levels.md): How truth is managed.
- [Entity Types](./4_ontology/entity_types.md): Archetypes vs Instances.
- [Graph Relationships](./4_ontology/graph_relationships.md): How Neo4j nodes connect.

## 5. Infrastructure (DevOps & Env)
- [Database Cluster](./5_infrastructure/database_cluster.md): The docker-compose setup.
- [Observability](./5_infrastructure/observability.md): Structlog and tracing.
- [Lain MCP Proxy](./5_infrastructure/lain_mcp_proxy.md): How Lain integrates.

## See Also
- [AGENTS.md](../AGENTS.md) - The primary system instructions for agents.

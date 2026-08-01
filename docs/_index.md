---
description: "The root index for all MONITOR agent documentation."
tags: [index, root, map]
layer: 0
---

# MONITOR Documentation Map

Welcome to the MONITOR Agent Documentation. This structure is designed to be highly modular and dense to maximize context efficiency.

## 1. Product (What are we building?)
- [Vision & Modes](./1_product/vision_and_modes.md): The core pitch, modes of operation, and non-goals.
- [Epics](./1_product/epics.md): The 12 core development epics and their coverage.
- [Ideal State & Use Cases](./1_product/ideal_state.md): Examples of how the three modes should ideally operate.

## 2. Architecture (How is it built?)
- [The Three Layers](./2_architecture/the_three_layers.md): The strict `3-Layer Cake` dependency rules.
- [Layer 1: Data](./2_architecture/layer1_data.md): Databases and tools.
- [Layer 2: Agents](./2_architecture/layer2_agents.md): Specialized workers and DSPy.
- [Layer 3: Interface](./2_architecture/layer3_interface.md): CLI and UI.
- [MCP Transport](./2_architecture/mcp_transport.md): How agents communicate with data.

### Current architecture deep-dives (authoritative)
- [Project Status](./STATUS.md): **Canonical what-is-done / what-is-not**, verified against code (2026-07-23).
- [Gap Remediation Plan](./architecture/GAP_REMEDIATION_PLAN.md): Plan addressing every verified open gap (G-1 to G-9).
- [GM Assistant Mode Plan](./architecture/GM_ASSISTANT_MODE_PLAN.md): Full implementation plan for the Co-Pilot mode (supersedes G-5).
- [Forge Mode Plan](./architecture/FORGE_MODE_PLAN.md): Full implementation plan for the World Design / authoring mode.
- [GM as Authority](./architecture/GM_AS_AUTHORITY.md): **How narration works now** — the GMAgent → Narrator → Resolver pipeline, the `gm_tools` registry, and `GMVerdict`.
- [Retrieval Service](./architecture/RETRIEVAL_SERVICE.md): The single owner of embeddings + Qdrant (pinned model, model/dim guard, HyDE + rerank, `nearest`).
- [De-heuristic Principle](./architecture/DE_HEURISTIC_PRINCIPLE.md): Why classification is semantic/LLM, never keyword tables — and what that removed.
- [Play & Forge Direction](./architecture/PLAY_AND_FORGE_DIRECTION.md): Product direction for mode-first play and the authoring/playing split.
- [Character Templates & GM Conditioning Plan](./architecture/CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md): Extends Play & Forge §5/§6 with live multi-world test evidence; adds the (previously undesigned) story-premise conditioning gap.
- [Ingestion Pipeline Audit](./architecture/INGESTION_PIPELINE_AUDIT.md): Findings + remediation plan for game-system ingestion and character-creation parsing (silent degenerate extraction, missing provenance, step_type mislabeling).
- [Multi-Tenancy Plan](./architecture/MULTI_TENANCY_PLAN.md): Phase 1 of multi-user support — per-account private campaigns, public template/character-card gallery, and the auth/ownership model needed to get there; preserves the seam for a later multiplayer phase.

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

## 6. Reference & Guides
- [Gameplay Examples & GM Craft](./6_reference/_index.md): Narrative examples and design principles.
- [Use Case Catalog](./USE_CASES.md): The full list of target workflows and specifications.
- [E2E Testing (LLM-vs-LLM + full-stack)](./testing/INDEX.md): How to run the autonomous-GM and replay suites.

## See Also
- [AGENTS.md](../AGENTS.md) - The primary system instructions for agents.

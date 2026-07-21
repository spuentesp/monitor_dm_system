---
description: "Index for Ontology and Data Models."
tags: [ontology, index, data-model]
layer: 1
---

# 4. Ontology & Data Models

This directory defines the structures, meaning, and taxonomies of data stored in MONITOR's databases (primarily Neo4j).

## Core Concepts
- **[Fact Canon Levels](./fact_canon_levels.md)**: How truth is managed (e.g., rumor vs. hard canon).
- **[Entity Types](./entity_types.md)**: The difference between Archetypes (templates) and Instances (realized entities).
- **[Graph Relationships](./graph_relationships.md)**: How nodes in Neo4j connect to form the world graph.

## See Also
- [Layer 1: Data](../2_architecture/layer1_data.md)

---

## Entity Promotion: `anchor` vs `flavor`

The Narrator tags every newly-introduced entity with one of two intents so the engine knows whether it deserves a permanent UUID in Neo4j or should be garbage-collected at scene end.

| Tag | Meaning | Promotion path |
|---|---|---|
| `[Name](entity:anchor)` | Structurally important — has a stat block, faction tie, or recurring role | Auto-promoted to Neo4j by CanonKeeper |
| `[Name](entity:flavor)` | Environmental set dressing or disposable extra | Promoted only if `interaction_count > 3` (graduated by use) **or** mechanically bound by a `state_change`/`event`/combat payload. Otherwise discarded at scene end |

Untagged entities are silently ignored by the parser — the narrator MUST type every new entity on first introduction. The promotion rules are documented in detail in [§6 of the data-model workflow](../2_architecture/data_model_workflow.md#6-entity-promotion-gate-dl-2).

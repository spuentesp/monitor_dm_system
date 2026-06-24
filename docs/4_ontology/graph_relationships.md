---
description: "Standard edge labels used in the Neo4j Knowledge Graph."
tags: [ontology, neo4j, relationships]
layer: 1
---

# Graph Relationships

The Neo4j database uses standard edge (relationship) labels to construct the Knowledge Graph.

## Core Relationships
- `LOCATED_IN`: Spatial hierarchy (e.g., Tavern -> City -> Region).
- `OWNS` / `HAS_INVENTORY`: Possession.
- `KNOWS` / `ALLIED_WITH` / `ENEMIES_WITH`: Social topology.
- `BELIEVES`: Connects an Entity to a Subjective Fact.
- `INSTANCE_OF`: Connects an Instance to its Archetype.

By traversing these edges, the `ContextAssembly` agent builds the contextual package needed for a scene.

## See Also
- [Ontology Index](./_index.md)
- [Layer 1: Data](../2_architecture/layer1_data.md)

# Data Rules

## Databases
- **Neo4j**: Canonical Truth (UUIDs only).
- **MongoDB**: Narrative/Staging (Proposals, Scenes).
- **Qdrant**: Index (Derived).

## Canonization Flow
1. **Proposal**: Staged in MongoDB (`proposed`).
2. **Scene End**: CanonKeeper evaluates.
3. **Canon**: Written to Neo4j (`canon`).
4. **Index**: Indexed in Qdrant.

## Entities
- **Archetype**: Timeless concept (no state).
- **Instance**: Specific object (has State Tags).

# Q-11: World Graph Explorer

**Actor:** User
**Trigger:** Universes → [Universe] → Graph

**Purpose:** Visualise all entities in a universe as an interactive graph. Nodes are entities/locations/factions/concepts; edges are lore facts and relationships.

**Flow:**
1. Select universe
2. Load entity graph (nodes + edges from Neo4j)
3. Interactive canvas: pan, zoom, node selection
4. Filter by entity type, tags, or canon level
5. Click node → inline detail panel (name, type, tags, description)
6. Click edge → relationship or lore fact detail
7. Expand node → load its neighbours on demand
8. Export graph as SVG or JSON

**Output:** Interactive visual graph; optional export.

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity_graph(universe_id, filters={}) -> WorldGraph
neo4j_get_entity_neighbours(entity_id, depth=1) -> WorldGraph
```

**Layer 2 (Agents):**
- `ContextAssembly.build_world_graph(universe_id, filters)` — Structure graph data for rendering

**UI:**
- `WorldGraph`, `GraphNode`, `GraphEdge` types already defined in `packages/ui/frontend/src/lib/types.ts`
- React Flow canvas at `/universes/[id]/graph`

---

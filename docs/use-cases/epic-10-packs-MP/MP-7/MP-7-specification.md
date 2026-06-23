# MP-7: Apply Pack → New World

**Actor:** User
**Trigger:** Packs → [Pack] → Apply → New World

**Purpose:** Create a fresh Multiverse and Universe from a pack's contents. All pack items are committed to canon.

**Flow:**
1. User selects "Apply to New World"
2. Name the world (pre-filled from pack name)
3. System creates Multiverse → Universe in Neo4j (via CanonKeeper)
4. All entities → `EntityArchetype` nodes
5. All axioms → Axiom nodes linked to universe
6. All lore facts → Fact nodes
7. Game system linked to universe
8. Apply record appended to pack's `apply_history`

**Output:** New canon world; pack's `apply_history` updated.

### Implementation

**Layer 2 (Agents):**
```python
PackApplicator.apply_to_new_world(pack_id, world_name) -> ApplyResult
# All Neo4j writes route through CanonKeeper
```

**Layer 1 (Data Layer):**
```python
neo4j_create_multiverse(params)          # CanonKeeper only
neo4j_create_universe(multiverse_id, params)  # CanonKeeper only
neo4j_create_entity(universe_id, params) # CanonKeeper only — per entity
neo4j_create_fact(universe_id, params)   # CanonKeeper only — per lore/axiom
```

---

# P-17: Persist Universe Continuity Across Stories

**Actor:** User / System
**Trigger:** A scene or story ends, or a new story starts in an existing universe

**Purpose:** Ensure that if several stories are played inside the same universe, the universe retains the accepted consequences of earlier stories.

**Flow:**
1. During play, facts, state changes, injuries, relationship updates, and discoveries are staged as `ProposedChange` records
2. At scene end (P-8), CanonKeeper evaluates and commits accepted changes to canon
3. The universe timeline, participating entities, and relevant working state are updated
4. When a later story starts in the same universe, ContextAssembly retrieves the accumulated canon and recent narrative state
5. NPCs, locations, factions, and unresolved threads reflect what earlier player stories changed

**Output:** persistent continuity inside a universe across multiple stories, with a complete audit trail

### Implementation

**Layer 1 (Data Layer):**
```python
# Existing persistence path:
mongodb_list_proposed_changes(scene_id=...) -> proposals
neo4j_create_fact(...) -> Fact
neo4j_update_state_tags(entity_id, tags)
neo4j_create_event(...) -> Event
mongodb_update_scene(scene_id, {"status": "completed"})
```

**Layer 2 (Agents):**
- `CanonKeeper.evaluate_proposals(...)` — Commit accepted scene outcomes
- `ContextAssembly.get_universe_state(universe_id)` — Load persistent continuity for future stories
- `Narrator.generate_recap(...)` — Surface prior consequences when resuming play

**Persistence Guarantee:**

| Scope | What persists |
|------|----------------|
| Story | scene sequence, recap, plot beats |
| Universe | accepted canon changes from all stories in that timeline |
| Multiverse | baseline setting canon shared by its universes |

---

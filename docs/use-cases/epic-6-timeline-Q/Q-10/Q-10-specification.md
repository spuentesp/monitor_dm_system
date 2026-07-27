# Q-10: Audit Trail / History View

**Actor:** User (GM, Admin)
**Trigger:** Query → History, Entity → History, or troubleshooting

**Purpose:** View the complete history of changes to any entity, fact, or story element.

**Flow:**

1. **Select Subject:**
   - Entity, Fact, Story, Scene, or Universe
   - Or view global recent changes

2. **View History:**
   - Chronological list of all changes
   - Filter by: time range, author, change type
   - Show: what changed, who changed it, when, why (evidence)

3. **Drill Down:**
   - Click change to see full details
   - View before/after state
   - View related changes (cascading effects)

4. **Actions:**
   - Compare versions
   - Revert to previous state (with new fact as explanation)
   - Export history

### Implementation

**Layer 1 (Data Layer):**
```python
# History queries (MongoDB change_log)
mongodb_get_entity_history(entity_id, limit=50) -> list[ChangeRecord]
mongodb_get_fact_history(fact_id) -> list[ChangeRecord]
mongodb_get_story_history(story_id, include_scenes=True) -> list[ChangeRecord]
mongodb_get_recent_changes(universe_id=None, limit=50, filters={}) -> list[ChangeRecord]

# Comparison
mongodb_compare_versions(subject_id, time_a, time_b) -> Comparison

# Historical state reconstruction (DL-19)
neo4j_get_entity_at_time(entity_id, timestamp) -> Entity

# Revert (creates new change, doesn't delete)
neo4j_revert_to_version(entity_id, timestamp, reason) -> fact_id
```

**Layer 2 (Agents):**
- `ContextAssembly.get_entity_history(entity_id)` — Compile full history
- `ContextAssembly.compare_versions(entity_id, time_a, time_b)` — Diff two states
- `CanonKeeper.revert_entity(entity_id, timestamp, reason)` — Create reverting fact
- `Narrator.explain_history(history)` — Generate human-readable summary

**Layer 3 (CLI):**
```bash
# View entity history
monitor query history --entity <UUID>
monitor query history --entity <UUID> --since "2025-01-01"

# View fact history
monitor query history --fact <UUID>

# View story/scene history
monitor query history --story <UUID>

# View universe-wide recent changes
monitor query history --universe <UUID> --limit 100

# Compare versions
monitor query compare --entity <UUID> --time-a "2025-01-01" --time-b "2025-06-01"

# Revert
monitor manage entity revert <UUID> --to "2025-01-01" --reason "Incorrect data"
```

**Change Record Schema:**
```python
@dataclass
class ChangeRecord:
    id: UUID
    subject_type: SubjectType  # entity, fact, story, scene, relationship, axiom
    subject_id: UUID

    change_type: ChangeType  # created, updated, deleted, state_tag_added, etc.
    timestamp: datetime

    field_path: str | None     # "state_tags", "properties.hp"
    old_value: Any
    new_value: Any

    author: str                # "CanonKeeper", "User:123", "System"
    authority: str             # "gm", "player", "system"

    evidence_type: str | None  # "scene", "turn", "proposal", "manual"
    evidence_id: UUID | None
    reason: str | None

    transaction_id: UUID | None  # Groups related changes
```

**Database Reads:**

| Database | Collection | Query |
|----------|------------|-------|
| MongoDB | `change_log` | `WHERE subject_id = ? ORDER BY timestamp DESC` |
| Neo4j | Entity | Current state for comparison |
| MongoDB | `change_log` | Transaction group queries |

---

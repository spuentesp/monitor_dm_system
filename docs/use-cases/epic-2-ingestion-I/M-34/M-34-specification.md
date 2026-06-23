# M-34: World Snapshots

**Actor:** User (GM/World Designer)
**Trigger:** Manage → Snapshot, or automatic (story milestones)

**Purpose:** Create point-in-time snapshots of world state for backup, comparison, branching, or "what-if" exploration.

**Flow:**

1. **Create Snapshot:**
   - Select scope: Universe, region, or story
   - Name snapshot (e.g., "Before the Battle of Helm's Deep")
   - Optionally add description/notes
   - System captures current state of all entities, facts, and relationships

2. **Automatic Snapshots:**
   - Story start (P-1)
   - Before major events (marked by GM)
   - At story milestones
   - Before timeline branches (P-14 flashback)

3. **View Snapshot:**
   - Compare current state to snapshot
   - Highlight changes (added, modified, deleted)
   - Generate diff report

4. **Restore Snapshot:**
   - Revert to snapshot state (destructive)
   - Branch from snapshot (creates new timeline)
   - Selective restore (specific entities only)

5. **Branch from Snapshot:**
   - Create parallel universe from snapshot
   - Explore "what-if" scenarios
   - Independent evolution from branch point

#### Implementation

**Layer 1 (Data Layer):**
```python
# Snapshot management
mongodb_create_snapshot(scope, scope_id, params) -> snapshot_id
mongodb_get_snapshot(snapshot_id) -> WorldSnapshot
mongodb_list_snapshots(scope_id) -> list[WorldSnapshotSummary]
mongodb_delete_snapshot(snapshot_id)

# Capture current state
async def capture_snapshot(scope: SnapshotScope, scope_id: UUID) -> Snapshot:
    if scope == SnapshotScope.UNIVERSE:
        entities = await neo4j_list_entities(universe_id=scope_id)
        facts = await neo4j_list_facts(universe_id=scope_id)
        relationships = await neo4j_list_relationships(universe_id=scope_id)
        axioms = await neo4j_list_axioms(universe_id=scope_id)
    elif scope == SnapshotScope.STORY:
        # Capture story-related entities and story state
        ...

    return Snapshot(
        scope=scope,
        scope_id=scope_id,
        entities=entities,
        facts=facts,
        relationships=relationships,
        axioms=axioms,
        captured_at=datetime.now()
    )

# Compare states
mongodb_compare_snapshots(snapshot_a_id, snapshot_b_id) -> SnapshotDiff
mongodb_compare_to_current(snapshot_id, scope_id) -> SnapshotDiff
```

**Layer 2 (Agents):**
- `CanonKeeper.create_snapshot(scope, scope_id, params)` — Capture state
- `CanonKeeper.restore_snapshot(snapshot_id, mode)` — Restore state
- `Orchestrator.branch_from_snapshot(snapshot_id, new_universe_name)` — Create branch

**Layer 3 (CLI):**
```bash
monitor manage snapshot create --universe <UUID> --name "Pre-War State"
monitor manage snapshot create --story <UUID> --name "Before Final Battle"
monitor manage snapshot list --universe <UUID>
monitor manage snapshot view <SNAPSHOT_ID>
monitor manage snapshot compare <SNAPSHOT_ID> --to-current
monitor manage snapshot compare <SNAPSHOT_A> <SNAPSHOT_B>
monitor manage snapshot restore <SNAPSHOT_ID>
monitor manage snapshot branch <SNAPSHOT_ID> --name "What-If Timeline"
```

**World Snapshot Schema:**
```python
@dataclass
class WorldSnapshot:
    id: UUID
    name: str
    description: str | None

    scope: SnapshotScope  # universe, story, region
    scope_id: UUID

    # Captured state
    entities: list[EntityState]
    facts: list[FactState]
    relationships: list[RelationshipState]
    axioms: list[AxiomState]

    # For story scope
    story_state: StoryState | None
    scene_count: int
    turn_count: int

    # Metadata
    trigger: SnapshotTrigger  # manual, story_start, milestone, pre_branch
    created_at: datetime
    created_by: str  # "system" or user ID

    # Size metrics
    entity_count: int
    fact_count: int
    total_size_kb: int

class SnapshotScope(Enum):
    UNIVERSE = "universe"
    STORY = "story"
    REGION = "region"

class SnapshotTrigger(Enum):
    MANUAL = "manual"
    STORY_START = "story_start"
    MILESTONE = "milestone"
    PRE_BRANCH = "pre_branch"
    PRE_FLASHBACK = "pre_flashback"
    SCHEDULED = "scheduled"

@dataclass
class EntityState:
    entity_id: UUID
    entity_type: str
    name: str
    properties: dict
    state_tags: list[str]

@dataclass
class SnapshotDiff:
    snapshot_a_id: UUID
    snapshot_b_id: UUID | None  # None = compare to current

    added_entities: list[UUID]
    modified_entities: list[EntityDiff]
    deleted_entities: list[UUID]

    added_facts: list[UUID]
    modified_facts: list[FactDiff]
    deleted_facts: list[UUID]

    added_relationships: list[UUID]
    deleted_relationships: list[UUID]

    summary: str  # Human-readable summary

@dataclass
class EntityDiff:
    entity_id: UUID
    name: str
    changed_properties: dict[str, tuple[Any, Any]]  # {prop: (old, new)}
    added_state_tags: list[str]
    removed_state_tags: list[str]
```

**Snapshot Comparison Prompt:**
```python
SNAPSHOT_COMPARE_PROMPT = """
Compare these two world states and provide a narrative summary of changes.

Snapshot A (captured {time_a}): {name_a}
Snapshot B (captured {time_b}): {name_b}

Added entities: {added_entities}
Deleted entities: {deleted_entities}
Modified entities: {modified_entities}
Added facts: {added_facts}
Deleted facts: {deleted_facts}

Provide:
1. Brief narrative summary of what changed (1-2 paragraphs)
2. Most significant changes (bullet points)
3. Any potential continuity issues or inconsistencies
"""
```

---

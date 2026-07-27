# M-35: Universe Fork

**Actor:** User (GM/World Designer)
**Trigger:** Manage → Universe → Fork

**Purpose:** Create an alternate universe that branches from an existing one, allowing "what-if" exploration without affecting the original.

**Flow:**

1. **Select Branch Point:**
   - From current state
   - From a snapshot (M-34)
   - From a specific point in time

2. **Configure Fork:**
   - Name new universe
   - Describe divergence point
   - Select what to copy (all, entities only, etc.)

3. **Create Fork:**
   - Copy universe structure
   - Copy entities and relationships
   - Copy facts (up to branch point)
   - Mark as branch of original

4. **Divergent Evolution:**
   - Changes in fork don't affect original
   - Track relationship to parent universe
   - Optionally sync specific elements later

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_fork_universe(universe_id, params) -> new_universe_id
neo4j_get_universe_lineage(universe_id) -> list[UniverseLineage]
```

**Layer 2 (Agents):**
- `CanonKeeper.fork_universe(universe_id, branch_point, params)` — Create fork

**Layer 3 (CLI):**
```bash
monitor manage universe fork <UNIVERSE_ID> --name "Dark Timeline"
monitor manage universe fork <UNIVERSE_ID> --from-snapshot <SNAPSHOT_ID>
monitor manage universe lineage <UNIVERSE_ID>  # Show parent/children
```

**Universe Fork Schema:**
```python
@dataclass
class UniverseFork:
    id: UUID
    parent_universe_id: UUID
    name: str
    description: str

    branch_point: BranchPoint
    divergence_description: str  # What's different

    # Tracking
    created_at: datetime
    facts_at_fork: int
    entities_at_fork: int

@dataclass
class BranchPoint:
    type: str  # "current", "snapshot", "timestamp"
    reference_id: UUID | None  # Snapshot ID if from snapshot
    timestamp: datetime | None  # If from timestamp
```

---

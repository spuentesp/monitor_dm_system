# I-13: Cross-Source Synthesis (Merge Entities)

**Actor:** User
**Trigger:** Ingest → Sources → Merge Candidates, or World Forge → Entities → Merge

**Purpose:** When multiple source documents describe the same entity (e.g., three different PDFs all describe "Gandalf the Grey" with overlapping details), synthesize them into a single high-confidence entity. The user reviews differences, selects the best fields from each source, and creates a merged entity proposal.

**Problem Solved:**
Without this use case, users would end up with duplicate entities (e.g., "Gandalf the Grey", "Gandalf", "Mithrandir") representing the same character, each with partial information. Cross-source synthesis enables a canonical, authoritative entity with the best information from all sources.

**Flow:**

### Phase 1: Detect Merge Candidates
1. **Automatic detection**: After each ingestion, the system identifies potential duplicates based on:
   - Name similarity (fuzzy matching, e.g., "Gandalf" ≈ "Mithrandir")
   - Entity type match (both must be `character`, `location`, etc.)
   - Property overlap (e.g., both have `race: "Maiar"`, `age: "unknown"`)
   - Shared context (both appear in same universe/game system)
2. **Candidate grouping**: Group entities into merge candidates (e.g., [Entity A, Entity B, Entity C] all refer to same character)
3. **Confidence scoring**: Assign merge confidence (0.0-1.0) based on similarity metrics
4. **Show candidates**: Display in "Merge Candidates" panel with confidence score and key differences

### Phase 2: Review and Compare
1. User clicks merge candidate group → opens comparison view
2. Side-by-side comparison table:
   | Field | Source A (PDF 1) | Source B (PDF 2) | Source C (PDF 3) | Merged |
   |-------|-----------------|-----------------|-----------------|--------|
   | name | "Gandalf the Grey" | "Gandalf" | "Mithrandir" | [select] |
   | entity_type | character | character | character | character |
   | description | "A wizard..." | "The Grey Pilgrim..." | "Wanderer of the West..." | [select] |
   | properties.race | "Maiar" | "Maiar" | "Maiar" | "Maiar" |
   | properties.age | "unknown" | "2000+" | "ancient" | [select] |
3. Highlight conflicts (different values for same field) in red
4. Show agreement (same values across all sources) in green
3. Allow user to select best value for each field from any source, or enter custom value
4. Preview merged entity in real-time

### Phase 3: Resolve Relationships
1. Review all relationships from each source entity:
   - A → ALLIED_WITH → Frodo (confidence 0.9)
   - B → LEADS → Fellowship (confidence 0.8)
   - C → KNOWS → Saruman (confidence 0.7)
2. User selects which relationships to keep (can keep all, some, or none)
3. For conflicting relationships (e.g., A HOSTILE_TO X vs. B ALLIED_WITH X), user chooses
4. Relationship confidence can be boosted manually (e.g., from 0.7 to 1.0 if user trusts the source)

### Phase 4: Create Merge Proposal
1. User confirms merge → system creates `ProposedChange` in MongoDB
2. Proposal contains:
   - EntityCreate with merged fields
   - List of source entities being merged (for traceability)
   - Evidence refs pointing to all source documents
   - Resolution notes (user's merge decisions)
   - Confidence score (boosted if user manually reviewed)
3. Proposal goes to CanonKeeper for approval (see I-4)
4. If approved: old entities marked as `retconned`, new entity created with merged data
5. All relationships from old entities re-pointed to new entity

**Output:** Single high-confidence entity with best information from all sources; old entities marked as retconned with traceability back to sources.

### Implementation

**Layer 1 (Data Layer):**
```python
# New schemas in ingestion_delta.py
class EntityMergeCandidate(BaseModel):
    """Group of entities that likely represent the same thing."""
    entity_ids: List[UUID]  # Entities to merge
    merge_confidence: float  # 0.0-1.0
    similarity_metrics: Dict[str, float]  # name_sim, type_match, prop_overlap
    conflicting_fields: List[str]  # Fields with different values
    agreed_fields: List[str]  # Fields with same values

# New MCP tool
def mongodb_find_merge_candidates(
    universe_id: UUID,
    min_confidence: float = 0.7,
) -> List[EntityMergeCandidate]:
    """Find groups of entities that should be merged."""

# New MCP tool
def mongodb_create_merge_proposal(
    merged_entity: EntityCreate,
    source_entity_ids: List[UUID],
    resolution_notes: Dict[str, str],
) -> ProposedChange:
    """Create a ProposedChange for merging entities."""
```

**Layer 2 (Agents):**
```python
# New agent: MergerAgent
class MergerAgent(BaseAgent):
    """Handles entity merging across sources."""

    async def detect_merge_candidates(
        self,
        universe_id: UUID,
    ) -> List[EntityMergeCandidate]:
        """Use similarity algorithms to find duplicates."""

    async def create_merge_proposal(
        self,
        merged_entity: EntityCreate,
        source_entity_ids: List[UUID],
        user_decisions: Dict[str, Any],
    ) -> ProposedChange:
        """Create a proposal for CanonKeeper to review."""
```

**Layer 3 (CLI / UI):**
```bash
# CLI commands
monitor ingest merge-candidates <universe_id>
monitor ingest merge <candidate_id> --interactive
```

```typescript
// Frontend: MergePanel.tsx
interface MergeCandidate {
  entity_ids: string[];
  merge_confidence: number;
  entities: EntityResponse[];  // Full entity data for comparison
  conflicts: FieldConflict[];  // Fields with different values
}

interface FieldConflict {
  field_name: string;
  values: Array<{ entity_id: string; value: any; confidence: number }>;
  merged_value?: any;  // User-selected merged value
}
```

**Merge Algorithms:**
- **Name similarity**: Levenshtein distance, Jaro-Winkler, phonetic matching (for aliases like "Mithrandir" vs "Gandalf")
- **Type matching**: Exact match on `entity_type`
- **Property overlap**: Jaccard similarity on property keys and values
- **Context overlap**: Shared universe, game system, appearing in same relationships

### Edge Cases
- **Circular merges**: If A ≈ B and B ≈ C and C ≈ A, group all three together
- **Conflicting entity types**: Block merge if one is `character` and another is `location` (different fundamental types)
- **Identity ambiguity**: If two entities are truly distinct but have similar names (e.g., "King Arthur" vs "Arthur Pendragon"), user must explicitly reject merge
- **Partial information**: One source has full entity, another has just name + one property → still mergeable if confidence is high
- **Relationship conflicts**: If A HOSTILE_TO X but B ALLIED_WITH X, user must resolve (choose one, or keep both if it's a complex dynamic)

### Cross-References
- **I-4 (Proposal Review)**: Merge proposals go through same review flow as other proposals
- **DL-14 (Relationships)**: Merged entity inherits selected relationships from all sources
- **DL-2 (Entities)**: Merged entity follows EntityCreate schema
- **Q-2 (Search)**: After merge, old entity names redirect to merged entity (via retconned flag)

---

---

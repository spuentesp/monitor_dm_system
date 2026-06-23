# MP-1: Create Pack Manually

**Actor:** User
**Trigger:** Packs → New Pack → Manual

**Purpose:** Author a pack from scratch, without a PDF source.

**Flow:**
1. Name the pack, optional description and genre tags
2. Optionally link a game system; optionally link source documents
3. Start with empty entity/axiom/lore lists
4. Add content in Pack Editor (MP-4)
5. Save

**Output:** New pack in MongoDB with `status: "ready"`.

### Implementation
```python
POST /packs  →  {name, description?, game_system_id?, tags?, source_ids?}
```

---

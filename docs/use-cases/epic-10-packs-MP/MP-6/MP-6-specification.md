# MP-6: Save as New Pack (Independent)

**Actor:** User
**Trigger:** Pack Editor → Save as New Pack

**Purpose:** Save the current editor state as a fully independent pack with no lineage.

**Flow:**
1. User selects "Save as New Pack"
2. Prompt: name
3. New pack created with `parent_pack_ids = []`

**Output:** New independent pack.

### Implementation
```python
POST /packs  →  {name, parent_pack_ids: [], ...content}
```

---

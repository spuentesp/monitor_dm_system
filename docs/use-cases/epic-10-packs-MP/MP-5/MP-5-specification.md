# MP-5: Save Pack with Lineage

**Actor:** User
**Trigger:** Pack Editor → Save with Lineage

**Purpose:** Save the current editor state as a new pack, recording which packs it was derived from.

**Flow:**
1. User selects "Save with Lineage"
2. Prompt: name for new pack (pre-filled from source pack names)
3. New pack created with `parent_pack_ids = [source_pack_ids…]`
4. Source packs are unchanged

**Output:** New pack with lineage metadata; source packs unchanged.

### Implementation
```python
POST /packs  →  {name, parent_pack_ids: [...], ...content}
# parent_pack_ids are informational — not enforced FKs; source packs can be deleted
```

---

# I-10: Link Pack ↔ Source

**Actor:** User
**Trigger:** Pack detail → Sources panel, or Source detail → Packs panel

**Purpose:** Associate or disassociate a pack with a source document after the fact. The link is a reference only — no data is moved.

**Flow:**
1. From pack: view linked sources, add link (pick from source library), remove link
2. From source: view derived packs, link to existing pack, unlink

**Output:** `KnowledgePack.source_ids` updated.

### Implementation
- `PATCH /packs/{id}` with updated `source_ids` list
- Read-only view on source side (source record does not store back-links directly)

---

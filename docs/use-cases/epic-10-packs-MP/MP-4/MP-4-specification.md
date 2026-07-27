# MP-4: Pack Editor

**Actor:** User
**Trigger:** Packs → [Pack] → Edit; or any composition entry point (clone, merge, slice)

**Purpose:** Free-form editing surface for pack contents. This is the **single surface** for all composition operations. The World Graph Explorer (Q-11) is embedded as an optional panel.

The editor works on a **local working copy** — source packs are never modified until the user explicitly saves.

**Composition entry points:**

| Intent | How to open |
|--------|-------------|
| Clone | Open single pack → save as new |
| Slice | Open single pack → delete unwanted items → save |
| Merge | Open 2+ packs → resolve duplicates → save |
| Split | Open single pack → save subset → repeat |
| Add to | Open target pack → pull items from source pack |

**Editing capabilities:**
- Add / remove / edit entities, axioms, lore facts
- Change entity type, edit name/description/tags
- Change relationships between entities (via World Graph panel)
- Reorder and reclassify items
- Filter and search within working copy

**Output:** Editor state; user saves via MP-5 or MP-6.

### Implementation
- Client-side working copy (React state / Zustand store)
- All edits are local until explicitly saved
- World Graph panel re-uses Q-11 component
- Supports loading multiple packs simultaneously as source layers

---

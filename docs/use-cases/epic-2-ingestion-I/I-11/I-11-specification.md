# I-11: Link Pack ↔ Game System

**Actor:** User
**Trigger:** Pack detail → Game System field

**Purpose:** Explicitly set or change the game system linked to a pack, overriding what ingestion extracted.

**Flow:**
1. Pack detail shows current game system chip (or "none detected")
2. User picks from registered systems dropdown, or creates new via RS-1
3. Save → updates `KnowledgePack.game_system_id`
4. System chip becomes a navigable link (see RS-6)

**Output:** Pack linked to chosen game system.

### Implementation
- `PATCH /packs/{id}` with `{game_system_id}`
- Depends on RS-6 for navigation chip

---

# RS-6: Navigate to System from Pack

**Actor:** User
**Trigger:** Pack detail, Ingest job result, or World Forge game system chip

**Purpose:** Any game system reference in the pack/forge flow renders as a clickable chip that deep-links to the system's full detail in `/systems`.

**Flow:**
1. Pack shows `game_system_name` as a styled chip
2. Click → navigate to `/systems?id={game_system_id}`
3. Systems page auto-selects and expands the matching system

**Output:** Seamless navigation from pack → system detail.

### Implementation
- UI only: add `href` / `onClick` to system chip in pack card and detail components
- Systems page: accept `?id=` query param and auto-select on mount

---

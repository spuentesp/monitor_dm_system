# RS-7: System Source Provenance

**Actor:** User
**Trigger:** Systems → [System] → Sources tab

**Purpose:** In the system detail view, show which source documents the system definition was extracted from, with links back to the source library (I-7).

**Flow:**
1. System detail page adds a "Sources" tab
2. Lists all source documents that reference this system (`game_system_id` match)
3. Each row: filename, upload date, scan type, status
4. Click → navigate to source in Source Library (I-7)

**Output:** Full traceability from system definition back to origin PDFs.

### Implementation
- Query sources by `game_system_id`: MongoDB + Neo4j source records
- Depends on I-7 for source library navigation

---

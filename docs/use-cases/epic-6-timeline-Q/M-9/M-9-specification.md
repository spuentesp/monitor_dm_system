# M-9: List Stories

**Actor:** User
**Trigger:** Manage → Stories

**Filters:** universe, status, type
**Output:** Table with title, universe, status, scenes, last played

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_stories(universe_id=None, status=None, story_type=None) -> list[StorySummary]
```

**Layer 3 (CLI):**
```bash
monitor manage story list
monitor manage story list --universe <UUID> --status active
```

---

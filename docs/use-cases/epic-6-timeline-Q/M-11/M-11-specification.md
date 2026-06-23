# M-11: Edit Story

**Actor:** User
**Trigger:** Story → Edit

**Editable:** title, theme, premise, status

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_story(story_id) -> Story
neo4j_update_story(story_id, params)
```

**Layer 3 (CLI):**
```bash
monitor manage story edit <UUID> --status completed
```

---

# M-10: View Story

**Actor:** User
**Trigger:** Select story from list

**Output:**
- Basic info (title, type, theme, premise)
- Scene list with summaries
- Participating characters
- Plot threads (open, resolved)
- Event timeline

**Actions:** Continue, Edit, Archive, Delete

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_story(story_id) -> Story
mongodb_get_scenes(story_id) -> list[SceneSummary]
neo4j_list_plot_threads(story_id) -> list[PlotThread]
neo4j_list_events(story_id, limit=10) -> list[Event]
```

**Layer 3 (CLI):**
```bash
monitor manage story view <UUID>
```

---

# M-28: List Scenes (in Story)

**Actor:** User
**Trigger:** Story → Scenes

**Output:** Table of scenes with title, status, turn count, summary

#### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_scenes(story_id) -> list[SceneSummary]
```

---

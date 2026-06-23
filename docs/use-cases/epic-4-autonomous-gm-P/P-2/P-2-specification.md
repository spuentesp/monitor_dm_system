# P-2: Start Scene

**Actor:** User / story-scene runtime
**Trigger:** New story started, or previous scene ended

**Flow:**
1. Prompt: Scene title (or auto-generate from context)
2. Prompt: Scene purpose (combat, exploration, social, rest, travel)
3. Select location (existing entity or create → M-14)
4. Confirm participating entities (PCs + relevant NPCs)
5. Create Scene document in MongoDB
6. Narrator generates opening description
7. Display scene opening
8. → P-3 (Turn loop)

**Output:** scene_id, scene opening narration

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_entity(location_id)             # Validate location
neo4j_list_entities(universe_id, type="character")  # Get available entities
mongodb_create_scene(params) -> scene_id  # Create scene document
mongodb_append_turn(scene_id, turn)       # Opening narration
qdrant_search(query, "scene_chunks")      # Get similar scenes for context
```

**Layer 2 (Agents / runtime):**
- The web session bootstrap or `StoryLoop` creates the scene record and hands control to `SceneLoop`
- `ContextAssembly.assemble(...)` gathers the starting scene context
- `Narrator.generate_scene_opening(...)` produces the opening text

**Layer 3 (CLI / UI):**
```bash
# Live today:
web Play surface automatically creates/binds the current scene

# Target CLI UX:
monitor play scene --story <UUID> --title "Tavern Encounter"
```

**Database Writes:**

| Database | Collection/Node | Data |
|----------|-----------------|------|
| MongoDB | `scenes` | `{id, story_id, title, purpose, status: "active", location_ref, participating_entities, turns: []}` |
| MongoDB | `scenes.turns` | Opening turn: `{speaker: "gm", text: "<opening>"}` |

**Sequence:**
```
session bootstrap / StoryLoop
    │
    ├─→ mongodb_create_scene(story_id, params)
    ├─→ ContextAssembly.assemble(...)
    │       ├─→ neo4j_get_entity(location)
    │       ├─→ neo4j_list_entities(participating)
    │       └─→ qdrant_search(similar scenes)
    ├─→ Narrator.generate_scene_opening(context)
    ├─→ mongodb_append_turn(opening)
    └─→ Display to user → P-3
```

---

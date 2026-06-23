# P-1: Start New Story

**Actor:** User
**Trigger:** Play → New Story
**Preconditions:** At least one multiverse/setting exists (or a knowledge pack can create one during flow)

**Flow:**
1. Select setting / multiverse (or create/apply from pack → M-2, I-*, MP-*)
2. Select universe within that multiverse:
   - existing narrative instance / timeline, or
   - create a new universe → M-4
3. Prompt: Story title
4. Prompt: Story type (campaign, arc, episode, one-shot)
5. Prompt: Theme (optional)
6. Prompt: Premise (optional)
7. Select/create participating PCs (→ M-13)
8. Create Story node in Neo4j
9. Create story_outline in MongoDB
10. → P-2 (Start first scene)

**Output:** story_id, ready for scene in the selected universe

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_universe(universe_id)           # Validate universe exists
neo4j_create_story(params) -> story_id    # Create Story node
mongodb_create_story_outline(params)      # Create outline document
```

**Layer 2 (Agents / runtime):**
- Web session bootstrap in `packages/ui/backend/src/monitor_ui/routers/chat.py` validates the selected context and creates the initial story/story-outline record
- `StoryLoop` owns the longer-running campaign lifecycle after bootstrap

**Layer 3 (CLI / UI):**
```bash
# Live today:
web Play surface → /api/chat

# Target CLI UX:
monitor play new --universe <UUID> --title "Story Title"
```

**Database Writes:**

| Database | Collection/Node | Data |
|----------|-----------------|------|
| Neo4j | `:Story` | `{id, universe_id, title, story_type, theme, premise, status: "active"}` |
| MongoDB | `story_outlines` | `{story_id, beats: [], pc_ids: [...]}` |

**Sequence:**
```
User → Web Play UI / future CLI
                │
                ├─→ session bootstrap validates universe
                ├─→ neo4j_create_story() → story_id
                ├─→ mongodb_create_story_outline()
                └─→ P-2 (Start Scene)
```

---

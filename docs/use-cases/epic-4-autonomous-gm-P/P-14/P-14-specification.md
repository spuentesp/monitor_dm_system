# P-14: Flashback Mode

**Actor:** User or Narrator (AI-triggered)
**Trigger:** User command `/flashback`, narrative prompt, or backstory exploration

**Purpose:** Play scenes from the past to establish character history, reveal information, or resolve mysteries.

**Flow:**

1. **Trigger Flashback:**
   - User requests: `/flashback "How did Gandalf first meet Bilbo?"`
   - Narrator suggests: "Do you want to play out this memory?"
   - System detects backstory hook

2. **Set Temporal Context:**
   - When: "50 years before the current story"
   - Where: Select or create location
   - Who: Select participating entities (may include younger versions)

3. **Enter Flashback Scene:**
   - Create scene with `temporal_mode: "flashback"`
   - Narrator sets the stage in past tense
   - Player actions are in past tense ("You approached the door")

4. **Play Flashback:**
   - Normal turn loop (P-3) with modified context
   - Proposals marked with `authority: "historical"`
   - Facts created are backdated to flashback time_ref

5. **Flashback Resolution:**
   - Scene ends naturally or via `/flashback end`
   - Narrator transitions back to present
   - Relevant information now available in character memories

6. **Canonization:**
   - Facts from flashback become canon with historical timestamps
   - Character memories updated with flashback content
   - NPCs met in flashback may appear in present

**Meta Commands:**

| Command | Description |
|---------|-------------|
| `/flashback "<prompt>"` | Initiate flashback |
| `/flashback end` | End flashback, return to present |
| `/flashback abort` | Cancel flashback without canonizing |
| `/when` | Check current temporal context |

### Implementation

**Layer 1 (Data Layer):**
```python
# Modified scene creation:
mongodb_create_scene(story_id, params, temporal_mode="flashback", time_ref=past_date)

# Flashback-specific queries:
neo4j_get_entity_at_time(entity_id, time_ref) -> Entity
neo4j_list_facts_at_time(universe_id, time_ref) -> list[Fact]

# Backdated fact creation:
neo4j_create_fact(params, time_ref=past_date, authority="historical")
```

**Layer 2 (Agents / runtime):**
- story/scene runtime enters and exits flashback mode for the selected `time_ref`
- `ContextAssembly.get_historical_context(universe_id, time_ref)` — World state at past time
- `Narrator.generate_flashback_opening(prompt, context)` — Set the past scene
- `Narrator.generate_flashback_transition(direction)` — "The memory fades..."
- Flashback outcomes can be persisted as memories through the existing MongoDB/Qdrant memory flow

**Layer 3 (CLI):**
```bash
# In REPL
> /flashback "The day I found the sword"
# System enters flashback mode with past-tense narration

> /flashback end
# Returns to present, canonizes flashback facts
```

**Flashback Schema:**
```python
@dataclass
class FlashbackContext:
    id: UUID
    story_id: UUID
    parent_scene_id: UUID  # Scene we return to after

    prompt: str
    time_ref: WorldDate
    time_description: str  # "15 years ago"

    location_id: UUID
    participating_entities: list[UUID]

    status: FlashbackStatus  # active, completed, aborted

    facts_established: list[UUID]
    memories_created: list[UUID]
```

**Database Writes:**

| Database | Collection/Node | Data |
|----------|-----------------|------|
| MongoDB | `scenes` | Scene with `temporal_mode: "flashback"`, `parent_scene_id` |
| Neo4j | `:Fact` | Facts with historical `time_ref` and `authority: "historical"` |
| MongoDB | `memories` | Memories created from flashback for participating characters |

---

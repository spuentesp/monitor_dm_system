# P-3: Turn Loop (Core Gameplay)

**Actor:** User
**Trigger:** Within active scene
**This is the heart of the game.**

```
LOOP:
  1. Display: location, present entities, recent context
  2. Prompt: await user input
  3. Parse input type:
     - Action → P-4
     - Dialogue → P-5
     - Question → P-6
     - Meta-command → P-7
  4. Process through appropriate handler
  5. Narrator generates response
  6. Append turns to MongoDB
  7. Check: should scene end?
  8. IF end → P-8
  9. ELSE → continue loop
```

### Implementation

**Layer 1 (Data Layer):**
```python
# Each turn iteration:
mongodb_get_scene(scene_id)               # Get current scene state
mongodb_get_turns(scene_id, limit=10)     # Recent context
mongodb_append_turn(scene_id, user_turn)  # User input
mongodb_append_turn(scene_id, gm_turn)    # GM response
mongodb_create_proposal(scene_id, ...)    # If canonical changes proposed
```

**Layer 2 (Agents / runtime):**
- `SceneLoop.run(...)` is the main scene-level controller for live play
- `ContextAssembly.assemble(...)` builds turn context
- `Narrator.generate(...)` responds in fiction
- `Resolver.resolve(...)` handles checks, rolls, and consequence scaffolding

**Layer 3 (CLI / UI):**
- Live today: web chat composer and WebSocket updates in the Play UI
- Target CLI UX: interactive REPL mode within `monitor play`

**State Machine:**
```python
class TurnState(Enum):
    AWAITING_INPUT = "awaiting_input"
    PROCESSING = "processing"
    RESOLVING = "resolving"
    RESPONDING = "responding"
    CHECKING_END = "checking_end"
```

**Database Writes Per Turn:**

| Database | Operation | Data |
|----------|-----------|------|
| MongoDB | `scenes.turns.append` | `{turn_id, speaker: "user", text: "...", timestamp}` |
| MongoDB | `scenes.turns.append` | `{turn_id, speaker: "gm", text: "...", resolution_ref?}` |
| MongoDB | `proposed_changes.insert` | If action implies state change |

**Turn Parsing Logic:**
```python
def parse_input(text: str) -> InputType:
    if text.startswith("/"):
        return InputType.META_COMMAND
    if text.startswith('"') or "say" in text.lower():
        return InputType.DIALOGUE
    if "?" in text or text.lower().startswith(("what", "who", "where", "how")):
        return InputType.QUESTION
    return InputType.ACTION
```

---

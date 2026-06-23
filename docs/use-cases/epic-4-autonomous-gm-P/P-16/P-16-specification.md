# P-16: Select Controlled Characters and Active Speaker

**Actor:** User
**Trigger:** During session setup (P-15), party setup (P-13), or mid-scene via `/switch`

**Purpose:** Let one user control multiple PCs while making it explicit which character is currently speaking or acting for dialogue and checks.

**Flow:**
1. Select one or more player-controlled characters
2. For each missing character, offer:
   - create new character
   - import existing sheet
   - clone/adapt from another system
3. Designate the current **speaker PC**
4. During play, allow switching the active speaker from the party rail or with `/switch <name>`
5. Use the active speaker's sheet and working state for dialogue tags, action resolution, and roll modifiers
6. Preserve the controlled roster and speaker choice in the session record

**Output:** the session knows who the user controls and which character currently "speaks" into the scene

### Implementation

**Layer 1 (Data Layer):**
```python
# Existing schemas cover most of this; CRUD/session tools should expose it:
neo4j_get_entity(entity_id) -> EntityInstance
mongodb_list_character_sheets(entity_id=...) -> list[CharacterSheet]
# add/update session binding for controlled characters and current speaker:
mongodb_update_play_session(session_id, {
    "controlled_character_ids": [...],
    "speaker_character_id": ...,
})
# if multiple sheets exist, select the active one for the current system/story
set_active_sheet(entity_id, sheet_id)
```

**Layer 2 (Agents / runtime):**
- session bootstrap helpers persist `controlled_character_ids` and `speaker_character_id`
- `Resolver.resolve_turn(...)` reads the active speaker's stats when the user acts
- `SceneLoop` consumes the selected speaker and controlled roster during play

**UI / REPL controls:**

| Control | Description |
|---------|-------------|
| Character cards | Add/remove controlled PCs |
| `Speaker` toggle | Mark the current speaking/acting PC |
| `/switch <name>` | Change speaker mid-scene |
| Party rail | Show all controlled and supporting characters |

---

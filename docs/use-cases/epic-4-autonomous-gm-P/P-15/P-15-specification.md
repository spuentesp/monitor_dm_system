# P-15: Start Play Session

**Actor:** User
**Trigger:** Open Play mode (`monitor play` or the web Play surface)

**Purpose:** Provide a single entry flow for solo play that lets the user start or resume a session without manually hopping between world, character, and chat screens.

**Flow:**
1. Show **Play Home** with: `New Session`, `Continue Story`, `Quick Start`, `Recent Recaps`
2. If `New Session`:
   - select setting / multiverse
   - select or create universe
   - choose rules system and tone
   - select/create one or more controlled PCs
   - choose the active speaker PC
   - choose `New Story` or `Quick Scene`
3. If `Continue Story`:
   - filter by multiverse / universe
   - list active stories and last active scene
   - show recap and resume point
4. Create or update the session bootstrap record with the current play context
5. Enter P-1 (new story) or P-12 (continue story)

**Output:** a ready-to-play session bound to one multiverse, one universe, one active story/scene, and one or more controlled PCs

### Implementation

**Layer 1 (Data Layer):**
```python
# New or extended session tools:
mongodb_create_play_session(params) -> session_id
mongodb_get_play_session(session_id) -> PlaySession
mongodb_update_play_session(session_id, params)
neo4j_list_multiverses() -> list[Multiverse]
neo4j_list_universes(multiverse_id=...) -> list[Universe]
```

**Layer 2 (Agents / runtime):**
- `packages/ui/backend/src/monitor_ui/routers/chat.py` owns the current bootstrap/resume flow and phase transitions
- `ContextAssembly.get_session_recap(session_id)` — Build the resume summary
- `SceneLoop` / `StoryLoop` resume once `story_id` and `scene_id` are bound

**Layer 3 (CLI / UI):**
```bash
# Live today:
web Play surface + `/api/chat` REST/WebSocket
monitor playtest live|compare

# Target CLI UX:
monitor play
monitor play new
monitor play continue
```

**Session Bootstrap Shape:**
```python
@dataclass
class PlaySession:
    id: UUID
    multiverse_id: UUID
    universe_id: UUID
    story_id: UUID | None
    scene_id: UUID | None
    controlled_character_ids: list[UUID]
    speaker_character_id: UUID | None
    mode: str                     # autonomous_gm, gm_assistant
    tone: str                     # dramatic, gritty, etc.
    created_at: datetime
    updated_at: datetime
```

---

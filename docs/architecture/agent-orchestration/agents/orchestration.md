## Agent Specifications

### Loop Orchestration (LangGraph State Machines)

> **Implementation:** `packages/agents/src/monitor_agents/loops/`

Instead of a monolithic Orchestrator agent, MONITOR uses **LangGraph `StateGraph`** state machines. Each loop is a compiled graph whose nodes call the appropriate agents.

**SceneLoop** (core play loop):

```mermaid
stateDiagram-v2
    [*] --> load_context
    load_context --> resolve: S1→S3
    resolve --> narrate: S3→S4/S5
    narrate --> canonize: scene_complete or max_turns
    narrate --> [*]: continue (await next run)
    canonize --> [*]: scene finalized
```

- **Checkpointed:** Yes (`MongoDBSaver` — survives process restarts)
- **Nodes:** `load_context` (ContextAssembly) → `resolve` (Resolver) → `narrate` (Narrator) → `canonize` (CanonKeeper)

**StoryLoop** (campaign lifecycle):
```mermaid
stateDiagram-v2
    [*] --> init_story
    init_story --> [*]
    note right of init_story
      UI/CLI drives interactive SceneLoop turns.
      complete_current_scene() handles world advance and transition.
    end note
    finalize --> [*]
```

- **Checkpointed:** Yes (`MongoDBSaver`)
- **Nodes:** `init_story`; scene completion calls `simulate_world_advance` + `transition_scene` from `complete_current_scene()`.

**TurnLoop removed:** single-turn play is handled directly by `SceneLoop` (`ContextAssembly` → `Resolver` → `Narrator` → persistence). Scene remains the durability boundary.

**ConversationLoop** (NPC dialogue — DIRECT or ACTOR mode):
```mermaid
stateDiagram-v2
    [*] --> open_session
    open_session --> load_npc_context
    load_npc_context --> player_turn
    player_turn --> npc_responses
    npc_responses --> player_turn: not complete
    npc_responses --> close_session: is_complete or max_turns
    close_session --> [*]
```

- **No Resolver** (no dice rolls), **no CanonKeeper mid-loop** (proposals staged at session end)
- Uses **NPCVoice** agent with `ModelRole.LIGHT` for responsive dialogue

**WorldBuildingLoop** (collaborative setting creation):
```mermaid
stateDiagram-v2
    [*] --> load_world_context
    load_world_context --> process_user_input
    process_user_input --> format_response
    format_response --> [*]
```

- Uses **WorldArchitect** agent; auto-commits proposals via CanonKeeper
- No dice, no scenes — pure conversational world definition

---


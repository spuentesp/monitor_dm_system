# P-7: Meta Commands

**Actor:** User
**Trigger:** Input starts with `/`

| Command | Description | Flow |
|---------|-------------|------|
| `/roll [dice]` | Roll dice manually | → P-9 |
| `/status` | Show scene status, participants, proposals | Display context |
| `/recap` | Summarize recent turns | Generate summary |
| `/end` | End current scene | → P-8 |
| `/pause` | Save and exit to menu | Save state, exit |
| `/undo` | Undo last turn (if not canonized) | Remove turn |
| `/entities` | List entities in scene | Display list |
| `/facts [entity]` | Show facts about entity | → Q-4 |
| `/help` | Show commands | Display help |
| `/character [name]` | View character sheet | → M-16 |

### Implementation

**Layer 1 (Data Layer):**
```python
# Command-specific tools:

# /status
mongodb_get_scene(scene_id)
mongodb_list_pending_proposals(scene_id)

# /recap
mongodb_get_turns(scene_id, limit=20)

# /undo
mongodb_undo_turn(scene_id)

# /entities
neo4j_list_entities(universe_id, filters)

# /facts
neo4j_list_facts(entity_id)

# /character
mongodb_get_character_sheet(entity_id)
neo4j_get_entity(entity_id)
```

**Layer 2 (Agents / runtime):**
- `scene_runtime.handle_meta_command(command, args, context)` - Router
- Individual handlers per command type

**Command Router:**
```python
META_COMMANDS = {
    "/roll": handle_roll,
    "/status": handle_status,
    "/recap": handle_recap,
    "/end": handle_end,
    "/pause": handle_pause,
    "/undo": handle_undo,
    "/entities": handle_entities,
    "/facts": handle_facts,
    "/help": handle_help,
    "/character": handle_character,
}

async def handle_meta_command(input_text: str, context: Context) -> MetaResult:
    parts = input_text.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = META_COMMANDS.get(command)
    if not handler:
        return MetaResult(error=f"Unknown command: {command}")

    return await handler(args, context)
```

**Command Handlers:**
```python
async def handle_status(args: str, context: Context) -> MetaResult:
    scene = await mongodb_get_scene(context.scene_id)
    proposals = await mongodb_list_pending_proposals(context.scene_id)

    return MetaResult(
        display=format_status(scene, proposals),
        continue_loop=True
    )

async def handle_recap(args: str, context: Context) -> MetaResult:
    turns = await mongodb_get_turns(context.scene_id, limit=20)
    summary = await llm_summarize(turns)

    return MetaResult(
        display=summary,
        continue_loop=True
    )

async def handle_undo(args: str, context: Context) -> MetaResult:
    # Check if scene is not yet canonized
    scene = await mongodb_get_scene(context.scene_id)
    if scene.status != "active":
        return MetaResult(error="Cannot undo after canonization")

    await mongodb_undo_turn(context.scene_id)
    return MetaResult(
        display="Last turn undone.",
        continue_loop=True
    )

async def handle_end(args: str, context: Context) -> MetaResult:
    # Trigger scene end flow
    return MetaResult(
        trigger_scene_end=True,
        continue_loop=False
    )

async def handle_pause(args: str, context: Context) -> MetaResult:
    # Save state and exit
    await mongodb_update_scene(context.scene_id, {"paused": True})
    return MetaResult(
        display="Game paused. Your progress is saved.",
        exit_to_menu=True
    )
```

**Layer 3 (CLI):**
```python
# Commands are handled in the REPL loop
class REPLSession:
    async def process_input(self, text: str):
        if text.startswith("/"):
            result = await self.runtime.handle_meta_command(text, self.context)
            self.display(result)
            if result.exit_to_menu:
                return False  # Exit REPL
            if result.trigger_scene_end:
                await self.end_scene()
        else:
            # Normal turn processing
            await self.process_turn(text)
        return True
```

---

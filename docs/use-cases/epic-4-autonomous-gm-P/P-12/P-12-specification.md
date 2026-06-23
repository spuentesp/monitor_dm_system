# P-12: Continue Story

**Actor:** User
**Trigger:** Play → Continue

**Flow:**
1. List active stories (status = "active")
2. User selects story
3. Load story state:
   - Last scene (or scene list if between scenes)
   - Recent events summary
4. Display recap
5. Resume: P-3 (mid-scene) or P-2 (new scene)

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_list_stories(universe_id, status="active")   # Get active stories
neo4j_get_story(story_id)                          # Story details
mongodb_get_scenes(story_id, status="active")      # Active scenes
mongodb_get_scene(scene_id)                        # Scene details
mongodb_get_turns(scene_id, limit=10)              # Recent turns
qdrant_search(story_id, "scene_chunks")            # Story context
```

**Layer 2 (Agents):**
- `Orchestrator.list_continuable_stories(universe_id)` - Fetch active stories
- `Orchestrator.continue_story(story_id)` - Resume story
- `ContextAssembly.get_story_recap(story_id)` - Generate recap
- `Narrator.generate_continuation_prompt(context)` - Transition text

**Story State Resolution:**
```python
@dataclass
class StoryState:
    story_id: UUID
    title: str
    last_played: datetime
    active_scene: Scene | None
    scene_count: int
    resume_point: ResumePoint

class ResumePoint(Enum):
    MID_SCENE = "mid_scene"      # Active scene exists, continue turns
    BETWEEN_SCENES = "between"    # No active scene, start new scene
    PAUSED = "paused"            # Explicitly paused, show options

async def get_story_state(story_id: UUID) -> StoryState:
    """Determine where to resume a story."""
    story = await neo4j_get_story(story_id)
    scenes = await mongodb_get_scenes(story_id)

    active_scenes = [s for s in scenes if s.status == "active"]

    if active_scenes:
        return StoryState(
            story_id=story_id,
            title=story.title,
            last_played=story.updated_at,
            active_scene=active_scenes[0],
            scene_count=len(scenes),
            resume_point=ResumePoint.MID_SCENE
        )
    elif scenes and scenes[-1].status == "completed":
        return StoryState(
            story_id=story_id,
            title=story.title,
            last_played=story.updated_at,
            active_scene=None,
            scene_count=len(scenes),
            resume_point=ResumePoint.BETWEEN_SCENES
        )
    else:
        return StoryState(
            story_id=story_id,
            title=story.title,
            last_played=story.updated_at,
            active_scene=None,
            scene_count=len(scenes),
            resume_point=ResumePoint.PAUSED
        )
```

**Story Listing:**
```python
async def list_continuable_stories(universe_id: UUID | None = None) -> list[StorySummary]:
    """List all stories that can be continued."""
    filters = {"status": "active"}
    if universe_id:
        filters["universe_id"] = universe_id

    stories = await neo4j_list_stories(**filters)

    summaries = []
    for story in stories:
        state = await get_story_state(story.id)
        summaries.append(StorySummary(
            story_id=story.id,
            title=story.title,
            universe_name=story.universe.name,
            last_played=state.last_played,
            scene_count=state.scene_count,
            resume_point=state.resume_point
        ))

    # Sort by last played (most recent first)
    return sorted(summaries, key=lambda s: s.last_played, reverse=True)
```

**Recap Generation:**
```python
async def get_story_recap(story_id: UUID) -> str:
    """Generate a recap of recent story events."""
    # Get completed scenes (last 3)
    scenes = await mongodb_get_scenes(story_id, status="completed", limit=3)

    # Get recent events from Neo4j
    events = await neo4j_list_events(story_id, limit=10)

    # Get semantic context
    context_chunks = await qdrant_search(
        query=f"story:{story_id} recent events",
        collection="scene_chunks",
        limit=5
    )

    # Build recap with LLM
    recap = await llm_generate_recap(
        scenes=scenes,
        events=events,
        context=context_chunks
    )

    return recap
```

**Continue Flow:**
```python
async def continue_story(story_id: UUID) -> ContinueResult:
    """Resume a story from where it left off."""
    state = await get_story_state(story_id)

    # Generate recap
    recap = await get_story_recap(story_id)

    # Display recap
    display_recap(state.title, recap)

    match state.resume_point:
        case ResumePoint.MID_SCENE:
            # Resume existing scene
            scene = state.active_scene
            context = await build_scene_context(scene.scene_id)

            # Show recent turns
            recent_turns = await mongodb_get_turns(scene.scene_id, limit=5)
            display_recent_turns(recent_turns)

            # Enter turn loop
            return ContinueResult(
                action="enter_turn_loop",
                scene_id=scene.scene_id,
                context=context
            )

        case ResumePoint.BETWEEN_SCENES:
            # Prompt for new scene
            narrator_prompt = await narrator.generate_continuation_prompt(story_id)
            display(narrator_prompt)

            return ContinueResult(
                action="prompt_new_scene",
                story_id=story_id
            )

        case ResumePoint.PAUSED:
            # Show options
            return ContinueResult(
                action="show_resume_options",
                story_id=story_id,
                options=["Start new scene", "View story details", "End story"]
            )
```

**Layer 3 (CLI):**
```bash
# List continuable stories
monitor play continue

# Direct continue with story ID
monitor play continue --story <UUID>
```

**CLI Display:**
```python
def display_story_list(stories: list[StorySummary]):
    """Display list of continuable stories."""
    print("═══════════════════════════════════════════")
    print("  Continue Story")
    print("═══════════════════════════════════════════")
    print()

    for i, story in enumerate(stories, 1):
        status_icon = {
            ResumePoint.MID_SCENE: "▶",
            ResumePoint.BETWEEN_SCENES: "◯",
            ResumePoint.PAUSED: "⏸"
        }[story.resume_point]

        print(f"  [{i}] {status_icon} {story.title}")
        print(f"      Universe: {story.universe_name}")
        print(f"      Last played: {format_relative_time(story.last_played)}")
        print(f"      Scenes: {story.scene_count}")
        print()

def display_recap(title: str, recap: str):
    """Display story recap before resuming."""
    print()
    print(f"═══ {title} ═══")
    print()
    print("📜 Previously...")
    print()
    print(recap)
    print()
    print("─" * 40)
```

**Database Reads:**

| Database | Collection/Node | Query |
|----------|-----------------|-------|
| Neo4j | `:Story` | `WHERE status = "active"` |
| MongoDB | `scenes` | `WHERE story_id = ? ORDER BY created_at DESC` |
| MongoDB | `scenes.turns` | `WHERE scene_id = ? ORDER BY timestamp DESC LIMIT 10` |
| Qdrant | `scene_chunks` | Semantic search for story context |

---

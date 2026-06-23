# Stabilization & Target Roleplays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final gap between the passing tests and the realized product vision (Lorebook injection, Narrative Transitions via Story Arc pacing, and UI Story Arc rendering) to support the target roleplay examples.

**Architecture:** 
- `ContextAssembly` will scan player input against the Lorebook DB to inject matching character memories.
- `Narrator` will accept `story_state` to guide the DSPy LLM pacing with macro arc transitions.
- The `PlayConsole` React component will be updated to display the `StoryPanel` when a story is active.

**Tech Stack:** Python (FastAPI, DSPy), React (Next.js), MongoDB.

---

### Task 1: Activate Lorebook Injection in ContextAssembly

**Files:**
- Modify: `packages/agents/src/monitor_agents/context_assembly.py`
- Test: `packages/agents/tests/test_context_assembly.py`

- [ ] **Step 1: Write the failing test**

```python
# In packages/agents/tests/test_context_assembly.py
from unittest.mock import patch
import pytest
from uuid import uuid4

@pytest.mark.asyncio
@patch("monitor_data.tools.mongodb_tools.lorebook_tools.inject_lorebook_entries")
async def test_context_assembly_injects_lorebook(mock_inject):
    """Context assembly should invoke lorebook injection if an actor exists."""
    from monitor_agents.context_assembly import ContextAssembly
    mock_inject.return_value = ["The dragon of the north is ancient."]
    
    agent = ContextAssembly()
    context = await agent.assemble(
        scene_id=uuid4(),
        story_id=uuid4(),
        player_action="I look for the dragon",
        actor_context={"id": str(uuid4()), "name": "Brave Sir Robin", "role": "pc"}
    )
    
    # Assert lorebook was queried
    mock_inject.assert_called_once()
    
    # Assert lorebook was added to the profile context
    assert "The dragon of the north is ancient" in context.get("profile", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u MONGODB_URI pytest packages/agents/tests/test_context_assembly.py::test_context_assembly_injects_lorebook -v`
Expected: FAIL due to missing mock call or missing lorebook text.

- [ ] **Step 3: Write minimal implementation**

```python
# In packages/agents/src/monitor_agents/context_assembly.py
# Around line 258, inside the `assemble` method, after profile_context is built:
        
        # Gap 1: Inject actor personality, role, and tags into profile_context
        actor = actor_context
        if actor:
            actor_name = actor.get("name", "the character")
            role = actor.get("role", "pc")
            personality = actor.get("personality", "")
            tags = ", ".join(actor.get("state_tags", []))
            actor_block = f"\\n\\nACTOR PROFILE ({actor_name}):\\n- Role: {role}\\n"
            if personality:
                actor_block += f"- Personality: {personality}\\n"
            if tags:
                actor_block += f"- State: {tags}\\n"
            profile_context += actor_block
            
            # Lorebook Injection
            if player_action:
                try:
                    from monitor_data.tools.mongodb_tools.lorebook_tools import inject_lorebook_entries
                    actor_id = str(actor.get("id", ""))
                    if actor_id:
                        matched_lore = inject_lorebook_entries(
                            character_id=actor_id,
                            text=player_action,
                            increment_triggers=True,
                        )
                        if matched_lore:
                            profile_context += "\\n\\nRELEVANT LOREBOOK ENTRIES:\\n" + "\\n".join(matched_lore)
                except Exception as e:
                    logger.warning(f"Failed to inject lorebook entries: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `env -u MONGODB_URI pytest packages/agents/tests/test_context_assembly.py::test_context_assembly_injects_lorebook -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/context_assembly.py packages/agents/tests/test_context_assembly.py
git commit -m "feat(agents): activate lorebook injection in context assembly"
```

### Task 2: Pass Story State to Narrator

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/scene_loop.py`
- Modify: `packages/agents/src/monitor_agents/narrator.py`
- Test: `packages/agents/tests/test_scene_loop.py`

- [ ] **Step 1: Write the failing test**

```python
# In packages/agents/tests/test_narrator.py
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_narrator_uses_story_state():
    """Narrator should append story state to the profile_context if provided."""
    from monitor_agents.narrator import Narrator
    
    narrator = Narrator()
    narrator._narrator_module = MagicMock(return_value="Narrative output")
    narrator._persist_turn = AsyncMock(return_value="turn-123")
    
    story_state = {
        "arc_label": "Climax",
        "tension_score": 0.9,
        "active_threads": ["The dark ritual"]
    }
    
    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="I attack!",
        resolution=None,
        context={"entities": [], "memories": [], "turns": []},
        story_state=story_state
    )
    
    assert result["narrative_text"] == "Narrative output"
    
    # Verify the story_state was passed into the module via profile_context or game_system_context
    _, kwargs = narrator._narrator_module.call_args
    assert "Climax" in kwargs.get("profile_context", "") or "Climax" in kwargs.get("scene_context", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u MONGODB_URI pytest packages/agents/tests/test_narrator.py::test_narrator_uses_story_state -v`
Expected: FAIL because `narrate_turn` doesn't accept `story_state`.

- [ ] **Step 3: Write minimal implementation**

```python
# In packages/agents/src/monitor_agents/loops/scene_loop.py
# In `narrate` function:
    result = await narrator.narrate_turn(
        scene_id=state.scene_id,
        user_input=state.user_input,
        resolution=state.resolution,
        context={
            "entities": state.entity_context,
            "memories": state.memory_context,
            "turns": state.previous_turns,
            "source_profile": state.source_profile,
            "actor": state.actor_context,  # ensure actor_context is passed
        },
        game_context=state.game_context,
        session_tone=state.session_tone,
        gm_profile=state.gm_profile,
        story_state=getattr(state, "story_state", None), # Pass story state if it exists
    )

# In packages/agents/src/monitor_agents/narrator.py
# Add `story_state` parameter to narrate_turn
    async def narrate_turn(
        self,
        scene_id: UUID,
        user_input: Optional[str],
        resolution: Optional[Dict[str, Any]],
        context: Dict[str, Any],
        game_context: Optional[Dict[str, Any]] = None,
        session_tone: str = "dramatic",
        gm_profile: Optional[Dict[str, Any]] = None,
        story_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

# Update the call to _generate_narrative_and_proposals
        narrative_text, raw_proposals, minutes_elapsed = await self._generate_narrative_and_proposals(
            user_input=user_input,
            resolution=resolution,
            context=context,
            game_context=game_context,
            session_tone=session_tone,
            gm_profile=gm_profile,
            story_state=story_state,
        )

# Add `story_state` parameter to _generate_narrative_and_proposals
    async def _generate_narrative_and_proposals(
        self,
        *,
        user_input: Optional[str],
        resolution: Optional[Dict[str, Any]],
        context: Dict[str, Any],
        game_context: Optional[Dict[str, Any]] = None,
        session_tone: str = "dramatic",
        gm_profile: Optional[Dict[str, Any]] = None,
        story_state: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, List[Dict[str, Any]], int]:

# Inside _generate_narrative_and_proposals, inject story_state into profile_context
        if story_state:
            arc = story_state.get("arc_label", "Unknown")
            tension = story_state.get("tension_score", 0.5)
            threads = ", ".join(story_state.get("active_threads", []))
            story_block = f"\\n\\nSTORY ARC CONTEXT:\\n- Phase: {arc}\\n- Tension: {tension}/1.0\\n"
            if threads:
                story_block += f"- Active Threads: {threads}\\n"
            profile_context += story_block
```

- [ ] **Step 4: Run test to verify it passes**

Run: `env -u MONGODB_URI pytest packages/agents/tests/test_narrator.py::test_narrator_uses_story_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/scene_loop.py packages/agents/src/monitor_agents/narrator.py packages/agents/tests/test_narrator.py
git commit -m "feat(agents): pass story arc state into narrative context"
```

### Task 3: Integrate StoryPanel into PlayConsole

**Files:**
- Modify: `packages/ui/frontend/src/components/play/PlayConsole.tsx`

- [ ] **Step 1: Write the failing test**
(Skipping automated test for UI layout; manual visual verification via types)

- [ ] **Step 2: Write minimal implementation**

```tsx
// In packages/ui/frontend/src/components/play/PlayConsole.tsx

// 1. Add StoryPanel to imports
import { StoryPanel } from "./StoryPanel";

// 2. Around line 1300, locate the right-sidebar configuration.
// Look for `<CharacterPanel characterId={session.character_id} />`
// Replace it with:
          {session?.character_id && (
            <div className="flex-1 min-h-0">
              <CharacterPanel characterId={session.character_id} />
            </div>
          )}
          
          {session?.story_id && (
            <div className="h-1/3 min-h-[250px] border-t border-white/5">
              <StoryPanel storyId={session.story_id} />
            </div>
          )}
```

- [ ] **Step 3: Run test to verify it passes**

Run: `npm --prefix packages/ui/frontend run type-check`
Expected: PASS (No TypeScript errors).

- [ ] **Step 4: Commit**

```bash
git add packages/ui/frontend/src/components/play/PlayConsole.tsx
git commit -m "feat(ui): integrate story panel into play console sidebar"
```

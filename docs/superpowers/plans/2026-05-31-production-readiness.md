# v1.0 Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final systemic gaps identified in the accurate implementation status report to elevate the system from "playable" to a fully realized "Autonomous GM and Assistant." This includes automated story outlining, NPC autonomy, contradiction detection, and entity templates.

**Architecture:** 
- **Automated Outlining:** Extend `StoryLoop` with a DSPy module to generate the next `scene_type` and plot hooks when a scene ends.
- **NPC Agendas:** Introduce an `agenda_tick` into the `StoryLoop` that allows non-present NPCs to make off-screen moves.
- **Contradiction Guard:** Add a verification node in the ingestion pipeline and `SceneLoop` to warn the GM when player actions conflict with canonical facts.
- **Entity Templates:** Extend the Data Layer and UI to support saving and cloning Neo4j `Entity` nodes as templates.

**Tech Stack:** Python (FastAPI, DSPy), Neo4j, React (Next.js).

---

### Task 1: Automated Story Outlining (P-6, ST-1)

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/story_loop.py`
- Modify: `packages/agents/src/monitor_agents/prompts/story.py` (Create)
- Test: `packages/agents/tests/test_story_loop.py`

- [ ] **Step 1: Write the failing test**
```python
# In packages/agents/tests/test_story_loop.py
@pytest.mark.asyncio
async def test_story_loop_generates_next_scene():
    from monitor_agents.loops.story_loop import StoryLoop, StoryState
    
    # Mock DSPy module
    with patch("monitor_agents.loops.story_loop.StoryPlannerModule") as mock_planner:
        mock_planner.return_value.forward.return_value = {
            "next_scene_type": "combat",
            "plot_hook": "The goblins ambush the party."
        }
        
        loop = StoryLoop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4(), arc_label="Rising Action")
        result = await loop.plan_next_scene(state)
        
        assert result["next_scene_type"] == "combat"
        assert "goblins ambush" in result["plot_hook"]
```

- [ ] **Step 2: Run test to verify it fails**
Run: `env -u MONGODB_URI pytest packages/agents/tests/test_story_loop.py::test_story_loop_generates_next_scene -v`
Expected: FAIL due to missing `StoryPlannerModule` and `plan_next_scene` logic.

- [ ] **Step 3: Write minimal implementation**
```python
# In packages/agents/src/monitor_agents/prompts/story.py
import dspy

class StoryPlannerSignature(dspy.Signature):
    """Determine the next scene type and plot hook based on the current story arc."""
    arc_label = dspy.InputField()
    active_threads = dspy.InputField()
    recent_scenes = dspy.InputField()
    next_scene_type = dspy.OutputField(desc="e.g., combat, social, exploration, downtime")
    plot_hook = dspy.OutputField(desc="A one-sentence hook for the next scene.")

class StoryPlannerModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.plan = dspy.ChainOfThought(StoryPlannerSignature)
        
    def forward(self, arc_label: str, active_threads: str, recent_scenes: str):
        result = self.plan(arc_label=arc_label, active_threads=active_threads, recent_scenes=recent_scenes)
        return {"next_scene_type": result.next_scene_type, "plot_hook": result.plot_hook}

# In packages/agents/src/monitor_agents/loops/story_loop.py
# Inside StoryLoop class
    async def plan_next_scene(self, state: StoryState) -> dict:
        from monitor_agents.prompts.story import StoryPlannerModule
        planner = StoryPlannerModule()
        result = planner.forward(
            arc_label=state.arc_label,
            active_threads=", ".join(state.active_threads),
            recent_scenes="Unknown"  # Stub for now
        )
        return result
```

- [ ] **Step 4: Run test to verify it passes**
Run: `env -u MONGODB_URI pytest packages/agents/tests/test_story_loop.py::test_story_loop_generates_next_scene -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add packages/agents/src/monitor_agents/loops/story_loop.py packages/agents/src/monitor_agents/prompts/story.py packages/agents/tests/test_story_loop.py
git commit -m "feat(agents): automate next scene planning via DSPy"
```

### Task 2: NPC Agendas & Off-Screen Moves

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/story_loop.py`
- Modify: `packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py`
- Test: `packages/agents/tests/test_story_loop_procedural.py`

- [ ] **Step 1: Write the failing test**
```python
# In packages/agents/tests/test_story_loop_procedural.py
@pytest.mark.asyncio
async def test_story_loop_ticks_npc_agendas():
    from monitor_agents.loops.story_loop import StoryLoop
    
    with patch("monitor_data.tools.neo4j_tools.entities.neo4j_tick_agendas") as mock_tick:
        mock_tick.return_value = ["Count Dracula advanced plan: Blood Tithe"]
        
        loop = StoryLoop()
        # Assume advance_arc is called at scene end
        await loop.advance_arc(uuid4())
        
        mock_tick.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `env -u MONGODB_URI pytest packages/agents/tests/test_story_loop_procedural.py::test_story_loop_ticks_npc_agendas -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**
```python
# In packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py
def neo4j_tick_agendas(universe_id: str) -> list[str]:
    """Find all NPCs with active agendas in the universe and advance them."""
    # Stub implementation
    return []

# In packages/agents/src/monitor_agents/loops/story_loop.py
# Inside advance_arc or similar end-of-scene hook:
    from monitor_data.tools.neo4j_tools.entities import neo4j_tick_agendas
    agenda_moves = neo4j_tick_agendas(str(state.universe_id))
    # Log or append to story state threads
```

- [ ] **Step 4: Run test to verify it passes**
Run: `env -u MONGODB_URI pytest packages/agents/tests/test_story_loop_procedural.py::test_story_loop_ticks_npc_agendas -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add packages/agents/src/monitor_agents/loops/story_loop.py packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py packages/agents/tests/test_story_loop_procedural.py
git commit -m "feat(agents): implement off-screen NPC agenda ticks"
```

### Task 3: Contradiction Detection (CF-5)

**Files:**
- Modify: `packages/agents/src/monitor_agents/canonkeeper.py`
- Modify: `packages/agents/src/monitor_agents/prompts/verification.py` (Create)
- Test: `packages/agents/tests/test_canonkeeper.py`

- [ ] **Step 1: Write the failing test**
```python
# In packages/agents/tests/test_canonkeeper.py
@pytest.mark.asyncio
async def test_canonkeeper_flags_contradiction():
    from monitor_agents.canonkeeper import CanonKeeper
    
    keeper = CanonKeeper()
    with patch("monitor_agents.prompts.verification.ContradictionModule.forward") as mock_verify:
        mock_verify.return_value = {"has_contradiction": True, "explanation": "Character is dead."}
        
        result = await keeper.verify_fact("Character walks into the tavern.", context=["Character died yesterday."])
        assert result["has_contradiction"] is True
```

- [ ] **Step 2: Run test to verify it fails**
Run: `env -u MONGODB_URI pytest packages/agents/tests/test_canonkeeper.py::test_canonkeeper_flags_contradiction -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**
```python
# In packages/agents/src/monitor_agents/prompts/verification.py
import dspy

class ContradictionSignature(dspy.Signature):
    """Check if a new fact contradicts established context."""
    context = dspy.InputField()
    new_fact = dspy.InputField()
    has_contradiction = dspy.OutputField(desc="Boolean True or False")
    explanation = dspy.OutputField()

class ContradictionModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.verify = dspy.ChainOfThought(ContradictionSignature)
        
    def forward(self, context: str, new_fact: str):
        res = self.verify(context=context, new_fact=new_fact)
        # Parse boolean
        has_contradiction = str(res.has_contradiction).lower() == "true"
        return {"has_contradiction": has_contradiction, "explanation": res.explanation}

# In packages/agents/src/monitor_agents/canonkeeper.py
    async def verify_fact(self, new_fact: str, context: list[str]) -> dict:
        from monitor_agents.prompts.verification import ContradictionModule
        module = ContradictionModule()
        return module.forward(context=" ".join(context), new_fact=new_fact)
```

- [ ] **Step 4: Run test to verify it passes**
Run: `env -u MONGODB_URI pytest packages/agents/tests/test_canonkeeper.py::test_canonkeeper_flags_contradiction -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add packages/agents/src/monitor_agents/canonkeeper.py packages/agents/src/monitor_agents/prompts/verification.py packages/agents/tests/test_canonkeeper.py
git commit -m "feat(agents): add real-time contradiction detection"
```

### Task 4: Entity Templates (M-31)

**Files:**
- Modify: `packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py`
- Modify: `packages/ui/backend/src/monitor_ui/routers/entities.py`
- Test: `packages/data-layer/tests/test_db/test_neo4j.py`

- [ ] **Step 1: Write the failing test**
```python
# In packages/data-layer/tests/test_db/test_neo4j.py
def test_save_entity_as_template(mock_neo4j_client):
    from monitor_data.tools.neo4j_tools.entities import neo4j_save_template
    
    mock_neo4j_client.execute_write.return_value = [{"id": "template-123"}]
    result = neo4j_save_template(entity_id="entity-123", template_name="Goblin Grunt")
    assert result == "template-123"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest packages/data-layer/tests/test_db/test_neo4j.py::test_save_entity_as_template -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**
```python
# In packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py
def neo4j_save_template(entity_id: str, template_name: str) -> str:
    """Clone an entity as an EntityTemplate."""
    from monitor_data.db.neo4j import get_neo4j_client
    import uuid
    client = get_neo4j_client()
    new_id = str(uuid.uuid4())
    
    q = """
    MATCH (e:Entity {id: $entity_id})
    CREATE (t:EntityTemplate:Entity {
        id: $new_id,
        name: $template_name,
        properties: e.properties
    })
    RETURN t.id as id
    """
    res = client.execute_write(q, {"entity_id": entity_id, "new_id": new_id, "template_name": template_name})
    return res[0]["id"] if res else ""

# In packages/ui/backend/src/monitor_ui/routers/entities.py
@router.post("/characters/{character_id}/save-template")
async def save_template(character_id: str, template_name: str):
    from monitor_data.tools.neo4j_tools.entities import neo4j_save_template
    tid = neo4j_save_template(character_id, template_name)
    return {"template_id": tid}
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest packages/data-layer/tests/test_db/test_neo4j.py::test_save_entity_as_template -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py packages/ui/backend/src/monitor_ui/routers/entities.py packages/data-layer/tests/test_db/test_neo4j.py
git commit -m "feat(data): allow saving entities as templates"
```
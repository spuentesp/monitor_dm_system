# CF-4: Suggest Plot Hooks

**Actor:** Human GM
**Trigger:** Co-Pilot → Suggest (during prep or session)

**Purpose:** Generate contextually appropriate plot hooks based on world state.

**Flow:**
1. Analyze current context:
   - Active story and recent events
   - Present location and NPCs
   - Unresolved threads (→ CF-3)
   - Character goals and relationships
   - Faction tensions
2. Generate hook suggestions:
   - **Immediate:** Can happen right now
   - **Near-term:** Next session material
   - **Long-term:** Arc-level developments
3. For each hook, provide:
   - Description
   - Involved entities
   - Potential outcomes
   - Connection to existing threads
4. GM selects, modifies, or dismisses
5. Selected hooks optionally saved as plot_thread

**Output:** Contextual plot hook suggestions

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_entities(universe_id, type="faction")   # Active factions
neo4j_get_relationships(entity_id, depth=2)        # NPC networks
neo4j_list_facts(entity_id, type="goal")           # Character motivations
mongodb_get_scene(current_scene_id)                # Current situation
```

**Layer 2 (Agents):**
- `ContextAssembly.get_story_context(story_id)` — Current state
- `Narrator.generate_hooks(context, count=5)` — LLM generation
- `Orchestrator.save_plot_thread(hook)` — If GM accepts

**Layer 3 (CLI):**
```bash
monitor copilot suggest --story <UUID>
monitor copilot suggest --story <UUID> --type combat
monitor copilot suggest --story <UUID> --involving <ENTITY_ID>
```

**Hook Generation Prompt:**
```python
HOOK_PROMPT = """
Given this story context, suggest {count} plot hooks.

Current situation: {scene_summary}
Active factions: {factions}
Unresolved threads: {threads}
Character goals: {character_goals}

For each hook provide:
1. Brief description (1-2 sentences)
2. Why it's relevant now
3. Potential complications
4. Which threads it advances

Genre: {genre}
Tone: {tone}
"""
```

---

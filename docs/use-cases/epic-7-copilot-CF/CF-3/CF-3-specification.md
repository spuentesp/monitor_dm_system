# CF-3: Detect Unresolved Threads

**Actor:** Human GM
**Trigger:** Co-Pilot → Threads (or automatic at session end)

**Purpose:** Surface plot hooks, promises, and dangling storylines the GM may have forgotten.

**Flow:**
1. Analyze story history:
   - All scenes in current story
   - All proposals and facts
   - NPC statements and promises
   - Player stated intentions
2. Identify unresolved items:
   - **Open Questions:** Things players asked but weren't answered
   - **Unfulfilled Promises:** NPCs promised something, not delivered
   - **Dangling Hooks:** Clues planted but not followed up
   - **Incomplete Quests:** Started but not finished
   - **Missing Payoffs:** Setups without resolution
3. Rank by:
   - Recency (older = more urgent)
   - Importance (player interest level)
   - Story relevance
4. Display prioritized list
5. GM can: dismiss, mark resolved, add notes

**Output:** Prioritized list of unresolved threads

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_list_scenes(story_id)                  # All scenes
mongodb_get_turns(scene_id) for each scene     # All dialogue
neo4j_list_facts(story_id, type="promise")     # Tracked promises
neo4j_list_plot_threads(story_id, status="open")  # Open threads
qdrant_search(query="unresolved", story_id)    # Semantic search
```

**Layer 2 (Agents):**
- `ContextAssembly.get_story_history(story_id)` — Full story context
- `CanonKeeper.analyze_threads(story_history)` — LLM analysis for threads

**Layer 3 (CLI):**
```bash
monitor copilot threads --story <UUID>
monitor copilot threads --story <UUID> --critical  # High priority only
```

**Thread Categories:**
```python
class ThreadType(Enum):
    OPEN_QUESTION = "open_question"      # "Who killed the duke?"
    PROMISE = "promise"                   # NPC said they would do X
    HOOK = "hook"                        # Clue planted
    QUEST = "quest"                      # Active objective
    FORESHADOWING = "foreshadowing"      # Setup without payoff
    RELATIONSHIP = "relationship"         # Unresolved NPC tension
```

---

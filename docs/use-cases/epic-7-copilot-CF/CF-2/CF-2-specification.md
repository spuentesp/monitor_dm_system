# CF-2: Generate Session Recap

**Actor:** Human GM or Player
**Trigger:** Co-Pilot → Recap (after session ends)

**Purpose:** Create human-readable summary of what happened.

**Flow:**
1. Select session/scene to recap
2. System analyzes:
   - All turns in scene
   - Accepted proposals
   - Key decisions and outcomes
3. Generate structured recap:
   - **Summary:** 2-3 paragraph overview
   - **Key Events:** Bulleted list
   - **Decisions Made:** Player choices and consequences
   - **NPCs Encountered:** Names and roles
   - **Threads Opened/Closed:** Plot progression
   - **Loot/Rewards:** If applicable
4. Display recap
5. Option: Export as Markdown, share with players

**Output:** Formatted session summary

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_scene(scene_id)                    # Get scene
mongodb_get_turns(scene_id)                    # All turns
mongodb_get_proposals(scene_id, status="accepted")  # What became canon
neo4j_list_events(scene_id)                    # Canonical events
```

**Layer 2 (Agents):**
- `ContextAssembly.get_full_scene_history(scene_id)` — Compile all data
- `Narrator.generate_recap(scene_history)` — LLM summarization

**Layer 3 (CLI):**
```bash
monitor copilot recap --scene <UUID>
monitor copilot recap --story <UUID> --last   # Most recent scene
monitor copilot recap --story <UUID> --all    # Full story recap
```

**LLM Prompt Structure:**
```python
RECAP_PROMPT = """
Summarize this RPG session for players. Include:
1. What happened (narrative summary)
2. Important decisions the party made
3. New information learned
4. Unresolved questions or hooks

Session data:
{scene_turns}

Tone: {story_tone}
"""
```

---

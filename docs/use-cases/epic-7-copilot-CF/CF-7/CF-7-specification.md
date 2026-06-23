# CF-7: Session Prep Assistant

**Actor:** Human GM
**Trigger:** Co-Pilot → Prep (before session)

**Purpose:** Help GM prepare for upcoming session with contextual briefing and suggestions.

**Flow:**

1. **Pre-Session Briefing:**
   - Recap: What happened in previous sessions
   - Dangling threads: Unresolved plot points
   - NPC status: Where key NPCs are, what they want
   - World state: Time, location, active events
   - Player intentions: Stated goals (if recorded)

2. **Suggested Prep:**
   - NPCs likely to appear (based on location/plot)
   - Scenes that might occur
   - Rolls that might be needed
   - Reference materials to review

3. **Checklist Generation:**
   - Customizable prep checklist
   - Mark items as ready
   - Generate missing content on demand

4. **Quick Content Generation:**
   - Generate NPC names/traits
   - Generate location descriptions
   - Generate rumors/hooks
   - Roll on random tables

### Implementation

**Layer 1 (Data Layer):**
```python
# Gather story state
neo4j_get_story(story_id)
neo4j_list_plot_threads(story_id, status="open")
neo4j_list_entities(story_id, type="character", role="npc")
mongodb_get_story_outline(story_id)
mongodb_list_scenes(story_id, limit=5, order="desc")
```

**Layer 2 (Agents):**
- `ContextAssembly.generate_session_briefing(story_id)` — Full context
- `Narrator.suggest_session_content(context)` — What might happen
- `Narrator.generate_prep_checklist(context, template)` — Customized checklist

**Layer 3 (CLI):**
```bash
monitor copilot prep --story <UUID>
monitor copilot prep --story <UUID> --quick  # Just briefing
monitor copilot prep --story <UUID> --checklist
```

**Session Prep Schema:**
```python
@dataclass
class SessionBriefing:
    story_id: UUID
    generated_at: datetime

    # Recap
    last_session_summary: str
    sessions_since_last_play: int

    # Current State
    world_date: WorldDate
    party_location: str
    party_status: str

    # Dangling Threads
    open_threads: list[PlotThreadSummary]
    urgent_deadlines: list[Deadline]

    # NPCs
    active_npcs: list[NPCSummary]
    npc_intentions: dict[UUID, str]  # What each NPC wants

    # Suggestions
    likely_scenes: list[str]
    potential_encounters: list[str]
    hooks_to_introduce: list[str]

    # Prep Checklist
    checklist: list[PrepItem]

@dataclass
class PrepItem:
    category: str  # "npc", "location", "combat", "lore"
    description: str
    status: PrepStatus  # pending, ready, skipped
    generated_content: str | None
```

**Session Prep Prompt:**
```python
PREP_PROMPT = """
You are helping a GM prepare for their next session.

Story: {story_title}
Last Session: {last_session_summary}
Open Threads: {open_threads}
Active NPCs: {active_npcs}
Party Location: {party_location}

Generate a session prep briefing that includes:
1. Key things to remember from last session
2. What NPCs are doing "off-screen"
3. Likely player actions and how to handle them
4. 2-3 potential scenes that could occur
5. Any prep work needed (maps, stat blocks, etc.)

Keep it concise and actionable.
"""
```

---

# DL-6 Narrative Engine Implementation

## Overview

DL-6 provides a comprehensive narrative engine infrastructure that supports story planning, beat progression, mystery mechanics, pacing tracking, and plot thread management. This document maps the implementation to use cases and identifies agent-level features that leverage these tools.

---

## What Was Built (Data Layer)

### MongoDB - Story Outlines

**Core Planning:**
- Story beats with status tracking (pending/in_progress/completed/skipped)
- Beat relationships to plot threads
- Structure types (linear/branching/open_world)
- Arc templates (three_act/heist/mystery/journey/siege/political/dungeon/custom)
- Branching points for non-linear narratives

**Mystery Mechanics:**
- Mystery structure with core clues, bonus clues, red herrings
- Suspects with evidence tracking (for/against)
- Clue discovery workflow (hidden → discovered → revealed)
- Current player theories tracking
- Discovery scene mapping (which scene discovered which clue)

**Pacing System:**
- Auto-calculated completion percentage (completed_beats / total_beats)
- Current act tracking (1-5)
- Tension level (0.0-1.0)
- Scenes since major event counter
- Last updated timestamp

**Beat Operations:**
- Add beats (append to end)
- Remove beats by ID
- Update existing beats (preserves order)
- Reorder beats (requires all beat IDs)
- Mark clues as discovered

### Neo4j - Plot Threads

**Thread Tracking:**
- Thread type (main/side/character/mystery)
- Status (open/advanced/resolved/abandoned)
- Priority (main/major/minor/background)
- Urgency (low/medium/high/critical)
- Deadlines with in-game world_time

**Relationships (5 types):**
- `HAS_THREAD` - Story → PlotThread
- `ADVANCED_BY` - PlotThread → Scene (scenes that progressed thread)
- `INVOLVES` - PlotThread → Entity (entities involved)
- `FORESHADOWS` - Event → PlotThread (setup)
- `REVEALS` - Event → PlotThread (payoff)

**Foreshadowing/Payoff:**
- PayoffStatus tracking (setup_only → partial_payoff → full_payoff → abandoned)
- Foreshadowing events list
- Revelation events list
- Prevents orphaned setups

**Engagement Metrics:**
- Player interest level (0.0-1.0, tracked from engagement)
- GM importance (0.0-1.0, set by GM)
- Timestamps (created_at, updated_at, resolved_at)

**Querying:**
- Filter by story, type, status, priority, entity
- Sort by created_at, updated_at, priority, urgency
- Pagination support

---

## How It Supports Use Cases

### ST-1: Plan Story Arc ✅
**Implementation Status:** Fully supported by DL-6

**Data Layer Support:**
- `mongodb_create_story_outline` - Create arc with beats and template
- `mongodb_update_story_outline` - Modify beats, add branching points
- `neo4j_create_plot_thread` - Create threads for inciting incident, rising actions, crisis points

**Agent Layer Needed:**
- `Narrator.generate_arc_structure(params)` - LLM arc generation
- `CanonKeeper.validate_arc(arc)` - Check consistency with canon
- `Orchestrator.plan_arc(story_id, params)` - Coordinate planning

**Example Flow:**
```python
# 1. Create story outline with template
outline = mongodb_create_story_outline(
    story_id=story_id,
    theme="Revenge and redemption",
    template=ArcTemplate.THREE_ACT,
    beats=[
        StoryBeat(title="Inciting Incident", order=0),
        StoryBeat(title="Rising Action 1", order=1),
        # ...
    ]
)

# 2. Create plot threads for major arcs
main_thread = neo4j_create_plot_thread(
    story_id=story_id,
    title="Avenge murdered family",
    thread_type=PlotThreadType.MAIN,
    priority=ThreadPriority.MAIN
)
```

---

### ST-4: Design Mystery Structure ✅
**Implementation Status:** Fully supported by DL-6

**Data Layer Support:**
- `mongodb_create_story_outline(mystery_structure=...)` - Full mystery setup
- `mongodb_update_story_outline(mark_clue_discovered=...)` - Track discoveries
- Clue visibility state machine (hidden/discovered/revealed)
- Suspect evidence tracking

**Agent Layer Needed:**
- `Narrator.design_mystery(params)` - Generate mystery structure
- `Narrator.validate_solvability(mystery)` - Check three-clue rule
- `ContextAssembly.track_discoveries(scene_id)` - Track what players found

**Example Flow:**
```python
# Create mystery structure
mystery = MysteryStructure(
    truth="The butler did it to protect the family secret",
    question="Who killed Lord Ashton?",
    core_clues=[
        MysteryClue(
            content="Muddy footprints match the butler's boots",
            discovery_methods=["investigation", "search"],
            visibility=ClueVisibility.HIDDEN,
            points_to="butler"
        ),
        # ... more core clues (3+ for solvability)
    ],
    suspects=[
        MysterySuspect(
            entity_id=butler_id,
            theory="Butler killed him for inheritance",
            evidence_for=[clue1_id, clue2_id],
            evidence_against=[clue3_id]
        )
    ]
)

outline = mongodb_create_story_outline(
    story_id=story_id,
    template=ArcTemplate.MYSTERY,
    mystery_structure=mystery
)

# During play: mark clues discovered
mongodb_update_story_outline(
    story_id=story_id,
    mark_clue_discovered=clue1_id
)
```

---

### P-1: Begin Solo Play ✅ (Partial)
**Implementation Status:** Data support exists, agent integration pending

**Data Layer Support:**
- Beat progression tracking (status transitions)
- Scene completion mapping (`completed_in_scene_id`)
- Pacing metrics (auto-calculated)

**Agent Layer Needed:**
- `Narrator.check_beat_triggers()` - Check if required_for_threads are active
- `Narrator.complete_beat(beat_id, scene_id)` - Mark beat complete
- `Orchestrator.adjust_pacing()` - Use pacing metrics to guide session flow

**Example Flow:**
```python
# During scene: check if beat should trigger
beat = current_outline.beats[current_beat_index]
if all_required_threads_active(beat.required_for_threads):
    mongodb_update_story_outline(
        story_id=story_id,
        update_beats=[
            StoryBeat(
                beat_id=beat.beat_id,
                status=BeatStatus.IN_PROGRESS,
                started_at=datetime.now(timezone.utc)
            )
        ]
    )

# When beat completes
mongodb_update_story_outline(
    story_id=story_id,
    update_beats=[
        StoryBeat(
            beat_id=beat.beat_id,
            status=BeatStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            completed_in_scene_id=current_scene_id
        )
    ]
)
```

---

### P-8: Conclude Scene ✅ (Partial)
**Implementation Status:** Data support exists, agent integration pending

**Data Layer Support:**
- `neo4j_update_plot_thread(add_scene_ids=[scene_id])` - Mark scene advanced thread
- Thread status transitions (open → advanced → resolved)
- Beat completion tracking

**Agent Layer Needed:**
- `CanonKeeper.advance_threads(scene_id)` - Identify which threads advanced
- `CanonKeeper.mark_beats_complete(scene_id)` - Complete associated beats

**Example Flow:**
```python
# Scene finalization
scene_summary = analyze_scene(scene_id)

# Advance relevant threads
for thread_id in scene_summary.advanced_threads:
    neo4j_update_plot_thread(
        thread_id=thread_id,
        status=PlotThreadStatus.ADVANCED,
        add_scene_ids=[scene_id]
    )

# Check if any beats completed
for beat_id in scene_summary.completed_beats:
    mongodb_update_story_outline(
        story_id=story_id,
        update_beats=[
            StoryBeat(
                beat_id=beat_id,
                status=BeatStatus.COMPLETED,
                completed_in_scene_id=scene_id
            )
        ]
    )
```

---

### CF-3: Post-Session Analysis ✅ (Partial)
**Implementation Status:** Data support exists, agent integration pending

**Data Layer Support:**
- `neo4j_list_plot_threads(status=PlotThreadStatus.OPEN)` - Find unresolved threads
- `neo4j_list_plot_threads(payoff_status=PayoffStatus.SETUP_ONLY)` - Find orphaned setups
- Pacing metrics (tension, completion, scenes since major event)

**Agent Layer Needed:**
- `Analyzer.list_open_threads()` - Query unresolved threads
- `Analyzer.check_pacing()` - Review pacing metrics for balance
- `Analyzer.orphaned_foreshadowing()` - Find setups without payoff

**Example Flow:**
```python
# Post-session: check for unresolved threads
open_threads = neo4j_list_plot_threads(
    story_id=story_id,
    status=PlotThreadStatus.OPEN,
    sort_by="priority",
    sort_order="desc"
)

# Check for orphaned foreshadowing
orphaned = neo4j_list_plot_threads(
    story_id=story_id,
    payoff_status=PayoffStatus.SETUP_ONLY,
    priority=ThreadPriority.MAIN  # High priority setups without payoff
)

# Check pacing
outline = mongodb_get_story_outline(story_id)
if outline.pacing_metrics.scenes_since_major_event > 5:
    suggest_major_event()
```

---

## Agent-Level Features to Build

These features need agent implementation to leverage DL-6:

### 1. Beat Progression Manager (Layer 2 - Narrator)
**Purpose:** Automatically track and trigger story beats during play

**Responsibilities:**
- Check beat trigger conditions (`required_for_threads`)
- Mark beats as in_progress when scene starts
- Mark beats as completed when objectives met
- Notify Orchestrator of beat completion for pacing

**Tools Used:**
- `mongodb_get_story_outline` - Get current beats
- `mongodb_update_story_outline(update_beats)` - Update statuses
- `neo4j_list_plot_threads` - Check required threads

---

### 2. Pacing Monitor (Layer 2 - Orchestrator)
**Purpose:** Use pacing metrics to guide session flow

**Responsibilities:**
- Monitor `scenes_since_major_event`
- Track `estimated_completion` for session length estimates
- Adjust `tension_level` based on narrative flow
- Suggest pacing adjustments to GM

**Tools Used:**
- `mongodb_get_story_outline` - Read pacing metrics
- `mongodb_update_story_outline` - Update pacing (if auto-adjusted)

**Pacing Rules:**
```python
if pacing.scenes_since_major_event > 5:
    suggest("Consider introducing a major plot development")

if pacing.tension_level < 0.3 and pacing.current_act >= 3:
    suggest("Tension low for Act 3 - escalate stakes")

if pacing.estimated_completion > 0.9 and open_threads > 3:
    suggest("Approaching finale with many unresolved threads")
```

---

### 3. Thread Advancement Tracker (Layer 2 - CanonKeeper)
**Purpose:** Link scenes to plot threads during scene finalization

**Responsibilities:**
- Analyze scene to identify which threads advanced
- Create `ADVANCED_BY` relationships
- Update thread status (open → advanced → resolved)
- Track which entities were involved (`INVOLVES`)

**Tools Used:**
- `neo4j_update_plot_thread(add_scene_ids, add_entity_ids, status)`

---

### 4. Foreshadowing/Payoff Manager (Layer 2 - Narrator)
**Purpose:** Track narrative setups and ensure payoffs

**Responsibilities:**
- Mark events as `FORESHADOWS` when introducing threads
- Mark events as `REVEALS` when paying off threads
- Update `payoff_status` (setup_only → partial_payoff → full_payoff)
- Alert if high-priority threads have setup_only status for too long

**Tools Used:**
- `neo4j_create_plot_thread(foreshadowing_events, payoff_status)`
- `neo4j_update_plot_thread(add_revelation_events, payoff_status)`
- `neo4j_list_plot_threads(payoff_status=SETUP_ONLY)` - Find orphans

**Orphan Detection:**
```python
# Find threads with setup but no payoff after N sessions
orphans = neo4j_list_plot_threads(
    story_id=story_id,
    payoff_status=PayoffStatus.SETUP_ONLY,
    priority__in=[ThreadPriority.MAIN, ThreadPriority.MAJOR]
)

for thread in orphans:
    sessions_since_setup = calculate_sessions(thread.created_at)
    if sessions_since_setup > 3:
        alert(f"Thread '{thread.title}' has setup but no payoff for {sessions_since_setup} sessions")
```

---

### 5. Clue Discovery Manager (Layer 2 - Narrator)
**Purpose:** Handle investigation mechanics and clue reveals

**Responsibilities:**
- Check if player actions match `discovery_methods`
- Mark clues as discovered via `mark_clue_discovered`
- Update clue `visibility` (hidden → discovered → revealed)
- Track which scene discovered the clue

**Tools Used:**
- `mongodb_update_story_outline(mark_clue_discovered=clue_id)`

**Investigation Flow:**
```python
# Player searches library
action = "search library"
outline = mongodb_get_story_outline(story_id)

for clue in outline.mystery_structure.core_clues:
    if not clue.is_discovered and "search" in clue.discovery_methods:
        # Found clue!
        mongodb_update_story_outline(
            story_id=story_id,
            mark_clue_discovered=clue.clue_id
        )
        reveal_clue_to_player(clue)
```

---

### 6. Thread Query Service (Layer 2 - Context Assembly)
**Purpose:** Provide thread information to other agents

**Responsibilities:**
- List open threads for session prep
- Find threads involving specific entities
- Filter threads by priority for focus
- Sort by urgency for deadline pressure

**Tools Used:**
- `neo4j_list_plot_threads` with various filters

**Query Examples:**
```python
# Session prep: "What threads involve this NPC?"
npc_threads = neo4j_list_plot_threads(
    story_id=story_id,
    entity_id=npc_id,
    status__in=[PlotThreadStatus.OPEN, PlotThreadStatus.ADVANCED]
)

# GM: "What are the urgent open threads?"
urgent = neo4j_list_plot_threads(
    story_id=story_id,
    status=PlotThreadStatus.OPEN,
    urgency__in=[ThreadUrgency.HIGH, ThreadUrgency.CRITICAL],
    sort_by="urgency",
    sort_order="desc"
)

# Analysis: "Show main plot threads"
main_plot = neo4j_list_plot_threads(
    story_id=story_id,
    thread_type=PlotThreadType.MAIN,
    sort_by="created_at"
)
```

---

## Summary

**What DL-6 Provides (Layer 1):**
- ✅ Story outline CRUD with beat manipulation
- ✅ Mystery structure with clue tracking
- ✅ Pacing metrics (auto-calculated)
- ✅ Plot thread CRUD with 5 relationship types
- ✅ Foreshadowing/payoff tracking
- ✅ Comprehensive querying and filtering

**What Agents Need to Build (Layer 2):**
- ⏳ Beat Progression Manager (Narrator)
- ⏳ Pacing Monitor (Orchestrator)
- ⏳ Thread Advancement Tracker (CanonKeeper)
- ⏳ Foreshadowing/Payoff Manager (Narrator)
- ⏳ Clue Discovery Manager (Narrator)
- ⏳ Thread Query Service (Context Assembly)

**Status:**
- Data Layer (DL-6): ✅ Complete (merged PR #96)
- Agent Layer: ⏳ Pending implementation
- CLI Layer: ⏳ Pending (`monitor story` commands)

The DL-6 implementation provides a comprehensive foundation for narrative mechanics. The next step is implementing agent-level features that use these tools during actual gameplay.

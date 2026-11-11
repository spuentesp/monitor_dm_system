# CF-12: Generate Campaign (Story-Arc) Recap

**Status:** proposed (gap G05, plan `docs/architecture/gm-assistant-gap-plans/G05-campaign-recap-CF-12.md`)

**Actor:** Human GM
**Trigger:** Story page "Campaign So Far" section / Prep panel, or automatically at session wrap-up

**Purpose:** Produce a "where are we in the campaign" document across ALL scenes of a
story — major arcs, party journey, faction shifts, resolved vs. open threads — and
persist it so later reads do not regenerate it (complements CF-2, the per-session recap).

**Flow:**
1. GM opens the story (GM page → Prep panel "Campaign So Far", collapsible) or POSTs
   `/api/stories/{story_id}/arc-recap`
2. System gathers, per story:
   - All scenes (MongoDB, oldest first) with their persisted per-scene summaries (CF-2)
   - Story outline (beats/theme/premise)
   - Significant canon facts (Neo4j, high magnitude)
   - **Accepted** proposed changes only (pending/rejected never count as canon)
   - Open/resolved plot threads
3. `RecapAgent.generate_arc_recap(story_id, universe_id, detail)` runs hierarchical
   map-reduce: scene recaps → chunks of N scenes → arc beats per chunk → one campaign
   summary (stays within context limits for long campaigns)
4. Result persisted as one MongoDB `arc_recaps` document per story (upsert =
   idempotent), stored with `generated_at` and a scene watermark
   (`scene_count`, `scenes_watermark`, `last_scene_id`)
5. `GET /api/stories/{story_id}/arc-recap` returns the persisted artifact
   (`{"persisted": true, ...}`) without regenerating; 404 when none exists yet
6. Session wrap-up (`POST /chat/{session_id}/wrap-up`) auto-refreshes the arc recap
   best-effort after persisting the CF-2 session recap

**Output:** Markdown campaign recap with sections: Major Arcs, Party Journey,
Faction Shifts, Resolved Threads, Open Threads.

**Length controls:** `detail` = `short | standard | detailed` (matches CF-6 detail levels).

**CF-6 reuse:** handout type `campaign_summary` draws on the persisted arc recap.

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_list_scenes(SceneFilter(story_id=..., limit=1000, sort_order="asc"))
mongodb_get_story_outline(story_id)
mongodb_list_proposed_changes(ProposedChangeFilter(story_id=..., status=ACCEPTED))
neo4j_list_facts(FactFilter(universe_id=..., min_magnitude=4))
neo4j_list_plot_threads(PlotThreadFilter(story_id=...))
mongodb_save_arc_recap(ArcRecapCreate(...))   # upsert, one doc per story
mongodb_get_arc_recap(story_id)                # persisted read
```

**Layer 2 (Agents):**
- `RecapAgent.generate_arc_recap(story_id, universe_id, detail="standard", persist=True)`
  in `packages/agents/src/monitor_agents/recap/agent.py` — map-reduce over scene recaps
  (`ArcRecapModule` DSPy signatures in `recap/recap.py`)

**Layer 3 (UI backend):**
```python
GET  /api/stories/{story_id}/arc-recap   # persisted read, never regenerates
POST /api/stories/{story_id}/arc-recap   # generate/refresh (body: {"detail": ...})
```

---

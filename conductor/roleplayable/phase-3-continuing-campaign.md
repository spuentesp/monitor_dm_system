# Phase 3 brief: a campaign that continues

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** After the opening, the campaign carries on: each scene leads to the next, the GM
knows what happened in earlier scenes in order, in-game time means something, and the world
moves between scenes. A campaign survives a backend restart with nothing lost.

**Context.** A turn works. Above the turn, a new scene starts with zero turns, a recap of only
the previous scene cut to 120 characters, and three memories chosen by similarity. The arc is
a function of scene count. In-game time starts at year 1000 for every story and nothing reads
it. The validators that check time have no callers. Arc state for the Narrator sits in a
process dict.

**You own.** In `packages/agents/src/monitor_agents/`: `loops/story_loop.py`, `story/`,
`context_assembly/`, `temporal_validation.py`, `recap/`; `complete_current_scene` and
`load_context` in `loops/scene_loop.py`; the scene-completion block of
`loops/scene_orchestrator.py`. In `packages/data-layer/src/monitor_data/tools/`:
`mongodb_tools/stories.py`, `mongodb_tools/scenes.py`, `temporal_tools/`. In
`packages/ui/backend/src/monitor_ui/routers/chat_loops.py`: `_STORY_STATES` and the scene-end
path.

**Do not touch.** Pre-play loops and world seed (Phase 2). The `narrate` node inputs,
`narrator/`, `extraction/`, `npc_voice/` (Phase 4). You may add one new input field to the
Narrator for the ledger; tell Phase 4 its name.

## Tasks

1. **Story ledger.** At every scene end, on both the automatic and the explicit end-scene
   paths, write a ledger entry on the story: a 150–300 word summary, a list of state changes
   (who, what, where), open questions, the scene's in-game start and end time. One
   STANDARD-tier call. Store all entries; never overwrite.
2. **Feed the ledger.** Context assembly returns the last two entries in full and older ones
   compressed to a line each, within the token budget. Remove the 120-character cap in
   `_opening_recap_block` and have the Narrator and GMAgent receive the ledger on every turn
   of a scene, not only the first.
3. **Arc from events.** Replace the scene-count heuristic in `StoryAgent.evaluate_arc` with a
   model evaluation over the ledger and the story's plot-thread records in Neo4j. It returns
   the arc phase, tension, which threads advanced or closed, and whether the story is
   complete. Keep the scene budget from PR #136 as an upper bound, not the driver. Remove the
   hardcoded `central_conflict` and `character_motivation` threads.
4. **Persist arc state.** Delete `_STORY_STATES`. Read story state from the MongoDB checkpoint
   every time. A restart between any two turns must change nothing the Narrator sees.
5. **World moves.** With the agenda tick fixed in Phase 1, feed its moves into the next scene:
   the ledger entry records them and the next scene's hook may use them.
6. **In-game time.** Seed `in_game_time` from the universe (a setting date or era; ask the
   world seed or fall back to a model estimate) instead of year 1000. Pass the current time
   into every fact, event and memory written during play as `time_ref`.
7. **Use time at retrieval.** Order facts by `time_ref` and exclude superseded ones using the
   existing `get_active_facts`. In flashback scenes only, call `validate_scene_revision`
   before canonization and surface its warnings.
8. **Progression.** Replace `prog_loop.start(available_xp=5)` with a value derived from the
   scene, and wait for the player's choice before applying it.

## Out of scope

Per-NPC memory and the cast list (Phase 4). Extracting chronology from books.

## Done when

- A scripted five-scene campaign with a backend restart after scenes 2 and 4 completes with
  an ended story.
- The ledger has five entries with increasing in-game times.
- The prompt for scene 5's first turn contains a fact from scene 1 that is not in canon.
- A fact superseded in scene 3 is absent from scene 4's context.
- The arc phase changes at least twice, and not on fixed scene numbers across two different
  runs.
- `tests/e2e` covers the restart case and asserts that the agenda tick, ledger write and arc
  evaluation each ran.

---
description: "The LangGraph Story Loop — campaign/arc progression across scenes."
tags: [loop, langgraph, story-loop]
layer: 2
---

# Story Loop (Campaign Progression)

**Intent:** Manage a story arc — sequence scenes, advance the world off-screen
between them, and finalize when the arc completes.

**Source:** `packages/agents/src/monitor_agents/loops/story_loop.py`
(`build_story_graph`). Delegates each scene to the [Scene Loop](./scene_loop.md).

## Arc contract

A story spans several scenes. Finishing a scene advances the story to the next
one; the story itself ends when its arc resolves.

Every scene that ends writes a **ledger entry**: a 150–300 word summary, the
state changes it caused (who, what, where), the questions it left open and the
scene's in-game start and end time. The ledger is append-only and lives in
MongoDB; it is the campaign's memory and it is what the arc is judged from.

The arc moves through four phases, and a model reads the ledger and the story's
plot threads to say which one the story is in:

| Phase | What happens |
|---|---|
| `rising_action` | Tension climbs; the story's plot threads are open. |
| `climax` | The conflict is confronted. |
| `falling_action` | The aftermath of the climax. |
| `resolution` | The arc resolves and the story is complete. |

The story's `scene_budget` (5 scenes by default) is an **upper bound** on the
campaign's length, not the thing that drives the arc: a story that reaches its
budget resolves, but a story never resolves early because a counter said so. A
caller that wants a longer or shorter campaign sets `scene_budget` on the
`StoryState`; a caller that wants the story to end early passes `story_complete`
in the scene outcome.

## Nodes

- `init_story` — establish arc parameters + initial world state.
- `run_scene` — hand control to the Scene Loop for one scene.
- `evaluate_arc` — after a scene, decide: continue, transition, or finalize.
- `world_advance` — run the world-simulation step (faction moves, NPC actions,
  environmental change) based on elapsed time.
- `transition` — update continuity + plot threads before the next scene.
- `finalize` — wrap the arc; ensure final world state is canonized.

## State

The story state is checkpointed after every scene, so a campaign that is
interrupted — or resumed in another process — keeps its scenes, its arc
position, its ledger and its in-game time. `StoryLoop.start_or_resume()` returns
the checkpointed story when there is one instead of starting over, and
`StoryLoop.load_checkpoint_state()` reads it without running the graph.

The in-game clock is seeded from the world: the story's own `start_time_ref`,
then the world seed, then a model estimate read from the universe. The clock
moves with the scenes, and everything a scene writes — facts, events, memories —
carries the time it happened at.

## See Also
- [Scene Loop](./scene_loop.md) · [Loops Index](./_index.md)

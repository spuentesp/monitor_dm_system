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

The arc runs through four phases, and the story's `scene_budget` (5 scenes by
default) decides how many scenes each phase takes:

| Phase | Scenes | What happens |
|---|---|---|
| `rising_action` | until `budget - 3` | Tension climbs; the story opens its plot threads. |
| `climax` | `budget - 2` | The conflict is confronted and the plot threads are paid off. |
| `falling_action` | `budget - 1` | The aftermath of the climax. |
| `resolution` | `budget` | The arc resolves and the story is complete. |

Because the phases are ordered, the arc always reaches its resolution — a
story cannot stall. A caller that wants a longer or shorter campaign sets
`scene_budget` on the `StoryState`; a caller that wants the story to end early
passes `story_complete` in the scene outcome.

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
position and its in-game time. `StoryLoop.start_or_resume()` returns the
checkpointed story when there is one instead of starting over.

## See Also
- [Scene Loop](./scene_loop.md) · [Loops Index](./_index.md)

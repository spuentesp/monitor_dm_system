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

## Nodes

- `init_story` — establish arc parameters + initial world state.
- `run_scene` — hand control to the Scene Loop for one scene.
- `evaluate_arc` — after a scene, decide: continue, transition, or finalize.
- `world_advance` — run the world-simulation step (faction moves, NPC actions,
  environmental change) based on elapsed time.
- `transition` — update continuity + plot threads before the next scene.
- `finalize` — wrap the arc; ensure final world state is canonized.

## See Also
- [Scene Loop](./scene_loop.md) · [Loops Index](./_index.md)

---
description: "The World-Building Loop — collaborative setting creation (World Architect mode)."
tags: [loop, langgraph, world-building]
layer: 2
---

# World-Building Loop

**Intent:** A structured, collaborative session between the user and the
`WorldArchitect` to define or expand a setting (entities, axioms, lore) before
play — Mode 1 (World Architect).

**Source:** `packages/agents/src/monitor_agents/loops/world_building_loop.py`
(`build_world_building_graph`). Driven by the chat router (backend).

## Nodes

```
load_world_context → process_user_input → format_response
```

- `load_world_context` — pull the current setting state relevant to the request.
- `process_user_input` — interpret the authoring request; stage setting changes
  as batched `ProposedChange`s for mass-canonization.
- `format_response` — return the assistant reply + any proposals for review.

## See Also
- [Vision & Modes](../1_product/vision_and_modes.md) · [Loops Index](./_index.md)

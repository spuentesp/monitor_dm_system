---
description: "The Progression Loop — character advancement / level-up."
tags: [loop, langgraph, progression]
layer: 2
---

# Progression Loop

**Intent:** Apply character advancement — present schema-valid advancement
options and finalize the chosen changes.

**Source:** `packages/agents/src/monitor_agents/loops/progression_loop.py`
(`build_progression_graph`).

## Flow

```
load_options → finalize
```

- `load_options` — derive the advancement choices available to the character
  from the game system's progression rules.
- `finalize` — apply the selected advancement, staging the changes as
  `ProposedChange`s for CanonKeeper.

## See Also
- [Character Creation Loop](./character_creation_loop.md) · [Loops Index](./_index.md)

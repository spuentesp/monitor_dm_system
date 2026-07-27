---
description: "The Character Creation Loop — conversational, schema-driven character builder."
tags: [loop, langgraph, character-creation]
layer: 2
---

# Character Creation Loop

**Intent:** Build a character step-by-step, driven by the game system's own
creation procedure (schema-defined steps), as a conversation.

**Source:** `packages/agents/src/monitor_agents/loops/character_creation_loop.py`
(`build_character_creation_graph`).
**Called by:** the Story Loop or Conversation Loop.

## Flow

```
load_system → present_step ⇄ process_input → (loop until steps complete)
```

- `load_system` — load the `GameSystemRuntime`; if the system has no creation
  steps, infer a default sequence and inject a canonical "choose name" step
  (`step_number=1`, enum value `choose_name`) that passes the
  `CreationStepType` schema check.
- `present_step` — show the current step's prompt/options.
- `process_input` — validate + record the player's choice, advance the step.

## See Also
- [Session Zero Loop](./session_zero_loop.md) — story-first character interview
- [Progression Loop](./progression_loop.md) · [Loops Index](./_index.md)

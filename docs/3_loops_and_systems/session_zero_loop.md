---
description: "The Session Zero Loop — guided, story-first character development interview."
tags: [loop, langgraph, session-zero]
layer: 2
---

# Session Zero Loop

**Intent:** Conduct a guided, story-first character-development interview before
play begins — draw out concept, background, and hooks conversationally.

**Source:** `packages/agents/src/monitor_agents/loops/session_zero_loop.py`
(`build_session_zero_graph`).
**Called by:** `chat_loops.py` via `run_preplay_turn`.

## Flow

```
ask ⇄ process → summarize
```

- `ask` — pose the next interview question (story-first, not stat-first).
- `process` — record the answer, decide whether to continue or wrap up.
- `summarize` — synthesize the answers into a character concept + seeds.

## See Also
- [Character Creation Loop](./character_creation_loop.md) — mechanical build
- [Conversation Loop](./conversation_loop.md) · [Loops Index](./_index.md)

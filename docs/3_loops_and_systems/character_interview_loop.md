---
description: "The character-interview loop — guided, story-first character development interview before play begins."
tags: [loop, langgraph, character-interview, session-zero]
layer: 2
---

# Character Interview Loop

**Intent:** Collect the player's character concept, backstory, bonds,
fears, and motivations through a guided interview before mechanical
character creation runs.

**Source:** `packages/agents/src/monitor_agents/loops/character_interview_loop.py`
(`CharacterInterviewLoop`; compatibility alias for the old
`SessionZeroLoop`).

**Called by:** `preplay_orchestrator.handle_character_interview`.

## Flow

```
ask ⇄ process → summarize
```

- `ask` — pose the next interview question (story-first, not stat-first).
- `process` — record the answer, decide whether to continue or wrap up.
- `summarize` — synthesize the answers into a character concept + seeds
  that the next pre-play stage consumes.

## Distinction from Session Zero (the agreement stage)

The P-19 redesign split the old `SessionZeroLoop` into two stages:

- **Character Interview** (this loop) — *who* is the character.
- **Story Agreements** (`story_agreements_loop.py`) — *what story* the table
  is about (premise, themes, lines, veils). The player confirms agreements
  by pressing **Begin Story**.

## See Also
- [Character Creation Loop](./character_creation_loop.md) — mechanical build
- [Story Agreements Loop](./story_agreements_loop.md) — table agreements
- [Scene Loop](./scene_loop.md) · [Loops Index](./_index.md)

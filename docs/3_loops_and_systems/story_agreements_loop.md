---
description: "The story-agreements loop — three-question Session Zero agreement interview that captures premise, themes, lines, and veils."
tags: [loop, langgraph, story-agreements, session-zero]
layer: 2
---

# Story Agreements Loop

**Intent:** Capture the table-level contract for the upcoming story —
desired story, themes, tone/pacing, and hard content boundaries (lines
and veils) — and emit a structured `StoryAgreements` summary the player
confirms by pressing **Begin Story**.

**Source:** `packages/agents/src/monitor_agents/loops/story_agreements_loop.py`
(`StoryAgreementsLoop`).

**Called by:** `preplay_orchestrator.handle_story_agreements`.

## Flow

```
present → process → summarize
```

- `present` — pose the next of three questions (premise, themes, boundaries)
  or an authored variant from a `PromptCollection` with
  `category="story_agreements"`.
- `process` — record the answer, move the question pointer forward.
- `summarize` — call `summarize_story_agreements` to assemble the
  `StoryAgreements` Pydantic model. The loop stays in
  `awaiting_confirmation=True` until the player presses **Begin Story**.

## Agreement schema

`StoryAgreements` is persisted at `session["story_agreements"]` and
includes, at minimum:

- `story_premise`, `themes`, `tone`, `pacing`, `pc_role`
- `lines` (subjects that must never be depicted or introduced)
- `veils` (subjects that may exist but must fade to black)
- `source`, `revision`, `confirmed`, `confirmed_at`

Lines and veils are propagated to every subsequent SceneLoop turn via
`SceneState.agreements_lines`/`agreements_veils`, the Resolver and
Narrator `scene_context["agreements"]` block, and the GMAgent ReAct
`table_agreements` directive.

## See Also
- [Character Interview Loop](./character_interview_loop.md) — character identity
- [Scene Loop](./scene_loop.md) — lines & veils enforcement
- [Loops Index](./_index.md)

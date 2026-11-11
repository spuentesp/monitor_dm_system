# G05 — Campaign-level (story-arc) recap (proposed CF-12)

> **Status:** proposed 2026-11-11. Gap: recap exists only per chat session
> (`GET /chat/{id}/recap`, persisted). `stories.py` exposes scenes/threads
> but no arc-level summary — after a long campaign there is no "where are
> we" document, even though the CF-2 spec describes a full-story mode.

## Goal

Generate and persist a story-arc recap across all scenes of a story:
major arcs, party journey, faction shifts, resolved vs. open threads —
refreshable on demand and after each session, cached like CF-2.

## Use case

Propose **CF-12 "Generate Campaign (Story-Arc) Recap"**; complements CF-2
(session recap). CF-6 handout type "campaign summary" reuses this output.

## Design

- **Layer 1:** read path only — `mongodb_list_scenes(story_id)`,
  per-scene persisted recaps (CF-2), accepted proposals, `neo4j_list_*`
  via MCP; new `mongodb` doc per story: `arc_recap` (like the session
  recap persistence pattern in `chat.py:628`).
- **Layer 2:** new `RecapAgent.generate_arc_recap(story_id)` (extends the
  existing recap agent in the narrator/recap module) — hierarchical
  summarization: scene recaps → arc beats → campaign summary (map-reduce
  over scene recaps to stay within context limits; precedent:
  `ContextAssembly.get_full_scene_history` chunking).
- **Layer 3:** `POST /stories/{story_id}/arc-recap` (generate/refresh) and
  `GET /stories/{story_id}/arc-recap` (persisted read) in `routers/stories.py`;
  UI: button on the story/forge page + a section in the CF-7 prep briefing
  ("campaign so far" collapsible).

## Phases

1. Agent: `generate_arc_recap` + tests with FakeLLMClient (chunking,
   empty-story edge, idempotent persistence).
2. Persistence schema/tool + routes (`test_stories_arc_recap.py`).
3. UI: story page section + prep-panel integration; vitest.
4. CF-6 "campaign summary" handout type wired to this output.

## Acceptance

- `GET` returns the persisted arc recap without regenerating (same
  contract as CF-2's `{"persisted": true}`).
- Recap covers all scenes, is refreshable after each session, and stays
  consistent with canon (only accepted proposals count).
- Commits reference CF-12; tests green at agents + backend + frontend.

## Open decisions

- Refresh policy: manual refresh + auto-refresh on session wrap-up
  (recommended), stored with `generated_at` and scene watermark.
- Length controls (short/standard/detailed) matching CF-6 detail levels.

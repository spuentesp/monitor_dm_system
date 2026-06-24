# Mode Walkthroughs (UI scripts)

> Hand-runnable versions of `tests/e2e/test_09_mode_walkthroughs.py`.
> Stack up via `./dev.sh`; frontend at http://localhost:3000.

## 1 — World Architect (T-029)

1. **Worlds** → create a multiverse, then a universe inside it.
2. **World Forge → Pack Library** → *New Pack* → name it, add an entity
   archetype ("Barnaby the Innkeeper", character) and a lore fact.
3. On the pack card choose **Apply → existing world** → pick your universe.
   The pack flips to *review pending* and proposals are created — or use
   **Canonize** to commit directly.
4. **Worlds** (or `GET /api/universes/universes/{id}/state`) → the new
   entity and fact are part of the canon. **Explorer** shows the node.

## 2 — GM Co-Pilot (T-030)

1. Create a story for the universe (start any session in **Play**, or POST
   `/api/stories` flow via session bootstrap).
2. **GM Assistant** page:
   - *Plot hooks* → 3 suggestions referencing your world.
   - *Contradictions* → scan completes (empty on a fresh world).
   - *Session prep* → recap/threads/NPC reminders payload.
   - *Handouts* → session-recap handout text.
3. **Canon review**: record a turn or create a proposal in a scene; the
   scene appears under the story's canon queue. Accept it — its status
   becomes `accepted`.

## 3 — Autonomous GM extras (T-031)

1. **Play** → new session → create/roll a character → enter the scene.
2. Ask the oracle an unknown-state question: *"Is the cellar door locked?"*
   → the GM answers with a fixed yes/no(+and/but) truth and narrates it.
3. Declare a committed attack: *"I swing my sword at the villager!"* → the
   GM rolls (or proposes a roll), reports the breakdown, and narrates the
   outcome. `/end-scene` completes the scene and advances the story.

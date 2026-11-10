# Phase 7 brief: light RP preset and the GM assistant at a table

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** The two other modes in the vision reach the same standard as the auto-GM. Light RP:
pick a character, start talking, with no setup and replies that stream. GM assistant: a human
GM runs one real session with it open and it helps more than it interrupts.

**Context.** Light RP exists as the Conversatory (`routers/character_conversation.py`,
`loops/conversation_loop.py`), with SillyTavern and Risu card and lorebook import and an
OpenAI-compatible endpoint (`routers/openai_compat.py`). In session mode that endpoint rejects
`stream=true`. NPCVoice recalls and writes memories here, which scene play did not do before
Phase 4. There is no single "light" preset: the user still chooses among modes and settings.
The GM assistant has a `/gm` page backed by `routers/gm_tools.py` and `routers/gm_notes.py`.
The rest of it (GM notes ingest, recording archive, G-6 templates, G-9 contradiction depth,
prep workflows) merged into master on 2026-11-10 as PR #137. Audio capture was descoped on
2026-11-06. That work records a live verification of its Phase A; the review found no record
of a session run at a real table.

**Depends on.** Phase 4 (cast list, NPC memory, and its cherry-picks of G-9 and G-6). Part A
and Part B are independent of each other and can go to two agents.

**You own.** Part A: `loops/conversation_loop.py`, `routers/character_conversation.py` (not
`ensure_conversatory_universe`, which is Phase 6), `routers/openai_compat.py`,
`routers/character_cards.py`, `routers/lorebook.py`, the Conversatory pages in the frontend.
Part B: `routers/gm_tools.py`, `routers/gm_notes.py`, `gm_awareness.py`, the `/gm` page.

**Do not touch.** Scene and story loops. Auth and ownership (Phase 6).

## Part A: light RP

1. **One-click start.** From a character card or any character in a universe: one action
   opens a chat with a first message. No interview, no session zero, no mode choice.
2. **Preset.** A named "light" preset: no dice, no GM verdict step, no canonization prompts,
   LIGHT or STANDARD tier by default. It is configuration over the existing loop, not a new
   loop.
3. **Streaming.** Support `stream=true` in session mode on the OpenAI-compatible endpoint and
   stream in the Conversatory UI. Memory writes happen after the stream completes.
4. **Persona.** The user's persona is in the prompt by name and description, and the cast rule
   from Phase 4 applies: the character never speaks for the user.
5. **Memory that shows.** After 30 turns across two sittings, the character recalls a detail
   from the first sitting. Add a "what this character remembers about you" view with delete.
6. **Graduate to a campaign.** From a light chat, "start a campaign with this character" hands
   the character, persona and memories to the guided start (Phase 2) in a chosen universe.
7. **Client check.** Connect one external client (SillyTavern) to the endpoint and run 20
   turns. Record what breaks.

## Part B: GM assistant

1. **Inventory.** PR #137 merged the GM assistant branch. List what the `/gm` page can do on
   master now and what in `docs/architecture/GM_ASSISTANT_MODE_PLAN.md` is still open.
2. **Prep to table.** One flow: ingest the GM's notes for a session, review what was
   extracted, and open the `/gm` page with tonight's NPCs, locations and threads ready.
3. **At the table.** The lookups a GM needs within a few seconds each: who is this NPC and
   what do they want, what do the party know, what was said last session, a name or a
   complication on demand, a rules answer with its source.
4. **After the session.** The GM types or pastes what happened; the assistant proposes canon
   changes for review and flags contradictions with existing canon (G-9).
5. **Table test.** A human GM runs one real session of at least two hours with it. Before:
   write the script of what will be tried. After: record every lookup, whether it helped, how
   long it took, and every time the GM gave up and did it by hand.
6. **Fix the top five.** From the table test, fix the five worst problems and list the rest.

## Out of scope

Audio capture and transcription. Group chats with several characters. A mobile layout. Voice.

## Done when

- A new user goes from a character card to a streamed first reply in one action.
- The 30-turn, two-sitting recall check passes and has a live transcript.
- SillyTavern completes 20 streamed turns against the endpoint.
- The table-test report exists under `docs/testing/` with the lookup log, and its top five
  problems are fixed or have a PR.

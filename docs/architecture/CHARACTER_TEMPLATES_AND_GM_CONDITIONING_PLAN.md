# Character Templates, GM Conditioning, and Narration-Start — Implementation Plan

> **Status:** proposed, grounded in live testing (2026-07-23)
> **Status (reconciled 2026-07-23):** Q1 partially addressed, Q2 not started, Q3 shipped.
> **Extends:** `docs/architecture/PLAY_AND_FORGE_DIRECTION.md` (§5, §6) — read that
> first. This doc does not repeat its reasoning, only adds what it doesn't cover
> (GM conditioning) and grounds all three questions in fresh evidence from three
> live multi-world LLM-vs-LLM sessions run this session.

## Evidence this plan is built on

Three full 8-turn LLM-GM-vs-LLM-player sessions were run against the real
production API (`POST /api/chat`, `POST /api/chat/{id}/send}` — not a mocked
harness) via `scripts/live_llm_gm_vs_player_test.py`, one turn budget each,
across three genuinely different systems with real canonized content. The
transcripts below are numbered turns 0–9: turn 0 is the real session-opening
message (`build_gm_opening`), recovered after-the-fact once an initial gap in
the test tool itself was found and fixed — see the correction note under
Question 1.

| World | universe_id | Entities | Turns | Phase split |
|---|---|---|---|---|
| Fallout 2d20 | `b492380f-9f7e-4deb-b4fd-ba51f2a91c8a` | 983 | 9/9, 0 errors | 1 opening, 6 session_zero, 2 active_play |
| Vampire: The Masquerade V20 | `7c737c26-7b84-4704-9ff6-4fc19492eac4` | 588 | 9/9, 0 errors | 1 opening, 6 session_zero, 2 active_play |
| Death in Space | `6f0d9ef2-ee5e-4e52-a1bf-e10c29f8b495` (freshly seeded) | minimal by design | 9/9, 0 errors | 1 opening, 6 session_zero, 2 active_play |

Full transcripts: `docs/testing/live_gm_vs_player/*.{json,md}`.

**The session_zero:active_play split was identical across three unrelated
systems.** That's not noise — it's a systemic property of the current flow,
not a per-system quirk, and it holds regardless of the opening's quality (see
Question 1's correction: the opening itself is good). This directly confirms
`PLAY_AND_FORGE_DIRECTION.md`'s existing diagnosis ("Session zero is an
interrogation... seven back-to-back introspective questions") is still live
today, reproduced fresh, independent of game system.

A secondary finding from the same transcripts: the VtM session's final turn
(`vampire_the_masquerade_v20_...json`, turn 9) shows
`resolution_type: propose_roll, success_level: pending` — a roll was proposed
and never resolved before the turn budget ran out. This is consistent with
(though not conclusive proof of) the direction doc's §2 finding that resolution
is keyword-gated (`resolver.py:840`) and natural narration doesn't satisfy it.
Worth a targeted look when §2 (dice fix) is scheduled.

Running this test suite is also what surfaced two real bugs, both already
fixed and merged this session:
- A cross-universe data leak in `answer_ooc_question()` (`chat_loops.py`) —
  an `OR 1=1` tautology defeated the universe scope on every OOC question,
  in every session, for every user.
- A frontend bug where dice-roll prompts silently don't render whenever the
  WebSocket isn't connected (REST fallback discarded `dice_request`).

Both are concrete demonstrations of why "run the real thing across several
worlds" surfaces bugs that a single richly-populated test world hides — the
OOC leak in particular was invisible against Fallout's 983 entities and only
showed up against the freshly-created, nearly-empty Death in Space universe.

---

## Question 1: How do narrations start?

**Answer (reconciled 2026-07-23): partially addressed. Openings: the resume-aware branch now exists, authored-module-intro is still missing. Session Zero's length problem is mitigated mechanically (adaptive questions, early stop, persona-seeded budgets) but still reproduced live for a brand-new character — the 6:2 evidence in this doc still stands.**

Current state, confirmed by reading `narrator.py` and `chat_opening.py` directly,
*and* by re-checking the live test transcripts after fixing a gap in the test
tool itself (see "Correction" below):

- `build_gm_opening()` (`chat_opening.py`) already runs on every new
  `mode="play"` session and already produces exactly what §5 asks for in the
  cold-open case: a single, atmospheric, in-fiction paragraph pulling real
  axioms/facts/locations from the universe, ending on one in-world question
  -- never a form or list. Confirmed live: all three test worlds got a real,
  well-written, hook-ending opening (e.g. Fallout's referenced an actual
  canonized location, "Novac," entity-linked in the message markup).
- Of the other two branches §5 names: the **resume-aware** opening branch
  now EXISTS (`chat_opening.py:136-156`, via `RecapAgent.generate_recap`,
  tested in `packages/ui/backend/tests/test_build_gm_opening_resume.py`); the
  **authored-module-intro** branch (verbatim, if the ingested source has
  one) is still missing (`chat_opening.py:131-134`).
- The bigger, confirmed-live friction is NOT the opening's quality -- it's
  Session Zero's length. This is now mitigated mechanically: questions are
  LLM-generated adaptively one at a time
  (`packages/agents/src/monitor_agents/loops/session_zero_loop.py:106`), stop
  signals end it early (`:159-163`), and returning-persona `seed_answers`
  shrink the budget to as few as 2 (`:333-343`, wired at
  `chat_loops.py:966-981`). BUT the 2026-07-23 live evidence in this doc
  (6:2 session_zero:active_play split across 3 systems) still stands as
  observed behavior -- a brand-new character with no persona/premise still
  faces up to 7 questions + CAMPAIGN_INTENT (`session_zero_loop.py:42,47-52`).

### Correction (found after initial drafting of this plan)

The first version of this document, and the test tool
(`scripts/live_llm_gm_vs_player_test.py`) it was built on, both missed the
actual opening message: `POST /api/chat` generates it server-side via
`build_gm_opening`, but the endpoint's response only returns `Session`
fields, not the messages it also stores. The test script's turn loop
started by sending a player line as if no opening had happened, so every
transcript's "turn 1" was really the *second* GM message in the true
conversation, and the original draft of this section significantly
overstated the gap (implying no warm opening existed at all). Both the
script and the three existing transcripts have been corrected to include
the true opening as turn 0.

**Recommendation, revised:** implement only the remaining missing §5 branch
(authored-module-intro) as a conditional path *before*
`build_gm_opening`'s existing generate-fresh behavior, which needs no
changes — the resume-aware branch has since shipped (see the answer above).
This is a smaller change than originally scoped.

## Question 2: Character templates ("that character player also needs to be persisted as a template")

**Answer (reconciled 2026-07-23): still NOT STARTED — there is no `CharacterTemplate` schema. The analysis below of adjacent existing pieces (`EntityTemplate` in `entity_templates.py` for NPC generation, `NPCProfileCreate`, `CharacterSheetCreate`, `ExtractedCharacterProfile`; persona only as session `persona_id`) still stands. Partial progress toward the template vision shipped 2026-07-23: the persona→Session Zero `seed_answers` bridge (`chat_loops.py:966-981`, `session_zero_loop.py:333-343`), via branch `worktree-persona-template-bridge`.**

The original assessment of the adjacent pieces, still accurate as analysis:

This is the single most important finding of this investigation. Two
character concepts already coexist in the codebase, unconnected:

1. **In-fiction PC** — built conversationally via `session_zero.py` +
   `CharacterCreationLoop`, persisted as a `CharacterSheet`
   (`packages/data-layer/.../character_sheets.py`) bound to a specific
   `entity_id` in a specific universe, fully mechanical (`stats`, `resources`,
   `skills`, `class_levels`, `equipment`). This is what `monitor play` and
   the chat API build today. Zero portability — one PC, one world, gone if
   you start a new story.

2. **Standalone character** — `POST /api/characters` ("no universe
   required"), schema `CharacterCreate` (`entities_schemas.py:209`):
   `name, description, avatar_url, personality, gm_notes, first_message`.
   **No stats. No world binding. No system association.** This is *exactly*
   the `CharacterTemplate` shape §6 of the direction doc calls for, field for
   field. It already has import/export via **`chara_card_v2`** — the real,
   established SillyTavern/Character.AI portable character-card format — so
   portability *outside* MONITOR is already solved too.

The catch: standalone characters exist today for a **different purpose** —
NPC/companion persona chat (`character_conversation.py`,
`CharacterEditor.tsx`), not "start a new story as this persona." The frontend
agent's audit confirmed zero code path connects the two: a full grep for
`session_zero`/`char_creation_complete`/`saved_character` inside the frontend
returns nothing outside phase-label strings.

**Recommendation — do not design a new schema.** Build the instantiation
step §6 already names:

1. When starting a new story, offer "play as an existing persona" alongside
   "create new," listing the player's saved standalone characters.
2. On selection, feed the persona's `description`/`personality`/
   `first_message`/`gm_notes` into `CharacterCreationLoop` as **pre-filled
   answers**, not a blank slate — this is the same mechanism Session Zero
   already uses to synthesize a character from free-text answers (see the
   live transcripts: 6-7 free-text answers → a full concept/backstory/bonds/
   fears/motivations synthesis already happens today). A saved persona
   *already contains* that information; Session Zero should detect it and
   skip straight to system-specific stat mapping.
3. Persist the resulting world-bound `CharacterSheet` with a back-reference
   to the source standalone-character `id`, so returning to the same persona
   in a *different* world re-instantiates from the same template rather than
   re-interviewing from scratch.

This single change also meaningfully improves the 6:2 turn-budget problem
for any returning player — the second time someone plays "Rook the
scavenger," there should be no 6-question interview at all.

---

## Question 3: Conditioning / "leading" the GM toward a kind of story

**Answer (reconciled 2026-07-23): SHIPPED 2026-07-23. The gap analysis below was accurate when written; both halves of the fix are now in — the `CAMPAIGN_INTENT` Session Zero pre-question (`session_zero_loop.py:47-52`, asked only when no `story_premise` was set at creation — `chat_loops.py:985`) and the `StoryLoop`→`SceneLoop` `story_state` threading (was dead code; wired 2026-07-23 per git history). See "Implementation status" under Suggested sequencing for the full account.**

The gap as originally confirmed by direct inspection, not inference:
- `SessionCreate` (`chat_schemas.py:15`) has `tone: str = "dramatic"` (a mood
  enum: dramatic/grim/horror/heroic/mystery/adventure) and `gm_profile_id`
  (a GM *personality*/voice selector). Neither carries plot, genre, or
  premise information — they shape *how* the GM talks, not *what story* it
  tells.
- `QuestionCategory` (`session_zero.py:76`) — the fixed set of things Session
  Zero can ask about — is entirely character-focused: name, origin, bond,
  fear, motivation, conflict, secret, loss, appearance, skill, faith,
  relationship. There is no category for "what kind of story do you want,"
  "what should this campaign be about," or "what do you want to avoid."
- `generate_opening` does accept a raw `user_input` string, so there is a
  low-level hook a player's free-text opening message *could* flow through —
  but Session Zero's fixed 7-question loop is what actually runs first, and
  per the direction doc's own diagnosed symptom ("GM answers a rich player
  intro with *another question* instead of advancing fiction"), a player's
  stated creative intent today gets steamrolled by the interview rather than
  shaping it.

**This needs new design, not just implementation of an existing plan.**
Proposed shape, minimal and consistent with the rest of the system's
conventions:

1. **A structured field, not just freeform prose in the tone slot.** Add
   `story_premise: str | None` to `SessionCreate` (parallel to how `tone`
   already works) — a short player-authored pitch ("heist against a rival
   Prince," "survival horror, no combat, focus on isolation," "political
   intrigue, low violence"). Optional; omitting it should behave exactly as
   today.
2. **Thread it through `generate_opening` and Session Zero.** `user_input`
   already reaches `generate_opening` — extend that call to also receive
   `story_premise` and have the prompt treat it as a hard steering
   constraint on the opening scene's content, not just its mood.
3. **A `CAMPAIGN_INTENT` (or similarly named) Session Zero category** —
   optionally, ask *one* question up front ("What kind of story pulls you
   in tonight?") before the character-focused categories, and feed the
   answer into the same `story_premise` slot if the player didn't set one
   at session creation. This reuses the exact mechanism Session Zero
   already has (`QuestionCategory` enum + the same synthesis step) rather
   than inventing a parallel system.
4. **Carry it forward per-scene, not just at session start.** `StoryLoop`
   already threads `story_state`/`arc_label` across scenes (per §5) — the
   premise should live there too, so a mid-campaign "steer this more toward
   X" isn't a one-time setup step but something `StoryLoop.start_or_resume`
   can pick up and hand to the Narrator on every scene transition.

This is the smallest of the three gaps to close (one new optional field,
one new prompt input, one optional new Session Zero category), but it's
the one with no existing plan to build on — everything above is a new
proposal, not an implementation of already-decided direction.

---

## Suggested sequencing

**Status update (reconciled 2026-07-23):** item 1 is **partially done**
(resume-aware opening shipped — `chat_opening.py:136-156`; authored-module-intro
still missing — `chat_opening.py:131-134`; Session Zero length mitigated
mechanically but still reproduced live for new characters), item 2 is **not
started** as a template system (no `CharacterTemplate` schema; the
persona→Session Zero `seed_answers` bridge shipped 2026-07-23 via branch
`worktree-persona-template-bridge` as partial progress), item 3 is **done**
(all four design sub-items, including the `StoryLoop`→`SceneLoop`
per-scene threading that initially looked blocked on a deeper gap; that gap
is now fixed too, see "Implementation status" below).
Item 4 (dice/resolution fix) turned out to already be shipped by earlier,
unrelated work — see `PLAY_AND_FORGE_DIRECTION.md`'s own status update.
See "Implementation status" below for what each item actually covers and,
more importantly, what it deliberately doesn't.

The direction doc's own sequencing (dice fix → Forge/Play split → openings →
personas) predates this session's findings. Given what's now confirmed live:

1. **Story-aware openings (§5)** — small, already-scoped, and the mechanism
   (`generate_opening`) already exists. Directly attacks the 6:2 turn-budget
   problem observed in all three live tests.
2. **Persona-template instantiation (§6, this doc's Q2)** — the schema and
   portability already exist; this is a bridge, not new data-layer work.
   Also attacks the turn-budget problem for returning players.
3. **Story-premise conditioning (this doc's Q3)** — new design, small
   surface area, depends on nothing from #1/#2 but is most useful once
   openings are hook-first (#1) so a stated premise has an opening to shape.
4. **Dice/resolution fix (§2 of the direction doc)** — unchanged priority
   from the original doc; the live VtM pending-roll finding is a fresh data
   point supporting it, not a new problem. **Already shipped by earlier,
   unrelated work** — see the status update above.

Items 1–3 are all additive, backward-compatible (every new field is
optional, every new behavior falls back to today's behavior when unset),
and none require the Forge/Play UI split to land first.

### Implementation status

1. **Story-aware openings** — resume-aware branch shipped: `is_resume` +
   `RecapAgent` synthesize "the story so far" when a session resumes an
   existing story with real prior content (completed scenes, populated
   outline beats, or significant facts); falls back to a fresh cold open
   otherwise. The authored-module-intro branch is still not implemented (no
   schema field for it exists yet — separate, larger work).
2. **Persona-template instantiation** — `persona_id` on `SessionCreate`
   pre-seeds Session Zero from a saved standalone character (shrinks the
   question budget, `gm_notes` deliberately excluded from player-facing
   seeding) and the resulting `CharacterSheet` keeps `source_persona_id` as
   a back-reference. Live-verified through a full mechanical
   character-creation flow, not just the narrative-only fallback.
3. **Story-premise conditioning** — `story_premise` on `SessionCreate`
   threads into `Narrator`'s `setting_anchor` (the same hard-constraint
   channel that already locks genre/setting) and forces the LLM opening
   path even on lore-free ground. `CAMPAIGN_INTENT` — a Session Zero
   pre-question asked once, up front, only when `story_premise` wasn't
   already set at creation — is also shipped: `SessionZeroLoop` asks it as
   question 0 (outside the character-question budget, not recorded into
   the answers that feed backstory synthesis) and `chat_loops.py`
   backfills `session["story_premise"]` from the answer. Live-verified:
   question_number=0/category=campaign_intent when unset, skipped straight
   to question_number=1 when a premise was already provided, and the
   backfill lands on the session correctly either way.

   **`StoryLoop` carrying it forward per-scene — shipped, after finding a
   deeper gap than expected.** Investigated before implementing: `StoryState`
   (the model `arc_label`/`tension_score`/`active_threads` already live on,
   and where `story_premise` needed to sit alongside them) is tracked by
   `StoryLoop.start_or_resume`/`advance`, but `SceneLoop` — the class that
   actually runs every live turn, on both the web backend
   (`chat_loops.py`'s `get_scene_loop`) and the CLI
   (`monitor_cli/commands/play.py`) — never received a `story_state` at
   all. Its constructor parameter defaulted to `None` and neither real
   call site passed one, so the `if story_state:` branch inside
   `Narrator._generate_narrative_and_proposals` that injects
   `arc_label`/`tension_score`/`active_threads` into `setting_anchor` was
   dead code for actual play, for every field it already had, not just a
   new one being added. Confirmed by reading both construction sites
   directly, not by assumption.

   Fixed the actual gap rather than adding `story_premise` next to fields
   that were equally unreachable: `StoryState` gained `story_premise`;
   `chat_loops.py` gained `_build_story_state_dict()` (merges
   `session["story_premise"]` with whatever the last `StoryLoop`
   advancement cached) and now actually passes it to `SceneLoop`; the CLI
   already had a real `story_state` dict in scope the whole time
   (`start_or_resume()`'s own return value) and just needed the one-line
   pass-through. This restores the arc/tension/thread injection for real
   play on both surfaces for the first time, not just `story_premise`.

   Live-verified: a session with a distinctive premise ("prison break from
   an NCR labor camp — tense, quiet, no gunfights") carried it through
   three full active-play turns after the opening — turn 3 spontaneously
   developed "three checkpoints... perimeter fence... razor wire, motion
   sensors" fully consistent with the premise, with no re-statement of it
   in the player's own input. Full suite green (2739 passed) after the
   change.

   All four of Q3's design items are now shipped. The plan's own "open
   questions" section below still has one live item: whether `StoryLoop`
   should support changing the premise mid-campaign as a player-invokable
   command — that's a new interaction, not a wiring gap, and is
   deliberately left open rather than guessed at.

A secondary, real bug surfaced by playing through this work live (not part
of the original three questions): the resolver's schema-free fallback
(no game system bound to the universe) hardcoded `("action", "Strength",
12)` for every action regardless of content — a stealth action got a
Strength check. Fixed with the same semantic-routing approach the
schema-bound path already used, against six generic abilities.

## Open questions for the user

Settled by the 2026-07-23 work and removed from this list: the Q2
skip-vs-abbreviate question (shipped behavior runs an abbreviated version —
persona `seed_answers` shrink the budget to as few as 2 questions,
`session_zero_loop.py:333-343`) and the sequencing question (items 1–3 are
done or partially done per the status update above; item 4 was already
shipped by earlier work).

- Q3: is `story_premise` a session-level setting only, or should
  `StoryLoop` support changing it mid-campaign as a player-invokable command
  (mirroring the existing `/flashback` CLI command's pattern)?

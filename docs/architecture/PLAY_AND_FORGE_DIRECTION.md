# Play & Forge — Product Direction

> **Status:** partially implemented (rev. 2 — + dice experience). Per-section
> status markers below were verified by direct code inspection on 2026-07-23.
> **Scope:** How MONITOR should *feel* to use — mode-first play, a clean split
> between authoring and playing, story-aware openings, and portable character
> templates. Sets direction across agents + web UI; individual slices get their
> own implementation plans.

## Context

The narration *generation* is genuinely good. In the latest LLM playtest
(`tests/e2e/logs/live_gameplay_llm_run01_20260629T231745Z.md`) the prose is
atmospheric and shippable (~590 chars/turn avg). The problem is **friction**,
not prose quality:

- **Session zero is an interrogation.** Seven back-to-back introspective
  questions before play starts. That log shows `question_marks_from_gm: 11`
  and a mostly-`pending` success sequence — the GM answers a rich player intro
  with *another question* instead of advancing fiction.
- **Dice ceremony** is always present in game modes, even for trivial turns.
- **World drift** — the opening scene (a dockside bar) silently teleported to
  the player's backstory location on turn 1.
- **Setup is heavy**, and authoring is tangled into the play surface.

The reference products the team likes (character.ai, Character Tavern / the
SillyTavern ecosystem, Emochi, Hoshi) win on *ease*: tap-and-play, warm single
openings, optional choice chips, dice hidden unless they matter, and a clean
separation between "make a world/character" and "play with it."

## Guiding insight

`play_mode == "narrative"` **already** short-circuits the whole GMAwareness
classifier (`gm_awareness.py:783-784`) — it accepts declared outcomes and never
rolls dice. The brittle narration keyword/regex heuristic
(`narration_heuristic.py`) only runs in *dice* modes (line 799, after the
narrative check). So the platforms-style freeform experience the team wants
**does not depend on that heuristic at all**. Mode separation dissolves most of
the classification-brittleness concern rather than requiring a smarter matcher.

## Direction

### 1. Mode-first play (default = freeform, dice opt-in)

> **Status (verified 2026-07-23): partially shipped** — the web UI defaults to
> narrative/freeform with a prominent two-button "Play style" selector
> (`packages/ui/frontend/src/components/play/SetupPanel.tsx:67-68, 238-243`),
> but the backend session-create schemas still default
> `play_mode='dice_game_system'`
> (`packages/ui/backend/src/monitor_ui/routers/chat_schemas.py:63, 115`) and
> the CLI still defaults to dice mode with narrative only via `/godmode`
> (`packages/cli/src/monitor_cli/commands/play.py:53-54, 286-296`).

- **Freeform / narrative mode is the default front door.** No dice, no roll
  classification — like the reference platforms. This is already the behavior
  of `play_mode == "narrative"`; the work is making it the default and the
  primary UI, not a hidden `/godmode` toggle.
- **Game mode** keeps dice, but they surface **only when consequential.**
  GMAwareness already tags `roll_necessity: trivial | propose_roll | contested`
  (`gm_awareness.py`). Render the dice UI only on `propose_roll`/`contested`;
  resolve `trivial` silently.
- **Do not extend the narration heuristic.** Keep it committed
  (branch `narration-heuristic-wip`) as saved state, but freeze Phase B/C.
  Literal keyword matching is brittle; mode separation makes it low-stakes
  (dice mode only, where a false-negative just costs one LLM call). If dice-mode
  intent detection ever needs improvement, prefer embedding similarity or a
  better DSPy signature over a bigger deny-list.

### 2. Dice experience (tabletop imitation)

> **Status update (2026-07-23): this entire section is shipped.** Verified by
> direct code inspection and live testing against the real chat API, not
> inference from the diff alone:
> - `resolver.py`'s own comments today explicitly document the keyword gate's
>   removal ("We deliberately do NOT gate the narrative behind a magic
>   keyword... That keyword parser was brittle and produced a stuck-`pending`
>   loop"). `DiceRollPrompt.tsx`'s tap-to-roll path calls `onServerRoll`
>   (server-authoritative); client `Math.random()` survives only as a
>   documented "Legacy fallback" for the separate manual-entry path.
> - Live-verified today: a `propose_roll` tapped via the structured
>   `[ROLL REQUEST]` action resolved server-side in one beat
>   (`1d20(13) + -5 = 8 vs DC 12`, woven into narration). A *second* live
>   test sent a plain narrative message while a roll was still pending, with
>   no roll/dice keyword in it at all — the pending roll auto-resolved and
>   was woven into the response with no pushback nag, exactly matching
>   "never block on a pending roll" below.
> - Sessions already carry a real `roll_model` field (`"tap"` confirmed live;
>   `"manual"`/`"gm"` are wired in `DiceRollPrompt.tsx`'s props), matching
>   "roll model is a per-session setting."
> - The playtest logs' stuck-`pending` symptom that motivated this section
>   was re-examined directly: a fresh VtM live-test transcript
>   (`docs/testing/live_gm_vs_player/vampire_the_masquerade_v20_20260723_011344.md`,
>   run well after this section's "decisions locked 2026-07-13" date) ends
>   its fixed 9-turn budget exactly on a `propose_roll` — the automated
>   player script simply ran out of turns before tapping the die, not a
>   resolver bug. No reproduction of an actual stuck loop was found against
>   current code.
>
> Left as a **separate, unrelated finding** from that same transcript (not
> part of this section, tracked instead under
> `CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md`): the same final turn's
> `stat: Strength` for what reads as an intimidation/composure moment, not a
> physical one, is the same schema-free-fallback bug already fixed there
> (`resolver.py`'s `_infer_generic_stat`) -- that VtM universe very likely
> also had no bound game system, the same condition that produced the
> original Fallout finding.

We want **both** experiences: simple narrative (no dice) *and* a faithful
tabletop imitation. Dice are critical to the second, and were broken as of
this section's original drafting. Three concrete breakages in the flow
*at that time*:

1. **Keyword-gated resolution.** A proposed roll can only be resolved by typing
   a magic word — `resolver.py:840` matches `\b(roll|dice|d20|/roll)\b`. Natural
   narration triggers `forced_narrative_pushback` ("Roll the dice before
   continuing"). This is the source of the stuck-`pending` loop in the playtest
   logs, and it's the same brittle keyword-matching we reject everywhere else.
2. **Two-turn ceremony.** propose_roll → player types "roll" → result. Should be
   one beat, like a GM saying "give me a FIN check" and you roll immediately.
3. **Cosmetic, non-authoritative dice.** `DiceRollPrompt.tsx` rolls client-side
   with `Math.random()` and shows the player a number; the server then rolls its
   *own* dice at `resolver.py:1002` and uses that instead. The player-facing roll
   is discarded and isn't authoritative anyway.

**Target design (decisions locked 2026-07-13):**

- **Server-authoritative rolls.** The roll happens on the server and is the
  single source of truth (reproducible, not client-cheatable). Replace the
  client `Math.random()` outcome with a structured roll action the server
  resolves.
- **Structured roll affordance, one beat.** `propose_roll` renders a real
  "Roll FIN (DC 10)" control; activating it sends a typed `roll` action (not
  free text) that resolves in place. Retire the keyword gate and the
  `forced_narrative_pushback`-by-keyword path.
- **Roll model is a per-session setting** the player picks at session start:
  - *Tap-to-roll (default)* — player taps a die; server rolls authoritatively
    and reveals it with animation.
  - *Full manual* — player rolls/enters their own value; server validates the
    formula. Max tabletop feel (accepts it's not fully authoritative).
  - *GM auto-rolls* — system rolls silently and weaves the result into
    narration (`auto_roll` already exists).
- **Never block on a pending roll.** If the player narrates instead of rolling,
  the system **auto-rolls behind the scenes and weaves the outcome** into the GM
  response — no pushback nag. (Applies to tap-to-roll and manual; GM-auto never
  has a pending roll.)
- **Dice only when they matter.** Surface the roll UI on `roll_necessity`
  propose_roll/contested; resolve `trivial` silently.
- **Fix pending-roll threading** (`scene_loop.py:340-360` ↔ `resolver.py:838`)
  so a proposed roll can't silently re-propose across turns.
- **Explicit roll semantics per game system.** `_uses_roll_under` already
  supports both roll-under and roll-over; make the mode explicit in the
  game-system config and show it in the dice UI.

Files: `resolver.py` (resolve_turn pending/propose/contested branches,
~537-1050), `loops/scene_loop.py` (pending-roll machine + resolve node),
`ui/backend/.../chat_loops.py` (structured roll action), `DiceRollPrompt.tsx` +
`DiceResultCard.tsx` (affordance; drop client `Math.random` authority),
`monitor_data/utils/dice.py` (server roll).

### 3. Suggested-action chips

> **Status (verified 2026-07-23): shipped** — `suggested_actions` is a Narrator
> signature output (`packages/agents/src/monitor_agents/narrator/narrator.py:161`),
> carried and populated in scene-loop state
> (`packages/agents/src/monitor_agents/loops/scene_loop.py:181, 432`), and
> rendered as chips in the web composer
> (`packages/ui/frontend/src/components/play/PlayConsole.tsx:347-356`).

Add a `suggested_actions` output field to the Narrator signature
(`packages/agents/src/monitor_agents/narrator/narrator.py`) and render 2–3
dismissable chips in the web Composer (`packages/ui/frontend/src/features/chat/`).
Optional, never rails — blank-page relief, mirroring Emochi's choice affordance.

### 4. Forge vs Play — separate authoring from playing

> **Status (verified 2026-07-23): shipped** as route groups. `/forge` has a hub
> + ingestion, `/forge/apply`, `/forge/editor`, and `/forge/review`
> (`packages/ui/frontend/src/app/forge/`); the `ProposedChange` review UI
> accepts/rejects/commits to canon (`/forge/review/page.tsx` wired via `api.ts`
> to the `pack_library.py` endpoints), and universes are creatable from the
> `/worlds` page. The separate-deployables decision remains open.

Two surfaces sharing one API:

- **Forge / Studio** (write-heavy): create, ingest, and *modify* worlds,
  lorebooks, entities, tone; review canon via `ProposedChange` / CanonKeeper.
- **Play** (read-mostly): pick a world, play, get assisted.

Mirrors how character.ai and SillyTavern split card/lorebook editing from chat,
and aligns with the layer architecture. The backend already has the seam
(`gm_tools`, `tone`, `chat_*` routers under `packages/ui/backend`). Start as two
route-groups in the existing Next.js app (`/forge` vs `/play`) before deciding
whether they become separate deployables.

### 5. Story/module-aware openings

> **Status (verified 2026-07-23): partially shipped** — the resume-aware opening
> exists: when `is_resume` and `story_id`, `build_gm_opening` calls
> `RecapAgent.generate_recap()`
> (`packages/ui/backend/src/monitor_ui/routers/chat_opening.py:136-156`, tested
> in `packages/ui/backend/tests/test_build_gm_opening_resume.py`). The authored-module-intro branch
> is NOT implemented — `chat_opening.py:131-134`'s docstring states no
> KnowledgePack schema field exists for it.

`Narrator.generate_opening` already accepts `story_state` and uses `arc_label`
(`narrator.py:178,276`). Formalize the rule:

- Story/module **in progress** → resume-aware opening.
- Authored module **has an intro** → use it (largely verbatim).
- Otherwise → generate.

Warm, single-paragraph opening ending on a hook — never a questionnaire.

### 6. Persona = character *template*, instantiated per world

> **Status (verified 2026-07-23): not started** — no `CharacterTemplate`/
> `Persona` schema exists. The adjacent `EntityTemplate`
> (`packages/data-layer/src/monitor_data/schemas/entity_templates.py`) is
> NPC-generation blueprints, not portable player personas; "Persona" exists
> only as a session `persona_id` field.

No `Persona`/`CharacterTemplate` schema exists today (greenfield).

- **`CharacterTemplate`** — portable, **system-agnostic** core: concept,
  personality, backstory beats, voice, portrait. **No stats, no world bindings,
  no system associations.**
- **Instantiation** binds a template to a world, producing a world-scoped
  `Character` that maps traits onto *that world's* game system
  (stats/skills/conditions) and canon.

The template deliberately holds no multi-system associations — the instantiation
step is the only place system-specific data attaches. This is what lets one
persona travel across worlds without coupling to any one system.

## Suggested sequencing

1. **Tabletop dice fix + mode-first play** — freeform default, structured
   server-authoritative rolls, dice-when-important, per-session roll model,
   auto-roll-and-weave, chips. Highest impact on "feels easy"; the user flagged
   dice as critical. Touches resolver, scene_loop, chat_loops, Narrator
   signature, and web chat/dice components.
   **Status (verified 2026-07-23): dice experience, structured rolls, and
   suggested-action chips shipped; mode-first play partially shipped** (web UI
   defaults to freeform, but the backend session-create defaults and the CLI
   still default to dice mode — those defaults remain to flip).
2. **Forge/Play UI split** — structural; unblocks authoring UX and future work.
   **Status (verified 2026-07-23): done** — `/forge` route groups shipped
   (hub/ingestion, apply, editor, ProposedChange review); the separate-deployables
   decision is still open.
3. **Story/module-aware openings** — small, builds on existing `generate_opening`.
   **Status (verified 2026-07-23): partially done** — resume-aware openings
   shipped; the authored-module-intro branch remains (needs a KnowledgePack
   schema field).
4. **Persona templates** — self-contained data-layer + instantiation + light UI.
   **Status (verified 2026-07-23): not started.**

## Open questions

- Forge/Play: the two route-groups now exist — is that enough, or commit to two
  deployables?
- Do suggested chips also appear in game mode, or freeform only?
- Persona templates: net-new schema, or extend the existing character-entity
  model with a `is_template` facet?

Settled by shipped work (verified 2026-07-23):

- *Default mode for brand-new players* — answered by the shipped web setup: a
  prominent two-button "Play style" selector defaulting to narrative/freeform.
  (Flipping the backend session-create and CLI defaults to match is remaining
  implementation work, not an open design question.)

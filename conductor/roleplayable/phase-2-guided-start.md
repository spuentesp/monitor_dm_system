# Phase 2 brief: the guided start

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** A new player picks a world and is led by the auto-GM from first question to first
scene: a short series of questions, two to four concrete suggestions for how to begin that
come from this world, a character, and an opening scene that has a place, people present and
something at stake.

**Context.** Pre-play already runs as a LangGraph flow: setting intro, character interview
(max 4 questions, seeded by a persona), character creation for game-system worlds, story
agreements, then a generated prologue. What it lacks is grounding. The one campaign question
lists the same genres for every world, nothing suggests a way in, and the opening has no
location, NPCs or plot threads behind it. Applying an ingested pack creates a universe and
proposals and no starting situation.

**You own.** In `packages/agents/src/monitor_agents/`: `loops/preplay_orchestrator.py`,
`loops/preplay_support.py`, `loops/preplay_finalize.py`, `loops/preplay_phases.py`,
`loops/session_zero_loop.py`, `loops/character_interview_loop.py`,
`loops/session_bootstrap.py`, `session_zero.py`, `setting_intro.py`, `quick_world/`, and a new
`world_seed/`. In `packages/ui/backend/src/monitor_ui/routers/`: `chat_opening.py` and the
pre-play parts of `chat_loops.py`. In the frontend: `SetupPanel.tsx` and the pre-play parts of
`PlayConsole.tsx`.

**Do not touch.** `story_loop.py`, `story/agent.py`, `context_assembly/` (Phase 3).
`narrator/`, `extraction/`, `npc_voice/`, `turn_context.py` (Phase 4).

## Tasks

1. **World seed.** New agent `WorldSeed` that, given a universe, returns a starting situation:
   2–4 start options, each with a location, 2–4 named NPCs present, a hook, and a suggested
   role for the player. Build options from what the universe holds (entities, lore facts,
   agendas, plot threads, pack `character_profiles` and `topologies`). When the universe is
   sparse, generate and mark the result as generated. Reuse the Quick World signature rather
   than writing a second generator.
2. **Start suggestions in the flow.** Replace the fixed `CAMPAIGN_INTENT_QUESTION` with a
   model-written question that presents the seed's start options by name and still accepts a
   free answer or "surprise me". Return the options as structured data so the UI can show them
   as chips, the same way suggested actions work in play.
3. **Question series.** Keep the cap at 4. Order the questions: how to start, who you are,
   what you want, one adaptive follow-up. A persona or a rich first message still shortens it.
   Each question may carry 2–3 suggested answers.
4. **Materialize the chosen start.** When pre-play finishes, turn the chosen option into
   state: the location and NPCs as entity instances (not archetypes) with NPC profiles and
   agendas, 2–3 plot threads, the PC placed at the location, all through CanonKeeper as
   proposals accepted for the opening. Extend `bootstrap_story_scene`; it already creates plot
   threads.
5. **Opening scene.** Make the first GM message narrate that situation: where the PC is, who
   is there, what is happening, and end on a prompt to act. Keep the existing precedence:
   authored module intro first, resume recap second, generated opening third.
6. **Pack apply path.** After `POST /packs/{id}/apply/new-world`, offer "prepare a starting
   situation", which runs the seed against the new universe, so an ingested book yields
   somewhere to stand. Also commit pack `agendas` and `plot_threads`; CanonKeeper's
   `_COMMIT_ORDER` skips them today.
7. **Skip path.** "Skip to play" must still produce a seeded opening, picking the first option.
8. **Resume.** Pre-play checkpoints must survive a backend restart at every step, including
   after the start is chosen and before the opening is written.

## Out of scope

Character template portability (on `gm_assist_overhaul`; Phase 4 brings it). Book
decomposition. Event chronology extraction.

## Done when

- On a fresh universe from Quick World, and on one from an applied pack, a scripted player
  reaches active play in at most 5 GM turns.
- The opening names a location and at least two NPCs that exist as instances in Neo4j with
  profiles in MongoDB.
- At least two plot threads exist for the story.
- The start options shown differ between two different worlds.
- Killing the backend mid-flow and resuming continues from the same question.
- This is an e2e walkthrough beside `tests/e2e/test_09_mode_walkthroughs.py`, with one live
  LLM-vs-LLM transcript per world under `docs/testing/`.

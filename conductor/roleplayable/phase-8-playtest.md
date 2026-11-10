# Phase 8 brief: the playtest

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** Apply the test for done: a person who did not write the code plays a real campaign
over several days, and what breaks gets found, ranked and fixed. Nothing before this phase
proves the system is roleplayable; scripted tests and single transcripts only prove the parts.

**Context.** Every earlier phase ends on automated checks and one live transcript. The repo
has LLM-vs-LLM harnesses (`scripts/live_llm_gm_vs_player_test.py`,
`scripts/coherence_playtest.py`, `scripts/eval_gm_playtest.py`, `docs/testing/REPLAYS.md`) and
no record of a multi-day campaign played by a person.

**Depends on.** Phases 0 to 4. Run it again after Phase 5 on a book-derived world.

**Needs a person.** The player. An agent prepares, observes and fixes; it cannot be the
player. The player should not be the author if one is available.

**You own.** A new `docs/testing/PLAYTEST_PROTOCOL.md`, playtest reports under
`docs/testing/`, the harness scripts named above, and bug-fix PRs in whichever files the
defects are in (follow that file's owning phase rules and say so in the PR).

## Tasks

1. **Protocol.** Write `PLAYTEST_PROTOCOL.md`: setup, what the player does on each day, what
   to note, and the pass criteria below. Keep it to one page the player will read.
2. **Dry run with a model player.** Before taking a person's time, run the full protocol with
   the LLM-vs-LLM harness: guided start, five scenes, a backend restart between sittings.
   Fix whatever stops it completing.
3. **Instrument.** For each turn record latency, model calls, tokens, errors captured by
   `RoleplayErrorRecorder`, and whether the agenda tick, ledger write, arc evaluation and NPC
   memory writes ran. The player should not have to report what a log can.
4. **The run.** Three sittings on three different days, five scenes or more in total, two
   user-controlled characters in at least one scene, one deliberate callback by the player to
   an early event, one backtrack, one stop mid-scene and resume the next day.
5. **Collect.** After each sitting: the player's notes (what felt wrong, in their words), the
   transcript, the instrumented log. Do not prompt the player toward the pass criteria.
6. **Triage.** Group defects: broke play, broke continuity, wrong about who is who, NPC out of
   character or knowing too much, slow, cosmetic. Rank by how often and how badly.
7. **Fix and repeat.** Fix everything in the first three groups, then run a second playtest
   with a fresh campaign. Report both.

## Pass criteria

- The player reaches active play in at most 5 GM turns from picking the world.
- No turn narrates actions, speech or feelings for a user-controlled character.
- In scene five or later, an NPC brings up, unprompted and correctly, something the player
  did in scene two.
- No NPC reveals something it could not know.
- In-game time moves forward and the GM refers to it correctly at least once.
- After each restart and each overnight gap, play resumes with nothing lost and a recap the
  player judges accurate.
- The story reaches an ending, or the player can say where it is in its arc and the system
  agrees.
- The player wants to play another session.

## Out of scope

Balance and game-system correctness beyond what blocks play. Load testing. More than one
player at once.

## Done when

Two playtest reports exist, the second passes every criterion, and every defect from the
first is fixed, has a PR, or is listed with a reason it was left.

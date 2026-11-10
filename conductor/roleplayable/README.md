# Roleplayable Plan — nine phases for independent agents

> **Status:** proposed, 2026-11-09. Based on a code review of `origin/master` at `b082664`.
> File paths and line numbers were read on that date; verify them before relying on them.
> `conductor/plan.md` is an older, completed plan and is unrelated.

## Target experience

The auto-GM asks a short series of questions, offers concrete suggestions for how to begin,
the player makes a character, and the campaign carries on from there across sessions. The GM
always knows which characters the user controls.

| Step | Target | On master today |
|---|---|---|
| 1. Setting intro | The GM introduces the world from its own canon | Works (`assemble_session_intro`) |
| 2. Campaign questions | A few questions about the story the player wants | One fixed question (`CAMPAIGN_INTENT_QUESTION`) with generic genres, then up to 4 interview questions |
| 3. Start suggestions | 2–4 concrete ways to begin, drawn from this world | Missing |
| 4. Character | Create one, or pick a persona | Works; portable templates are on an unmerged branch |
| 5. Table agreements | Lines and veils | Works |
| 6. Opening scene | Where, who is there, what is at stake | Partial: a prologue, with no location, NPCs or plot threads behind it |
| 7. Campaign continues | Scenes follow one another; the story remembers | Broken above the scene |
| 8. Who is who | The GM knows every user-controlled character and the speaker | Partial: the session stores the list; only the speaker reaches the turn |

## Findings the phases rest on

- **A story cannot end.** `StoryAgent.evaluate_arc` seeds two hardcoded threads and nothing
  closes a thread. PR #136 fixes it and is unmerged.
- **The NPC agenda tick never runs.** `loops/story_loop.py` (~line 480) calls
  `self.call_tool(...)`; `StoryLoop` has no such method and a blanket `except` hides it.
- **Thin cross-scene continuity.** A new scene gets zero turns, a recap of only the previous
  scene cut to 120 characters (`_opening_recap_block`), and the top 3 memories by similarity.
- **Arc state in process memory.** `_STORY_STATES` in `routers/chat_loops.py`.
- **Time is stored and unused.** `in_game_time` starts at year 1000 for every story.
  `validate_scene_revision`, `check_fact_validity` and `get_active_facts` have no callers.
- **NPCs have no memory in scene play.** Memories are extracted only for the acting character.
  NPCVoice recall exists only in the conversation loop.
- **No model of who knows what.** Canon facts are global to a universe.
- **Only the speaker reaches the turn.** The session holds `persona_id`,
  `speaker_character_id` and `controlled_character_ids`; `get_scene_loop` passes one `actor_id`.
- **Pack apply yields no starting situation.** No location, present NPCs or opening scene.
  CanonKeeper's `_COMMIT_ORDER` skips pack `agendas` and `plot_threads`.
- **Stranded work (resolved 2026-11-10).** Auth hardening merged as PR #138 and
  `Sebastian/gm_assist_overhaul` (G-6 templates, G-9 contradiction depth) as PR #137. PRs
  #135 and #136 are rebuilt in PR #139.
- **The local stack cannot run a turn.** Postgres has 0 `model_pairs` and 0
  `llm_node_assignments`; MinIO, GLiNER and the UI are not running; MongoDB has no universes.
- **Book-to-world is unproven.** Real models have run two chapters. Each book yields two
  packs, no novel has been ingested, and packs carry no chronology.
- **Tenancy is enforced at the HTTP layer only.** One shared hidden Conversatory universe, no
  per-user model quota, provider keys stored as plain text.
- **CI.** Weekly Integration fails on pulling `quay.io/minio/minio:latest`. Four of the last
  six pushes to master failed or were cancelled.

## Phases

Phases 0 and 1 go first and can run side by side. Phases 2, 3 and 4 then run in parallel on
separate branches and merge in the order 2, 3, 4. Phases 5, 6 and 7 follow and are independent
of one another. Phase 8 is the acceptance test and needs a person to play.

| Phase | Outcome | Owns | Depends on | Brief |
|---|---|---|---|---|
| 0. Local stack | Every service up, every tier has a model, one scene plays locally | Seed scripts, `doctor.sh`, setup doc | Nothing | [phase-0-local-stack.md](phase-0-local-stack.md) |
| 1. Stabilize | Master is green, protected, and holds the stranded fixes | CI, branches, PRs #135 and #136, auth hardening | Nothing | [phase-1-stabilize.md](phase-1-stabilize.md) |
| 2. Guided start | Questions, world-grounded start suggestions, character, opening scene | Pre-play loops, session intro, world seed, opening | Phase 1 merged | [phase-2-guided-start.md](phase-2-guided-start.md) |
| 3. Continuing campaign | The story remembers, time is used, the world moves | Story loop, story ledger, context assembly, scene end | Phase 1 merged | [phase-3-continuing-campaign.md](phase-3-continuing-campaign.md) |
| 4. Cast and NPC depth | The GM knows who the user controls; NPCs remember and know only what they witnessed | Cast list, turn inputs, memory extraction, NPC state | Phase 1 merged; rebases on Phase 3 | [phase-4-cast-and-npc-depth.md](phase-4-cast-and-npc-depth.md) |
| 5. Book to world | A whole book, real models, one pack, a playable start; a sourcebook and a novel | Book decomposition, Analyzer, pack schema | Phases 0 and 2 | [phase-5-book-to-world.md](phase-5-book-to-world.md) |
| 6. Multi-tenant hardening | A second account cannot read, change or overspend the first | Ownership, router guards, quotas, provider keys | Phase 1; after 2, 3, 4 merge | [phase-6-multi-tenant-hardening.md](phase-6-multi-tenant-hardening.md) |
| 7. Light RP and GM assistant | One-click streamed character chat; a GM assistant tested at a real table | Conversatory, OpenAI-compatible endpoint, `/gm` page | Phase 4 | [phase-7-light-rp-and-gm-assistant.md](phase-7-light-rp-and-gm-assistant.md) |
| 8. Playtest | A person plays five scenes over three days; defects found, ranked, fixed | Playtest protocol, reports, bug-fix PRs | Phases 0 to 4; repeat after 5 | [phase-8-playtest.md](phase-8-playtest.md) |

**What each gate needs.** Solo auto-GM play: Phases 0 to 4, then 8. Playing in a world taken
from a book: add Phase 5. Giving anyone else an account: add Phase 6. Phase 7 is the other two
modes and blocks neither.

**Where a person is needed.** Phase 0: provider keys and model choice. Phase 1: pushing the
auth branch, branch protection, deleting branches. Phase 5: which books, the model budget,
labelling claims. Phase 6: the key-encryption scheme and quota numbers. Phase 7: a GM for the
table test. Phase 8: the player.

**Getting the briefs to agents.** These files must be on `origin/master` (or handed to the
agent directly) before an agent branching from `origin/master` can read them.

**Still left out:** autonomous PC, audio capture, whole-repo mutation score, new database
backends, latency work, and multiplayer with several humans in one scene.

**The test for done.** A person who is not the author applies a pack, plays five scenes over
three days, and in scene five an NPC brings up, unprompted and correctly, something the player
did in scene two. Phase 8 runs it.

## Brief every agent gets

Give this section to the agent together with its phase file.

- **Repo and base.** Branch from `origin/master` after Phase 1 has merged (Phases 0 and 1
  branch from current `origin/master`). Fetch first; the
  local `master` in the main checkout has been stale. Open a PR; never push to master.
- **Read first.** `AGENTS.md`, `CLAUDE.md`, `docs/2_architecture/the_three_layers.md`,
  `docs/architecture/GM_AS_AUTHORITY.md`, `docs/architecture/DE_HEURISTIC_PRINCIPLE.md`, and
  this README.
- **Layer rule.** data-layer → agents → cli/ui. The UI and CLI never import `monitor_data.db`.
- **Canon rule.** Only CanonKeeper writes Neo4j. Everything else stages a `ProposedChange` in
  MongoDB. Every canonical fact carries `evidence_refs`.
- **No heuristics.** Classification and judgment go to a model call with a typed signature,
  never to keyword tables or counters. Pick the cheapest tier that works (LIGHT, STANDARD,
  HEAVY).
- **Code rules.** Agent methods that call MCP tools are `async`. Log with `structlog`, never
  `print`. Pydantic v2, line length 100, strict mypy.
- **Use case ids.** Look up the matching ids in `docs/USE_CASES.md` and put them in every
  commit and the PR title.
- **Tests.** Every change has unit tests and one integration or e2e test. Never edit
  `tests/verification/**` or `tests/property/**`. Never weaken an assert to get green.
- **Prove the wiring.** The hermetic suite fakes every database, which is how a call to a
  method that does not exist shipped unnoticed. For each new call across a component boundary,
  add a test that asserts the real callee was invoked with the expected arguments.
- **No silent degradation.** Do not add `except Exception` that logs and continues around new
  logic. If a failure must not break a turn, record it through `RoleplayErrorRecorder`.
- **Checks before you report.**

```bash
uv run ruff check packages scripts
uv run ruff format packages
uv run mypy packages/data-layer/src packages/agents/src packages/cli/src packages/ui/backend/src --cache-dir /tmp/mypy-cache
uv run python scripts/check_layer_dependencies.py
uv run pytest packages tests -q --tb=short -p no:cacheprovider -n auto
```

- **Report back.** PR link; what changed by file; test and check output as it printed;
  anything in the brief you found to be wrong, with the file and line that shows it; anything
  you skipped and why.

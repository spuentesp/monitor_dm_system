---
description: "Canonical project status: what is shipped, what is not, quality gates. Verified against code."
tags: [status, canonical, verified]
layer: 0
---

# MONITOR — Project Status

> **Verified 2026-07-23** by direct code inspection (not inferred from docs or diffs).
> This is the canonical status doc referenced by `CHANGELOG.md` and `conductor/plan.md`.
> When a claim here conflicts with another doc, this doc wins — and please fix the other doc.

## Quality gates

| Gate | State |
|------|-------|
| Unit/integration suite | ~5,900 tests, hermetic (no keys/network), ~5 min — `uv run pytest packages tests -q` |
| E2E (full stack) | 147 tests incl. three mode walkthroughs — `RUN_E2E=1 RUN_INTEGRATION=1 uv run pytest tests/e2e -q --timeout=300` |
| Lint / format | `uv run ruff check packages` / `uv run ruff format packages` |
| Types | `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache` (strict) |
| Layer boundaries | `python scripts/check_layer_dependencies.py` |
| Mutation testing | **Removed** — cosmic-ray hangs on the async stack; claims formally dropped (T-017) |
| Live LLM-vs-LLM playtests | `scripts/live_llm_gm_vs_player_test.py`; transcripts in `docs/testing/live_gm_vs_player/` |

## Live smoke

Last verified play pass: T-055 (2026-06-13, dockerized stack, full core loop via UI).
Live multi-world verification 2026-07-23: three 9-turn LLM-GM-vs-LLM-player sessions
(Fallout 2d20, VtM V20, Death in Space) against the real chat API — 0 errors; transcripts
in `docs/testing/live_gm_vs_player/`. Server-authoritative tap-to-roll and
auto-roll-and-weave live-verified the same day.

## Shipped (verified 2026-07-23)

- **Core play loop** — GMAgent → Narrator → Resolver pipeline, web chat + CLI.
- **Dice experience (P&F §2)** — server-authoritative rolls, one-beat structured roll
  action, auto-roll-and-weave on pending rolls, per-session roll model, dice only on
  `propose_roll`/`contested`.
- **Suggested-action chips (P&F §3)** — `packages/agents/src/monitor_agents/narrator/narrator.py:161` →
  `scene_loop.py:181,432` → `PlayConsole.tsx:347-356`.
- **Forge/Play UI split (P&F §4)** — `/forge` (hub, apply, editor, review) vs `/play`;
  ProposedChange review UI accepts/rejects/commits to canon.
- **Resume-aware openings (P&F §5, partial)** — `chat_opening.py:136-156` via RecapAgent;
  tested (`packages/ui/backend/tests/test_build_gm_opening_resume.py`).
- **GM conditioning** — CAMPAIGN_INTENT pre-question when no story_premise
  (`session_zero_loop.py:47-52`, `chat_loops.py:985`); StoryLoop→SceneLoop `story_state`
  threading (wired 2026-07-23).
- **Persona→Session-Zero bridge** — returning personas shrink the interview to as few as
  2 questions (`session_zero_loop.py:333-343`, `chat_loops.py:966-981`).
- **Freeform default in web UI (P&F §1, partial)** — narrative mode default + visible
  "Play style" selector (`SetupPanel.tsx:67-68,238-243`).
- **Character-creation parsing** — LLM structured extraction replacing regex
  (`character_creation_loop.py:692-872`); attribute/skill step isolation fixed (:244-246).
- **Ingestion hardening** — degenerate-extraction detection with `needs_review` +
  `degenerate_reason` (`_game_system_persistence.py:582-616`); PARTIAL job status with
  failed batch/section detail (`ingestion_pipeline.py:598-667`); provenance
  (`source_ref`/`evidence_refs_json`) on extracted items; `step_type` content
  cross-check (:343-397); multi-column PDF reading order (`pdf_processing.py:290-343`);
  upload-time SHA-256 duplicate rejection; 200MB size cap + 64MB mmap streaming budget.
- **CanonKeeper LLM contradiction detection** — DSPy ChainOfThought per-fact and batch
  (`canonkeeper.py:345-360,629-643`, `packages/agents/src/monitor_agents/canonkeeper/verification.py`); keyword heuristic is
  fallback only.
- **Pack operations UI** — batch select + Merge/Export/Clone/Slice, all wired
  (`PackLibrary.tsx` ↔ `pack_library.py`).
- **Universe forking** — end-to-end: `POST /universes/{id}/fork` + Fork button on the
  snapshots page.
- **GM Assistant web surface** — `/gm` page: session recorder, plot hooks, session prep,
  handouts (`gm_tools.py:103-155`).
- **Downtime & progression (P-21)** — downtime trigger in scene_loop, level-up
  endpoints, `progression_loop.py`.
- **Narrator hallucination guard ([G-4], 2026-07-23)** — empty-sheet sentinel
  prepended by `Narrator._build_actor_block` when stats / inventory /
  conditions / personality / state_tags are all empty; prompt-level
  do-not-invent rule added to `setting_anchor` in
  `packages/agents/src/monitor_agents/narrator/narrator.py`. Stops the live-recorded bug where the narrator
  invented a clan the player never picked. Test:
  `packages/agents/tests/test_narrator_hallucination_guard.py`.
- **Session Zero skip-preplay affordance ([G-1 (c)], 2026-07-23)** —
  `POST /api/chat/{session_id}/skip-preplay` — 404 unknown session, 409
  if `phase` not in {awaiting_character, session_zero, char_creation}.
  Pops both loop caches (`pop_session_zero_loop`, `pop_character_creation_loop`),
  flips `phase` to `active_play`, generates a prologue via
  `_generate_prologue` (with a generic-opening fallback if no
  `session_zero_summary.backstory`), persists and fans out the GM
  message. Client: `chatApi.skipPreplay` mirrors `endScene` (180s
  timeout). UI: a ghost "Skip to play" button next to `PhaseChip` in
  `PlayConsole.tsx`, visible only during preplay phases. Tests:
  `test_skip_preplay.py` covers 404, 409, 200 happy path, and a
  parametrized matrix over the three accepted phases.
- **Session Zero live-verification ([G-1 (d)], 2026-07-23)** — Captured against
  a fresh ``monitor-ui`` from this master checkout on UI_PORT=8123,
  the worktree backend on :8000 having been killed (with the user's
  explicit authorization — ``kill 477221 477224``). Three worlds,
  10 turns each, rich opening line per world. Session Zero fires
  exactly 4 ``metadata.phase=session_zero`` GM messages in all 3
  worlds, with transition to ``active_play`` (Death in Space, VtM V20)
  or ``char_creation`` (Fallout 2d20) at GM turn 5. The path:
  cap=4 + rich-intro seed consumes 1 answer → effective budget 3
  questions. Compared to the pre-G-1 baseline (7-question cap, 6:2
  split, ~7–8 GM turns to active_play), this is a 43%
  session_zero GM-turn reduction on every world. Raw transcripts and
  raw JSON phase arrays in
  ``docs/testing/live_verification_g1_2026-07-23.md``.
- **Session Zero cap + premise-aware budget ([G-1 (a)+(b)], 2026-07-23)** —
  `DEFAULT_MAX_QUESTIONS` dropped 7 → 4 in
  `session_zero_loop.py:42`. The hardcoded `max_questions=7` literal in
  `chat_loops.py:302` (and the two `total_questions` fallbacks at
  `:734,:1000`) replaced with the imported `DEFAULT_MAX_QUESTIONS`
  constant — eliminates the prior drift between loop default and
  API-facing fallback. Prompt text in `session_zero.py:224,250,268`
  bumped from "5-7"/"7" to "2-4"/"4". Premise-aware budget: when no
  persona is attached but the player's first `user_content` is
  non-empty, it seeds as a single consumed answer — no new LLM call —
  shrinking the budget from 4 → 3 for the rich-intro case
  (matching the docs/STATUS.md ≤3 target). Behavior test
  `TestSessionZeroState.test_default_state` and the
  `total_questions` assertion in `TestSessionZeroStart` updated;
  `test_session_zero_prompts` fixtures left intact (prompt-test
  data, not assertions).
- **Module-intro analyzer extraction ([G-2 (b)], 2026-07-23)** — New
  `ModuleIntroExtractionSignature` / `ModuleIntroExtractionModule`
  (HEAVY) in `packages/agents/src/monitor_agents/analyzer/analyzer.py`,
  immediately below `SectionSummaryModule`. Inputs: `sections_context`
  (first ≤6 page-ordered sections formatted as `## heading + body`,
  bounded to 4000 chars/section), `source_name`. Output: `intro_text`
  (verbatim, or empty if no authored intro). Wired in
  `Analyzer.__init__` as `self._module_intro_extractor`. New
  `_extract_module_intro` helper short-circuits ``""`` for any
  non-`ADVENTURE_MODULE` pack so the HEAVY LLM call never fires on
  rulebooks. Length floor (40 chars) prevents a one-line quote from
  short-circuiting the system's cold open. LLM failures warn-and-continue
  (plan mandate). Called once per ingest (after Phase 5, before
  `_assemble_and_finalize`); result threads through as
  `KnowledgePackUpdate(intro_text=…)`. Test:
  `TestExtractModuleIntro` (7 cases) + `TestFormatFirstNSections`
  (4 cases) in `test_module_intro_extraction.py`.
- **Authored-module-intro openings ([G-2 (a)+(c)+(d)], 2026-07-23)** —
  `KnowledgePack` schemas gain `intro_text` (`max_length=8000`,
  persisted via `_convert_knowledge_pack_doc` and propagated through
  `KnowledgePackUpdate` patches). `build_gm_opening`'s fresh-session
  path now resolves `session["pack_id"]` → `mongodb_get_knowledge_pack`
  → `pack.intro_text` and returns it verbatim when >40 chars, ahead
  of the resume-recap and generated cold-open branches. Resume keeps
  priority for its recap branch. Tests:
  `TestBuildGmOpeningModuleIntro` in
  `test_build_gm_opening_module_intro.py` (7 cases) + 6 schema
  round-trip cases in `test_knowledge_pack_artifacts.py`.
- **Dice-mode default outside web UI ([G-3], 2026-07-23)** — `play_mode` now
  defaults to `"narrative"` system-wide (API schemas `chat_schemas.py`,
  CLI `play.py` `--mode`, and 3 read-path fallbacks in `chat.py` /
  `chat_loops.py`). Web UI default was already this; the flip brings
  CLI / API / read-paths in line. Engine defaults (resolver,
  scene_loop, gm_agent, gm_awareness) intentionally NOT flipped —
  every production caller passes `play_mode` explicitly, so a global
  flip would touch hot paths for no behavior gain. Tests:
  `TestPlayModeDefault` in `packages/ui/backend/tests/test_session_api.py`.
- **PDF structure cache + VtM legacy fix ([G-8 (d)+(e)], 2026-07-23)** —
  (d): ``extract_pdf_structure`` in
  ``packages/data-layer/src/monitor_data/tools/ingest_tools/pdf_processing.py``
  now wraps an in-memory SHA-256 LRU (4-entry cap). Cache key is the
  full ``hashlib.sha256(pdf_bytes).hexdigest()``; ``_deep_copy_sections``
  builds per-call fresh ``SectionBlock`` instances so caller
  mutations don't bleed. 4 tests pin cache hit / mutation isolation /
  cache miss / LRU eviction. (e): ``scripts/fix_vtm_seed_creation_steps.py``
  operational fix for the legacy VtM seed (``a227676a-…``) — preconditions
  asserted (doc exists, ≥5 steps, step titles match the expected
  mapping), dry-run by default, exits 2 on precondition failures and
  0 on clean dry-run / successful apply / no-op idempotent re-run.
  Apply path flips the two wrong step_types in place + stamps
  ``hand_authored: True`` so the G-8(c) gate finds provenance later.
- **Game-system provenance gate ([G-8 (c)], 2026-07-23)** —
  `mongodb_create_game_system` in
  `packages/data-layer/src/monitor_data/tools/mongodb_tools/game_systems.py`
  now raises ``ValueError`` when neither ``source_document_id``
  (ingested) nor ``hand_authored`` (deliberately curated) is set.
  Production paths already comply: ingestion sets
  ``source_document_id``; the UI hand-author editor sets
  ``hand_authored=True`` (entities.py:605). Direct callers updated:
  ``test_create_game_system_success`` (contract test now supplies
  ``source_document_id``); ``tests/e2e/conftest.py`` + ``test_03_game_system.py``
  (set ``hand_authored=True``); ``scripts/seed_game_systems.py``
  (stamps ``hand_authored: True`` on its raw dict even though it
  bypasses the tool). New tests:
  ``test_create_game_system_without_provenance_raises`` +
  ``test_create_game_system_with_hand_authored_succeeds`` in
  ``test_game_system_tools.py``.
- **Ingestion residual (a)+(b) ([G-8], 2026-07-23)** — silent skip events in
  `_build_typed_list` now threaded through every wrapper via
  `label=`/`skipped=` keyword args; `save_game_system(..., job_id=...)`
  appends a ≤400-char summary to the parent `IngestionJob.warnings`.
  Power/subsystem merge now propagates `source_ref` and `formula` to
  `GameRule` (was hardcoded `None`; provenance silently dropped). Tests:
  `TestBuildTypedList.test_skip_list_records_*` and three new `job_id`
  cases in `TestSaveGameSystem`.

## Not shipped / open gaps (verified 2026-07-23)

Tracked in `docs/architecture/GAP_REMEDIATION_PLAN.md`. Summary:

1. **Session Zero length ([G-1 fully shipped 2026-07-23])** —
   `DEFAULT_MAX_QUESTIONS` lowered 7 → 4; prompt text in `session_zero.py`
   updated ("Typically 4"; "after 2-4 substantive answers"); chat-loop
   premise-aware budget seeds the player's opening message as one consumed
   answer when no persona is set. Skip-preplay endpoint
   `POST /api/chat/{session_id}/skip-preplay` accepts
   {awaiting_character, session_zero, char_creation} (409 otherwise),
   pops both loop caches, sets phase to active_play, generates a
   prologue, and fans out a GM message; corresponding
   `chatApi.skipPreplay` in `api.ts` and a "Skip to play" ghost button
   in `PlayConsole.tsx` (next to `PhaseChip`). **(d) live-verification
   captured 2026-07-23 against a fresh master checkout backend (port
   8123) across Death in Space / Fallout 2d20 / VtM V20. Session Zero
   fires exactly 4 GM messages in all 3 worlds, with transition to the
   next phase (``active_play`` for narrative worlds, ``char_creation``
   for game-system worlds) at GM turn 5. Compared to the pre-G-1 baseline
   (7-question cap, ~7–8 GM turns) this is a 43% session_zero reduction
   on every world. Method + transcripts:
   `docs/testing/live_verification_g1_2026-07-23.md`.
2. **Authored-module-intro openings (analyzer-extraction now wired)** —
   schema + persistence + precedence branch + analyzer extraction all
   shipped ([G-2 (a)+(b)+(c)+(d)], 2026-07-23). New
   `ModuleIntroExtractionSignature` + `ModuleIntroExtractionModule`
   (HEAVY) in `packages/agents/src/monitor_agents/analyzer/analyzer.py`; wired in `Analyzer.__init__` as
   `self._module_intro_extractor`. `_extract_module_intro` gates on
   `pack_type == ADVENTURE_MODULE`, caps at first 6 sections, requires
   >40 chars, warns-and-continues on LLM failure. Called once per
   adventure-module ingest (after Phase 5; result threaded into
   `_assemble_and_finalize` → `KnowledgePackUpdate(intro_text=…)`).
   Existing packs get `intro_text=None` until re-ingested.
3. **Dice-mode default outside web UI** — shipped [G-3], 2026-07-23. API
   schemas + CLI `--mode` + 3 read-path fallbacks (`chat.py:234`,
   `chat_loops.py:142,:214`) now default to `"narrative"`. Engine-internals
   defaults (resolver / gm_agent / gm_awareness / scene_loop) intentionally
   untouched — all production callers pass `play_mode` explicitly
   (verified grep).
4. **Co-Pilot mode polish** — web `/gm` surface exists; CLI `monitor copilot` never
   shipped; end-to-end human-GM workflow unpolished. Full plan:
   `docs/architecture/GM_ASSISTANT_MODE_PLAN.md`.
5. **Portable character templates (P&F §6)** — no `CharacterTemplate` schema or
   per-world instantiation. (`EntityTemplate` is NPC-generation only.)
6. **Autonomous PC (PC-Agent)** — no implementation. (The P-21 ID was reused for
   downtime/progression, which shipped.)
8. **Ingestion residuals (partial — [G-8 (a)+(b)+(c)+(d)+(e)] shipped 2026-07-23)** —
   (a)+(b): `_build_typed_list` skip events surfaced via
   `save_game_system(..., job_id=...)` → `IngestionJobUpdate.warnings`;
   powers/subsystems merge propagates `source_ref`/`formula`. (c):
   `mongodb_create_game_system` rejects any `GameSystemCreate` missing
   both `source_document_id` and `hand_authored`. (d): in-memory SHA-256
   LRU cache on `extract_pdf_structure` (4-entry cap, copy-on-return)
   so re-ingest within a process doesn't reparse the same PDF. (e): a
   one-off operational script `scripts/fix_vtm_seed_creation_steps.py`
   that rewrites the legacy VtM seed's `steps[3].step_type` (`choose_class`
   → `choose_disciplines`) and `steps[4].step_type` (`choose_skills` →
   `choose_background`) via direct `update_one` (the tool choke rejects
   `is_builtin` docs) + `$set: hand_authored: True`. Dry-run by default;
   asserts the doc exists, has ≥5 steps, and titles match before
   applying.
9. **CanonKeeper depth** — detection scoped to direct logical contradictions; no
   impossible-state-transition or implication-level checks.

## Latency

Known: complex turns take multiple serial LLM calls (10s+ measured). **Accepted for now —
target is < 40s per turn, which current performance meets.** No active work.

## Deferred (formal)

- Mutation testing (tooling incompatible with async stack).
- Autonomous PC (see gap 7).
- Latency optimization (see above).

## Doc map for status

- Play & Forge direction: `docs/architecture/PLAY_AND_FORGE_DIRECTION.md` (per-section status markers)
- Character templates / GM conditioning: `docs/architecture/CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md` (Q1–Q3 reconciled)
- Ingestion audit: `docs/architecture/INGESTION_PIPELINE_AUDIT.md` (20/24 items done, per-finding status)
- Gap remediation plan: `docs/architecture/GAP_REMEDIATION_PLAN.md`
- GM Assistant (Co-Pilot) mode plan: `docs/architecture/GM_ASSISTANT_MODE_PLAN.md`
- Forge (World Design) mode plan: `docs/architecture/FORGE_MODE_PLAN.md`

> Note: `docs/blog/post-09-current-state/draft.md` describes the system as of June 2026
> and is kept as a dated snapshot — several of its "what's missing" items have since
> shipped. Do not treat it as current status.

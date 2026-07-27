# Gap Remediation Plan

> **Status:** proposed (2026-07-23, rev. 2 — detailed designs grounded in direct code
> inspection). Every gap verified against code on 2026-07-23; evidence in
> `docs/STATUS.md`. Ordered by impact/effort, not by gap number.
>
> Conventions: DSPy modules are co-located with their respective agents; MCP calls async; `structlog` (no
> print); pydantic v2; line-length 100; mypy strict; layer rules
> (CLI→agents→data-layer, only CanonKeeper writes Neo4j). Test fixtures:
> `FakeMCPClient`/`FakeLLMClient` in `tests/conftest.py:165,261`.

---

## G-4 · Narrator hallucination guard (S, do first)

**Gap:** No prompt-level prohibition on inventing character facts. A sparse sheet
yields only `ACTOR PROFILE (<name>):\n- Role: pc\n` — personality/tags/stats/
inventory/conditions lines are silently skipped (`narrator.py:313-327`) and the
Narrator fills the vacuum (observed live: invented a clan). The `setting_anchor`
CRITICAL line (`narrator.py:405-413`) only forbids *changing* identity mid-session,
not *inventing* it.

### Step 1 — Signature instructions (`packages/agents/src/monitor_agents/narrator/narrator.py`)

- **(a)** Add to the "Core GM craft rules" list in the `NarratorSignature` docstring
  (after :40):

  ```
  - Character identity facts (clan, class, species, stats, background) may only be
    referenced when they appear in the ACTOR PROFILE block, the setting anchor, or
    ESTABLISHED FACTS. If the actor block says the character sheet is empty, narrate
    without assigning the character any clan, class, stats, or backstory — leave the
    character's identity undefined until the player defines it.
  ```

- **(b)** Append to the `profile_context` field desc (:86-92):
  `" When it states the character sheet is empty, do not invent clan, class, stats, or background."`
- **(c)** Prepend to the `narrative_text` output desc (:135-147), before the
  think/feel rule: `"Never assign the player character identity facts (clan, class,
  species, stats, background) that are not present in the inputs. "`

Rationale: docstring bullets survive DSPy optimizers least reliably, so the rule is
repeated in the input field (closest to the data) and output field (closest to
generation) — matches the file's existing redundancy pattern.

### Step 2 — Actor block guard line (`packages/agents/src/monitor_agents/narrator.py`)

Insert in `_generate_narrative_and_proposals` between :327 (end of conditions block)
and :328 (`profile_context += actor_block`), inside the `if actor:` branch:

```python
            sheet_facts = [personality, tags, stats, inventory, conditions]
            if not any(sheet_facts):
                actor_block += (
                    "- CHARACTER SHEET EMPTY: no clan, class, stats, or background "
                    "are defined. Do not invent or assign identity facts; narrate "
                    "only what the player has stated.\n"
                )
```

Reuse the values already fetched at :310-325 — no new lookups. Optional hardening
(recommended): hoist the flag and also append `" The character sheet is empty — do
not assign clan/class/stats."` to the CRITICAL `setting_anchor` string (:405-413)
under the same condition.

### Step 3 — Tests

- `packages/agents/tests/test_narrator.py`, new `TestActorBlockGuard` reusing
  `TestNarrateTurn._make_prediction`/`_make_narrator` (the Narrator's LLM path is
  DSPy — `FakeLLMClient` is NOT on it; mock `_narrator_module` and inspect
  `call_args[1]["profile_context"]`, pattern at :372-380):
  - empty-sheet actor (name+role only) → `"CHARACTER SHEET EMPTY"` in profile_context
  - populated sheet (`stats={"Strength": 3}`) → guard absent, `"- Stats: Strength: 3"`
    preserved
- `tests/behavior/test_narrator_choreography_behavior.py`, new
  `TestHallucinationGuardPrompt`: `NarratorSignature.__doc__` contains
  "identity facts" and "character sheet is empty".

Note: keyword-checking the canned prediction's output would be vacuous (the fake
returns scripted text) — the meaningful assertions are on prompt construction.

**Risks:** signature edits invalidate prompt caches/optimized programs (none checked
in — low). Guard also fires for bare NPC actor dicts — acceptable; gate on
`role == "pc"` if noisy.

---

## G-3 · Flip dice-mode default to `narrative` outside the web UI (S)

**Gap:** Web UI defaults to freeform (`SetupPanel.tsx:67-68`) but API schemas and CLI
default to `dice_game_system`. Verified: **no test asserts the old default** — every
dice-dependent test/script passes `play_mode` explicitly (grep-verified across
`packages/`, `tests/`, `scripts/`).

### Steps

1. **API schemas** — `packages/ui/backend/src/monitor_ui/routers/chat_schemas.py:63-65`
   (`SessionCreate.play_mode`) and :115-117 (`Session.play_mode`):
   ```python
   play_mode: str = "narrative"  # "narrative" | "dice_standard" | "dice_game_system"
   ```
2. **CLI** — `packages/cli/src/monitor_cli/commands/play.py:53-58`: default
   `"dice_game_system"` → `"narrative"`; reorder help text to
   `narrative (default)/dice_standard/dice_game_system`. Fix the stale comment at
   :289 (`# Fallback to default` → `# Switch back to dice rules`); note the UX oddity
   in the PR (first `/godmode` now *enables* dice) but keep the toggle strings.
3. **Read-path fallbacks (recommended, 3 one-word edits)** — `chat.py:234`,
   `chat_loops.py:142`, `chat_loops.py:214`: `session.get("play_mode",
   "dice_game_system")` → `"narrative"` (fires only for legacy stored docs).
4. **Do NOT touch:** internal engine defaults (`resolver.py:471,664`,
   `gm_agent.py:467,536`, `gm_awareness.py:782`, `scene_loop.py:106,1408,1465`) — all
   production callers pass `play_mode` explicitly. Intentionally-dice flows
   (`forge.py:359,435`, playtest scripts/benchmarks) already pass modes explicitly.

### Tests

- Add one API-boundary test in `packages/ui/backend/tests/test_session_api.py`
  (alongside :63-89): POST without `play_mode` → response `play_mode == "narrative"`.
- No existing tests break (verified). Note for future e2e: dice-mode e2e tests must
  keep passing an explicit dice mode (`test_04_gm_loop.py:42`,
  `test_09_mode_walkthroughs.py:316` already do).

### Behavior change to document

With `narrative`, `gm_awareness.predict()` short-circuits at `gm_awareness.py:712-713`
(`_narrative_mode_verdict()`): the GM-awareness LLM call is skipped, no rolls are
proposed, resolver dice branch unreachable. Cached SceneLoops are keyed by a
signature that includes `play_mode` (`chat_loops.py:130-151`) — no stale-cache issue.
Pre-flip sessions keep their stored mode; no migration.

---

## G-8 · Ingestion residuals (S–M; do (b)+(a) together — same file)

**(a) Surface `_build_typed_list` skips (M).** Today it silently drops non-dict items
and builder exceptions (`_game_system_persistence.py:132-158`, six callers
:161-234,541-579). Job warnings infra exists: `IngestionJobUpdate.warnings`
(`schemas/ingestion_jobs.py:141`), appended atomically with 400-char cap
(`mongodb_tools/ingestion_jobs.py:257-260`) — no schema change.

1. `_build_typed_list` gains keyword params `label: str = ""`,
   `skipped: Optional[List[str]] = None`; both silent `continue`s record a skip entry
   (label + item name[:60] + exception type); end-of-loop `logger.warning` with count
   + first 3 samples. Update the "skipping invalid items silently" docstring (:137).
2. Thread `label`/`skipped` through the six wrappers (mechanical, one line each).
3. `save_game_system` (:619-633) gains `job_id: Optional[UUID] = None`; collects
   `skipped_items` from all six `_build_*` calls; after the degenerate-extraction
   block (:685-695) appends one ≤400-char summary warning to the job via
   `mongodb_update_ingestion_job(job_id, IngestionJobUpdate(warnings=[summary]))`
   (import additions at :53-56; layer-legal).
4. Plumb `job_id` through `Analyzer._save_game_system` (`_core.py:3118-3133`) and the
   call site (`_core.py:1466`).

Tests (`packages/agents/tests/test_game_system_persistence.py`): skipped items land
in the collector with names; `save_game_system(..., job_id=...)` with one invalid
attribute asserts the job-warning call; existing skip tests (:188,:192) still pass.

**(b) Propagate `source_ref` in `_merge_powers_and_subsystems` (S).** Each merged rule
originates from exactly one power/subsystem item — 1:1 copy, **no schema change**
(`GameRule.source_ref` is `Optional[str]`, max 200, `game_systems.py:511`).

- :282 → `source_ref=(str(power["source_ref"])[:200] if power.get("source_ref") else None),`
- :303 → same for `subsystem`.
- Add a comment above the function (:264): `powers`/`subsystems` are currently never
  populated by the live extraction path (`CharacterSheetExtractionSignature` declares
  no such OutputFields; `_extract_one` maps no such keys, `_core.py:2526-2534`) — the
  merge is exercised only by unit tests. Wiring extraction belongs with re-ingestion
  work, NOT this gap.

Tests (`TestMergePowersAndSubsystems` :533-575): ref carried; absent → `None`.

**(c) `source_document_id` requiredness (S).** Enforce at the tool choke point, NOT a
pydantic validator — contract/property tests construct `GameSystemCreate` directly and
assert "minimal is valid" (`test_DL_20_contracts.py:122-137` etc.). Create is the only
injection point (`GameSystemUpdate` can't set provenance fields).

- `mongodb_tools/game_systems.py:102-103`, after the `is_builtin` rejection:
  ```python
  if not params.source_document_id and not params.hand_authored:
      raise ValueError(
          "Game system requires provenance: set source_document_id (ingested) "
          "or hand_authored=True (deliberately hand-curated) — see "
          "INGESTION_PIPELINE_AUDIT.md Finding 3."
      )
  ```
- Production paths already comply (ingestion sets `source_document_id`; UI hand-author
  sets `hand_authored=True`, `entities.py:605`). Fix non-compliant test call sites:
  `test_game_system_tools.py:153-163`, `tests/e2e/conftest.py:686`,
  `tests/e2e/test_03_game_system.py:127-140` (add `hand_authored=True`).
- One-liner hygiene: `"hand_authored": True` in `scripts/seed_game_systems.py`'s raw
  doc (it bypasses the tool via pymongo).
- Tests: new raise case next to `test_create_game_system_builtin_rejected` (:188) +
  positive case with `source_document_id`.

**(d) `extract_pdf_structure()` caching (S).** Only one production parse per ingestion
run (`indexer.py:756`); the repeated-parse pain is re-ingestion within the process
(cross-upload dupes already prevented by SHA-256 dedup, `ingestion_pipeline.py:306-343`).
Design: **in-memory content-hash LRU, no disk cache** (disk buys serialization +
invalidation complexity for marginal benefit).

- Rename body (:174-274) to `_extract_pdf_structure_uncached`; public wrapper keeps
  name/signature, keys on `hashlib.sha256(pdf_bytes)`, `OrderedDict` LRU capped at 4
  entries (entries hold full section text), returns per-field copies of the mutable
  `SectionBlock` dataclass (`_models.py:88-95`).
- Tests (`packages/data-layer/tests/test_db/test_ingest_tools.py`, alongside :38-67):
  same bytes parsed once (count `fitz.open`), mutation isolation, different bytes miss.

**(e) Legacy VtM seed doc hand-fix (S).** The bad doc (`game_systems.system_id =
a227676a-edab-4a43-80d9-8f76b74ff289`, `is_builtin=True`) predates all seed scripts;
referenced by `scripts/e2e_full_loop_scenarios.py:125` and
`scripts/test_vtm_full_session.py:42`. The tool path can't fix it —
`mongodb_update_game_system` rejects builtin docs (`game_systems.py:357-359`).

New script `scripts/fix_vtm_seed_creation_steps.py` (dry-run default, `--apply` to
write, direct-collection pattern per `scripts/vtm_game_system.py:114-127`):
`update_one` fixing `character_creation.steps[3].step_type` `"choose_class" →
"choose_disciplines"` and `steps[4].step_type` `"choose_skills" → "choose_background"`,
plus `$set: hand_authored: true`. Preconditions: assert doc exists, ≥5 steps, titles
match expected before writing; idempotent (re-run is a no-op). Do NOT rename or touch
`system_id`. No pytest (one-off data op); verify operationally: dry-run → --apply →
dry-run clean.

**Cross-cutting:** after implementation, tick these boxes and update the "Remaining"
bullets in `INGESTION_PIPELINE_AUDIT.md`. Open observations recorded for later:
`powers`/`subsystems` extraction wiring (bundle with re-ingestion); the provenance
audit script skips `is_builtin` docs (`audit_ingestion_documents.py:81`) — decide
whether builtins lacking `hand_authored` should be reported.

---

## G-2 · Authored-module-intro openings (M)

**Gap:** `build_gm_opening` (`chat_opening.py:113-253`) has two branches (resume recap
:136-156, cold open :158-253); the docstring (:131-134) marks the authored-intro case
unimplemented.

**(a) Schema: `intro_text` on KnowledgePack** — the intro is a property of the module
(= pack), not a universe (many packs can apply) and not an extracted list item.
Sessions already carry `pack_id` (`chat.py:274-364`). Four edit sites:

1. `KnowledgePackCreate` (`schemas/knowledge_packs.py:575-604`, after `description`):
   `intro_text: Optional[str] = Field(None, max_length=8000, description=...)` citing P&F §5.
2. `KnowledgePackUpdate` (:607-629) and `KnowledgePackResponse` (:640-675): same field.
3. `mongodb_tools/knowledge_packs.py`: `_convert_knowledge_pack_doc` (:48-95),
   create doc dict (:118-154), update (:201-257, only when not None).

**(b) Extraction: one LLM call, no heuristics.** Per `DE_HEURISTIC_PRINCIPLE.md`,
"is this section the read-aloud intro?" is a meaning-level decision → semantic, not
keyword matching. New `ModuleIntroExtractionSignature` + `ModuleIntroExtractionModule`
(`_role = ModelRole.HEAVY`) in `packages/agents/src/monitor_agents/analyzer/analyzer.py` near `SectionSummaryModule`
(:1528-1546): inputs `sections_context` (first ≤6 page-ordered sections) +
`source_name`; output `intro_text` (quote EXACTLY, empty string if none). Wire in
`Analyzer.__init__` (:239-262); new `_extract_module_intro` helper (near :858) that
returns `None` unless `pack_type == ADVENTURE_MODULE`, caps at first 6 candidates,
accepts only `len > 40`, warns-and-continues on failure; call after Phase 2
(:602-615); pass through `_assemble_and_finalize` (:1428-1457) into the
`KnowledgePackUpdate` (:1485-1503). Cost: one HEAVY call per adventure-module ingest.

**(c) Precedence branch** — top of `build_gm_opening`, before `if is_resume:` (:136):

```python
    # P&F S5 case 3: the ingested module's own authored intro, verbatim.
    # Fresh sessions only — resume keeps priority for its recap branch below.
    if not is_resume:
        intro = _fetch_module_intro(session)
        if intro:
            return intro, {"type": "gm_opening", "module_intro": True}
```

New helper `_fetch_module_intro(session)` above it: reads `session["pack_id"]`, calls
`mongodb_get_knowledge_pack` (sync-in-async pattern already at :172-183), returns the
intro if `len > 40`, `""` on any failure (debug log). Update the docstring (:120-135)
— the "NOT implemented" note becomes the implemented first case.

**(d) No entity-linking/processing of intro_text.** Openings are deliberately
non-persisting (`test_chat_router_ooc.py:142` pins this); extraction from the module
already happened at ingestion. Verbatim text goes through the same plain GM-message
path (`chat.py:474-479`).

**(e) Tests:**
- New `packages/ui/backend/tests/test_build_gm_opening_module_intro.py` modeled on
  `test_build_gm_opening_resume.py`: verbatim intro + meta; resume+pack → recap wins;
  `None`/`""`/short intro → cold open; tool raising → cold open, no exception.
- Data-layer round-trip: create/convert/update carry `intro_text`.
- Analyzer test (`packages/agents/tests/test_analyzer.py`, reuse
  `_patch_common_analyzer_dependencies` :30-54): ADVENTURE_MODULE → update carries
  `intro_text`; RULEBOOK → `None`, no LLM call.

**Risks/limits:** fires only when the module pack is the session's system source
(universe-applied packs without `pack_id` get no intro — documented limitation);
verbatim fidelity is best-effort; existing packs have `intro_text=None` until
re-ingested; gated on correct `pack_type`.

---

## G-1 · Session Zero length for new characters (M; (a)+(b) together, then (c), then (d))

**Gap:** Brand-new character, no persona/premise: up to 7 questions + CAMPAIGN_INTENT;
live 6:2 session_zero:active_play split across three worlds (2026-07-23 baseline).
`DEFAULT_MAX_QUESTIONS = 7` at `session_zero_loop.py:42`, duplicated as a literal at
`chat_loops.py:302` and fallbacks at :732,:998.

**(a) Lower `DEFAULT_MAX_QUESTIONS` 7 → 4.** Not 3: the summary LLM needs enough
answers to weave a non-degenerate backstory. With (b)'s seed, a rich intro yields
`max(2, 4-1) = 3` — hitting the ≤3 target.

1. `session_zero_loop.py:42` → 4; update module docstring (:20-21) and
   `session_zero.py:16-18` class docstring.
2. `chat_loops.py:302` → use the imported constant; :732,:998 fallbacks likewise.
3. Prompt texts (behavioral — the LIGHT question generator reads them):
   `session_zero.py:224` "5-7 substantive answers" → "2-4"; :250 "Typically 7" →
   "Typically 4"; :268 "usually after 5-7" → "usually after 2-4". Grep for "5-7"
   after editing.
4. Test updates (`tests/behavior/test_session_zero_loop_choreography_behavior.py`):
   only the default-asserting tests change (:42, :78: 7→4). Explicit `max_questions=7`
   seed-arithmetic tests (:229-264) and `test_session_zero_prompts.py:438-461` stay.
   Historical live logs are artifacts — do not edit.

**(b) Premise-aware budget: seed the opening message as a consumed answer.** The
player's first substantive message *is* the answer to the GM's opening question
("Who are you, and where does your story begin?", `chat_opening.py:236-248`) — record
it as one seed answer, no new LLM call. The question LLM already avoids re-asking
covered ground via `prior_answers` (`session_zero.py:252-254,656-660`) — de-heuristic
compliant. Edit `chat_loops.py:966-986`: keep the persona-seed path; when no persona
seed and `user_content.strip()`, set

```python
seed_answers = [{
    "question": "Who are you, and where does your story begin?",
    "answer": user_content.strip(),
    "category": "origin",
}]
```

Effect with (a): persona-less new character → budget 3; persona path unchanged.
Do NOT build the optional multi-seed LLM extractor (gold-plating; single seed already
hits target). Campaign-intent front-loading already handled by
`ask_campaign_intent=not session.get("story_premise")` (:985).

**(c) Visible "skip to play" affordance.** Today skip is a typed stop word
(`session_zero_loop.py:159`) that only ends the interview. New endpoint in `chat.py`
next to `end-scene` (:860): `POST /{session_id}/skip-preplay` — 404 unknown session,
409 unless phase ∈ {`awaiting_character`, `session_zero`, `char_creation`}; pops both
loop caches (`pop_session_zero_loop` :316, `pop_character_creation_loop` :268), sets
`phase = "active_play"`, saves, generates the prologue via `_generate_prologue`
(:557) with any `session_zero_summary.backstory`, appends + fans out the GM message
(same helpers as `send_message` :637-641). Frontend: `chatApi.skipPreplay` in
`api.ts` (mirror `endScene` :230-231, 180s timeout); "Skip to play" ghost button in
`PlayConsole.tsx` next to `PhaseChip` (:516) when phase is preplay; invalidate the
session-state query in `onSuccess`.

**(d) Live-verification protocol.** Prereqs: `./dev.sh` stack + local Ollama
`qwen2.5:latest`. Rerun the three worlds with a RICH `--opening-line` (default at
`live_llm_gm_vs_player_test.py:240-242` is thin):

```bash
uv run python scripts/live_llm_gm_vs_player_test.py \
  --universe-id 6f0d9ef2-ee5e-4e52-a1bf-e10c29f8b495 --world-label "Death in Space" \
  --turns 8 --opening-line "<rich intro>"
# + Fallout b492380f-9f7e-4deb-b4fd-ba51f2a91c8a, VtM 7c737c26-7b84-4704-9ff6-4fc19492eac4
```

Metric: GM turns by `metadata.phase` (harness records at :152-166) vs the 6:2
baseline. **Pass:** `active_play` reached by GM turn ≤ 4 in ≥ 2 of 3 worlds; eyeball
that the first question references the seeded intro. Player is stochastic — one
regressing world = re-run signal, not necessarily a code failure.

**Tests:** behavior test `SessionZeroLoop(max_questions=4, seed×1)` → budget 3,
completes after 3 answers; router-level test asserting `answers[0]["answer"] ==
user_content` and `max_questions == 3`; API test for skip-preplay (200/409);
`PlayConsole.test.tsx` button visibility + click.

**Risks:** thinner backstories (4 answers + 1 seed vs 7 — mitigated, summary handles
0-1 answers at `session_zero_loop.py:185-189`; verify subjectively in live runs);
prompt drift if a "5-7" string is missed; early `is_final` could collapse the
interview to 1 question — confirm in live runs; skip-endpoint race with a mid-flight
send is the same last-write-wins class the codebase already accepts.

---

## G-5 · Co-Pilot mode polish (decision first, then core-loop polish)

> **Superseded 2026-07-23 by `GM_ASSISTANT_MODE_PLAN.md`** — the full mode plan.
> The decision (web `/gm` only, no CLI copilot) and the gap ordering below are
> adopted there as Phase 0–3. This section is kept as the summary record.

**Verified today:** web `/gm` page with 9 panels (rules ref, dice roller,
SessionRecorder, scratchpad, hooks, threads, contradictions, prep, handouts); 4
backend endpoints (`gm_tools.py:103-171` over PlotHookAgent); SessionRecorder is a
real capture loop (gm_assistant chat session, close → endScene, proposals →
CanonReviewPanel, RecapModal → RecapAgent). CLI `monitor copilot` does not exist
(`main.py:49-62`), though `main.py:15` and `vision_and_modes.md:22-27` still promise
it. Stale: `session-support.md:39` cites the deleted `session_ingest.py`.

### Decision: Option A — `/gm` is THE copilot surface (recommended)

| | A: web-only | B: also CLI `monitor copilot` |
|---|---|---|
| Fit | Built for GM-at-table glanceability | REPL can't show panels alongside transcript without a TUI |
| Cost | Gap-closure only | New Typer group + second UX for every CF feature |
| Parity | One surface | Permanent two-surface burden; CF-8 batch review is deeply UI-shaped |
| Momentum | Recorder/review/recap already web-shaped | CLI has no recorder concept at all |

If a CLI affordance is later demanded, ship thin read-only wrappers (`monitor query`
already covers canon exploration), not a parallel copilot. **Option A work, part 1 —
doc alignment (~0.5 day):** `vision_and_modes.md:22-27` (Assisted GM → `/gm` web;
Post-Session → `/gm` + `monitor query`), `main.py:10-17` docstring,
`docs/use-cases/epic-7-copilot-CF/*` stale refs, `docs/STATUS.md`.

### Gap list vs the vision's Assisted-GM / Post-Session roles (ordered)

Core loop polish first:
1. **No live contradiction alerts during capture** — checking is a manual side-panel
   button (`page.tsx:524-531`); CanonKeeper's check runs only at scene end. Add a
   per-entry/debounced check in the gm_assistant turn path with an inline alert.
2. **Recorder insights are generic** — no capture-specific behavior (auto-tag
   participants/locations, visible candidate facts per entry); CF-1 spec only
   partially met by generic scene-end proposals.
3. **No guided wrap-up flow** — pieces exist unsequenced. Build an "End of session"
   digest: recap + canon changes (accepted/rejected) + open-threads delta + next-prep
   teaser.
4. **Recap is not an artifact** — recaps regenerate on demand, never persisted; no
   session archive ("what happened in session 12?").

Surface consistency next:
5. **Dice roller off-pipeline** — client `Math.random` (`page.tsx:46-61`) contradicts
   the shipped server-authoritative doctrine (P&F §2); call the server roll path or
   label non-authoritative.
6. **Rules panel not universe-aware** — manual system dropdown (:1047-1055) instead of
   the selected universe's bound system.
7. **Scratchpad ephemeral** — localStorage-only (:320-340); "Ingest" fires the full
   document pipeline on a text blob, disconnected from the recording's review queue.

Scope calls last:
8. **Audio/hybrid capture** in CF-1 spec never shipped — descope in spec or build.
9. **Notes→canon review linkage** — scratchpad ingestion proposals land in
   `/forge/review`, not the recording's story-scoped queue.
10. **Recordings undifferentiated** in the sessions list — no archive status or
    per-recording summary metadata.

---

## G-6 · Portable character templates (L; 3 phases)

**Key finding:** the template *shape* already exists in production — the standalone
`characters` Mongo collection (`character_storage.py:26-48`: name, description,
avatar_url, personality, gm_notes, first_message + per-universe `versions[]`). No
stats, no world binding — field-for-field the P&F §6 template. The narrative-seed
bridge also shipped (`persona_id` → `_seed_answers_from_persona`,
`chat_loops.py:321-350,966-981`; `CharacterSheetCreate.source_persona_id`,
`character_sheets.py:76-84`). `EntityTemplate` is NOT a viable base (universe-scoped,
stat-generation machinery for NPC stubbing — opposite of portable).

**Open question resolved: net-new schema, NOT an `is_template` facet.** Character
identity/mechanics are split across Neo4j `EntityInstance` + Mongo `CharacterSheet`;
a facet would entangle a user-library object with CanonKeeper's write authority and
canon queries, and P&F §6's "no stats/world/system" invariant is unenforcible on a
model whose purpose is exactly those bindings. Net-new formalizes proven data.

### Phase 1 — data-layer contract

- New `schemas/character_templates.py` (Create/Update/Response/Filter/ListResponse
  quintet, conventions per `character_sheets.py`/`entity_templates.py`):
  `name, concept, personality, backstory_beats: list[str], voice, portrait_url,
  first_message, gm_notes` — explicitly NO stats/skills/universe_id/game_system_id.
  Response adds `template_id, usage_count, created_at, updated_at`.
- Storage: **extend the existing `characters` collection** (additive optional fields;
  live readers keep working). Rejected: fresh collection + migration (strands
  OOC-persona usage).
- New MCP tools `mongodb_tools/character_templates.py` copying `templates.py`'s
  structure (:30-133): create/get/list/update/delete + `increment_usage`. Register in
  `mongodb_tools/__init__.py` + `schemas/__init__.py`. No `middleware/auth.py` entry —
  user-library documents, Mongo-only, not canon.
- Migrate the entities router's standalone-character CRUD from `character_storage.py`
  raw dicts to the new tools (API shape stable).
- Tests: FakeMCPClient pattern (`tests/conftest.py:165`).

### Phase 2 — fields + UI polish

- Add `backstory_beats`/`voice` to `_seed_answers_from_persona` emissions.
- Extend `CharacterEditor.tsx` with the two fields (cheaper and more correct than a
  new forge tab — one editor, no duplicated CRUD); SetupPanel persona picker
  (:102-105) shows voice/beat count + "create new template".

### Phase 3 — system binding (the real instantiation)

After Session Zero synthesis, route through the existing `CharacterCreationLoop`
(`character_creation_loop.py:450`, wired at `chat_loops.py:237-265`) with
template-informed pre-fill: new `TemplateAnswerDraftingModule` (LIGHT role) in
`packages/agents/src/monitor_agents/character_creator/character_creation.py` drafts a "player answer" per creation step from
concept/personality/beats, fed through the same `process_input` path — reuses
`AttributeAssignmentModule`/`SkillSelectionModule`, no new parsing, no per-system
hardcoding. Persist with `source_persona_id` (already wired, `chat_loops.py:396-398`)
+ optionally a `versions[]` entry (`character_storage.py:163-209`). Phase 3 is
independent of Phases 1-2 — the bridge infra is already live; can be prototyped first.

---

## G-9 · CanonKeeper depth (L; 3 phases, flagging-first)

**Verified today:** per-fact LLM contradiction check (`canonkeeper.py:327-360`,
`ContradictionModule`); runtime pipeline `_evaluate_single` (:1345-1438): policy gate
→ `_check_contradiction` (:2411-2529) → reasoning → verdict; batch check (:593-644,
chunks of 15, opt-in bulk-ingest only) explicitly scoped to *direct* contradictions
(`verification.py:60-62`). State changes flow as `STATE_CHANGE` proposals
(`PersistenceService`) → `_commit_state_change` (:1783-1815); current tags
readable via `neo4j_get_state_tags`.

### Phase 1 — implication-level detection + FP measurement (no behavior change)

- New `ImplicationContradictionSignature` + module in `packages/agents/src/monitor_agents/canonkeeper/verification.py`
  (separate from the calibrated direct check; mirrors the batch signature's
  numbered-list I/O so chunking/parsing is reusable — `_LINE_RE`, :86). Outputs
  include an explicit `implications` field so the reasoning is auditable in logs.
  Wire into `_batch_contradiction_check` behind a config flag, mapped to a new
  additive `ContradictionType.IMPLICATION_CONFLICT` at HIGH severity — never
  CRITICAL, nothing hard-rejected.
- FP measurement: new `scripts/eval_canonkeeper_depth.py` replays committed
  `proposed_changes` (known-good → every flag is an FP by construction) from the
  populated universes (Fallout 983 entities, VtM 588) through the new module; emits
  counts + flag samples for spot-check. Some "FPs" will be latent canon drift —
  itself a finding.

### Phase 2 — transition rules + advisory flagging

- Deterministic rules (pure Python, no LLM, ~40 lines + a small `_TRANSITION_RULES`
  table) in `_evaluate_single` between :1374-1396, gated on
  `change_type == "state_change"`, comparing `neo4j_get_state_tags` against
  `add_tags`/`remove_tags`:
  1. **Terminal-tag finality:** `dead`/`destroyed` may not be removed, and no
     agency-implying tag may be added to a terminal-tagged entity, unless the proposal
     carries `content["override_reason"]` (resurrection is legal fiction — it must be
     explicit).
  2. **Mutual exclusion:** tiny static complement-pair list (e.g. dead/alive family);
     keep short and explicit, not inferred.
  3. **Location/teleport: deferred** — needs event-sequence reasoning; that's the
     implication check's job. Said out loud to avoid over-scoping.
- Flagging reuses existing idioms: stamp `meta.needs_review=True,
  meta.review_reason, meta.review_source` on the proposal + verdict
  (`_record_verdict` :2328-2339); add a `needs_review` filter to `canon_review.py`'s
  queue endpoints (:103,:144) and a badge in `CanonReviewPanel` / `/forge/review`
  (fits PROPOSAL_TABS, :46-57).
- Unit tests with FakeMCPClient/FakeLLMClient.

### Phase 3 — hard rejection (gated on data)

Enable REJECTED verdicts for transition-rule violations first (deterministic, low FP
risk). Implication-level stays flag-only until Phase 1 replay shows FP < 5% on
committed proposals with manual spot-check confirmation.

---

## G-7 · Autonomous PC (formally deferred — no work without product commitment)

No implementation exists. If activated: spec under
`docs/use-cases/epic-4-autonomous-gm-P/`; the LLM-as-player harness
(`scripts/live_llm_gm_vs_player_test.py`) is the seed for a PC-Agent.

---

## Sequencing

The two mode plans are the roadmap priorities and each is self-contained:
`GM_ASSISTANT_MODE_PLAN.md` (supersedes G-5) and `FORGE_MODE_PLAN.md` (deepens
the shipped P&F §4 split into a full mode). The remaining gaps below sequence
around them:

1. **GM Assistant mode** — per `GM_ASSISTANT_MODE_PLAN.md` (P0 → P2.1 → P2.2 →
   P1.1 → P1.2 → P1.3+P1.4 → P2.3 → P3 decisions).
2. **Forge mode** — per `FORGE_MODE_PLAN.md` (Phase 1 consolidate & wire →
   Phase 2 depth → Phase 3 advanced).
3. **G-4 + G-3** — small, independent, high-value; slot into either mode's
   early PRs.
4. **G-8** — (b)+(a) in one commit (same file), then (c), (d), (e). Feeds
   Forge Phase 2 (F2-4 job visibility).
5. **G-2** — module intros; unblocks authored-content play.
6. **G-1** — (a)+(b) together, then (c), then (d) live verification.
7. **G-6** — phases 1→3 (phase 3 can be prototyped early).
8. **G-9** — phase 1 measurement first; flagging before any hard rejection.
   Feeds Forge F2-3 and GM Assistant P1.1.
9. **G-7** — only with explicit product commitment.

## Verification (applies to all)

- `uv run pytest packages tests -q` green; new behavior gets tests per repo conventions.
- `uv run ruff check packages`; `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`;
  `python scripts/check_layer_dependencies.py`.
- Live verification for play-affecting changes: `scripts/live_llm_gm_vs_player_test.py`
  across ≥ 2 worlds.
- After each gap lands: tick its boxes here and update `docs/STATUS.md` (and the
  source audit/direction docs where applicable).

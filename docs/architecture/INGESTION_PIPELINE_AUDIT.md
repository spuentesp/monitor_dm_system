---
description: "Audit of the game-system ingestion + character-creation parsing pipeline: findings and a phased remediation plan."
tags: [architecture, ingestion, analyzer, indexer, character-creation, validation]
layer: 1
---

# Ingestion Pipeline Audit & Remediation Plan

> **Status (verified 2026-07-23, direct code inspection):** Finding 1 —
> parser gaps FIXED (regex parsing replaced by LLM structured extraction);
> the Narrator-hallucination-on-empty-sheet guard is still OPEN. Finding 2 —
> semantic step_type validation FIXED; the one-off hand-fix of the legacy
> VtM seed doc is unverified. Finding 3 — PARTIAL (`hand_authored` marker +
> provenance/dedup audit script landed; requiredness not enforced; the
> retire/relabel decision on `a227676a...` is still open). Finding 4 —
> empty-shell doc unchanged; the code-side fixes it depended on (Findings
> 2/5/6) are now in place, real re-ingestion still pending. Finding 5 —
> FIXED (`needs_review`/`degenerate_reason` + PARTIAL job status). Finding
> 6 — FIXED (fixture-PDF regression test in the suite). Finding 7 — dedup
> audit tooling + upload-time content-hash rejection landed; PDF-structure
> caching still open. Finding 8 — FIXED (targeted update + hand-author
> paths, with semantic validation).

> Triggered by a live full-loop run (2026-07-21, VtM `vtm_primogen` scenario) whose
> character sheet came out with default attributes, garbage skills, and a
> Narrator-hallucinated clan. Investigating *why* traced through character
> creation parsing, into the seed data, and finally into the PDF ingestion
> pipeline itself. This doc is the record of that investigation and the plan
> to fix what it found.

---

## 0. How to read this doc

Each finding has: **Evidence** (what was actually observed, with commands/paths),
**Root cause** (traced to specific code), and **Plan** (concrete steps, ordered).
Findings are ordered from the symptom outward to the root causes, since that's
the order they were discovered and each one explains the next.

---

## 1. Finding: Character sheet came out empty/wrong after a live LLM-driven creation dialogue

### Evidence

Live run `tests/e2e/logs/full_loop/full_loop_vtm_primogen_new_20260721T170454Z.md`
(and its predecessor). The player LLM answered all 8 character-creation steps in
character-appropriate detail. The persisted `CharacterSheet` in MongoDB came out:

```json
"stats": {"STR": 1, "DEX": 1, "STA": 1, "CHA": 1, "MAN": 1, "COM": 1, "INT": 1, "WIT": 1, "RES": 1},
"skills": {"Combat": true, "Arts": true, "Meditation": true, "Weaponry": true,
           "Brawl": true, "Intimidation": true, "Athletics": true},
"background": null
```

All attributes are still at their schema default (1). Skills are boolean flags
(not dot ratings) mixing tokens from **two different, unrelated creation
steps**. No clan/class field was ever stored. Yet the Narrator's live
narration referred to the character as "young Ventrue" — a clan the player
never said (they said "Toreador," then a typo "Torene," several times).
The Entity node's `description` field is also blank.

### Root cause — two parser gaps in `character_creation_loop.py`

1. **`_FIELD_KEYS_BY_STEP`** (the table that isolates which single line of the
   LLM's multi-field answer dump belongs to the *current* step) has entries
   for `choose_name`, `choose_concept`, `choose_class`, `choose_species`,
   `choose_disciplines`, `choose_background`, `choose_equipment`,
   `choose_feats`, `choose_spells`, `write_backstory` — but **no entry for
   `generate_attributes`/`assign_attributes` or `choose_skills`**. So for
   exactly the two step types that matter most mechanically, the isolation
   step is skipped and the parser receives the player's *entire* multi-field
   answer dump (Name/Clan/Class/Dot Assignments/Skill Picks/Discipline Names
   all together) instead of just the relevant line.

2. **`_parse_attribute_assignment`** only recognizes two input shapes:
   explicit `STR=4` pairs, or VtM5-style category totals (`"5 Physical, 3
   Social, 4 Mental"`). The player's actual phrasing —
   `"5 Willpower, 3 Stamina, 2 Strength"` (individual attribute names,
   number-first, and "Willpower" isn't even an Attribute in this system, it's
   a Resource/Track) — matches neither shape. Because the function's contract
   is "never crash, never lose existing values," an unrecognized shape
   silently leaves the attributes at their defaults with no error surfaced
   anywhere.

The Narrator's "young Ventrue" line is not grounded in anything — it's a
plain hallucination, invented because the actual character state it should
have been reading from (`background: null`, no clan field at all) had nothing
to read.

### Plan

- [x] Add `generate_attributes`/`assign_attributes` and `choose_skills` to
      `_FIELD_KEYS_BY_STEP` so `_extract_field` isolates the "Dot
      Assignments:" / "Skill Picks:" line before it ever reaches the parser.
- [x] Extend `_parse_attribute_assignment` with a third pass: individual
      attribute-name matching (`"2 Strength"`, `"Strength 2"`, `"Strength: 2"`)
      against the system's own attribute list (`game_context["attributes"]`),
      not just the two current fixed shapes — this generalizes across game
      systems instead of hardcoding VtM's Physical/Social/Mental categories.
- [x] When a Resource name (e.g. "Willpower") appears where an Attribute was
      expected, route it to `state.resources` instead of silently dropping it
      — the player's intent is usually genuine, just mis-typed.
- [x] Add a **loud** log (not silent) whenever
      `_parse_attribute_assignment`/`_parse_skill_choices` returns unchanged
      input for a non-skip, non-empty answer — this is exactly the class of
      failure that went unnoticed for months.
- [x] Add hermetic tests reproducing the exact live-run answer strings above
      (not synthetic clean-format strings) so regressions in real LLM
      phrasing are caught, not just regressions in the two narrow formats the
      parser already expects.

> **Status (verified 2026-07-23):** All five items done. Item 1: the three
> step types are in `_FIELD_KEYS_BY_STEP`
> (`packages/agents/src/monitor_agents/loops/character_creation_loop.py:244-246`,
> comment cites this audit). Items 2–3 landed differently than planned —
> instead of a third regex pass, `_parse_attribute_assignment` was replaced
> by LLM structured extraction: `AttributeAssignmentModule` grounded in the
> schema's attribute *and* resource names (so "Willpower" routes to
> `state.resources`, covering item 3), plus `SkillSelectionModule` and
> `OptionMatchModule`
> (`character_creation_loop.py:692-798`, `:801-840`, `:843-872`). Item 4:
> extraction failures log a warning (`character_creation_loop.py:775-776`,
> `:793-796`). Item 5: the exact live-run strings (`"Dot Assignments: 5
> Willpower, 3 Stamina, 2 Strength"`) are reproduced in
> `tests/unit/test_cc_parsers.py` and
> `tests/behavior/test_character_creation_loop_choreography_behavior.py`.
>
> Remaining (verified 2026-07-23):
> - Narrator hallucination on empty sheets: the Actor block omits lines
>   when the sheet is empty, and no "do not invent character facts"
>   instruction exists anywhere in the narrator/GM prompts
>   (`packages/agents/src/monitor_agents/narrator.py:306-328`; `gm_agent.py`
>   and agent folders checked). The "young Ventrue" class of failure is still
>   possible.

---

## 2. Finding: The VtM seed data itself has two mislabeled character-creation steps

### Evidence

```
1 | choose_class      | Choose Clan
2 | generate_attributes | Assign Attributes
3 | choose_skills     | Assign Skills
4 | choose_class      | Select Disciplines      <- wrong type
5 | choose_skills     | Choose Advantages       <- wrong type
6 | calculate_derived | Calculate Derived Stats
7 | write_backstory   | Define Touchstones & Convictions
8 | write_backstory   | Write Sire & Embrace
```

(`game_systems` doc `a227676a-edab-4a43-80d9-8f76b74ff289`, "Vampire: The
Masquerade 5th Edition" — the doc currently referenced by
`scripts/e2e_full_loop_scenarios.py`.)

Step 5's own instructions read *"Select Backgrounds and Merits... Allocate 7
dots across Backgrounds. Choose Flaws for bonus XP"* — nothing about skills —
yet it's typed `choose_skills`. That's precisely why the final skills dict
above is contaminated with `Brawl`/`Intimidation`/`Athletics`: those came from
step 5's answer, which the parser dutifully treated as a second
skill-assignment step because of the step_type label. Step 4 ("Select
Disciplines") is typed `choose_class`, identical to step 1 — it doesn't crash
(there's a fallback key when `"class"` is already taken) but it extracts the
wrong field from the player's answer (the `"Class:"` line instead of
`"Discipline Names:"`).

### Root cause

Traced to `analyzer/_game_system_persistence.py::_build_character_creation`,
which builds each `CreationStep` from raw LLM-extracted dicts:

```python
try:
    step_type = CreationStepType(s.get("step_type", "custom"))
except ValueError:
    step_type = CreationStepType.CUSTOM
```

This only guards against a *syntactically invalid* enum value (falls back to
`CUSTOM`). It has **no semantic check** that the chosen `step_type` actually
matches the step's own `title`/`instructions` — so an LLM extraction call
that plausibly-but-wrongly labels a Backgrounds/Merits/Flaws step as
`choose_skills` sails straight through, unvalidated, into the persisted,
actively-used document.

### Plan

- [x] Add a semantic cross-check in `_build_character_creation`: for each
      step, verify the step_type's expected keywords (reuse
      `_FIELD_KEYS_BY_STEP`'s vocabulary — `background`/`backgrounds` for
      `choose_background`, `discipline`/`powers` for `choose_disciplines`,
      etc.) actually appear in the step's own `title`+`instructions` text.
      Mismatch → log a WARNING and either re-classify to the type suggested
      by the *content* or fall back to `CUSTOM` (safe, no field-extraction
      applied, but also no silent misrouting).
- [x] This is generic across game systems, not a VtM-specific patch — every
      ingested system benefits from the same check.
- [ ] Hand-fix this specific document's steps 4/5 as an immediate, separate
      one-line Mongo update (`choose_disciplines` / `choose_background`) so
      today's testing isn't blocked on the broader ingestion-pipeline plan
      below.

> **Status (verified 2026-07-23):** Items 1–2 done — `_step_type_matches_content`
> relabels mismatched steps to `custom` with a warning
> (`packages/agents/src/monitor_agents/analyzer/_game_system_persistence.py:343-354`,
> `:372-397`), generic across game systems, and the same check is enforced in
> the UI router (`packages/ui/backend/src/monitor_ui/routers/entities.py:722`).
>
> Remaining (verified 2026-07-23):
> - The one-off hand-fix of the legacy VtM seed doc's steps 4/5 is a data
>   operation, not verifiable from code; no migration/fix script for that
>   specific document was found.
> - `_build_typed_list` still silently skips invalid items
>   (`_game_system_persistence.py:137`) — the same silent-degradation class
>   as Finding 5, at the per-item level.

---

## 3. Finding: The active "5th Edition" doc has no traceable origin — it looks confabulated

### Evidence

```
a227676a-edab-4a43-80d9-8f76b74ff289 | Vampire: The Masquerade 5th Edition | is_builtin=True | created 2026-05-31 | source_ids: None
```

No `source_ids`, `source_id`, or `knowledge_pack_id` populated. The only VtM
PDF ever uploaded (`WtWf-VtM20th.pdf`) is the **20th Anniversary** edition —
a different edition than what this doc claims. Cross-checking the
`documents` collection: the *first* upload of that PDF (2026-04-08) sat at
`extraction_status: "pending"` and was never processed; the *only* other
attempt before this doc's creation date failed outright
(2026-06-12, after the doc already existed). At the moment this doc was
created (2026-05-31), **no successful extraction of any VtM source material
existed anywhere in the system.**

### Root cause

The `game_systems` schema has no required provenance field, so nothing
prevented (and nothing records) this document being produced by directly
prompting an LLM for "a VtM 5e game system definition" with zero grounding in
an actual rulebook — separate from, and never routed through, the PDF
ingestion pipeline at all. It happens to be detailed and plausible-sounding
(general LLM training data on VtM is rich), which is exactly what makes an
ungrounded document dangerous: it's indistinguishable from a properly-ingested
one until you check for a source trail and find there isn't one.

### Plan

- [ ] Make `source_document_id` (or `source_ids`) a **required** field on any
      newly-created `game_systems` document going forward; `is_builtin: true`
      hand-authored systems are the sole exception and must set a
      `hand_authored: true` marker instead so the two provenance stories are
      distinguishable at a glance.
- [x] Add a one-time audit query/report enumerating every existing
      `game_systems` doc lacking provenance, so this class of "looks real,
      isn't" content doesn't lurk elsewhere for other systems too.
- [ ] Decide, once re-ingestion (Finding 5) produces a usable result: either
      retire `a227676a...` in favor of a properly-sourced, honestly-named
      "20th Anniversary" system, or keep it explicitly labeled as a
      hand-authored reference system (not "5th Edition" — we don't have 5e
      source material at all).

> **Status (verified 2026-07-23):** Partially addressed. The `hand_authored`
> marker from item 1 exists on the schema and is recorded by the create path
> (`packages/data-layer/src/monitor_data/schemas/game_systems.py:765-775`,
> `:859`; `packages/data-layer/src/monitor_data/tools/mongodb_tools/game_systems.py:150`,
> description cites this audit), but `source_document_id` is still
> `Optional` with no requiredness validation — a new doc can still be
> created with neither a source nor `hand_authored: true`. Item 2 done:
> `scripts/audit_ingestion_documents.py` reports every `game_systems` doc
> with neither `source_document_id` nor `hand_authored=True`
> (read-only by default; docstring cites this finding).
>
> Separately, entity-level provenance also landed: extraction prompts now
> require `source_ref` + `evidence_refs_json`
> (`packages/agents/src/monitor_agents/analyzer/analyzer.py:101-102,145,228`),
> schemas carry `source_ref`
> (`packages/data-layer/src/monitor_data/schemas/knowledge_packs.py:122` + 8
> more), and chunks carry `section_path`/`page_number`
> (`packages/agents/src/monitor_agents/analyzer/_core.py:1663-1665`).
>
> Remaining (verified 2026-07-23):
> - Requiredness: nothing rejects a new `game_systems` doc that has neither
>   `source_document_id` nor `hand_authored: true`.
> - The retire/relabel decision on `a227676a...` (item 3) — still pending
>   the real re-ingestion (Finding 4 / sequencing step 6).
> - Entity-level residual: powers/subsystems merged into `rules` get
>   `source_ref=None`
>   (`packages/agents/src/monitor_agents/analyzer/_game_system_persistence.py:282,303`).

---

## 4. Finding: The one *real* PDF-ingested VtM doc is an empty shell

### Evidence

```
2418a85d-bfec-4567-b439-0b9fc08ea0bf | Vampire: The Masquerade 20th Anniversary Edition | is_builtin=False | created 2026-06-22 18:01:17
```

Created 9 minutes after `documents` record `353d48f8-...` (same PDF,
`extraction_status: "completed"`, `snippet_count: 3107`) finished indexing.
Despite that successful large-scale indexing pass, the resulting
`game_systems` doc is essentially empty:

```json
"attributes": [], "skills": [], "resources": [], "character_creation": null,
"core_mechanic": {
    "type": "d20",
    "formula": "Auto-detected — review and correct as needed",
    "success_type": "meet_or_beat"
}
```

`"type": "d20"` / `"meet_or_beat"` are hardcoded placeholder defaults in
`_game_system_persistence.py` (`cm_data.get("type", "d20")`,
`.get("formula", "Auto-detected — review and correct as needed")`) — d20 is
flatly wrong for VtM's d10 dice-pool mechanic. Their presence means the
core-mechanic-detection LLM call returned nothing usable, and every
downstream extraction (`_extract_character_sheet` et al.) also came back
empty — that function literally starts with `if not sections: return
{empty...}`, meaning **zero** sections were judged relevant for this
3,107-snippet, 529-page book.

### Root cause investigation — traced through the pipeline, live, at zero API cost

Re-ran the actual PDF (fetched via `MinIOClient.download`, not raw filesystem
— MinIO stores objects in its own erasure-coded format) through today's live
code, locally:

1. **`extract_pdf_structure()`** — works perfectly. 167 real TOC/bookmark
   entries (`fitz.get_toc()`), correctly nested (Book → Chapter → Section),
   clean extracted text (`"CHAPTER FOUR: DISCIPLINES... the vampire spends a
   blood point..."` — no OCR garbage).
2. **`system_section_score()`** — works excellently. Scored all 167 real
   sections; **"Character Creation Process" ranks #1** (score 27),
   "Abilities" ranks #2 (25), "Attributes" makes the top 12. Only 34/167
   sections scored zero (mostly pure-lore chapters, as expected).
3. **Section text quality** — the actual "Character Creation Process" text is
   pristine: correct 7/5/3 attribute priority, 13/9/5 abilities priority,
   the real clan list, 20th-Anniversary-specific terminology (Appearance,
   Perception) — exactly what a downstream LLM extraction call needs.

**Conclusion: the current PDF-parsing and section-relevance layers are not
the problem** — they work correctly against the real book, today, for free.
The empty `2418a85d` document was very likely produced by an **earlier,
less mature version of this pipeline** (these modules — `_summaries.py`,
`_sections.py`, the TagPool pre-filter — show signs of having been built up
incrementally) or hit a **transient failure in the actual extraction LLM
call** that wasn't retried (we have a directly-recorded sibling failure on
this same PDF: `"InternalServerError: ... Connection error"`, 2026-06-12).
Either way, nothing has verified since 2026-06-22 whether a fresh attempt,
with today's code, still fails — and the silent-default behavior in finding
5 means we'd have no way to tell even if we tried.

### Plan

See Finding 5/6/7 below — this finding's root cause *is* the combination of
those three gaps, not a single fix.

> **Status (verified 2026-07-23):** The code-side gaps this finding depended
> on are now closed — Finding 5's degenerate-extraction guard, Finding 2's
> semantic step_type check, and Finding 6's fixture-PDF regression test are
> all in place (see those findings). The `2418a85d` empty-shell document
> itself and the real re-ingestion of `WtWf-VtM20th.pdf` it calls for
> remain pending (sequencing step 6).

---

## 5. Finding: Silent degenerate-extraction fallback hides total pipeline failure

### Evidence

`_game_system_persistence.py`:

```python
cm_type = CoreMechanicType(cm_data.get("type", "d20").lower())
cm_success = SuccessType(cm_data.get("success_type", "meet_or_beat").lower())
formula = cm_data.get("formula", "Auto-detected — review and correct as needed")[:200]
```

These fire whenever the LLM extraction call for core-mechanic detection
returns an empty/missing dict — which is exactly what happened for the VtM
ingestion. The resulting document is **indistinguishable from a
successfully-extracted d20 system** unless someone happens to know VtM isn't
d20 and goes looking. No error, no warning, no flag.

### Plan

- [x] Replace bare defaults with an explicit "extraction incomplete" state:
      either leave `core_mechanic` fields `None` and let downstream code
      handle absence explicitly, or set a `needs_review: true` /
      `extraction_status: "degenerate"` marker on the document.
- [x] Apply the same principle to `_extract_character_sheet`'s
      `if not sections: return {all-empty}` path and any other
      "gracefully degrade to nothing" branch in the Analyzer — degrading
      gracefully is right for *partial* misses, wrong for *total* ones. A
      document with **zero** populated fields across attributes/skills/
      resources/character_creation should never be persisted as if it
      succeeded.
- [x] Surface a clear signal at the call site (`save_game_system`) so a
      caller — a script, a UI action, a test — can immediately tell "this
      ingestion produced nothing usable" instead of discovering it three
      dependency layers later, in a live gameplay transcript, weeks after
      the fact (exactly how this was actually discovered).

> **Status (verified 2026-07-23):** All three items done.
> `_detect_degenerate_extraction` flags total misses and the result is
> persisted as `needs_review=True` + `degenerate_reason` on the document
> (`packages/agents/src/monitor_agents/analyzer/_game_system_persistence.py:582-616`,
> `:717-718`, `:743-744`; schema fields at
> `packages/data-layer/src/monitor_data/schemas/game_systems.py:776-789`,
> descriptions cite this audit). Batch LLM failures also surface as a
> PARTIAL status with `failed_batches`/`failed_sections` on the
> `IngestionJob` (`packages/agents/src/monitor_agents/ingestion_pipeline.py:598-667`),
> so the call-site signal of item 3 exists at both the document and job
> level. The fixture-PDF regression test exercises the guard end to end
> (Finding 6).
>
> Remaining (verified 2026-07-23):
> - `_build_typed_list` still silently skips invalid items
>   (`_game_system_persistence.py:137`) — per-item degradation without a
>   log, the same class of problem one level down.

---

## 6. Finding: No regression test exercises the real end-to-end ingestion pipeline

### Evidence

Nothing in the test suite runs `Analyzer.analyze_source` (or equivalent)
against a real PDF fixture and asserts the resulting `game_systems` document
is non-degenerate. Every existing Analyzer test mocks the LLM extraction
calls, which is correct for unit-level coverage but means **the actual
failure mode here — real content producing an empty result — has zero
coverage anywhere.** This is why it sat unnoticed from 2026-06-22 until this
audit.

### Plan

- [x] Add a small, checked-in fixture PDF (a few pages, real bookmarks,
      hand-verified expected attributes/skills/character-creation steps —
      NOT a 112MB rulebook) specifically for exercising the full ingestion
      path with only the LLM calls mocked at the boundary (real PDF parsing,
      real section scoring, real `_build_character_creation` assembly).
- [x] Assert: `attributes` non-empty, `character_creation.steps` non-empty
      AND each step's `step_type` semantically matches its title (this
      exercises the Finding 2 fix), `core_mechanic.type` is not the bare
      default unless the mocked LLM response explicitly returned nothing.
- [x] Wire this into the same "nothing is done until tested" discipline as
      the rest of this branch — this is the single test that would have
      caught everything in Findings 1–5 months ago.

> **Status (verified 2026-07-23):** All three items done.
> `tests/fixtures/ingestion/tiny_rulebook.pdf` is checked in, and
> `packages/agents/tests/test_ingestion_fixture_regression.py` runs real
> `extract_pdf_structure()` + real `system_section_score()` + real
> `_build_character_creation` / `_detect_degenerate_extraction` against it
> with only the two DSPy calls mocked at the boundary. It asserts non-empty
> attributes, a non-bare-default core mechanic, semantic step_type validity
> (a deliberately mislabeled step must be relabeled to `CUSTOM`, exercising
> Finding 2), and that a healthy extraction does NOT trip the Finding 5
> guard. The test module's docstring cites this audit.

---

## 7. Finding: Redundant re-uploads and test-fixture noise in MinIO + `documents`

### Evidence

`infra/minio/data/monitor/uploads/` has 49 PDF objects across 60 `documents`
records. Real content is duplicated repeatedly: `WtWf-VtM20th.pdf` uploaded
5×, `Death_in_Space_Core_Rules.pdf` ~10×, `7thSea_DTRPG...` 2×. A large
fraction of the rest (`probe1`–`probe5`, `t1`, `t2`, `corrupt.pdf`,
`corrupt2.pdf`, `harrowfen`, `ashfall`, `ashfall_compact`, `millhaven-test`)
are clearly automated test/probe fixtures, several repeated across many
throwaway universe_ids.

MinIO stores each object in its own erasure-coded on-disk directory —
**not** a plain file; must go through the S3 API / `MinIOClient`, never raw
filesystem deletion (confirmed while investigating this: `fitz.open()` on the
raw upload directory path fails immediately with `FileDataError`).

### Plan

- [x] Enumerate `documents` records grouped by `filename` +
      `file_size_bytes` (a cheap proxy for content-identity without hashing
      every object); for each real content group, keep exactly the one
      record with `extraction_status: "completed"` and the highest
      `snippet_count` (or the most recent if none completed), delete the
      rest via `MinIOClient.delete()` + the corresponding `documents` Mongo
      record.
- [x] Delete all `probe*`/`t1`/`t2`/`corrupt*` test-fixture uploads outright
      — they carry no real content and were never meant to persist.
- [x] Add upload-time content-hash dedup (reject or silently point at the
      existing record when an identical-hash file is re-uploaded) so this
      doesn't reaccumulate.
- [ ] Cache `extract_pdf_structure()`'s output by content hash — it's pure
      and deterministic; repeated attempts on the same PDF (which happened
      5× here) shouldn't re-parse 529 pages of PDF structure each time.

> **Status (verified 2026-07-23):** Items 1–2 are implemented by
> `scripts/audit_ingestion_documents.py` (docstring cites this finding):
> read-only-by-default grouping by `(filename, file_size_bytes)` with
> keep-best/delete-rest reporting, filename-pattern flagging of probe/test
> fixtures, and a destructive `--apply-dedup` path that deletes via the
> MinIO client after a typed confirmation. Item 3 done: the ingestion
> pipeline computes a SHA-256 content hash before touching the database and
> points at the existing record when identical content is re-uploaded
> (`packages/agents/src/monitor_agents/ingestion_pipeline.py:300-343`,
> comment cites this finding).
>
> Remaining (verified 2026-07-23):
> - `extract_pdf_structure()` output is still not cached by content hash —
>   no caching layer found in `pdf_processing.py`, `indexer.py`, or
>   `ingestion_pipeline.py` (item 4).
> - Whether `--apply-dedup` has actually been run against the live MinIO /
>   `documents` data is a data operation, not verifiable from code.

---

## 8. Finding: No way to fix or hand-author a `game_systems` document after ingestion

### Evidence

Every gap found above (Findings 1–5) currently has exactly one remedy
available: full re-ingestion, or a raw, ad-hoc Mongo `update_one` run by
hand from a Python shell (as done during this very audit). There is no
supported tool, MCP method, or CLI command for: patching a specific field of
an already-ingested system, or authoring a system from scratch without a
source PDF (e.g. a homebrew system, or a well-known system we choose to
hand-author deliberately, like `vtm_game_system.py` already does once).

### Plan

- [x] Add `mongodb_update_game_system` (or equivalent MCP tool /
      `game_systems.py` router endpoint) supporting targeted field patches —
      e.g. relabel one `character_creation.steps[i].step_type`, fill in a
      missing attribute, correct `core_mechanic` — without touching anything
      else on the document. Mirrors the existing `mongodb_update_*` pattern
      used elsewhere in this codebase (e.g. `mongodb_update_npc_profile`).
- [x] Add a `mongodb_create_game_system` path for hand-authoring (formalizing
      what `vtm_game_system.py` already does ad hoc) with the same schema
      validation the ingestion path uses, so hand-authored and ingested
      systems are structurally identical and both usable everywhere the
      Analyzer's output is.
- [x] Both paths should run through the same semantic validation from
      Finding 2/5 — a hand-author or hand-patch should not be able to
      introduce the same class of step_type/content mismatch either.

> **Status (verified 2026-07-23):** All three items done.
> `mongodb_create_game_system` and `mongodb_update_game_system` exist as
> data-layer tools
> (`packages/data-layer/src/monitor_data/tools/mongodb_tools/game_systems.py:88`,
> `:335`) with router endpoints in the UI backend
> (`packages/ui/backend/src/monitor_ui/routers/entities.py:589`, `:729`) and
> coverage in `packages/data-layer/tests/test_tools/test_game_system_tools.py`
> and `packages/ui/backend/tests/test_systems_hand_author_and_patch.py`.
> Hand-authored systems are marked via the `hand_authored` flag (Finding 3).
> Item 3: the Finding 2 semantic step_type check is enforced in the UI
> router's update path
> (`packages/ui/backend/src/monitor_ui/routers/entities.py:722`).

---

## Suggested sequencing

> **Status (verified 2026-07-23):** Steps 1–5 are done in code — Finding 5's
> degenerate-extraction guard, Finding 2's semantic validation, Finding 1's
> parser fixes, Finding 6's fixture-PDF regression test, and Finding 7's
> dedup tooling + upload-time content-hash rejection are all in place (see
> each finding's status note). Steps 6–8 remain: the real re-ingestion of
> the deduplicated `WtWf-VtM20th.pdf` has not been re-run/verified, so the
> Finding 3 retire/relabel decision (step 7) is still blocked on it. Step 8's
> tooling (Finding 8) turned out to be needed earlier and already exists.
> Two new open items surfaced during verification that belong in this
> sequence: the Narrator-hallucination guard on empty sheets (Finding 1
> remainder) and `_build_typed_list`'s silent item-skipping (Findings 2/5
> remainder).

The findings compound — fixing later ones without earlier ones just
reproduces silent failure with better tooling. Recommended order:

1. **Finding 5** (fail loud on degenerate extraction) — cheapest, and
   without it every subsequent re-ingestion attempt is unverifiable.
2. **Finding 2** (semantic step_type validation) — cheap, generic, prevents
   the exact bug that started this whole investigation from recurring in
   *any* future ingestion, hand-authored or automated.
3. **Finding 1** (character-creation parser gaps) — unblocks correct
   character sheets today, independent of the ingestion-side fixes.
4. **Finding 6** (regression test with a small fixture PDF) — write this
   *before* attempting the real re-ingestion in step 6, so the real attempt
   has something trustworthy to compare against.
5. **Finding 7** (dedupe MinIO/`documents`) — cheap, mechanical, unblocks a
   clean re-ingestion attempt without redundant noise.
6. **Re-run real ingestion** against the deduplicated `WtWf-VtM20th.pdf`
   with fixes 1/2/5 in place; compare the result against both the current
   "5th Edition" doc and known-correct VtM 20th Anniversary rules.
7. **Finding 3** (retire or relabel the ungrounded "5th Edition" doc) —
   decide once step 6's result is in hand.
8. **Finding 8** (fix/adjust + create tooling) — build once we know, from
   steps 6/7, exactly what shape of manual correction is actually needed in
   practice.

## See Also

- [De-heuristic Principle](./DE_HEURISTIC_PRINCIPLE.md) — why
  `system_section_score`'s keyword pre-filter is a deliberate, documented
  exception (cost-driven, targets short structural headings) rather than a
  violation of that principle.
- [Data Model Workflow](../2_architecture/data_model_workflow.md) — where `game_systems`
  sits relative to the rest of the data layer.

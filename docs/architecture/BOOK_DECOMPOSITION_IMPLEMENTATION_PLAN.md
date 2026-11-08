# Book Decomposition Implementation Plan

> Status: **implemented on branch `feat/book-decomposition-i17`, 2026-11-04**. Storage has run on real MongoDB and
> Neo4j, and one chapter has run with live models, with 27 of 30 sampled claims labeled canon as written.
> Use case: [`I-17`](../use-cases/epic-2-ingestion-I/I-17/I-17-specification.md).
> Design and measurements: [Book Decomposition Plan](BOOK_DECOMPOSITION_PLAN.md).

This moves the prototype into the real ingestion pipeline, one file at a time. **No step calls a live model.** Tests use scripted models, and PDF work is measured directly from the PDF.

## What was built

| Phase | Result | Measured or tested |
|---|---|---|
| **B. PDF reader** | `extract_pdf_structure` reads through the book tree | On Dune: section text from 5.01× the book to about 1×, chunks from 3,730 to 889, all 19,630 lines accounted for, including 102 the old reader lost before the first bookmark |
| **C. Analyzer sampling** | Reads all matches, then an even, repeatable sample, and logs truncation | 9 sampler tests. Chunks reaching the model are still capped at 512 |
| **D. Small fixes** | Audit doc corrected, the analyzer's limit now sits 5 minutes inside the job's, and the unused loop, triage, mechanics and vision code plus a stale artifact removed | Timeout tests and the full suite |
| **E. Storage** | `book_records` and `book_leases`, with MongoDB backends for outcomes, checks, coverage, trees and reviews | Mongomock tests, plus `test_book_real_databases.py` on real MongoDB: bulk writes, leases, resume and one pack per book |
| **F. Pipeline stage** | A separate background job behind `MONITOR_BOOK_DECOMPOSITION`, with pause, resume, cancel and UI progress | Backend and frontend tests. 40 Dune pages ran through the real service with scripted models |
| **G. Packs** | Reviewed claims become one review-ready pack with evidence. Rules go in `game_system_data.rules` | Mapper tests. The pack path is covered by the service tests |
| **H. Code checks** | Ruled tables, titles inside text, examples past sidebars, sample-character and book-description checks, and verb false alarms | On Dune: fragments from 1,055 to 896, empty divisions from 33 to 27, no text lost. On saved claims: the 2 sample-character claims and 4 book descriptions are caught |
| **I. Graph** | `domain` on claims, stored rules and lore trees, a graph step behind `MONITOR_BOOK_GRAPH`, graph search removed, and book structure stored in Neo4j through CanonKeeper behind `MONITOR_BOOK_NEO4J` | Scripted model tests, and `test_book_real_databases.py` on real Neo4j |
| **J. Prototype retired** | Kimi client, prototype script and its fixtures deleted | Full suite |

**Full Dune on real MongoDB 7 and Neo4j 5, with scripted models:** all 10,173 sentences covered, 9,909 claims kept, one pack with 4,619 rules and 5,290 lore facts, and 16,975 book nodes written to Neo4j in 2.4 seconds, in 63 seconds overall. A rerun made no extraction or verification calls and created no second pack. This proves the plumbing at full-book size, not claim quality, and real model calls will take far longer.

**First live run (2026-11-04), Chapter 7, pages 198–215, on real MongoDB with Mistral medium extracting and Mistral large reviewing:** all 576 sentences covered, no failed windows, 778 claims reviewed and 683 kept, with 55 merged, 38 sent to a person, 1 set aside as an example and 1 rejected. Extraction used about 122k input and 47k output tokens. The run was cut off by a 10-minute shell limit during review, and the resumed job reused all 778 saved checks and created one pack. It also showed that models write freeform entity types, so all 153 entities had become plain facts, which is now fixed. 

**First quality measure (30 kept claims from that run, labeled by a person with nothing pre-filled):**

| Measure | Result |
|---|---|
| Canon as written | **27 of 30 (90%)**. With only 30 claims, the true rate could plausibly be anywhere from about 73% to 98% |
| Flagged as dropping something | 10 of 30 |
| Scope | 16 general rule, 13 setting canon, 1 single example |

- **The 3 not canon:** one lost its subject, saying "Specialist" where the book means specialist troops. One lifted a sentence about poison out of its poison snooper entry. One came from corrupted source text.
- **The 10 flagged:** most read as incomplete alone, such as a claim about bodkin blades or the Baradye pistol that doesn't say it's describing an item entry. Linked claims are meant to cover those. At least 2 lost a real limit: hunter-seekers require an inside agent, and kanly must follow the Great Convention. That's still the main known weakness.
- **What this can't show:** it only samples kept claims, from part of one mostly equipment and lore chapter (pages 198–215 of a chapter ending on page 225), so it says nothing about rules that were wrongly removed or never extracted.
- **A flaw in this sample:** 5 of the 30 claims were shown with their wording from before review, not the wording that reached the pack. Those 5 are being labeled again in final wording, so treat 27 of 30 as provisional.

**Second live run (2026-11-04), Chapter 5, pages 150–169, on the fixed reader:** all 585 sentences covered, no failed windows, 500 claims reviewed and 416 kept, with 20 merged, 35 set aside as examples, 25 sent to a person and 4 rejected. Extraction used about 84k input and 34k output tokens, and the job took about 8 minutes. The pack holds 337 rules, 38 entities, 35 axioms and 6 facts. Earlier prompt work used this chapter, so its quality may read better than an unseen one. Its sample also covers removed claims, without showing the labeler which were removed, to measure rules wrongly removed.

**Second quality measure (53 claims, 2026-11-05):** a person labeled only 10 of them, and Claude labeled the other 43, so **this is a rough check, not a measure**. Claude had also seen a few removal reasons before labeling.

| Group | Claims | Canon as written | Labeled by a person |
|---|---|---|---|
| Kept in the pack | 30 | 26 | 6, all canon |
| Rejected | 4 | 2 | 0 |
| Set aside as examples | 8 | 4 | 2, 1 canon |
| Sent to a person | 6 | 5 | 1, canon |
| Chapter 7 claims in final wording | 5 | 4 | 1, not canon |

- **A book conflict was settled without a person:** pages 159 and 166 say Determination re-rolls an entire dice pool, while the detailed rule on page 166 says any number of dice, and the example on page 167 re-rolls only some. Review kept "entire" and rejected "any number" as refuted, and this was sent to no one. Settling now goes to a person when each claim matches its own source, tested without a new model run.
- **Fixed after this check, without model calls:** large decorated first letters now rejoin their paragraphs, so "he best way" reads "The best way" again, and stat-block numbers no longer become headings. Headings fell from 1,176 to 914 on Dune, with nothing lost. Jobs now count claims sent to a person, which before showed up nowhere.
- **Entity names can lose words:** a person marked "Specialist" not canon because the book means specialist troops. Review's final wording keeps the short name, and this isn't fixed.
- **Sending claims to a person is doing its job, with false alarms:** most held claims were fine, but none reached the pack, so they depend on someone reviewing them.
- **Held claims can now be reviewed:** a job with claims waiting shows "Review claims". Each claim shows why it waits, the book's sentences, and for a contradiction the other side. A person can accept it, edit its wording first, or reject it. An accepted claim joins the book's pack, which still goes through pack review and CanonKeeper. Decisions are stored apart from the ledger, so a resumed run keeps them, and a rebuilt pack includes accepted claims. A pack already applied refuses new claims, and no decision can be made while the book is being decomposed. All 25 held claims from the Chapter 5 run load with their sources. Accepted claims also join the rules and lore trees, right away and on every later run. They join the graphs only when the graphs are next built, since that takes a model call.
- **Set-aside examples:** the rules they restate are often stated elsewhere, so most aren't lost.

**Corrupted text, found by these labels:** this PDF draws some text twice at one spot as a shadow effect, so paragraphs held repeated phrases. The reader now keeps it once, and the no-text-lost check accounts for what it removed, 4,515 characters on Dune. The same check found that ruled boxes around prose were being treated as tables, which wrongly removed them from sentence splitting. The live run predates both fixes, so re-extracting would change some of its claims.

To repeat the storage tests: `RUN_INTEGRATION=1 MONITOR_TEST_MONGO_URI=... MONITOR_TEST_NEO4J_URI=... uv run pytest packages/agents/tests/test_book_real_databases.py`. The Neo4j test connects without a password, so it needs a local server with authentication off. CI doesn't set these variables, so it skips them.

**Changes from the plan below:**

- **Storage (E):** one `book_records` collection with typed records, instead of one collection per type.
- **Not MCP tools (E3, E4):** the MongoDB storage functions aren't exported, so they need no auth entries.
- **Separate job (F4, F5):** decomposition runs as its own job after the normal ingest, on its own worker, instead of as a stage inside `ingest_file`. So the Analyzer still runs and its pack still exists. A book gets two packs for now.
- **Book with no bookmarks (H3):** already handled by font-detected headings in B2, so this needed no more code.
- **File logs (J3):** `ExtractionLog` and `CheckLog` stay, because tests and `scripts/answer_key_sheet.py` use them. The sheet can only read existing output folders until something writes that format again.
- **Neo4j (I4):** CanonKeeper does the writing, with `neo4j_merge_book_tree` authorized for CanonKeeper alone. That keeps the existing rule, so no decision or guard change was needed, which replaces this plan's earlier "widen the rule" recommendation. `BookNode` records never touch canon labels. It's off by default, because it adds book text to Neo4j.
- **Analyzer timeout (D2):** the UI route now passes a limit of the job's limit minus 5 minutes, so 40 minutes by default. A stuck provider now fails with a clear message instead of the generic job timeout. Callers with no job limit keep 180 minutes, and `MONITOR_ANALYZE_TIMEOUT` still caps it. An analysis taking 40–45 minutes used to pass if everything else was quick, and now fails. Real durations could still justify changing it.
- **Paragraph check:** with Kimi gone, it uses the review model and is off by default behind `MONITOR_BOOK_COVERAGE`, because Mistral was noisy at it.

## Audit against the plan

Every step below was checked against the code on 2026-11-04.

| Steps | State |
|---|---|
| A1–A3 | Done. PR #119 is open, labels are backed up, and each experiment has a decision |
| B1–B4, C1–C4 | Done and measured |
| D1–D3 | Done |
| E1, E2, E5–E8 | Done, and run on real MongoDB. E3 and E4 don't apply, because these aren't MCP tools |
| F1–F7 | Done, with the differences listed above |
| G1–G4 | Done |
| H1–H7 | Done. H3 needed no new code |
| I1–I4 | Done. I3's fixture was deleted, because nothing uses it after I2 |
| J1–J4 | Done |

**The plan's open checks, now settled:**

| Check | Answer |
|---|---|
| Old Qdrant points on re-ingest | A rescan deliberately reuses existing chunks, so old and new don't mix. Retrying a failed index now clears the source's chunks first. So **documents already indexed keep their old chunks until deleted and uploaded again** |
| `chunk_index` on older points | Handled: a missing value counts as 0, and the order is still repeatable |
| How indexes are created | `MongoDBClient._create_indexes`, which now covers `book_records` |
| Frontend and an unknown stage | It displays the stage as plain text, so nothing breaks |
| References to the unused loop | Only docs, which were updated |

**Found by this audit:** nothing ever set `stage_last_progress_at`, so the stale-job watchdog failed every job 45 minutes after it started, however well it was progressing. Every job update now sets it, and decomposition jobs send a heartbeat during quiet stretches.

## Outside this plan

These aren't steps here: the plan's steps call no live model, and it leaves retiring the Analyzer for later.

| Item | Why it's separate |
|---|---|
| Wider quality measure | One chapter is labeled. Rules pages and other books aren't, and nothing yet measures rules wrongly removed |
| One pack per book | With the flag on, the Analyzer still runs too, until the fields below are covered or found unnecessary |
| Short Dune quotes in a public repo | Removed at the owner's request, 2026-11-04, including from this branch's history |

**Fields only the Analyzer fills today (G4):** `random_tables`, `agendas`, `topologies`, `character_profiles`, `generation_templates`, `tone_profiles`, `plot_threads`, `entity_relationships`, chunk and section summaries, `source_mindscape`, `source_profile_data`, and the structured game system: attributes, skills, resources, tracks, conditions and the rest. Decomposition fills `axioms`, `lore_facts`, simple `entity_archetypes` and `game_system_data.rules`. So the Analyzer can't be retired for books until these are covered or found unnecessary.

## How to execute this

Work through the steps in order. Each step changes one source file and its test file, and leaves the suite green.

For each step:

1. Do its **Check first** items. If one contradicts the plan, stop and update the plan.
2. Write the failing test, then make the change.
3. Run the fast checks below.
4. Confirm its **Done when**.
5. Commit, with the use case ID in the message, and push.

```bash
# Fast checks, every step
uv run ruff check packages scripts
uv run mypy packages/data-layer/src packages/agents/src packages/cli/src packages/ui/backend/src --cache-dir /tmp/mypy-cache
uv run python scripts/check_layer_dependencies.py
uv run pytest <the step's test files> -q

# Full suite, at the end of each phase
uv run pytest packages tests -q --tb=short -p no:cacheprovider -n auto
```

**Rollback:** every step is one commit, so `git revert <sha>` undoes it, unless a step says otherwise.

**Rules that apply throughout:** never touch `tests/verification/**` or `tests/property/**`. Layers stay data-layer → agents → cli. Only CanonKeeper writes canon. Use `structlog`, not `print()`.

## Order at a glance

| Phase | What it delivers | Needs your decision? |
|---|---|---|
| [A. Cleanup and safety](#phase-a-cleanup-and-safety) | CI runs on the branch, labels are safe, experiments are sorted | Yes: labels, merge |
| [B. PDF reader](#phase-b-replace-the-pdf-reader) | Real uploads get the fixed reader | No |
| [C. Analyzer sampling](#phase-c-fix-the-analyzer-sampling) | The sample is repeatable and spans the book, at the same cost | No |
| [D. Small fixes and dead code](#phase-d-small-fixes-and-dead-code) | Stale docs and an unused loop are gone | Yes: timeout |
| [E. Storage in MongoDB](#phase-e-move-storage-to-mongodb) | Progress survives outside local files | No |
| [F. Pipeline stage](#phase-f-add-the-pipeline-stage) | Decomposition runs inside uploads, behind a flag, and can resume | Yes: which models |
| [G. KnowledgePack mapping](#phase-g-map-claims-to-knowledgepacks) | Claims can reach `ProposedChange` and canon | Yes: where rules go |
| [H. Code checks](#phase-h-improve-the-code-checks) | Better tables, headings and example detection | No |
| [I. Graph](#phase-i-finish-the-graph) | Stored domains and a stricter question test | Yes: Neo4j writer |
| [J. Retire the prototype](#phase-j-retire-the-prototype) | No parallel code path remains | No |

## Phase A: Cleanup and safety

**Already done:** the 4 local servers are stopped, and the graph viewers, graph output and browser profiles are deleted. Paid results and labels were kept.

### A1. Open a draft PR

- **No file changes.** Run `gh pr create --draft`.
- **Why first:** CI only runs on pull requests and on pushes to `master`, so nothing has checked this branch. The branch also changes CI itself, and a broken required check would block every later step.
- **Done when:** the `static` and `tests` jobs pass. Fix any failure before Phase B.

### A2. Protect the labels

- **The risk:** the only copies of your hand labels are `out/dune/answer-key.jsonl` and `out/dune-mistral/answer-key.jsonl`, in a gitignored folder. The repo is public and the row files hold book text, so they can't simply be committed.
- **Your decision:** where should they live? I recommend a private location outside the repo. The label files hold IDs and values and little book text, but check their notes first.
- **Done when:** a copy exists outside this working tree.

### A3. Decide what each experiment becomes

| Item | Decision | Reason | Done in |
|---|---|---|---|
| `book_decomposition/kimi_cli.py` | **Retire** | It reports no token counts, hits a 5-hour limit, and depends on a logged-in command line. It isn't suitable for production. | J1 |
| `graph` and `graph-questions` commands | **Retire the commands, keep the logic** | They become library code and tests. | J2 |
| `book_decomposition/knowledge_graph.py` | **Keep, reduced** | The graph structure is useful, but its search lost to keywords. | I2 |
| `scripts/prototype_book_decomposition.py` | **Retire last** | It's the only way to run the work until Phase F. | J3 |
| `scripts/answer_key_sheet.py` and `.html` | **Keep** as a developer tool | It's how quality gets measured. | Stays |
| `book_decomposition/answer_key.py` | **Keep** | Same reason. | Stays |
| `out/` | **Keep paid logs and labels** | They cost tokens, and old claims still cite the old tree. | Stays |

## Phase B: Replace the PDF reader

**Goal:** every PDF upload gets the lossless reader, with no change to how much the Indexer spends.

**Verified constraints:**

- `extract_pdf_structure` has a cache wrapper pinned by 4 tests, and 8 indexer tests patch it by name. So its name, signature and wrapper stay. Only `_extract_pdf_structure_uncached` changes.
- The Indexer makes up to one model call per section. So one bookmark division must stay one `SectionBlock`, or live upload costs change.
- `IngestedChunk.stable_id` includes the chunk's position and text, so re-ingesting a changed document produces new chunk IDs.

### B1. Measure before changing anything

- **Tool:** a throwaway script in the scratch folder, not committed.
- **Record, on `tiny_rulebook.pdf`, the other PDF fixtures and Dune:** section count, heading paths, characters per section, repeated text, and what `extract_tables_as_sections` returns.
- **Done when:** the old numbers are written down in the B4 commit message or the design doc.
- **Result (2026-11-04), current reader:**

| | `tiny_rulebook.pdf` | Dune, 339 pages |
|---|---|---|
| Bookmarks / sections | 5 / 5 | 732 / 732 |
| Empty sections | 0 | 0 |
| Alphanumeric characters on the pages | 966 | 892,837 |
| Alphanumeric characters across sections | 966 | **4,474,588 (5.01× the book)** |
| Lines in more sections than their pages explain | 0 | **19,417 of 19,630** |
| Lines missing from every section | 0 | 102, not yet examined |
| Largest section, alphanumeric characters | 287 | 214,558 |
| Table sections | 0 | 128 |
| Read time | Under 0.01 s | 4.22 s |

- **What this changes:**
  - On a bookmarked book, the current reader embeds and analyzes about 5 times the book's text, so the fix should cut chunks and embedding work by far more than the plan first assumed.
  - Section counts won't stay exactly equal, because bookmarks with no text of their own won't become sections. Earlier work found 57 empty divisions on Dune. Fewer sections can only lower categorization calls, but B3 must report the new count and chunk count.
  - `tiny_rulebook.pdf` is the only PDF in the repo, and it has no nesting. It can't show this bug, so B2 and B3 need generated PDFs with nested and same-page bookmarks, and one with no bookmarks.
  - B3 must explain the 102 missing lines: they may be real losses, or differences in how lines were compared.

### B2. `packages/data-layer/src/monitor_data/tools/ingest_tools/book_tree.py`

- **Add** `sections_from_tree(tree: BookTree) -> list[SectionBlock]`.
- **Behavior:**
  - One `SectionBlock` per division that has text, with its full heading path and depth.
  - A PDF with no bookmarks splits on `HEADING` nodes, or it would become one giant section.
  - Running headers and page numbers are left out.
  - A nested parent holds only its own text.
- **Check first:** importing `SectionBlock` from `_models.py` must not create an import cycle.
- **Test file:** `packages/data-layer/tests/test_book_tree.py`.
- **Done when:** tests cover nested bookmarks, same-page siblings, no bookmarks, an empty division, and no text repeated across sections.
- **Commit:** `feat(ingest): I-17 convert a book tree to section blocks`.

### B3. `packages/data-layer/src/monitor_data/tools/ingest_tools/pdf_processing.py`

- **Change** `_extract_pdf_structure_uncached` to call `decompose_pdf`, then `sections_from_tree`.
- **Keep:** the public function, the cache, `_deep_copy_sections`, and the empty-bytes guard.
- **Check first:**
  - `decompose_pdf` needs a document ID and title. Use the content hash and an empty title, as neither reaches the sections.
  - Find out which tests depend on old quirks. Fix a test only if it pinned a bug, and say so in the commit.
- **Test files:** `packages/data-layer/tests/test_db/test_ingest_tools.py`, `packages/agents/tests/test_indexer.py`, `packages/agents/tests/test_ingestion_fixture_regression.py`.
- **Done when:**
  - All three test files pass, including `test_real_section_scoring_ranks_schema_sections_above_lore`.
  - Section counts match B1 on bookmarked PDFs, or each difference is explained.
  - Text that a parent used to repeat is gone, and no text is lost.
- **Commit:** `fix(ingest): I-17 read PDF sections through the lossless book tree`.

### B4. `packages/agents/tests/test_ingestion_fixture_regression.py`

- **Add** a regression test on the real fixture: no text appears in two sections, and every extracted word is present.
- **Check first:** how does re-ingesting an existing document treat old Qdrant points? `ingest_file` looks documents up by content hash, so an unchanged file may never re-index, but this is unverified. If old points can linger, add a step here before continuing.
- **Done when:** the test fails against the old reader and passes against the new one.
- **Commit:** `test(ingest): I-17 pin that PDF sections neither repeat nor lose text`.

## Phase C: Fix the Analyzer sampling

**Goal:** a repeatable sample spread across the book, at the same cost.

**Verified:** `_core.py` scrolls Qdrant until `MAX_CATEGORY_CHUNKS` (512) in two places, near lines 1758 and 1895. Scroll order follows chunk IDs, which are hashes, so which chunks get read is effectively arbitrary.

**Not doing:** removing the cap. Reading everything would multiply model calls on every upload. Phase F replaces this path for books instead.

### C1. `packages/agents/src/monitor_agents/analyzer/_sampling.py` (new)

- **Add** `select_spread(chunks, limit)`: order by `chunk_index`, then take evenly spaced chunks up to `limit`, always including the first and last.
- **Test file:** `packages/agents/tests/test_analyzer_sampling.py` (new).
- **Done when:** the result doesn't depend on input order, is unchanged under the limit, and spans the book when over it.
- **Commit:** `feat(analyzer): I-17 add a repeatable, book-wide chunk sampler`.

### C2. `packages/agents/src/monitor_agents/analyzer/_core.py`, category scroll (near line 1758)

- **Change:** scroll every match first without the early cap, then apply `select_spread`.
- **Check first:**
  - Is `chunk_index` always in the payload? Handle older points without it.
  - Scrolling everything loads all the payload text. If that's too heavy, scroll IDs and `chunk_index` first, then fetch the chosen points.
- **Test file:** find the existing tests with `grep -l _MAX_CATEGORY_CHUNKS packages/agents/tests/*`, or add to the file from C1.
- **Done when:** a fake Qdrant with 2,000 chunks gives the same 512 on every run, spread across the book, and the same number of chunks as before reaches the model.
- **Commit:** `fix(analyzer): I-17 sample category chunks across the whole book`.

### C3. `packages/agents/src/monitor_agents/analyzer/_core.py`, source fallback scroll (near line 1896)

- **Same change and test as C2.** Also read the third scroll near line 3014 and decide if it needs this.
- **Commit:** `fix(analyzer): I-17 sample fallback chunks across the whole book`.

### C4. `packages/agents/src/monitor_agents/analyzer/_core.py`, truncation warning

- **Change:** log how many chunks were read of how many found, so truncation is visible.
- **Done when:** a test sees the counts in the log output.
- **Commit:** `feat(analyzer): I-17 report how much of a book the sample covers`.

## Phase D: Small fixes and dead code

### D1. `docs/architecture/INGESTION_PIPELINE_AUDIT.md`

- **Fix** line 518, which says `extract_pdf_structure` isn't cached. It is, per `pdf_processing.py` and `docs/STATUS.md`.
- **Commit:** `docs: correct the audit's claim about PDF structure caching`.

### D2. `packages/agents/src/monitor_agents/ingestion/agent.py`, analyzer timeout

- **Verified problem:** the comment says the default is 30 minutes and tighter than the job timeout, but the value is 180 minutes. On the UI route, the 45-minute `_JOB_TIMEOUT_SECS` always fires first, so this guard can't run there. It has been like this since the initial commit.
- **Your decision:** this changes behavior on every upload. What do real jobs take? Check durations in the `ingestion_jobs` collection before choosing:
  - 30 minutes, matching the comment and giving a clear stage failure, or
  - keep the value, and just correct the comment.
- **Until decided:** only the comment changes.
- **Commit:** `fix(ingest): correct the analyzer timeout comment`.

### D3. `packages/agents/src/monitor_agents/loops/ingestion_loop.py`

- **Verified:** a search of Python imports finds only its tests calling it. `TriageAgent` and `MechanicsArchitect` are used only from this loop.
- **Check first:** look for non-Python references, such as configs, string-based loading and docs. Keep it if any turn up.
- **Delete, in separate commits:** the loop and `packages/agents/tests/test_ingestion_loop.py`, then `ingestion/triage.py`, then `ingestion/mechanics_architect.py`, plus their tests. Check `ingestion/vision.py` the same way.
- **Done when:** the full suite passes and nothing references them.
- **Commit:** `chore(ingest): remove the unused ingestion loop`, and so on.

## Phase E: Move storage to MongoDB

**Goal:** the same resume and audit behavior, without local files. The file backend stays until Phase J, so the script keeps working.

**Verified:** `server.py` registers anything with the `mongodb_` prefix that `mongodb_tools` exports as an MCP tool, so every new tool needs an entry in `middleware/auth.py`.

**Design:**

| Today | Collection | Unique key |
|---|---|---|
| `tree.json` | `book_nodes` | `doc_id` + `node_id` |
| `ExtractionLog` | `book_outcomes` | `doc_id` + `window_id` + `run_key` |
| `CheckLog` | `book_checks` | `doc_id` + `check_key` + fingerprint |
| `CoverageLog` | `book_coverage` | `doc_id` + `key` + fingerprint |
| Ledger and reviewed claims | `book_claims` | `doc_id` + `claim_id` + `review_run` |
| `flock` | `book_leases` | `doc_id`, with an expiry |

Writes are upserts, so a repeated write is harmless and a crash can't leave a half-written line. A tree can have over 18,000 nodes, so nodes get their own documents, bulk-written.

### E1. `packages/data-layer/src/monitor_data/schemas/book_graph.py`

- **Add** record models for outcomes, checks, coverage, claims and leases.
- **Test file:** `packages/data-layer/tests/test_book_graph_schemas.py` (new).
- **Commit:** `feat(data): I-17 add book decomposition storage schemas`.

### E2. `packages/data-layer/src/monitor_data/tools/mongodb_tools/book_decomposition.py` (new)

- **Add** bulk upserts and reads per collection, using `mongodb_tools/ingestion_jobs.py` as the pattern, plus lease acquire, renew and release.
- **Lease behavior:** a second worker is refused while a lease is live, and can take over after it expires.
- **Check first:** where existing collections create their indexes. Unique indexes are what make upserts safe.
- **Test file:** `packages/data-layer/tests/test_tools/test_book_decomposition_tools.py` (new). Patch `get_mongodb_client` as `test_ingestion_job_tools.py` does.
- **Commit:** `feat(data): I-17 add book decomposition MongoDB tools`.

### E3. `packages/data-layer/src/monitor_data/middleware/auth.py`

- **Add** writes for `IngestionPipeline` only, and reads for `*`.
- **Check first:** whether these should be MCP tools at all. If they shouldn't be, don't export them, as was done for `book_tree`.
- **Done when:** a test proves another agent is refused a write.
- **Commit:** `feat(data): I-17 restrict book decomposition writes to the pipeline`.

### E4. `packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py`

- **Export** the tools, if E3 says so.
- **Commit:** `feat(data): I-17 export book decomposition tools`.

### E5. `packages/agents/src/monitor_agents/book_decomposition/store.py` (new)

- **Add** a `BookStore` protocol, a `FileBookStore` wrapping today's formats, and a `MongoBookStore` calling E2.
- **Test file:** `packages/agents/tests/test_book_store.py` (new). The same tests run against both backends.
- **Commit:** `feat(agents): I-17 add a book store with file and MongoDB backends`.

### E6. `packages/agents/src/monitor_agents/book_decomposition/ledger.py`

- **Change:** read and write through `BookStore`, and replace `flock` with the lease.
- **Test file:** `packages/agents/tests/test_book_recovery.py`.
- **Done when:** the crash, torn-write, resume and double-run tests pass on both backends.
- **Commit:** `refactor(agents): I-17 run the extraction log through the book store`.

### E7. `packages/agents/src/monitor_agents/book_decomposition/runner.py`

- **Change:** take a `BookStore` and renew the lease while running.
- **Test file:** `packages/agents/tests/test_book_recovery.py`.
- **Commit:** `refactor(agents): I-17 run ingestion rounds through the book store`.

### E8. `packages/agents/src/monitor_agents/book_decomposition/review.py`

- **Change:** route `CheckLog` and `CoverageLog` through `BookStore`, and save the ledger and reviewed claims.
- **Also fix:** review saves its ledger only at the end, so a stopped review shows nothing. Save progress as it goes.
- **Test file:** `packages/agents/tests/test_book_review.py`.
- **Commit:** `refactor(agents): I-17 store review progress through the book store`.

## Phase F: Add the pipeline stage

**Goal:** a flagged stage inside `IngestionPipeline`. With the flag off, nothing changes.

**Verified problem:** the UI route wraps the whole job in a 45-minute `asyncio.wait_for`, and decomposition takes hours. So this stage must run outside that wait, and must be able to pause and resume.

**Your decision before F3:** which models to use for extraction, review and the paragraph check. Tests use scripted models, so the code can be built first.

### F1. `packages/data-layer/src/monitor_data/schemas/ingestion_jobs.py`

- **Add** `IngestionStage.DECOMPOSE`, a `paused` state, and coverage fields: sentences total, done and quarantined, claims kept, pause reason.
- **Check first:** how `IngestionStatus` is defined and used, since a new status may affect code that assumes jobs end.
- **Test file:** `packages/data-layer/tests/test_tools/test_ingestion_job_tools.py`.
- **Commit:** `feat(data): I-17 add a decompose stage and coverage to ingestion jobs`.

### F2. `packages/ui/backend/src/monitor_ui/routers/ingest_shared.py`

- **Change:** map the new stage and status for the API.
- **Check first:** `packages/ui/frontend/src/lib/types.ts` and `IngestionJobsList.tsx`, as an unknown stage may break the list.
- **Commit:** `feat(ui): I-17 report the decompose stage through the API`.

### F3. `packages/agents/src/monitor_agents/book_decomposition/service.py` (new)

- **Add** `decompose_book(pdf_bytes, doc_id, title, store, extractor, review_model, guard, on_progress)`, which runs tree, extraction and review, and returns complete, partial or paused.
- **Test file:** `packages/agents/tests/test_book_service.py` (new), with scripted models.
- **Done when:** a test kills the run partway, and the rerun finishes without resending finished sentences.
- **Commit:** `feat(agents): I-17 orchestrate book decomposition as a service`.

### F4. `packages/agents/src/monitor_agents/ingestion/agent.py`

- **Add** the stage, after indexing, behind `MONITOR_BOOK_DECOMPOSITION` (default off), for PDFs only.
- **Keep:** all existing stages and their order. Search chunks are still built.
- **Test file:** `packages/agents/tests/test_ingestion_book_stage.py` (new).
- **Done when:** with the flag off, calls and outputs match today's, and with it on, a scripted run updates job progress and cancellation still works.
- **Commit:** `feat(ingest): I-17 run book decomposition as a flagged pipeline stage`.

### F5. `packages/ui/backend/src/monitor_ui/routers/ingest.py`

- **Change:** run this stage outside the 45-minute wait, record a pause, and add `POST /ingest/jobs/{id}/resume`.
- **Check first:** the executor and shutdown behavior. A long job must not hold the only worker slot.
- **Test file:** `packages/ui/backend/tests/test_ingest_resume.py` (new).
- **Done when:** a paused job resumes, a double resume is refused by the lease, and non-book jobs keep the existing timeout.
- **Commit:** `feat(ui): I-17 pause and resume long book ingests`.

### F6. `packages/ui/frontend/src/lib/types.ts`

- **Add** the new stage, status and fields.
- **Commit:** `feat(ui): I-17 add decomposition job types`.

### F7. `packages/ui/frontend/src/components/forge/ingest/IngestionJobsList.tsx`

- **Show** coverage, pause reason and a Resume button, with a matching test file.
- **Commit:** `feat(ui): I-17 show decomposition progress and resume`.

## Phase G: Map claims to KnowledgePacks

**Goal:** reviewed claims flow into the existing pack path, so the existing duplicate and contradiction checks and CanonKeeper still apply.

**Verified:** packs have `axioms` (500 character limit) and `lore_facts` (1,000 character limit), with `evidence_refs` whose `ref` is limited to 300 characters. They have no general rule item, though a `GameRule` schema and `game_system_data` exist.

### G1. Decide where rules go

- **Your decision, after reading `GameRule` and `EmbeddedGameSystem`:** rules go either in `game_system_data`, or in a new rules list on the pack. Check `_game_system_persistence.py` first, as the former may be the existing route. No code changes in this step.

### G2. `packages/agents/src/monitor_agents/book_decomposition/pack_mapper.py` (new)

- **Add** `claims_to_pack(claims, source, tree)`:

| Claim | Goes to |
|---|---|
| axiom | `axioms` |
| fact, relationship | `lore_facts` |
| entity | `entity_archetypes`, if its fields fit; otherwise `lore_facts` |
| rule | The G1 decision |
| example, rejected, needs a person | **Not in the pack** |

- **Evidence:** one `ProfileEvidenceRef` per cited sentence: `ref` holds the document and sentence IDs, `section_path` the headings, and `page_hint` the page.
- **Too long for a field:** never cut it. Send it to a person instead, because cutting could remove a condition.
- **Test file:** `packages/agents/tests/test_book_pack_mapper.py` (new).
- **Done when:** every mapped item has evidence, and every claim is accounted for as mapped or held back.
- **Commit:** `feat(agents): I-17 map reviewed claims to a KnowledgePack`.

### G3. `packages/agents/src/monitor_agents/book_decomposition/service.py`

- **Change:** create the pack after review, in the same status today's Analyzer uses, so it waits for approval as usual.
- **Test file:** `packages/agents/tests/test_book_service.py`.
- **Commit:** `feat(agents): I-17 create a KnowledgePack from a decomposed book`.

### G4. Compare with the Analyzer

- **Add** a scripted comparison test: which pack fields does the Analyzer fill that this path doesn't?
- **Done when:** a written list exists in the design doc. It decides when the Analyzer's book path can be retired, and that retirement isn't in this plan.

## Phase H: Improve the code checks

Each change here can alter paragraph text, and so paragraph IDs. So each one reports how many IDs changed, and bumps `DECOMPOSER_VERSION`. `out/dune` keeps its old tree, because its labels depend on it.

| Step | File | Change | Done when |
|---|---|---|---|
| **H1** | `ingest_tools/book_tree.py` | Detect tables from word positions and repeated rows | The complication table on page 163 becomes one table, and the 20% fragment rate on Dune falls, with no text lost |
| **H2** | `ingest_tools/book_tree.py` | Find the headings on the page 155 difficulty list, and attach bookmarks that currently fail to place | The 57 empty divisions on Dune fall, and each remaining one is explained |
| **H3** | `ingest_tools/book_tree.py` | Build sections from fonts for books with no bookmarks | A no-bookmark fixture gets real sections |
| **H4** | `book_decomposition/review.py` | Find why the page 176 example paragraphs aren't flagged, then fix it | They're flagged, and quotes and sidebars still aren't |
| **H5** | `book_decomposition/checks.py` and `review.py` | Collect names from labeled examples, and send kept claims naming them to a person | On saved claims, the 2 sample-character claims on page 173 are flagged, with the false alarm count reported |
| **H6** | `book_decomposition/checks.py` | Stop treating ordinary capitalized words such as "Keeps" as names, by matching word stems | On saved claims, "Keeps" is no longer flagged and the numbers check is unchanged |
| **H7** | `book_decomposition/checks.py` | Hold back claims that only describe the book, such as "This section provides guidance", and pure pointers | Tested on saved claims, with what it removed read by hand |

Test files: `packages/data-layer/tests/test_book_tree.py`, `packages/agents/tests/test_book_review.py`, `packages/agents/tests/test_book_checks.py`.

H4 to H7 can be checked on saved claims with no model calls, and their results read by hand. This can't prove claim quality improved overall. That needs labels.

## Phase I: Finish the graph

### I1. `packages/data-layer/src/monitor_data/schemas/book_graph.py`

- **Add** a `domain` field (rules or lore) on `ReviewedClaim`, stored through `BookStore`.
- **Without a model:** the domain comes from the claim kind and its chapter. A model's label can replace it later.
- **Test file:** `packages/agents/tests/test_book_knowledge_graph.py`.
- **Commit:** `feat(data): I-17 store a rules or lore domain on claims`.

### I2. `packages/agents/src/monitor_agents/book_decomposition/knowledge_graph.py`

- **Remove** `graph_search` and `keyword_search`.
- **De-scoped, and why:** graph search lost 12 to 15 to plain keywords, so it isn't worth keeping as a retrieval path. The graph stays as structure, for linking and browsing. The existing retrieval service stays the search path.
- **Keep:** assembly, citation checks, fixed predicate lists, merging and domain trees.
- **Commit:** `refactor(agents): I-17 remove graph search that lost to keywords`.

### I3. `tests/fixtures/ingestion/dune_graph_questions.json`

> This file held book text, so it's since been deleted and removed from the branch's history.

- **Tighten** the answer patterns, which are loose today, and keep this file for evaluating retrieval.
- **Decide** when doing this whether it's still used after I2. If it isn't, delete it.

### I4. `packages/data-layer/src/monitor_data/tools/neo4j_tools/book_tree.py`

- **Built:** `neo4j_merge_book_tree`, authorized for CanonKeeper alone and called through `CanonKeeper.record_book_structure`. It's off by default behind `MONITOR_BOOK_NEO4J`.
- **Why this route:** the rule that only CanonKeeper writes to Neo4j stays as it is, and its guard tests are unchanged apart from registering the new tools.
- **Found on real Neo4j:** without a uniqueness constraint, `MERGE` slowed down badly on a full book, so the loader creates one first.

## Phase J: Retire the prototype

### J1. Delete `book_decomposition/kimi_cli.py`

- **When:** after Phase F's models are chosen. Also delete `packages/agents/tests/test_book_kimi_cli.py`, and remove the Kimi-specific text from `pacing.py`.
- **Commit:** `chore(agents): I-17 remove the Kimi command line client`.

### J2. Remove the `graph` and `graph-questions` commands

- **File:** `scripts/prototype_book_decomposition.py`.
- **Commit:** `chore(scripts): I-17 remove experimental graph commands`.

### J3. Delete `scripts/prototype_book_decomposition.py`

- **When:** after Phase F works end to end. Decide then whether `FileBookStore` is still needed for tests or local runs.
- **Commit:** `chore(scripts): I-17 retire the prototype script`.

### J4. Update the docs

- **Files:** `docs/architecture/BOOK_DECOMPOSITION_PLAN.md`, `docs/use-cases/epic-2-ingestion-I/I-17/I-17-specification.md`, `docs/use-cases/epic-2-ingestion-I/I-17/I-17.yml`, `docs/STATUS.md`.
- **Commit:** `docs: I-17 describe book decomposition as part of the pipeline`.

## Decisions

| Step | Decision | Outcome |
|---|---|---|
| A1 | Open a draft PR | Done: PR #119 |
| A2 | Where the labels live | Backed up to `~/monitor-dm-labels/`, on the same machine |
| A2 | Whether short Dune quotes stay in a public repo | **Decided: removed.** Tests and help text now use invented examples, and the branch's history was rewritten |
| D2 | Analyzer timeout | Set inside the job's limit. Real durations could still justify changing it |
| F3 | Models for extraction, review and the paragraph check | Defaults are Mistral medium and large, set by environment variables. The paragraph check is off by default |
| G1 | Where rule claims go in a pack | `game_system_data.rules` |
| I4 | Who writes the book tree to Neo4j | CanonKeeper, so the existing rule holds |

## Known limits

- **No quality proof:** tests show the code behaves as designed. Whether claims get better needs live runs and labels.
- **Line numbers** are from 2026-11-04 and will drift.

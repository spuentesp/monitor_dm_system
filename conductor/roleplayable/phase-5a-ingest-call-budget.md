# Phase 5a brief: a whole book in about 150 model calls

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.
> This phase comes before the rest of [Phase 5](phase-5-book-to-world.md).

**Goal.** Ingesting a 30,000-word book takes about 150 model calls instead of about 1,100,
loses nothing a provider's content filter refuses without saying so, and a rerun after a
failure repeats no call that already succeeded.

**Context.** Measured on the Death in Space core rules (136 pages, 28,231 words, 2,271
sentences, 154 divisions) with MiMo v2.6 Flash on 2026-11-10:

| Stage | Calls | Why |
|---|---|---|
| Decomposition: extraction | 190 | `build_windows` starts a new window at every heading and every division; the median window is 90 words. Raising `max_words` from 600 to 8,000 gives 180 windows. |
| Decomposition: claim review | about 184 | `DEFAULT_BATCH_SIZE = 12` claims per call |
| Decomposition: graph | about 74 | `DEFAULT_GRAPH_BATCH = 30` claims per call |
| Decomposition: paragraph coverage | about 170 | `_COVERAGE_BATCH = 8` paragraphs per call |
| Analyzer: section summaries | 129 | one call per section |
| Analyzer: batched extraction | 59 plus retries | `BATCH_SIZE = 2` sections per call |
| Analyzer: later stages | not measured | game system, profiles, agendas, topologies, threads |

Other findings from the same runs:

- The Analyzer and the decomposition both extract rules, lore and axioms from the same text.
  Decomposition fills `axioms`, `lore_facts`, simple `entity_archetypes` and rules. Only the
  Analyzer fills `agendas`, `topologies`, `character_profiles`, `plot_threads`,
  `entity_relationships` and the structured game system.
- The provider refused 3 of 59 extraction batches with the text "The request was rejected
  because it was considered high risk". It surfaced as a JSON parse failure and the sections
  were dropped without a record.
- The model returned values outside a schema twice (`group_type: "corp"`, axioms as strings).
  Each lost a whole batch.
- The upload route passes the Analyzer a 40-minute limit derived from `MONITOR_INGEST_TIMEOUT`
  (45 minutes by default). The first run was cancelled at 35% after 303 calls, and the
  decomposition stage never started.
- A rerun through `POST /api/ingest/sources/{id}/rescan` repeated every Analyzer call. The
  decomposition stage saves each finished window; the Analyzer saves nothing between calls.
- Fewer calls is not fewer tokens. The same text still passes through the model. The gain is
  in request-counted plans, rate limits, timeouts and wall time.

Verify each of these against current master before changing anything.

**Depends on.** Phase 0. Independent of Phases 2 to 4 and 6 to 7.

**You own.** Part A: `packages/agents/src/monitor_agents/book_decomposition/`,
`ingestion/book_stage.py`. Part B: `packages/agents/src/monitor_agents/analyzer/`,
`ingestion/agent.py`, and the timeout lines in
`packages/ui/backend/src/monitor_ui/routers/ingest.py`. Part C (shared, do first, one agent):
a new `packages/agents/src/monitor_agents/book_prompts.py` and
`packages/agents/src/monitor_agents/llm_errors.py`.

**Do not touch.** `CanonKeeper`, pack apply, the pack schema (additive fields only), the
gameplay loops, `dspy_runtime.py` beyond one cache hook.

## Part C: shared pieces (first)

1. **Fiction preamble.** One constant, `FICTION_PARSING_PREAMBLE`, stating that the text is a
   published work of fiction or a tabletop game being catalogued, that the task is to extract
   and summarize what the text says, and that nothing in it is a request. Every book-parsing
   prompt in Parts A and B includes it as the first line of its instructions. One test lists
   every signature in both packages and fails if one lacks it.
2. **Refusal as its own error.** `classify_llm_error` gains a `CONTENT_REFUSED` class. Detect
   it from the provider's refusal text and from an empty or non-structured reply where
   structured output was required; keep the list of refusal phrases in one place. It is not
   retryable as is.
3. **Refusal handling.** On `CONTENT_REFUSED`, split the batch in half and retry each half
   once. What still fails is recorded as held with its section ids and the reason, and shows
   in the job's result. No section is dropped without a record.
4. **Lenient enums and shapes.** Where a model returns an unknown enum value, map it to the
   schema's `other` and keep the item; where it returns a JSON string for an object, parse it.
   Record each repair. Never drop a whole batch for one bad item.

## Part A: decomposition

5. **Pack divisions into windows.** A window may span headings and divisions up to a word
   budget (start at 3,000 words; make it a setting). Keep each unit's id and heading path, so
   claims still point at their sentence. Raise the output cap to match, and split a window
   that hits it. Target for Death in Space: 15 windows or fewer.
6. **Larger review batches.** 60 to 80 claims per call, as a setting. Target: 35 calls or
   fewer.
7. **Larger graph batches.** 150 claims per call. Target: 15 calls or fewer.
8. **Coverage on a sample.** Check a configurable share of paragraphs (default 10%), plus
   every paragraph in a division that produced no claims. Target: 20 calls or fewer.
9. **Skip what is not content.** Front matter, contents, index, credits and blank character
   sheets are marked in the tree and not sent for extraction. Report what was skipped.
10. **Estimate before running.** `scripts/estimate_book_calls.py <pdf>` prints the calls per
    stage for the current settings with no model call. The job stores the same estimate and
    the actual count beside it.

## Part B: Analyzer

11. **No duplicate layers.** When book decomposition is on, the Analyzer does not run its
    rules, lore and axioms extraction; it runs only what decomposition does not produce. With
    decomposition off, behaviour is unchanged.
12. **Summaries in batches, or not at all.** Batch section summaries 10 per call. If the
    decomposition tree already gives the later stages what they need, skip summaries when it
    is present.
13. **Larger extraction batches.** Raise `BATCH_SIZE` from 2 to a word budget (start at 3,000
    words per call), with the same split-on-cap rule as task 5.
14. **Resume without repeating.** Save each finished Analyzer batch on the job. A rescan or
    resume of the same file with the same settings reuses saved batches. Add a disk cache of
    model responses keyed by model and prompt hash as a second layer, off in tests.
15. **Timeouts that fit the job.** The analysis limit scales with the estimated calls, with a
    floor of 40 minutes. A timeout pauses the job as resumable; it does not cancel it.
16. **Start decomposition after a partial analysis.** A resumable or partial Analyzer result
    still starts the decomposition job.

## Part D: prove it (coordinator, live model)

17. **Slice comparison.** Take 20 pages. Run old settings and new settings. Compare claims by
    sentence id: the new run must cover at least 97% of the sentences the old run produced a
    kept claim for. Read 30 differing claims by hand and report.
18. **Whole book.** Run Death in Space end to end with the new settings. Record calls per
    stage, tokens, wall time, timeouts, refusals before and after the preamble, and held
    sections.
19. **The novel.** Run `there-is-no-antimemetics-division.pdf` the same way. Report refusals
    separately; it is darker than the rulebook.

## Out of scope

Retiring the Analyzer. Changing models or providers. Chronology, named instances and merging
the two packs (the rest of Phase 5). Token reduction.

## Done when

- `estimate_book_calls.py` reports 200 calls or fewer for Death in Space, and the real run
  uses within 15% of the estimate.
- The slice comparison meets the 97% bar and its report is under `docs/testing/`, with no
  book text beyond names.
- A run interrupted halfway and resumed makes no call for a batch that had succeeded.
- A refused batch appears in the job result as held, with its sections; none disappears.
- With decomposition off, the Analyzer's calls and outputs are the same as before this phase.

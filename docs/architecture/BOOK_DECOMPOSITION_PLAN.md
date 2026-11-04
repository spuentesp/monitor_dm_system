# Book Decomposition Plan

> Status: prototype, 2026-11-04. It runs from a script and writes local files, and it's **not connected to
> `IngestionPipeline` or the UI yet**. It has run on parts of Dune; the VtM PDF hasn't been decomposed
> (see [Phase 1](#phase-1--vtm-spike)). Claim quality isn't proven: see [the claim truth plan](#8-claim-truth-plan).
> Next: map its overlap with the existing pipeline, then replace the old parts in place.
> Use case: [`I-17`](../use-cases/epic-2-ingestion-I/I-17/I-17-specification.md).

## 1. The goal

A book should become a graph, with nothing selected or sampled:

```
Book → Chapter → Section → Paragraph → Sentence
                                          ↑ SUPPORTED_BY
                         Axiom / Entity / Fact / Rule / Relationship
```

Every sentence is read, and every sentence ends with a recorded outcome. "Did we read the
whole book?" and "which sentence says this?" both become queries.

## 2. Why the current pipeline can't get there

Ingestion chunks a book into Qdrant, then runs category queries to choose what the Analyzer
reads. That is a retrieval design, and these limits follow from it:

| Problem | Evidence |
|---|---|
| Reads a thin sample | `MAX_CATEGORY_CHUNKS = 512`, and scroll returns points in ID order. IDs are uuid5 hashes, so a capped scroll is effectively random. A simulated 3,107-chunk book got about 3 of every 18 chunks per section. |
| Sections get truncated | `MAX_SECTION_WORDS = 1500` cuts text with no log or warning. |
| Section text is wrong before any cap applies | `extract_pdf_structure` gives a parent all its children's text, and same-page siblings each get the whole page. |
| Books get mixed together | Analyzer filters use the display title (`_core.py:1747`, `1811`, `1886`, `3005`), so two books with one title share chunks. |
| No document-level coverage | Nothing can report what fraction of a book was read. |
| Entities have no source | `_commit_entity` passes no `source_ids`, and `evidence_refs` never reaches a proposal. |

Raising the caps, as GAP-8 and GAP-9 did, only moves the cutoff. Patching can't produce full
coverage, because selection is the design.

**Keep:** the `ProposedChange` → CanonKeeper boundary, content-hash dedup, the failure
categories and `PARTIAL` status, the degenerate-extraction guard, and the DSPy provider runtime.

## 3. Principles

1. **Lossless first.** Decomposition is deterministic, needs no LLM, and proves it lost nothing.
2. **Every unit gets an outcome.** Each sentence or table is cited by an atom, explicitly
   skipped with a reason, or reported as uncovered. Code checks this, not the model.
3. **Nothing without a source.** An atom citing a unit that doesn't exist is dropped.
4. **Context is wider than citation.** The model reads a passage but cites individual sentences,
   because "it costs one blood point" means nothing alone.
5. **Not every sentence is an axiom.** Flavor, examples and navigation are valid outcomes, and
   they are recorded so they can be audited.
6. **Search is a derived index.** Qdrant serves gameplay retrieval. It is no longer how
   ingestion decides what to read.

## 4. Architecture

```
PDF
 │  [1] DECOMPOSE   deterministic, ~11 s for 339 pages, no LLM
 ▼
Book tree + DecompositionReport (is_lossless, pages without text, TOC entries found)
 │  [2] WINDOW      paragraphs grouped by section, ~600 words, each unit in exactly one window
 ▼
Windows
 │  [3] EXTRACT     LLM per window; code validates; retries only missing units; checkpointed
 ▼
Atoms + CoverageReport
 │  [4] CONSOLIDATE merge duplicates across the book, keeping every citation
 ▼
Consolidated entities, axioms, facts, rules, relationships
 │  [5] PROPOSE     ProposedChange with evidence_refs → sentence IDs
 ▼
Review by chapter and confidence
 │  [6] COMMIT      CanonKeeper writes canon + SUPPORTED_BY → Sentence
 ▼
Neo4j canon, traceable to the exact sentence    ·    game_systems docs built from rule atoms
```

### Stage notes

**Decompose** (`tools/ingest_tools/book_tree.py`, built). Each text block goes to exactly one
division by its position. The check counts alphanumeric characters on the PDF's pages against
those in the tree, which ignores whitespace and dehyphenation. Node IDs derive from `doc_id`, so
they can't collide between documents.

This check proves no text was lost. It does **not** prove the reading order is right or the
sections are correct, and it can't see text inside images. Those need the Phase 1 review and
OCR respectively.

**Window** (`book_decomposition/windows.py`, built). Windows never cross a division or heading.
The last 60 words of the previous window are passed as read-only context.

**Extract** (`book_decomposition/pipeline.py`, built; run on Dune Chapter 5). Windows
run concurrently, and each finished window is written to the extraction log immediately, so a crash
or provider outage loses only in-flight work. Each outcome records its model and prompt version.
Work from an older prompt is kept by default, because redoing it costs quota;
`--redo-older-prompts` redoes it. Unparseable output splits the window in half rather than
repeating the request, since it usually means the answer outgrew the token limit.

**Recovery** (`book_tree.py`, `book_decomposition/ledger.py`, `runner.py`, built; not yet run against
a real provider failure). Recovery rests on three things:
- *Idempotent division.* Node IDs come from content rather than position: a paragraph's ID hashes the
  document, its normalized text and which occurrence it is. Sentences are scoped to their paragraph.
  Re-decomposing keeps the IDs of unchanged text. Tested on the Dune PDF: changing the column or
  heading thresholds kept 98.4% and 99.9% of paragraph IDs, where positional IDs would keep under 1%.
- *One append-only log, tracked per unit.* A unit is done once any outcome accounts for it. State is
  always recomputed from the log, so parts can run in any order, overlap, or crash, and only what's
  missing is ever sent. A torn last line is ignored, and an OS file lock stops two runs from
  paying for the same work without leaving a stale lock behind.
- *A loop with one recovery per failure.* Quota errors pause and can wait and retry. Rate limits back
  off. Provider failures retry, and never count against the text. A sentence that repeatedly can't be
  parsed is quarantined, so it can't block the book, and is listed for a person. Budget stops
  never auto-resume.

Limits: the log is a local file with one writer, so Phase 4 moves it to MongoDB. Review saves
verification checks per claim, but skip checks and stacking still rely on DSPy's cache to resume.

**Review** (`book_decomposition/review.py`, built; tried on 2 pages, see section 8). Runs after
extraction, in four steps:
1. Re-read every skipped sentence and rescue anything the extractor missed.
2. Check each claim against its whole source paragraph: supported, corrected (including dropped
   conditions), example, filler or unsupported.
3. Group by type, cluster similar claims, merge duplicates, and settle contradictions. A conflict
   only resolves automatically when the source text shows a misreading; otherwise a person decides.
4. Write a ledger. Every original claim gets exactly one status, merged claims pass their citations
   on, and any sentence left with no surviving claim is reported as orphaned.

Worked examples are kept out of canon, but never deleted. Anything unverified goes to a person
and is never approved by default.

**Consolidate** (partly built by Review; the rest is not built). The same entity appears in dozens
of windows, and each mention must keep its citation:
- Group entity atoms by normalized name and alias, then use the LLM to settle ambiguous groups.
- Cluster axiom, fact and rule atoms by embedding, then have the LLM decide whether each cluster
  states one claim, and flag contradictions rather than picking a winner.
- Use the tree: atoms in one section are the likeliest duplicates, so merge bottom-up from
  section to chapter to book. That also keeps comparisons from growing with the square of the
  atom count.

**Game systems** (not built). `game_systems` documents get built from rule atoms instead of
top-scored sections, so each attribute and creation step cites its source. This removes the
30-section limit (`SYSTEM_SCHEMA_SECTION_LIMIT`) as a constraint on what can be seen.

**Review** (not built). Thousands of proposals can't be approved one at a time. Review needs to
work per chapter, with high-confidence atoms accepted in bulk and low-confidence atoms and
contradictions shown first.

**Gameplay retrieval** (not built). Paragraphs are embedded after decomposition, with `doc_id`
and node IDs in the payload, so a Qdrant hit can link back into the graph.

### Data model

```cypher
(:Source)-[:HAS_ROOT]->(:BookNode {kind: 'book'})
(:BookNode)-[:HAS_CHILD {order}]->(:BookNode)       // division, paragraph, table, sentence
(:Axiom|Fact|Entity)-[:SUPPORTED_BY]->(:BookNode)   // a sentence or table; repeated for each citation
```

`BookNode` carries `id`, `doc_id`, `kind`, `seq`, `text`, `page_start`, `page_end`. Headings and
page furniture stay in the artifact for the losslessness check, and don't need to go in the
graph unless a use for them appears.

## 5. Measured so far

Decomposition of a real 339-page rulebook (`Dune`, used only as a layout test, with no LLM):

| Measure | Result |
|---|---|
| Time | 11 s |
| Characters lost | **0** of 892,837 |
| Words | 189,670 |
| Sentences + tables | 10,640 units, about 31 per page |
| Windows at 600 words | 1,217 |
| TOC entries located by title | 656 of 732 (90%) |
| Pages with no text layer | 3 |
| Paragraphs of 3 words or fewer | 1,066 of 5,213 (20%): credits, but also **broken table rows** |
| Tables detected | 64, including false positives such as an ISBN barcode and a running header; real tables are likely missed |
| Divisions with no direct paragraphs | 57 of 732: some are real parent headings; others may be misplaced, and aren't yet reviewed |

That run exposed three defects a synthetic fixture didn't, all now fixed and tested: bookmarks
out of page order, letter-spaced headings, and soft hyphens.

### Rough projection for VtM (529 pages)

Scaled by page count, so about 16,600 units and 1,900 windows.

| | Estimate | Basis |
|---|---|---|
| Input tokens | ~1.3M+ | ~390k of book text, plus an assumed 500 tokens of prompt per window. The prompt carries the output JSON schema, so this may be low. |
| Output tokens | ~15M | Measured on Dune Chapter 5 with MiniMax-M3.1-Flash: about 8,200 per window counting only successful calls, and about 12,100 with failed calls. Before any prompt tuning. Reasoning was 92% of output (515k of 559k tokens), so controlling it matters far more than claim wording. |
| Wall time | Far above 1 hour | Median window took 75 s, and quota limits dominate on a monthly plan |
| Atoms | ~30k before review | Measured: about 16.6 per window, before merging |

For comparison, the UI job limit is 45 minutes today.

## 6. Prototype

Files only; it touches no database and isn't wired into the live pipeline.

| Part | Location |
|---|---|
| Schemas | `packages/data-layer/src/monitor_data/schemas/book_graph.py` |
| Decomposer | `packages/data-layer/src/monitor_data/tools/ingest_tools/book_tree.py` |
| Windows, extractor, pipeline | `packages/agents/src/monitor_agents/book_decomposition/` |
| CLI | `scripts/prototype_book_decomposition.py` |
| Tests | `packages/data-layer/tests/test_book_tree.py`, `packages/agents/tests/test_book_decomposition.py` |
| Dune expected facts | `tests/fixtures/ingestion/dune_ch5_rules_expect.json` |

The extractor runs through the real DSPy adapter in tests, but with a dummy LM.

The expected-facts file is a rough check. 7/5/3 and 13/9/5 come from
`INGESTION_PIPELINE_AUDIT.md`; the Discipline, Background, Virtue and freebie values were written
from memory and **must be checked against the book**.

## 7. Phases

Each phase has a gate. Don't start the next one until it passes.

### Phase 1 — VtM spike

```bash
uv run scripts/prototype_book_decomposition.py decompose WtWf-VtM20th.pdf --out out/vtm
uv run scripts/prototype_book_decomposition.py divisions --out out/vtm
uv run scripts/prototype_book_decomposition.py extract --out out/vtm \
    --division "Character Creation" \
    --model mistral/mistral-medium-latest
```

**Gate:**
- [ ] Decomposition is lossless, and a person has read 10 sampled pages for reading order.
- [ ] Unit coverage is at least 99.5% on the chapter, with failures listed.
- [ ] 6/6 expected facts are found, after checking those facts against the book.
- [ ] A person judges 50 sampled atoms: at least 90% correct and correctly cited.
- [ ] Real tokens, latency and atom counts replace the unknowns in section 5.

**If it fails:** low precision or poor coverage is a prompt and window-size problem, so iterate
here. If it can't reach the gate at an acceptable cost, sentence-level citation is the
assumption to revisit, and paragraph-level is the fallback.

### Phase 2 — Tables and layout
Handle the fragment problem: group runs of short aligned blocks into tables, and try
`page.find_tables()`. Add OCR for pages with no text layer. Sidebars need checking too.
**Gate:** fragment rate on VtM and one other book reviewed by a person; known tables come through
intact.

### Phase 3 — Identity and persistence
Add `I-17`. Store the tree, add write tools and authority checks, and add indexes on `doc_id`.
Filter by `doc_id` everywhere, which also fixes the title-mixing bug in the current pipeline.
This part can ship early on its own. **Gate:** two books with one title stay fully separate in an
integration test.

### Phase 4 — Durable extraction job
Move checkpoints to MongoDB, add per-window progress and a cost budget, and replace the fixed job
timeout with a stall timeout, so a long run that's still progressing isn't killed. Quota-aware
scheduling is required: Chapter 5 (46 of 1,217 windows, about 559k output tokens including failed calls) finished off a
MiniMax plan's weekly limit, along with that week's other use of the key, so a full book has to span quota windows. The prototype's `RunGuard` stops on
quota and auth errors, backs off on rate limits, and enforces a token budget that includes failed calls; the job needs to
carry that forward and resume by itself. Coverage shows in the job UI. Runs behind a flag, next to the old path. **Gate:** kill a full-book run midway and resume with
no repeated windows.

### Phase 5 — Consolidation and game systems
**Gate:** a VtM graph with no duplicate clan or Discipline entities, every merged entity keeping
all its citations, and a `game_systems` document that passes the existing degenerate check with
correct values. This also finally resolves Finding 3 and Finding 4 of the ingestion audit.

### Phase 6 — Canon and provenance
Add `evidence_refs` to proposals, add `source_ids` to `EntityCreate`, and create `SUPPORTED_BY`
edges to sentences. Build chapter-level review. **Gate:** from any canon node in the UI, reach the
exact sentence and page.

### Phase 7 — Cutover
Make this the default. Remove category retrieval, section digests, the per-section mindscape pass
and the caps. Migrate other `extract_pdf_structure` callers or remove it. **Gate:** ingestion tests
pass on the new path, and one rulebook, one supplement and one short adventure are each
ingested end to end.

## 8. Claim truth plan

> Status: proposed, 2026-11-03. None of the steps below are built or tested. Expected benefits are
> judgement, and the targets are starting points to adjust once the baseline is measured. This work
> sits inside Phase 1's gate, whose "at least 90% correct" check it is meant to pass.

### What the first real review showed

Mistral (`mistral-large-latest`) reviewed 112 MiniMax claims from Dune pages 153 and 163:

| Check | Result |
|---|---|
| Dropped veto on adding traits | Caught and corrected |
| Sample-character claims | 13 of 32 stayed in canon: 11 on page 153 and 2 on page 163, counting a merged claim |
| Rejections | 2 of 3 look wrong, including "Certain skill tests cannot be failed outright", which the source states |
| Merges | Separate rules were combined, such as the "easier" and "harder" outcomes |
| Orphan check | Listed the wrongly rejected rule, so a person could catch it |
| Cost | About 32,000 input and 7,300 output tokens, or about 65 output tokens per claim |

### The main finding: truth is more than one value

A claim that a sample character has some trait is true to the source, so a verifier asking "is this true?" accepts
it. What's wrong is its scope: it describes an example. A single verdict can't express that, and
more agents asking the same question wouldn't change it.

Each claim should carry separate values:

| Value | Options | Decided by |
|---|---|---|
| **Support** | quoted, entailed, inferred, unsupported | Code checks the quote; a model handles the rest |
| **Scope** | general rule, setting canon, single example | Paragraph roles, plus code |
| **Force** | must, may, usually, cannot | A model extracts it; code compares it |
| **Authority** | core rule, optional rule, GM advice, in-world fiction | Book structure, plus a model |

Authority matters because in-world fiction can be unreliable, so it shouldn't weigh the same as a rule.

### Pipeline

```
Windows
 │  [Q2] ROLES       one cheap pass per section: rule, example, fiction or advice per paragraph
 ▼
 │  EXTRACT          the extractor never sees the truth table; claims inherit their paragraph's role
 ▼
 │  [Q2] CODE CHECKS quote, numbers, dropped conditions, unknown names: these flag or reject only
 ▼
 │  [Q3] VERIFY      fills in the values above and quotes its evidence; sees headings and neighbours
 ▼
 │  [Q4] NORMALIZE   term, attribute, force, value, condition
 ▼
 │  [Q4] TRUTH TABLE same key and value = duplicate; same key, other value = contradiction
 ▼
 │  [Q5] ESCALATE    disputed claims only: cheap red team, then tie-breaker, then a person
 ▼
ProposedChange with evidence_refs → CanonKeeper
```

### Steps

Each step has a gate. Don't start the next until it passes.

#### Q1 — Answer key

Hand-label 100–150 claims with their support, scope, force and authority. Pre-fill the labels so a
person only corrects them, which should take about 30–45 minutes. Keep most of them away from
tuning: use pages not yet inspected, plus a sample from another book such as VtM once it's
decomposed. Then score the current review to get a baseline.

**Gate:** baseline numbers exist for false accepts, false rejects and caught dropped conditions,
with tuning and test sets kept separate.

**Baseline (2026-11-03, Dune pp. 151–167, `mistral-large-latest` reviewing MiniMax claims, 90 test
claims):** 8 of 19 not-canon claims kept, 7 of 18 not-canon example claims kept, 4 of 71 canon claims removed,
and 2 of 5 dropped conditions corrected or rejected, with 1 more merged and not yet checked. The
dropped-condition figure rests on too few claims to test a 90% gate. All 5 dropped-condition claims
are also labeled canon, which conflicts with "canon as written"; if they become not canon, the first
and third figures become 11 of 24 and 3 of 66. The full run used 152 requests, about 214k input and
50k output tokens.

#### Q2 — Code checks and paragraph roles

Code can't establish that a claim is true, but it can prove a claim is unsupported. These checks can
flag or reject, and never approve a claim alone:

- **Quote:** the model must quote its evidence, and code confirms those words are in the source.
- **Numbers:** every number in a claim must appear in its source.
- **Dropped conditions:** the source has "but", "unless" or "only" and the claim doesn't. This should
  have flagged the veto, but its false-alarm rate is unmeasured.
- **Unknown names:** every named term must appear in the source or its heading.
- **Layout (built):** the tree records each paragraph's main font and color. A paragraph that directly
  follows a labeled example in the same non-body style is treated as continuing it, and the verifier
  gets a note. Style alone isn't enough: Dune also uses it for quotes and for a core rule on page 96.
  That rule is still flagged, and only the verifier's judgement can keep it, which is untested on real
  claims because page 96 hasn't been extracted. A style needs at least 2 labeled paragraphs, so a book
  with no labeled examples gets nothing from this.

Paragraph roles are the most direct fix for sample characters: the running example on page 153 has no "Example:"
label, and the reviewer only sees each claim's own paragraph. The layout rule may cover most of this
for Dune, at no model cost. A model pass is only worth building if the test set or another book shows
that it falls short.

**Results after Q2's layout rule and code checks (2026-11-03):**

| Measure | Tuning before → after | Test before → after |
|---|---|---|
| Bad claims kept | 5 of 16 → 0 of 16 | 10 of 21 → 2 of 21 |
| Not-canon example claims kept | 5 of 16 → 0 of 16 | 9 of 20 → 1 of 20 |
| Good claims removed | 2 of 14 → 2 of 14 | 3 of 65 → 1 of 65 |
| Dropped conditions, by the person's corrected labels | none labeled | no change: see below |

After the person's second pass, 4 test claims are real drops. For the 3 whose fact belongs in canon
once restored, the review accepted 1 unchanged, rejected 1 and merged 1 without keeping its condition, so it
restored none of them. It corrected the fourth and kept it, though that fact doesn't belong in canon.

These counts leave out dropped-condition claims, which are scored on their own row. The test range ran
twice: the first run showed a problem outside the labeled sample, described below, and fixing it barely
moved the labeled scores. Treat the test figures as slightly less clean than a single run. One claim moved from test to tuning
afterward, because the person raised it and it was read, so later counts use 89 test and 31 tuning claims.

**Another kind of example: a specific case inside rule text.** A passage defines a category of ability.
Its next sentence names one group's ability as a case of it. The second sentence only illustrates
the first, and it has no example label or layout. Adding this to the verifier's instructions didn't catch
that claim, so the change was reverted. It's a scope problem, so Q3's separate scope value is the next
place to try. Rerunning 3 pages alone also changed 21 non-test statuses compared with the full-range run. Reviewing fewer
pages, the prompt change and run-to-run variation can't be told apart there, so a rerun like that isn't
evidence that a prompt change works. In identical verifier runs on pages 153 and 163 with caching off, 3 of
112 verdicts differed, so a change of a few claims on those pages could be noise.

**Setting details (tried and removed).** A separate model step moved a named case out of the rules, into
a `setting_detail` status linked to its source. It was removed because it did more harm than good: on pages
168–180, 5 of the 8 claims it moved were real rules, so named cases like the Mentat claim stay in the rules for
now. Asked about every claim, it moved 38 of 161 on
3 pages, including a gamemaster veto, table rows and Momentum rules. Limited to claims whose sentence had wording
like "types of" or "such as", 43 of the 764 claims, it moved the two
claims about two named groups and one test claim, but left the labeled claim about one group's ability
in the rules.

Also added: a correction that grows by at least 25 words and doubles in length goes to a person (5 of 123
saved corrections), and a name now only has to appear somewhere in its section. The test range hasn't been
rerun with these changes, so its scores above predate them.

**A passing key isn't enough.** The first run looked better on every labeled measure, yet it wrongly
rejected 24 valid rules from the difficulty list on page 155, because the number sat in the heading above
each bullet. None of the 24 were in the sample. Rejections and orphaned sentences showed it, going from 14
to 34 and from 6 to 25. Check those totals beside the scores on every run. After the fix they're 13 and 8.
Now only a possible dropped condition goes to the verifier as a note. A number or name still missing from
the source and heading sends the claim to a person.

**Q2's gate isn't met.** Example claims reaching canon sit at 5%, just over the under-5% target. The
dropped-condition check fails: it flagged 1 of 4 labeled drops, against a 90% target, and also flagged
24 of the other 86 claims. Tuning it needs more
labeled drops from outside the test set, because the tuning pages have none.

**Gate (proposed):** on the test set, under 5% of example claims reach canon, and the code checks
flag at least 90% of dropped conditions. These checks fall under the pre-filter and parsing uses that
the [de-heuristic principle](DE_HEURISTIC_PRINCIPLE.md) permits, since ingestion isn't the gameplay path.

#### Q3 — Verifier with separate values

Replace the single verdict with the four values, and require a quote. Show the heading path and
neighbouring paragraphs. A claim that nearly restates its source can't be called unsupported: if the
verifier is unsure, it goes to a person.

**Gate (proposed):** under 2% of true claims wrongly rejected on the test set, with no drop in Q2's
results.

#### Q4 — Structured form and truth table

A model turns each claim into term, attribute, force, value and condition. Code then decides: the
same key and value is a duplicate, and the same key with another value is a contradiction. Embedding
lookup finds likely matches for a new claim, which replaces word-overlap clustering and its groups of
12. A model only decides what the structured form can't.

- **Rebuildable:** claims and decisions go in an append-only log, and the table is built from it.
  Grooming adds decisions, and never deletes a claim or a citation.
- **Blind extraction:** the extractor doesn't see the table, or an early mistake would steer everything
  after it. At most, it gets a glossary of terms.
- **Canon boundary:** the table stays at the `ProposedChange` stage. CanonKeeper remains the only
  writer of canon, and citations carry over as `evidence_refs`.
- **Atomic claims:** merging only applies to claims that say the same thing, and code rejects a merge
  whose canonical statement combines separate rules.

**Gate (proposed):** contradictions planted in the test set with different wording are found, no
citations are lost, and rebuilding the table from the log gives an identical result.

#### Q5 — Red team and tie-breaker (only if needed)

Build this only for the kinds of claim the answer key shows are still failing. It runs on disputed
claims only, or the cost multiplies.

- **Red team:** a cheap agent with a narrow job, such as "quote the words that support this" or "find
  the condition it dropped".
- **Tie-breaker:** a stronger model that sees both sides, and can answer "a person decides".

More agents won't fix a context problem, because they'd all share the same blind spot.

**Gate (proposed):** it measurably beats Q4 on the test set at a cost you accept. Otherwise, leave it out.

### Further checks, once the core works

- **Round trip:** for each paragraph, ask what the surviving claims fail to cover. This catches lost
  meaning that checking claims one at a time can't.
- **Two extractors:** run two models on a sample and investigate where they disagree, to measure what's
  being missed.
- **Local entailment model:** a fixed model comparing source and claim gives repeatable results and uses
  no quota. It can be wrong, but consistently so, which makes it a useful second opinion.
- **Rules questions:** test whether the final claims can answer real rules questions, because that's
  what the game needs from them.

### Known limits

- Truth here means "true to this book". Conflicts between books, and errata, aren't covered.
- Pages 153 and 163 have been inspected, so they can't serve as a test set. Using the test claims to
  tune prompts would spoil them too, and they all come from one chapter of one book.
- Reasoning effort on MiniMax is unmeasured until its weekly limit resets on 2026-11-05.
- `mistral-medium-latest` extracted pages 153, 163 and 168–180 with full coverage, at about 860 output
  tokens per window where MiniMax's Chapter 5 run used about 8,200. Both the model and the prompt changed,
  so the gain can't be credited to either yet, and claim quality is unlabeled so far. On page 153 it turned
  example passages into general statements, which can overgeneralize, and left "players may add as many
  traits as they like" unstated. That missed claim is the kind of loss the round-trip check is meant to find.
- A hand check of 60 decisions on pages 168–180 found 9 of 13 rejections and 5 of 8 setting-detail moves
  wrong. Now a rejected claim that closely matches its cited sentence goes to a person, setting-detail
  detection is off by default, the extractor is told not to build rules from what one character does, and
  a sentence broken by a font change is rejoined (41 paragraphs across Dune). On the rerun, rejections fell
  from 13 to 2, orphaned sentences from 13 to 2, and items for a person rose from 8 to 15. The close-match
  threshold was set on these same claims, and two kept claims still name a sample character.
- A person labeled 25 Mistral claims from pages 168–180, all from sentences with a limiting word, with nothing
  pre-filled. They accepted 24 as canon and flagged 11 as dropping something; neither Mistral large nor Claude
  flagged any of the 11. All 7 flagged claims with notes, and an eighth with a note but no flag, had the missing
  point in another claim from the same paragraph. So the main problem there is that a claim reads as incomplete
  alone, not that the book's content is lost. Showing a claim's paragraph siblings, plus a paragraph-level check
  for real losses, looks like a better next step than a per-claim dropped-condition check.
- Reviewed claims now link to others from the same paragraph, and the per-claim condition note is gone. A
  paragraph check reports what a paragraph says that its claims don't, and code confirms each quote. On 107
  shared paragraphs, Mistral large reported 34 gaps, of which about 6 looked real on a hand read. It missed the
  known-answer case on page 153. A fresh Claude reported 12, with every quote confirmed, and caught that case.
  Kimi `k3.1-pro`, run independently, reported 13 with every quote confirmed, caught the same case, and shared
  7 of Claude's 9 paragraphs, against 5 and 4 for Mistral with those two. Codex hit its usage limit. Kimi ran
  through its command line on a plan login, so its use as a pipeline model and its cost are untested.
- Kimi K2.8 reported 5 gaps on the same paragraphs, all also found by Claude and K3.1 Pro, and so was precise
  but found less. The pipeline now runs the check through the `kimi` command (`--coverage-model`), with tools
  off, an empty folder, a call limit and a resume log. Prompt mode can otherwise write files and run commands.
  Kimi reports no token counts there, so plan use per book is unknown.
- Verified gaps now become claims and go through the same verifier. A merge that would gather separate rules
  into one statement is refused. On pages 168–180 with K3.1 Pro this gave 19 new claims and 6 refused merges,
  and removed the bundled Difficulty 2 claim, with 306 claims kept. The new claims were only read by title,
  and their verifier is the same Mistral that missed these gaps.
- Pages 181–197 ran through the same pipeline: all 505 sentences covered, 566 claims in and 492 kept, 17 gaps from
  201 paragraphs, about 14 Kimi calls, and about 268k input and 71k output tokens on Mistral. At that rate a full
  book is very roughly 5M input and 1.4M output tokens plus 220 Kimi calls. No claims from these pages are labeled.
- Knowledge graph test (`graph` command, Kimi K3.1 Pro, pages 168–180): 101 nodes and 200 relationships from 158
  claims, each citing its claims, with 38 of 253 proposals dropped because a name wasn't in the cited claim. One
  batch of 40 claims (pages 176–177) timed out twice. It has 93 distinct predicates and some duplicate nodes, such
  as "extended task" and "extended test". Triples lose conditions, so they index the claims and don't replace them.
- Rules and lore now get separate trees and graphs, each with a fixed predicate list, over 1,109 claims from pages
  37–43 and 168–197. Kimi's domain labels put 680 of 798 claims from the rules pages in rules and 307 of 311 from the
  lore pages in lore. In a 16-question test with loose patterns, plain keyword search found 15 and the graph 12, so
  the graph is no better than keywords at finding a claim. The build also hit Kimi's 5-hour limit after about 37 calls
  in 36 minutes, so the plan can't run a full book in one sitting.
- `out/dune` keeps its version 3 tree, because rebuilding it would change the IDs of 82 paragraphs that its
  answer key and claims may cite. `out/dune-mistral` uses version 4, with the first run saved in `run1`.
- Mistral's pricing and how this key is billed haven't been checked.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Cost and duration on full books | Measure in Phase 1; checkpointing and budgets in Phase 4. |
| Model marks too much as skipped to satisfy coverage | Report skip rates by reason and sample skipped units in review. Coverage alone isn't a quality measure. |
| Model cites the wrong sentence | Citation accuracy is part of the Phase 1 sample. Validation only proves the cited unit exists. |
| Too many atoms, duplicates | Consolidation in Phase 5 is required rather than optional. |
| Layout varies by book | Report-driven: every run shows located TOC entries, fragments and empty pages. |
| Sentence splitting is imperfect | A wrong split changes citation granularity but loses no text. A sentence split across paragraphs remains a known gap. |
| PDFs with no bookmarks | Partly handled: no text is lost, but it all sits directly under the book root, split only by detected headings. Needs font-based sections, in Phase 2. |

## 10. Decisions needed

1. **Where does the book tree live, and who writes it?**
   Recommendation: in Neo4j, written by `IngestionPipeline`, and treated as a record of the file
   rather than canon. About 25k nodes per book is well within Neo4j's range, and it delivers the
   book-as-graph goal. It does widen the "only CanonKeeper writes Neo4j" rule, which already has
   the `neo4j_create_source` exception (`middleware/auth.py:86`), so `AGENTS.md` should state the
   narrower rule: *only CanonKeeper writes canon*.
2. **Does sentence-level citation stay if it costs more than paragraph-level?**
   Recommendation: decide from Phase 1 numbers.
3. **Does this run on every upload?**
   Recommendation: yes for core books; consider a cheaper mode for short notes.
4. **What counts as canon when a claim is true but comes from an example?**
   Recommendation: keep it out of canon, linked to its source, unless it states a general rule. The
   answer key in Q1 settles the edge cases, and that judgement belongs to a person.
5. **Where does the truth table live?**
   Recommendation: a local append-only log in the prototype, moving to MongoDB with Phase 4.

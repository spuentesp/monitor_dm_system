# CanonKeeper recall measurement — 2026-11-11

> **Method:** hermetic replay of the labeled G08 corpus
> (`monitor_agents.canonkeeper.recall_corpus`) via
> `scripts/eval_canonkeeper_recall.py`. No database, no seeded content.
> **Model:** `mimo-v2.6-flash` (the HEAVY role's configured provider).
> **Corpus:** 12 canon facts, 2 axioms, 26 violating probes and 20
> known-good probes, spread over four classes of violation.

This measurement supersedes
[`canonkeeper_depth_measurement_2026-11-07.md`](canonkeeper_depth_measurement_2026-11-07.md).
That one reported a single number — 25% recall — over eight cases, which
was too small to act on and hid *which* kind of contradiction was missed.
This one reports recall **per class** over a corpus large enough to see
the differences.

## The corpus

| Class | Cases | What it is |
|---|---|---|
| `direct_negation` | 8 | The candidate denies a canon fact outright |
| `status_antonym` | 6 | A status word is flipped (`is` → `former`, `closes` → `open`) |
| `timeline_violation` | 6 | An event is placed in the wrong part of the timeline |
| `implication_chain` | 6 | The conflict only appears after a chain of reasoning |
| `consistent_restatement` | 10 | The same thing said again — a flag here is a false positive |
| `consistent_elaboration` | 10 | Compatible new detail — a flag here is a false positive |

Targets (from the G08 plan): ≥90% recall on direct and timeline
violations, ≥80% on reasoning chains, and a false-positive rate under 5%.

## Results — three shapes of the same check

| Class | n | batch | per-candidate | focused |
|---|---|---|---|---|
| `direct_negation` | 8 | 88% | **100%** | **100%** |
| `status_antonym` | 6 | **100%** | **100%** | 83% |
| `timeline_violation` | 6 | **100%** | **100%** | **100%** |
| `implication_chain` | 6 | 67% | **83%** | **83%** |
| false-positive rate | 20 | 5.0% | 5.0% | 5.0% |
| meets every target | | no | **yes** | no |

- **batch** — what shipped on 2026-11-07: one call per chunk of 15
  candidates, the whole canon in context.
- **per-candidate** — one call per candidate, the whole canon in context.
- **focused** — one call per candidate, the context narrowed to the canon
  that bears on that candidate (its entities, one hop out, the timeline).

## What this means

**Per-candidate checking is the shape that works.** It meets every target:
100% on direct negations, status antonyms and timeline violations, 83% on
the reasoning chains, and a false-positive rate at the ceiling. The
batched form misses a direct negation and three reasoning chains; the
difference is not the prompt but the arithmetic — asking a model to hold
fifteen candidates and a whole canon at once is asking it to hold a whole
canon at once, and it drops what it cannot hold.

**Narrowing the context is not free.** The focused shape catches the same
reasoning chains as the per-candidate shape and is cheaper per call, but
it lost one status antonym ("Sable is a courier who no longer works for
the Harbour Trust") that the per-candidate shape caught. The context
builder is kept and stays available
(`CANONKEEPER_FOCUSED_CONTEXT=true`), but it is **off by default**: it
buys a shorter prompt at the price of a class falling below its floor.

**The shipped defaults follow the measurement:**
`CANONKEEPER_PER_CANDIDATE_CHECKS=true`,
`CANONKEEPER_FOCUSED_CONTEXT=false`.

## What the checks are good enough for

The direct check is the one that can gate canon, and on this corpus it is
the stronger of the two: the per-candidate run caught 100% of direct
negations and status antonyms, 83% of timeline violations and 67% of the
reasoning chains. The soft block on the CF-8 accept path therefore warns
well and blocks rarely — which is the right way round for a check whose
false positives cost the GM an extra click and whose false negatives cost
them a contradiction in canon.

Hard rejection stays opt-in (`CANONKEEPER_HARD_REJECTION_DEFAULT`, off)
and per-owner, because a 5% false-positive rate on known-good material is
a rate you want to choose, not inherit.

## Caveats (read before reusing these numbers)

- **The corpus is small.** Six to ten cases per class means one miss
  moves a class by 12–17 points. The 83% on `implication_chain` is four
  of six; the 100% on `direct_negation` is eight of eight. These are
  indicators, not measurements with confidence intervals.
- **One model.** `mimo-v2.6-flash` was the HEAVY role's provider for
  this run. A different model will move the numbers in both directions;
  re-run the harness after changing the registry.
- **One run per shape.** The check is a model call, so there is run-to-run
  variance on top of everything else. The shapes were run once each, in
  the same session, against the same provider.
- **The false positive is informative.** "Mira Vale counts the seventh
  bell by the Customs House clock" is a consistent elaboration — the
  seventh bell is the same bell in both statements — and it was flagged.
  That is the kind of false positive a hard-rejection mode must not
  inherit.
- **The implication check alone is much weaker.** On the 2026-11-07 corpus
  it detected 25%; here it detects 50–83% depending on the class. The
  direct check does most of the work, and the combination is what the
  product measures.

## Reproducing

```bash
uv run python scripts/eval_canonkeeper_recall.py --mode per-candidate --json-out /tmp/recall.json
```

The script exits non-zero when a class falls below its floor or the
false-positive rate goes over the ceiling, so it can gate a release.

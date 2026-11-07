# CanonKeeper depth measurement — 2026-11-07

> **Method:** hermetic replay of the synthetic narrative corpus
> (`packages/agents/src/monitor_agents/canonkeeper/synthetic_corpus.py`) via
> `scripts/eval_canonkeeper_depth.py --synthetic`. No database, no seeded
> content — required because the seeded universes are mechanical and the
> product boundary (2026-11-07) rules them out.
> **Model:** `qwen2.5:7b` via the local Ollama provider (HEAVY role).
> **Corpus:** 12 canon facts, 16 consistent probes, 8 contradicting probes,
> 12 good state transitions, 3 impossible transitions.

## Results

| Check | False positives | Detection |
|---|---|---|
| Deterministic transition rules (no model) | **0 / 12** | **3 / 3 (100%)** |
| Implication-level contradiction check (LLM) | **0 / 16 (0.0%)** | **2 / 8 (25%)** |

The two detected implication contradictions were "Mira Vale has crossed into
the Burnside district a dozen times" and "Mira Vale no longer works for the
Grey Line" — the two most *direct* contradictions in the set. The remaining
six contradictions (status antonyms, negations of canon) were not flagged.

## What this means

The gap plan's Phase 3 gate — "implication-level stays flag-only until the
false-positive rate on committed proposals is < 5%" — is **met on this
corpus**: 0%. But the detection rate of 25% is the finding that matters.
The implication check is very conservative: it almost never fires, and when
it does, it is right. Enabling hard rejection on it would therefore be safe
*and largely useless* — three out of four real contradictions would still
pass through unflagged.

**Conclusion: keep `CANONKEEPER_REJECT_TRANSITION_VIOLATIONS` off, and keep
the implication check flag-only.** The blocker is no longer "we don't know
the FP rate" but "the check doesn't catch enough to be worth enforcing". The
work that would change the answer is recall, not rejection.

## Caveats (read before reusing these numbers)

- The corpus is **small and hand-written** (16 consistent / 8 contradicting
  probes). These rates are indicative, not statistically robust.
- `qwen2.5:7b` is a mid-size model. The production providers
  (`mistral-large-latest`, the MiniMax M2.7 family) may behave differently —
  this is a floor for the check's capability, not a guarantee about the
  production pipeline.
- A 1B model (`llama3.2:1b`) was tried first and **failed to produce the
  structured output at all** — it returned prose instead of the
  `contradictions`/`implications` fields, so the parse failed soft and the
  measurement produced nothing. Any measurement of this check requires a
  model capable of following the numbered-list output contract.
- The contradicting probes are deliberately obvious (status antonyms,
  negations). A detection rate of 25% *on obvious probes* is a weak result —
  subtler contradictions would likely score worse, not better.

## Follow-ups (in priority order)

1. **Recall, not rejection.** Evaluate whether per-candidate checking (one
  candidate per call, the shape the direct `verify_fact` path uses) detects
  more than the batched numbered-list form. The batch format asks the model
  to hold 15 candidates and a full canon in its head at once, which is the
  most likely reason for the misses.
2. Re-run the same corpus against the production providers
  (`mistral-large-latest`, MiniMax M2.7) to see whether the recall gap is a
  model issue or a prompt issue.
3. Only when detection is meaningfully above chance (and FP stays < 5%),
  revisit Phase 3.

The deterministic transition rules need no such work: 100% detection and no
false positives on the corpus, so they are the part of G-9 that is *safe to
enforce* — but they are also near-dormant in the play loop today (vital-state
tags only arrive via the Forge entity inspector), so there is nothing urgent
to switch on.

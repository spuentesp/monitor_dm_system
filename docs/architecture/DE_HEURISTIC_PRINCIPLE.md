# De-heuristic principle — what we mean by "no regex"

> Status: living document, last updated 2026-07-29 (P-19 pre-play redesign).

## The principle

**No keyword/regex decision in the gameplay path.** When the system has to
choose between game states (roll? / which stat? / combat or social? / which
condition fires?), the answer must come from semantic reasoning — embeddings,
an LLM, or a trained model — not a hand-fed word list. The reason isn't
aesthetic. Hand-fed word lists:

- Can't generalize across genres (`take fire damage` vs `take a fire break`).
- Drift from world vocabulary every time we add a new system.
- Hide bugs (the keyword "matched" but the meaning didn't).
- Punish non-English speakers.

The cost of semantics (an embed call, an LLM verdict) is paid exactly where
the cost of being wrong is paid: in the gameplay turn. There the ratio is
obvious — one extra API call vs one player told "you can't do that."

## What this principle does NOT cover

Pre-filters and stop-lists are a different tool and should be evaluated as
such, not lumped in with gameplay heuristics.

| Surface | Type | Replace with semantics? |
|---|---|---|
| `roll_classifier.classify` (roll necessity) | Gameplay decision | ✅ **Deleted** — the GMAgent LLM emits `roll_necessity` directly (2026-07-17). |
| `classifiers/intent.classify` (player intent) | Gameplay decision | ✅ **Deleted** — the GMAgent LLM emits `intent_type` directly (2026-07-17). |
| `_action_routing.infer_action_context` (stat / DC / subsystem) | Gameplay decision | ✅ Demoted → `RetrievalService.nearest` over schema routes (2026-07-17). |
| `_tracks_conditions.evaluate_scenery_and_conditions` (scenery modifiers) | Gameplay decision | ✅ Demoted → `RetrievalService.nearest` per rule (2026-07-17). |
| `_tracks_conditions.check_condition_triggers` (condition fires?) | Gameplay decision | ✅ Demoted → `RetrievalService.nearest` per trigger (2026-07-17). |
| `scene_loop._is_combat_action` (combat gate) | Gameplay decision | ✅ Removed — folded into the router's `subsystem_hint`. |
| `perception_tools.classify_intent` (intent keyword scores) | Gameplay decision | ✅ Removed — moved to agents/classifiers/intent. |
| `chat_loops.answer_ooc_question` (action probe word list) | Gameplay decision | ✅ Removed — folded into the router. |
| `analyzer._summaries.system_section_score` (`REFERENCE_SECTION_KEYWORDS`) | **Pre-filter before LLM** | ❌ Keep — semantic replacement costs more AND is less accurate. |
| `analyzer._game_filters.is_npc_stat_name` (`_NPC_STAT_PATTERNS`) | **Pre-filter before LLM** | ❌ Keep — same reasoning. |
| `analyzer._social.infer_social_entity_identity` (faction vs org) | Graph-extraction decision | ❌ Keep for now — runs once per extracted entity; can move to LLM batch verification if profile drift shows up. |
| `analyzer._entities.split_semantic_values` (`_INTERIOR_VERBS`, `_SENTENCE_STARTERS`) | **English stop-words** | ❌ Keep — these are morphology, not decisions. Renamed for clarity. |
| `_resolve_base_dc` regex (extract DC number from `success_threshold`) | **Structured parsing** | ❌ Keep — extracts a number from structured text. |
| `resolver._extract_(( ... ))` OOC markers | **Structured parsing** | ❌ Keep — extracts markers from a syntactic format. |
| `_char_generation` dice-formula parsing (`\d*d\d+`) | **Structured parsing** | ❌ Keep — parses a well-defined format. |
| Pre-play `preplay_support.is_ooc_question` (`_OOC_PATTERNS`) | **Pre-filter before LLM** | ❌ Keep — cheap router; semantic replacement costs more than the question it answers. |
| Pre-play `infer_character_name_from_text` regex | **Structured parsing** | ❌ Keep — extracts a name from a self-introduction. |
| Pre-play `handle_char_creation` `_SKIP_RE` regex | **Pre-filter before LLM** | ❌ Keep — single short turn to a deterministic branch; semantic replacement costs more than the decision. |
| `StoryAgreementsLoop` authored prompt collection (`resolve_authored_questions`) | **Authoritative content** | ❌ Keep — a curated prompt collection is content, not a heuristic decision. |

## The litmus test

For any heuristic-looking code that survived this sweep, ask:

1. **Is this deciding between game states?** If yes → must be semantic. Reject.
2. **Is this filtering work before an expensive decision step?** If yes →
   it's a pre-filter, not a decision. Keyword/regex is the right tool — it's
   100× faster and more deterministic. Document it as a pre-filter.
3. **Is this parsing structured text?** If yes → regex is the right tool.
   "Parse a number from `Base target 10; roll under or equal to`" is not a
   heuristic about *meaning*. It's a tokenizer.

When in doubt, the test is: *would replacing this with embeddings make the
end product smarter, or just slower?* If only slower, leave it.

## Where semantics is NOT enough

Embeddings are static vectors — they can't reason over multi-input state.
The remaining gaps the de-heuristic sweep doesn't close:

- **World-aware action understanding** — a 350M–1B param classifier fine-tuned
  on TTRPG corpora could learn that `feeding` has a different DC at `frenzy`
  than at `cold blood`, with the full state as context. Embeddings can't.
- **Multi-turn continuity** — embeddings see one input; a small model can take
  `(action, character_state, world_state, recent_turns)` and decide jointly.
- **Lower latency at scale** — a fine-tuned classifier at 10ms beats an embed
  call + cosine over hundreds of routes.

These are the right places to spend on a small trained model. Embeddings are
the 80%; a small SLM is the next 15%; an LLM verdict is the last 5% (and
already exists in the resolver).

## Classifier-as-tool — the next move

The classifier-as-authority architecture (the resolver composing a verdict
*before* the LLM sees the action) inverts who should be in control.
The fix: classifiers become **sensors the GM (LLM) consults**, not
referees it defers to. The GMAgent owns a ReAct loop over the
``gm_tools`` registry; the resolver becomes a thin harness.

See ``docs/architecture/GM_AS_AUTHORITY.md`` for the full architecture
diagram, the 3-agent split (GMAgent / Narrator / Resolver), the tool
surface, and the migration guide. The principle applies **inside** the
classifier surface too: a future fine-tuned SLM plugs in at the same
boundary (it just answers the same tool questions faster and with more
context than embeddings can).

## Two jobs for embeddings — and only one survived

Making the LLM the decider exposed that embeddings were doing **two**
different jobs, and only one is still legitimate:

1. **Retrieval / enrichment** (RAG over memories, snippets, entities,
   knowledge) — the LLM genuinely needs this; it cannot find "the 5 relevant
   facts about the Shadow Cabal" across a corebook without vectors.
   **Legitimate — kept.**
2. **Classification** (roll necessity, intent) — the GMAgent LLM already
   emits `intent_type` / `roll_necessity` / `action_type` directly. The
   embedding-nearest classifiers were a de-heuristic stepping stone that the
   GM-as-authority refactor made redundant. **Deleted.**

The remaining embedding uses (action routing, condition/scenery matching)
were **demoted**: they are still nearest-in-embedding-space lookups against
the world's own schema, but they now go through a single owner —
`monitor_data.retrieval.RetrievalService.nearest(...)` — rather than each
calling `embed_text` directly. Encapsulating embeddings behind one service
(pinned model, model/dim guard, HyDE + rerank for `retrieve`) is what keeps
index-time and query-time consistent by construction. See
``docs/architecture/RETRIEVAL_SERVICE.md``.

## Audit log

| Date | Surface | Action | Commit |
|---|---|---|---|
| 2026-07-14 | `_action_routing` regex keywords + signal tables | Removed → embeddings + schema | this PR |
| 2026-07-14 | `perception_tools.classify_intent` | Removed → `classifiers/intent.py` | this PR |
| 2026-07-14 | `_tracks_conditions` trigger matching | Replaced → embeddings per trigger | this PR |
| 2026-07-14 | `scene_loop._is_combat_action` | Removed → `subsystem_hint` from router | this PR |
| 2026-07-14 | `chat_loops.answer_ooc_question` action probe list | Removed → router call | this PR |
| 2026-07-14 | Ingestion pre-filters (`REFERENCE_SECTION_KEYWORDS`, `_NPC_STAT_PATTERNS`, `_INTERIOR_VERBS`) | Documented as pre-filters, not decisions | this PR |
| 2026-07-15 | Resolver / Narrator composed 6-classifier verdict as authorities | Refactored → GMAgent + downstream Narrator + thin Resolver | `gm-tool-authority` branch (T1–T8) |
| 2026-07-17 | `roll_classifier` + `classifiers/intent` (roll necessity + intent) | **Deleted** — GMAgent LLM emits both directly; resolver falls back to a thin intent→necessity map | `gm-tool-authority` (P5) |
| 2026-07-17 | `_action_routing` + `_tracks_conditions` embedding calls | Demoted → `RetrievalService.nearest` (one embedding owner) | `gm-tool-authority` (P4) |
| 2026-07-17 | All direct `embed_text`/`embed_batch` retrieval callers | Routed through `RetrievalService` (pinned model, model/dim guard) | `gm-tool-authority` (P1–P3) |
| 2026-07-29 | Session Zero character interview & OOC regex; CC skip-word regex | Documented as pre-filters / structured parsing (kept) | P-19 pre-play redesign |

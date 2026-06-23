# Situated Conversational Retrieval Implementation Plan

> Purpose: improve retrieval of dialogue turns, transcript snippets, and short evidence spans whose meaning depends on surrounding context.
>
> **Implementation status (April 2026):** Ready for implementation. Ingestion-side profile and mindscape artifacts now exist, but the dialogue-specific retrieval layer itself is still not implemented. This plan is the recommended next runtime milestone after the remaining ingestion substrate cleanup.
>
> Source inspiration:
> - Junjie Wu et al., *SitEmb-v1.5: Improved Context-Aware Dense Retrieval for Semantic Association and Long Story Comprehension*, arXiv:2508.01959, 2025. https://arxiv.org/abs/2508.01959
>
> Related MONITOR docs:
> - `docs/architecture/futures/HYBRID_MINDSCAPE_AND_TRAVERSAL_PLAN.md`
> - `docs/architecture/futures/INGESTION_FIRST_CONTEXTUAL_RETRIEVAL_PLAN.md`

---

## Goal

Make short evidence units retrievable with awareness of their local neighborhood.

In MONITOR, this applies to:

- conversation turns
- scene transcript lines
- short lore snippets
- rule examples embedded in longer chapters
- recap and clue recovery from prior scenes

The central idea is simple:

> retrieve short evidence spans, but represent them with context from the nearby turns or sections.

---

## Why this matters in MONITOR

A single line in play is often ambiguous on its own.
Its meaning depends on:

- who said it
- what happened immediately before
- the scene stakes
- the social relationship in play
- the current topic or clue trail

This is a direct fit for NPC dialogue recall and session transcript querying.

---

## Retrieval units

Recommended local evidence units:

| Unit | Example |
|---|---|
| Conversation turn | one player or NPC utterance |
| Turn window | current turn plus nearby turns |
| Scene snippet | short passage from the active or prior scene |
| Local rules example | a small example embedded in a longer rules chapter |

For each unit, MONITOR should preserve both the raw text and its nearby context summary.

---

## Data shape

For each retrievable turn or snippet, store:

- raw text
- speaker / actor metadata
- scene id, story id, universe id
- neighboring turn ids
- short local summary
- optional neighborhood summary
- embedding for the raw unit
- optional embedding for the situated representation

---

## Proposed runtime flow

```text
query about a conversation or clue
  -> detect dialogue / recap / clue intent
  -> prefer transcript and turn-level retrieval
  -> search using raw + situated representations
  -> rerank by speaker, scene, recency, and local coherence
  -> return the best turn bundle and nearby support
```

---

## Concrete code map

### Layer ownership

| Concern | Put code in | Do not put it in |
|---|---|---|
| Conversation session data shape | `packages/data-layer/src/monitor_data/schemas/conversations.py` | agent prompt code |
| Turn persistence and staging | `packages/agents/src/monitor_agents/npc_voice.py` and `loops/conversation_loop.py` | CLI |
| Turn-window selection and reranking | new `packages/agents/src/monitor_agents/utils/conversation_retrieval.py` | scattered branches across multiple agents |
| Runtime retrieval orchestration | `packages/agents/src/monitor_agents/context_assembly.py` | Mongo schema code |

### Symbols to add

#### Data-layer
Extend conversation payloads with optional metadata fields such as:
- `scene_id`
- `story_id`
- `speaker_role`
- `speaker_entity_id`
- `neighbor_turn_ids`
- `tags` or `retrieval_hints`

Keep these as plain fields in the existing conversation schema rather than inventing a second conversation model.

#### Agents layer
Add a focused helper module:
- `packages/agents/src/monitor_agents/utils/conversation_retrieval.py`

Recommended functions:
- `build_turn_window()`
- `summarize_turn_window()`
- `score_dialogue_hit()`
- `select_dialogue_candidates()`
- `is_dialogue_query()`

### Concrete file edits

1. `packages/agents/src/monitor_agents/loops/conversation_loop.py`
   - ensure turn metadata needed for retrieval is always present
   - keep loop orchestration only; avoid embedding retrieval logic here

2. `packages/agents/src/monitor_agents/npc_voice.py`
   - emit richer memory and turn metadata for later retrieval
   - keep response generation separate from retrieval ranking helpers

3. `packages/agents/src/monitor_agents/context_assembly.py`
   - add a dialogue-aware branch that activates when the query is about promises, clues, suspicion, prior speech, or recap
   - call shared helper functions instead of adding more inline ranking code

4. optional later: transcript-to-Qdrant indexing helpers in the agents layer so conversation turns can be searched as first-class evidence units

### Test placement

Add or extend tests in:
- `packages/agents/tests/test_context_assembly.py`
- `packages/agents/tests/test_npc_voice.py`
- `packages/agents/tests/test_conversation_loop.py`

### SOLID / DRY guardrails

- keep dialogue retrieval heuristics in one helper module, not duplicated across `NPCVoice`, `Narrator`, and `ContextAssembly`
- do not overload `NPCVoice` with transcript search responsibilities; it should generate and persist, not rank retrieval candidates
- keep scene / speaker scoring rules centralized so dialogue behavior stays consistent across play surfaces

---

## Implementation phases

### Phase 1 — Turn-aware indexing

**Files**
- transcript / conversation persistence surfaces
- `packages/agents/src/monitor_agents/npc_voice.py`
- `packages/agents/src/monitor_agents/loops/conversation_loop.py`

**Tasks**
1. ensure each turn is persisted as its own retrievable evidence unit
2. attach speaker, scene, and relationship metadata
3. keep neighboring-turn references for local context reconstruction

### Phase 2 — Situated summaries

**Files**
- `packages/agents/src/monitor_agents/analyzer.py`
- helper utilities in the agents layer

**Tasks**
1. create short summaries for turn windows or local transcript neighborhoods
2. store these alongside the raw turns
3. embed both the raw text and its contextualized form when useful

### Phase 3 — Contextual reranking

**Files**
- `packages/agents/src/monitor_agents/context_assembly.py`
- Qdrant filtering / reranking helpers

**Tasks**
1. bias retrieval toward the active scene and relevant speakers
2. favor nearby turn bundles over isolated single lines when the query is ambiguous
3. surface both answer evidence and clue evidence for conversational questions

### Phase 4 — Dialogue-specialized retrieval policies

**Tasks**
1. detect questions like “what did they promise,” “why are they suspicious,” or “what clue did we miss”
2. route those queries to a dialogue-aware retrieval path first
3. only broaden to general retrieval if the dialogue path is weak

---

## Acceptance criteria

- transcript retrieval improves for dialogue-heavy questions
- NPC recall stays grounded in what was actually said
- clue retrieval surfaces nearby supporting turns, not just isolated quotes
- conversation recaps become more coherent and evidence-backed

---

## Recommended first implementation

Start with two concrete PRs.

### PR 1 — turn-aware evidence plumbing
1. treat turns as first-class evidence units
2. add neighboring-turn metadata
3. keep scene, story, and speaker fields populated consistently

### PR 2 — dialogue-aware retrieval path
1. add a shared conversation retrieval helper module
2. generate local turn-window summaries
3. rerank transcript retrieval with scene and speaker awareness
4. route promise, clue, suspicion, and recap questions into this path first

That should produce immediate gains for conversational play without needing a custom embedding training pipeline first.
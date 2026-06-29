# Session Zero — Implementation Plan

> **Goal:** Add a guided, story-first character development phase ("Session Zero")
> between the GM opening message and mechanical character creation / active play.
> Inspired by Legend of the Five Rings' 20 Questions, Dungeon World bonds, and
> the VtM20 Prelude pattern.

## Architecture

```
build_gm_opening (scene + "who are you?")
  → player responds
  → run_preplay_turn detects substantive response
  → SessionZeroLoop.start()  ← NEW
      │
      ├─ interview_node: asks ONE evocative question at a time
      │   (DSPy SessionZeroSignature, tone + system + lore aware)
      ├─ summarize_node: distills answers into character concept + backstory
      └─ transition: hands off to CharacterCreationLoop (mechanics)
          or narrative-only mode (skip stats)
  → active_play with prologue scene
```

### Phase state machine (updated)

```
awaiting_character → session_zero → char_creation → active_play
                                              ↘ (narrative-only) → active_play
```

## Implementation Steps

### Step 1: SessionZeroSignature DSPy module
- [x] Create `packages/agents/src/monitor_agents/session_zero.py`
- [x] Pydantic model: `SessionZeroQuestion` (question text, question category, is_final)
- [x] DSPy Signature: tone, system, lore, prior answers → next question
- [x] DSPy Module: `SessionZeroModule` wrapping `Predict(SessionZeroSignature)`
- [x] `prediction_to_question()` converter (lenient parsing)
- [x] `ask_session_zero_question()` async entry point (mirrors `check_gm_awareness`)
- [x] Fallback question generator (no LLM needed)
- [x] `SessionZeroSummarySignature` + `summarize_session_zero_answers()` for distilling answers

### Step 2: SessionZeroLoop LangGraph graph
- [x] Create `packages/agents/src/monitor_agents/loops/session_zero_loop.py`
- [x] State: `SessionZeroState` (answers, question_count, concept, backstory, complete)
- [x] Nodes: `ask_question → await_player → process_answer → (loop or summarize)`
- [x] `summarize_node`: LLM call to distill answers into concept + backstory
- [x] `SessionZeroLoop` class with `start()` and `process_player_input()` methods
- [x] Max questions configurable (default 7, inspired by L5R but shorter)

### Step 3: Register in dspy_runtime
- [x] Add `session_zero` to `_NODE_DEFAULT_ROLES` with `ModelRole.LIGHT`

### Step 4: Add session_zero phase routing in chat router
- [x] Update `chat.py` phase routing to handle `session_zero` phase (both REST and WS paths)
- [x] Route `session_zero` turns to `run_preplay_turn` (which dispatches to SessionZeroLoop)
- [x] Add `pop_session_zero_loop` to `delete_session` cleanup

### Step 5: Wire SessionZeroLoop into run_preplay_turn
- [x] Add `_SESSION_ZERO_AVAILABLE` import guard in `chat_loops.py`
- [x] Add `_SESSION_ZERO_LOOPS` cache + `get_session_zero_loop` / `pop_session_zero_loop`
- [x] In `run_preplay_turn`: when player describes character, start SessionZeroLoop
  instead of jumping directly to char_creation
- [x] When in `session_zero` phase, route to SessionZeroLoop.process_player_input()
- [x] When SessionZeroLoop completes, transition to char_creation or active_play

### Step 6: Prologue handoff
- [x] Added `_generate_prologue()` helper in `chat_loops.py`
- [x] After session zero completes (narrative-only path), generate a prologue opening
  that incorporates the character's backstory using `Narrator.generate_opening`
- [x] Transition to `active_play` with the prologue as the first GM message
- [x] After session zero completes (mechanics path), hand off to CharacterCreationLoop

### Step 7: Gold-set prompt tests
- [x] Create `packages/agents/tests/test_session_zero_prompts.py`
- [x] Golden inputs: tone + system + prior answers → expected question category
- [x] `metric()` function scoring question quality
- [x] Parser mutation tests (category aliases, is_final parsing, empty values)
- [x] Summary parser tests
- [x] Fallback question tests (all 6 tones)
- [x] Fallback summary tests
- [x] All 37 tests passing

### Step 8: Choreography behavior tests
- [x] Create `tests/behavior/test_session_zero_loop_choreography_behavior.py`
- [x] Test state transitions, max questions, summarize, fallback
- [x] Test SessionZeroLoop.start() and process_player_input() without LLM
- [x] Test stop signals ("done", "skip", "that's all")
- [x] Test summary generation and name extraction
- [x] Test graph builder and routing functions
- [x] Test LLM integration with mocks
- [x] All 27 tests passing

### Step 9: Run full test suite
- [x] `uv run pytest packages/agents -q` — **1164 passed, 2 skipped, 0 failed**
- [x] `uv run pytest tests/behavior -q` — **1009 passed, 23 skipped, 0 failed**
- [x] `uv run pytest packages/ui/backend -k "chat or preplay or phase"` — **17 passed, 0 failed**
- [x] No regressions detected

### Step 10: Update plan with completion marks
- [x] Mark all steps complete in this document

## Key Design Decisions

1. **DSPy over instructor** — the prompt IS the test surface (same as GMAwareness)
2. **One question at a time** — follows UC-GM-3 principle
3. **Tone-aware questions** — grim settings ask about loss, heroic about quests
4. **Lore-aware** — questions reference world facts when available
5. **Adaptive** — LLM sees prior answers and adapts the next question
6. **Bounded** — max 7 questions (not 20) to respect player patience
7. **Graceful fallback** — if LLM fails, use canned tone-based questions
8. **Separate loop** — doesn't modify CharacterCreationLoop (mechanics stay separate)
9. **Prologue handoff** — backstory feeds into the opening scene narration

## Files to Create

| File | Layer | Purpose |
|------|-------|---------|
| `packages/agents/src/monitor_agents/session_zero.py` | 2 | DSPy signature, module, entry point |
| `packages/agents/src/monitor_agents/loops/session_zero_loop.py` | 2 | LangGraph loop |
| `packages/agents/tests/test_session_zero_prompts.py` | test | Gold-set prompt tests |
| `tests/behavior/test_session_zero_loop_choreography_behavior.py` | test | Choreography tests |

## Files to Modify

| File | Change |
|------|--------|
| `packages/agents/src/monitor_agents/dspy_runtime.py` | Add `session_zero` to role map |
| `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` | Wire SessionZeroLoop into preplay |
| `packages/ui/backend/src/monitor_ui/routers/chat.py` | Add `session_zero` phase routing |
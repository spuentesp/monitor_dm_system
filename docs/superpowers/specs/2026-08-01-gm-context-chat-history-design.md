# GM Context — Chat History Carry-Over (Design)

Date: 2026-08-01
Status: Approved (design), pending spec review
Approach: A — Three controlled channels

## Problem

The GM (Narrator) never sees the session's chat history. `chat_messages` is read
nowhere in `packages/agents/src`; each turn's context is assembled from scene
turns (IC-only, last 10), Neo4j entities, Qdrant memories, lorebook hits, plot
threads, and the game-system profile. Consequences observed in real sessions:

- Session-0 negotiation (character definitions, tone, boundaries) is invisible
  once narration starts → "characters are ill-defined", narration is generic.
- OOC Q&A answers contain facts the player assumes are true → contradictions.
- No short-term conversational continuity → narration feels disconnected.

## Goal

Carry chat history into GM context through three controlled, labeled,
hard-capped channels — without raw-log noise and without meta-leak into fiction.

Non-goal: changing how the UI displays chat; this is backend/agents only.

## Architecture

All three channels ride the existing director-notes path:
`get_scene_loop` (`packages/ui/backend/src/monitor_ui/routers/chat_loops.py`)
hands session state to `SceneLoop.__init__`, `run()` copies it into
`SceneState`, and the Narrator renders blocks into `profile_context`
(`packages/agents/src/monitor_agents/narrator/agent.py`, alongside the existing
`ESTABLISHED FACTS` block at `agent.py:418-423`).

Nothing goes through `ContextAssembly.assemble()` — its Redis cache would serve
stale session data. Each block is omitted entirely when empty.

## Channel 1 — Session-0 → canon (at `begin_story`)

### Required intake (new requirement)

Session zero, for **all** games, must at minimum ask for:

- character **name**
- character **origin** (background)
- character **general appearance**
- and end with a **small story review** (a recap of what was agreed, presented
  for confirmation before the story can begin).

Implementation: a baseline question set (name / origin / appearance) merged
into the output of `resolve_authored_session_zero_questions()`
(`packages/agents/src/monitor_agents/loops/preplay_support.py:634`), deduped
against authored pack questions. The story review is a confirmation step in the
session-zero phase: the agreements/summary is presented, and `begin_story`
requires it to have been shown (the existing
`story_agreements_summary` metadata gate stays the trigger).

### Canon seeding

When `begin_story` fires and `canon_seeded` is not set on the session:

1. Build the canon payload from the already-structured session data —
   `character_summary` (name, concept/origin, appearance, backstory),
   `story_premise`, `tone`. (The approved design originally called for an
   LLM extraction pass over the session-0 chat; this was simplified during
   planning because the intake answers are already distilled into
   `character_summary` by the interview loop — an extra LLM pass adds
   latency and failure modes without adding information.)
2. Characters themselves are already persisted by the pre-play flow via the
   existing helpers (`persist_session_character` / `_persist_generated_entity`,
   `preplay_support.py:217,325`). Note: these helpers write entities directly
   with `Authority.SYSTEM` / `CanonLevel.CANON` — the established pre-play
   exception to the CanonKeeper-only Neo4j write rule. We reuse that path
   as-is; no new write path is introduced.
3. The character payload becomes a high-importance Qdrant-searchable memory
   (MongoDB `mongodb_create_memory`, which embeds via its hook) so
   ContextAssembly retrieves who the PC is on every turn.
4. Premise/tone append to `director_notes` (feeds `ESTABLISHED FACTS`).
5. Set `session["canon_seeded"] = True` first, so failures still never re-run.

Failure at any step → log, continue; the story still starts unseeded (today's
behavior).

## Channel 2 — OOC TABLE TALK

- `answer_ooc_question` (`preplay_support.py:428`) appends
  `{question, answer, timestamp}` to `session["ooc_exchanges"]` — in-place list
  reference, same pattern as `director_notes`. Cap 8, drop oldest.
- `get_scene_loop` passes the reference into `SceneLoop`; `run()` copies it
  into `SceneState`.
- Narrator renders, narrator only (resolver does not need table talk):

  ```
  TABLE TALK (out-of-character discussion — background only; never reference this channel in fiction):
  Q: ...
  A: ...
  ```

- Each entry truncated to ~300 chars at render time.

## Channel 3 — Raw recent tail

- `get_scene_loop` already loads the session's `chat_messages` for the UI; it
  passes the last 6 messages (both modes) into `SceneLoop` as `recent_chat`.
  No new MCP tool.
- Narrator renders `[IC]` / `[OOC]`-labeled lines under
  `RECENT TABLE CONVERSATION`, hard-capped at ~500 tokens total, oldest dropped
  first.

## Error handling & invariants

- Every channel degrades to silence: missing/empty field → no block, no
  exception.
- Caps enforced at render time (not only at write time), so a hand-edited
  session cannot blow the prompt.
- IC/OOC labels are fixed strings; the narrator signature treats them as
  provenance, not content, and is instructed never to reference the OOC
  channel in fiction.

## Testing

- `packages/agents/tests/test_begin_story_command.py`:
  - OOC exchange persistence + 8-cap.
  - Canon seeding: memory write with faked `mongodb_create_memory`;
    premise/tone → director_notes; `canon_seeded` idempotency; failure
    degrades to a log line.
  - Baseline session-0 questions (name/origin/appearance) present even with no
    authored pack questions; dedupe against authored ones.
  - Story review presented before begin-story confirmation.
- `packages/agents/tests/test_scene_loop.py`: state carries
  `ooc_exchanges` / `recent_chat`; narrator renders both blocks, respects caps,
  omits empty blocks.
- `packages/ui/backend/tests/`: `get_scene_loop` wires the new fields.
- Full agents + UI backend suites green; ruff/mypy/layer-deps clean.

## Explicitly out of scope

- Raw full-log injection (Approach C) and LLM-distilled memory-only (B).
- Frontend changes.
- Migrating existing sessions (their poisoned history stays; fresh sessions
  benefit).

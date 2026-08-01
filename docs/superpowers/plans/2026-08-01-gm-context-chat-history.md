# GM Context — Chat History Carry-Over Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry chat history into GM context through three controlled channels — OOC table talk, a raw recent tail, and session-0 canon seeding — so narration stops contradicting what the table established.

**Architecture:** New session state (`ooc_exchanges`, `chat_log`) rides the existing director-notes path: `get_scene_loop` → `SceneLoop.__init__` → `SceneState` → narrator `context` dict → labeled blocks in `profile_context`. Session-0 improvements (baseline questions, appearance in summary, story review recap) feed a one-time canon seeding at `begin_story` that writes a Qdrant memory and director notes.

**Tech Stack:** Python 3.11, Pydantic v2, DSPy, LangGraph, FastAPI, pytest. Repo: three-layer monorepo (`monitor-data` L1 / `monitor-agents` L2 / `monitor-cli` + `monitor_ui` L3).

**Spec:** `docs/superpowers/specs/2026-08-01-gm-context-chat-history-design.md`

## Global Constraints

- Caps (enforced at render time, not just write time): OOC exchanges 8, each entry ≤ 300 chars; recent tail 6 messages, ≤ 500 tokens; established facts 20; director notes 20.
- Every channel degrades to silence: missing/empty field → no block, no exception.
- Blocks are self-labeling: `TABLE TALK (…never reference this channel in fiction)`, `RECENT TABLE CONVERSATION` with `[IC]`/`[OOC]` prefixes.
- No direct Neo4j writes from agents beyond the existing pre-play exception (`_persist_generated_entity`, `Authority.SYSTEM`). Canon seeding writes MongoDB memories only (Qdrant embedding happens inside the `mongodb_create_memory` hook).
- No frontend changes.
- Minimal diffs: do NOT reformat pre-existing `ruff format` drift in `preplay_support.py` / `chat.py`.
- Tests: `uv run pytest packages/agents -q`, `uv run pytest packages/ui/backend -q`. Lint: `uv run ruff check packages`, `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`, `python scripts/check_layer_dependencies.py`.
- Test fakes follow the existing pattern in `packages/agents/tests/test_begin_story_command.py` (`_FakePredict` + `dspy_context_for` patched to a nullcontext).

---

### Task 1: Persist OOC Q&A exchanges on the session

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/preplay_support.py` (add `record_ooc_exchange` after `record_director_note` at line 176; rename `answer_ooc_question` body at line 428 to `_compose_ooc_answer`; add thin wrapper)
- Test: `packages/agents/tests/test_ooc_exchanges.py` (new)

**Interfaces:**
- Consumes: existing `normalize_ooc_text(text) -> str` (preplay_support.py:29).
- Produces:
  - `OOC_EXCHANGES_CAP = 8` (module constant)
  - `record_ooc_exchange(session: dict[str, Any], question: str, answer: str) -> None` — appends `{"question", "answer", "timestamp"}` to `session["ooc_exchanges"]` (in-place, cap 8 drop oldest).
  - `answer_ooc_question(session, question, *, session_game_system_doc, gsr_available) -> str` — UNCHANGED signature; now records the exchange before returning.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for OOC exchange persistence (TABLE TALK channel, write side)."""

from __future__ import annotations

from typing import Any

import pytest

from monitor_agents.loops import preplay_support
from monitor_agents.loops.preplay_support import (
    OOC_EXCHANGES_CAP,
    answer_ooc_question,
    record_ooc_exchange,
)


def test_record_ooc_exchange_appends_and_caps() -> None:
    session: dict[str, Any] = {}
    for i in range(OOC_EXCHANGES_CAP + 3):
        record_ooc_exchange(session, f"question {i}", f"answer {i}")
    exchanges = session["ooc_exchanges"]
    assert len(exchanges) == OOC_EXCHANGES_CAP
    # Oldest dropped: first surviving entry is question 3.
    assert exchanges[0]["question"] == "question 3"
    assert exchanges[-1]["question"] == f"question {OOC_EXCHANGES_CAP + 2}"
    assert set(exchanges[0]) == {"question", "answer", "timestamp"}


@pytest.mark.asyncio
async def test_answer_ooc_question_records_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even the fallback (LLM down) answer must be recorded."""
    import dspy

    class _BoomPredict:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __call__(self, **kwargs: Any) -> Any:
            raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(dspy, "Predict", _BoomPredict)
    session: dict[str, Any] = {"director_notes": []}
    answer = await answer_ooc_question(
        session,
        "((what do I roll to sneak?))",
        session_game_system_doc=None,
        gsr_available=False,
    )
    assert answer
    exchanges = session.get("ooc_exchanges")
    assert isinstance(exchanges, list) and len(exchanges) == 1
    assert exchanges[0]["answer"] == answer
    assert "sneak" in exchanges[0]["question"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_ooc_exchanges.py -v`
Expected: FAIL — `ImportError: cannot import name 'OOC_EXCHANGES_CAP'`

- [ ] **Step 3: Write minimal implementation**

In `preplay_support.py`, after `record_director_note` (ends ~line 200):

```python
OOC_EXCHANGES_CAP = 8


def record_ooc_exchange(session: dict[str, Any], question: str, answer: str) -> None:
    """Append an OOC Q&A pair to the session for later narrator context.

    In-place append (same shared-reference pattern as director notes) so a
    cached SceneLoop sees new exchanges on the next turn. Cap: newest 8.
    """
    exchanges = session.setdefault("ooc_exchanges", [])
    if not isinstance(exchanges, list):
        exchanges = session["ooc_exchanges"] = []
    exchanges.append(
        {
            "question": question.strip(),
            "answer": answer.strip(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    del exchanges[:-OOC_EXCHANGES_CAP]
```

Ensure `from datetime import UTC, datetime` is imported at module top (check existing imports first; the module already imports `datetime` only if present — add if missing).

Then rename the existing `async def answer_ooc_question(...)` (line 428) to `async def _compose_ooc_answer(...)` with an unchanged body, and add the wrapper directly above it:

```python
async def answer_ooc_question(
    session: dict[str, Any],
    question: str,
    *,
    session_game_system_doc: Any,
    gsr_available: bool,
) -> str:
    """Answer an OOC message and record the exchange for later GM context."""
    answer = await _compose_ooc_answer(
        session,
        question,
        session_game_system_doc=session_game_system_doc,
        gsr_available=gsr_available,
    )
    record_ooc_exchange(session, normalize_ooc_text(question), answer)
    return answer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/agents/tests/test_ooc_exchanges.py packages/agents/tests/test_begin_story_command.py -q`
Expected: PASS (both files — the rename must not break existing callers; existing tests import `answer_ooc_question`, which keeps its signature).

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/preplay_support.py packages/agents/tests/test_ooc_exchanges.py
git commit -m "feat: persist OOC Q&A exchanges on session (cap 8)"
```

---

### Task 2: TABLE TALK channel — plumb `ooc_exchanges` into narrator context

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/scene_loop.py` — `SceneState` (field after `established_facts`, line 174), `SceneLoop.__init__` (line 994), `SceneLoop.run` (`SceneState(...)` at line 1061), `narrate` node context dict (line 401)
- Modify: `packages/agents/src/monitor_agents/narrator/agent.py` — module-level helper + injection after the established-facts block (line 423)
- Modify: `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` — `get_scene_loop` (line 237)
- Test: `packages/agents/tests/test_table_talk_context.py` (new)

**Interfaces:**
- Consumes: `session["ooc_exchanges"]` from Task 1.
- Produces:
  - `SceneState.ooc_exchanges: list[dict[str, Any]]` (default `[]`)
  - `SceneLoop(..., ooc_exchanges: list[dict[str, Any]] | None = None)` — kept as a REFERENCE like `director_notes`.
  - `_table_talk_block(ooc_exchanges: Any, *, cap: int = 8, max_chars: int = 300) -> str` in `narrator/agent.py` module scope. Returns `""` when empty.
  - narrator `context` dict key `"ooc_exchanges"`.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the TABLE TALK narrator context block (read side)."""

from __future__ import annotations

from typing import Any

from monitor_agents.narrator.agent import _table_talk_block
from monitor_agents.loops.scene_loop import SceneLoop, SceneState


def _pairs(n: int) -> list[dict[str, str]]:
    return [{"question": f"q{i}", "answer": f"a{i}", "timestamp": "t"} for i in range(n)]


def test_table_talk_block_renders_pairs() -> None:
    block = _table_talk_block(_pairs(2))
    assert "TABLE TALK" in block
    assert "never reference this channel in fiction" in block
    assert "Q: q0\nA: a0\n" in block
    assert "Q: q1\nA: a1\n" in block


def test_table_talk_block_empty_is_silent() -> None:
    assert _table_talk_block([]) == ""
    assert _table_talk_block(None) == ""
    assert _table_talk_block("junk") == ""


def test_table_talk_block_caps_entries_and_chars() -> None:
    pairs = _pairs(12)
    pairs.append({"question": "x" * 500, "answer": "y" * 500, "timestamp": "t"})
    block = _table_talk_block(pairs)
    assert block.count("Q:") == 8  # cap
    assert "x" * 301 not in block  # 300-char truncation
    assert "q3" not in block  # oldest dropped


def test_scene_state_carries_ooc_exchanges() -> None:
    import uuid

    exchanges = _pairs(1)
    state = SceneState(
        scene_id=uuid.uuid4(),
        story_id=uuid.uuid4(),
        ooc_exchanges=exchanges,
    )
    assert state.ooc_exchanges == exchanges
```

The test file's imports then only need `_table_talk_block` and `SceneState` (drop `SceneLoop` from the import).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_table_talk_context.py -v`
Expected: FAIL — `ImportError: cannot import name '_table_talk_block'`

- [ ] **Step 3: Write minimal implementation**

1. `narrator/agent.py`, module level (near other helpers, before the `Narrator` class):

```python
def _table_talk_block(ooc_exchanges: Any, *, cap: int = 8, max_chars: int = 300) -> str:
    """Render OOC Q&A pairs as a labeled, capped context block ("" when empty)."""
    if not isinstance(ooc_exchanges, list) or not ooc_exchanges:
        return ""
    lines = ""
    count = 0
    for pair in ooc_exchanges[-cap:]:
        if not isinstance(pair, dict):
            continue
        q = str(pair.get("question") or "")[:max_chars].strip()
        a = str(pair.get("answer") or "")[:max_chars].strip()
        if not q and not a:
            continue
        lines += f"Q: {q}\nA: {a}\n"
        count += 1
    if not count:
        return ""
    return (
        "\n\nTABLE TALK (out-of-character discussion — background only; "
        "never reference this channel in fiction):\n" + lines
    )
```

2. `narrator/agent.py`, after the established-facts injection (after line 423 `profile_context += facts_block`):

```python
        # Inject OOC table talk (player questions + GM answers) as background.
        profile_context += _table_talk_block(context.get("ooc_exchanges"))
```

3. `scene_loop.py` `SceneState`, after `established_facts` (line 174):

```python
    # OOC table talk (Q&A pairs) from the session, rendered by the Narrator.
    ooc_exchanges: list[dict[str, Any]] = Field(default_factory=list)
```

4. `scene_loop.py` `SceneLoop.__init__`: add param `ooc_exchanges: list[dict[str, Any]] | None = None` after `director_notes`, and after the `self.director_notes` assignment:

```python
        # OOC Q&A exchanges — REFERENCE to the session's list (same pattern
        # as director_notes) so answers given mid-scene show up next turn.
        self.ooc_exchanges = ooc_exchanges if ooc_exchanges is not None else []
```

5. `scene_loop.py` `run()`, in the `SceneState(...)` call after `established_facts=...`:

```python
                ooc_exchanges=list(getattr(self, "ooc_exchanges", []) or []),
```

6. `scene_loop.py` `narrate` node, context dict (after `"established_facts": state.established_facts,`):

```python
            "ooc_exchanges": state.ooc_exchanges,
```

7. `chat_loops.py` `get_scene_loop`, in the `SceneLoop(...)` call after `director_notes=...`:

```python
        # Shared reference: OOC answers appended after this loop is cached
        # must be visible on the next turn.
        ooc_exchanges=session.setdefault("ooc_exchanges", []),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agents/tests/test_table_talk_context.py packages/agents/tests/test_scene_loop.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/scene_loop.py packages/agents/src/monitor_agents/narrator/agent.py packages/ui/backend/src/monitor_ui/routers/chat_loops.py packages/agents/tests/test_table_talk_context.py
git commit -m "feat: render OOC table talk as labeled narrator context block"
```

---

### Task 3: RECENT TABLE CONVERSATION — raw chat tail into narrator context

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/scene_orchestrator.py` — helper + `get_scene_loop` call site (line 260)
- Modify: `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` — `get_scene_loop` signature (line 210) + cache-hit refresh + `SceneLoop(...)` call
- Modify: `packages/agents/src/monitor_agents/loops/scene_loop.py` — `_chat_tail` module helper, `SceneState.recent_chat`, `SceneLoop.__init__` (`chat_log` param), `run()`, `narrate` node
- Modify: `packages/agents/src/monitor_agents/narrator/agent.py` — `_recent_chat_block` helper + injection after the TABLE TALK injection
- Test: `packages/agents/tests/test_recent_chat_context.py` (new)
- Test: `packages/ui/backend/tests/test_scene_loop_chat_wiring.py` (new)

**Interfaces:**
- Consumes: UI message dicts `{"role": str, "content": str, "metadata": {"chat_mode": "ic"|"ooc"} | None, "chat_mode": str | None}` (see `make_player_message`/`make_gm_message`, chat.py:179, 883).
- Produces:
  - `_chat_log_for(callbacks: Any, session_id: str) -> list[Any] | None` in `scene_orchestrator.py`.
  - `get_scene_loop(..., chat_log: list[Any] | None = None)` — refreshes `loop.chat_log` even on cache hit.
  - `SceneLoop(..., chat_log: list[Any] | None = None)` — attribute `self.chat_log`.
  - `_chat_tail(chat_log: Any, *, limit: int = 6) -> list[dict[str, str]]` in `scene_loop.py` — items `{"role", "mode", "content"}`.
  - `SceneState.recent_chat: list[dict[str, Any]]`.
  - `_recent_chat_block(recent_chat: Any, *, max_tokens: int = 500) -> str` in `narrator/agent.py`.
  - narrator `context` dict key `"recent_chat"`.

- [ ] **Step 1: Write the failing tests**

`packages/agents/tests/test_recent_chat_context.py`:

```python
"""Tests for the raw recent-chat tail (RECENT TABLE CONVERSATION channel)."""

from __future__ import annotations

from typing import Any

from monitor_agents.loops.scene_loop import _chat_tail
from monitor_agents.narrator.agent import _recent_chat_block


def _msg(role: str, content: str, mode: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": role, "content": content}
    if mode:
        msg["metadata"] = {"chat_mode": mode}
    return msg


def test_chat_tail_takes_last_six_and_labels_mode() -> None:
    log = [_msg("player", f"m{i}") for i in range(8)]
    log[7] = _msg("player", "ooc note", "ooc")
    tail = _chat_tail(log)
    assert len(tail) == 6
    assert tail[0]["content"] == "m2"
    assert tail[-1] == {"role": "player", "mode": "ooc", "content": "ooc note"}
    assert tail[0]["mode"] == "ic"


def test_chat_tail_handles_junk() -> None:
    assert _chat_tail(None) == []
    assert _chat_tail([{"role": "player"}, "junk", {"content": ""}]) == []


def test_recent_chat_block_renders_and_caps_tokens() -> None:
    tail = [{"role": "gm", "mode": "ic", "content": "word " * 200}]
    block = _recent_chat_block(tail, max_tokens=40)
    assert "RECENT TABLE CONVERSATION" in block
    assert "[IC] gm:" in block
    assert len(block) < len("word " * 200)  # truncated


def test_recent_chat_block_empty_is_silent() -> None:
    assert _recent_chat_block([]) == ""
    assert _recent_chat_block(None) == ""
```

`packages/ui/backend/tests/test_scene_loop_chat_wiring.py`:

```python
"""get_scene_loop wiring: chat_log + ooc_exchanges reach SceneLoop."""

from __future__ import annotations

from typing import Any

from monitor_ui.routers import chat_loops


class _FakeLoop:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.chat_log = kwargs.get("chat_log")


def test_get_scene_loop_passes_and_refreshes_chat_log(monkeypatch) -> None:
    monkeypatch.setattr(chat_loops, "SceneLoop", _FakeLoop)
    chat_loops._SCENE_LOOPS.clear()
    session: dict[str, Any] = {"ooc_exchanges": [{"question": "q", "answer": "a"}]}
    sid = "s1"
    scene_id = "11111111-1111-1111-1111-111111111111"
    story_id = "22222222-2222-2222-2222-222222222222"

    log1 = [{"role": "player", "content": "hi"}]
    loop1 = chat_loops.get_scene_loop(sid, session, scene_id=scene_id, story_id=story_id, chat_log=log1)
    assert loop1.kwargs["chat_log"] is log1
    assert loop1.kwargs["ooc_exchanges"] is session["ooc_exchanges"]

    # Cache hit: same signature, but the chat log reference must refresh.
    log2 = [{"role": "player", "content": "hi"}, {"role": "gm", "content": "yo"}]
    loop2 = chat_loops.get_scene_loop(sid, session, scene_id=scene_id, story_id=story_id, chat_log=log2)
    assert loop2 is loop1
    assert loop2.chat_log is log2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agents/tests/test_recent_chat_context.py packages/ui/backend/tests/test_scene_loop_chat_wiring.py -v`
Expected: FAIL — `ImportError: cannot import name '_chat_tail'`; backend: `TypeError: get_scene_loop() got an unexpected keyword argument 'chat_log'`

- [ ] **Step 3: Write minimal implementation**

1. `scene_loop.py`, module level (near `route_after_narration`):

```python
def _chat_tail(chat_log: Any, *, limit: int = 6) -> list[dict[str, str]]:
    """Last `limit` chat messages as {role, mode, content} dicts (IC/OOC labeled)."""
    if not isinstance(chat_log, list) or not chat_log:
        return []
    tail: list[dict[str, str]] = []
    for m in chat_log[-limit:]:
        if not isinstance(m, dict):
            continue
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
        mode = str(m.get("chat_mode") or meta.get("chat_mode") or "ic")
        tail.append({"role": str(m.get("role") or "?"), "mode": mode, "content": content})
    return tail
```

2. `scene_loop.py` `SceneState`, after `ooc_exchanges`:

```python
    # Raw recent chat tail (IC + OOC, labeled) rendered by the Narrator.
    recent_chat: list[dict[str, Any]] = Field(default_factory=list)
```

3. `scene_loop.py` `SceneLoop.__init__`: add param `chat_log: list[Any] | None = None` after `ooc_exchanges`; assign `self.chat_log = chat_log`. In `run()`, `SceneState(...)` after `ooc_exchanges=...`:

```python
                recent_chat=_chat_tail(getattr(self, "chat_log", None)),
```

4. `scene_loop.py` `narrate` node, context dict after `"ooc_exchanges": ...`:

```python
            "recent_chat": state.recent_chat,
```

5. `narrator/agent.py`, module level after `_table_talk_block`:

```python
def _recent_chat_block(recent_chat: Any, *, max_tokens: int = 500) -> str:
    """Render the raw chat tail as a labeled block, hard-capped by tokens."""
    if not isinstance(recent_chat, list) or not recent_chat:
        return ""
    from monitor_agents.token_budget import count_tokens

    lines: list[str] = []
    used = 0
    for item in reversed(recent_chat):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        label = "[OOC]" if str(item.get("mode") or "ic").lower() == "ooc" else "[IC]"
        line = f"{label} {item.get('role') or '?'}: {content}"
        cost = count_tokens(line)
        if used + cost > max_tokens:
            break
        lines.append(line)
        used += cost
    if not lines:
        return ""
    lines.reverse()
    return (
        "\n\nRECENT TABLE CONVERSATION (provenance labels, not content — "
        "never address OOC remarks in fiction):\n" + "\n".join(lines) + "\n"
    )
```

(Verify `count_tokens` is importable from `monitor_agents.token_budget` — it is used the same way in `context_assembly/agent.py:32`.)

6. `narrator/agent.py`, after the TABLE TALK injection:

```python
        # Inject the raw recent chat tail (IC + OOC, labeled).
        profile_context += _recent_chat_block(context.get("recent_chat"))
```

7. `chat_loops.py` `get_scene_loop`: add param `chat_log: list[Any] | None = None`; in the cache-hit branch before `return cached[1]`:

```python
    if cached and cached[0] == signature:
        _SCENE_LOOPS.move_to_end(session_id)
        if chat_log is not None:
            cached[1].chat_log = chat_log  # refresh volatile reference
        return cached[1]
```

and in the `SceneLoop(...)` call after `ooc_exchanges=...`:

```python
        chat_log=chat_log,
```

8. `scene_orchestrator.py`, module level:

```python
def _chat_log_for(callbacks: Any, session_id: str) -> list[Any] | None:
    """Live chat message list for a session via UI-provided callbacks."""
    try:
        messages = getattr(callbacks, "messages", None)
        if isinstance(messages, dict):
            log = messages.get(session_id)
            if isinstance(log, list):
                return log
        loader = getattr(callbacks, "db_load_messages", None)
        if callable(loader):
            loaded = loader(session_id)
            return loaded if isinstance(loaded, list) else None
    except Exception:
        return None
    return None
```

and at the call site (line 260) add the kwarg:

```python
        loop = callbacks.get_scene_loop(
            state.session_id,
            session,
            scene_id=scene_id,
            story_id=story_id,
            actor_context=state.actor_context,
            chat_log=_chat_log_for(callbacks, state.session_id),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agents/tests/test_recent_chat_context.py packages/agents/tests/test_scene_loop.py packages/ui/backend/tests/test_scene_loop_chat_wiring.py packages/ui/backend/tests/test_begin_story_chat_command.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/scene_orchestrator.py packages/agents/src/monitor_agents/loops/scene_loop.py packages/agents/src/monitor_agents/narrator/agent.py packages/ui/backend/src/monitor_ui/routers/chat_loops.py packages/agents/tests/test_recent_chat_context.py packages/ui/backend/tests/test_scene_loop_chat_wiring.py
git commit -m "feat: inject labeled recent chat tail into narrator context"
```

---

### Task 4: Baseline session-0 questions (name / origin / appearance) + appearance in summary

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/preplay_support.py` — `BASELINE_SESSION_ZERO_QUESTIONS` constant + merge in `resolve_authored_session_zero_questions` (line 634)
- Modify: `packages/agents/src/monitor_agents/session_zero.py` — `SessionZeroSummary.appearance` field (near line 157), DSPy summary signature output field (near line 339), `prediction_to_summary` mapping
- Test: `packages/agents/tests/test_session_zero_baseline_questions.py` (new)

**Interfaces:**
- Consumes: `resolve_authored_questions(session, session_game_system_doc, *, category) -> list[dict]` (preplay_support.py:568).
- Produces:
  - `BASELINE_SESSION_ZERO_QUESTIONS: list[dict[str, Any]]` — question dicts shaped exactly like authored ones: `{"question_text", "category", "is_final", "answer_options"}`.
  - `resolve_authored_session_zero_questions(...)` now returns baseline-first, deduped by `category` (an authored question with the same category suppresses that baseline question).
  - `SessionZeroSummary.appearance: str | None = None` — flows into `session["character_summary"]` automatically via `handle_character_interview` (`summary.model_dump()`, preplay_orchestrator.py:387).

- [ ] **Step 1: Write the failing test**

```python
"""Baseline session-0 intake questions + appearance in the summary model."""

from __future__ import annotations

from typing import Any

import pytest

from monitor_agents.loops import preplay_support
from monitor_agents.loops.preplay_support import (
    BASELINE_SESSION_ZERO_QUESTIONS,
    resolve_authored_session_zero_questions,
)
from monitor_agents.session_zero import SessionZeroSummary


def test_baseline_questions_present_without_authored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preplay_support, "resolve_authored_questions", lambda *a, **k: [])
    questions = resolve_authored_session_zero_questions({}, None)
    categories = [q["category"] for q in questions]
    assert categories[:3] == ["name", "origin", "appearance"]
    for q in questions:
        assert q["question_text"].strip()
        assert set(q) == {"question_text", "category", "is_final", "answer_options"}


def test_authored_question_suppresses_matching_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    authored = [
        {"question_text": "How are you called?", "category": "name", "is_final": False, "answer_options": []},
        {"question_text": "What drives you?", "category": "motivation", "is_final": True, "answer_options": []},
    ]
    monkeypatch.setattr(preplay_support, "resolve_authored_questions", lambda *a, **k: authored)
    questions = resolve_authored_session_zero_questions({}, None)
    categories = [q["category"] for q in questions]
    assert categories.count("name") == 1  # authored wins, baseline name suppressed
    assert "origin" in categories and "appearance" in categories
    assert categories[-2:] == ["name", "motivation"]  # authored kept, after baseline


def test_baseline_constant_is_defensive_copy_safe() -> None:
    assert len(BASELINE_SESSION_ZERO_QUESTIONS) == 3


def test_summary_model_has_appearance() -> None:
    summary = SessionZeroSummary(concept="c", backstory="b", appearance="scarred, tall")
    assert summary.model_dump()["appearance"] == "scarred, tall"
    default = SessionZeroSummary(concept="c", backstory="b")
    assert default.appearance is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_session_zero_baseline_questions.py -v`
Expected: FAIL — `ImportError: cannot import name 'BASELINE_SESSION_ZERO_QUESTIONS'`

- [ ] **Step 3: Write minimal implementation**

1. `preplay_support.py`, near the top-level constants (before `resolve_authored_questions`):

```python
# Minimum Session-Zero intake, asked for EVERY game (deduped against authored
# pack questions by category). These feed the character summary and, at
# begin_story, the one-time canon seed.
BASELINE_SESSION_ZERO_QUESTIONS: list[dict[str, Any]] = [
    {
        "question_text": "What is your character's name?",
        "category": "name",
        "is_final": False,
        "answer_options": [],
    },
    {
        "question_text": "Where does your character come from? Give their origin or background in a sentence or two.",
        "category": "origin",
        "is_final": False,
        "answer_options": [],
    },
    {
        "question_text": "What does your character look like? Describe their general appearance.",
        "category": "appearance",
        "is_final": False,
        "answer_options": [],
    },
]
```

2. Replace the body of `resolve_authored_session_zero_questions` (line 634-643):

```python
def resolve_authored_session_zero_questions(
    session: dict[str, Any],
    session_game_system_doc: Any,
) -> list[dict[str, Any]]:
    """Character-interview questions: universal baseline + authored pack questions.

    Baseline questions (name/origin/appearance) come first; an authored
    question with the same category suppresses its baseline counterpart.
    """
    authored = resolve_authored_questions(
        session,
        session_game_system_doc,
        category="session_zero",
    )
    authored_categories = {
        str(q.get("category") or "").strip().lower() for q in authored
    }
    baseline = [
        dict(q)
        for q in BASELINE_SESSION_ZERO_QUESTIONS
        if q["category"] not in authored_categories
    ]
    return baseline + authored
```

3. `session_zero.py` `SessionZeroSummary` (after the `backstory` field, ~line 167):

```python
    appearance: str | None = Field(
        None,
        description="General physical appearance, if mentioned in the answers.",
    )
```

4. `session_zero.py` DSPy summary signature (after the `backstory` OutputField, ~line 345):

```python
        appearance: str = dspy.OutputField(
            desc="A one-sentence physical description distilled from the answers; empty string if none given.",
        )
```

5. `session_zero.py` `prediction_to_summary`: mirror how `character_name` is mapped — add `appearance` passthrough, e.g. `appearance=str(getattr(pred, "appearance", "") or "") or None`. Read the existing function and match its exact style. Also check `_fallback_summary`: if it builds a `SessionZeroSummary`, leave appearance unset (defaults to `None`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agents/tests/test_session_zero_baseline_questions.py packages/agents/tests/test_preplay_session_zero_to_cc_handoff.py packages/ui/backend/tests/test_session_zero_authored_resolver.py -q`
Expected: PASS (note: `test_session_zero_authored_resolver.py` asserts pure-authored behavior — the baseline merge changes its expectations; update those assertions to expect baseline-first ordering, since baseline-before-authored is the intended new contract).

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/preplay_support.py packages/agents/src/monitor_agents/session_zero.py packages/agents/tests/test_session_zero_baseline_questions.py packages/ui/backend/tests/test_session_zero_authored_resolver.py
git commit -m "feat: universal session-0 intake (name/origin/appearance) + appearance in summary"
```

---

### Task 5: Story review recap before Begin Story

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/preplay_orchestrator.py` — `_character_recap` helper + prepend in `handle_story_agreements` (line 527-554)
- Test: `packages/agents/tests/test_story_review_recap.py` (new)

**Interfaces:**
- Consumes: `session["character_summary"]` (fields `character_name`, `concept`, `appearance`, `backstory` — appearance requires Task 4), `session["speaker_label"]`.
- Produces: `_character_recap(session: dict[str, Any]) -> str` in `preplay_orchestrator.py` — `""` when nothing to recap. When the story-agreements loop completes, its `gm_message` (the agreements summary / story review) is prefixed with the character recap so the player confirms both before Begin Story.

- [ ] **Step 1: Write the failing test**

```python
"""Story review includes a character recap (session-0 closing review)."""

from __future__ import annotations

from typing import Any

import pytest

from monitor_agents.loops import preplay_orchestrator
from monitor_agents.loops.preplay_orchestrator import _character_recap


def test_character_recap_renders_known_fields() -> None:
    session: dict[str, Any] = {
        "character_summary": {
            "character_name": "Vex",
            "concept": "exiled cartographer",
            "appearance": "ink-stained hands, one clouded eye",
            "backstory": "Mapped the drowned coast. " * 40,
        }
    }
    recap = _character_recap(session)
    assert "CHARACTER REVIEW" in recap
    assert "Name: Vex" in recap
    assert "cartographer" in recap
    assert "clouded eye" in recap
    assert len(recap) < 800  # backstory excerpt bounded


def test_character_recap_empty_is_silent() -> None:
    assert _character_recap({}) == ""
    assert _character_recap({"character_summary": "junk"}) == ""


@pytest.mark.asyncio
async def test_completed_agreements_prefixed_with_recap(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeLoop:
        async def process_player_input(self, text: str) -> dict[str, Any]:
            return {
                "complete": True,
                "gm_message": "AGREEMENTS SUMMARY: premise, tone, lines.",
                "agreements": None,
            }

    monkeypatch.setattr(preplay_orchestrator, "get_story_agreements_loop", lambda *a, **k: _FakeLoop())
    monkeypatch.setattr(preplay_orchestrator, "_save_checkpoint", lambda *a, **k: None)
    state = preplay_orchestrator.PreplayState(
        session_id="s1",
        user_content="looks good",
        session_data={
            "phase": "session_zero",
            "character_summary": {"character_name": "Vex", "concept": "exiled cartographer"},
        },
        system_doc=None,
        gsr_available=False,
    )
    result = await preplay_orchestrator.handle_story_agreements(state)
    assert result["response_text"].startswith("CHARACTER REVIEW")
    assert "AGREEMENTS SUMMARY" in result["response_text"]
    assert result["metadata"]["type"] == "story_agreements_summary"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_story_review_recap.py -v`
Expected: FAIL — `ImportError: cannot import name '_character_recap'`

- [ ] **Step 3: Write minimal implementation**

In `preplay_orchestrator.py`, module level (before `handle_story_agreements`):

```python
def _character_recap(session: dict[str, Any]) -> str:
    """Small review of the established character, prepended to the closing
    Session-Zero summary so the player confirms it before Begin Story."""
    summary = session.get("character_summary")
    if not isinstance(summary, dict):
        return ""
    lines = ["CHARACTER REVIEW — what we established:"]
    name = str(summary.get("character_name") or session.get("speaker_label") or "").strip()
    concept = str(summary.get("concept") or "").strip()
    appearance = str(summary.get("appearance") or "").strip()
    backstory = str(summary.get("backstory") or "").strip()
    if name:
        lines.append(f"- Name: {name}")
    if concept:
        lines.append(f"- Origin & concept: {concept}")
    if appearance:
        lines.append(f"- Appearance: {appearance}")
    if backstory:
        lines.append(f"- Story so far: {backstory[:400]}")
    return "\n".join(lines) if len(lines) > 1 else ""
```

In `handle_story_agreements`, compute the recap once and use it in the return dict — insert directly above the final `return {`:

```python
    recap = _character_recap(session) if result.get("complete") else ""
    gm_message = result.get("gm_message", "Tell me more.")
    if recap:
        gm_message = recap + "\n\n---\n\n" + gm_message
```

and change the return's `"response_text": result.get("gm_message", "Tell me more."),` to `"response_text": gm_message,`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agents/tests/test_story_review_recap.py packages/agents/tests/test_preplay_session_zero_to_cc_handoff.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/preplay_orchestrator.py packages/agents/tests/test_story_review_recap.py
git commit -m "feat: character recap in session-0 closing review"
```

---

### Task 6: Canon seeding at `begin_story`

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/preplay_finalize.py` — `seed_canon_from_session_zero` + call in `finalize_preplay` (after line 51, before `_load_gm_profile`)
- Test: `packages/agents/tests/test_canon_seeding.py` (new)

**Interfaces:**
- Consumes: `session["character_summary"]`, `session["story_premise"]`, `session["tone"]`, `session["universe_id"|"world_id"]`, `session["character_id"]`, `session["story_id"]`, `session["scene_id"]`, `session["director_notes"]`; `MemoryCreate` (data-layer schemas/memories.py:23); `mongodb_create_memory` (sync tool, embeds into Qdrant via its hook — same pattern as `PersistenceService.persist_memories`, persistence_service.py:103-113).
- Produces: `async def seed_canon_from_session_zero(session: dict[str, Any]) -> None` — one-time (`session["canon_seeded"]`), never raises.

- [ ] **Step 1: Write the failing test**

```python
"""One-time canon seeding from Session-Zero outcomes at begin_story."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

import monitor_data.tools.mongodb_tools as mongo_tools
from monitor_agents.loops import preplay_finalize
from monitor_agents.loops.preplay_finalize import seed_canon_from_session_zero


def _session() -> dict[str, Any]:
    return {
        "universe_id": str(uuid4()),
        "character_id": str(uuid4()),
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "story_premise": "a heist on the tide-locks",
        "tone": "grim",
        "director_notes": [],
        "character_summary": {
            "character_name": "Vex",
            "concept": "exiled cartographer",
            "appearance": "ink-stained hands",
            "backstory": "Mapped the drowned coast.",
        },
    }


@pytest.mark.asyncio
async def test_seed_writes_memory_and_director_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Any] = []

    class _Res:
        memory_id = uuid4()

    def _fake_create(params: Any) -> Any:
        created.append(params)
        return _Res()

    monkeypatch.setattr(mongo_tools, "mongodb_create_memory", _fake_create)
    session = _session()
    await seed_canon_from_session_zero(session)

    assert session["canon_seeded"] is True
    assert len(created) == 1
    params = created[0]
    assert "Vex" in params.text and "ink-stained hands" in params.text
    assert params.metadata["story_id"] == session["story_id"]
    assert params.importance == 0.9
    assert "Story premise: a heist on the tide-locks" in session["director_notes"]
    assert "Tone: grim" in session["director_notes"]


@pytest.mark.asyncio
async def test_seed_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mongo_tools,
        "mongodb_create_memory",
        lambda params: pytest.fail("must not write twice"),
    )
    session = _session()
    session["canon_seeded"] = True
    await seed_canon_from_session_zero(session)  # no exception, no writes


@pytest.mark.asyncio
async def test_seed_failure_does_not_raise_and_still_marks_seeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(params: Any) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(mongo_tools, "mongodb_create_memory", _boom)
    session = _session()
    await seed_canon_from_session_zero(session)  # must not raise
    assert session["canon_seeded"] is True
    # Director notes are independent of the memory write.
    assert "Tone: grim" in session["director_notes"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_canon_seeding.py -v`
Expected: FAIL — `ImportError: cannot import name 'seed_canon_from_session_zero'`

- [ ] **Step 3: Write minimal implementation**

In `preplay_finalize.py`, after the imports:

```python
DIRECTOR_NOTES_CAP = 20


async def seed_canon_from_session_zero(session: dict[str, Any]) -> None:
    """One-time: turn Session-Zero outcomes into retrievable canon.

    Writes a high-importance character memory (MongoDB + Qdrant via the
    create hook) so ContextAssembly retrieves who the PC is on every turn,
    and records premise/tone as director notes (ESTABLISHED FACTS). Runs at
    most once per session; failures degrade to a log line — the story still
    begins.
    """
    if session.get("canon_seeded"):
        return
    session["canon_seeded"] = True  # mark first: idempotent even on failure

    summary = session.get("character_summary")
    parts: list[str] = []
    if isinstance(summary, dict):
        name = str(summary.get("character_name") or session.get("speaker_label") or "").strip()
        concept = str(summary.get("concept") or "").strip()
        appearance = str(summary.get("appearance") or "").strip()
        backstory = str(summary.get("backstory") or "").strip()
        if name:
            parts.append(f"Name: {name}")
        if concept:
            parts.append(f"Origin & concept: {concept}")
        if appearance:
            parts.append(f"Appearance: {appearance}")
        if backstory:
            parts.append(f"Backstory: {backstory}")

    universe_id = session.get("universe_id") or session.get("world_id")
    entity_id = session.get("character_id")
    story_id = session.get("story_id")
    scene_id = session.get("scene_id")
    if parts and universe_id and entity_id and story_id:
        try:
            import anyio

            from monitor_data.schemas.memories import MemoryCreate
            from monitor_data.tools.mongodb_tools import mongodb_create_memory

            text = "PLAYER CHARACTER (established in Session Zero):\n" + "\n".join(parts)
            params = MemoryCreate(
                universe_id=UUID(str(universe_id)),
                entity_id=UUID(str(entity_id)),
                scene_id=UUID(str(scene_id)) if scene_id else None,
                text=text[:5000],
                importance=0.9,
                emotional_valence=0.0,
                metadata={"story_id": str(story_id), "source": "session_zero_canon_seed"},
            )
            await anyio.to_thread.run_sync(mongodb_create_memory, params)
        except Exception as exc:
            log.warning("preplay.canon_seed_memory_failed", error=str(exc))

    notes = session.setdefault("director_notes", [])
    if isinstance(notes, list):
        premise = str(session.get("story_premise") or "").strip()
        tone = str(session.get("tone") or "").strip()
        candidates = ([f"Story premise: {premise}"] if premise else []) + (
            [f"Tone: {tone}"] if tone else []
        )
        for note in candidates:
            if note not in notes:
                notes.append(note)
        del notes[:-DIRECTOR_NOTES_CAP]
```

In `finalize_preplay`, after `session["scene_id"] = scene_id` and the `RuntimeError` guard (line 51), before `gm_profile = await _load_gm_profile(...)`:

```python
    await seed_canon_from_session_zero(session)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agents/tests/test_canon_seeding.py packages/agents/tests/test_begin_story_command.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/preplay_finalize.py packages/agents/tests/test_canon_seeding.py
git commit -m "feat: seed character memory + director notes at begin_story"
```

---

### Task 7: Full verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Full agents + backend suites**

Run: `uv run pytest packages/agents -q && uv run pytest packages/ui/backend -q && uv run pytest packages/cli -q`
Expected: PASS. Any pre-existing failures must be confirmed pre-existing (`git stash` + rerun on demand) and reported, not silently tolerated.

- [ ] **Step 2: Lint, types, layer boundaries**

Run: `uv run ruff check packages && uv run mypy packages/*/src --cache-dir /tmp/mypy-cache && python scripts/check_layer_dependencies.py`
Expected: clean (only pre-existing format drift in untouched regions may remain — do not reformat it).

- [ ] **Step 3: Live smoke (manual, with the user)**

Restart the backend (`./dev.sh`), create a fresh session, and verify: session 0 asks name → origin → appearance; the closing review shows the character recap; after Begin Story, an OOC `((question))` is answered in meta voice; the next IC turn's narration stays consistent with the OOC answer. Existing sessions (`fb47f1e6…`, `b3bebf4f…`) keep their poisoned history — do not migrate them.

- [ ] **Step 4: Final commit (if any fixes fell out of the sweep)**

```bash
git add -A
git commit -m "chore: verification sweep fixes for gm context carry-over"
```

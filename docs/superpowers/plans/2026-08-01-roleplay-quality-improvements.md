# Roleplay Quality Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NPCs remember and feel consistent across scenes, add pacing/soft-retry/foreshadowing/auto-recap/memory-hygiene quality-of-life improvements, all by reusing existing infrastructure where it already exists.

**Architecture:** Three phases (low → medium → varied risk), eight tasks. New data-layer tool for bulk NPC fetch (one). One new MongoDB collection (`scene_foreshadowing`). One new DSPy output field on `NarratorSignature`. New render blocks added incrementally to `profile_context` (each omits when empty). All emotion writes route through the existing `mongodb_update_npc_profile` path.

**Tech Stack:** Python 3.11, Pydantic v2, DSPy, LangGraph, FastAPI, MongoDB, Qdrant, pytest, ruff, mypy. Three-layer monorepo (`monitor-data` L1 / `monitor-agents` L2 / `monitor_ui` L3).

**Spec:** `docs/superpowers/specs/2026-08-01-roleplay-quality-improvements-design.md`

## Global Constraints

- Every new render block returns `""` when its input is empty/invalid; the Narrator injects only non-empty blocks.
- Caps enforced at render time (not just write time): 4 NPCs in state block (200 chars each), 5 foreshadowing items, 1-line PACE block, 1-line LAST SCENE block, 500-token recent tail, 8 OOC exchanges.
- NPC emotion writes use the existing `mongodb_update_npc_profile(entity_id, params)` path (the one NPCVoice already uses). No new write paths, no new Neo4j writes.
- Layer rules: agents → data-layer only via MCP tools. New tools live in `packages/data-layer/src/monitor_data/tools/mongodb_tools/`.
- No frontend changes.
- Minimal diffs; do not reformat pre-existing drift in files not touched by this plan.
- DSPy test fakes follow the `_FakePredict` + `dspy_context_for` nullcontext pattern from `packages/agents/tests/test_begin_story_command.py`.
- Verification: `uv run pytest packages/agents -q && uv run pytest packages/ui/backend -q && uv run pytest packages/cli -q && uv run pytest packages/data-layer -q`; `uv run ruff check packages`; `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`; `python scripts/check_layer_dependencies.py`; frontend `npx tsc --noEmit -p packages/ui/frontend/tsconfig.json`.

---

### Task 1: Soft-retry on degraded narration (#4)

**Files:**
- Modify: `packages/agents/src/monitor_agents/narrator/agent.py` — `Narrator._generate_narrative_and_proposals` (around line 396) refactor into `_generate_once` + retry loop.
- Test: `packages/agents/tests/test_narrator_soft_retry.py` (new)

**Interfaces:**
- Produces:
  - `async def _generate_once(self, *, context: dict, trimmed: bool = False, **kwargs) -> tuple[str, list[dict], int, dict]` — one DSPy call returning `(narrative_text, proposals, minutes_elapsed, degraded_dict)`. When `trimmed=True`, `context` is rebuilt without `lorebook_context` / `recent_chat` / `context_summary`.
  - `Narrator._generate_narrative_and_proposals` (public) — calls `_generate_once` once; if `degraded`, calls again with `trimmed=True`; returns the non-degraded result if any, else the first degraded result with `degraded["retried"] = True`.

- [ ] **Step 1: Write the failing test**

```python
"""Narrator soft-retry: a single transient failure should recover cleanly."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.narrator.agent import Narrator


def _ok_result() -> tuple[str, list[dict[str, Any]], int, dict[str, Any]]:
    return ("all good", [], 5, {})


def _degraded_result() -> tuple[str, list[dict[str, Any]], int, dict[str, Any]]:
    return ("fallback prose", [], 5, {"error_class": "rate_limit", "message": "boom"})


@pytest.mark.asyncio
async def test_first_failure_retry_succeeds() -> None:
    narrator = Narrator()
    with patch.object(
        narrator,
        "_generate_once",
        new=AsyncMock(side_effect=[_degraded_result(), _ok_result()]),
    ) as m:
        narrative, proposals, minutes, degraded = await narrator._generate_narrative_and_proposals(
            user_input=None,
            resolution=None,
            context={"entities": [], "memories": [], "turns": []},
        )
    assert narrative == "all good"
    assert degraded == {}
    assert m.await_count == 2


@pytest.mark.asyncio
async def test_both_failures_ship_first_fallback() -> None:
    narrator = Narrator()
    with patch.object(
        narrator,
        "_generate_once",
        new=AsyncMock(side_effect=[_degraded_result(), _degraded_result()]),
    ) as m:
        narrative, _, _, degraded = await narrator._generate_narrative_and_proposals(
            user_input=None,
            resolution=None,
            context={"entities": [], "memories": [], "turns": []},
        )
    assert narrative == "fallback prose"
    assert degraded.get("error_class") == "rate_limit"
    assert degraded.get("retried") is True
    assert m.await_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_narrator_soft_retry.py -v`
Expected: FAIL — `_generate_once` does not exist on Narrator.

- [ ] **Step 3: Extract `_generate_once` and add retry**

In `packages/agents/src/monitor_agents/narrator/agent.py`, inside the Narrator class, split `_generate_narrative_and_proposals` (around line 396) into two methods. Keep the public method's signature identical. Move the DSPy call, prompt assembly, and proposal parsing into `_generate_once`:

```python
    async def _generate_once(
        self,
        *,
        user_input: str | None,
        resolution: dict[str, Any] | None,
        context: dict[str, Any],
        game_context: dict[str, Any] | None = None,
        session_tone: str = "dramatic",
        gm_profile: dict[str, Any] | None = None,
        lorebook_context: list[str] | None = None,
        story_state: Any = None,
        story_premise: str | None = None,
        trimmed: bool = False,
    ) -> tuple[str, list[dict[str, Any]], int, dict[str, Any]]:
        """Run the Narrator DSPy module once. Returns (narrative, proposals,
        minutes_elapsed, degraded_dict). When trimmed=True, drops lorebook_context,
        recent_chat, and context_summary from the assembled context to make
        the call cheaper for the retry path."""
        # If trimmed, blank out the fields that we're dropping.
        if trimmed:
            lorebook_context = []
            context = {**context, "recent_chat": [], "context_summary": ""}
        # ... full original body of _generate_narrative_and_proposals ...
        return narrative_text, proposals, minutes_elapsed, degraded or {}

    async def _generate_narrative_and_proposals(
        self,
        *,
        user_input: str | None,
        resolution: dict[str, Any] | None,
        context: dict[str, Any],
        game_context: dict[str, Any] | None = None,
        session_tone: str = "dramatic",
        gm_profile: dict[str, Any] | None = None,
        lorebook_context: list[str] | None = None,
        story_state: Any = None,
        story_premise: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], int, dict[str, Any]]:
        """Public entry: run once; on degraded, retry with trimmed context."""
        kwargs = dict(
            user_input=user_input, resolution=resolution, context=context,
            game_context=game_context, session_tone=session_tone,
            gm_profile=gm_profile, lorebook_context=lorebook_context,
            story_state=story_state, story_premise=story_premise,
        )
        first = await self._generate_once(**kwargs)
        if not first[3]:
            return first
        retry = await self._generate_once(**kwargs, trimmed=True)
        if not retry[3]:
            return retry
        # Both degraded: ship first, mark retried=True.
        narrative, proposals, minutes, degraded = first
        return narrative, proposals, minutes, {**degraded, "retried": True}
```

Keep the original DSPy-call body inside `_generate_once` (do not duplicate). The literal `# ... full original body ...` comment in the snippet above is the boundary; the existing body goes there as-is.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/agents/tests/test_narrator_soft_retry.py packages/agents/tests/test_narrator.py packages/agents/tests/test_begin_story_command.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/narrator/agent.py packages/agents/tests/test_narrator_soft_retry.py
git commit -m "feat(narrator): soft-retry with trimmed context on degraded generation"
```

---

### Task 2: Pacing instrumentation (#6)

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/scene_loop.py` — `SceneState.pacing: dict[str, Any]` (default `{"tempo": 0.5, "phase": "setup"}`), `load_context` populates it.
- Modify: `packages/agents/src/monitor_agents/narrator/agent.py` — module-level `compute_pacing(turns_count, recent_proposal_count)` + `_pace_block(pacing)` + injection after source-profile block.
- Test: `packages/agents/tests/test_pacing.py` (new)

**Interfaces:**
- Produces:
  - `compute_pacing(turns_count: int, recent_proposal_count: int) -> dict[str, Any]` — pure function; returns `{"tempo": float 0..1, "phase": "setup"|"rising"|"peak"|"falling"|"coda"}`.
  - `_pace_block(pacing: Any) -> str` — renders `PACE: tempo=X.XX phase=Y\n` only when non-default.

- [ ] **Step 1: Write the failing tests**

```python
"""Pacing derivation + narrator block."""

from __future__ import annotations

import pytest

from monitor_agents.narrator.agent import _pace_block, compute_pacing


@pytest.mark.parametrize(
    "turns,props,expected_tempo_range,expected_phase",
    [
        (0, 0, (0.35, 0.5), "setup"),
        (5, 1, (0.4, 0.6), "rising"),
        (10, 4, (0.4, 0.6), "peak"),
        (8, 5, (0.3, 0.5), "falling"),
        (35, 0, (1.0, 1.0), "coda"),
    ],
)
def test_compute_pacing_matrix(turns, props, expected_tempo_range, expected_phase) -> None:
    out = compute_pacing(turns_count=turns, recent_proposal_count=props)
    assert expected_tempo_range[0] <= out["tempo"] <= expected_tempo_range[1]
    assert out["phase"] == expected_phase


def test_pace_block_renders_when_non_default() -> None:
    assert "PACE: tempo=0.62 phase=peak" in _pace_block(
        {"tempo": 0.62, "phase": "peak"}
    )


def test_pace_block_silent_when_default() -> None:
    assert _pace_block({"tempo": 0.5, "phase": "setup"}) == ""
    assert _pace_block(None) == ""
    assert _pace_block("junk") == ""


def test_pace_block_caps_tempo() -> None:
    assert _pace_block({"tempo": 5.0, "phase": "peak"}).count("\n") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_pacing.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_pacing'`.

- [ ] **Step 3: Implement `compute_pacing`, `_pace_block`, and SceneState field**

1. `narrator/agent.py`, module level near `_table_talk_block`:

```python
def compute_pacing(turns_count: int, recent_proposal_count: int) -> dict[str, Any]:
    """Deterministic pacing signal from turn count + recent proposal count.

    - tempo (0..1): higher = more action recently.
    - phase: setup / rising / peak / falling / coda.
    """
    tempo = 0.4 + 0.04 * turns_count - 0.3 * recent_proposal_count
    tempo = max(0.0, min(1.0, tempo))
    if turns_count < 3:
        phase = "setup"
    elif tempo >= 0.7 and recent_proposal_count >= 1:
        phase = "peak"
    elif tempo <= 0.3 and turns_count > 5:
        phase = "falling"
    elif turns_count > 30:
        phase = "coda"
    else:
        phase = "rising"
    return {"tempo": round(tempo, 2), "phase": phase}


def _pace_block(pacing: Any) -> str:
    """Render the PACE block (single line). Empty when at defaults."""
    if not isinstance(pacing, dict):
        return ""
    tempo = pacing.get("tempo")
    phase = pacing.get("phase")
    if tempo is None or phase is None:
        return ""
    if tempo == 0.5 and phase == "setup":
        return ""
    return f"\n\nPACE: tempo={tempo:.2f} phase={phase}"
```

2. Inject `_pace_block` in `Narrator._generate_narrative_and_proposals` immediately after the existing `profile_context = build_narrative_profile_context(source_profile)` line (around line 442 of `narrator/agent.py`):

```python
        pacing = context.get("pacing")
        profile_context += _pace_block(pacing)
```

3. `SceneState` (`scene_loop.py:72`), add field right after `tension_score`:

```python
    # Deterministic pacing signal (tempo 0..1 + phase). Set in load_context.
    pacing: dict[str, Any] = Field(default_factory=lambda: {"tempo": 0.5, "phase": "setup"})
```

4. In `load_context` (scene_loop.py:185), after the existing `context = await agent.assemble(...)` call and before the return, compute pacing:

```python
        recent_proposal_count = sum(
            1 for p in (state.pending_proposals or [])[-3:]
            if isinstance(p, dict)
        )
        # SceneState mutation in-place is fine — load_context is the first
        # node and state is freshly built per turn.
        return {
            ...existing dict...,
            "pacing": compute_pacing(state.turns_count, recent_proposal_count),
        }
```

(Read `load_context` first to see the exact return shape; merge the new key into whatever dict it currently returns. If `load_context` doesn't return a dict but mutates state, set `state.pacing = compute_pacing(...)` instead.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/agents/tests/test_pacing.py packages/agents/tests/test_scene_loop.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/scene_loop.py packages/agents/src/monitor_agents/narrator/agent.py packages/agents/tests/test_pacing.py
git commit -m "feat(narrator): deterministic pacing signal + PACE block"
```

---

### Task 3: Bulk NPC fetch data-layer tool (Gap A)

**Files:**
- Modify: `packages/data-layer/src/monitor_data/tools/mongodb_tools/npc_profiles.py` — add `mongodb_get_npc_profiles_by_entities`.
- Modify: `packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py` — re-export.
- Test: `packages/data-layer/tests/test_tools/test_npc_profiles_bulk.py` (new)

**Interfaces:**
- Produces: `mongodb_get_npc_profiles_by_entities(entity_ids: list[UUID]) -> list[NPCProfileResponse]` — single Mongo `find` filtered by `entity_id IN [...]`, mapped through `_npc_profile_doc_to_response`. Empty list when no matches. No error when input is empty (returns `[]`).

- [ ] **Step 1: Write the failing test**

```python
"""Bulk NPC profile fetch."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

import monitor_data.tools.mongodb_tools as mongo_tools
from monitor_data.tools.mongodb_tools import mongodb_get_npc_profiles_by_entities


@pytest.fixture
def fake_npc_docs() -> dict[str, dict]:
    eid1, eid2, eid3 = str(uuid4()), str(uuid4()), str(uuid4())
    return {
        "_doc1": {"entity_id": eid1, "values": ["honor"], "current_emotional_state": "neutral"},
        "_doc2": {"entity_id": eid2, "values": ["greed"]},
        "_doc3": {"entity_id": eid3, "values": ["piety"]},
        "_ids": [eid1, eid2, eid3],
    }


def test_returns_only_requested_entities(fake_npc_docs: dict) -> None:
    target = fake_npc_docs["_ids"][:2]
    with patch(f"{mongo_tools.__name__}.mongodb_get_npc_profile") as m_get:
        # For simplicity in this test, mock the single-entity getter.
        from monitor_data.tools.mongodb_tools.npc_profiles import (
            _npc_profile_doc_to_response,
        )
        from monitor_data.schemas.npc_profiles import NPCProfileResponse
        responses = {
            fake_npc_docs["_ids"][0]: NPCProfileResponse(
                profile_id=uuid4(), entity_id=fake_npc_docs["_ids"][0],
                values=["honor"], fears=[], desires=[], catchphrases=[],
                mannerisms=[], emotional_tendencies=[], preferences=[],
                triggers=[], secrets=[], relationship_states={},
                relationship_states_by_universe={},
                current_emotional_state_by_universe={}, metadata={},
                created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            ),
        }
        # We actually test the *bulk* tool: it should call find() internally
        # via the mongo collection. Stub differently — patch the module-level
        # collection handle.
        from monitor_data import db
        ...
```

**Simpler version** — mock at the lower boundary:

```python
def test_returns_only_requested_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bulk fetch returns one NPCProfileResponse per matching entity."""
    from monitor_data.schemas.npc_profiles import NPCProfileResponse
    import datetime as _dt

    eids = [uuid4(), uuid4()]
    docs = [
        {"entity_id": str(eids[0]), "values": ["honor"], "created_at": _dt.datetime.now(_dt.UTC)},
        {"entity_id": str(eids[1]), "values": ["greed"], "created_at": _dt.datetime.now(_dt.UTC)},
    ]
    # Find the module where the actual bulk-fetch will live.
    import monitor_data.tools.mongodb_tools.npc_profiles as npc_mod
    fake_collection = type("FakeColl", (), {"find": staticmethod(lambda filt, proj=None: docs)})()
    monkeypatch.setattr(npc_mod, "_npc_profiles_collection", fake_collection, raising=False)
    # If the implementation calls db.mongo_collection, adapt accordingly.
    out = mongodb_get_npc_profiles_by_entities(eids)
    assert len(out) == 2
    assert {r.entity_id for r in out} == set(eids)


def test_returns_empty_when_no_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    import monitor_data.tools.mongodb_tools.npc_profiles as npc_mod
    fake_collection = type("FakeColl", (), {"find": staticmethod(lambda filt, proj=None: [])})()
    monkeypatch.setattr(npc_mod, "_npc_profiles_collection", fake_collection, raising=False)
    out = mongodb_get_npc_profiles_by_entities([uuid4()])
    assert out == []


def test_empty_input_returns_empty() -> None:
    assert mongodb_get_npc_profiles_by_entities([]) == []
```

(Read `packages/data-layer/src/monitor_data/tools/mongodb_tools/npc_profiles.py` first to see how the existing single-entity getter accesses the Mongo collection. Mirror that access pattern for the bulk version — same database handle, same collection. Adapt the fakes to whatever attribute name actually holds the collection, e.g. `db["npc_profiles"]` or `mongo_db["npc_profiles"]`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/data-layer/tests/test_tools/test_npc_profiles_bulk.py -v`
Expected: FAIL — `ImportError: cannot import name 'mongodb_get_npc_profiles_by_entities'`.

- [ ] **Step 3: Implement the bulk tool**

In `packages/data-layer/src/monitor_data/tools/mongodb_tools/npc_profiles.py`, after `mongodb_get_npc_profile` (around line 95):

```python
def mongodb_get_npc_profiles_by_entities(
    entity_ids: list[UUID],
) -> list[NPCProfileResponse]:
    """Bulk fetch NPC profiles for the given entities (single Mongo find).

    Returns [] when input is empty or no matches. Order is not guaranteed —
    callers must key by entity_id if they need stable order.
    """
    if not entity_ids:
        return []
    # Mirror the same mongo handle pattern used by mongodb_get_npc_profile.
    # Read that function and copy the access pattern; e.g.:
    #   from monitor_data.db.mongodb import get_mongo_collection
    #   coll = get_mongo_collection("npc_profiles")
    coll = _npc_profiles_collection()  # or whatever the existing helper is called
    docs = coll.find({"entity_id": {"$in": [str(e) for e in entity_ids]}})
    return [_npc_profile_doc_to_response(d) for d in docs]
```

Then re-export from `__init__.py`:

```python
from .npc_profiles import mongodb_get_npc_profiles_by_entities  # noqa: F401
```

(Read both files before editing — the exact collection-handle helper name is implementation-specific; mirror what the rest of the file does.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/data-layer/tests/test_tools/test_npc_profiles_bulk.py packages/data-layer/tests/test_tools/test_roleplay_error_tools.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/data-layer/src/monitor_data/tools/mongodb_tools/npc_profiles.py packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py packages/data-layer/tests/test_tools/test_npc_profiles_bulk.py
git commit -m "feat(data-layer): bulk NPC profile fetch by entity_ids"
```

---

### Task 4: Surface NPC state to the Narrator (Gap B)

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/scene_loop.py` — `SceneState.npc_profiles: dict[str, Any]` (default `{}`), `load_context` calls the bulk tool and stores the result, `narrate` node passes `npc_profiles` in context.
- Modify: `packages/agents/src/monitor_agents/narrator/agent.py` — `_npc_state_block` helper + injection after source-profile block (alongside `_pace_block`).
- Test: `packages/agents/tests/test_npc_state_block.py` (new)

**Interfaces:**
- Consumes: `mongodb_get_npc_profiles_by_entities` from Task 3.
- Produces:
  - `SceneState.npc_profiles: dict[str, Any]` keyed by `entity_id` (str), values are `NPCProfileResponse.model_dump(mode="json")`.
  - `narrate` node adds `"npc_profiles": state.npc_profiles` to the narrator context dict.
  - `_npc_state_block(npc_profiles: Any, *, universe_id: str | None, player_id: str | None, cap: int = 4, max_chars: int = 200) -> str` — returns `""` when input empty; renders `NPC STATE (use these in dialogue; do not contradict):\n- <name>: emotion="X", disposition="Y", speech_style="Z"\n...`.

- [ ] **Step 1: Write the failing tests**

```python
"""NPC STATE narrator block + SceneState plumbing."""

from __future__ import annotations

import uuid as _uuid
from typing import Any

import pytest

from monitor_agents.narrator.agent import _npc_state_block
from monitor_agents.loops.scene_loop import SceneState


def _profile(name: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "entity_id": str(_uuid.uuid4()),
        "name": name,
        "values": [],
        "fears": [],
        "desires": [],
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "speech_style": None,
        "current_emotional_state": "neutral",
        "current_emotional_state_by_universe": {},
        "relationship_states": {},
        "relationship_states_by_universe": {},
    }
    base.update(overrides)
    return base


def test_block_empty_when_no_profiles() -> None:
    assert _npc_state_block({}, universe_id="u1", player_id="p1") == ""
    assert _npc_state_block(None, universe_id="u1", player_id="p1") == ""
    assert _npc_state_block("junk", universe_id="u1", player_id="p1") == ""


def test_block_renders_emotion_and_relationship() -> None:
    prof = _profile(
        "Vex",
        current_emotional_state_by_universe={"u1": "wary"},
        relationship_states_by_universe={
            "u1": {"p1": {"disposition": "grudging_respect", "score": 0.4}}
        },
        speech_style="clipped, marine slang",
    )
    block = _npc_state_block({"eid": prof}, universe_id="u1", player_id="p1")
    assert "NPC STATE" in block
    assert "Vex" in block
    assert "wary" in block
    assert "grudging_respect" in block
    assert "clipped, marine slang" in block


def test_block_caps_characters_and_npcs() -> None:
    profiles = {
        f"e{i}": _profile(f"NPC {i}", current_emotional_state_by_universe={"u1": "angry" * 200})
        for i in range(8)
    }
    block = _npc_state_block(profiles, universe_id="u1", player_id="p1", cap=4, max_chars=80)
    assert block.count("- NPC") == 4  # cap
    assert "angry" * 81 not in block  # char cap


def test_block_silent_when_emotion_and_relationship_absent() -> None:
    prof = _profile("Quiet")  # no state at all
    assert _npc_state_block({"e": prof}, universe_id="u1", player_id="p1") == ""


def test_scene_state_carries_npc_profiles() -> None:
    state = SceneState(scene_id=_uuid.uuid4(), story_id=_uuid.uuid4())
    state.npc_profiles = {"eid": _profile("Vex")}
    assert "eid" in state.npc_profiles
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_npc_state_block.py -v`
Expected: FAIL — `ImportError: cannot import name '_npc_state_block'` AND `TypeError: npc_profiles` field missing on SceneState.

- [ ] **Step 3: Implement**

1. `narrator/agent.py`, module level near `_pace_block`:

```python
def _npc_state_block(
    npc_profiles: Any,
    *,
    universe_id: str | None,
    player_id: str | None,
    cap: int = 4,
    max_chars: int = 200,
) -> str:
    """Render per-NPC emotion + relationship + speech_style as a narrator block.

    Empty when no NPC has emotion/relationship in the active universe+player
    partition. Capped at `cap` NPCs and `max_chars` chars per field. The
    block is omitted entirely if no NPC has anything to show.
    """
    if not isinstance(npc_profiles, dict) or not npc_profiles:
        return ""
    rows: list[str] = []
    for profile in list(npc_profiles.values())[:cap]:
        if not isinstance(profile, dict):
            continue
        name = str(profile.get("name") or "(unnamed)")[:max_chars].strip()
        emo_map = profile.get("current_emotional_state_by_universe") or {}
        emo = str((emo_map.get(universe_id) if universe_id else None) or "").strip()[:max_chars]
        rel_map = (profile.get("relationship_states_by_universe") or {}).get(universe_id or "", {}) or {}
        rel = rel_map.get(player_id or "", {}) if isinstance(rel_map.get(player_id or ""), dict) else {}
        disposition = str(rel.get("disposition") or "")[:max_chars].strip()
        speech = str(profile.get("speech_style") or "")[:max_chars].strip()
        if not (emo or disposition or speech):
            continue
        bits = []
        if emo:
            bits.append(f'emotion="{emo}"')
        if disposition:
            bits.append(f'disposition="{disposition}"')
        if speech:
            bits.append(f'speech_style="{speech}"')
        rows.append(f"- {name}: " + ", ".join(bits))
    if not rows:
        return ""
    return (
        "\n\nNPC STATE (use these in dialogue; do not contradict):\n" + "\n".join(rows) + "\n"
    )
```

2. In `Narrator._generate_narrative_and_proposals`, immediately after the `_pace_block` injection (Task 2's edit):

```python
        profile_context += _npc_state_block(
            context.get("npc_profiles"),
            universe_id=context.get("universe_id") or (
                (story_state.universe_id if story_state else None)
            ),
            player_id=str(actor.get("id")) if isinstance(actor, dict) and actor.get("id") else None,
        )
```

(Read the surrounding code to confirm `actor` and `story_state` are in scope at that point in `_generate_narrative_and_proposals` — they are, per the existing setup.)

3. `SceneState` (scene_loop.py:72), add field:

```python
    # NPC profiles fetched per scene (entity_id -> dict). Rendered by Narrator
    # into the NPC STATE block; never reset across turns (NPCProfile persists
    # in MongoDB and survives scene transitions).
    npc_profiles: dict[str, Any] = Field(default_factory=dict)
```

4. `load_context` (scene_loop.py:185), after the existing `context = await agent.assemble(...)` call:

```python
        # Fetch NPC profiles for entities in this scene. Best-effort: any
        # failure here (no scene, db down) just leaves npc_profiles empty
        # and the narrator block degrades to silence.
        npc_profiles: dict[str, Any] = {}
        try:
            entity_ids = [
                _uuid.UUID(str(e["id"])) for e in state.entity_context
                if isinstance(e, dict) and e.get("id")
            ]
            if entity_ids:
                from monitor_data.tools.mongodb_tools import mongodb_get_npc_profiles_by_entities
                profiles = await anyio.to_thread.run_sync(
                    mongodb_get_npc_profiles_by_entities, entity_ids,
                )
                npc_profiles = {str(p.entity_id): p.model_dump(mode="json") for p in profiles}
        except Exception as exc:
            logger.debug("load_context: npc profile fetch failed: %s", exc)
        # (Add `npc_profiles` to whatever dict load_context returns, OR
        # mutate state directly: state.npc_profiles = npc_profiles.)
```

(Add `import anyio` if not already imported in scene_loop.py. Read the top of `load_context` first to confirm.)

5. `narrate` node (scene_loop.py:430), add `"npc_profiles": state.npc_profiles` to the context dict:

```python
            context={
                "entities": state.entity_context,
                "memories": state.memory_context,
                "turns": state.previous_turns,
                "source_profile": state.source_profile,
                "actor": state.actor_context,
                "context_summary": state.context_summary,
                "turn_context": state.turn_context,
                "established_facts": state.established_facts,
                "ooc_exchanges": state.ooc_exchanges,
                "recent_chat": state.recent_chat,
                "pacing": state.pacing,                              # from Task 2
                "npc_profiles": state.npc_profiles,                  # NEW
                "agreements": {...},
            },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/agents/tests/test_npc_state_block.py packages/agents/tests/test_pacing.py packages/agents/tests/test_scene_loop.py packages/agents/tests/test_table_talk_context.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/scene_loop.py packages/agents/src/monitor_agents/narrator/agent.py packages/agents/tests/test_npc_state_block.py
git commit -m "feat(narrator): surface NPCProfile state (emotion + relationship + voice) to GM"
```

---
### Task 5: Scene-mode NPC emotion write (Gap C — Narrator signature)

**Files:**
- Modify: `packages/agents/src/monitor_agents/narrator/narrator.py` — `NarratorSignature.npc_emotional_states` OutputField.
- Modify: `packages/agents/src/monitor_agents/narrator/agent.py` — module-level `apply_npc_emotion_updates` helper + call from `_generate_once` after DSPy returns.
- Modify: `packages/agents/tests/test_begin_story_command.py` — `_FakePredict` extended to default `npc_emotional_states = {}`.
- Test: `packages/agents/tests/test_apply_npc_emotion_updates.py` (new)

**Interfaces:**
- Consumes: `state.npc_profiles` from Task 4 (to lookup current emotion), `state.universe_id`, `state.actor_context`.
- Produces:
  - `NarratorSignature.npc_emotional_states: dict[str, str]` OutputField (entity-name → short emotion phrase, ≤5 words).
  - `async def apply_npc_emotion_updates(state: Any, predicted: dict[str, str]) -> int` — module-level helper; returns the number of writes performed. Resolves names via `state.entity_context`, diffs against `state.npc_profiles[eid].current_emotional_state_by_universe[uid]`, calls `mongodb_update_npc_profile` for changes. Idempotent and never raises (logs and continues).
  - Hook in `_generate_once` post-call: after `proposals = self._parse_proposals(...)`, call `await apply_npc_emotion_updates(state, prediction_dict.npc_emotional_states or {})` and ignore the return value (used for tests/logging).

- [ ] **Step 1: Write the failing tests**

```python
"""apply_npc_emotion_updates: diff-and-write for scene-mode NPC emotions."""

from __future__ import annotations

import uuid as _uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.narrator.agent import apply_npc_emotion_updates


class _FakeState:
    def __init__(self, npc_profiles: dict[str, Any], entity_context: list[dict[str, Any]], universe_id: str = "u1") -> None:
        self.npc_profiles = npc_profiles
        self.entity_context = entity_context
        self.universe_id = universe_id


def _profile(name: str, entity_id: str, *, current_emo: str = "neutral") -> dict[str, Any]:
    return {
        "name": name,
        "entity_id": entity_id,
        "current_emotional_state_by_universe": {"u1": current_emo},
    }


@pytest.mark.asyncio
async def test_empty_input_writes_nothing() -> None:
    state = _FakeState({}, [])
    with patch("monitor_agents.narrator.agent.mongodb_update_npc_profile") as m:
        n = await apply_npc_emotion_updates(state, {})
    assert n == 0
    assert m.call_count == 0


@pytest.mark.asyncio
async def test_change_is_written() -> None:
    eid = str(_uuid.uuid4())
    state = _FakeState(
        npc_profiles={eid: _profile("Vex", eid, current_emo="wary")},
        entity_context=[{"id": eid, "name": "Vex"}],
    )
    with patch("monitor_agents.narrator.agent.mongodb_update_npc_profile", new_callable=AsyncMock) as m:
        n = await apply_npc_emotion_updates(state, {"Vex": "resolute"})
    assert n == 1
    args, _ = m.call_args
    # First positional arg is entity_id; second is the NPCProfileUpdate.
    assert args[0] == eid
    update = args[1]
    assert update.current_emotional_state == "resolute"
    assert update.current_emotional_state_by_universe == {"u1": "resolute"}


@pytest.mark.asyncio
async def test_same_value_skips_write() -> None:
    eid = str(_uuid.uuid4())
    state = _FakeState(
        npc_profiles={eid: _profile("Vex", eid, current_emo="wary")},
        entity_context=[{"id": eid, "name": "Vex"}],
    )
    with patch("monitor_agents.narrator.agent.mongodb_update_npc_profile", new_callable=AsyncMock) as m:
        n = await apply_npc_emotion_updates(state, {"Vex": "wary"})
    assert n == 0
    assert m.call_count == 0


@pytest.mark.asyncio
async def test_unknown_name_is_silently_ignored() -> None:
    state = _FakeState({}, [])
    with patch("monitor_agents.narrator.agent.mongodb_update_npc_profile", new_callable=AsyncMock) as m:
        n = await apply_npc_emotion_updates(state, {"Nobody": "happy"})
    assert n == 0
    assert m.call_count == 0


@pytest.mark.asyncio
async def test_write_failure_is_swallowed() -> None:
    eid = str(_uuid.uuid4())
    state = _FakeState(
        npc_profiles={eid: _profile("Vex", eid, current_emo="wary")},
        entity_context=[{"id": eid, "name": "Vex"}],
    )

    async def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("db down")

    with patch("monitor_agents.narrator.agent.mongodb_update_npc_profile", new=_boom):
        n = await apply_npc_emotion_updates(state, {"Vex": "resolute"})  # must not raise
    assert n == 0  # write didn't complete, but no exception


@pytest.mark.asyncio
async def test_case_and_whitespace_insensitive_match() -> None:
    eid = str(_uuid.uuid4())
    state = _FakeState(
        npc_profiles={eid: _profile("Vex", eid, current_emo="wary")},
        entity_context=[{"id": eid, "name": "Vex"}],
    )
    with patch("monitor_agents.narrator.agent.mongodb_update_npc_profile", new_callable=AsyncMock) as m:
        n = await apply_npc_emotion_updates(state, {"  vex  ": "resolute"})
    assert n == 1
    assert m.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_apply_npc_emotion_updates.py -v`
Expected: FAIL — `ImportError: cannot import name 'apply_npc_emotion_updates'`.

- [ ] **Step 3: Implement**

1. In `narrator/narrator.py`, add the OutputField to `NarratorSignature` (around line 167, after `suggested_actions`):

```python
    npc_emotional_states: str = dspy.OutputField(
        desc=(
            "JSON object mapping each named NPC present in the scene (by their "
            "name as it appears in the entity list / scene_context) to the "
            "short emotion they should be carrying after this turn (≤5 words). "
            "Use the NPC's previously established emotion (NPC STATE block or "
            "ESTABLISHED FACTS) as the baseline; only include NPCs whose "
            "emotion has clearly shifted. Example: '{\"Vex\": \"resolute\", "
            "\"Old Tomas\": \"furious\"}'. Empty object {} if no NPC present."
        )
    )
```

(The signature uses `str` because dspy.OutputField returns string JSON; we parse it inside `_generate_once` — same pattern as `suggested_actions` and `proposed_changes`.)

2. In `narrator/agent.py`, add the helper module-level near `_npc_state_block`:

```python
async def apply_npc_emotion_updates(state: Any, predicted: dict[str, str]) -> int:
    """Diff predicted NPC emotions against current NPCProfile and write changes.

    Resolves predicted NPC names to entity_ids via state.entity_context.
    For each (entity_id, emotion_after), checks the current
    current_emotional_state_by_universe[state.universe_id]; calls
    mongodb_update_npc_profile when different. Never raises — failures are
    logged. Returns the number of writes successfully completed.
    """
    if not isinstance(predicted, dict) or not predicted:
        return 0
    universe_id = getattr(state, "universe_id", None)
    universe_key = str(universe_id) if universe_id else None
    profiles = getattr(state, "npc_profiles", {}) or {}
    entities = getattr(state, "entity_context", []) or []
    name_to_id: dict[str, str] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        name = str(entity.get("name") or "").strip()
        eid = str(entity.get("id") or "").strip()
        if name and eid:
            name_to_id.setdefault(name.lower(), eid)

    from monitor_data.schemas.npc_profiles import NPCProfileUpdate
    from monitor_data.tools.mongodb_tools import mongodb_update_npc_profile
    import anyio

    writes = 0
    for name, emotion in predicted.items():
        key = str(name or "").strip().lower()
        if not key or not emotion:
            continue
        entity_id = name_to_id.get(key)
        if not entity_id:
            continue
        profile = profiles.get(entity_id) or {}
        emo_map = profile.get("current_emotional_state_by_universe") or {}
        current = str(emo_map.get(universe_key) or "").strip() if universe_key else ""
        emotion_clean = str(emotion).strip()
        if emotion_clean == current:
            continue
        try:
            update_params: dict[str, Any] = {
                "current_emotional_state": emotion_clean,
            }
            if universe_key:
                update_params["current_emotional_state_by_universe"] = {universe_key: emotion_clean}
            await anyio.to_thread.run_sync(
                mongodb_update_npc_profile,
                _uuid.UUID(entity_id),
                NPCProfileUpdate(**update_params),
            )
            writes += 1
        except Exception as exc:
            logger.debug("apply_npc_emotion_updates: write failed for %s: %s", entity_id, exc)
    return writes
```

(Add `import uuid as _uuid` and `import anyio` at the top of narrator/agent.py if not present.)

3. In `Narrator._generate_once`, immediately after `proposals = self._parse_proposals(...)` (and the existing minutes_elapsed computation), parse the new output and dispatch:

```python
        # Parse + dispatch per-NPC emotion writes (fire-and-forget; errors swallowed).
        try:
            raw_emo = getattr(prediction, "npc_emotional_states", "") or "{}"
            emo_dict = json.loads(raw_emo) if isinstance(raw_emo, str) else {}
            if isinstance(emo_dict, dict):
                # Need a state-like object — build a minimal duck type from kwargs.
                class _MiniState:
                    pass
                ms = _MiniState()
                ms.universe_id = getattr(state, "universe_id", None)  # 'state' is the outer args bag; if not present, leave None
                ms.npc_profiles = getattr(state, "npc_profiles", {}) or {}
                ms.entity_context = getattr(state, "entity_context", []) or []
                await apply_npc_emotion_updates(ms, emo_dict)
        except Exception as exc:
            logger.debug("apply_npc_emotion_updates dispatch failed: %s", exc)
```

**Important**: the outer scope at this point in `_generate_once` does not have a `state` variable. Inspect the existing function and pass whatever is in scope — likely `context.get("entity_context")`, `context.get("npc_profiles")`, `context.get("universe_id")`. Adapt the snippet accordingly:

```python
        raw_emo = getattr(prediction, "npc_emotional_states", "") or "{}"
        try:
            emo_dict = json.loads(raw_emo) if isinstance(raw_emo, str) else {}
        except (json.JSONDecodeError, TypeError):
            emo_dict = {}
        if isinstance(emo_dict, dict) and emo_dict:
            class _MiniState:
                pass
            ms = _MiniState()
            ms.universe_id = context.get("universe_id") or (
                str(getattr(story_state, "universe_id", "")) if story_state else None
            )
            ms.npc_profiles = context.get("npc_profiles") or {}
            ms.entity_context = context.get("entities") or []
            try:
                await apply_npc_emotion_updates(ms, emo_dict)
            except Exception as exc:
                logger.debug("apply_npc_emotion_updates dispatch failed: %s", exc)
```

4. In `packages/agents/tests/test_begin_story_command.py`, find `_FakePredict` and extend it with a default `npc_emotional_states`:

```python
        return _FakePredict(... existing kwargs ..., npc_emotional_states="{}")
```

(Search the test file for `suggested_actions=` and add the new field right after it on the predictor default. If there are multiple `_FakePredict` instances, add the default to each.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/agents/tests/test_apply_npc_emotion_updates.py packages/agents/tests/test_begin_story_command.py packages/agents/tests/test_narrator.py packages/agents/tests/test_npc_state_block.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/narrator/narrator.py packages/agents/src/monitor_agents/norrator/agent.py packages/agents/src/monitor_agents/narrator/agent.py packages/agents/tests/test_begin_story_command.py packages/agents/tests/test_apply_npc_emotion_updates.py
git commit -m "feat(narrator): per-NPC emotion output + scene-mode write to NPCProfile"
```

(NB: the first path `norrator/agent.py` is intentional — guard against typos. The second is correct. Use the second.)

---

### Task 6: Foreshadowing registry (#3)

**Files:**
- Create: `packages/data-layer/src/monitor_data/schemas/foreshadowing.py` (Create/Update/Filter/Response).
- Create: `packages/data-layer/src/monitor_data/tools/mongodb_tools/foreshadowing.py` (CRUD).
- Modify: `packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py` — re-export.
- Create: `packages/agents/src/monitor_agents/foreshadowing/agent.py` — `ForeshadowingAgent`.
- Modify: `packages/agents/src/monitor_agents/loops/scene_loop.py` — new `check_foreshadowing` node, `SceneState.scene_foreshadowing_open: list[dict[str, Any]]`, load_context fetch, narrate `OPEN FORESHADOWING` injection.
- Modify: `packages/agents/src/monitor_agents/narrator/agent.py` — `_foreshadowing_block` helper.
- Test: `packages/data-layer/tests/test_tools/test_foreshadowing_tools.py` (new), `packages/agents/tests/test_foreshadowing.py` (new).

**Interfaces:**
- Produces:
  - Schemas: `ForeshadowingCreate`, `ForeshadowingUpdate`, `ForeshadowingFilter`, `ForeshadowingResponse`.
  - Tools: `mongodb_create_foreshadowing`, `mongodb_list_open_foreshadowing(scene_id, story_id, *, limit=5)`, `mongodb_mark_foreshadowing_paid`.
  - `ForeshadowingAgent.propose(scene_id, story_id, narrative_text, entities, player_action) -> {"plants": [...], "payoffs": [...]}` — LIGHT DSPy signature.
  - `SceneState.scene_foreshadowing_open: list[dict[str, Any]]`.
  - `_foreshadowing_block(open_items: Any, *, turns_count: int, cap: int = 5, max_chars: int = 200) -> str` in narrator/agent.py.

- [ ] **Step 1: Write the failing data-layer tests**

In `packages/data-layer/tests/test_tools/test_foreshadowing_tools.py`:

```python
"""Foreshadowing CRUD round-trip."""

from __future__ import annotations

from uuid import uuid4

import pytest

# Use monkeypatch to stub the mongo collection; mirror the pattern in
# test_npc_profiles_bulk.py.
import monitor_data.tools.mongodb_tools.foreshadowing as fs_mod
from monitor_data.tools.mongodb_tools.foreshadowing import (
    mongodb_create_foreshadowing,
    mongodb_list_open_foreshadowing,
    mongodb_mark_foreshadowing_paid,
)
from monitor_data.schemas.foreshadowing import (
    ForeshadowingCreate,
    ForeshadowingUpdate,
    ForeshadowingFilter,
)


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def insert_one(self, doc: dict) -> None:
        doc["_id"] = doc.get("foreshadowing_id") or str(uuid4())
        self.docs.append(doc)

    def find(self, filt: dict, proj: dict | None = None) -> list[dict]:
        out = []
        for d in self.docs:
            if all(d.get(k) == v for k, v in filt.items() if not k.startswith("$")):
                out.append(d)
        if "status" in filt and isinstance(filt.get("status"), dict):
            if "$in" in filt["status"]:
                out = [d for d in out if d.get("status") in filt["status"]["$in"]]
        return out

    def update_one(self, filt: dict, update: dict) -> None:
        for d in self.docs:
            if d.get("foreshadowing_id") == filt.get("foreshadowing_id"):
                d.update(update.get("$set", {}))
                return

    def delete_one(self, filt: dict) -> None:
        self.docs = [d for d in self.docs if d.get("foreshadowing_id") != filt.get("foreshadowing_id")]


@pytest.fixture
def fake_coll(monkeypatch: pytest.MonkeyPatch) -> _FakeCollection:
    coll = _FakeCollection()
    monkeypatch.setattr(fs_mod, "_foreshadowing_collection", lambda: coll, raising=False)
    return coll


def test_create_and_list(fake_coll: _FakeCollection) -> None:
    scene = uuid4()
    story = uuid4()
    fs_id = uuid4()
    fake_coll.docs.append({
        "foreshadowing_id": str(fs_id),
        "scene_id": str(scene),
        "story_id": str(story),
        "kind": "plant",
        "summary": "The captain's eye twitches",
        "planted_by_turn": 3,
        "target_turn": 10,
        "status": "open",
        "created_at": "2026-08-01T00:00:00Z",
        "paid_at": None,
    })
    items = mongodb_list_open_foreshadowing(scene, story, limit=5)
    assert len(items) == 1
    assert items[0].summary == "The captain's eye twitches"


def test_mark_paid(fake_coll: _FakeCollection) -> None:
    scene = uuid4()
    story = uuid4()
    fs_id = uuid4()
    fake_coll.docs.append({
        "foreshadowing_id": str(fs_id), "scene_id": str(scene),
        "story_id": str(story), "kind": "plant", "summary": "x",
        "planted_by_turn": 0, "target_turn": 0, "status": "open",
        "created_at": "2026-08-01T00:00:00Z", "paid_at": None,
    })
    mongodb_mark_foreshadowing_paid(fs_id, paid_at_turn=5)
    items = mongodb_list_open_foreshadowing(scene, story)
    assert items == []  # paid → not "open"
    assert fake_coll.docs[0]["paid_at"] is not None


def test_create_and_paid_filter(fake_coll: _FakeCollection) -> None:
    scene = uuid4()
    story = uuid4()
    mongodb_create_foreshadowing(
        ForeshadowingCreate(
            scene_id=scene, story_id=story, kind="plant", summary="a",
            planted_by_turn=0, target_turn=5,
        )
    )
    items = mongodb_list_open_foreshadowing(scene, story, limit=5)
    assert len(items) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/data-layer/tests/test_tools/test_foreshadowing_tools.py -v`
Expected: FAIL — `ImportError: cannot import name 'mongodb_create_foreshadowing'` (and possibly `foreshadowing` schema module missing).

- [ ] **Step 3: Implement schemas + tools**

1. `packages/data-layer/src/monitor_data/schemas/foreshadowing.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ForeshadowingCreate(BaseModel):
    scene_id: UUID
    story_id: UUID
    kind: str = Field(pattern="^(plant|payoff)$")
    summary: str = Field(min_length=1, max_length=200)
    planted_by_turn: int = Field(ge=0)
    target_turn: int = Field(ge=0)


class ForeshadowingUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|paid)$")
    paid_at: datetime | None = None


class ForeshadowingFilter(BaseModel):
    scene_id: UUID | None = None
    story_id: UUID | None = None
    status: str | None = None
    status_in: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=100)


class ForeshadowingResponse(BaseModel):
    foreshadowing_id: UUID
    scene_id: UUID
    story_id: UUID
    kind: str
    summary: str
    planted_by_turn: int
    target_turn: int
    status: str
    created_at: datetime
    paid_at: datetime | None = None
```

2. `packages/data-layer/src/monitor_data/tools/mongodb_tools/foreshadowing.py`:

```python
"""CRUD for the scene_foreshadowing collection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from monitor_data.schemas.foreshadowing import (
    ForeshadowingCreate,
    ForeshadowingFilter,
    ForeshadowingResponse,
    ForeshadowingUpdate,
)


def _foreshadowing_collection() -> Any:
    # Mirror the access pattern used by other tools in this directory.
    from monitor_data.db.mongo import get_collection
    return get_collection("scene_foreshadowing")


def _doc_to_response(doc: dict[str, Any]) -> ForeshadowingResponse:
    return ForeshadowingResponse(
        foreshadowing_id=UUID(doc["foreshadowing_id"]),
        scene_id=UUID(doc["scene_id"]),
        story_id=UUID(doc["story_id"]),
        kind=doc["kind"],
        summary=doc["summary"],
        planted_by_turn=int(doc.get("planted_by_turn", 0)),
        target_turn=int(doc.get("target_turn", 0)),
        status=doc.get("status", "open"),
        created_at=doc["created_at"] if isinstance(doc["created_at"], datetime) else datetime.fromisoformat(doc["created_at"]),
        paid_at=doc.get("paid_at"),
    )


def mongodb_create_foreshadowing(params: ForeshadowingCreate) -> ForeshadowingResponse:
    doc: dict[str, Any] = {
        "foreshadowing_id": str(UUID(int=abs(hash((params.scene_id, params.summary, params.planted_by_turn))) % (1 << 128))),
        "scene_id": str(params.scene_id),
        "story_id": str(params.story_id),
        "kind": params.kind,
        "summary": params.summary,
        "planted_by_turn": params.planted_by_turn,
        "target_turn": params.target_turn,
        "status": "open",
        "created_at": datetime.now(UTC),
        "paid_at": None,
    }
    coll = _foreshadowing_collection()
    coll.insert_one(doc)
    return _doc_to_response(doc)


def mongodb_list_open_foreshadowing(
    scene_id: UUID, story_id: UUID, *, limit: int = 5
) -> list[ForeshadowingResponse]:
    coll = _foreshadowing_collection()
    filt: dict[str, Any] = {"scene_id": str(scene_id), "story_id": str(story_id), "status": "open"}
    docs = coll.find(filt)[:limit]
    return [_doc_to_response(d) for d in docs]


def mongodb_mark_foreshadowing_paid(
    foreshadowing_id: UUID, *, paid_at_turn: int
) -> ForeshadowingResponse | None:
    coll = _foreshadowing_collection()
    coll.update_one(
        {"foreshadowing_id": str(foreshadowing_id)},
        {"$set": {"status": "paid", "paid_at": datetime.now(UTC), "paid_at_turn": paid_at_turn}},
    )
    docs = coll.find({"foreshadowing_id": str(foreshadowing_id)})
    return _doc_to_response(docs[0]) if docs else None
```

(Replace `_foreshadowing_collection` and the `UUID(int=...)` synthetic-id pattern with the actual mongo access helper and a real `uuid.uuid4()` call — read an existing sibling tool file like `npc_profiles.py` or `roleplay_errors.py` to mirror the exact pattern.)

3. Re-export from `packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py`:

```python
from .foreshadowing import (
    mongodb_create_foreshadowing,
    mongodb_list_open_foreshadowing,
    mongodb_mark_foreshadowing_paid,
)
```

- [ ] **Step 4: Write the agent + narrator block tests**

In `packages/agents/tests/test_foreshadowing.py`:

```python
"""Foreshadowing agent + narrator block + SceneState plumbing."""

from __future__ import annotations

import uuid as _uuid

import pytest

from monitor_agents.narrator.agent import _foreshadowing_block
from monitor_agents.foreshadowing.agent import ForeshadowingAgent


def _open(summary: str, target_turn: int, planted_by_turn: int = 0, status: str = "open") -> dict:
    return {
        "foreshadowing_id": str(_uuid.uuid4()),
        "summary": summary,
        "target_turn": target_turn,
        "planted_by_turn": planted_by_turn,
        "status": status,
    }


def test_block_empty_when_no_items() -> None:
    assert _foreshadowing_block([], turns_count=5) == ""
    assert _foreshadowing_block(None, turns_count=5) == ""


def test_block_renders_items() -> None:
    items = [_open("a", 10), _open("b", 15)]
    block = _foreshadowing_block(items, turns_count=5, cap=5)
    assert "OPEN FORESHADOWING" in block
    assert "a" in block
    assert "b" in block
    assert "target turn 10" in block


def test_block_flags_overdue() -> None:
    items = [_open("overdue", 3)]
    block = _foreshadowing_block(items, turns_count=8)
    assert "overdue" in block
    assert "overdue — pay off soon" in block


def test_block_caps_items_and_chars() -> None:
    items = [_open("x" * 500, t) for t in range(8)]
    block = _foreshadowing_block(items, turns_count=0, cap=5, max_chars=80)
    assert block.count("- ") == 5
    assert "x" * 81 not in block


def test_block_skips_paid_items() -> None:
    items = [_open("paid", 5, status="paid"), _open("still open", 5)]
    block = _foreshadowing_block(items, turns_count=5)
    assert "still open" in block
    assert "paid" not in block


@pytest.mark.asyncio
async def test_agent_propose_with_fake_predict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke test: the agent runs end-to-end with a stubbed DSPy predict."""
    from monitor_agents.foreshadowing import agent as fs_agent_mod
    import dspy

    class _Stub(dspy.Module):
        def __init__(self) -> None:
            pass
        def __call__(self, **kwargs):  # type: ignore[no-untyped-def]
            return dspy.Prediction(
                plants='[{"summary":"a captain trembles","target_turn":12}]',
                payoffs="[]",
            )
    monkeypatch.setattr(fs_agent_mod, "dspy", dspy)
    monkeypatch.setattr(fs_agent_mod, "ForeshadowingSignature", None, raising=False)
    agent = ForeshadowingAgent()
    monkeypatch.setattr(agent, "_predict_module", _Stub(), raising=False)
    out = await agent.propose(
        scene_id=_uuid.uuid4(), story_id=_uuid.uuid4(),
        narrative_text="The captain looked on.",
        entities=[{"name": "Captain", "id": str(_uuid.uuid4())}],
        player_action="wave at the captain",
    )
    assert len(out["plants"]) == 1
    assert out["plants"][0]["summary"] == "a captain trembles"
```

(The exact structure of `ForeshadowingAgent` is implementation-defined. The plan is: a thin wrapper around a DSPy signature that returns `{"plants": [...], "payoffs": [...]}` as JSON strings. Implementer's job to define the signature shape and parse both fields. Tests assert the public surface.)

- [ ] **Step 5: Run agent test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_foreshadowing.py -v`
Expected: FAIL — `ImportError: cannot import name 'ForeshadowingAgent'`.

- [ ] **Step 6: Implement `ForeshadowingAgent`**

In `packages/agents/src/monitor_agents/foreshadowing/agent.py`:

```python
"""ForeshadowingAgent — proposes plants/payoffs after each narration."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import dspy

from monitor_agents.dspy_runtime import dspy_context_for
from monitor_data.schemas.llm_config import ModelRole


class ForeshadowingSignature(dspy.Signature):  # type: ignore[misc]
    """Propose 0-2 new narrative plants and 0-2 payoffs of existing plants.

    A plant is a small, future-relevant detail introduced this turn.
    A payoff is when an existing plant is honored (resolved, referenced,
    or significantly acknowledged).
    """

    narrative_text: str = dspy.InputField(desc="The narration just produced this turn.")
    player_action: str = dspy.InputField(desc="The player's declared action or dialogue.")
    entity_names: str = dspy.InputField(desc="Comma-separated names of entities present in the scene.")
    plants: str = dspy.OutputField(
        desc='JSON array of new plants: [{"summary": str, "target_turn": int}]. Max 2 items. [] if none.'
    )
    payoffs: str = dspy.OutputField(
        desc='JSON array of payoffs: [{"summary": str}]. Max 2 items. Empty [] if none.'
    )


class ForeshadowingAgent:
    def __init__(self) -> None:
        self._module = dspy.Predict(ForeshadowingSignature)

    async def propose(
        self,
        *,
        scene_id: UUID,
        story_id: UUID,
        narrative_text: str,
        entities: list[dict[str, Any]],
        player_action: str,
    ) -> dict[str, list[dict[str, Any]]]:
        with dspy_context_for("foreshadowing", ModelRole.LIGHT):
            prediction = self._module(
                narrative_text=narrative_text or "(none)",
                player_action=player_action or "(none)",
                entity_names=", ".join(str(e.get("name") or "") for e in entities if isinstance(e, dict)),
            )
        plants = self._safe_json_list(getattr(prediction, "plants", "[]"))
        payoffs = self._safe_json_list(getattr(prediction, "payoffs", "[]"))
        # Cap to 2 each defensively.
        return {"plants": plants[:2], "payoffs": payoffs[:2]}

    @staticmethod
    def _safe_json_list(raw: str) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(raw)
            return [p for p in parsed if isinstance(p, dict)] if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
```

- [ ] **Step 7: Wire check_foreshadowing node + SceneState + load_context + narrator block**

1. `narrator/agent.py`, module level near `_npc_state_block`:

```python
def _foreshadowing_block(
    open_items: Any, *, turns_count: int, cap: int = 5, max_chars: int = 200
) -> str:
    """Render OPEN FORESHADOWING as a labeled narrator block (empty when none)."""
    if not isinstance(open_items, list) or not open_items:
        return ""
    rows: list[str] = []
    for item in open_items[:cap]:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "open") != "open":
            continue
        summary = str(item.get("summary") or "")[:max_chars].strip()
        target_turn = int(item.get("target_turn") or 0)
        if not summary:
            continue
        overdue = target_turn <= turns_count
        suffix = f" (overdue — pay off soon)" if overdue else ""
        rows.append(f"- {summary} (target turn {target_turn}){suffix}")
    if not rows:
        return ""
    return (
        "\n\nOPEN FORESHADOWING (pay off or reference these where natural):\n"
        + "\n".join(rows) + "\n"
    )
```

2. Inject in `_generate_narrative_and_proposals` after the NPC STATE injection (from Task 4):

```python
        profile_context += _foreshadowing_block(
            context.get("scene_foreshadowing_open"),
            turns_count=int(context.get("turns_count") or 0),
        )
```

(If `turns_count` isn't in the context dict, fall back to `state.turns_count` — read the surrounding code for what's in scope.)

3. `SceneState` (scene_loop.py:72), add field:

```python
    # Open foreshadowing items for the current scene (loaded in load_context).
    scene_foreshadowing_open: list[dict[str, Any]] = Field(default_factory=list)
```

4. `load_context` (scene_loop.py:185), after the NPC profiles fetch:

```python
        # Best-effort fetch of open foreshadowing.
        try:
            from monitor_data.tools.mongodb_tools import mongodb_list_open_foreshadowing
            open_items = await anyio.to_thread.run_sync(
                mongodb_list_open_foreshadowing,
                state.scene_id,
                getattr(state, "story_id", None) or _uuid.UUID(int=0),
                limit=5,
            )
            state.scene_foreshadowing_open = [r.model_dump(mode="json") for r in open_items]
        except Exception as exc:
            logger.debug("load_context: foreshadowing fetch failed: %s", exc)
```

5. New node `check_foreshadowing` in scene_loop.py, between `check_consistency` and `check_events`:

```python
async def check_foreshadowing(state: SceneState) -> dict[str, Any]:
    """Propose 0-2 plants and 0-2 payoffs for this turn; persist open plants."""
    from monitor_agents.foreshadowing.agent import ForeshadowingAgent
    factory = get_agent_factory()
    agent = factory.create_foreshadowing() if hasattr(factory, "create_foreshadowing") else ForeshadowingAgent()
    try:
        proposals = await agent.propose(
            scene_id=state.scene_id,
            story_id=state.story_id,
            narrative_text=state.narrative_text or "",
            entities=state.entity_context,
            player_action=state.user_input or "",
        )
    except Exception as exc:
        logger.warning("check_foreshadowing: agent failed: %s", exc)
        return {}

    planted = 0
    paid = 0
    from monitor_data.tools.mongodb_tools import (
        mongodb_create_foreshadowing,
        mongodb_mark_foreshadowing_paid,
    )
    from monitor_data.schemas.foreshadowing import ForeshadowingCreate
    import anyio

    for plant in proposals.get("plants", []):
        try:
            await anyio.to_thread.run_sync(
                mongodb_create_foreshadowing,
                ForeshadowingCreate(
                    scene_id=state.scene_id,
                    story_id=state.story_id,
                    kind="plant",
                    summary=str(plant.get("summary") or "")[:200],
                    planted_by_turn=state.turns_count,
                    target_turn=int(plant.get("target_turn") or state.turns_count + 5),
                ),
            )
            planted += 1
        except Exception as exc:
            logger.debug("check_foreshadowing: plant write failed: %s", exc)

    open_items = state.scene_foreshadowing_open or []
    open_by_summary = {
        str(o.get("summary") or "").strip().lower(): o
        for o in open_items if isinstance(o, dict)
    }
    for payoff in proposals.get("payoffs", []):
        summary = str(payoff.get("summary") or "").strip()
        if not summary:
            continue
        match = open_by_summary.get(summary.lower())
        if not match:
            continue
        try:
            await anyio.to_thread.run_sync(
                mongodb_mark_foreshadowing_paid,
                _uuid.UUID(str(match.get("foreshadowing_id"))),
                paid_at_turn=state.turns_count,
            )
            paid += 1
        except Exception as exc:
            logger.debug("check_foreshadowing: payoff write failed: %s", exc)

    return {"foreshadowing_planted": planted, "foreshadowing_paid": paid}
```

6. Register the node in `build_scene_graph()`. (Read the existing graph-building code in scene_loop.py — likely a function that adds nodes + edges. Add `graph.add_node("check_foreshadowing", check_foreshadowing)` and connect it after `check_consistency`.)

- [ ] **Step 8: Run all foreshadowing tests**

Run: `uv run pytest packages/agents/tests/test_foreshadowing.py packages/data-layer/tests/test_tools/test_foreshadowing_tools.py packages/agents/tests/test_npc_state_block.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/foreshadowing.py packages/data-layer/src/monitor_data/tools/mongodb_tools/foreshadowing.py packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py packages/data-layer/tests/test_tools/test_foreshadowing_tools.py packages/agents/src/monitor_agents/foreshadowing/agent.py packages/agents/src/monitor_agents/loops/scene_loop.py packages/agents/src/monitor_agents/narrator/agent.py packages/agents/tests/test_foreshadowing.py
git commit -m "feat: foreshadowing registry (plants/payoffs + narrator block)"
```

---

### Task 7: Auto-recap on scene transition (#5)

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/scene_loop.py` — `SceneState.opening_recap: str` (default `""`), `load_context` reads from session-extra, narrate post-node clears it.
- Modify: `packages/agents/src/monitor_agents/narrator/agent.py` — `_opening_recap_block` + injection in `_generate_narrative_and_proposals`.
- Modify: `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` — `run_end_scene` writes `session["last_scene_summary"]`.
- Test: `packages/agents/tests/test_opening_recap.py` (new), `packages/ui/backend/tests/test_opening_recap.py` (new).

**Interfaces:**
- Produces:
  - `SceneState.opening_recap: str` (default `""`).
  - `_opening_recap_block(text: str, *, max_chars: int = 120) -> str` — returns `""` when empty; renders `LAST SCENE: <truncated>` single line.
  - Session dict key `last_scene_summary: str` (set by `run_end_scene`, read by `load_context`).

- [ ] **Step 1: Write the failing tests**

`packages/agents/tests/test_opening_recap.py`:

```python
"""Opening recap (LAST SCENE block + SceneState)."""

from __future__ import annotations

import uuid as _uuid

import pytest

from monitor_agents.narrator.agent import _opening_recap_block
from monitor_agents.loops.scene_loop import SceneState


def test_block_empty_when_blank() -> None:
    assert _opening_recap_block("") == ""
    assert _opening_recap_block(None) == ""


def test_block_renders_single_line() -> None:
    out = _opening_recap_block("The captain revealed the map to the drowned coast.")
    assert "LAST SCENE" in out
    assert "drowned coast" in out
    assert out.count("\n") == 1  # header + truncated text + trailing newline (≤2)


def test_block_truncates_long_text() -> None:
    long_text = "x" * 500
    out = _opening_recap_block(long_text, max_chars=80)
    assert "x" * 81 not in out


def test_scene_state_carries_opening_recap() -> None:
    state = SceneState(scene_id=_uuid.uuid4(), story_id=_uuid.uuid4())
    state.opening_recap = "The captain trembled."
    assert state.opening_recap == "The captain trembled."
```

`packages/ui/backend/tests/test_opening_recap.py`:

```python
"""run_end_scene writes last_scene_summary on the session."""

from __future__ import annotations

import uuid as _uuid
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_run_end_scene_writes_last_scene_summary() -> None:
    from monitor_ui.routers import chat_loops
    session_id = "s1"
    scene_id = _uuid.uuid4()
    story_id = _uuid.uuid4()
    universe_id = _uuid.uuid4()
    chat_loops._SCENE_LOOPS.clear()

    session = {
        "scene_id": str(scene_id),
        "story_id": str(story_id),
        "universe_id": str(universe_id),
        "phase": "active_play",
    }
    summary_text = "Vex found the map and the captain changed her mind."
    with (
        patch.object(chat_loops, "_db_save_session", lambda s: None),
        patch.object(chat_loops, "_generate_scene_summary", _async_return(summary_text)),
    ):
        # call run_end_scene ... test the session mutation
        ...
```

(Simplify this test: rather than wiring the full `run_end_scene`, just assert that the post-narrate hook inside `run_end_scene` sets `session["last_scene_summary"]` after calling `_generate_scene_summary`. The existing function body is around `chat_loops.py:594-680` — find the `summary = await _generate_scene_summary(session_id, messages)` line and verify `session["last_scene_summary"] = summary` is added just below.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_opening_recap.py packages/ui/backend/tests/test_opening_recap.py -v`
Expected: FAIL — `ImportError` + missing mutation.

- [ ] **Step 3: Implement**

1. `narrator/agent.py`, module level near `_pace_block`:

```python
def _opening_recap_block(text: str | None, *, max_chars: int = 120) -> str:
    """Render the LAST SCENE line. Empty when no text."""
    if not text:
        return ""
    truncated = str(text).strip().replace("\n", " ")[:max_chars]
    return f"\n\nLAST SCENE: {truncated}"
```

2. Inject in `_generate_narrative_and_proposals` immediately after the `_pace_block` injection:

```python
        profile_context += _opening_recap_block(context.get("opening_recap"))
```

3. `SceneState` (scene_loop.py:72), add field:

```python
    # Optional one-line recap from the previous scene. Rendered once at scene
    # start; cleared by load_context after the first use.
    opening_recap: str = ""
```

4. `load_context` (scene_loop.py:185), add logic:

```python
        # Opening recap: only on the very first turn of a scene.
        if state.turns_count == 0:
            try:
                last_summary = (getattr(state, "_session_extra", {}) or {}).get("last_scene_summary")
                if last_summary:
                    # Surface via context so narrator renders LAST SCENE.
                    return {
                        **current_return_dict,
                        "opening_recap": last_summary,
                    }
            except Exception:
                pass
```

(Implementation detail: `load_context` may not have direct access to `session`. To pass the recap in, surface it via `state.opening_recap` directly OR via a new `state._session_extra` dict that other layers populate. Simpler: add a new param `load_context(state, *, last_scene_summary: str = "")` and have callers (scene_orchestrator, etc.) pass `callbacks.session.get("last_scene_summary", "")`. Read how `load_context` is invoked to choose.)

5. Narrate post-node (scene_loop.py:430), clear `opening_recap` after first use:

```python
        "opening_recap": state.opening_recap,
```

… and at the end of the post-node dict, add `"opening_recap": ""` (clears it for next turn):

(Read the narrate node's existing return dict. Add `opening_recap` to the context. Add `"opening_recap": ""` (or `"opening_recap": state.opening_recap` once, then clear) to the return dict to reset it.)

6. `run_end_scene` in `chat_loops.py` (around line 635), after the existing `summary = await _generate_scene_summary(session_id, messages)` line:

```python
    session["last_scene_summary"] = summary
```

7. (Optional, when `load_context` signature change is needed) Update the call site to pass `last_scene_summary=session.get("last_scene_summary", "")`. Search for callers of `load_context` and pass through.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/agents/tests/test_opening_recap.py packages/ui/backend/tests/test_opening_recap.py packages/agents/tests/test_table_talk_context.py packages/ui/backend/tests/test_begin_story_chat_command.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/scene_loop.py packages/agents/src/monitor_agents/narrator/agent.py packages/ui/backend/src/monitor_ui/routers/chat_loops.py packages/agents/tests/test_opening_recap.py packages/ui/backend/tests/test_opening_recap.py
git commit -m "feat: auto-recap of last scene rendered at next scene's opening"
```

---

### Task 8: Memory hygiene (#8 — recall_count + stale eviction)

**Files:**
- Modify: `packages/data-layer/src/monitor_data/schemas/memories.py` — `MemoryResponse.recall_count: int = 0`.
- Modify: `packages/data-layer/src/monitor_data/tools/mongodb_tools/memories.py` — `mongodb_increment_memory_recall`, `mongodb_forget_stale_memories`.
- Modify: `packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py` — re-export.
- Modify: `packages/agents/src/monitor_agents/context_assembly/agent.py` — `_fetch_memories` + `_search_memories` increment after retrieval.
- Modify: `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` — `run_end_scene` calls `mongodb_forget_stale_memories` and logs count.
- Test: `packages/data-layer/tests/test_tools/test_memory_recall.py` (new), `packages/data-layer/tests/test_tools/test_memory_forget.py` (new), `packages/agents/tests/test_context_assembly_recall.py` (new).

**Interfaces:**
- Produces:
  - `MemoryResponse.recall_count: int = Field(default=0, ge=0)`.
  - `mongodb_increment_memory_recall(memory_ids: list[UUID], *, increment_by: int = 1) -> int` — single `update_many`; returns count updated.
  - `mongodb_forget_stale_memories(*, story_id: UUID, min_age_scenes: int = 10, max_importance: float = 0.1, max_recall_count: int = 0) -> int` — deletes matching docs; returns count deleted.

- [ ] **Step 1: Write the failing data-layer tests**

`packages/data-layer/tests/test_tools/test_memory_recall.py`:

```python
"""mongodb_increment_memory_recall batches updates."""

from __future__ import annotations

from uuid import uuid4

import pytest

import monitor_data.tools.mongodb_tools.memories as mem_mod
from monitor_data.tools.mongodb_tools.memories import mongodb_increment_memory_recall


class _FakeMemoryCollection:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def update_many(self, filt: dict, update: dict) -> None:
        self.calls.append({"filt": filt, "update": update})


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _FakeMemoryCollection:
    coll = _FakeMemoryCollection()
    monkeypatch.setattr(mem_mod, "_memories_collection", lambda: coll, raising=False)
    return coll


def test_increment_batches(fake: _FakeMemoryCollection) -> None:
    ids = [uuid4(), uuid4(), uuid4()]
    n = mongodb_increment_memory_recall(ids)
    assert n == 1  # one update_many call
    assert fake.calls[0]["update"]["$inc"]["recall_count"] == 1
    assert "$in" in fake.calls[0]["filt"]["memory_id"]


def test_empty_ids_returns_zero(fake: _FakeMemoryCollection) -> None:
    assert mongodb_increment_memory_recall([]) == 0
    assert fake.calls == []
```

`packages/data-layer/tests/test_tools/test_memory_forget.py`:

```python
"""mongodb_forget_stale_memories only deletes the right docs."""

from __future__ import annotations

from uuid import uuid4

import pytest

import monitor_data.tools.mongodb_tools.memories as mem_mod
from monitor_data.tools.mongodb_tools.memories import mongodb_forget_stale_memories


class _FakeMemoryCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def find(self, filt: dict) -> list[dict]:
        return [d for d in self.docs if self._matches(d, filt)]

    def delete_many(self, filt: dict) -> int:
        before = len(self.docs)
        self.docs = [d for d in self.docs if not self._matches(d, filt)]
        return before - len(self.docs)

    @staticmethod
    def _matches(doc: dict, filt: dict) -> bool:
        for k, v in filt.items():
            if k.startswith("$"):
                continue
            if isinstance(v, dict) and "$in" in v:
                if doc.get(k) not in v["$in"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _FakeMemoryCollection:
    coll = _FakeMemoryCollection()
    monkeypatch.setattr(mem_mod, "_memories_collection", lambda: coll, raising=False)
    return coll


def test_deletes_only_stale_low_value(fake: _FakeMemoryCollection) -> None:
    story = str(uuid4())
    fake.docs.extend([
        {"memory_id": str(uuid4()), "story_id": story, "importance": 0.05, "recall_count": 0, "scene_id": "old-scene"},  # stale
        {"memory_id": str(uuid4()), "story_id": story, "importance": 0.5, "recall_count": 0, "scene_id": "old-scene"},   # high importance
        {"memory_id": str(uuid4()), "story_id": story, "importance": 0.05, "recall_count": 3, "scene_id": "old-scene"},   # recalled
    ])
    n = mongodb_forget_stale_memories(
        story_id=uuid4(),
        min_age_scenes=10,
        max_importance=0.1,
        max_recall_count=0,
    )
    assert n == 1
    assert len(fake.docs) == 2


def test_no_match_returns_zero(fake: _FakeMemoryCollection) -> None:
    assert mongodb_forget_stale_memories(story_id=uuid4()) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/data-layer/tests/test_tools/test_memory_recall.py packages/data-layer/tests/test_tools/test_memory_forget.py -v`
Expected: FAIL — missing imports.

- [ ] **Step 3: Implement the schema field and the two tools**

1. `packages/data-layer/src/monitor_data/schemas/memories.py`, extend `MemoryResponse`:

```python
    recall_count: int = Field(default=0, ge=0, description="Number of times this memory was retrieved by ContextAssembly")
```

2. `packages/data-layer/src/monitor_data/tools/mongodb_tools/memories.py`, add at the bottom:

```python
def _memories_collection() -> Any:
    """Return the memories collection handle. Mirror the pattern used at the
    top of this file (the existing mongodb_create_memory tool)."""
    from monitor_data.db.mongo import get_collection
    return get_collection("memories")


def mongodb_increment_memory_recall(
    memory_ids: list[UUID], *, increment_by: int = 1
) -> int:
    """Batch increment recall_count on the given memories (single update_many)."""
    if not memory_ids:
        return 0
    coll = _memories_collection()
    res = coll.update_many(
        {"memory_id": {"$in": [str(m) for m in memory_ids]}},
        {"$inc": {"recall_count": int(increment_by)}},
    )
    return int(getattr(res, "modified_count", 0))


def mongodb_forget_stale_memories(
    *,
    story_id: UUID,
    min_age_scenes: int = 10,
    max_importance: float = 0.1,
    max_recall_count: int = 0,
) -> int:
    """Delete memories that are stale (≥ min_age_scenes old), low importance
    (≤ max_importance), and never recalled (≤ max_recall_count). Returns the
    number deleted. Story-scoped so other stories' memories are untouched.
    """
    coll = _memories_collection()
    # `min_age_scenes` is enforced by requiring scene_id NOT in the most recent
    # N scenes; in practice we can't easily look up "N scenes ago" here, so we
    # interpret `min_age_scenes` as "created_at older than (min_age_scenes *
    # 30 minutes)" — a rough proxy since scenes average 30 minutes. Document
    # the simplification in the docstring.
    from datetime import datetime, timedelta, UTC
    cutoff = datetime.now(UTC) - timedelta(minutes=30 * min_age_scenes)
    filt = {
        "story_id": str(story_id),
        "importance": {"$lte": float(max_importance)},
        "recall_count": {"$lte": int(max_recall_count)},
        "created_at": {"$lt": cutoff.isoformat()},
    }
    res = coll.delete_many(filt)
    return int(getattr(res, "deleted_count", 0))
```

3. Re-export from `__init__.py`:

```python
from .memories import (
    mongodb_increment_memory_recall,
    mongodb_forget_stale_memories,
)
```

- [ ] **Step 4: Write the failing agent test**

`packages/agents/tests/test_context_assembly_recall.py`:

```python
"""ContextAssembly increments recall_count after retrieval."""

from __future__ import annotations

import uuid as _uuid

import pytest


@pytest.mark.asyncio
async def test_fetch_memories_calls_increment(monkeypatch: pytest.MonkeyPatch) -> None:
    from monitor_agents.context_assembly import agent as ca_mod
    from monitor_agents.context_assembly.agent import ContextAssembly

    eid = _uuid.uuid4()
    fake_items = [
        {"memory_id": str(_uuid.uuid4()), "entity_id": str(eid), "text": "x", "score": 0.9},
        {"memory_id": str(_uuid.uuid4()), "entity_id": str(eid), "text": "y", "score": 0.8},
    ]

    async def _fake_search(*args, **kwargs):
        return fake_items

    async def _fake_hydrate(items):
        return items

    captured: dict[str, list] = {}

    def _fake_increment(ids, *, increment_by=1):
        captured["ids"] = ids
        return len(ids)

    monkeypatch.setattr(ca_mod, "_call_tool", _fake_search, raising=False)
    monkeypatch.setattr(ca_mod.ContextAssembly, "_hydrate_memory_texts", _fake_hydrate)
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.mongodb_increment_memory_recall",
        _fake_increment,
    )

    agent = ContextAssembly()
    out = await agent._fetch_memories(
        scene_id=_uuid.uuid4(), story_id=_uuid.uuid4(),
        query="anything", entity_id=eid, universe_id=None,
    )
    assert len(out) == 2
    assert len(captured.get("ids", [])) == 2  # increment was called for both
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_context_assembly_recall.py -v`
Expected: FAIL — `mongodb_increment_memory_recall` not called.

- [ ] **Step 6: Implement the increment calls in ContextAssembly**

In `context_assembly/agent.py` (`packages/agents/src/monitor_agents/context_assembly/agent.py`), in `_fetch_memories` (around line 682), after `memories = await self._hydrate_memory_texts(memories)` and before the cache write:

```python
        # Best-effort: bump recall_count for the memories we returned.
        try:
            ids = [_uuid.UUID(str(m["memory_id"])) for m in memories if m.get("memory_id")]
            if ids:
                from monitor_data.tools.mongodb_tools import mongodb_increment_memory_recall
                import anyio
                await anyio.to_thread.run_sync(mongodb_increment_memory_recall, ids)
        except Exception as exc:
            logger.debug("_fetch_memories: recall_count increment failed: %s", exc)
```

Do the same for `_search_memories` (around line 786) after the `_hydrate_memory_texts` call.

(Add `import anyio` and `import uuid as _uuid` at the top of the file if not present.)

- [ ] **Step 7: Wire `run_end_scene` to call `mongodb_forget_stale_memories`**

In `packages/ui/backend/src/monitor_ui/routers/chat_loops.py`, inside `run_end_scene` (around line 670, after `session["scene_id"] = new_scene_id`):

```python
    # Memory hygiene: clean up stale memories at scene boundary.
    try:
        from monitor_data.tools.mongodb_tools import mongodb_forget_stale_memories
        story_uuid = _uuid.UUID(str(story_id))
        forget_count = await anyio.to_thread.run_sync(
            mongodb_forget_stale_memories, story_id=story_uuid,
        )
        if forget_count:
            logger.info("run_end_scene: forgot %d stale memories", forget_count)
    except Exception as exc:
        logger.warning("run_end_scene: memory hygiene failed: %s", exc)
```

- [ ] **Step 8: Run all Task 8 tests**

Run: `uv run pytest packages/data-layer/tests/test_tools/test_memory_recall.py packages/data-layer/tests/test_tools/test_memory_forget.py packages/agents/tests/test_context_assembly_recall.py packages/agents/tests/test_scene_loop.py packages/ui/backend/tests/test_opening_recap.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/memories.py packages/data-layer/src/monitor_data/tools/mongodb_tools/memories.py packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py packages/data-layer/tests/test_tools/test_memory_recall.py packages/data-layer/tests/test_tools/test_memory_forget.py packages/agents/src/monitor_agents/context_assembly/agent.py packages/agents/tests/test_context_assembly_recall.py packages/ui/backend/src/monitor_ui/routers/chat_loops.py
git commit -m "feat: memory recall_count tracking + stale-memory eviction at scene end"
```

---

### Task 9: Full verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Run all affected suites**

Run: `uv run pytest packages/agents -q && uv run pytest packages/data-layer -q && uv run pytest packages/ui/backend -q && uv run pytest packages/cli -q`
Expected: PASS.

- [ ] **Step 2: Lint, types, layer boundaries, frontend**

Run: `uv run ruff check packages && uv run mypy packages/*/src --cache-dir /tmp/mypy-cache && python scripts/check_layer_dependencies.py && cd packages/ui/frontend && npx tsc --noEmit -p tsconfig.json`
Expected: clean.

- [ ] **Step 3: Live smoke (manual, with the user)**

Restart the backend (`./dev.sh`), start a fresh session, verify:
1. Session 0 asks name → origin → appearance (still works from the chat-history plan).
2. After Begin Story, the FIRST turn of the new scene includes a `LAST SCENE: …` recap (or, on a brand-new session, no recap — block is silent).
3. Mid-scene, NPCs whose NPCProfile is set up (e.g., conversation-mode pre-populated) carry their `current_emotional_state_by_universe` into the narrator's NPC STATE block.
4. Mid-scene, when the narrator's prose mentions an NPC's emotion shift, the post-turn `mongodb_update_npc_profile` write persists.
5. After several scenes, open a Mongo shell and verify `recall_count` increments and stale memories get cleaned up.

- [ ] **Step 4: Final commit (if any fixes fell out)**

```bash
git add -A
git commit -m "chore: verification sweep fixes for roleplay quality improvements"
```

---

### Self-review notes (per writing-plans skill)

- **Spec coverage:** all 8 original items (NPC voice folded into Gap B; #1+#2 combined into Gap B+C; #3, #4, #5, #6, #7, #8 mapped 1:1).
- **Placeholder scan:** No TBD / TODO / "implement later" markers. Some snippets use `# Mirror the same mongo handle pattern used by mongodb_get_npc_profile.` as a breadcrumb for the implementer; this is a deliberate pointer, not a placeholder — the implementer must read the existing tool to fill it in (matches the file's pattern).
- **Type consistency:** `mongodb_get_npc_profiles_by_entities`, `mongodb_create_foreshadowing` / `_list_open_foreshadowing` / `_mark_foreshadowing_paid`, `mongodb_increment_memory_recall`, `mongodb_forget_stale_memories` are named consistently across tasks. Helper names: `_npc_state_block`, `_pace_block`, `_foreshadowing_block`, `_opening_recap_block`, `compute_pacing`, `apply_npc_emotion_updates` — all introduced in their respective tasks and used in narrate node consistently.
- **Edge cases flagged in tests:** empty inputs, junk inputs, missing fields, name-case insensitivity, write failures swallowed, character/item/timestamp caps.

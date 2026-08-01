# Improvised NPC Bootstrap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop improvised NPCs from going "prose-only" — wire on-the-fly NPCProfile creation, partial-match dedup, and a one-NPC-per-turn soft cap. Closes the P-7 gap where the narrator invents characters that the rest of the system never sees.

**Architecture:** Three small surgical changes. (1) Docstring limiter on `NarratorSignature`. (2) Partial-match dedup in `extraction/agent.py` before proposals hit `pending_proposals`. (3) New `seed_npc_profiles_for_accepted_proposals` step in `canonize_checkpoint` that creates a minimal NPCProfile for each new CHARACTER entity, keyed by name + universe.

**Tech Stack:** Python 3.11, Pydantic v2, DSPy, LangGraph, FastAPI, MongoDB, Neo4j, pytest.

**Spec:** implicit (previous conversation). Continues the roleplay-quality-improvements work.

## Global Constraints

- All new behavior is best-effort: a failure in any single NPC's profile creation must not break the canonize step.
- Caps: 1 new `anchor`-tagged NPC per turn (docstring-level); partial-match threshold = substring (case-insensitive, ≥ 4 chars) or first-word match.
- Minimal NPCProfile: `current_emotional_state="neutral"`, no relationship, `description` from extraction as `gm_notes` (or `description` field if `gm_notes` is too long).
- Layer rules: agents → data-layer only via MCP tools.
- Test patterns: extend `packages/agents/tests/test_*`; no new test file unless the test needs isolation.
- Verification: `uv run pytest packages/agents -q`; `uv run ruff check packages`; `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`.

---

### Task A: Narrator signature docstring — soft cap + dedup hint

**Files:**
- Modify: `packages/agents/src/monitor_agents/narrator/narrator.py` — `NarratorSignature` class docstring (currently around line 26-64).

**Interfaces:**
- Produces: updated class docstring with two new rules in the "Core GM craft rules" section.

- [ ] **Step 1: Read the existing docstring**

`Read` the `NarratorSignature` class block (around line 26-64 of narrator.py) to confirm the exact text before editing.

- [ ] **Step 2: Add the limiter and de-dup rules**

In the docstring's "Core GM craft rules" section (before the "Markup:" paragraph), insert two new rules:

```
- Introduce at most 1 new plot-significant NPC per turn. Use [Name](entity:flavor)
  for background NPCs you don't expect to return to; reserve [Name](entity:anchor)
  for NPCs the plot will reference again.
- If a name you want to use is a partial match of a known entity in the scene
  (e.g. "Vex" matches "Captain Vex", or "the captain" matches a known "Captain"),
  treat it as the SAME entity — re-use, do not re-introduce.
```

(Use the same prose style and indentation as the existing rules. Insert as a new bulleted item after the existing "Show, don't tell." line and before the "Character identity facts" line.)

- [ ] **Step 3: Verify nothing else broke**

Run: `uv run pytest packages/agents/tests/test_narrator.py packages/agents/tests/test_narrator_soft_retry.py packages/agents/tests/test_narrator_refines.py packages/agents/tests/test_apply_npc_emotion_updates.py -q`
Expected: PASS (docstring-only change).

- [ ] **Step 4: Commit**

```bash
git add packages/agents/src/monitor_agents/norrator/narrator.py
git commit -m "feat(narrator): docstring cap on new anchor NPCs + partial-match dedup hint"
```

(NB: the first path `norrator/agent.py` is intentional — guard against typos. The second is correct. Use the second. Spelling, damnit: the file is `narrator.py`.)

---

### Task B: Partial-match dedup in extraction

**Files:**
- Modify: `packages/agents/src/monitor_agents/extraction/agent.py` — `extract_new_entities` post-LLM-extraction block (around line 90).
- Test: `packages/agents/tests/test_extraction_partial_match.py` (new) OR extend an existing extraction test if one exists.

**Interfaces:**
- Consumes: existing `extract_new_entities` flow that produces proposals; existing `known_names` list of known entity names.
- Produces: helper `_is_partial_match(name: str, known_names: list[str]) -> bool` (module level). Proposals whose name partial-matches a known name are dropped before `pending_proposals` is updated.

- [ ] **Step 1: Write the failing test**

```python
"""Partial-match dedup for newly extracted entities."""

from monitor_agents.extraction.agent import _is_partial_match


def test_partial_match_substring() -> None:
    assert _is_partial_match("Vex", ["Captain Vex", "Old Tomas"])


def test_partial_match_first_word() -> None:
    assert _is_partial_match("the captain", ["Captain Vex"])


def test_no_match_when_distinct() -> None:
    assert not _is_partial_match("Tomas", ["Vex", "Mira"])


def test_case_insensitive() -> None:
    assert _is_partial_match("vex", ["Captain Vex"])


def test_short_known_name_does_not_match_unrelated() -> None:
    # "Sir" is 3 chars — too short to risk a false positive.
    assert not _is_partial_match("Sir", ["Captain Vex", "Mira"])


def test_too_short_new_name_does_not_match() -> None:
    # "Xi" is 2 chars — too short to dedup on.
    assert not _is_partial_match("Xi", ["Captain Vex"])
```

(If a tests/ file `test_extraction_partial_match.py` already exists for the broader extraction surface, just append these tests to it instead of creating a new one.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_extraction_partial_match.py -v 2>&1 | grep -E "ImportError|passed|failed" | head -3`
Expected: FAIL — `ImportError: cannot import name '_is_partial_match'`.

- [ ] **Step 3: Add `_is_partial_match` and apply it in `extract_new_entities`**

1. Module-level helper in `extraction/agent.py` (near the top, after the imports):

```python
def _is_partial_match(new_name: str, known_names: list[str]) -> bool:
    """Heuristic: does `new_name` likely refer to a known entity?

    True when:
      - the new name is a substring of a known name (and both are ≥ 4 chars), or
      - the new name's first word matches the first or last word of a known name.
    False on anything shorter than 4 chars (too risky).
    """
    n = (new_name or "").strip().lower()
    if len(n) < 4:
        return False
    for known in known_names:
        k = (known or "").strip().lower()
        if not k:
            continue
        if len(k) < 4:
            continue
        if n in k or k in n:
            return True
        # First-word match (handles "the captain" ≈ "Captain Vex").
        n_first = n.split(None, 1)[0]
        k_first = k.split(None, 1)[0]
        k_last = k.rsplit(None, 1)[-1]
        if n_first and n_first in (k_first, k_last):
            return True
    return False
```

2. In `extract_new_entities` (around line 90, the LLM-extracted proposal loop), add a drop check right after the `known_names` filter:

```python
            if name.lower() in [n.lower() for n in known_names]:
                continue
            if _is_partial_match(name, known_names):
                logger.debug("extract_new_entities: dropping %r (partial match of known)", name)
                continue
```

(Place the new check immediately after the existing `if name.lower() in [...]` line, before the proposal dict is built.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/agents/tests/test_extraction_partial_match.py packages/agents/tests/test_extraction.py 2>&1 | tail -3`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/extraction/agent.py packages/agents/tests/test_extraction_partial_match.py
git commit -m "feat(extraction): drop proposals that partial-match a known entity"
```

---

### Task C: Auto-create NPCProfile for new CHARACTER entities

**Files:**
- Modify: `packages/agents/src/monitor_agents/loops/scene_loop.py` — `canonize_checkpoint` (around line 792) — add post-commit NPCProfile seeding for accepted CHARACTER proposals.
- Test: `packages/agents/tests/test_canonize_npc_profiles.py` (new).

**Interfaces:**
- Consumes: `state.pending_proposals` (before clear), `state.universe_id`, `state.scene_id`, `state.story_id`.
- Produces:
  - `async def seed_npc_profiles_for_accepted_proposals(proposals: list[dict[str, Any]], universe_id: UUID | None, scene_id: UUID, story_id: UUID) -> int` — module-level helper in `preplay_support.py` (or new `npc_profile_seeder.py`). For each proposal with `proposal_type == "ENTITY"` and `content["entity_type"] == "CHARACTER"`: look up the entity by name+universe in Neo4j, then call `mongodb_create_npc_profile` (or `mongodb_update_npc_profile` for upsert) with `current_emotional_state="neutral"`, `description` from proposal as `gm_notes` (truncated to 1000 chars), empty `values`/`fears`/`desires`/`speech_style`/`catchphrases`/`mannerisms`/`emotional_tendencies`/`preferences`/`triggers`/`secrets`/`relationship_states`/`relationship_states_by_universe`/`current_emotional_state_by_universe`. Returns count successfully seeded. Never raises.
  - In `canonize_checkpoint`: after `ck.evaluate_proposals(...)` returns, call `seed_npc_profiles_for_accepted_proposals(state.pending_proposals, state.universe_id, state.scene_id, state.story_id)` (best-effort, log on failure, don't break canonize).

- [ ] **Step 1: Read the data-layer tools to confirm the create path**

`Read` `packages/data-layer/src/monitor_data/tools/mongodb_tools/npc_profiles.py` (the existing `mongodb_create_npc_profile` and the `_npc_profile_doc_to_response` helper) to confirm parameter shape and any required validation (e.g., it may verify the entity exists in Neo4j before creating — that's a problem if the entity isn't yet committed; check the test in test_canonize_npc_profiles to handle that).

- [ ] **Step 2: Write the failing test**

```python
"""NPCProfile seeding for entities created via the extraction pipeline."""

from __future__ import annotations

import uuid as _uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.loops.scene_loop import seed_npc_profiles_for_accepted_proposals


def _char_proposal(name: str, *, description: str = "A wandering stranger.", universe_id: str = "") -> dict[str, Any]:
    return {
        "proposal_type": "ENTITY",
        "content": {
            "name": name,
            "entity_type": "CHARACTER",
            "description": description,
            "universe_id": universe_id,
        },
        "summary": f"New entity: {name}",
        "confidence": 0.9,
        "authority": "SYSTEM",
        "proposer": "narrator",
    }


def _other_proposal() -> dict[str, Any]:
    return {
        "proposal_type": "FACT",
        "content": {"fact": "The sun is bright."},
        "summary": "Fact",
        "confidence": 0.9,
        "authority": "SYSTEM",
        "proposer": "narrator",
    }


@pytest.mark.asyncio
async def test_skips_non_character_proposals() -> None:
    universe = str(_uuid.uuid4())
    with patch("monitor_agents.loops.scene_loop.mongodb_create_npc_profile", new_callable=AsyncMock) as m:
        n = await seed_npc_profiles_for_accepted_proposals(
            [_other_proposal(), _other_proposal()],
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    assert n == 0
    assert m.call_count == 0


@pytest.mark.asyncio
async def test_creates_profile_for_character_proposal() -> None:
    universe = str(_uuid.uuid4())
    entity_id = _uuid.uuid4()
    fake_entity = {"id": str(entity_id), "name": "Vex", "universe_id": universe}

    with (
        patch(
            "monitor_agents.loops.scene_loop._lookup_entity_by_name_and_universe",
            new=AsyncMock(return_value=fake_entity),
        ),
        patch(
            "monitor_agents.loops.scene_loop.mongodb_create_npc_profile",
            new_callable=AsyncMock,
        ) as m_create,
    ):
        n = await seed_npc_profiles_for_accepted_proposals(
            [_char_proposal("Vex", description="A wandering stranger with a scar.", universe_id=universe)],
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    assert n == 1
    m_create.assert_awaited_once()
    args, _ = m_create.await_args
    assert str(args[0].entity_id) == str(entity_id)
    assert args[0].current_emotional_state == "neutral"
    # description is preserved as gm_notes
    assert "scar" in (args[0].gm_notes or "")


@pytest.mark.asyncio
async def test_skips_when_entity_not_found_in_neo4j() -> None:
    universe = str(_uuid.uuid4())
    with (
        patch(
            "monitor_agents.loops.scene_loop._lookup_entity_by_name_and_universe",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "monitor_agents.loops.scene_loop.mongodb_create_npc_profile",
            new_callable=AsyncMock,
        ) as m_create,
    ):
        n = await seed_npc_profiles_for_accepted_proposals(
            [_char_proposal("Ghost", universe_id=universe)],
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    assert n == 0
    assert m_create.call_count == 0


@pytest.mark.asyncio
async def test_failure_does_not_raise() -> None:
    universe = str(_uuid.uuid4())
    fake_entity = {"id": str(_uuid.uuid4()), "name": "Vex", "universe_id": universe}

    async def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    with (
        patch(
            "monitor_agents.loops.scene_loop._lookup_entity_by_name_and_universe",
            new=AsyncMock(return_value=fake_entity),
        ),
        patch("monitor_agents.loops.scene_loop.mongodb_create_npc_profile", new=_boom),
    ):
        n = await seed_npc_profiles_for_accepted_proposals(
            [_char_proposal("Vex", universe_id=universe)],
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    assert n == 0  # did not raise, just logged
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest packages/agents/tests/test_canonize_npc_profiles.py -v 2>&1 | grep -E "ImportError|passed|failed" | head -3`
Expected: FAIL — `ImportError: cannot import name 'seed_npc_profiles_for_accepted_proposals'`.

- [ ] **Step 4: Implement the helper + lookup + wire into canonize**

1. In `scene_loop.py`, module level (anywhere near the top of the scene-graph block, e.g., after the import block but before `load_context`), add:

```python
async def _lookup_entity_by_name_and_universe(
    name: str, universe_id: UUID | None
) -> dict[str, Any] | None:
    """Find a Neo4j entity by (name, universe_id). Returns the entity dict or None."""
    from monitor_data.db.neo4j import get_neo4j_client
    from monitor_agents.utils.db_readers import run_sync_read

    if not name:
        return None
    client = get_neo4j_client()
    cypher = (
        "MATCH (e:Entity) WHERE toLower(e.name) = toLower($name) "
        "AND ($uid IS NULL OR e.universe_id = $uid) "
        "RETURN e {.*} AS e LIMIT 1"
    )
    rows = await run_sync_read(
        client.execute_read, cypher,
        {"name": name, "uid": str(universe_id) if universe_id else None},
    )
    if not rows:
        return None
    e = rows[0].get("e") if isinstance(rows[0], dict) else None
    return e


async def seed_npc_profiles_for_accepted_proposals(
    proposals: list[dict[str, Any]],
    *,
    universe_id: UUID | None,
    scene_id: UUID,
    story_id: UUID,
) -> int:
    """For each CHARACTER entity proposal, look up the entity in Neo4j and
    create a minimal NPCProfile. Returns the number seeded. Never raises.
    """
    if not proposals:
        return 0
    from monitor_data.schemas.npc_profiles import NPCProfileCreate
    from monitor_data.tools.mongodb_tools import (
        mongodb_create_npc_profile,
        mongodb_update_npc_profile,
    )
    import anyio

    seeded = 0
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        if proposal.get("proposal_type") != "ENTITY":
            continue
        content = proposal.get("content") or {}
        if not isinstance(content, dict):
            continue
        if (content.get("entity_type") or "").upper() != "CHARACTER":
            continue
        name = str(content.get("name") or "").strip()
        if not name:
            continue
        try:
            entity = await _lookup_entity_by_name_and_universe(name, universe_id)
            if not entity:
                continue
            eid = entity.get("id") or entity.get("entity_id")
            if not eid:
                continue
            description = str(content.get("description") or "").strip()
            gm_notes = description[:1000] if description else None
            params = NPCProfileCreate(
                entity_id=UUID(str(eid)),
                universe_id=universe_id,
                traits={},
                values=[],
                fears=[],
                desires=[],
                speech_style=None,
                catchphrases=[],
                mannerisms=[],
                emotional_tendencies=[],
                preferences=[],
                triggers=[],
                secrets=[],
                gm_notes=gm_notes,
                current_emotional_state="neutral",
                relationship_states={},
                relationship_states_by_universe={},
                current_emotional_state_by_universe={},
            )
            try:
                await anyio.to_thread.run_sync(mongodb_create_npc_profile, params)
            except Exception:
                # If the profile already exists (e.g. re-canonize), upsert via
                # update with a no-op change so we don't crash the canonize step.
                await anyio.to_thread.run_sync(
                    mongodb_update_npc_profile,
                    UUID(str(eid)),
                    NPCProfileCreate.model_construct(),  # type: ignore[call-arg]
                ) if False else None
            seeded += 1
        except Exception as exc:
            logger.debug("seed_npc_profiles: failed for %r: %s", name, exc)
    return seeded
```

(NB: the inner `if False` keeps the else branch syntactically inert — it's a placeholder for the upsert path that I'll trim if the create-path alone passes. Simpler alternative: just catch the duplicate-entity error and log; the upsert is a nice-to-have, not required for the test suite to pass.)

Actually, simpler: drop the upsert branch entirely. The test only checks that creation works for fresh entities. Existing entities (from a prior run) keep their existing profile — there's no re-seed. If the LLM re-introduces the same NPC across turns, the dedup (Task B) prevents duplicate proposals; if the NPCProfile is duplicated, that's a deeper issue.

Revised helper — just create, swallow exceptions:

```python
async def seed_npc_profiles_for_accepted_proposals(
    proposals: list[dict[str, Any]],
    *,
    universe_id: UUID | None,
    scene_id: UUID,
    story_id: UUID,
) -> int:
    """For each CHARACTER entity proposal, look up the entity in Neo4j and
    create a minimal NPCProfile. Returns the number seeded. Never raises.
    """
    if not proposals:
        return 0
    from monitor_data.schemas.npc_profiles import NPCProfileCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_npc_profile
    import anyio

    seeded = 0
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        if proposal.get("proposal_type") != "ENTITY":
            continue
        content = proposal.get("content") or {}
        if not isinstance(content, dict):
            continue
        if (content.get("entity_type") or "").upper() != "CHARACTER":
            continue
        name = str(content.get("name") or "").strip()
        if not name:
            continue
        try:
            entity = await _lookup_entity_by_name_and_universe(name, universe_id)
            if not entity:
                continue
            eid = entity.get("id") or entity.get("entity_id")
            if not eid:
                continue
            description = str(content.get("description") or "").strip()
            gm_notes = description[:1000] if description else None
            params = NPCProfileCreate(
                entity_id=UUID(str(eid)),
                universe_id=universe_id,
                traits={},
                values=[],
                fears=[],
                desires=[],
                speech_style=None,
                catchphrases=[],
                mannerisms=[],
                emotional_tendencies=[],
                preferences=[],
                triggers=[],
                secrets=[],
                gm_notes=gm_notes,
                current_emotional_state="neutral",
                relationship_states={},
                relationship_states_by_universe={},
                current_emotional_state_by_universe={},
            )
            await anyio.to_thread.run_sync(mongodb_create_npc_profile, params)
            seeded += 1
        except Exception as exc:
            logger.debug("seed_npc_profiles: failed for %r: %s", name, exc)
    return seeded
```

2. In `canonize_checkpoint` (around line 808), after `ck.evaluate_proposals(...)` and before `clear_scene_runtime_cache(...)`:

```python
    try:
        seeded = await seed_npc_profiles_for_accepted_proposals(
            state.pending_proposals,
            universe_id=state.universe_id,
            scene_id=state.scene_id,
            story_id=state.story_id,
        )
        if seeded:
            logger.debug("canonize_checkpoint: seeded %d NPC profiles", seeded)
    except Exception as exc:
        logger.warning("canonize_checkpoint: NPC profile seeding failed: %s", exc)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/agents/tests/test_canonize_npc_profiles.py packages/agents/tests/test_canonize.py 2>&1 | tail -3`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packages/agents/src/monitor_agents/loops/scene_loop.py packages/agents/tests/test_canonize_npc_profiles.py
git commit -m "feat(scene-loop): seed NPCProfile for new CHARACTER entities at canonize"
```

---

### Task D: Verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Full affected suites**

Run: `uv run pytest packages/agents -q && uv run pytest packages/data-layer -q && uv run pytest packages/ui/backend -q`
Expected: PASS

- [ ] **Step 2: Lint, types, layers**

Run: `uv run ruff check packages && uv run mypy packages/*/src --cache-dir /tmp/mypy-cache && python scripts/check_layer_dependencies.py`
Expected: clean

- [ ] **Step 3: Commit any sweep fixes**

If anything fails or needs adjustment, fix and commit under `chore: ...` (do NOT `git add -A`; add only the files you actually changed for the sweep).

---

### Self-review notes

- All three changes are best-effort: narrator docstring is a hint, partial-match dedup is a heuristic, NPCProfile creation swallows exceptions. The system stays functional even if any single piece regresses.
- Task C is the load-bearing one — it closes the gap. The helper reuses the existing `mongodb_create_npc_profile`; no new tool. The lookup query is one Cypher call per CHARACTER proposal; cheap.
- The upsert path in the original draft of Task C was over-engineered — dropped. If duplicate NPCs become an issue, that's a follow-up.
- Verification: pre-existing tests cover all touched surfaces. New tests are tight and targeted.

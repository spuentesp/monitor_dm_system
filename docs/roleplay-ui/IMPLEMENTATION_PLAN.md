# Roleplay UI — Detailed Implementation Plan

**Date:** 2026-05-30
**Status:** Draft → Ready for Implementation
**Branch:** `feat/roleplay-ui` (create before starting)

---

## What Exists vs. What's Planned

| Component | Status | Location |
|-----------|--------|----------|
| G1 fix: `mongodb_create_memory` → Qdrant embed | ✅ Implemented | `memories.py:89-110` |
| G2 fix: `entity_id` filter in `_fetch_memories` | ✅ Implemented | `context_assembly.py:576-610` |
| `MessageSend.chat_mode` + `character_id` schema field | ✅ Implemented | `chat_schemas.py:10-20` |
| G3: auto-summarization trigger | ❌ Not implemented | — |
| Character CRUD schemas (`CharacterCreate`, etc.) | ❌ Not implemented | — |
| `/api/characters` endpoints | ❌ Not implemented | — |
| OOC/IC routing in `send_message` | ❌ Not implemented | — |
| Frontend components | ❌ Not implemented | — |

---

## Phase 0: G3 — Auto-Summarization Trigger

### Problem
`TokenBudget` and `_summarise_context` exist but no code path checks if assembled context exceeds budget and invokes compression.

### Files to modify
- `packages/agents/src/monitor_agents/context_assembly.py`
- `packages/agents/src/monitor_agents/loops/scene_loop.py`

### Step 0.1 — Add budget check method to `ContextAssembly`

**File:** `context_assembly.py`
**Location:** Add after `_summarise_context` (after line ~1380)

```python
async def check_and_compress_if_needed(
    self,
    assembled_context: Dict[str, Any],
    player_action: str,
) -> Dict[str, Any]:
    """
    G3: If the assembled context exceeds the token budget, compress memories.

    Called from SceneLoop.load_context after assemble() returns.
    Checks context size against available budget and, if exceeded,
    re-summarises memories to fit within summary_budget.

    Returns the context unchanged if within budget.
    """
    context_tokens = count_tokens(json.dumps(assembled_context))
    available = self._token_budget.available_for_context(prompt_tokens=context_tokens)

    # If we have headroom, nothing to do
    if available > 0:
        return assembled_context

    # Compress: re-run _summarise_context on the memories list
    memories = assembled_context.get("memories", [])
    if not memories:
        return assembled_context

    summarised = await self._summarise_context(
        player_action=player_action,
        entities=assembled_context.get("entities", []),
        memories=memories,
        snippets=assembled_context.get("snippets", []),
        profile_context=assembled_context.get("source_profile", ""),
    )

    assembled_context["memories"] = [{"text": summarised, "is_summary": True}]
    assembled_context["_compressed"] = True
    return assembled_context
```

### Step 0.2 — Call the compression check in `SceneLoop.load_context`

**File:** `scene_loop.py`
**Location:** In `load_context` function, after `agent.assemble()` returns (around line 195)

```python
    # G3: Check token budget and compress context if needed
    compressed_context = await agent.check_and_compress_if_needed(
        context, player_action=state.user_input or ""
    )

    return {
        "entity_context": compressed_context.get("entities", []),
        "memory_context": compressed_context.get("memories", []),
        ...
    }
```

### Step 0.3 — Add unit test for G3

**File:** `packages/agents/tests/test_context_assembly.py`
**New test:** `test_check_and_compress_if_needed_truncates_when_over_budget`

```python
async def test_check_and_compress_if_needed_truncates_when_over_budget():
    """When assembled context exceeds token budget, memories are summarised."""
    agent = ContextAssembly()
    large_context = {
        "entities": [],
        "memories": [{"text": "x" * 5000}] * 20,  # oversized
        "snippets": [],
        "source_profile": "",
    }
    result = await agent.check_and_compress_if_needed(
        large_context, player_action="I attack the dragon"
    )
    # Result should have _compressed=True and a single summarised memory
    assert result.get("_compressed") is True
    assert len(result["memories"]) == 1
    assert "is_summary" in result["memories"][0]
```

---

## Phase 1: Character CRUD — Schemas + Backend Endpoints

### Step 1.1 — Add Character schemas

**File:** `packages/ui/backend/src/monitor_ui/routers/entities_schemas.py`
**Change:** Add new classes after existing NPC models (after `PaginatedNPCs`, around line 50)

```python
class CharacterCreate(BaseModel):
    """Create a standalone character (no universe dependency)."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    avatar_url: str | None = Field(default=None)
    personality: str = Field(default="", description="Free-text personality notes")
    gm_notes: str = Field(
        default="",
        description="Author's Note — instructions for the AI, not shown to players",
    )
    first_message: str = Field(default="", description="Opening message when chat starts")
    is_ooc_persona: bool = Field(
        default=False,
        description="If True, this character is a bare AI persona (no memory/world context in OOC mode)",
    )


class CharacterUpdate(BaseModel):
    """Update an existing standalone character."""
    name: str | None = None
    description: str | None = None
    avatar_url: str | None = None
    personality: str | None = None
    gm_notes: str | None = None
    first_message: str | None = None
    is_ooc_persona: bool | None = None


class CharacterDetail(CharacterCreate):
    """Full character response with runtime stats."""
    id: str
    entity_id: str | None = None  # Neo4j entity ID if linked to universe
    memory_count: int = 0
    created_at: str
    updated_at: str


class CharacterImportRequest(BaseModel):
    """Import a universe NPC as a standalone character."""
    source_entity_id: str = Field(..., description="Neo4j entity ID of the NPC to import")
    as_ooc_persona: bool = Field(
        default=False,
        description="If True, import without universe/memory context",
    )
```

### Step 1.2 — Implement character MongoDB storage

Characters are stored in a new MongoDB collection `characters`. They are **not** full Neo4j entities — they live in MongoDB only and optionally reference a Neo4j entity ID if imported from a universe.

**New file:** `packages/ui/backend/src/monitor_ui/routers/character_storage.py`

```python
"""Character persistence helpers — MongoDB-only storage for standalone characters."""

from datetime import datetime, timezone
from uuid import uuid4

from monitor_ui.config import get_settings

_settings = get_settings()


def _coll():
    from monitor_data.db.mongodb import get_mongodb_client
    return get_mongodb_client().get_collection("characters")


def create_character(data: dict) -> dict:
    """Insert a new character document. Returns the created doc."""
    now = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid4()),
        "name": data["name"],
        "description": data.get("description", ""),
        "avatar_url": data.get("avatar_url"),
        "personality": data.get("personality", ""),
        "gm_notes": data.get("gm_notes", ""),
        "first_message": data.get("first_message", ""),
        "is_ooc_persona": data.get("is_ooc_persona", False),
        "entity_id": data.get("entity_id"),  # may be None
        "source_universe_id": data.get("source_universe_id"),
        "memory_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    _coll().insert_one(doc)
    return doc


def get_character(character_id: str) -> dict | None:
    return _coll().find_one({"id": character_id})


def update_character(character_id: str, updates: dict) -> dict | None:
    updates["updated_at"] = datetime.now(timezone.utc)
    result = _coll().find_one_and_update(
        {"id": character_id},
        {"$set": updates},
        return_document=True,
    )
    return result


def delete_character(character_id: str) -> bool:
    result = _coll().delete_one({"id": character_id})
    return result.deleted_count > 0


def list_characters(limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    total = _coll().count_documents({})
    cursor = _coll().find({}).sort("updated_at", -1).skip(offset).limit(limit)
    return list(cursor), total


def increment_memory_count(character_id: str, delta: int = 1) -> None:
    _coll().update_one(
        {"id": character_id},
        {"$inc": {"memory_count": delta}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )
```

### Step 1.3 — Add character CRUD endpoints

**File:** `packages/ui/backend/src/monitor_ui/routers/entities.py`
**Change:** Add new router for `/api/characters`

```python
from .character_storage import (
    create_character,
    get_character,
    update_character,
    delete_character,
    list_characters,
)
from .entities_schemas import (
    CharacterCreate,
    CharacterUpdate,
    CharacterDetail,
    CharacterImportRequest,
)

@router.post("/characters", response_model=CharacterDetail, status_code=201)
async def create_character_endpoint(body: CharacterCreate) -> CharacterDetail:
    """Create a standalone character (stored in MongoDB, no universe required)."""
    doc = create_character(body.model_dump())
    return CharacterDetail(**doc)


@router.get("/characters", response_model=list[CharacterDetail])
async def list_characters_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CharacterDetail]:
    chars, total = list_characters(limit=limit, offset=offset)
    return [CharacterDetail(**c) for c in chars]


@router.get("/characters/{character_id}", response_model=CharacterDetail)
async def get_character_endpoint(character_id: str) -> CharacterDetail:
    doc = get_character(character_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterDetail(**doc)


@router.put("/characters/{character_id}", response_model=CharacterDetail)
async def update_character_endpoint(
    character_id: str,
    body: CharacterUpdate,
) -> CharacterDetail:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    doc = update_character(character_id, updates)
    if not doc:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterDetail(**doc)


@router.delete("/characters/{character_id}", status_code=204)
async def delete_character_endpoint(character_id: str) -> None:
    deleted = delete_character(character_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Character not found")


@router.post("/characters/{character_id}/import-from-universe", response_model=CharacterDetail)
async def import_character_from_universe(
    character_id: str,
    body: CharacterImportRequest,
) -> CharacterDetail:
    """Import an existing universe NPC as a standalone character."""
    # Fetch NPC entity from Neo4j
    from monitor_data.db.neo4j import get_neo4j_client
    client = get_neo4j_client()
    rows = client.execute_read(
        "MATCH (e:EntityInstance {id: $id}) RETURN e",
        {"id": body.source_entity_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="NPC not found in universe")
    entity = rows[0]["e"]

    doc = create_character({
        "name": entity.get("name", "Unknown"),
        "description": entity.get("description", ""),
        "personality": entity.get("properties", {}).get("personality", ""),
        "gm_notes": entity.get("properties", {}).get("gm_notes", ""),
        "is_ooc_persona": body.as_ooc_persona,
        "entity_id": body.source_entity_id,
    })
    return CharacterDetail(**doc)


@router.get("/characters/{character_id}/memories")
async def get_character_memories(
    character_id: str,
    min_importance: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List memories for a character (from MongoDB character_memories collection)."""
    char = get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    entity_id = char.get("entity_id")
    if not entity_id:
        return {"memories": [], "total": 0}

    from monitor_data.tools.mongodb_tools.memories import mongodb_list_memories
    from monitor_data.schemas.memories import MemoryFilter
    result = mongodb_list_memories(MemoryFilter(
        entity_id=uuid.UUID(entity_id),
        min_importance=min_importance,
        limit=limit,
    ))
    return {
        "memories": [
            {"id": str(m.memory_id), "text": m.text, "importance": m.importance,
             "created_at": m.created_at.isoformat()}
            for m in result.memories
        ],
        "total": result.total,
    }


@router.delete("/characters/{character_id}/memories", status_code=204)
async def clear_character_memories(character_id: str) -> None:
    """Delete all memories for a character."""
    char = get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    entity_id = char.get("entity_id")
    if not entity_id:
        return
    from monitor_data.db.mongodb import get_mongodb_client
    get_mongodb_client().get_collection("character_memories").delete_many(
        {"entity_id": entity_id}
    )
```

### Step 1.4 — Unit tests for character CRUD

**New file:** `packages/ui/backend/tests/test_characters.py`

```python
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


def test_create_character():
    ...


def test_list_characters():
    ...


def test_get_character_not_found():
    ...


def test_update_character():
    ...


def test_delete_character():
    ...
```

---

## Phase 2: OOC/IC Routing — Chat Mode Decision

### Step 2.1 — Add `run_ooc_turn` in `chat_loops.py`

**File:** `packages/ui/backend/src/monitor_ui/routers/chat_loops.py`
**Location:** Add after `run_scene_turn` (after line ~1130)

```python
async def run_ooc_turn(
    session_id: str,
    user_content: str,
    character_id: str,
    sessions: dict[str, dict],
    messages: dict[str, list[dict]],
    db_save_session: Any,
) -> tuple[str, dict[str, Any]]:
    """
    OOC turn — bare AI persona with no memory/world context.

    Routing: send_message → chat_mode == "ooc" or is_ooc_persona == True.
    Skips SceneLoop entirely. Uses character card + gm_notes as the prompt.
    No memory is read or written.
    """
    from monitor_ui.routers.character_storage import get_character
    from monitor_ui.routers.chat_support import make_gm_message

    character = get_character(character_id)
    if not character:
        return ("Character not found.", {"type": "error", "chat_mode": "ooc"})

    # Build bare character prompt
    prompt_parts = []
    if character.get("name"):
        prompt_parts.append(f"Name: {character['name']}")
    if character.get("description"):
        prompt_parts.append(f"Description: {character['description']}")
    if character.get("personality"):
        prompt_parts.append(f"Personality: {character['personality']}")
    if character.get("first_message"):
        prompt_parts.append(f"First message: {character['first_message']}")

    gm_notes = character.get("gm_notes", "").strip()
    if gm_notes:
        prompt_parts.append(f"\n[AI Instructions / Author's Note]:\n{gm_notes}")

    character_prompt = "\n\n".join(prompt_parts)

    # Run Narrator in bare mode (no entities, no memories, no game system)
    try:
        from monitor_agents.narrator import Narrator
        narrator = Narrator()
        result = await narrator.narrate_turn(
            scene_id=uuid.uuid4(),  # dummy — not used in OOC mode
            user_input=user_content,
            resolution=None,
            context={
                "entities": [],
                "memories": [],
                "turns": [],
                "source_profile": {},
            },
            game_context={},
            session_tone="dramatic",
            gm_profile={"prompt_override": character_prompt},
        )
        narrative = result.get("narrative_text", "")
    except Exception as exc:
        logger.warning("OOC turn failed: %s", exc)
        narrative = "The character is unavailable right now."

    # Update session tone to indicate OOC
    session = sessions.get(session_id, {})
    session["phase"] = "ooc"
    session["updated_at"] = now_iso()
    db_save_session(session)

    return (
        narrative,
        {
            "type": "character_response",
            "chat_mode": "ooc",
            "character_id": character_id,
            "character_name": character.get("name"),
            "is_ooc_persona": character.get("is_ooc_persona", False),
        },
    )
```

### Step 2.2 — Wire OOC routing in `send_message`

**File:** `packages/ui/backend/src/monitor_ui/routers/chat.py`
**Location:** In `send_message`, before the `else` block that calls `_run_scene_turn` (around line 600)

**Change:** Add after the `is_ooc_question` check and before the scene_end block:

```python
    # === OOC / AI Persona mode (chat_mode == "ooc") ===
    if body.chat_mode == "ooc" and body.character_id:
        narrative, meta = await _run_ooc_turn(
            session_id,
            body.content,
            body.character_id,
            sessions=_SESSIONS,
            messages=_MESSAGES,
            db_save_session=_db_save_session,
        )
        gm_msg = _make_gm_msg(session_id, narrative, meta)
        msgs.append(gm_msg)
        _db_save_message(gm_msg)
        asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
        return Message(**gm_msg)

    # === IC with is_ooc_persona (skip SceneLoop, bare character context) ===
    if body.is_ooc_persona and body.character_id:
        narrative, meta = await _run_ooc_turn(
            session_id,
            body.content,
            body.character_id,
            sessions=_SESSIONS,
            messages=_MESSAGES,
            db_save_session=_db_save_session,
        )
        gm_msg = _make_gm_msg(session_id, narrative, meta)
        msgs.append(gm_msg)
        _db_save_message(gm_msg)
        asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
        return Message(**gm_msg)
```

### Step 2.3 — Add `Message.chat_mode` and `character_id` to response

**File:** `packages/ui/backend/src/monitor_ui/routers/chat_schemas.py`
**Location:** In `Message` class (around line 88)

```python
class Message(BaseModel):
    id: str
    session_id: str
    role: str  # "gm" | "player" | "system"
    content: str
    timestamp: str
    metadata: dict[str, Any] = {}
    chat_mode: str = "ic"  # "ic" | "ooc"
    character_id: str | None = None
```

### Step 2.4 — Add unit test for OOC routing

**New file:** `packages/ui/backend/tests/test_chat_router_ooc.py`

```python
@pytest.mark.asyncio
async def test_send_message_ooc_mode_routes_to_ooc_turn():
    ...


@pytest.mark.asyncio
async def test_send_message_ooc_no_memory_written():
    ...


@pytest.mark.asyncio
async def test_send_message_is_ooc_persona_skips_scene_loop():
    ...
```

---

## Phase 3: Frontend Components

### Step 3.1 — Add `CharacterPanel` component

**File:** `packages/ui/frontend/src/components/play/CharacterPanel.tsx`
**New component.**

Features:
- Left sidebar panel listing all characters (fetched from `/api/characters`)
- Each character shows: avatar, name, short description
- "Create Character" button opens `CharacterEditor` modal
- "Import from Universe" button → picker modal
- Click character to select it for the current chat session
- Selected character highlighted
- OOC/IC mode toggle per character

### Step 3.2 — Add `CharacterEditor` modal

**File:** `packages/ui/frontend/src/components/play/CharacterEditor.tsx`
**New component.**

Fields:
- Name (text input)
- Description (textarea)
- Avatar URL (text input + preview)
- Personality (textarea)
- GM Notes / Author's Note (textarea)
- First Message (textarea)
- "Add to Universe" checkbox + universe selector (if applicable)

### Step 3.3 — Add `ChatModeToggle` component

**File:** `packages/ui/frontend/src/components/play/ChatModeToggle.tsx`
**New component.**

- Toggle button: **IC** / **OOC**
- When IC: green dot, "In-Character" label
- When OOC: amber dot, "Out-of-Character" label
- Emits `onChange(mode: 'ic' | 'ooc')`

### Step 3.4 — Add `MemoryInspector` component

**File:** `packages/ui/frontend/src/components/play/MemoryInspector.tsx`
**New component.**

- Accessible from character "..." context menu
- Lists memories from `/api/characters/{id}/memories`
- Importance filter slider
- Delete individual memory
- "Clear All" with confirmation
- Shows memory text + timestamp + importance score

### Step 3.5 — Wire into `PlayConsole`

**File:** `packages/ui/frontend/src/components/play/PlayConsole.tsx`
**Change:**

- Add `CharacterPanel` to left sidebar
- Add `ChatModeToggle` to header bar
- When character selected + mode = OOC → send `chat_mode: "ooc"` + `character_id` in `MessageSend`
- When character selected + mode = IC → send `character_id` in `MessageSend` (no chat_mode, defaults to IC)

---

## Phase 4: End-to-End Tests

### Step 4.1 — E2E: OOC chat flow

**File:** `tests/e2e/test_roleplay_ooc.py`

```python
@pytest.mark.e2e
async def test_ooc_chat_no_memory():
    """OOC message should not persist memory or trigger SceneLoop."""
    # 1. Create character via API
    # 2. Start session
    # 3. Send OOC message
    # 4. Verify: no scene created, no memory written, character response returned
```

### Step 4.2 — E2E: IC chat with memory persistence

**File:** `tests/e2e/test_roleplay_ic.py`

```python
@pytest.mark.e2e
async def test_ic_chat_persists_memory():
    """IC message with character should trigger memory write + Qdrant embed."""
    # 1. Create character + link to universe
    # 2. Start IC session with character_id
    # 3. Send IC message
    # 4. Verify memory written to MongoDB and Qdrant
    # 5. Send follow-up — verify memory retrieved
```

---

## Implementation Order Summary

| Phase | Task | Files | Test |
|-------|------|-------|------|
| 0 | G3 auto-summarization | `context_assembly.py`, `scene_loop.py` | `test_context_assembly.py` |
| 1 | Character CRUD schemas | `entities_schemas.py` | — |
| 1 | Character storage helper | `character_storage.py` (new) | `test_characters.py` (new) |
| 1 | Character endpoints | `entities.py` | `test_characters.py` |
| 2 | `run_ooc_turn` function | `chat_loops.py` | `test_chat_router_ooc.py` |
| 2 | OOC routing in `send_message` | `chat.py` | `test_chat_router_ooc.py` |
| 2 | `Message.chat_mode` in response | `chat_schemas.py` | — |
| 3 | `CharacterPanel` | `CharacterPanel.tsx` (new) | — |
| 3 | `CharacterEditor` modal | `CharacterEditor.tsx` (new) | — |
| 3 | `ChatModeToggle` | `ChatModeToggle.tsx` (new) | — |
| 3 | `MemoryInspector` | `MemoryInspector.tsx` (new) | — |
| 3 | Wire into `PlayConsole` | `PlayConsole.tsx` | — |
| 4 | E2E OOC test | `test_roleplay_ooc.py` (new) | e2e |
| 4 | E2E IC memory test | `test_roleplay_ic.py` (new) | e2e |

---

## Verification Checklist

Before each phase is considered "done", the following must be true:

| Phase | Check |
|-------|-------|
| 0 | `test_check_and_compress_if_needed_truncates_when_over_budget` passes with `RUN_INTEGRATION=0` |
| 1 | `uv run pytest packages/ui/backend/tests/test_characters.py -q` passes |
| 1 | `GET /api/characters` returns 200; `POST /api/characters` creates and returns `CharacterDetail` |
| 2 | `uv run pytest packages/ui/backend/tests/test_chat_router_ooc.py -q` passes |
| 2 | Sending `chat_mode: "ooc"` + `character_id` returns character response without scene context |
| 3 | PlayConsole renders CharacterPanel + ChatModeToggle; clicking character sets session state |
| 4 | `RUN_E2E=1 pytest tests/e2e/test_roleplay_ooc.py -q` passes |
| 4 | `RUN_E2E=1 pytest tests/e2e/test_roleplay_ic.py -q` passes (memory write + Qdrant retrieve) |

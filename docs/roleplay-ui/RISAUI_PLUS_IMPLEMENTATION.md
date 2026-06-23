# Risuai-Plus: Unified NPC Memory & Roleplay System — Implementation Plan

**Date:** 2026-05-30
**Goal:** Not just "copy Risuai" — build a system where NPCs have persistent memory,
keyword-triggered lorebook, and Author's Note injection that works identically in IC
and OOC modes, with the full MONITOR narration stack available when needed.

---

## Architecture: The Unified NPC Prompt Stack

Every NPC response (OOC or IC) flows through the same **5-layer prompt enrichment**:

```
Layer 1: Character Card     (name, description, personality, role)
Layer 2: Author's Note      (gm_notes — AI instructions, invisible to player)
Layer 3: Lorebook           (keyword-triggered memory entries — dynamic)
Layer 4: Session Memory      (NPC's episodic memories from Qdrant)
Layer 5: Relationship State  (current stance + emotional temperature)
```

The difference between OOC and IC is only **Layers 4-5 scope**:
- **OOC**: Layers 1-3 only → bare AI persona mode
- **IC**: Layers 1-5 → full scene context with memories

---

## What's Implemented vs. What's New

### Implemented (verified working)

| Component | Status | Location |
|-----------|--------|----------|
| G1: memory → Qdrant embed (fire-and-forget) | ✅ | `memories.py:89-110` |
| G2: entity_id filter in `_fetch_memories` | ✅ | `context_assembly.py:576-610` |
| G3: budget-triggered auto-summarization | ✅ | `context_assembly.py:1376` |
| `check_and_compress_if_needed()` called in SceneLoop | ✅ | `scene_loop.py:202` |
| Character CRUD (MongoDB-only, soft-delete) | ✅ | `character_storage.py`, `entities.py` |
| OOC routing (`run_ooc_turn`) | ✅ | `chat_loops.py:1641` |
| OOC routing in `send_message` (chat_mode="ooc") | ✅ | `chat.py:573` |
| Character greeting endpoint (`/greet`) | ✅ | `chat.py:783` |
| Frontend: CharacterPanel, CharacterEditor, ChatModeToggle, MemoryInspector | ✅ | `packages/ui/frontend/src/components/play/` |
| DSPy `NPCDirectVoiceModule` (LIGHT, Predict) | ✅ | `npc_voice.py:161` |
| DSPy `NPCActorModule` (LIGHT, CoT) | ✅ | `npc_voice.py:202` |
| DSPy `NarratorModule` (HEAVY, CoT) | ✅ | `narrator.py:158` |

### Missing: The Real Implementation Gaps

| # | Gap | Severity | Why It Matters |
|---|-----|----------|----------------|
| **M1** | `gm_notes` never reaches any DSPy module | 🔴 Critical | Author's Note is Risuai's core feature — without it, AI doesn't follow character instructions |
| **M2** | `gm_notes` explicitly popped + discarded in NPCVoice | 🔴 Critical | `npc_voice.py:352` has `profile.pop("gm_notes", None)` — dead code actively removing the field |
| **M3** | No Lorebook system (keyword → memory injection) | 🟡 High | Risuai's defining UX: setting keywords auto-injects lore entries into context |
| **M4** | OOC mode has no memory write-back | 🟡 High | OOC conversations leave no trace; can't "remember" what was discussed |
| **M5** | Lorebook UI — no way to create/edit entries per character | 🟡 High | Only raw memory CRUD exists; no keyword/priority fields |
| **M6** | Restart conversation / re-greet not exposed | 🟡 Medium | Greeting is idempotent but no UI to reset it |
| **M7** | `conversation_active` flag not wired to frontend | 🟡 Medium | Conversation mode exists in backend but no frontend toggle |
| **M8** | Emotional state from NPC response not displayed | 🟡 Low | `emotional_state_after` computed but frontend ignores it |

---

## Detailed Implementation: M1 + M2 — Author's Note Injection

### M2 Fix: Remove the gm_notes destruction

**File:** `packages/agents/src/monitor_agents/npc_voice.py`
**Line:** ~352 — `profile.pop("gm_notes", None)` inside `_load_npc_data` or before calling `_direct_module`

```python
# REMOVE THIS LINE (M2 fix):
profile.pop("gm_notes", None)  # ← DELETE THIS — gm_notes should be preserved

# REPLACE WITH: keep gm_notes in profile so it reaches the DSPy module
```

**After removal**, `gm_notes` will flow through `source_profile` into `profile_context` in the `NPCDirectVoiceModule.forward()` call.

### M1-A: Inject gm_notes into `NPCDirectVoiceModule` Signature

**File:** `packages/agents/src/monitor_agents/prompts/npc_voice.py`
**Location:** In `NPCDirectVoiceSignature`, add new input field after `profile_context`:

```python
    # ── Inputs ──────────────────────────────────────────────────────────────
    # ... existing fields ...

    gm_notes: str = dspy.InputField(
        desc=(
            "Author's Note — private instructions for the AI, not shown to the player. "
            "Contains character-specific behavior rules, tone guidance, and constraints. "
            "Must be followed absolutely. Example: 'Never break character. If asked "
            "about the world, deflect. Speak in archaic English.' "
            "Empty string if not set."
        )
    )
```

### M1-B: Update `NPCDirectVoiceModule.forward()` to pass gm_notes

**File:** `packages/agents/src/monitor_agents/prompts/npc_voice.py`
**Location:** After `profile_context` in `NPCDirectVoiceModule.forward()`:

```python
    def forward(
        self,
        # ... existing params ...
        profile_context: str,
        gm_notes: str = "",  # NEW
        player_said: str,
    ) -> dspy.Prediction:
        with dspy_context_for("npc_voice", ModelRole.LIGHT):
            return self.speak(
                # ... existing args ...
                profile_context=profile_context,
                gm_notes=gm_notes,  # NEW
                player_said=player_said,
            )
```

### M1-C: Update `NPCVoice.respond_direct()` to extract and pass gm_notes

**File:** `packages/agents/src/monitor_agents/npc_voice.py`
**Location:** In `respond_direct()`, build `gm_notes` from profile and pass to `_direct_module`:

```python
        # Build gm_notes (Author's Note) from profile — M1 fix
        gm_notes = profile.get("gm_notes", "").strip()

        profile_context = build_npc_profile_context(
            normalize_source_profile(source_profile or {}),
            npc_name=npc_data["name"],
            npc_role=npc_data["role"],
            npc_facts=npc_data.get("facts", []),
        )

        # M1: Pass gm_notes to the DSPy module
        prediction = self._direct_module(
            npc_name=npc_data["name"],
            npc_role=npc_data["role"],
            personality_summary=self._format_personality(profile, relationship_snapshot_before),
            current_emotional_state=self._format_emotional_context(
                profile, relationship_snapshot_before
            ),
            relevant_memories=json.dumps(memories[:5]),
            known_facts=json.dumps(npc_data.get("facts", [])[:8]),
            active_triggers=json.dumps(active_triggers),
            conversation_history=history_text,
            profile_context=profile_context,
            gm_notes=gm_notes,  # NEW — Author's Note injection
            player_said=player_said,
        )
```

### M1-D: Inject gm_notes into `NarratorModule` for IC SceneLoop

**File:** `packages/agents/src/monitor_agents/prompts/narrator.py`
**Location:** Add `gm_notes` to `NarratorSignature` inputs and `NarratorModule.forward()`:

```python
    # In NarratorSignature (add after profile_context):
    gm_notes: str = dspy.InputField(
        desc=(
            "Author's Note — private instructions for the AI narrator. "
            "Contains scene tone guidance, character-specific narration rules, "
            "and GM constraints not shown to players. "
            "Example: 'Keep narration under 3 sentences. Use sensory details. "
            "Never break the fourth wall.' Empty string if not set."
        )
    )
```

**Update `NarratorModule.forward()`:**
```python
    def forward(
        self,
        # ... existing fields ...
        gm_notes: str = "",  # NEW
        role: Optional[ModelRole] = None,
    ) -> dspy.Prediction:
        with dspy_context_for("narrator", role or ModelRole.HEAVY):
            return self.generate(
                # ... existing args ...
                gm_notes=gm_notes,  # NEW
            )
```

### M1-E: Pass gm_notes from SceneLoop → Narrator

**File:** `packages/agents/src/monitor_agents/loops/scene_loop.py`
**Location:** In the `narrate` node function, extract character gm_notes and pass to Narrator:

```python
    # Inside narrate node, around line 220:
    gm_profile = state.gm_profile or {}
    
    # M1: Extract gm_notes from speaker character if available
    speaker_char_id = state.get("speaker_character_id")
    if speaker_char_id and not gm_profile.get("prompt_override"):
        from monitor_ui.routers.character_storage import get_character
        char = get_character(str(speaker_char_id))
        if char:
            notes = char.get("gm_notes", "").strip()
            if notes:
                gm_profile = dict(gm_profile)  # copy to avoid mutation
                gm_profile["prompt_override"] = notes

    result = await narrator.narrate_turn(
        scene_id=state.scene_id,
        user_input=state.user_input,
        resolution=resolution,
        context={
            "entities": entity_context,
            "memories": memory_context,
            "turns": prior_turns,
            "source_profile": gm_profile,
        },
        game_context=state.get("game_system_doc"),
        session_tone=state.session_tone or "dramatic",
        gm_profile=gm_profile,  # Narrator checks gm_profile.gm_notes via _resolve_tone_context
    )
```

**Also**: Update `Narrator._resolve_tone_context` to check for `gm_notes` in `gm_profile`:
```python
    async def _resolve_tone_context(
        self,
        session_tone: str = "dramatic",
        system_name: str = "",
        source_profile: Optional[Dict[str, Any]] = None,
        gm_profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        # M1: Prepend gm_notes as Author's Note prefix if present
        base = await self._tone_resolver.resolve_from_profile(gm_profile, fallback_tone=session_tone)
        
        gm_notes = (gm_profile or {}).get("gm_notes", "").strip()
        if gm_notes:
            base = f"[Author's Note: {gm_notes}]\n{base}"
        
        # ... rest unchanged ...
```

### M1-F: Inject gm_notes into `run_ooc_turn` (already done but refine)

**File:** `packages/ui/backend/src/monitor_ui/routers/chat_loops.py`
**Location:** `run_ooc_turn` already builds `character_prompt` from `gm_notes` — but now also pass it as structured field to Narrator:

```python
    # In run_ooc_turn, after building character_prompt:
    gm_profile = {"prompt_override": character_prompt}
    
    # If gm_notes was in character, also expose as gm_notes for Narrator
    if character.get("gm_notes"):
        gm_profile["gm_notes"] = character["gm_notes"]
```

The current implementation appends `gm_notes` to `prompt_parts` in the character prompt string. Keep that (for the prompt string), but also pass `gm_notes` separately so Narrator can use it as a structured field.

---

## Detailed Implementation: M3 — Lorebook System

### M3-A: Lorebook Schema

**File:** `packages/data-layer/src/monitor_data/schemas/`
**New file:** `lorebook.py`

```python
"""Lorebook entries — keyword-triggered memory injections for characters."""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, Field


class LorebookEntry(BaseModel):
    """A single lorebook entry for a character (or universe)."""
    id: str
    character_id: str  # Which character this belongs to (or "universe:<id>")
    keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Trigger phrases. When ANY keyword appears in user input, "
            "this entry's content is injected into context. Case-insensitive. "
            "Example: ['dragon', 'wyrm', 'hoard']"
        ),
    )
    content: str = Field(
        ...,
        min_length=1,
        description="The memory/lore content injected when a keyword matches.",
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=100,
        description=(
            "Higher priority entries are injected first. "
            "Tie-break: order of creation. Use 1-3 for essential world facts, "
            "0 for optional flavor."
        ),
    )
    is_active: bool = Field(default=True)
    created_at: str


class LorebookEntryCreate(BaseModel):
    keywords: list[str]
    content: str
    priority: int = 0
    is_active: bool = True


class LorebookEntryUpdate(BaseModel):
    keywords: list[str] | None = None
    content: str | None = None
    priority: int | None = None
    is_active: bool | None = None
```

### M3-B: Lorebook MongoDB Operations

**File:** `packages/data-layer/src/monitor_data/tools/mongodb_tools/`
**New file:** `lorebook_tools.py`

```python
"""MongoDB CRUD for character lorebook entries."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.lorebook import LorebookEntry, LorebookEntryCreate


def _coll() -> Any:
    return get_mongodb_client().get_collection("lorebook_entries")


def create_lorebook_entry(
    character_id: str,
    data: LorebookEntryCreate,
) -> LorebookEntry:
    """Insert a lorebook entry. Generates keywords from content if none provided."""
    now = datetime.now(timezone.utc)
    keywords = data.keywords

    # Auto-generate keywords from content if none provided (first 5 nouns)
    if not keywords and data.content:
        words = [w for w in re.findall(r'\b[A-Z][a-z]+\b', data.content)][:5]
        keywords = [w.lower() for w in words]

    doc = {
        "id": str(uuid4()),
        "character_id": character_id,
        "keywords": keywords,
        "content": data.content,
        "priority": data.priority,
        "is_active": data.is_active,
        "created_at": now.isoformat(),
    }
    _coll().insert_one(doc)
    return LorebookEntry(**doc)


def get_lorebook_entries(character_id: str) -> list[LorebookEntry]:
    """List all active lorebook entries for a character, sorted by priority desc."""
    cursor = _coll().find(
        {"character_id": character_id, "is_active": True}
    ).sort("priority", -1)
    return [LorebookEntry(**d) for d in cursor]


def update_lorebook_entry(entry_id: str, updates: dict) -> LorebookEntry | None:
    result = _coll().find_one_and_update(
        {"id": entry_id},
        {"$set": {**updates, "updated_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True,
    )
    return LorebookEntry(**result) if result else None


def delete_lorebook_entry(entry_id: str) -> bool:
    result = _coll().delete_one({"id": entry_id})
    return result.deleted_count > 0


def inject_lorebook_entries(
    character_id: str,
    text: str,
) -> list[str]:
    """
    Scan `text` against all active lorebook entries for `character_id`.
    Returns list of matched entry contents, deduplicated, ordered by priority.

    Case-insensitive keyword matching. Supports phrase keywords (multi-word).
    """
    entries = get_lorebook_entries(character_id)
    matched: list[tuple[int, str]] = []  # (priority, content)
    text_lower = text.lower()

    for entry in entries:
        for kw in entry.keywords:
            if kw.lower() in text_lower:
                matched.append((entry.priority, entry.content))
                break  # Only match each entry once

    matched.sort(key=lambda x: (-x[0],))
    # Deduplicate while preserving order
    seen_content: set[str] = set()
    results: list[str] = []
    for _, content in matched:
        if content not in seen_content:
            seen_content.add(content)
            results.append(content)
    return results
```

### M3-C: Wire Lorebook into `NPCVoice.respond_direct()` (IC mode)

**File:** `packages/agents/src/monitor_agents/npc_voice.py`
**Location:** In `respond_direct()`, after `_recall_memories()` and before calling `_direct_module`:

```python
        # 2. Recall NPC's memories of the player from Qdrant
        memories = await self._recall_memories(npc_id, player_said)

        # 2b. M3: Lorebook injection — check keywords against player input
        try:
            from monitor_data.tools.mongodb_tools.lorebook_tools import inject_lorebook_entries
            lore_entries = inject_lorebook_entries(str(npc_id), player_said)
        except Exception:  # noqa: BLE001
            lore_entries = []

        # Append lorebook content to memory context
        if lore_entries:
            memories = memories + [{"text": entry, "is_lorebook": True} for entry in lore_entries]
```

### M3-D: Wire Lorebook into `run_ooc_turn` (OOC mode)

**File:** `packages/ui/backend/src/monitor_ui/routers/chat_loops.py`
**Location:** In `run_ooc_turn()`, after getting character and before building prompt:

```python
    # M3: Lorebook injection for OOC mode
    lore_entries: list[str] = []
    try:
        from monitor_data.tools.mongodb_tools.lorebook_tools import inject_lorebook_entries
        lore_entries = inject_lorebook_entries(character_id, user_content)
    except Exception:  # noqa: BLE001
        pass

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

    # M3: Inject lorebook entries into context
    if lore_entries:
        prompt_parts.append(f"\n[Lorebook — injected because your input matched keywords]:\n")
        for entry in lore_entries:
            prompt_parts.append(f"- {entry}")

    gm_notes = character.get("gm_notes", "").strip()
    if gm_notes:
        prompt_parts.append(f"\n[AI Instructions / Author's Note]:\n{gm_notes}")

    character_prompt = "\n\n".join(prompt_parts)
```

### M3-E: Lorebook REST Endpoints

**File:** `packages/ui/backend/src/monitor_ui/routers/entities.py`
**Location:** After character endpoints (~line 1160):

```python
from monitor_data.schemas.lorebook import LorebookEntryCreate, LorebookEntryUpdate
from monitor_data.tools.mongodb_tools.lorebook_tools import (
    create_lorebook_entry,
    get_lorebook_entries,
    update_lorebook_entry,
    delete_lorebook_entry,
)


@router.get("/characters/{character_id}/lorebook", response_model=list[LorebookEntry])
async def list_lorebook_entries(character_id: str) -> list[LorebookEntry]:
    """List all lorebook entries for a character."""
    return get_lorebook_entries(character_id)


@router.post("/characters/{character_id}/lorebook", response_model=LorebookEntry, status_code=201)
async def create_lorebook_entry_endpoint(
    character_id: str,
    body: LorebookEntryCreate,
) -> LorebookEntry:
    """Create a lorebook entry for a character."""
    # Verify character exists
    char = get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    return create_lorebook_entry(character_id, body)


@router.put("/characters/{character_id}/lorebook/{entry_id}", response_model=LorebookEntry)
async def update_lorebook_entry_endpoint(
    character_id: str,
    entry_id: str,
    body: LorebookEntryUpdate,
) -> LorebookEntry:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = update_lorebook_entry(entry_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Lorebook entry not found")
    return result


@router.delete("/characters/{character_id}/lorebook/{entry_id}", status_code=204)
async def delete_lorebook_entry_endpoint(character_id: str, entry_id: str) -> None:
    deleted = delete_lorebook_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lorebook entry not found")
```

### M3-F: Lorebook Frontend — Editor Component

**File:** `packages/ui/frontend/src/components/play/LorebookEditor.tsx`
**New component** (~150 lines).

Features:
- Shown inside `CharacterEditor` as a tab/section
- List of lorebook entries for selected character (fetched from `/characters/{id}/lorebook`)
- Each entry: keywords (comma-separated), content (textarea), priority slider, active toggle
- "Add Entry" button → inline form
- Auto-generate keywords button (extracts keywords from content using common NLP or regex)
- Delete entry with confirmation
-实时 preview: "Type something to test keyword matches" text input

---

## Detailed Implementation: M4 — OOC Memory Write-Back

### Decision: OOC memories should be written but with lower importance

In Risuai, OOC conversations typically don't persist memories (pure persona mode). However, MONITOR's design allows opt-in memory persistence. Add a toggle:

**Add to `CharacterCreate` / `CharacterUpdate` schema:**
```python
    persist_ooc_memories: bool = Field(
        default=False,
        description="If True, OOC conversations with this character are remembered",
    )
```

**In `run_ooc_turn`, after getting the narrative response:**

```python
    # M4: Optional OOC memory write-back
    character = get_character(character_id)
    if character.get("persist_ooc_memories", False):
        try:
            from monitor_data.tools.mongodb_tools import mongodb_create_memory
            from monitor_data.schemas.memories import MemoryCreate
            memory_req = MemoryCreate(
                entity_id=uuid.UUID(character.get("entity_id", uuid.uuid4())),
                story_id=uuid.uuid4(),  # OOC sessions may not have story_id
                scene_id=uuid.uuid4(),
                text=f"OOC conversation: {user_content} → {narrative[:200]}",
                memory_type="episodic",
                importance=0.3,  # Lower importance for OOC memories
                metadata={"ooc": True, "character_id": character_id},
            )
            mongodb_create_memory(memory_req)
        except Exception:  # noqa: BLE001
            pass  # Fire-and-forget
```

---

## Detailed Implementation: M6 — Restart Conversation / Re-greet

### M6: Add `POST /{session_id}/conversation/restart` endpoint

**File:** `packages/ui/backend/src/monitor_ui/routers/chat.py`
**Location:** After `greet_character` (~line 810):

```python
@router.post("/{session_id}/conversation/restart", response_model=Message)
async def restart_conversation(session_id: str, character_id: str) -> Message:
    """
    M6: Clear the conversation history and re-send the character's first_message.
    
    Use when the player wants to "start fresh" with a character without
    creating a new session.
    """
    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Clear all 'character' role messages for this character in this session
    msgs = _MESSAGES.get(session_id, [])
    character_msg_ids = [
        m["id"] for m in msgs
        if m.get("role") == "character"
        and m.get("metadata", {}).get("character_id") == character_id
    ]
    
    # Remove character messages from in-memory store
    _MESSAGES[session_id] = [m for m in msgs if m["id"] not in character_msg_ids]
    
    # Delete from DB
    try:
        from monitor_data.db.mongodb import get_mongodb_client
        mdb = get_mongodb_client()
        mdb.get_collection("chat_messages").delete_many({
            "session_id": session_id,
            "role": "character",
            "metadata.character_id": character_id,
        })
    except Exception:  # noqa: BLE001
        pass

    # Re-fire greet (will create a new first_message)
    return await greet_character(session_id, character_id)
```

---

## Testing Plan

### Unit Tests

| Test | File | What it verifies |
|------|------|-----------------|
| `test_gm_notes_reaches_direct_module` | `test_npc_voice.py` | `gm_notes` flows from profile → DSPy module |
| `test_gm_notes_in_narrator_signature` | `test_narrator.py` | `gm_notes` field in NarratorModule |
| `test_lorebook_keyword_injection` | `test_lorebook.py` (new) | `inject_lorebook_entries()` matches keywords |
| `test_lorebook_deduplication_by_priority` | `test_lorebook.py` (new) | Priority ordering + dedup |
| `test_ooc_turn_injects_lorebook` | `test_chat_router_ooc.py` | OOC path calls `inject_lorebook_entries` |
| `test_ooc_memory_write_when_enabled` | `test_chat_router_ooc.py` | `persist_ooc_memories=True` triggers `mongodb_create_memory` |
| `test_restart_conversation_clears_history` | `test_session_api.py` | Restart endpoint deletes character messages |

### Integration Tests

| Test | File | What it verifies |
|------|------|-----------------|
| `test_ic_chat_with_gm_notes_in_prose` | `test_npc_voice.py` | Full turn with `gm_notes` set produces compliant NPC voice |
| `test_lorebook_auto_generates_keywords` | `test_lorebook.py` | Creating entry with no keywords auto-generates from content |
| `test_restart_conversation_re_greets` | `test_session_api.py` | `/conversation/restart` → new first_message created |

### E2E Tests

| Test | File | What it verifies |
|------|------|-----------------|
| `test_full_ roleplay_flow_with_lorebook` | `tests/e2e/test_roleplay_ic.py` | Character + lorebook entries + IC chat → lorebook injected |
| `test_ooc_remembers_when_persist_enabled` | `tests/e2e/test_roleplay_ooc.py` | OOC with `persist_ooc_memories=True` → memory written |

---

## Implementation Order

| Order | Change | Files | Reason |
|-------|--------|-------|--------|
| 1 | **M2**: Remove `profile.pop("gm_notes")` | `npc_voice.py:352` | Unblocks everything else |
| 2 | **M1-A/B/C**: `gm_notes` in DSPy signatures + pass through | `npc_voice.py`, `npc_voice.py:prompts`, `narrator.py` | Core Author's Note feature |
| 3 | **M1-D/E**: Inject into SceneLoop → Narrator path | `scene_loop.py`, `narrator.py` | Full narration gets Author's Note |
| 4 | **M1-F**: Refine `run_ooc_turn` gm_notes handling | `chat_loops.py` | OOC mode already works, refine it |
| 5 | **M3-A/B**: Lorebook schema + MongoDB ops | `schemas/lorebook.py`, `lorebook_tools.py` | Foundation for M3 |
| 6 | **M3-C/D**: Wire lorebook into NPCVoice + run_ooc_turn | `npc_voice.py`, `chat_loops.py` | Both modes get keyword triggers |
| 7 | **M3-E**: Lorebook REST endpoints | `entities.py` | API for lorebook management |
| 8 | **M3-F**: LorebookEditor frontend | `LorebookEditor.tsx` (new) | User-facing lorebook creation |
| 9 | **M4**: OOC memory write-back toggle | `entities_schemas.py`, `run_ooc_turn` | Opt-in persistence |
| 10 | **M6**: Restart conversation endpoint | `chat.py` | Re-greet functionality |

---

## Verification Checklist

| Phase | Done? | How to verify |
|-------|-------|---------------|
| M2 | ☐ | `grep -n "gm_notes.*pop" npc_voice.py` → no results |
| M1 | ☐ | Unit test: `test_gm_notes_reaches_direct_module` passes |
| M1 (Narrator) | ☐ | Unit test: `test_gm_notes_in_narrator_signature` passes |
| M3 lorebook | ☐ | `test_lorebook_keyword_injection` passes |
| M3 inject (NPC) | ☐ | IC turn with keyword → lore entry in memories list |
| M3 inject (OOC) | ☐ | OOC turn with keyword → lore entry in prompt |
| M4 OOC memory | ☐ | Character with `persist_ooc_memories=True` → memory written after OOC turn |
| M6 restart | ☐ | `POST /{sid}/conversation/restart?character_id=X` → new first_message |
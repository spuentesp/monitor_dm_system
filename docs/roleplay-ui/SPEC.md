# Roleplay UI — Implementation Spec

**Date:** 2026-05-30
**Status:** Draft

---

## 1. Problem Statement

Three infrastructure gaps block a working Risuai-style roleplay use case:

| Gap | Severity | Location |
|-----|----------|----------|
| **G1:** `mongodb_create_memory` does not trigger Qdrant embedding — memories written to MongoDB never get vectorized | Critical | `memories.py` |
| **G2:** `ContextAssembly._fetch_memories` has no `entity_id` filter — all characters' memories returned undifferentiated | High | `context_assembly.py` |
| **G3:** No budget-triggered auto-summarization — `TokenBudget` exists but nothing invokes compression when context fills | Medium | `token_budget.py`, `context_assembly.py` |

Plus a new frontend is needed for character curation and roleplay chat with OOC/IC modes.

---

## 2. Architecture Overview

### Two Chat Modes

| Mode | Context | Memory | World |
|------|---------|--------|-------|
| **IC (In-Character)** | Full: scene entities, NPC memories, world facts, lore | Enabled — NPC memories retrieved per-turn via `qdrant_search_memories` | Enabled — full context assembly |
| **OOC (Out-of-Character)** | Minimal: character card only | Disabled — AI persona mode, no memory persistence | Disabled |

OOC mode is treated like a bare AI persona (no lorebook, no memory, no world context) — just a character definition prompt.

### Character Types

| Type | Source | Importable? |
|------|--------|-------------|
| **Universe Character** | Created within a Universe (owns NPC in Neo4j + profile in MongoDB) | Yes — import copies into standalone |
| **Standalone Character** | Created independently, no universe | Yes — can be added to a universe |

---

## 3. Infrastructure Fixes

### G1: Wire `mongodb_create_memory` → Qdrant embedding

**Problem:** `mongodb_create_memory` writes to MongoDB but does not trigger embedding.

**Fix:** After successful MongoDB insert in `memories.py`, call `qdrant_embed_memory` synchronously (or via fire-and-forget async task).

**File:** `packages/data-layer/src/monitor_data/tools/mongodb_tools/memories.py`

```python
# At end of mongodb_create_memory(), after insert_one:
# Fire-and-forget Qdrant embedding (idempotent — safe to fail silently)
try:
    from monitor_data.tools.qdrant_tools import qdrant_embed_memory, MemoryEmbedRequest
    embed_req = MemoryEmbedRequest(
        memory_id=memory_id,
        text=params.text,
        metadata={
            "entity_id": str(params.entity_id),
            "story_id": str(params.story_id) if params.story_id else None,
            "scene_id": str(params.scene_id) if params.scene_id else None,
            "importance": params.importance,
        },
    )
    # Run sync in thread pool — MongoDB write is already complete
    import threading
    thread = threading.Thread(target=qdrant_embed_memory, args=(embed_req,))
    thread.start()
except Exception:
    pass  # Don't fail the memory write if embedding fails
```

**Alternative (cleaner):** Add `qdrant_embed_memory` as a step in the same MongoDB transaction or emit an event that the Indexer consumes.

### G2: Add `entity_id` filter to `ContextAssembly._fetch_memories`

**Problem:** `_fetch_memories` only filters by `story_id`, returning all characters' memories.

**Fix:** Accept optional `entity_id` parameter. When present, add to Qdrant filter.

**File:** `packages/agents/src/monitor_agents/context_assembly.py`

```python
async def _fetch_memories(
    self, scene_id: UUID, story_id: UUID, query: str,
    entity_id: UUID | None = None,  # NEW
) -> List[Dict[str, Any]]:
    """Search character memories from Qdrant."""
    if not query:
        return []
    # ...
    filter_dict: Dict[str, Any] = {"story_id": str(story_id)}
    if entity_id:
        filter_dict["entity_id"] = str(entity_id)  # NEW

    raw = await self.call_tool(
        "qdrant_search",  # NOTE: uses generic qdrant_search, which supports arbitrary filter
        {
            "collection": "memories",
            "query_text": query,
            "limit": 10,
            "filter": filter_dict,
        },
    )
    # ...
```

**Also update:** `assemble()` to accept `entity_id` and pass it to `_fetch_memories`.

### G3: Auto-summarization trigger

**Problem:** `TokenBudget` and `_summarise_context` exist but nothing triggers compression when context fills.

**Fix:** In `SceneLoop` `load_context` node (or in `ContextAssembly.assemble()`), check if assembled context exceeds budget. If so, invoke an LLM summarizer to condense older memories before proceeding.

**File:** `packages/agents/src/monitor_agents/context_assembly.py` (new method) + `packages/agents/src/monitor_agents/loops/scene_loop.py`

```python
# In ContextAssembly:
async def check_and_summarise_context(
    self,
    context: Dict[str, Any],
    player_action: str,
    budget: TokenBudget,
) -> Dict[str, Any]:
    """
    If assembled context exceeds token budget, invoke LLM summarization
    over the memories list to compress them before the turn proceeds.
    
    Triggered by: SceneLoop.load_context node.
    """
    context_tokens = count_tokens(json.dumps(context))
    available = budget.available_for_context(prompt_tokens=context_tokens)
    
    if available > 0:
        return context  # No compression needed
    
    # Invoke summarization — compress memories to summary_budget tokens
    summarised = await self._summarise_context(
        player_action=player_action,
        entities=context.get("entities", []),
        memories=context.get("memories", []),
        snippets=context.get("snippets", []),
        profile_context=context.get("source_profile", ""),
    )
    context["memories"] = [{"text": summarised, "is_summary": True}]
    context["_compressed"] = True
    return context
```

**SceneLoop** calls this in `load_context` after `ContextAssembly.assemble()` returns.

---

## 4. Backend API Additions

### New Schemas

**File:** `packages/ui/backend/src/monitor_ui/routers/chat_schemas.py`

```python
class MessageSend(BaseModel):
    content: str
    chat_mode: str = "ic"  # "ic" | "ooc"
    character_id: str | None = None  # Which character to chat as (for OOC/IC)

class Message(BaseModel):
    id: str
    session_id: str
    role: str  # "gm" | "player" | "character"
    content: str
    timestamp: str
    metadata: dict[str, Any] = {}
    chat_mode: str = "ic"  # "ic" | "ooc"
    character_id: str | None = None
```

**File:** `packages/ui/backend/src/monitor_ui/routers/entities_schemas.py`

```python
class CharacterCreate(BaseModel):
    name: str
    description: str = ""
    avatar_url: str | None = None
    personality: str = ""  # Free-text personality notes
    gm_notes: str = ""  # Author's note / instructions for the AI
    first_message: str = ""  # Opening message when chat starts
    is_ooc_persona: bool = False  # If True, disable memory/world context
    universe_id: str | None = None  # If set, create inside this universe

class CharacterImport(BaseModel):
    character_id: str  # Existing NPC/character ID to import
    target_universe_id: str | None = None  # Optional universe to import into
    as_standalone: bool = True  # Create as standalone (no universe dependency)
```

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/characters` | Create standalone character |
| `GET` | `/api/characters` | List all standalone characters |
| `GET` | `/api/characters/{id}` | Get character detail |
| `PUT` | `/api/characters/{id}` | Update character |
| `DELETE` | `/api/characters/{id}` | Delete character |
| `POST` | `/api/characters/{id}/import` | Import universe character → standalone |
| `POST` | `/api/characters/{id}/add-to-universe` | Add standalone character to universe |
| `GET` | `/api/characters/{id}/memories` | Get character's memories |
| `DELETE` | `/api/characters/{id}/memories` | Clear character's memories |

### OOC vs IC Chat Routing

**File:** `packages/ui/backend/src/monitor_ui/routers/chat.py` (or `chat_loops.py`)

When `MessageSend.chat_mode == "ooc"` or `MessageSend.character_id` has `is_ooc_persona=True`:

1. Skip `SceneLoop` — route directly to **Narrator** with minimal prompt
2. Disable memory retrieval (`_fetch_memories` returns `[]`)
3. Disable entity context (`_fetch_entities` returns `[]`)
4. Build a bare character-prompt: `{character.description}\n\n{character.gm_notes}`
5. No memory write after the turn

When `chat_mode == "ic"`:

1. Full `SceneLoop` with all context assembly
2. `character_id` is the speaker NPC for this turn
3. Memory writes target `character_id` as `entity_id`

---

## 5. Frontend: Play Console Updates

### New Components

```
packages/ui/frontend/src/
├── app/play/page.tsx              — Existing, extend
├── components/
│   ├── play/
│   │   ├── PlayConsole.tsx        — Existing, extend
│   │   ├── CharacterPanel.tsx     — NEW: character list + selector
│   │   ├── CharacterEditor.tsx    — NEW: create/edit character modal
│   │   ├── ChatModeToggle.tsx     — NEW: OOC / IC toggle
│   │   └── MemoryInspector.tsx    — NEW: view/clear character memories
```

### CharacterPanel

- Left sidebar listing all standalone characters + characters in current universe
- Click to select which character the player is "chatting as"
- Create new (standalone) character button
- Import from universe button
- Character avatar, name, short description preview

### ChatModeToggle

- Toggle button: **IC** (in-character) / **OOC** (out-of-character)
- When OOC: yellow/amber indicator, no memory icon shown in messages
- When IC: green indicator, memory icon shown

### CharacterEditor Modal

- Name, description (textarea), avatar URL
- Personality notes (textarea)
- GM Notes / Author's Note (textarea) — this is Risuai's "Author's Note" equivalent
- First Message (textarea)
- Universe selector (if adding to a universe)
- Save / Cancel

### MemoryInspector

- Accessible from character context menu (right-click or "..." button)
- Shows list of memories for selected character
- Importance filter slider
- Delete individual memories
- "Clear All" button with confirmation

---

## 6. Implementation Order

### Phase 1: Infrastructure Fixes (Layer 1, Layer 2)
1. Fix G1: Wire `mongodb_create_memory` → `qdrant_embed_memory` (critical, unblocks everything)
2. Fix G2: Add `entity_id` filter to `_fetch_memories` (high, fixes memory cross-talk)
3. Fix G3: Auto-summarization trigger in `SceneLoop.load_context` (medium)

### Phase 2: Backend API (Layer 3)
4. Add character CRUD schemas and endpoints (`/api/characters`)
5. Add OOC/IC routing in chat endpoint
6. Wire character → NPC profile → Neo4j entity creation

### Phase 3: Frontend UI (Layer 3 continued)
7. `CharacterPanel` component (character list + selection)
8. `CharacterEditor` modal (create/edit)
9. `ChatModeToggle` component
10. `MemoryInspector` component
11. Extend `PlayConsole` to wire all components together

---

## 7. Key Files to Modify

| File | Change |
|------|--------|
| `packages/data-layer/src/monitor_data/tools/mongodb_tools/memories.py` | G1: add Qdrant embed after MongoDB insert |
| `packages/agents/src/monitor_agents/context_assembly.py` | G2: add entity_id filter; G3: add summarization trigger |
| `packages/agents/src/monitor_agents/loops/scene_loop.py` | G3: call summarization check after load_context |
| `packages/ui/backend/src/monitor_ui/routers/chat_schemas.py` | Add `chat_mode`, `character_id` to `MessageSend` |
| `packages/ui/backend/src/monitor_ui/routers/entities_schemas.py` | Add `CharacterCreate`, `CharacterImport`, `CharacterDetail` |
| `packages/ui/backend/src/monitor_ui/routers/entities.py` | Add character CRUD endpoints |
| `packages/ui/backend/src/monitor_ui/routers/chat.py` | OOC/IC routing decision |
| `packages/ui/frontend/src/components/play/PlayConsole.tsx` | Integrate new components |
| `packages/ui/frontend/src/components/play/CharacterPanel.tsx` | NEW |
| `packages/ui/frontend/src/components/play/CharacterEditor.tsx` | NEW |
| `packages/ui/frontend/src/components/play/ChatModeToggle.tsx` | NEW |
| `packages/ui/frontend/src/components/play/MemoryInspector.tsx` | NEW |
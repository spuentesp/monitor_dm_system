## Phase B — Immersive GM Craft (2 weeks)

> **Delivers:** Session opening that feels like a real GM. Narrator with persona. OOC handling.

### B.1 Session Phase State Machine

**Why:** The system has no concept of session phase. Every message routes through the full SceneLoop, even before the player has a character.

| Task | File(s) | Details |
|------|---------|---------|
| Session phases | `packages/ui/backend/src/monitor_ui/routers/chat.py` | Add `phase` to session document: `"awaiting_character" \| "char_creation" \| "active_play" \| "ooc" \| "scene_end"` |
| Phase-aware routing | `chat.py` — `send_message()` | Implement routing per GM_CRAFT UC-GM-9: `awaiting_character` → character definition handler, `char_creation` → creation handler, `ooc` → OOC handler, `active_play` → SceneLoop |
| OOC intent detection | `chat.py` or `chat_support.py` | Simple DSPy classifier: is this message in-character or out-of-character? Regex pre-filter for "how does", "what is", "can you explain", "OOC:" |
| OOC handler | `chat_support.py` | `_handle_ooc_question(session, msg)` — query game system schema for rules questions, entity archetypes for "what can I play", produce natural-language answer without rolling dice |

**Routing logic:**
```python
if session.phase == "awaiting_character":
    return _handle_character_definition(session, msg)
elif session.phase == "char_creation":
    return _handle_char_creation_response(session, msg)
elif _is_ooc(msg):
    return _handle_ooc(session, msg)
else:
    return _run_scene_turn(session, msg)
```

**Success criteria:**
- [ ] New sessions start in `awaiting_character` phase
- [ ] OOC questions ("what can I play?", "how does combat work?") get answered without dice rolls
- [ ] Phase transitions are persisted in session document
- [ ] No `"MONITOR could not start the live GM loop"` errors during pre-play

### B.2 Immersive Session Opening

**Why:** Currently opens with metadata or form-like questions. Must feel like a GM painting a scene.

| Task | File(s) | Details |
|------|---------|---------|
| Diegetic opening generator | `narrator.py` or new `opening.py` | DSPy signature that takes: tone, axioms, entities (locations), lore facts → produces one evocative paragraph + single question. No metadata. No system labels |
| Rich opening hook | `chat.py` — `_fetch_opening_hook()` | Expand beyond Axioms: also query `LoreFact` nodes and `Entity[type=location]` nodes. Pass all to diegetic generator |
| Tone-aware opening questions | `narrator.py` | Per GM_CRAFT UC-GM-3: generate ONE question matched to tone. Dramatic→"What do you want from tonight?", Grim→"What broke?", Heroic→"What did you do?", Sandbox→"Why are you here?" |
| Consent-before-roll | `chat.py` — `_maybe_do_char_creation()` | Per GM_CRAFT UC-GM-1: GM OFFERS to roll attributes, describes method, waits for player confirmation. No auto-roll on session start |

**Success criteria:**
- [ ] Opening message contains zero metadata (no mode/tone/system labels)
- [ ] Opening uses lore facts and location descriptions, not just axioms
- [ ] Exactly one question posed to player
- [ ] Character stats offered, not auto-generated

### B.3 Narrator Dynamic Length & Adaptive Pressure

**Why:** `NarratorSignature` says "2-4 paragraphs" for everything. A GM reaction to "I open the door" should not be 4 paragraphs.

| Task | File(s) | Details |
|------|---------|---------|
| Dynamic length control | `prompts/narrator.py` | Replace static "2-4 paragraphs" with computed guidance: action intensity → response length. Trivial: 1-2 sentences. Standard: 1 paragraph. Climactic: 2-3 paragraphs. |
| Narrative pressure gauge | `narrator.py` | Track `narrative_pressure: float` in turn context. Rising when tension increases, falling after resolution. High pressure → shorter, punchier prose. Low pressure → descriptive, atmospheric |
| Session-aware narration | `narrator.py` | First turn of session: scene-setting, atmospheric. Mid-session: action-focused. Session closing: reflective, summarizing. Use `turns_count` and `tension_score` from StoryState |

**Success criteria:**
- [ ] Trivial actions get 1-2 sentence responses
- [ ] Climactic moments get multi-paragraph treatment
- [ ] Opening turn is atmospheric and scene-setting
- [ ] No verbose prose for simple player actions

### B.4 Context Assembly Improvements

**Why:** ContextAssembly loads all relevant data but has no temporal awareness, deduplication, or token budgeting.

| Task | File(s) | Details |
|------|---------|---------|
| Temporal relevance decay | `context_assembly.py` | Weight memories and turns by recency. Recent turns: full weight. 5+ turns ago: 0.5 weight. 10+ turns: 0.2 weight. 20+ turns: summary only. Add `recency_weight` to context scoring |
| Entity deduplication | `context_assembly.py` | Merge duplicate entity references from Neo4j + Qdrant + MongoDB. Same entity from multiple sources → single deduplicated entry with merged attributes |
| Token budget awareness | `context_assembly.py` | Calculate token count of assembled context. If over budget (e.g., 4000 tokens for context), prioritize: (1) current scene entities, (2) recent turns, (3) relevant memories, (4) distant memories. Truncate low-priority items |
| Context relevance scoring | `context_assembly.py` | Score each context item against user_input using embedding similarity. Keep top-N by score within token budget |

**Success criteria:**
- [ ] Recent turns have higher weight in context
- [ ] No duplicate entity entries from multiple sources
- [ ] Context stays within token budget for long sessions (50+ turns)
- [ ] Low-relevance memories are deprioritized

---


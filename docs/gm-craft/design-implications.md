## 5. System Design Implications

### 5.1 Session phase field

```python
# chat.py Session model
class Session(BaseModel):
    ...
    phase: str = "awaiting_character"
    # "awaiting_character" | "char_creation" | "active_play" | "scene_end"
```

```python
# create_session — play modes
session["phase"] = "active_play" if body.character_id else "awaiting_character"
```

### 5.2 Pre-play message routing (send_message)

```python
if session.get("mode") == "world_architect":
    narrative, meta = await _run_world_architect_turn(...)
elif session.get("phase") in ("awaiting_character", "char_creation"):
    narrative, meta = await _run_preplay_turn(session_id, body.content)
else:
    narrative, meta = await _run_scene_turn(session_id, body.content)
```

### 5.3 NarratorSignature tone field

```python
class NarratorSignature(dspy.Signature):
    tone_context: str = dspy.InputField(
        desc=(
            "GM persona guidance for this session. Set the narrative voice, "
            "sentence rhythm, and emotional register. Example: "
            "'Terse, industrial, cosmic-dread. Short sentences. Second-person present. "
            "Death is ordinary. The void is patient.'"
        )
    )
    # (existing fields unchanged)
```

### 5.4 Resolver roll proposal model

```python
# Three resolution branches in resolve_turn:
# 1. trivial → success, no roll
# 2. propose_roll → return resolution_type="propose_roll", stat, dc
# 3. contested → roll immediately

# The Narrator reads resolution_type:
# - "propose_roll" → GM proposes the roll in prose, waits
# - "dice" → narrates the already-rolled outcome
# - "trivial" → narrates freely
# - "narrative" → narrates freely
```

### 5.5 Pre-play turn handler sketch

```python
async def _run_preplay_turn(session_id: str, user_content: str) -> tuple[str, dict]:
    """
    Handles all turns before active play begins.
    Classifies: OOC question | character description | char-creation confirmation
    Transitions phase to "active_play" when character is confirmed.
    """
    session = _SESSIONS.get(session_id)
    # 1. Detect OOC question (rules, "what can I be?", "how does X work?")
    # 2. If OOC: query game system schema + entity archetypes → in-fiction answer
    # 3. If character description: acknowledge, offer mechanical options or transition to active play
    # 4. If char-creation confirmation ("yes, roll" / "use those stats"):
    #    → trigger roll, narrate the result, set phase = "active_play"
    ...
```

---

## 6. Priority Order

| Priority | Use Case | Complexity | Player-facing impact |
|----------|----------|------------|----------------------|
| **P0** | UC-GM-9 Session phase state machine | Medium | Fixes "chat before character" loop failure |
| **P0** | UC-GM-4 OOC question recognition | Low | Fixes the screenshot failure directly |
| **P0** | UC-GM-10 Fiction-first character creation | Medium | Core agency fix |
| **P1** | UC-GM-3 Single in-fiction opening question | Low | Polish, immediate quality |
| **P1** | UC-GM-6 Propose-roll pattern | High | Changes resolver + narrator + frontend |
| **P1** | UC-GM-8 Lore-driven scene opening | Medium | Immersion quality |
| **P2** | UC-GM-7 Narrator persona per system | Medium | Voice consistency |
| **P2** | UC-GM-12 Dice results as GM narration | Medium | Mechanical tone |
| **P2** | UC-GM-2 No metadata leakage | Low | Polish |
| **P3** | UC-GM-5 Graceful failure ambient text | Low | Error path quality |
| **P3** | UC-GM-11 NPC-voice archetype answers | Medium | Discovery quality |
| **P3** | UC-GM-1 Consent-before-roll (part of UC-GM-10) | — | Covered by P0 |

---

## 7. What MONITOR Should Feel Like

**Opening a new session:**
> The Iron Ring hangs in the dark, a rusted knuckle around Inauro.
> Recycled air. Bad lighting. Somewhere, static whispers in the speakers —
> not random, almost shaped.
> Who are you, and why are you still here?

**Player asks an OOC question:**
> Out in the Tenebris system, survival favours different kinds of people.
> There are those who trust their bodies, haulers and fighters who work the
> hull with their hands. There are those who trust their reflexes — pilots,
> thieves, people who move through tight spaces. There are the fix-it types,
> the technical minds who know what's broken before it breaks them.
> And then there are those who talk their way through, trading in information
> and favours when everyone else has run out of options.
> What sounds like you?

**GM proposing a roll:**
> You reach for the panel. Three layers of old repairs, someone's electrical
> tape over someone else's electrical tape. This could go clean — or it could
> take the whole corridor's lighting with it.
> Roll your Tech for me.

**After a critical failure:**
> The panel sparks. Then the corridor lights go red.
> Somewhere below, a pressurization alarm starts. 
> Someone on this station is now looking for whoever did that.
> What do you do?

---

*This document is the design reference for improving the GM loop.*
*All implementation work should reference it and use the UC-GM-N identifiers in commits.*

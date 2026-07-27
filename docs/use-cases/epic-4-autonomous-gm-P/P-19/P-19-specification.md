# P-19: Chat-Guided Session Setup and Character Creation

**Actor:** User
**Trigger:** User starts natural-language onboarding in the chat interface at session start

**Purpose:** Allow MONITOR to guide the player conversationally through selecting a setting, choosing or creating a universe, and building one or more PCs — using the normal chat interface.

**Flow:**
1. User types a natural-language intent such as:
   - "I want a grim fantasy one-shot"
   - "Let me keep playing in my Witcher universe"
   - "Help me make two characters"
2. System extracts likely preferences:
   - multiverse / setting
   - universe / timeline
   - tone and rules system
   - party size and character concepts
3. MONITOR asks targeted follow-up questions in chat for any missing fields
4. Choices are shown back to the user as structured confirmation cards in the same interface
5. On confirmation, MONITOR creates or selects the session, characters, and first story/scene
6. The player continues naturally in the same chat-driven play surface

**Output:** a low-friction onboarding path where MONITOR acts like a real DM guiding setup through chat

### Implementation

**Layer 2 (Agents / runtime):**
- `packages/ui/backend/src/monitor_ui/routers/chat.py` handles the structured setup state and phase transitions (`awaiting_character` → `char_creation` → `active_play`)
- `Narrator` presents the follow-up prompts in the configured tone
- `Resolver` is not used until actual actions/checks begin

**Layer 3 (UI):**
- chat-first onboarding inside the Play Console
- structured confirmation cards for setting, universe, PCs, and story
- seamless handoff from setup chat into active play

---

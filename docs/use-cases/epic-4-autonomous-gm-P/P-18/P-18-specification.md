# P-18: Play Console UI

**Actor:** User
**Trigger:** User enters an active solo-play session in the CLI or web UI

**Purpose:** Provide a unified DM-facing play surface where world selection, party control, narration, rolls, and scene controls are available without switching between multiple pages.

**Flow:**
1. Load the bound play session (`multiverse`, `universe`, `story`, `scene`, controlled PCs, current speaker)
2. Render the **session rail**:
   - current story and scene
   - party roster
   - speaker switcher
   - continue / pause / end-scene controls
3. Render the **main narrative panel**:
   - GM narration
   - player turns
   - NPC/entity dialogue turns
   - quick actions (`Talk`, `Act`, `Inspect`, `Roll`, `Party`, `End Scene`)
4. Render the **context panel**:
   - active character sheet snapshot
   - resources / conditions
   - location and present entities
   - latest roll breakdown or consequence card
5. Accept input through the chat composer as free text, slash commands, or quick actions
6. Each submitted action enters P-3 and the screen updates in place

**Output:** one coherent play surface that feels like a DM console instead of separate admin pages

### Implementation

**Layer 3 (UI):**
```text
Play Home → Session Setup → Play Console → Combat / Audit drawers
```

**Suggested regions:**

| Region | Content |
|--------|---------|
| Left rail | story/scene list, party roster, speaker switch |
| Center | DM chat feed, narration, action composer |
| Right rail | character stats, effects, dice/audit summary |
| Bottom bar | chat input, slash commands, quick action buttons |

---

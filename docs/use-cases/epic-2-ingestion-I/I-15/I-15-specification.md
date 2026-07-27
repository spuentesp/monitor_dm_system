# I-15: Real-Time Session-to-Canon (Live Extraction)

**Actor:** IngestionLoop / SceneLoop
**Trigger:** Live gameplay turns occurring in a session.

**Purpose:** Automatically capture world-state changes and plot events during play without manual note-taking.

**Flow:**
1. `IngestionLoop` receives micro-batches of chat transcript.
2. `SessionListenerModule` extracts events and lore.
3. Distinguishes between "Plot Events" (something happened) and "Lore" (revealed fact).
4. Creates `ProposedChange` documents in MongoDB linked to the current scene.

**Output:** Proposed events/facts staged for canonization.

---

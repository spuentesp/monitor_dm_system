# MONITOR — System Description

> **Multi-Ontology Narrative Intelligence Through Omniversal Representation**

---

## One-Sentence Pitch

A persistent narrative intelligence system that can build worlds, run solo RPGs, and assist human Game Masters by remembering everything that matters and reacting like a coherent storyteller.

---

## 1. What It Is

MONITOR is a **narrative intelligence system** that can create, understand, run, and assist tabletop role-playing games across one or multiple worlds.

It operates in three distinct modes:

| Mode | Description |
|------|-------------|
| **World Architect** | Builds and maintains fictional worlds and multiverses from structured and unstructured sources |
| **Autonomous Game Master** | Runs full solo RPG experiences with turn-by-turn narration and rules enforcement |
| **Game Master Assistant** | Supports human-led campaigns by recording, tracking, recalling, and analyzing sessions |

The system treats **worlds, characters, events, and stories as persistent entities that evolve over time**.

---

## 2. Core Objectives

What success looks like:

| ID | Objective | Description |
|----|-----------|-------------|
| **O1** | Persistent Fictional Worlds | Create and maintain consistent worlds that retain facts, history, entities, and causal continuity across sessions |
| **O2** | Playable Narrative Experiences | Deliver full solo RPG gameplay where the system narrates, adjudicates rules, and reacts meaningfully to player choices |
| **O3** | System-Agnostic Rules Handling | Support multiple RPG systems (dice, cards, custom mechanics) without hard-coding any single game |
| **O4** | Assisted Human GMing | Act as a reliable co-pilot for live or recorded sessions: remembering what happened, tracking consequences, and surfacing useful insights |
| **O5** | World Evolution Over Time | Allow worlds and characters to change permanently based on play, not reset between sessions |

---

## 3. Epics

### EPIC 1 — World & Multiverse Definition

**Goal:** Allow users to create, expand, and modify fictional worlds with structured consistency.

**Capabilities:**
- Define worlds, universes, and multiverses
- Store facts, locations, factions, rules of reality
- Track canonical vs optional or alternative truths

**Key Use Cases:**
- Ingest a setting book or PDF and extract:
  - Geography
  - Cultures
  - Magic/technology rules
- Manually add or edit world facts
- Fork timelines or alternate universes
- Ask factual questions about the world ("What gods exist in this region?")

---

### EPIC 2 — Knowledge & Memory Ingestion

**Goal:** Convert external information into usable world knowledge.

**Capabilities:**
- Ingest:
  - Written lore
  - Session summaries
  - Player notes
  - Transcripts or recordings
- Distinguish:
  - Facts
  - Rumors
  - Character beliefs
  - Player knowledge vs character knowledge

**Key Use Cases:**
- Upload campaign notes → world memory updates
- Record a live session → automatic event timeline
- Ask: "What did the party promise the Duke?"
- Detect contradictions or unresolved threads

---

### EPIC 3 — Character Creation & Identity Management

**Goal:** Support persistent player characters and NPCs across stories.

**Capabilities:**
- Create player characters tied to:
  - A world
  - A rule system
- Maintain:
  - Stats
  - Inventory
  - Relationships
  - Psychological traits
- Allow characters to reappear as NPCs in other stories

**Key Use Cases:**
- Create a solo character and start a campaign
- Import an existing character sheet
- Reuse a past PC as an NPC in a new story
- Ask: "How would this character realistically react?"

---

### EPIC 4 — Autonomous Narrative Game Master

**Goal:** Run a complete RPG session without a human GM.

**Capabilities:**
- Scene-based narration
- Turn-by-turn interaction
- Player choice → world reaction
- Maintain tone, genre, and pacing
- Track unresolved consequences

**Key Use Cases:**
- Play a solo campaign like an interactive novel
- Switch between:
  - Freeform roleplay
  - Structured turns
- Pause, rewind, or branch the story
- Ask the GM for clarification or summaries mid-session

---

### EPIC 5 — Rules & Randomization Engine

**Goal:** Apply RPG mechanics consistently and transparently.

**Capabilities:**
- Support:
  - Dice systems (d20, dice pools, percentiles)
  - Card-based systems
  - Custom probability rules
- Enforce:
  - Success/failure logic
  - Partial successes
  - Narrative consequences

**Key Use Cases:**
- Roll dice automatically when required
- Explain why an outcome happened
- Override or house-rule mechanics
- Ask: "What are my odds if I try this?"

---

### EPIC 6 — Session Tracking & Timeline Management

**Goal:** Treat gameplay as a sequence of meaningful events.

**Capabilities:**
- Record:
  - Scenes
  - Actions
  - Decisions
  - Outcomes
- Maintain:
  - World timelines
  - Character timelines
- Enable querying past events

**Key Use Cases:**
- Review last session summary
- Ask: "When did this NPC betray us?"
- Detect dangling plot threads
- Generate recaps for players

---

### EPIC 7 — Human GM Assistant Mode

**Goal:** Augment, not replace, a human Dungeon Master.

**Capabilities:**
- Listen to or ingest live sessions
- Track:
  - NPC names
  - Improvised lore
  - Player decisions
- Suggest:
  - Plot hooks
  - Consequences
  - Continuations

**Key Use Cases:**
- GM runs a live table; system records canon
- Ask mid-campaign:
  - "What threads have I not resolved?"
- Generate prep notes for next session
- Detect inconsistencies introduced accidentally

---

### EPIC 8 — Planning & Meta-Narrative Tools

**Goal:** Help design stories without breaking immersion.

**Capabilities:**
- Plan arcs without forcing outcomes
- Model factions, tensions, and goals
- Simulate "what if" scenarios

**Key Use Cases:**
- Ask: "What happens if the kingdom collapses?"
- Design a mystery with multiple valid solutions
- Balance player agency with narrative pressure

---

## 4. System Modes

| Mode | Who Leads | System Role | CLI Command | Use Cases |
|------|-----------|-------------|-------------|-----------|
| **Solo Play** | Player | Full GM | `monitor play` | P-1 to P-12 |
| **Assisted GM** | Human GM | Memory + Analyst | `monitor copilot` | CF-1 to CF-5 |
| **World Design** | User | Architect | `monitor manage` | M-1 to M-30 |
| **Post-Session Analysis** | User | Archivist | `monitor copilot`, `monitor query` | CF-2, CF-3, Q-* |

### Additional Commands

| Command | Purpose | Use Cases |
|---------|---------|-----------|
| `monitor query` | Search and explore canon | Q-1 to Q-8 |
| `monitor ingest` | Upload and process documents | I-1 to I-5 |
| `monitor story` | Arc planning, faction modeling, what-if | ST-1 to ST-5 |
| `monitor rules` | Game system definition | RS-1 to RS-4 |

---

## 5. Non-Goals

The system does **NOT**:

- Force stories toward predefined endings
- Replace player agency
- Require a single RPG system
- Assume combat-only gameplay

---

## 6. Epic → Use Case Alignment

> Cross-reference to `docs/USE_CASES.md`

### Use Cases by Category

| Category | Prefix | Count | Description |
|----------|--------|-------|-------------|
| Play | `P-` | 12 | Core gameplay loop |
| Manage | `M-` | 30 | World administration |
| Query | `Q-` | 8 | Canon exploration |
| Ingest | `I-` | 5 | Knowledge import |
| System | `SYS-` | 8 | App lifecycle |
| Co-Pilot | `CF-` | 5 | Human GM assistant |
| Story | `ST-` | 5 | Planning & meta-narrative |
| Rules | `RS-` | 4 | Game system definition |

### Epic Mapping

| Epic | Use Cases | Coverage |
|------|-----------|----------|
| **EPIC 0** — Data Layer Access | DL-1 to DL-14 (canonical data/MCP interfaces) | Defined |
| **EPIC 1** — World & Multiverse | M-1 to M-8 (hierarchy), M-23 to M-25 (axioms), M-30 (time) | Complete |
| **EPIC 2** — Knowledge Ingestion | I-1 to I-6 | Complete |
| **EPIC 3** — Character & Identity | M-12 to M-22 (entities, characters, memories) | Complete |
| **EPIC 4** — Autonomous GM | P-1 to P-8, P-11, P-12 (play loop) | Complete |
| **EPIC 5** — Rules & Randomization | P-4, P-9, P-10, **RS-1 to RS-4** (game systems) | Complete |
| **EPIC 6** — Session & Timeline | M-26 to M-30 (facts, scenes, time), Q-5 (timeline) | Complete |
| **EPIC 7** — Human GM Assistant | CF-1 to CF-5 (co-pilot features) | Complete |
| **EPIC 8** — Planning & Meta-Narrative | ST-1 to ST-5 (story planning) | Complete |
| **EPIC 9** — Documentation | DOC-1 | Defined |

### Use Case Summary

| Prefix | Name | Count | Epic |
|--------|------|-------|------|
| `DL-` | Data Layer | 14 | EPIC 0 |
| `P-` | Play | 12 | EPIC 4, 5 |
| `M-` | Manage | 30 | EPIC 1, 3, 6 |
| `Q-` | Query | 9 | EPIC 6 |
| `I-` | Ingest | 6 | EPIC 2 |
| `SYS-` | System | 10 | — |
| `CF-` | Co-Pilot | 5 | EPIC 7 |
| `ST-` | Story Planning | 5 | EPIC 8 |
| `RS-` | Rules | 4 | EPIC 5 |
| `DOC-` | Documentation | 1 | EPIC 9 |

**Total: 96 use cases**

---

## 7. Document Map

| Document | Purpose |
|----------|---------|
| `SYSTEM.md` | **This file** — Product vision and epics |
| `ARCHITECTURE.md` | Technical layer architecture |
| `STRUCTURE.md` | Repository folder definitions |
| `docs/USE_CASES.md` | Detailed use case specifications |
| `docs/AI_DOCS.md` | Quick reference for implementation |
| `packages/*/IMPLEMENTATION.md` | Layer-specific task lists |

# NPC Social Play Architecture

> Purpose: define the canonical Phase 4 design for durable NPC social memory, relationship canonization, and organic conversation consequences.
>
> Canonical references:
> - `docs/architecture/AGENT_ORCHESTRATION.md`
> - `docs/architecture/CONVERSATIONAL_LOOPS.md`
> - `docs/use-cases/play/P-17.yml`
> - `packages/agents/src/monitor_agents/npc_voice.py`
> - `packages/agents/src/monitor_agents/loops/conversation_loop.py`
> - `packages/data-layer/src/monitor_data/schemas/npc_profiles.py`
> - `packages/data-layer/src/monitor_data/schemas/relationships.py`

## Why this doc exists

MONITOR already has most of the raw building blocks for NPC play:

- `ConversationLoop` for DIRECT / ACTOR dialogue sessions
- `NPCVoice` for live NPC speech
- `NPCProfile` for personality and relationship snapshots in MongoDB
- `CharacterMemory` + Qdrant recall for episodic memory
- `ProposedChange` + `CanonKeeper` for canon-safe writes

What is still missing is a **single architecture** that explains how those parts should work together so NPCs feel:

- persistent across scenes
- asymmetrical and human rather than binary
- sensitive to history, leverage, and tone
- canon-safe under MONITOR's existing write rules

This document is the design target for Phase 4. It is intentionally architecture-first and implementation-second.

---

## Design goals

1. **Organic, not gamey**
   - NPCs should not flip from friendly to hostile because of a single line unless the fiction clearly warrants it.
   - Social drift should usually be incremental, contextual, and evidence-backed.

2. **Asymmetrical relationships**
   - `NPC → PC` and `PC → NPC` are not assumed to match.
   - Trust, fear, admiration, resentment, and obligation can coexist.

3. **Memory-backed behavior**
   - NPCs should remember *why* they feel a certain way, not only a numeric score.
   - Recalled memories should shape tone, suspicion, warmth, and what the NPC volunteers.

4. **Layer-safe canonization**
   - `NPCVoice` and `ConversationLoop` stage proposals only.
   - `CanonKeeper` remains the sole path for Neo4j writes.

5. **Scene-aware but reusable**
   - Social state should work both in direct NPC conversation and inside the main scene loop.
   - The same social state must be queryable by later scenes, not only by the conversation that created it.

---

## Non-goals

This phase does **not** aim to build:

- a full romance-sim subsystem
- perfect psychological simulation
- per-token sentiment analytics
- player reputation across the entire multiverse in one pass

The objective is a robust narrative-social architecture that feels believable in live play.

---

## Core architecture

### Storage roles

| Layer / Store | Purpose | Source of truth for | Write authority |
|---|---|---|---|
| `MongoDB: conversations` | direct session transcript + turn-level emotional state | current dialogue session | `NPCVoice`, `ConversationLoop` |
| `MongoDB: npc_profiles` | working social model and personality state | mutable NPC psychology and per-target stance snapshots | `NPCVoice` (working updates), later reviewed updates |
| `MongoDB: proposed_changes` | staged social consequences awaiting canon review | candidate social/canon changes | any proposing agent |
| `MongoDB: memories` + `Qdrant` | episodic recall with emotional coloring | what the NPC remembers | `NPCVoice`, `Narrator` |
| `Neo4j: Entity relationships + state tags` | accepted, canonical social facts | long-lived relationship truth | `CanonKeeper` only |

### Canon boundary

The core rule is unchanged:

- **conversation sessions are working space**
- **scene end / checkpoint is canonization time**
- **CanonKeeper decides what becomes world truth**

This keeps NPC social play expressive without letting every fleeting mood become permanent canon.

---

## Social state model

### 1. Working social snapshot in `NPCProfile`

`NPCProfile.relationship_states[target_entity_id]` should be treated as a **standardized social snapshot**, not an arbitrary dict.

Recommended shape:

```json
{
  "stance": "guarded",
  "trust": 0.15,
  "affinity": 0.10,
  "fear": 0.35,
  "leverage": 0.40,
  "familiarity": 0.55,
  "interest": 0.20,
  "last_shift_reason": "The PC protected me during the salvage dispute.",
  "last_scene_id": "<uuid>",
  "last_turn_id": "<uuid>",
  "memory_anchor_ids": ["<uuid>", "<uuid>"],
  "updated_at": "<iso8601>"
}
```

#### Semantics

- `stance`: short narrative label for fast prompt injection and UI display
- `trust`: confidence the NPC places in the target's honesty / reliability
- `affinity`: warmth, fondness, attraction, or positive identification
- `fear`: how dangerous or destabilizing the target feels
- `leverage`: how much the target currently has over the NPC
- `familiarity`: how well the NPC knows the target
- `interest`: curiosity / fixation / narrative pull

All values are normalized and **slow-moving by default**.

### 2. Emotional state model

For organic behavior, separate:

- **internal emotional state** — what the NPC actually feels
- **surface emotional state** — what the NPC shows outwardly

The existing `NPCProfile.current_emotional_state` can hold the dominant internal state. Surface emotion belongs in turn/session metadata unless we later formalize it.

This matters because good NPC play includes:

- polite speech masking resentment
- fear hidden behind bravado
- warmth under guarded formality

### 3. Canonical relationship representation in Neo4j

Accepted social outcomes should become directional edges and/or state tags in Neo4j.

#### Structural relationship examples
- `KNOWS`
- `ALLIED_WITH`
- `HOSTILE_TO`
- `WORKS_FOR`
- `OWNS`

#### Emotional relationship examples
- `TRUSTS`
- `DISTRUSTS`
- `FEARS`
- `ADMIRES`
- `LOVES`
- `HATES`
- `LOYAL_TO`
- `INDEBTED_TO`

#### Edge properties

```json
{
  "strength": 0.62,
  "confidence": 0.81,
  "last_updated": "<iso8601>",
  "source_scene_id": "<uuid>",
  "source_turn_ids": ["<uuid>", "<uuid>"],
  "reason": "The PC took a risk to protect the NPC.",
  "canon_level": "canon",
  "authority": "system"
}
```

These are **directional** and should not be auto-mirrored.

---

## Runtime flow

### A. Direct NPC conversation (`ConversationLoop`)

```text
open session
  -> load NPC profile + memories + prior relationship snapshot
  -> player speaks
  -> NPCVoice computes a social beat
  -> turn persisted to MongoDB
  -> working social state updated in MongoDB
  -> proposals staged for CanonKeeper
close session
  -> proposals remain attached to scene/story context
  -> CanonKeeper reviews at checkpoint / scene end
```

### B. Scene-integrated social play (`SceneLoop`)

When a player speaks to an NPC inside an active scene, the conversation outcome should feed back into the scene loop as:

- relationship deltas
- state tags (`friendly`, `hostile`, `revealed`, etc.)
- follow-up facts
- new memory anchors

That way a conversation can change later narration in the *same scene* and later scenes as well.

### C. Actor mode

Actor mode remains a GM-facing introspection path, but any durable insight still becomes a staged proposal instead of a direct write.

---

## The per-turn “social beat” contract

The current `relationship_delta: "trust:+0.1"` string is too weak for organic play.

Phase 4 should move toward a structured per-turn social beat like:

```json
{
  "npc_response": "...",
  "internal_emotion_after": "uneasy respect",
  "surface_emotion_after": "guarded",
  "social_read": {
    "target_entity_id": "<uuid>",
    "stance_after": "guarded but warming",
    "deltas": {
      "trust": 0.12,
      "affinity": 0.05,
      "fear": -0.04,
      "leverage": 0.00
    },
    "reason": "The player offered costly help without pressing for payment.",
    "confidence": 0.76,
    "trigger_ids": ["<trigger-id>"],
    "memory_anchor_required": true
  },
  "proposal_candidates": [ ... ]
}
```

This gives the system enough structure to behave consistently without flattening the dialogue into a scoreboard.

---

## Proposal architecture

### Proposal types needed for Phase 4

These proposal types should be canonical and intentional:

1. **`relationship`**
   - create/update structural or emotional edge in Neo4j
   - example: NPC now `TRUSTS` the PC at strength `0.6`

2. **`state_change`**
   - update entity state tags such as `friendly`, `hostile`, `revealed`, `frightened`

3. **`fact`**
   - store a concise world fact when the conversation establishes something durable
   - example: “Marta promised to smuggle the crew out if they bring her the black box.”

4. **`npc_profile_update`** *(working-space, not direct canon)*
   - update MongoDB profile state such as emotional baseline, new trigger, or speech shift
   - may optionally generate a canonical follow-up proposal if the change should affect world truth

### CanonKeeper responsibilities

`CanonKeeper` should decide whether a social beat is:

- **ephemeral** → keep only in Mongo working state / memory
- **scene-relevant** → keep in working state and scene checkpoint
- **canon-worthy** → commit to Neo4j relationship/state tag/fact updates

This is the correct place to prevent over-canonization from weak conversational signals.

---

## Naturalness rules

These rules are necessary if the system is to feel human and organic.

### 1. Do not overreact to one line

A single exchange should rarely create a dramatic permanent shift unless it includes one of the following:

- confession of major truth
- betrayal, lie exposed, or direct threat
- rescue / sacrifice / abandonment under pressure
- major request granted or refused at cost

### 2. Relationships are asymmetric

If the NPC admires the player while the player resents the NPC, both can be true.
Do **not** auto-sync both sides.

### 3. Memory matters more than raw delta

The system should prefer remembered reasons such as:

- “you lied to me at the dock”
- “you spared my brother”
- “you knew my real name and didn’t use it against me”

over naked numbers.

### 4. Surface and interior can differ

NPCs should be able to:

- speak calmly while afraid
- flatter while hostile
- test the player before showing trust

### 5. Repetition compounds

Several small aligned beats may justify a large shift even if no single turn would.

### 6. Strong baselines resist sudden change

An NPC with deep fear, ideology, debt, or trauma should not be easily swayed without repeated evidence.

---

## Edge cases that the design must handle

| Edge case | Required behavior |
|---|---|
| **Conflicting signals in one conversation** | allow mixed movement: trust can rise while fear also rises |
| **Multi-NPC conversations** | track deltas per NPC, not one global social result |
| **No existing profile** | fall back gracefully to neutral defaults and create working profile state |
| **Player lies successfully** | update trust only if the NPC has evidence later; immediate trust rise may later invert |
| **Player apologizes after harm** | allow partial recovery over several turns; no instant reset |
| **NPC is masking emotion** | surface tone may differ from `current_emotional_state` |
| **Conversation interrupted by violence / scene escalation** | flush working social state into scene checkpoint before leaving the sub-loop |
| **Third-party gossip / faction alignment** | other entities may inherit moderated stance drift when facts implicate allies or rivals |
| **Long gaps between scenes** | recent emotional sharpness can decay while core facts remain |
| **Retcon / GM override** | GM may override relationship state via explicit proposal or admin tools |
| **Low-confidence weak social signal** | keep in memory/working state only; do not canonize |
| **Repeated harassment or manipulation** | accumulate trigger risk, distrust, and hostility even if each single line is subtle |

---

## Required API / MCP work before implementation

Phase 4 should not proceed without a clear contract for the missing writes.

### Already present
- `mongodb_get_npc_profile`
- `mongodb_update_npc_profile`
- `mongodb_create_proposed_change`
- `neo4j_create_relationship`
- `neo4j_update_state_tags`

### Missing or strongly recommended

1. **`neo4j_upsert_emotional_relationship`**
   - upsert directional emotional edges with `strength`, `confidence`, `reason`, `updated_at`
   - avoids abusing generic relationship creation for every social change

2. **`neo4j_list_emotional_relationships`**
   - retrieve NPC social context directly for prompt assembly, debugging, and UI

3. **`mongodb_get_npc_social_snapshot`** *(optional convenience layer)*
   - return normalized `relationship_states` + recent memory anchors for a given target entity

4. **chat/session state extension for social diagnostics**
   - expose the latest NPC stance and relationship snapshot in the same way current persistence now exposes working state

---

## Implementation order after design approval

### Slice 1 — Social contract normalization
- standardize `relationship_states` shape in `NPCProfile`
- replace freeform `relationship_delta` strings with structured social-beat data
- define proposal payloads for social consequences

### Slice 2 — CanonKeeper social routing
- add canonical handling for emotional/structural relationship proposals
- add confidence / threshold rules to avoid over-canonization
- upsert emotional edges in Neo4j

### Slice 3 — Memory-backed response shaping
- inject relationship snapshot + relevant memories into `NPCVoice`
- make triggers and remembered harms/favors shape response tone and disclosure

### Slice 4 — UI/debugging surfaces
- expose social stance and emotional drift in chat state / debug responses
- keep this visible for tuning and benchmark review

### Slice 5 — E2E validation
- prove that an NPC conversation changes later behavior in a later scene
- include at least:
  - trust gain after help
  - distrust after betrayal
  - mixed response when fear and admiration coexist

---

## Acceptance standard for Phase 4

Phase 4 is only complete when all of the following are true:

- the same NPC reacts differently in later scenes because of prior social play
- relationship changes are queryable from Neo4j after CanonKeeper approval
- NPC profiles preserve nuanced working state in MongoDB
- Qdrant-backed memory recall reflects prior hurts, debts, promises, and acts of care
- social change is incremental and believable rather than binary or random

---

## Recommendation

Do **not** continue Phase 4 implementation until the repo agrees on this contract:

1. what a social beat returns
2. what is working state vs canonical state
3. which proposal types are allowed
4. what thresholds make a social change durable

Once that is agreed, implementation can proceed in narrow, test-first slices without architecture churn.

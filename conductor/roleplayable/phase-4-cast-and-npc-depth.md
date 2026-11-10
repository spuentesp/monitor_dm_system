# Phase 4 brief: cast, personas and NPC depth

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** On every turn the GM knows who is who: which characters the user controls, which
one is speaking, which persona is behind each, and which characters are the GM's. NPCs
remember what they lived through and speak only from what they could know.

**Context.** The chat session stores `persona_id`, `speaker_character_id` and
`controlled_character_ids`. `get_scene_loop` in `chat_loops.py` passes one `actor_id` into the
turn, so the rest of the list never reaches the GM, the Narrator or memory extraction. Three
consequences: the Narrator has no rule against speaking or acting for a user-controlled
character who is not the current speaker; memories are written only for the speaker; and a
persona (who the user is across worlds) is linked to its incarnation (the character in this
world) only by seeding interview answers, so the link is lost once play begins. In scene play
the Narrator writes all NPC dialogue from an `NPC STATE` block with no per-NPC recall. Canon
facts are global to a universe, so any NPC can speak about anything.

**You own.** In `packages/agents/src/monitor_agents/`: a new `cast.py`; `turn_context.py`;
the `narrate`, `extract_memories` and `persist_memories_node` nodes in `loops/scene_loop.py`;
`narrator/`, `extraction/`, `npc_voice/`, and the inputs of `gm_agent.py`. In
`packages/ui/backend/src/monitor_ui/routers/`: `get_scene_loop` in `chat_loops.py`,
`character_resolution.py`, `character_storage.py`. In
`packages/data-layer/src/monitor_data/schemas/`: `memories.py`, `facts.py` (additive fields
only). In the frontend: the cast panel in the play console.

**Do not touch.** Story loop, context assembly, ledger (Phase 3). Pre-play (Phase 2). Rebase
on Phase 3 before opening your PR; you both edit `scene_loop.py` and `chat_loops.py`.

## Tasks

1. **Cast list.** Build `Cast` once per turn: every entity in the scene with `entity_id`,
   `name`, `role`, `controller` (`user` or `gm`), `is_speaker`, and for user characters
   `persona_id` and persona name. Source it from the session's controlled ids, the scene's
   entities and the party record. Pass it into SceneLoop state and to GMAgent, Narrator and
   the extractor.
2. **Agency rule.** In the GMAgent and Narrator signatures: never decide actions, speech,
   thoughts or feelings for a character whose controller is `user`, speaker or not. Put the
   rule next to the cast input and in the output field, as the existing hallucination guard
   does. Test on prompt construction.
3. **Speaker switching.** When the user switches speaker mid-scene, the cached SceneLoop must
   pick it up on the next turn. `scene_loop_signature` already includes the actor; confirm the
   cast refreshes and add a test with two controlled characters alternating.
4. **Persona link.** Persist the persona-to-incarnation link on the character record at
   pre-play finalize (Phase 2 writes the character; you add the field and read it). A persona
   playing in two worlds has two incarnations and one identity. Show it in the cast.
5. **Cast panel.** In the play console, a compact list: user characters first with the speaker
   marked, then NPCs present. Clicking a user character makes it the speaker.
6. **NPC scene memory.** At scene end, run `MemoryExtractor` once per GM-controlled character
   present, from that character's point of view, and persist under its `entity_id` and
   `universe_id`. Do the same for every user-controlled character present, not only the
   speaker. Replace the raw-text fallback on JSON parse failure with a typed output.
7. **NPC recall in scenes.** For each NPC in the `NPC STATE` block, add its top 3 memories
   relevant to the current action, using the same recall NPCVoice uses.
8. **Who knows what.** Add `witnesses: list[UUID]` to facts and memories written in play,
   filled from the cast. When building an NPC's state block, include only facts that NPC
   witnessed, was told, or that are marked common knowledge. Ingested lore defaults to common
   knowledge.
9. **NPC intent.** Before narration, one LIGHT-tier call per present NPC, capped at 4, returns
   a one-line intent from its agenda, desires and recalled memories. The Narrator receives it
   and may not contradict it.
10. **Confirm what PR #137 brought.** `Sebastian/gm_assist_overhaul` merged into master on
    2026-11-10 (PR #137), so G-9 contradiction depth and G-6 character templates no longer
    need cherry-picking. Read what landed, and use the template and contradiction code where
    the tasks above touch characters and facts instead of writing parallel versions.

## Out of scope

Autonomous PC. Multiplayer with several humans. False or decaying memories.

## Done when

- With two user-controlled characters in a scene, 20 scripted turns produce no narration that
  acts or speaks for the non-speaking one.
- Switching speaker takes effect on the next turn.
- An NPC present in scene 2 has memories of it and refers to one correctly in scene 5.
- An NPC absent from scene 2 does not reveal a fact established only there.
- The cast panel matches the session's controlled ids.
- One live transcript shows the scene 2 to scene 5 recall.

# MONITOR — Full GM System Implementation Plan

> **Goal:** Transform MONITOR from a functional prototype (~70%) into a full-fledged GM system capable of autonomous world-building, immersive session play, and human GM co-pilot assistance.
> **Date:** June 2026.
> **Cross-refs:** [`SYSTEM.md`](../SYSTEM.md), [`ARCHITECTURE.md`](../ARCHITECTURE.md), [`docs/USE_CASES.md`](USE_CASES.md), [`docs/COMPLETION_PLAN.md`](COMPLETION_PLAN.md), [`docs/GM_CRAFT.md`](GM_CRAFT.md).

---

## Current State Summary

| Subsystem | File | Completion | Critical Gap |
|-----------|------|------------|--------------|
| SceneLoop | `loops/scene_loop.py` | ~90% | Active-turn path, resolution persistence, and accepted-roll flow are covered; combat routing and scene-end polish remain |
| StoryLoop | `loops/story_loop.py` | ~55% | Bootstrap/scene-completion paths are safe, but `run_scene` is still externally driven and there is no arc evaluation |
| WorldBuildingLoop | `loops/world_building_loop.py` | ~70% | No relationship extraction between entities |
| ConversationLoop | `loops/conversation_loop.py` | ~75% | No social state tracking depth |
| Resolver | `resolver.py` | ~85% | No opposed checks, no advantage/disadvantage |
| Narrator | `narrator.py` | ~80% | No dynamic length control, persona OK |
| WorldArchitect | `world_architect.py` | ~75% | No semantic conflict detection |
| ContextAssembly | `context_assembly.py` | ~90% | No temporal decay, no token budget |
| CanonKeeper | `canonkeeper.py` | ~90% | No conflict resolution, no rollback |
| GameSystemRuntime | `game_system.py` | ~85% | No combat loop, no advancement |
| NPCVoice | `npc_voice.py` | ~80% | Working actor + direct modes |
| Frontend | `packages/ui/frontend/` | ~60% | Many placeholder views |

---

## Plan Structure

Phases are ordered by **dependency** and **impact**. Each phase produces a playable increment.

```
Phase A → Core Loop Completion (StoryLoop + Combat)
Phase B → Immersive GM Craft (Session Flow + Narrator)
Phase C → Living World (Relationships + Autonomous Evolution)
Phase D → Co-Pilot Mode (Human GM Assistance)
Phase E → Professional Polish (Advancement + Frontend + Testing)
```

---

